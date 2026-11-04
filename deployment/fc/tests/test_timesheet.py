import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from timesheet import TimesheetService, SourceError


def payload(hours=16, **extra):
    return {'period': {'startDate': '2026-11-01', 'endDate': '2027-01-31'},
            'unit': 'hours', 'statusBasis': 'submitted', 'complete': True,
            'snapshotId': 'source-export-1', 'nextPage': None,
            'resources': [{'employeeId': 'E1', 'name': 'Nick Han', 'totalHours': hours}], **extra}


class TimesheetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.site = Path(self.temp.name)
        (self.site / 'assets').mkdir()
        roster = {'domains': [{'resources': [
            {'name': 'Nick Han', 'key': 'nick_han'},
            {'name': 'Nichole Yu', 'key': 'nichole_yu'},
            {'name': 'Bi Yu', 'key': 'bi_yu'}]}]}
        (self.site / 'assets/resource-list-data.json').write_text(json.dumps(roster))
        self.env = {'TIMESHEET_API_URL': 'https://timesheet.example/api/totals',
                    'TIMESHEET_STATUS_BASIS': 'submitted'}
        self.now = 0

    def tearDown(self):
        self.temp.cleanup()

    def service(self, fetcher, env=None):
        return TimesheetService(self.site, self.env if env is None else env,
                                clock=lambda: self.now, fetcher=fetcher)

    def test_not_configured_never_fabricates_zero(self):
        s = self.service(lambda *_: self.fail('Must not fetch'), {})
        self.assertEqual(s.read()['status'], 'not_configured')
        self.assertEqual(s.read()['resources'], [])

    def test_status_basis_is_required(self):
        s = self.service(lambda *_: self.fail('Must not fetch'), {'TIMESHEET_API_URL': self.env['TIMESHEET_API_URL']})
        self.assertEqual(s.read()['status'], 'status_basis_required')

    def test_hours_conversion_zero_and_missing_are_distinct(self):
        p = payload(0)
        s = self.service(lambda *_: p)
        d = s.read()
        self.assertEqual(d['status'], 'ready')
        self.assertEqual(d['resources'][0]['actualMD'], 0)
        self.assertFalse(any(r['resourceKey'] == 'bi_yu' for r in d['resources']))

    def test_cumulative_snapshots_replace_including_reductions(self):
        source = payload(16)
        calls = []
        def fetch(*_):
            calls.append(1)
            return source
        s = self.service(fetch)
        self.assertEqual(s.read()['resources'][0]['actualMD'], 2)
        self.assertEqual(s.read()['resources'][0]['actualMD'], 2)
        self.assertEqual(len(calls), 1)
        source['resources'][0]['totalHours'] = 8
        self.now = 301
        self.assertEqual(s.read()['resources'][0]['actualMD'], 1)

    def test_decimal_hours_keep_precision(self):
        s = self.service(lambda *_: payload('7.25'))
        self.assertEqual(s.read()['resources'][0]['actualMD'], .90625)

    def test_cross_domain_same_person_one_source_total(self):
        p = payload()
        p['resources'][0].update(name='Nicole Yu', employeeId='E2')
        s = self.service(lambda *_: p)
        self.assertEqual(s.read()['resources'][0]['resourceKey'], 'nichole_yu')
        self.assertEqual(s.read()['matchedResourceCount'], 1)

    def test_stable_identity_mapping_and_public_redaction(self):
        env = {**self.env, 'TIMESHEET_RESOURCE_MAP': '{"E1":"bi_yu"}', 'TIMESHEET_API_TOKEN': 'sensitive-test-token'}
        p = payload();p['resources'][0]['email'] = 'private@example.com'
        d = self.service(lambda *_: p, env).read()
        self.assertEqual(d['resources'][0]['resourceKey'], 'bi_yu')
        text = json.dumps(d)
        for private in ('private@example.com', 'E1', 'sensitive-test-token', 'timesheet.example'):
            self.assertNotIn(private, text)

    def test_unknown_person_is_not_silently_added_to_scope(self):
        p = payload();p['resources'][0]['name'] = 'Unknown Person'
        d = self.service(lambda *_: p).read()
        self.assertEqual(d['resources'], [])
        self.assertEqual(d['unmatchedResourceCount'], 1)

    def test_invalid_source_contracts_are_rejected(self):
        bad = [
            {'period': {'startDate': '2026-10-01', 'endDate': '2027-01-31'}},
            {'unit': 'days'}, {'statusBasis': 'approved'}, {'complete': False},
            {'snapshotId': ''}, {'resources': 'invalid'}, {'nextPage': 1}]
        for change in bad:
            with self.subTest(change=change):
                d = self.service(lambda *_, c=change: payload(**c)).read()
                self.assertEqual(d['status'], 'unavailable')
                self.assertEqual(d['resources'], [])

    def test_invalid_hours_reject_snapshot(self):
        for value in (-1, True, None, '', 'NaN', 'Infinity', '1e999', 'not a number'):
            with self.subTest(value=value):
                self.assertEqual(self.service(lambda *_: payload(value)).read()['status'], 'unavailable')

    def test_pagination_complete_and_same_snapshot(self):
        first = payload(nextPage=2)
        last = payload();last['resources'][0].update(employeeId='E2', name='Bi Yu', totalHours=4)
        s = self.service(lambda cfg, page: first if page == 1 else last)
        self.assertEqual(s.read()['matchedResourceCount'], 2)
        last['snapshotId'] = 'new-snapshot'
        self.assertEqual(self.service(lambda cfg, page: first if page == 1 else last).read()['status'], 'unavailable')

    def test_duplicate_employee_or_ambiguous_person_rejects(self):
        for employee in ('E1', 'E2'):
            p = payload();p['resources'].append({'employeeId': employee, 'name': 'Nick Han', 'totalHours': 4})
            self.assertEqual(self.service(lambda *_: p).read()['status'], 'unavailable')

    def test_failed_refresh_preserves_old_snapshot_as_stale_and_backs_off(self):
        calls = []
        def fetch(cfg, page):
            calls.append(1)
            if len(calls) == 1:return payload()
            raise SourceError('source_unavailable')
        s = self.service(fetch);old = s.read()
        self.now = 301
        stale = s.read()
        self.assertEqual(stale['status'], 'stale')
        self.assertEqual(stale['resources'], old['resources'])
        self.assertEqual(stale['lastSuccessfulSyncAt'], old['lastSuccessfulSyncAt'])
        s.read();self.assertEqual(len(calls), 2)

    def test_status_endpoint_does_not_fetch(self):
        self.assertEqual(self.service(lambda *_: self.fail()).read(fetch=False)['status'], 'pending')

    def test_insecure_source_and_unrecognized_mapping_rejected(self):
        for env in ({**self.env, 'TIMESHEET_API_URL': 'http://untrusted.example/totals'},
                    {**self.env, 'TIMESHEET_RESOURCE_MAP': '{"E1":"unknown_person"}'}):
            self.assertEqual(self.service(lambda *_: self.fail(), env).read()['resources'], [])


if __name__ == '__main__':
    unittest.main()