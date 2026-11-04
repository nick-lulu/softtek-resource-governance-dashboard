"""Read-only adapter for authoritative per-person Timesheet period totals.

No vendor credentials, source employee IDs or email addresses leave this module.
The source contract is documented in TIMESHEET_API.md; adapt fetch_page only when
Softtek supplies its actual API specification.
"""
import json
import math
import os
import re
import threading
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener

PERIOD = {'startDate': '2026-11-01', 'endDate': '2027-01-31', 'label': 'FY26 Q4'}
HOURS_PER_MD = Decimal('8')
ALIASES = {'nicole_yu': 'nichole_yu', 'eunice_bi': 'bi_yu',
           'xian_wang': 'wang_xian', 'ping_yang': 'yang_ping',
           'daisy': 'daisy_tang', 'dasiy': 'daisy_tang', 'ayla_hou': 'ayla',
           'jade_zhang': 'jade'}


class SourceError(Exception):
    """Sanitized errors only: never include URLs, tokens or source bodies."""


def canonical(value):
    key = re.sub(r'[^a-z0-9]+', '_', str(value or '').strip().lower()).strip('_')
    return ALIASES.get(key, key)


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise SourceError('invalid_actual_hours')
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        raise SourceError('invalid_actual_hours') from None
    if not result.is_finite() or result < 0 or not math.isfinite(float(result)):
        raise SourceError('invalid_actual_hours')
    return result


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Do not forward the Timesheet credential to a redirect destination.
        return None


class TimesheetService:
    def __init__(self, site, environ=None, clock=time.monotonic, fetcher=None):
        self.env = os.environ if environ is None else environ
        self.clock, self.fetcher = clock, fetcher
        self.lock = threading.Lock()
        self.snapshot = None
        self.last_success = None
        self.deadline = 0
        self.error = None
        self.roster = {}
        source = site / 'assets/resource-list-data.json'
        if source.exists():
            bundle = json.loads(source.read_text(encoding='utf8'))
            for domain in bundle['domains']:
                for resource in domain.get('resources', []) + domain.get('roster', []):
                    if resource.get('resourceRef') or not resource.get('name'):
                        continue
                    key = canonical(resource.get('key') or resource['name'])
                    self.roster[key] = resource['name']

    def config(self):
        url = self.env.get('TIMESHEET_API_URL', '').strip()
        basis = self.env.get('TIMESHEET_STATUS_BASIS', '').strip().lower()
        if not url:
            return None, 'not_configured'
        if basis not in ('filled', 'submitted', 'approved'):
            return None, 'status_basis_required'
        parsed = urlsplit(url)
        allow_test = self.env.get('TIMESHEET_ALLOW_LOCAL_TEST') == '1'
        if parsed.scheme != 'https' and not (allow_test and parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1', 'localhost')):
            raise SourceError('https_source_required')
        if not parsed.hostname or parsed.username or parsed.password or parsed.fragment or parsed.query:
            raise SourceError('invalid_source_url')
        try:
            ttl = int(self.env.get('TIMESHEET_POLL_SECONDS', '300'))
            timeout = int(self.env.get('TIMESHEET_TIMEOUT_SECONDS', '10'))
            mapping = json.loads(self.env.get('TIMESHEET_RESOURCE_MAP', '{}'))
        except (ValueError, TypeError):
            raise SourceError('invalid_configuration') from None
        if not 30 <= ttl <= 3600 or not 1 <= timeout <= 30 or not isinstance(mapping, dict):
            raise SourceError('invalid_configuration')
        if any(not isinstance(k, str) or not isinstance(v, str) or canonical(v) not in self.roster for k, v in mapping.items()):
            raise SourceError('invalid_resource_mapping')
        return {'url': url, 'basis': basis, 'ttl': ttl, 'timeout': timeout,
                'mapping': mapping}, None

    def fetch_page(self, config, page):
        if self.fetcher:
            return self.fetcher(config, page)
        params = {'startDate': PERIOD['startDate'], 'endDate': PERIOD['endDate'],
                  'statusBasis': config['basis'], 'page': page, 'pageSize': 500}
        headers = {'Accept': 'application/json'}
        token = self.env.get('TIMESHEET_API_TOKEN', '')
        auth = self.env.get('TIMESHEET_AUTH_MODE', 'bearer')
        if auth == 'bearer' and token:
            headers['Authorization'] = 'Bearer ' + token
        elif auth == 'api-key' and token:
            headers['X-API-Key'] = token
        elif auth != 'none':
            raise SourceError('source_authentication_not_configured')
        if '\r' in token or '\n' in token:
            raise SourceError('invalid_configuration')
        try:
            request = Request(config['url'] + '?' + urlencode(params), headers=headers)
            with build_opener(NoRedirect).open(request, timeout=config['timeout']) as response:
                body = response.read(4 * 1024 * 1024 + 1)
                if len(body) > 4 * 1024 * 1024:
                    raise SourceError('source_response_too_large')
                return json.loads(body)
        except HTTPError as exc:
            raise SourceError('source_authentication_failed' if exc.code in (401, 403) else 'source_http_error') from None
        except (URLError, TimeoutError, OSError):
            raise SourceError('source_unavailable') from None
        except (ValueError, UnicodeError):
            raise SourceError('invalid_source_json') from None

    def pull(self, config):
        result, employee_ids, resource_keys = [], set(), set()
        unmatched = 0
        snapshot_id = None
        request_deadline = time.monotonic() + 40
        for page in range(1, 101):
            if time.monotonic() >= request_deadline:
                raise SourceError('source_refresh_timeout')
            data = self.fetch_page(config, page)
            if not isinstance(data, dict):
                raise SourceError('invalid_source_contract')
            period = data.get('period', {})
            if not isinstance(period, dict) or any(period.get(k) != PERIOD[k] for k in ('startDate', 'endDate')):
                raise SourceError('source_period_mismatch')
            if data.get('statusBasis') != config['basis'] or data.get('unit') != 'hours':
                raise SourceError('source_basis_or_unit_mismatch')
            if data.get('complete') is not True or not isinstance(data.get('resources'), list):
                raise SourceError('incomplete_source_snapshot')
            # Pagination must read the same immutable source snapshot on every page.
            current_snapshot = data.get('snapshotId')
            if not isinstance(current_snapshot, str) or not current_snapshot:
                raise SourceError('source_snapshot_id_required')
            if snapshot_id is None:
                snapshot_id = current_snapshot
            if snapshot_id != current_snapshot:
                raise SourceError('source_snapshot_changed')
            for item in data['resources']:
                if not isinstance(item, dict) or not isinstance(item.get('employeeId'), str) or not item['employeeId'].strip():
                    raise SourceError('employee_id_required')
                employee_id = item['employeeId'].strip()
                if employee_id in employee_ids:
                    raise SourceError('duplicate_employee_total')
                employee_ids.add(employee_id)
                if len(employee_ids) > 50000:
                    raise SourceError('source_record_limit')
                hours = number(item.get('totalHours'))
                key = config['mapping'].get(employee_id) or config['mapping'].get(str(item.get('email') or '').lower())
                # An explicit stable ID mapping takes precedence over exact name matching.
                key = canonical(key or item.get('resourceKey') or item.get('name'))
                if key not in self.roster:
                    unmatched += 1
                    continue
                if key in resource_keys:
                    raise SourceError('multiple_employees_match_one_resource')
                resource_keys.add(key)
                result.append({'resourceKey': key, 'name': self.roster[key],
                               'actualHours': float(hours), 'actualMD': float(hours / HOURS_PER_MD)})
            next_page = data.get('nextPage')
            if next_page is None:
                return {'resources': sorted(result, key=lambda r: r['name']),
                        'matchedResourceCount': len(result), 'unmatchedResourceCount': unmatched}
            if isinstance(next_page, bool) or not isinstance(next_page, int) or next_page != page + 1:
                raise SourceError('invalid_pagination')
        raise SourceError('source_page_limit')

    def read(self, fetch=True):
        try:
            config, pending = self.config()
        except SourceError as exc:
            config, pending = None, str(exc)
        base = {'schemaVersion': 1, 'period': PERIOD, 'hoursPerMD': 8,
                'statusBasis': self.env.get('TIMESHEET_STATUS_BASIS') or None,
                'lastSuccessfulSyncAt': self.last_success,
                'refreshMode': 'read-through', 'refreshIntervalSeconds': config['ttl'] if config else None}
        if pending:
            return {**base, 'status': pending, 'resources': [], 'matchedResourceCount': 0,
                    'unmatchedResourceCount': 0}
        with self.lock:
            if fetch and self.clock() >= self.deadline:
                try:
                    snapshot = self.pull(config)
                    # Replace the cumulative totals atomically, never add snapshots.
                    self.snapshot = snapshot
                    self.last_success = datetime.now(timezone.utc).isoformat()
                    self.error = None
                    self.deadline = self.clock() + config['ttl']
                except SourceError as exc:
                    self.error = str(exc)
                    self.deadline = self.clock() + 30
            status = ('stale' if self.error else 'ready') if self.snapshot else ('unavailable' if self.error else 'pending')
            return {**base, 'status': status, 'lastSuccessfulSyncAt': self.last_success,
                    'errorCode': self.error, **(self.snapshot or {'resources': [],
                    'matchedResourceCount': 0, 'unmatchedResourceCount': 0})}