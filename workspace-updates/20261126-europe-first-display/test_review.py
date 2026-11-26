"""Exercise the result adapter with genuine archived full-time summaries."""

from datetime import timedelta
from hashlib import sha256
import json
from pathlib import Path
import tarfile
from tempfile import TemporaryDirectory
import unittest

from research.analysis_freeze import aware
from research_program.display_window_review import _validate_kickoff_reports
from review import certify_result, results, review


HISTORY = '20261106-uel-review/parts/review.tar.gz.part000'
HISTORY_SHA256 = '8502065c13760f6ebb59dc688e236a3438f8d19d8df73682131b5da27ba6a7ae'
EVIDENCE = 'WCPP/reports/review-uel-20261106/three-evidence/corrected/'
OLD_RESULTS = {'401915534': (0, 2), '401915533': (0, 1), '401915526': (1, 1)}


class FrozenReviewTest(unittest.TestCase):
    def test_complete_pending_rounds(self):
        status = review(at='2026-11-26T15:22:00+08:00')
        self.assertEqual(status['timed_market_verified'], 0)
        self.assertEqual(set(status['competitions']), {'uel', 'uecl'})
        expected_market = {'uecl': 17, 'uel': 18}
        for code, phase in status['competitions'].items():
            self.assertEqual((phase['registered'], phase['verified_results'], phase['pending']), (18, 0, 18))
            self.assertEqual(phase['verified_actual_kickoffs'], 0)
            self.assertEqual(phase['matched_market_firsts'], expected_market[code])
            self.assertEqual((phase['selected']['occupied'], phase['selected']['settled']), (3, 0))
            self.assertIsNone(phase['selected']['all_three_first_sweep'])
            self.assertEqual(phase['against_r7']['paired']['score_top1']['eligible'], 0)

    def test_real_europa_full_time_and_unverified_rows(self):
        archive = Path(__file__).resolve().parents[1] / HISTORY
        self.assertEqual(sha256(archive.read_bytes()).hexdigest(), HISTORY_SHA256)
        cutoff = aware('2026-11-06T09:00:00+08:00')
        with TemporaryDirectory() as work, tarfile.open(archive) as bundle:
            state = Path(work)
            entries = json.load(bundle.extractfile(EVIDENCE + 'manifest.json'))
            fixtures, starts, offsets, rows = {}, {}, set(), []
            for item in entries:
                if item['provider'] != 'ESPN':
                    continue
                event = item['event_id']
                if event not in OLD_RESULTS:
                    continue
                raw = bundle.extractfile(EVIDENCE + 'raw/' + item['file']).read()
                self.assertEqual(sha256(raw).hexdigest(), item['sha256'])
                (state / item['file']).write_bytes(raw)
                game, = json.loads(raw)['header']['competitions']
                teams = {t['homeAway']: 'espn:' + str(t['team']['id']) for t in game['competitors']}
                mid = 'espn:' + event
                fixture = dict(teams, match_id=mid, cohort='uefa.europa', kickoff_at=game['date'],
                               stage='UEFA Europa League, League Phase')
                home, away = OLD_RESULTS[event]
                stamp = item['query_time_beijing']
                row = dict(fixture, cohort='uefa.europa:NEW_FORMAT:league_phase', stage='NEW_FORMAT:league_phase',
                           home_goals=home, away_goals=away, event_status='FT', score_basis='regulation_90',
                           known_at=stamp, source_url=item['url'], raw_reference=dict(
                               path=item['file'], sha256=item['sha256'], source_url=item['url'], captured_at=stamp))
                # Use the checksummed raw bytes to test the same source path as future results.
                proof = certify_result(row, fixture, state, cutoff)
                self.assertEqual((proof['home'], proof['away']), (home, away))
                start = proof['actual_kickoff']
                self.assertIsNone(proof['kickoff_issue'])
                offsets.add(round((aware(start['actual_kickoff_at']) - aware(game['date'])).total_seconds()))
                starts[mid] = start
                self.assertRaises(ValueError, certify_result, dict(row, stage='knockout'), fixture, state, cutoff)
                fixtures[mid] = fixture
                rows.append(row)
            self.assertEqual(len(rows), 3)
            self.assertEqual(offsets, {83, 169, 187})
            self.assertEqual(set(_validate_kickoff_reports(starts, set(fixtures), {
                mid: dict(fixture, competition=fixture['cohort']) for mid, fixture in fixtures.items()
            }, state, cutoff)), set(fixtures))
            damaged = dict(rows[0], event_status='IN_PROGRESS')
            original = rows[0]['raw_reference']
            no_clock = json.loads((state / original['path']).read_bytes())
            no_clock.pop('keyEvents')
            body = json.dumps(no_clock).encode()
            (state / 'no-kickoff-event.json').write_bytes(body)
            earlier = (aware(original['captured_at']) - timedelta(seconds=1)).isoformat()
            missing = dict(rows[0], known_at=earlier, raw_reference=dict(original, captured_at=earlier,
                           path='no-kickoff-event.json', sha256=sha256(body).hexdigest()))
            missing_result = certify_result(missing, fixtures[missing['match_id']], state, cutoff)
            self.assertIsNone(missing_result['actual_kickoff'])
            (state / 'normalized-results.jsonl').write_text('\n'.join(json.dumps(r) for r in [damaged, missing, *rows]),
                                                          encoding='utf-8')
            certified, issues = results(state, fixtures, cutoff)
            self.assertEqual(set(certified), set(fixtures))
            self.assertEqual(set(issues), {rows[0]['match_id']})
            self.assertEqual(certified[missing['match_id']]['source'], missing['raw_reference'])
            self.assertEqual(certified[missing['match_id']]['actual_kickoff'], starts[missing['match_id']])

            disagree = json.loads((state / original['path']).read_bytes())
            kickoff, = (event for event in disagree['keyEvents']
                        if event['type']['type'] == 'kickoff' and event['period']['number'] == 1)
            kickoff['wallclock'] = (aware(kickoff['wallclock']) - timedelta(seconds=1)).isoformat()
            body = json.dumps(disagree).encode()
            (state / 'conflicting-kickoff.json').write_bytes(body)
            conflicting = dict(rows[0], raw_reference=dict(original, path='conflicting-kickoff.json',
                                                           sha256=sha256(body).hexdigest()))
            with (state / 'normalized-results.jsonl').open('a', encoding='utf-8') as output:
                output.write('\n' + json.dumps(conflicting))
            certified, _ = results(state, fixtures, cutoff)
            self.assertEqual(set(certified), set(fixtures))
            self.assertIsNone(certified[conflicting['match_id']]['actual_kickoff'])
            self.assertEqual(certified[conflicting['match_id']]['kickoff_issue'], 'conflicting verified actual kickoffs')


if __name__ == '__main__':
    unittest.main()
