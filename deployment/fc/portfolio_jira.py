"""Read-only Jira filter sync. Credentials stay in FC environment variables."""
import base64
import copy
import json
import os
import re
import threading
import time
from datetime import datetime, timezone, timedelta
from urllib.request import Request, HTTPRedirectHandler, build_opener

HOST = 'https://lululemon.atlassian.net'
JQL = 'project IN (CSCOP) AND created >= "2026-01-01" AND created <= "2026-10-22" AND status NOT IN (Cancelled, Closed, Done)'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class JiraService:
    def __init__(self, root, env=None, fetch_page=None, clock=time.monotonic):
        self.env = os.environ if env is None else env
        self.clock = clock
        self.fetch_page = fetch_page or self._fetch_page
        self.data = json.loads((root / 'assets/jira-master-data.json').read_text(encoding='utf8'))
        self.onepage = json.loads((root / 'assets/confluence-onepage-data.json').read_text(encoding='utf8'))
        self.lock = threading.Lock()
        self.busy = False
        self.last_attempt = None
        self.synced_at = None
        self.error = None
        self.configured = bool(self.env.get('ATLASSIAN_EMAIL') and self.env.get('ATLASSIAN_API_TOKEN'))

    def _fetch_page(self, next_token):
        payload = {'jql': JQL, 'maxResults': 100,
                   'fields': ['summary', 'status', 'assignee', 'created', 'updated', 'issuetype']}
        if next_token:
            payload['nextPageToken'] = next_token
        credentials = self.env['ATLASSIAN_EMAIL'] + ':' + self.env['ATLASSIAN_API_TOKEN']
        req = Request(HOST + '/rest/api/3/search/jql', data=json.dumps(payload).encode(),
                      headers={'Accept': 'application/json', 'Content-Type': 'application/json',
                               'Authorization': 'Basic ' + base64.b64encode(credentials.encode()).decode()},
                      method='POST')
        with build_opener(NoRedirect).open(req, timeout=15) as response:
            return json.load(response)

    def _build(self, issues):
        result = copy.deepcopy(self.data)
        projects = []
        rules = result.get('assigneeDomainRules', {})
        excluded = set(result.get('excludedKeys', []))
        seen = set()
        for issue in issues:
            key = issue['key']
            if not re.fullmatch(r'CSCOP-\d+', key) or key in seen:
                raise ValueError('invalid_issue_set')
            seen.add(key)
            if key in excluded:
                continue
            fields = issue['fields']
            owner = (fields.get('assignee') or {}).get('displayName', '')
            related = list(dict.fromkeys(p['domain'] for p in self.onepage['projects'] if key in p.get('references', [])))
            owning = [d for d in related if d != 'SCM Ops'] or related
            confirmed = rules.get(re.sub(r'[^a-z]', '', owner.casefold()))
            domain = confirmed or (owning[0] if len(owning) == 1 else 'Unmapped domain')
            projects.append({'key': key, 'id': key, 'references': [key], 'name': fields['summary'],
                             'domain': domain, 'relatedDomains': related,
                             'status': fields['status']['name'], 'assignee': owner,
                             'created': fields.get('created', ''), 'updated': fields.get('updated', ''),
                             'createdMonth': fields.get('created', '')[:7],
                             'issueType': (fields.get('issuetype') or {}).get('name', ''),
                             'url': HOST + '/browse/' + key})
        result.update(projects=projects, sourceCount=len(issues), displayCount=len(projects),
                      asOf=datetime.now(timezone(timedelta(hours=8))).date().isoformat(), jql=JQL,
                      complete=True, status='ready')
        return result

    def _sync(self):
        try:
            issues, token, tokens = [], None, set()
            for _ in range(100):
                page = self.fetch_page(token)
                if not isinstance(page.get('issues'), list):
                    raise ValueError('invalid_page')
                issues.extend(page['issues'])
                token = page.get('nextPageToken')
                if page.get('isLast') is True:
                    break
                if not token or token in tokens:
                    raise ValueError('incomplete_pagination')
                tokens.add(token)
            else:
                raise ValueError('page_limit')
            data = self._build(issues)
            with self.lock:
                self.data = data
                self.synced_at = datetime.now(timezone.utc).isoformat()
                self.error = None
        except Exception:
            # Never return upstream response bodies, request headers or credentials.
            with self.lock:
                self.error = 'jira_sync_failed'
        finally:
            with self.lock:
                self.busy = False

    def read(self, refresh=True):
        with self.lock:
            now = self.clock()
            if refresh and self.configured and not self.busy and (self.last_attempt is None or now - self.last_attempt >= 60):
                self.last_attempt = now
                self.busy = True
                threading.Thread(target=self._sync, daemon=True).start()
            result = copy.deepcopy(self.data)
            result['sync'] = {'state': 'not_configured' if not self.configured else 'updating' if self.busy else 'stale' if self.error else 'live' if self.synced_at else 'snapshot',
                              'syncedAt': self.synced_at, 'error': self.error,
                              'refreshSeconds': 60, 'onePageAsOf': self.onepage.get('snapshotDate')}
            return result
