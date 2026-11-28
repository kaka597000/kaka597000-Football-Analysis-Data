"""Rebuild the real pending weekend slate and its previously issued research choices."""

import argparse
from datetime import timezone
import gzip
from hashlib import sha256
import json
from pathlib import Path
import tarfile

from automation.market_identity import scheduled_competition
from research.analysis_freeze import aware, verify
from research_program.goal_state_study import sha, write_new


def read(path):
    return json.loads(path.read_bytes())


def slate(bundle):
    root = bundle / 'schedule'
    plan = read(root / 'manifest.json')
    start, end = (aware(plan[k]) for k in ('window_start', 'window_end_exclusive'))
    fixtures = {}
    for item in plan['sources']:
        path = root / item['path']
        if sha(path) != item['archive_sha256'] or item['http_status'] != 200:
            raise ValueError('weekend schedule capture differs')
        body = gzip.decompress(path.read_bytes())
        if sha256(body).hexdigest() != item['sha256']:
            raise ValueError('weekend source body differs')
        board = json.loads(body)
        code = item['competition']
        if [entry['slug'] for entry in board['leagues']] != [code]:
            raise ValueError('wrong league in the weekend schedule')
        for event in board['events']:
            kickoff = aware(event['date'])
            if not start <= kickoff < end:
                continue
            status = event['status']['type']
            if not status['state'] == 'pre' or status['completed'] or 'espn:' + event['id'] in fixtures:
                raise ValueError('the exact schedule captures must show unique unstarted matches')
            mid = 'espn:' + event['id']
            _, teams = scheduled_competition(event)
            fixtures[mid] = {'match_id': mid, 'cohort': code, 'kickoff_at': kickoff.astimezone(timezone.utc).isoformat(),
                'home': 'espn:' + teams['home']['id'], 'away': 'espn:' + teams['away']['id'],
                'names': [teams[key]['displayName'] for key in ('home', 'away')]}
    return plan, dict(sorted(fixtures.items(), key=lambda entry: (entry[1]['kickoff_at'], entry[0])))


def first_issues(path, fixtures):
    def check(index, load):
        registration = verify(load(index['registration']['file']))
        if registration['record_sha256'] != index['registration']['sha256']:
            raise ValueError('first-issue registration hash differs')
        records = {}
        for mid in index['matches'].keys() & fixtures.keys():
            identity, ref = fixtures[mid], index['matches'][mid]
            record = verify(load(ref['file']))
            f = record['fixture']
            if (record['freeze_id'] != ref['id'] or record['record_sha256'] != ref['sha256']
                    or record['stage'] != 'prematch' or record['revision'] != 1 or record['previous_sha256']
                    or record['payload']['registration_sha256'] != registration['record_sha256']
                    or any(identity[key] != f[key] for key in ('match_id', 'cohort', 'home', 'away'))
                    or aware(f['kickoff_at']) != aware(identity['kickoff_at'])
                    or not aware(registration['recorded_at']) <= aware(f['cutoff_at'])
                    <= aware(record['recorded_at']) < aware(identity['kickoff_at'])):
                raise ValueError('weekend research first-issue identity or timing mismatch: ' + mid)
            forecast = record['payload']['forecasts']['candidate']
            if (forecast['primary'] != forecast['top3'][0] or len(set(forecast['top3'])) != 3
                    or len(forecast['top3']) != 3):
                raise ValueError('first-issue scores are not three distinct ordered choices')
            records[mid] = {'freeze_id': ref['id'], 'sha256': ref['sha256'], 'recorded_at': record['recorded_at'],
                            'forecast': forecast}
        return records

    if path.is_dir():
        return check(read(path / 'receipts.json'), lambda file: read(path / file))
    with tarfile.open(path) as archive:
        return check(json.load(archive.extractfile('receipts.json')),
                     lambda file: json.load(archive.extractfile(file)))


def replay(data, bundle):
    plan, fixtures = slate(bundle)
    if len(fixtures) != 31:
        raise ValueError('the initial pending five-league scope was 31 matches')
    inputs = plan['first_issue_inputs']
    tracks = {arm: first_issues(data / 'workspace-updates' / path, fixtures) for arm, path in inputs.items()}
    results, differences, covered = {}, {}, {}
    for mid, fixture in fixtures.items():
        records = {arm: values[mid] for arm, values in tracks.items() if mid in values}
        baseline = records.get('R7', {}).get('forecast')
        diff = {}
        if baseline:
            for arm, record in records.items():
                if arm == 'R7':
                    continue
                next_ = record['forecast']
                first = next_['primary'] != baseline['primary']
                new = sorted(set(next_['top3']) - set(baseline['top3']))
                removed = sorted(set(baseline['top3']) - set(next_['top3']))
                if first or new:
                    diff[arm] = {'first_changed': first, 'top3_added': new, 'top3_removed': removed}
        results[mid] = dict(fixture, first_issues=records, versus_r7=diff)
        league = fixture['cohort']
        covered[league] = covered.get(league, 0) + 1
        for arm in records:
            if arm == 'R7' or not baseline:
                continue
            metrics = differences.setdefault(league, {}).setdefault(
                arm, {'paired': 0, 'first_changed': 0, 'top3_members_changed': 0})
            metrics['paired'] += 1
            metrics['first_changed'] += int(diff.get(arm, {}).get('first_changed', False))
            metrics['top3_members_changed'] += int(bool(diff.get(arm, {}).get('top3_added')))
    return {'registered': len(fixtures), 'window_start': plan['window_start'],
            'window_end_exclusive': plan['window_end_exclusive'], 'fixture_counts': covered,
            'track_coverage': {arm: len(values) for arm, values in tracks.items()},
            'same_fixture_disagreements': differences, 'fixtures': results}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    bundle = Path(__file__).resolve().parent
    write_new(args.out, replay(args.data_root, bundle))
    signed = bundle / 'weekend-freeze.json'
    if signed.exists():
        receipt = verify(read(signed))
        if (receipt['stage'] != 'prematch'
                or receipt['payload']['weekend_sha256'] != sha(args.out)
                or receipt['payload']['schedule_manifest_sha256'] != sha(bundle / 'schedule/manifest.json')):
            raise ValueError('the rebuilt weekend scope differs from its pre-kickoff freeze')
