"""Check the intake against independent real responses and isolated failure cases."""

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import shutil
import tarfile
from tempfile import TemporaryDirectory
import unittest

from review import KICKOFF_CONFLICT, grade, results, verify_kickoffs

import prepare
import result_intake as intake
from research.analysis_freeze import aware
from test_review import EVIDENCE, HISTORY, HISTORY_SHA256, OLD_RESULTS


HERE = Path(__file__).resolve().parent
PREFLIGHT = HERE/'result-intake-preflight'
OLD_BINDINGS = {
    'espn:401915534': dict(id='2050113', home='50058', away='52298', matchday=4),
    'espn:401915533': dict(id='2050111', home='50109', away='52748', matchday=4),
    'espn:401915526': dict(id='2050121', home='52916', away='2600431', matchday=4),
}


def write_manifest(path, rows):
    path.write_text(json.dumps(rows), encoding='utf-8')
    return path


def history(root):
    fixtures, captures = {}, []
    archive = HERE.parent/HISTORY
    if sha256(archive.read_bytes()).hexdigest() != HISTORY_SHA256:
        raise ValueError('historical ESPN input differs')
    with tarfile.open(archive) as bundle:
        for entry in json.load(bundle.extractfile(EVIDENCE+'manifest.json')):
            if entry['provider'] != 'ESPN' or entry['event_id'] not in OLD_RESULTS:
                continue
            raw = bundle.extractfile(EVIDENCE+'raw/'+entry['file']).read()
            game, = json.loads(raw)['header']['competitions']
            (root/entry['file']).write_bytes(raw)
            mid = 'espn:'+entry['event_id']
            teams = {r['homeAway']: 'espn:'+str(r['team']['id']) for r in game['competitors']}
            fixtures[mid] = dict(teams, match_id=mid, cohort='uefa.europa', kickoff_at=game['date'],
                                 stage='UEFA Europa League, League Phase')
            captures.append(dict(path=entry['file'], url=entry['url'], captured_at=entry['query_time_beijing'],
                                 sha256=entry['sha256'], http_status=entry['http_status']))
    official, _ = prepare.read(PREFLIGHT/'captures.json')
    shutil.copyfile(PREFLIGHT/official['path'], root/official['path'])
    return fixtures, captures, official


class ResultIntakeTest(unittest.TestCase):
    def test_real_calendars_preserve_each_registered_round(self):
        rosters = {window: intake.registered_fixtures(window) for window in ('round1', 'round2')}
        self.assertFalse(rosters['round1'].keys() & rosters['round2'].keys())
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            captures = []
            for short in prepare.COMPETITIONS:
                source = prepare.read(HERE/'calendar'/f'uefa-{short}-crosswalk.json')['meta']
                name = f'uefa-{short}.json.gz'
                shutil.copyfile(HERE/'calendar'/name, root/name)
                captures.append(dict(path=name, url=source['url'], captured_at=source['captured_at_utc'],
                                     sha256=source['sha256'], http_status=source['http_status']))
            complete = write_manifest(root/'captures.json', captures)
            partial = write_manifest(root/'partial.json', captures[:1])
            at = datetime.now(timezone.utc)
            for window, fixtures in rosters.items():
                with self.subTest(window=window):
                    bindings = intake.official_bindings(fixtures)
                    offset = int(window == 'round2')
                    self.assertEqual({(f['cohort'], bindings[mid]['matchday']) for mid, f in fixtures.items()},
                                     {('uefa.europa.conf', 4+offset), ('uefa.europa', 5+offset)})
                    out = root/window
                    report = intake.assemble(complete, out, fixtures, bindings, at)
                    self.assertEqual(report['registered'], 36)
                    self.assertEqual(report['captures_with_errors'], [])
                    self.assertTrue(all(len(v) == 1 and v[0]['status'] == 'UPCOMING' for v in report['matches'].values()))
                    self.assertEqual(results(out, fixtures, at), ({}, {}))
                    report = intake.assemble(partial, root/f'partial-{window}', fixtures, bindings, at)
                    self.assertEqual((report['registered'], sum(not rows for rows in report['matches'].values())), (36, 18))

    def test_real_dual_finals_and_provider_conflict(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixtures, espn, official = history(root)
            at = datetime.now(timezone.utc)
            captures = write_manifest(root/'captures.json', [*espn, official])
            intake.assemble(captures, root/'paired', fixtures, OLD_BINDINGS, at)
            settled, issues = results(root/'paired', fixtures, at, OLD_BINDINGS)
            self.assertEqual(issues, {})
            self.assertEqual({mid.removeprefix('espn:'): (r['home'], r['away']) for mid,r in settled.items()}, OLD_RESULTS)
            self.assertTrue(all(r['confirmed_result_sources'].keys() == {'espn', 'uefa'} for r in settled.values()))
            self.assertTrue(all(r['actual_kickoff'] is not None for r in settled.values()))

            write_manifest(captures, [official])
            intake.assemble(captures, root/'official-only', fixtures, OLD_BINDINGS, at)
            alone, issues = results(root/'official-only', fixtures, at, OLD_BINDINGS)
            self.assertEqual(issues, {})
            self.assertEqual(alone.keys(), fixtures.keys())
            self.assertTrue(all(r['confirmed_result_sources'].keys() == {'uefa'} and r['actual_kickoff'] is None
                                for r in alone.values()))

            # Alter only isolated test copies to exercise an independent score conflict and postponement.
            changed = 'espn:401915534'
            paused = 'espn:401915533'
            body = intake.raw_result(root, official['path'], official['sha256'])
            matches = json.loads(body)
            for m in matches:
                if str(m['id']) == OLD_BINDINGS[changed]['id']:
                    for score in m['score'].values():
                        score['home'] = 1
                if str(m['id']) == OLD_BINDINGS[paused]['id']:
                    m['status'] = 'POSTPONED'
                    m.pop('kickOffTime')
            modified = json.dumps(matches).encode()
            (root/'test-only.json').write_bytes(modified)
            altered = dict(official, sha256=sha256(modified).hexdigest(), path='test-only.json')
            write_manifest(captures, [item for item in espn if paused.removeprefix('espn:') not in item['url']] + [altered])
            report = intake.assemble(captures, root/'changed', fixtures, OLD_BINDINGS, at)
            settled, issues = results(root/'changed', fixtures, at, OLD_BINDINGS)
            self.assertEqual(report['matches'][paused][0]['status'], 'POSTPONED')
            self.assertEqual(set(settled), fixtures.keys()-{changed, paused})
            self.assertEqual(set(issues), {changed})

    def test_uefa_alone_can_verify_regulation_in_both_competitions(self):
        for capture, expected in zip(prepare.read(PREFLIGHT/'captures.json'), (17,18), strict=True):
            raw = intake.raw_result(PREFLIGHT, capture['path'], capture['sha256'])
            provider, code, _ = intake.endpoint(capture['url'])
            self.assertEqual(provider, 'uefa')
            games = json.loads(raw)
            self.assertEqual(len(games), expected)
            for game in games:
                fixture = dict(cohort=code, kickoff_at=game['kickOffTime']['dateTime'])
                binding = dict(id=str(game['id']), home=str(game['homeTeam']['id']), away=str(game['awayTeam']['id']),
                               matchday=game['matchday']['sequenceNumber'])
                status, score = intake.uefa_score(game, fixture, binding, aware(capture['captured_at']))
                self.assertEqual(status, 'FINISHED')
                self.assertEqual(score, tuple(game['score']['regular'][s] for s in ('home','away')))

    def test_in_play_kickoff_survives_pending_and_official_results(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixtures, espn, official = history(root)
            final = espn[0]
            mid = intake.endpoint(final['url'])[2]
            fixture = fixtures[mid]
            document = json.loads((root/final['path']).read_bytes())
            opening, = (event for event in document['keyEvents']
                        if event['type']['type'] == 'kickoff' and event['period']['number'] == 1)
            start = aware(opening['wallclock'])
            captured = start + timedelta(minutes=2)
            # An isolated in-play test case keeps the real typed opening event and omits later play.
            game, = document['header']['competitions']
            game['status']['type'].update(state='in', name='STATUS_IN_PROGRESS', completed=False)
            document['keyEvents'] = [opening]
            for team in game['competitors']:
                team.pop('score', None)
                team.pop('linescores', None)
            body = json.dumps(document).encode()
            (root/'test-opening.json').write_bytes(body)
            live = dict(final, path='test-opening.json', sha256=sha256(body).hexdigest(),
                        captured_at=captured.isoformat())
            manifest = write_manifest(root/'captures.json', [live])
            state = root/'live'
            progress = intake.assemble(manifest, state, fixtures, OLD_BINDINGS, captured)
            self.assertEqual(progress['candidate_regulation_rows'], 0)
            self.assertEqual(results(state, fixtures, captured, OLD_BINDINGS), ({}, {}))
            readback = verify_kickoffs(state, fixtures, {}, captured)
            self.assertEqual(aware(readback[mid]['actual_kickoff']['actual_kickoff_at']), start)
            self.assertEqual(verify_kickoffs(state, fixtures, {}, start), {})
            row = prepare.read(HERE/'publication/scorecard.json')['uel']['rows'][0]
            progress = grade([dict(row, fixture=fixture, rank=None)], {}, kickoffs=readback)
            self.assertEqual((progress['verified_actual_kickoffs_awaiting_result'], progress['verified_results']), (1, 0))
            self.assertIsNone(progress['per_match'][mid]['actual'])

            at = datetime.now(timezone.utc)
            write_manifest(manifest, [live, official])
            state = root/'with-official'
            intake.assemble(manifest, state, fixtures, OLD_BINDINGS, at)
            settled, issues = results(state, fixtures, at, OLD_BINDINGS)
            self.assertEqual((settled[mid]['home'], settled[mid]['away']), OLD_RESULTS[mid.removeprefix('espn:')])
            self.assertEqual(issues, {})
            self.assertEqual(verify_kickoffs(state, fixtures, settled, at), readback)

            opening['wallclock'] = (start + timedelta(seconds=1)).isoformat()
            body = json.dumps(document).encode()
            (root/'test-opening.json').write_bytes(body)
            write_manifest(manifest, [dict(live, sha256=sha256(body).hexdigest()), final, official])
            state = root/'clock-conflict'
            intake.assemble(manifest, state, fixtures, OLD_BINDINGS, at)
            settled, issues = results(state, fixtures, at, OLD_BINDINGS)
            self.assertIn(mid, settled)
            self.assertEqual(issues, {})
            self.assertEqual(verify_kickoffs(state, fixtures, settled, at)[mid],
                             dict(actual_kickoff=None, kickoff_issue=KICKOFF_CONFLICT))


if __name__ == '__main__':
    unittest.main()
