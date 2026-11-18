"""Bounded settlement polling, with real normalization and raw-source certification."""
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

if __package__:
    from . import poll_three_arm_results as poller
else:
    import poll_three_arm_results as poller


class PollResultsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.state = Path(temp.name)
        self.batch = self.state / 'batch'
        self.batch.mkdir()
        self.registration = self.state / 'protocol.json'
        self.kickoff = datetime(2026, 11, 18, 22, 30, tzinfo=timezone.utc)
        self.observed = self.kickoff + timedelta(hours=2, seconds=1)
        self.fixtures = {}
        self.events = []
        for idx in range(1, 7):
            mid = 'espn:' + str(idx)
            fixture = dict(match_id=mid, cohort='bra.1', stage='regular', home='espn:10',
                           away='espn:11', kickoff_at=self.kickoff.isoformat())
            self.fixtures[mid] = fixture
            sides = [{'homeAway': side, 'team': {'id': identifier}, 'score': score,
                      'linescores': [{'displayValue': '0'}, {'displayValue': score}]}
                     for side, identifier, score in [('home', '10', '2'), ('away', '11', '1')]]
            comp = {'competitors': sides, 'date': fixture['kickoff_at'], 'status': {
                'type': {'completed': True, 'name': 'STATUS_FULL_TIME'}, 'period': 2}}
            self.events.append({'id': str(idx), 'date': fixture['kickoff_at'], 'competitions': [comp]})
        board = json.dumps({'leagues': [{'slug': 'bra.1'}], 'events': self.events}).encode()
        (self.state / 'board.json').write_bytes(board)
        self.registration.write_text(json.dumps({
            'schema': 'THREE-ARM-RESEARCH-REGISTRATION-1', 'fixtures': list(self.fixtures.values()),
            'recorded_at': '2026-11-17T08:00Z', 'scoreboard_source': 'board.json',
            'scoreboard_sha256': hashlib.sha256(board).hexdigest(),
        }))
        self.binding = {'registration_sha256': hashlib.sha256(self.registration.read_bytes()).hexdigest()}
        plan = {'recorded_at': '2026-11-18T03:12Z', 'payload': {'binding': self.binding}}
        patcher = patch.object(poller, '_predictions', return_value=(plan, self.fixtures, {}))
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_poll(self, fetcher, now=None):
        return poller.poll(self.batch, self.registration, self.state, clock=lambda: now or self.observed,
                           fetcher=fetcher)

    def summary(self, url):
        header = self.events[int(url.split('=')[-1]) - 1]
        return json.dumps({'header': header, 'format': {'regulation': {'periods': 2}}},
                          indent=2).encode()

    def test_before_two_hours_no_transport_or_files(self):
        fetch = Mock()
        report = self.run_poll(fetch, self.kickoff + timedelta(hours=2) - timedelta(microseconds=1))
        fetch.assert_not_called()
        self.assertEqual(report['due_missing'], 0)
        self.assertFalse((self.batch / 'result-polling').exists())

    def test_certified_regulation_and_actual_raw_time_preserved_idempotently(self):
        fetch = Mock(side_effect=self.summary)
        first = self.run_poll(fetch)
        second = self.run_poll(fetch)
        log = self.state / 'normalized-results.jsonl'
        retained = log.read_bytes()
        self.assertEqual(first['accepted'], ['espn:1', 'espn:2', 'espn:3'])
        self.assertEqual(second['accepted'], ['espn:4', 'espn:5', 'espn:6'])
        self.assertEqual(self.run_poll(fetch)['requests'], 0)
        self.assertEqual(fetch.call_count, 6)
        self.assertEqual(log.read_bytes(), retained)
        for row in map(json.loads, retained.splitlines()):
            raw = gzip.decompress((self.state / row['raw_reference']['path']).read_bytes())
            self.assertEqual(raw, self.summary(row['source_url']))
            self.assertEqual(row['known_at'], self.observed.isoformat())
            self.assertEqual([row['home_goals'], row['away_goals']], [2, 1])
        requests = [json.loads(v) for v in (self.state / 'requests.jsonl').read_text().splitlines()]
        self.assertEqual(len(requests), 6)
        self.assertTrue(all(r['raw']['captured_at'] == self.observed.isoformat() for r in requests))

    def test_transport_failure_and_unfinished_or_conflicting_summaries_rotate(self):
        def fetch(url):
            if url.endswith('1'):
                raise subprocess.TimeoutExpired('curl', 6)
            body = json.loads(self.summary(url))
            competition = body['header']['competitions'][0]
            if url.endswith('2'):
                competition['status']['type']['completed'] = False
            else:
                competition['competitors'][0]['score'] = '3'
            return json.dumps(body).encode()
        first = self.run_poll(fetch)
        self.assertEqual(set(first['pending']), {'espn:1', 'espn:2', 'espn:3'})
        self.assertFalse((self.state / 'normalized-results.jsonl').exists())
        second = self.run_poll(self.summary)
        self.assertEqual(second['accepted'], ['espn:4', 'espn:5', 'espn:6'])
        third = self.run_poll(self.summary)
        self.assertEqual(third['accepted'], ['espn:1', 'espn:2', 'espn:3'])

    def test_changed_protocol_scoreboard_or_fixture_rejected(self):
        fetch = Mock()
        doc = json.loads(self.registration.read_bytes())
        doc['fixtures'][0]['home'] = 'espn:99'
        self.registration.write_text(json.dumps(doc))
        with self.assertRaisesRegex(ValueError, 'registration checksum'):
            self.run_poll(fetch)
        self.binding['registration_sha256'] = hashlib.sha256(self.registration.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, 'differs from frozen plan'):
            self.run_poll(fetch)
        (self.state / 'board.json').write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            self.run_poll(fetch)
        fetch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
