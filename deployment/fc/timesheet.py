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
PROJECT_MONTHS = {
    month: {'startDate': month + '-01', 'endDate': month + '-' + last_day, 'label': month}
    for month, last_day in (('2026-11', '30'), ('2026-12', '31'), ('2027-01', '31'))
}
HOURS_PER_MD = Decimal('8')
TOTALS_REFRESH_SECONDS = 60
UNNUMBERED_PROJECT_CSCOP = {'operation resource pool': 'CSCOP-1139'}
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
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
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
        self.token_lock = threading.Lock()
        self.project_cache = {}
        self.snapshot = None
        self.last_success = None
        self.deadline = 0
        self.error = None
        self.token = None
        self.token_deadline = 0
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
        self.project_locks = {key: threading.Lock() for key in self.roster}

    def config(self):
        url = self.env.get('TIMESHEET_API_URL', '').strip()
        basis = self.env.get('TIMESHEET_STATUS_BASIS', '').strip().lower()
        if not url:
            return None, 'not_configured'
        softtek = self.env.get('TIMESHEET_PROVIDER') == 'softtek'
        if softtek:
            basis = 'filled'
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
        if len(set(canonical(v) for v in mapping.values())) != len(mapping):
            raise SourceError('multiple_emails_match_one_resource')
        if softtek:
            if parsed.path not in ('', '/'):
                raise SourceError('source_base_url_required')
            if not self.env.get('TIMESHEET_AK') or not self.env.get('TIMESHEET_SK'):
                return None, 'source_authentication_not_configured'
            if not mapping:
                return None, 'resource_mapping_required'
            if any(not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email) for email in mapping):
                raise SourceError('invalid_email_mapping')
        return {'url': url, 'basis': basis, 'ttl': ttl, 'timeout': timeout,
                'mapping': mapping, 'provider': 'softtek' if softtek else 'legacy'}, None

    def softtek_post(self, config, path, payload, token=None):
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        request = Request(config['url'].rstrip('/') + path, headers=headers,
                          data=json.dumps(payload).encode('utf8'), method='POST')
        try:
            with build_opener(NoRedirect).open(request, timeout=config['timeout']) as response:
                body = response.read(1024 * 1024 + 1)
            if len(body) > 1024 * 1024:
                raise SourceError('source_response_too_large')
            data = json.loads(body, parse_float=Decimal)
        except HTTPError as exc:
            raise SourceError('source_authentication_failed' if exc.code in (401, 403) else 'source_http_error') from None
        except (URLError, TimeoutError, OSError):
            raise SourceError('source_unavailable') from None
        except (ValueError, UnicodeError):
            raise SourceError('invalid_source_json') from None
        if not isinstance(data, dict):
            raise SourceError('invalid_source_contract')
        # Softtek may return HTTP 200 with a business-level 401.
        if data.get('code') != 200:
            raise SourceError('source_authentication_failed' if data.get('code') == 401 else 'source_business_error')
        return data.get('data')

    def softtek_token(self, config):
        if self.token and self.clock() < self.token_deadline:
            return self.token
        data = self.softtek_post(config, '/open-api/v1/token',
                                 {'ak': self.env['TIMESHEET_AK'], 'sk': self.env['TIMESHEET_SK']})
        if not isinstance(data, dict):
            raise SourceError('invalid_token_response')
        token, expires = data.get('access_token'), data.get('expires_in')
        if not isinstance(token, str) or not token or '\r' in token or '\n' in token:
            raise SourceError('invalid_token_response')
        if isinstance(expires, bool) or not isinstance(expires, (int, Decimal)) or expires <= 0:
            raise SourceError('invalid_token_response')
        self.token, self.token_deadline = token, self.clock() + max(0, float(expires) - 60)
        return token

    def softtek_hours(self, config, path, payload):
        for attempt in range(2):
            with self.token_lock:
                token = self.softtek_token(config)
            try:
                return self.softtek_post(config, path, payload, token)
            except SourceError as exc:
                if str(exc) != 'source_authentication_failed' or attempt:
                    raise
                with self.token_lock:
                    if self.token == token:
                        self.token = None

    def project_summary(self, config, email, project_map, period):
        payload = {'email': email, 'startDate': period['startDate'], 'endDate': period['endDate']}
        rows = self.softtek_hours(config, '/open-api/v1/hours/project-summary', payload)
        if not isinstance(rows, list):
            raise SourceError('invalid_project_summary')
        projects = {}
        for row in rows:
            if not isinstance(row, dict):
                raise SourceError('invalid_project_summary')
            project_no, name = row.get('projectNo'), row.get('projectName')
            value = row.get('totalHours')
            if project_no is None:
                project_no = ''
            if not isinstance(project_no, str) or not isinstance(name, str) or not (project_no.strip() or name.strip()):
                raise SourceError('invalid_project_summary')
            if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
                raise SourceError('invalid_actual_hours')
            project_no = project_no.strip().upper()
            normalized_name = name.strip().casefold()
            if project_no:
                cscop = project_no if re.fullmatch(r'CSCOP-\d+', project_no) else project_map.get(project_no)
            else:
                cscop = UNNUMBERED_PROJECT_CSCOP.get(normalized_name)
            key = ('id', cscop or project_no) if cscop or project_no else ('name', normalized_name)
            project = projects.setdefault(key, {'cscop': cscop, 'projectNo': project_no,
                                               'projectName': '', 'actualHours': Decimal(0)})
            if project_no and not project['projectNo']:
                project['projectNo'] = project_no
                project['projectName'] = name.strip()
            project['projectName'] = project['projectName'] or name.strip()
            project['actualHours'] += number(value)
        return [{**project, 'actualHours': float(number(project['actualHours'])),
                 'actualMD': float(project['actualHours'] / HOURS_PER_MD)}
                for project in projects.values()]

    def read_projects(self, resource_key, fetch=True, month=None):
        period = PROJECT_MONTHS[month] if month else PERIOD
        base = {'schemaVersion': 1, 'resourceKey': resource_key, 'period': period,
                'hoursPerMD': int(HOURS_PER_MD), 'projects': [], 'lastSuccessfulSyncAt': None}
        if resource_key not in self.roster:
            return {**base, 'status': 'unknown_resource'}
        try:
            config, pending = self.config()
            if pending or config['provider'] != 'softtek':
                return {**base, 'status': pending or 'not_configured'}
            email = next((email for email, key in config['mapping'].items()
                          if canonical(key) == resource_key), None)
            if not email:
                return {**base, 'status': 'resource_mapping_required'}
            raw_map = json.loads(self.env.get('TIMESHEET_PROJECT_MAP', '{}'))
            if not isinstance(raw_map, dict):
                raise ValueError
            project_map = {}
            for project_no, cscop in raw_map.items():
                if not project_no.strip() or not isinstance(cscop, str) or not re.fullmatch(r'CSCOP-\d+', cscop.strip(), re.I):
                    raise ValueError
                project_map[project_no.strip().upper()] = cscop.strip().upper()
        except (ValueError, TypeError, SourceError):
            return {**base, 'status': 'invalid_configuration'}
        cache_key = (resource_key, month, email, config['url'], tuple(sorted(project_map.items())))
        with self.project_locks[resource_key]:
            cached = self.project_cache.get(cache_key)
            if not fetch:
                return {**base, **(cached[1] if cached else {'status': 'pending'})}
            if cached and self.clock() < cached[0]:
                return {**base, **cached[1]}
            try:
                payload = {'status': 'ready', 'projects': self.project_summary(config, email, project_map, period),
                           'lastSuccessfulSyncAt': datetime.now(timezone.utc).isoformat()}
                interval = config['ttl']
            except SourceError:
                payload = ({**cached[1], 'status': 'stale'} if cached and cached[1].get('lastSuccessfulSyncAt')
                           else {'status': 'unavailable'})
                interval = 30
            self.project_cache[cache_key] = (self.clock() + interval, payload)
            return {**base, **payload}

    def pull_softtek(self, config):
        result = []
        emails = sorted(config['mapping'])
        started = time.monotonic()
        for offset in range(0, len(emails), 100):
            if time.monotonic() - started > 35:
                raise SourceError('source_refresh_timeout')
            batch = emails[offset:offset + 100]
            payload = {'emails': batch, 'startDate': PERIOD['startDate'], 'endDate': PERIOD['endDate']}
            rows = self.softtek_hours(config, '/open-api/v1/hours/summary', payload)
            if not isinstance(rows, list) or len(rows) != len(batch):
                raise SourceError('incomplete_source_snapshot')
            seen = set()
            for row in rows:
                if not isinstance(row, dict):
                    raise SourceError('invalid_source_contract')
                email = row.get('email')
                if not isinstance(email, str) or email not in batch or email in seen:
                    raise SourceError('unexpected_response_identity')
                seen.add(email)
                value = row.get('totalHours')
                if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
                    raise SourceError('invalid_actual_hours')
                hours = number(value)
                key = canonical(config['mapping'][email])
                result.append({'resourceKey': key, 'name': self.roster[key],
                               'actualHours': float(hours), 'actualMD': float(hours / HOURS_PER_MD)})
        return {'resources': sorted(result, key=lambda r: r['name']),
                'matchedResourceCount': len(result), 'unmatchedResourceCount': 0}

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
        if config['provider'] == 'softtek':
            return self.pull_softtek(config)
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
                'statusBasis': config['basis'] if config else None,
                'lastSuccessfulSyncAt': self.last_success,
                'refreshMode': 'read-through',
                'refreshIntervalSeconds': TOTALS_REFRESH_SECONDS if config and config['provider'] == 'softtek' else config['ttl'] if config else None,
                'rosterResourceCount': len(self.roster),
                'configuredResourceCount': len(config['mapping']) if config else 0}
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
                    interval = TOTALS_REFRESH_SECONDS if config['provider'] == 'softtek' else config['ttl']
                    self.deadline = self.clock() + interval
                except SourceError as exc:
                    self.error = str(exc)
                    self.deadline = self.clock() + 30
            status = ('stale' if self.error else 'ready') if self.snapshot else ('unavailable' if self.error else 'pending')
            return {**base, 'status': status, 'lastSuccessfulSyncAt': self.last_success,
                    'errorCode': self.error, **(self.snapshot or {'resources': [],
                    'matchedResourceCount': 0, 'unmatchedResourceCount': 0})}
