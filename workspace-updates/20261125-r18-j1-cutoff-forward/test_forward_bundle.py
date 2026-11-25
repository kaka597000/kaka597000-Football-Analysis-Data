"""Offline packaging tests. No test issues a registration or a forecast."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

import bundle_io as io
import evidence_slice as sl
import forward_bundle as fb


class TemporaryTest(unittest.TestCase):
    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)


class ArchiveTests(TemporaryTest):
    def test_deterministic_archive_is_keyed_by_original_bytes(self):
        a, b = self.root / 'one.gz', self.root / 'two.gz'
        io.archive(a, {'b': b'two', 'a': b'one'})
        io.archive(b, {'a': b'one', 'b': b'two'})
        self.assertEqual(a.read_bytes(), b.read_bytes())
        self.assertEqual(io.members(a, lambda name: name == 'a'), {'a': b'one'})

    def test_duplicate_traversal_and_links_are_rejected_even_outside_selection(self):
        for i, name in enumerate(('a', '../escape', '/outside', 'link')):
            path = self.root / str(i)
            with tarfile.open(path, 'w') as tar:
                tar.addfile(tarfile.TarInfo('a'), BytesIO())
                item = tarfile.TarInfo(name)
                if name == 'link':
                    item.type, item.linkname = tarfile.SYMTYPE, '../file'
                tar.addfile(item, BytesIO())
            with self.subTest(name=name), self.assertRaises(ValueError):
                io.members(path, lambda _: False)

    def test_no_overwrite_empty_unrelated_or_link(self):
        src = self.root / 'good'
        io.write(src, 'a', b'exact')
        for name in ('empty', 'occupied', 'link'):
            target = self.root / name
            if name == 'empty':
                target.mkdir()
            elif name == 'occupied':
                io.write(target, 'a', b'old first')
            else:
                target.symlink_to(src, target_is_directory=True)
            with self.subTest(name=name), self.assertRaises(ValueError):
                io.install(src, target)
        self.assertFalse(list((self.root / 'empty').iterdir()))
        self.assertEqual((self.root / 'occupied/a').read_bytes(), b'old first')

    def test_parallel_identical_recovery_is_idempotent(self):
        target = self.root / 'restored'
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: fb.stage_files({'original.json': b'original bytes\n'}, target), range(4)))
        before = (target / 'original.json').stat().st_ino
        fb.stage_files({'original.json': b'original bytes\n'}, target)
        self.assertEqual((target / 'original.json').stat().st_ino, before)
        with self.assertRaisesRegex(ValueError, 'existing output differs'):
            fb.stage_files({'original.json': b'changed'}, target)

    def test_canonical_and_parent_directories_are_protected(self):
        f = SimpleNamespace(ledger=SimpleNamespace(DEFAULT_ROOT=self.root / 'store'))
        for path in (self.root, self.root / 'store', self.root / 'store/issued', self.root / 'intake/export'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                fb.protected_output(f, path, self.root / 'intake')


class EvidenceTests(TemporaryTest):
    """Tiny byte fixtures exercise packaging mechanics; no match or first record is generated."""

    def setUp(self):
        super().setUp()
        self.at = '2026-11-25T12:12:00+00:00'
        self.f = SimpleNamespace(aware=datetime.fromisoformat)
        self.log_rows = {name: [] for name in (*sl.LOGS, sl.DAILY)}
        self.index = {'acquisitions': []}
        for i, (name, code, selected) in enumerate(((sl.ESPN, 'afc', False), (sl.ESPN, 'jpn.1', True),
                                                    (sl.LIVE, None, True), (sl.LIVE, None, True),
                                                    (sl.ORIGINAL, None, False), (sl.DAILY, 'jpn.1', True))):
            data = b'same official body' if name == sl.LIVE else str(i).encode()
            path = f'raw/test/{i}'
            row = dict(path=path, sha256=io.digest(data), bytes=len(data), url=f'https://example.test/{i}',
                       requested_at_utc=self.at, captured_at_utc=self.at, http_status=200, kind='summary', league_slug=code)
            self.log_rows[name].append(row)
            if selected:
                io.write(self.root / 'intake', path, data)
                self.index['acquisitions'].append(dict(log=name, source={k: row[k] for k in sl.FIELDS}))
        self.logs = {n: b''.join((json.dumps(r) + '\n').encode() for r in rows) for n, rows in self.log_rows.items()}
        audit = b'original calendar audit'
        io.write(self.root / 'intake', sl.AUDIT, audit)
        self.index['audit'] = {'sha256': io.digest(audit)}
        self.signed = dict(acquisition_log_sha256={n: io.digest(self.logs[n]) for n in sl.LOGS},
                           calendar=dict(scoreboard_log_sha256=io.digest(self.logs[sl.DAILY]), audit_sha256=io.digest(audit),
                                         audit_created_at_utc=self.at))
        self.files = sl.package_inputs(self.root / 'intake', self.index, self.logs)

    def restore(self):
        return sl.materialize(self.f, self.files, self.index, self.signed, self.root / 'restored', self.f.aware(self.at))

    def test_preserves_full_log_bytes_but_keeps_only_cited_bodies_once(self):
        logs, projected = self.restore()
        self.assertEqual(logs, self.logs)
        self.assertNotEqual(projected[sl.ESPN], self.signed['acquisition_log_sha256'][sl.ESPN])
        self.assertNotIn(sl.ORIGINAL, projected)
        self.assertEqual(sum(n.startswith('objects/') for n in self.files), 3)
        self.assertFalse((self.root / 'restored/raw/test/0').exists())
        self.assertEqual((self.root / 'restored/raw/test/2').read_bytes(), (self.root / 'restored/raw/test/3').read_bytes())

    def test_dropped_unselected_metadata_breaks_original_checksum(self):
        self.files['logs/' + sl.ESPN] = self.logs[sl.ESPN].splitlines(keepends=True)[1]
        with self.assertRaisesRegex(ValueError, 'complete acquisition'):
            self.restore()

    def test_missing_body_fails(self):
        self.files.pop(next(n for n in self.files if n.startswith('objects/')))
        with self.assertRaises(KeyError):
            self.restore()

    def test_injected_unused_body_fails(self):
        self.files['objects/' + io.digest(b'unused')] = b'unused'
        with self.assertRaisesRegex(ValueError, 'unused files'):
            self.restore()

    def test_changed_body_fails_even_if_length_unchanged(self):
        key = next(n for n in self.files if n.startswith('objects/'))
        self.files[key] = b'x' * len(self.files[key])
        with self.assertRaisesRegex(ValueError, 'acquisition bytes differ'):
            self.restore()

    def test_url_and_capture_clock_are_bound_to_original_log(self):
        self.index['acquisitions'][0]['source']['url'] += '?mismatch'
        with self.assertRaisesRegex(ValueError, 'different source'):
            self.restore()

    def test_earlier_cutoff_rejects_future_metadata(self):
        with self.assertRaisesRegex(ValueError, 'future row'):
            sl.materialize(self.f, self.files, self.index, self.signed, self.root / 'clock',
                           self.f.aware('2026-11-25T12:11:00+00:00'))

    def test_afc_body_cannot_join_j1_portable_evidence(self):
        row = self.log_rows[sl.ESPN][0]
        self.index['acquisitions'].append(dict(log=sl.ESPN, source={k: row[k] for k in sl.FIELDS}))
        self.files['objects/' + row['sha256']] = b'0'
        with self.assertRaisesRegex(ValueError, 'out-of-scope'):
            self.restore()

    def test_duplicate_receipt_path_rejected(self):
        with self.assertRaisesRegex(ValueError, 'non-unique'):
            sl.receipts({sl.LIVE: self.logs[sl.LIVE] * 2})

    def test_unfinished_nine_review_cannot_supply_raw_members(self):
        ft = io.encoded(dict(registered=9, certified_ft90=8, pending=1, at=self.at))
        name = 'snapshot/ft-review.json'
        manifest = io.encoded(dict(schema='NOV25-OFFLINE-PACKAGE-1', as_of=self.at,
                                   files={name: dict(bytes=len(ft), sha256=io.digest(ft))}))
        with self.assertRaisesRegex(ValueError, 'nine certified FT90'):
            sl.final_review({name: ft, 'package-manifest.json': manifest})

    def test_shared_storage_resolves_only_existing_cited_bytes(self):
        name = 'snapshot/ft-review.json'
        ft = io.encoded(dict(registered=9, certified_ft90=9, pending=0, at=self.at))
        raw = {name: ft, 'intake/raw/test/2': b'same official body', 'intake/raw/test/3': b'same official body',
               'intake/raw/test/0': b'extraneous AFC body'}
        meta = {n: dict(bytes=len(b), sha256=io.digest(b)) for n, b in raw.items()}
        raw['package-manifest.json'] = io.encoded(dict(schema='NOV25-OFFLINE-PACKAGE-1', as_of=self.at, files=meta))
        path = self.root / 'nine.gz'
        io.archive(path, raw)
        ref, bodies = fb.shared_reference(self.root, path, self.index)
        key = 'objects/' + io.digest(b'same official body')
        self.assertEqual(ref['members'], {key: 'intake/raw/test/2'})
        self.assertEqual(bodies, {key: b'same official body'})

    def test_nine_match_source_restores_only_cutoff_eligible_j1_and_calendar(self):
        source, cal = {}, self.root / 'calendar'
        ft = dict(registered=9, certified_ft90=9, pending=0, at=self.at)
        source['snapshot/ft-review.json'] = io.encoded(ft)
        for name in sl.LOGS:
            source[sl.ALIASES[name]] = self.logs[name]
            for row in self.log_rows[name]:
                if name != sl.ESPN or row['league_slug'] == 'jpn.1':
                    body = b'same official body' if name == sl.LIVE else row['path'].rsplit('/', 1)[-1].encode()
                    source['intake/' + row['path']] = body
        future = dict(self.log_rows[sl.LIVE][0], path='raw/not-yet-read', captured_at_utc='2026-11-26T01:00:00+00:00')
        source[sl.ALIASES[sl.LIVE]] += (json.dumps(future) + '\n').encode()
        meta = {n: dict(bytes=len(b), sha256=io.digest(b)) for n, b in source.items()}
        source['package-manifest.json'] = io.encoded(dict(schema='NOV25-OFFLINE-PACKAGE-1', as_of=self.at, files=meta))
        tar = self.root / 'review.gz'
        io.archive(tar, source)
        io.write(cal, sl.AUDIT, io.encoded(dict(audit_created_at_utc=self.at)))
        io.write(cal, sl.DAILY, self.logs[sl.DAILY])
        io.write(cal, 'raw/test/5', b'5')

        def dated(path, at):
            rows = list(map(json.loads, path.read_bytes().splitlines()))
            return [(i, r) for i, r in enumerate(rows) if datetime.fromisoformat(r['captured_at_utc']) <= at], None

        f = SimpleNamespace(aware=datetime.fromisoformat, CODE='jpn.1', review=SimpleNamespace(dated_log=dated))
        restored = sl.nine_intake(f, tar, cal, f.aware(self.at), self.root / 'from-nine')
        self.assertEqual((restored / 'raw/test/2').read_bytes(), b'same official body')
        self.assertFalse((restored / 'raw/test/0').exists())
        self.assertFalse((restored / 'raw/not-yet-read').exists())
        self.assertEqual((restored / sl.ESPN).read_bytes(), self.logs[sl.ESPN])


class ArchivedR15Tests(TemporaryTest):
    @unittest.skipUnless(os.environ.get('R18_SOURCE'), 'requires the pinned local source repository')
    def test_actual_r15_batch_cannot_be_packaged_as_r18(self):
        tar = fb.HERE.parent / '20261125-r15-j1-lineups-forward/first-issues.tar.gz'
        canon, export, target = self.root / 'original-r15', self.root / 'export', self.root / 'out'
        for name, body in io.members(tar, lambda n: n.startswith('firsts/')).items():
            io.write(canon / 'issued', name.removeprefix('firsts/'), body)
        shutil.copytree(canon / 'issued', export)
        reg = json.loads((export / 'receipts.json').read_bytes())['registration']['sha256']
        command = [sys.executable, '-B', str(fb.HERE / 'forward_bundle.py'), 'pack', '--source', os.environ['R18_SOURCE'],
                   '--registration-sha256', reg, '--receipts-sha256', fb.R15_RECEIPTS, '--canonical', str(canon),
                   '--intake', str(self.root / 'unused'), '--firsts', str(export), '--out', str(target)]
        if os.environ.get('R18_TEST_ROSTERS'):
            command += ['--rosters', os.environ['R18_TEST_ROSTERS']]
        result = subprocess.run(command, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'original prematch freeze required', result.stderr)
        self.assertFalse(target.exists())
        self.assertEqual(io.file_sha(export / 'receipts.json'), fb.R15_RECEIPTS)

    def test_ten_real_originals_require_both_pins_and_exact_inventory(self):
        updates = fb.HERE.parent
        tar = updates / '20261125-r15-j1-lineups-forward/first-issues.tar.gz'
        files = io.members(tar, lambda n: n.startswith('firsts/'))
        originals = self.root / 'firsts'
        for name, body in files.items():
            io.write(originals, name.removeprefix('firsts/'), body)
        registration = '45804bc3636bac38293bf037b887e8cb1e385fd93d981dbdafde419c15336fb0'
        bodies, plan = io.first_files(originals, registration, fb.R15_RECEIPTS)
        self.assertEqual(len(bodies), 12)
        self.assertEqual(plan['record_sha256'], registration)
        for a, b in ((registration, '0' * 64), ('0' * 64, fb.R15_RECEIPTS)):
            with self.assertRaises(ValueError):
                io.first_files(originals, a, b)
        io.write(originals, 'unexpected-revision', b'')
        with self.assertRaisesRegex(ValueError, 'unindexed'):
            io.first_files(originals, registration, fb.R15_RECEIPTS)

    @unittest.skipUnless(os.environ.get('R18_TEST_INTAKE') and os.environ.get('R18_SOURCE'),
                         'requires local original nine-match intake and pinned source')
    def test_real_six_of_seven_at_observed_cutoff_without_new_firsts(self):
        cmd = [sys.executable, '-B', str(fb.HERE / 'forward_bundle.py'), 'probe', '--source', os.environ['R18_SOURCE'],
               '--intake', os.environ['R18_TEST_INTAKE'], '--as-of', '2026-11-25T12:12:30+00:00']
        if os.environ.get('R18_TEST_ROSTERS'):
            cmd += ['--rosters', os.environ['R18_TEST_ROSTERS']]
        result = json.loads(subprocess.check_output(cmd))
        self.assertEqual((result['original_targets'], result['dual_ft90'], result['preview_payloads']), (10, 6, 0))
        self.assertEqual(result['pending'], ['espn:401877547'])
        self.assertEqual(result['calendar'], {'20261122': 0, '20261123': 0, '20261124': 0, '20261125': 7})
        self.assertEqual(result['historical_slots']['normalized'], 2822)
        self.assertEqual(list(result['official_final_kinds'].values()).count('postgame-state-check'), 3)
        self.assertEqual(set(result['doses']['full'].values()), {0.0})


class ArchivedR18Tests(unittest.TestCase):
    def test_real_issued_population_quotes_exposures_and_three_seats(self):
        release = fb.HERE / 'release'
        files = io.members(release / fb.TAR, lambda n: n.startswith('firsts/'))
        index = json.loads(files['firsts/receipts.json'])
        self.assertEqual(io.digest(files['firsts/receipts.json']), '0a9de0ba4f2e2b1a4ad63821b1ea335cbbdbecc73a4dd47f1d88d8552132a30a')
        self.assertEqual(index['registration']['sha256'], '9ba2b89ecb7e504ce9eef40701cbf002082c7548df3f06bce458b286852249be')
        identity = json.loads(files['firsts/' + index['registration']['file']])['payload']['identity']
        r15 = fb.HERE.parent / '20261125-r15-j1-lineups-forward/first-issues.tar.gz'
        old_files = io.members(r15, lambda n: n.startswith('firsts/'))
        old = json.loads(old_files['firsts/receipts.json'])
        self.assertEqual(index['matches'].keys(), old['matches'].keys())
        self.assertEqual((len(files), len(index['matches'])), (12, 10))
        self.assertEqual([s['match_id'] for s in identity['selected']['jpn.1']],
                         ['espn:401877524', 'espn:401877541', 'espn:401877538'])
        for mid, ref in index['matches'].items():
            with self.subTest(match=mid):
                after = json.loads(files['firsts/' + ref['file']])['payload']
                before = json.loads(old_files['firsts/' + old['matches'][mid]['file']])['payload']
                self.assertEqual(after['r15_first_sha256'], old['matches'][mid]['sha256'])
                for field in ('prices', 'line', 'source_slots', 'market_evidence', 'fixture_sources', 'doses'):
                    self.assertEqual(after[field], before[field])
                self.assertEqual(after['forecasts']['candidate'], before['forecasts']['candidate'])
                self.assertEqual((after['rank'], after['seat']), (after['r15_rank'], after['r15_seat']))
                self.assertTrue(after['features_changed'])
                self.assertTrue(any(v['delta'] != 0 for side in after['features'].values() for v in side.values()))
                self.assertEqual(len(after['new_history']), 7)


if __name__ == '__main__':
    unittest.main()
