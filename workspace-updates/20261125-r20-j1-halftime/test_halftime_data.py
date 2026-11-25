"""Regression checks for halftime-source eligibility, original population, and immutable evidence."""

from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from bundle_io import digest, first_files, install, members, write
import evidence as ev
import package as pkg
from study_checks import OUTPUTS, read_rows


class RawHalfTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        release = pkg.HERE / 'release'
        files = members(release / 'r18-reference.tar.gz')
        receipts = json.loads(files['firsts/receipts.json'])
        parent = json.loads(files['firsts/' + receipts['registration']['file']])
        cls.mid = 'espn:401877547'
        event = parent['payload']['identity']['evidence']['events'][cls.mid]
        cls.doc = json.loads(files['objects/' + event['espn']['sha256']])
        cls.kickoff = event['fixture']['kickoff_at']
        cls.ids = [event['fixture'][s][5:] for s in ev.SIDES]
        cls.actual = event['score']

    def decode(self, doc):
        return ev.raw_halves(json.dumps(doc).encode(), self.mid, self.kickoff, self.ids, self.actual)

    def test_real_original_final_sums_to_two_each(self):
        full, first, second, _, reasons = self.decode(self.doc)
        self.assertEqual(full, [2, 2])
        self.assertEqual([a + b for a, b in zip(first, second)], full)
        self.assertEqual(reasons, [])

    def test_missing_linescore_stays_missing(self):
        doc = deepcopy(self.doc)
        team = doc['header']['competitions'][0]['competitors'][0]
        team.pop('linescores')
        _, first, second, _, reasons = self.decode(doc)
        i = ev.SIDES.index(team['homeAway'])
        self.assertIsNone(first[i])
        self.assertIsNone(second[i])
        self.assertIn(team['homeAway'] + '_linescores_not_exactly_two_periods', reasons)

    def test_bad_cell_and_wrong_period_keep_explicit_reasons(self):
        for shown, period, suffix in (('-', 1, 'display_value_invalid'), ('0.5', 1, 'display_value_invalid'),
                                      ('0', 2, 'label_mismatch')):
            with self.subTest(shown=shown, period=period):
                doc = deepcopy(self.doc)
                team = doc['header']['competitions'][0]['competitors'][0]
                team['linescores'][0] = {'displayValue': shown, 'period': period}
                self.assertIn(f"{team['homeAway']}_period_1_{suffix}", self.decode(doc)[-1])

    def test_wrong_identity_live_state_or_extra_period_rejected(self):
        mutations = []
        for change in ('team', 'league', 'clock', 'not_final', 'extra_period', 'shootout'):
            doc = deepcopy(self.doc)
            game = doc['header']['competitions'][0]
            if change == 'team':
                game['competitors'][0]['team']['id'] = 'different'
            elif change == 'league':
                doc['header']['league']['slug'] = 'different'
            elif change == 'clock':
                game['date'] = (ev.utc(self.kickoff) + timedelta(days=1)).isoformat()
            elif change == 'not_final':
                game['status']['type']['completed'] = False
            elif change == 'extra_period':
                game['status']['period'] = 3
            else:
                game['competitors'][0]['shootoutScore'] = '1'
            mutations.append((change, doc))
        for name, doc in mutations:
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.decode(doc)

    def test_halves_disagreeing_with_ft_do_not_enter_training(self):
        doc = deepcopy(self.doc)
        team = doc['header']['competitions'][0]['competitors'][0]
        team['linescores'] = [{'displayValue': '0'}, {'displayValue': '19'}]
        self.assertIn(team['homeAway'] + '_halves_do_not_sum_to_full', self.decode(doc)[-1])


class RealReleaseTests(unittest.TestCase):
    def test_eligible_and_excluded_membership_and_archived_original_bytes(self):
        release = pkg.HERE / 'release'
        intake = members(release / 'halves-intake.tar.gz')
        rows = list(map(json.loads, intake['matches.jsonl'].splitlines()))
        self.assertEqual(digest(intake['matches.jsonl']), '923dfda86ab85343a59a3b97f9cdeb816633fd47c29d450a3934b57ec7565839')
        self.assertEqual(digest(intake['artifact-manifest.json']), '46f4c05bc84081fcd8496da1848f93ab498098af7204d109a831cf8123a2a16a')
        self.assertEqual(len(ev.unique(rows, 'match_id')), 2822)
        self.assertEqual({r['match_id'] for r in rows if not r['eligible']},
                         {'espn:601618', 'espn:593437', 'espn:697148', 'espn:697149'})
        late = list(map(json.loads, intake['late-seven-excluded.jsonl'].splitlines()))
        self.assertEqual(len(late), 7)
        self.assertTrue(all(r['eligible'] is False for r in late))
        self.assertFalse({r['match_id'] for r in rows} & {r['match_id'] for r in late})
        for k in intake:
            self.assertFalse(k.endswith('.tar') or k.endswith('.json.gz'))

    def test_true_history_estimates_and_registered_zero_dose_heads(self):
        p = pkg.HERE / 'release/study'
        self.assertEqual(set(pkg.inventory(p)), set(OUTPUTS))
        fit = ev.read(p / 'fit.json')
        full = ev.read(p / 'forward.json')
        self.assertEqual(fit['calibration']['training_observed'], 1910)
        self.assertEqual(full['calibration']['training_observed'], 2818)
        self.assertEqual(set(fit['doses'].values()), {0.0})
        rows = read_rows(p / 'forecasts.jsonl.gz')
        self.assertEqual(sum(r['window'] == 'evaluation' for r in rows), 380)
        self.assertEqual(sum(r['window'] == 'recent' for r in rows), 150)
        self.assertTrue(all(r['line'] is None and r['forecast']['r7'] == r['forecast']['candidate'] for r in rows))
        self.assertTrue(any(r['forecast']['fixed_full'] != r['forecast']['r7'] for r in rows))
        self.assertEqual(ev.read(p / 'metrics.json')['evaluation']['paired']['market']['actual_ou']['date_cluster_ci'], None)

    def test_merge_or_rename_firsts_cannot_change_the_original_ingest(self):
        release = pkg.HERE / 'release'
        with TemporaryDirectory() as root:
            folder = Path(root) / 'firsts'
            pkg.unpack(release / 'ten-firsts.tar.gz', folder)
            sha = '8b718c63b4620a34d8640d7df2fa7efa2849c3a24bea15cb058c470ce3614f65'
            receipts = 'f84db93bd24092db6d84dfd039996c5f738d2c6561c32642b5cc9ae69041195f'
            originals, plan = first_files(folder, sha, receipts)
            self.assertEqual((len(originals), plan['record_sha256']), (12, sha))
            write(folder, 'different-revision.json', b'{}')
            with self.assertRaisesRegex(ValueError, 'unindexed'):
                first_files(folder, sha, receipts)

    def test_staged_install_preserves_existing_receipts(self):
        with TemporaryDirectory() as name:
            root = Path(name)
            write(root / 'old', 'receipts.json', b'real original bytes')
            write(root / 'different', 'receipts.json', b'different')
            with self.assertRaises(ValueError):
                install(root / 'different', root / 'old')
            self.assertEqual((root / 'old/receipts.json').read_bytes(), b'real original bytes')


if __name__ == '__main__':
    unittest.main()
