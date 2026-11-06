import json
from decimal import Decimal
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from timesheet import TimesheetService, SourceError


class SofttekTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.site = Path(self.temp.name)
        (self.site / 'assets').mkdir()
        (self.site / 'assets/resource-list-data.json').write_text(json.dumps({'domains': [
            {'resources': [{'key': 'nick_han', 'name': 'Nick Han'},
                           {'key': 'bi_yu', 'name': 'Bi Yu'}]}]}))
        self.env = {'TIMESHEET_PROVIDER': 'softtek', 'TIMESHEET_API_URL': 'https://source.example',
                    'TIMESHEET_AK': 'test-ak', 'TIMESHEET_SK': 'test-sk',
                    'TIMESHEET_RESOURCE_MAP': '{"nick@example.com":"nick_han"}'}
        self.now = 0
        self.service = TimesheetService(self.site, self.env, clock=lambda: self.now)
        self.calls = []
        self.hours = Decimal('32.00')
        self.service.softtek_post = self.post

    def tearDown(self):
        self.temp.cleanup()

    def post(self, cfg, path, payload, token=None):
        self.calls.append((path, payload, token))
        if path.endswith('/token'):
            return {'access_token': 'private-token', 'expires_in': 3600}
        return [{'email': 'nick@example.com', 'totalHours': self.hours}]

    def test_prod_conversion_identity_and_each_request_is_fresh(self):
        first = self.service.read()
        self.assertEqual(first['statusBasis'], 'filled')
        self.assertEqual(first['refreshMode'], 'on-request')
        self.assertEqual(first['resources'][0]['actualMD'], 4)
        self.assertEqual(first['resources'][0]['resourceKey'], 'nick_han')
        self.assertEqual(first['configuredResourceCount'], 1)
        self.assertEqual(first['rosterResourceCount'], 2)
        self.hours = Decimal('24')  # Corrections reduce the next snapshot.
        self.assertEqual(self.service.read()['resources'][0]['actualMD'], 3)
        self.assertEqual(sum(p.endswith('/token') for p, _, _ in self.calls), 1)
        self.assertEqual(sum(p.endswith('/summary') for p, _, _ in self.calls), 2)
        self.assertEqual(self.calls[1][1], {'emails': ['nick@example.com'],
                         'startDate': '2026-11-01', 'endDate': '2027-01-31'})
        self.assertNotIn('bi_yu', json.dumps(first['resources']))
        for secret in ('nick@example.com', 'test-ak', 'test-sk', 'private-token', 'source.example'):
            self.assertNotIn(secret, json.dumps(first))

    def test_business_401_refreshes_token_once(self):
        attempts = []
        def post(cfg, path, payload, token=None):
            if path.endswith('/summary'):
                attempts.append(1)
                if len(attempts) == 1:
                    raise SourceError('source_authentication_failed')
            return self.post(cfg, path, payload, token)
        self.service.softtek_post = post
        self.assertEqual(self.service.read()['status'], 'ready')
        self.assertEqual(len(attempts), 2)
        self.assertEqual(sum(p.endswith('/token') for p, _, _ in self.calls), 2)

    def test_bad_identity_or_hours_does_not_publish(self):
        for rows in ([], [{'email': 'wrong@example.com', 'totalHours': 32}],
                     [{'email': 'nick@example.com', 'totalHours': -1}],
                     [{'email': 'nick@example.com', 'totalHours': '32'}]):
            with self.subTest(rows=rows):
                service = TimesheetService(self.site, self.env)
                service.softtek_token = lambda cfg: 'test'
                service.softtek_post = lambda *args: rows
                self.assertEqual(service.read()['status'], 'unavailable')
                self.assertEqual(service.read(fetch=False)['resources'], [])

    def test_zero_is_not_missing_and_failure_keeps_stale_snapshot(self):
        self.hours = 0
        self.assertEqual(self.service.read()['resources'][0]['actualMD'], 0)
        def fail(*args):
            raise SourceError('source_unavailable')
        self.service.softtek_post = fail
        stale = self.service.read()
        self.assertEqual(stale['status'], 'stale')
        self.assertEqual(stale['resources'][0]['actualMD'], 0)
        self.assertIsNotNone(stale['lastSuccessfulSyncAt'])

    def test_status_does_not_fetch_and_unconfigured_is_pending(self):
        self.assertEqual(self.service.read(fetch=False)['status'], 'pending')
        self.assertEqual(self.calls, [])
        self.env['TIMESHEET_RESOURCE_MAP'] = '{}'
        self.assertEqual(self.service.read()['status'], 'resource_mapping_required')

    def test_http_200_business_401_is_failure(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, *_): return b'{"code":401,"msg":"private vendor detail"}'
        with patch('timesheet.build_opener') as opener:
            opener.return_value.open.return_value = Response()
            with self.assertRaisesRegex(SourceError, '^source_authentication_failed$'):
                TimesheetService.softtek_post(self.service, self.service.config()[0], '/test', {})


if __name__ == '__main__':
    unittest.main()
