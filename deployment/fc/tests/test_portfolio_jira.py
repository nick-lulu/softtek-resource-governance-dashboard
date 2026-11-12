import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from portfolio_jira import JiraService, JQL


def issue(key, owner='Nick Han'):
    return {'key': key, 'fields': {'summary': key + ' project', 'status': {'name': 'New'},
                                 'assignee': {'displayName': owner}, 'created': '2026-10-01',
                                 'description': 'PRIVATE MUST NOT LEAVE'}}


class JiraTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'assets').mkdir()
        self.base = {'status': 'ready', 'complete': True, 'asOf': '2026-11-11',
                     'sourceType': 'jira', 'projects': [{'key': 'CSCOP-1'}],
                     'excludedKeys': ['CSCOP-1067'], 'assigneeDomainRules': {'nickhan': 'SCM Ops'}}
        (self.root / 'assets/jira-master-data.json').write_text(json.dumps(self.base))
        (self.root / 'assets/confluence-onepage-data.json').write_text(json.dumps({
            'snapshotDate': '2026-11-11', 'projects': [{'references': ['CSCOP-2'], 'domain': 'Corporate'}]}))
        self.env = {'ATLASSIAN_EMAIL': 'service@example.test', 'ATLASSIAN_API_TOKEN': 'fake-unit-test-secret'}

    def tearDown(self):
        self.temp.cleanup()

    def test_complete_pagination_sanitized_mapping_and_exclusion(self):
        calls = []
        def fetch(token):
            calls.append(token)
            return {'issues': [issue('CSCOP-2', 'Other')], 'nextPageToken': 'second', 'isLast': False} if token is None else {
                'issues': [issue('CSCOP-3'), issue('CSCOP-1067')], 'isLast': True}
        service = JiraService(self.root, self.env, fetch_page=fetch)
        service._sync()
        data = service.read(refresh=False)
        self.assertEqual(calls, [None, 'second'])
        self.assertEqual(data['sourceCount'], 3)
        self.assertEqual(data['displayCount'], 2)
        self.assertEqual([p['domain'] for p in data['projects']], ['Corporate', 'SCM Ops'])
        self.assertEqual(data['sync']['state'], 'live')
        self.assertNotIn('PRIVATE', json.dumps(data))
        self.assertNotIn('fake-unit-test-secret', json.dumps(data))

    def test_failed_or_incomplete_fetch_never_replaces_good_data(self):
        for fetch in [lambda _: {'issues': [issue('CSCOP-2')]},
                      lambda _: {'issues': [issue('CSCOP-2')], 'nextPageToken': 'loop'},
                      lambda _: {'issues': [issue('CSCOP-2'), issue('CSCOP-2')], 'isLast': True}]:
            service = JiraService(self.root, self.env, fetch_page=fetch)
            service._sync()
            data = service.read(refresh=False)
            self.assertEqual(data['projects'], self.base['projects'])
            self.assertEqual(data['sync']['state'], 'stale')

    def test_nonblocking_cache_single_worker_and_ttl(self):
        entered, release = threading.Event(), threading.Event()
        now = [0]
        calls = []
        def fetch(_):
            calls.append(1)
            entered.set()
            release.wait(3)
            return {'issues': [issue('CSCOP-3')], 'isLast': True}
        service = JiraService(self.root, self.env, fetch_page=fetch, clock=lambda: now[0])
        first = service.read()
        self.assertEqual(first['projects'], self.base['projects'])
        self.assertTrue(entered.wait(1))
        service.read()
        self.assertEqual(len(calls), 1)
        release.set()
        for thread in threading.enumerate():
            if thread is not threading.current_thread() and thread.daemon:
                thread.join(1)
        service.read()
        self.assertEqual(len(calls), 1)

    def test_missing_configuration_does_not_fetch(self):
        service = JiraService(self.root, {}, fetch_page=lambda _: self.fail('must not fetch'))
        self.assertEqual(service.read()['sync']['state'], 'not_configured')
        self.assertIn('created <= "2026-10-22"', JQL)


if __name__ == '__main__':
    unittest.main()
