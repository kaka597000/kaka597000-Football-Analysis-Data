"""Replay the retained recent same-venue xG for the two next live comparisons."""

import argparse
import gzip
import json
from math import isfinite
from pathlib import Path

from research.analysis_freeze import aware, verify
from research_program.goal_state_study import sha, write_new
from result_evidence import endpoint, fotmob, retained
from settlement import load_window, locked_bindings, read


def expected_goals(body):
    all_stats = body['content']['stats']['Periods']['All']['stats']
    left_right, = {tuple(float(value) for value in row['stats'])
                   for group in all_stats for row in group['stats']
                   if row['key'] == 'expected_goals' and row['type'] == 'text'}
    if len(left_right) != 2 or not all(isfinite(value) and value >= 0 for value in left_right):
        raise ValueError('invalid or incomplete xG from the retained match')
    return left_right


def locked_summaries(bundle):
    target_sources = bundle / 'first-order/native-firsts.json'
    lock = verify(read(bundle / 'first-order/native-firsts-freeze.json'))
    if lock['payload']['native_firsts_sha256'] != sha(target_sources):
        raise ValueError('the target match summaries differ from their pre-kickoff receipt')
    return read(target_sources)


def same_venue_form(bundle, fixture, capture, side):
    provider_target, = (row for row in capture['sources'] if row['source_url'].startswith('https://www.fotmob.com/'))
    schedule_raw = bundle / provider_target['file']
    if sha(schedule_raw) != provider_target['archive_sha256'] or aware(provider_target['captured_at']) >= aware(fixture['kickoff_at']):
        raise ValueError('target team-form archive differs')
    upcoming = json.loads(gzip.decompress(schedule_raw.read_bytes()))
    index = ('home', 'away').index(side)
    side_id = fixture['fotmob'][side + '_id']
    same_venue = [row for row in upcoming['content']['matchFacts']['teamForm'][index]
                  if row[side]['isOurTeam'] and str(row[side]['id']) == side_id]
    form = {row['linkToMatch'].rsplit('#', 1)[-1]: row for row in same_venue}
    if len(form) != len(same_venue):
        raise ValueError('repeated match in the original form list')
    return form


def build(bundle):
    root = (bundle / 'recent-process').resolve()
    targets = load_window(bundle, locked_bindings(bundle))
    sources = locked_summaries(bundle)
    groups = {}
    for r in read(root / 'receipts.json'):
        match, side = r['target'], r['side']
        fixture, capture = targets[match], sources[match]
        kickoff = aware(fixture['kickoff_at'])
        index = ('home', 'away').index(side)
        history = same_venue_form(bundle, fixture, capture, side)[r['prior_match_id']]
        body, collected = retained(root, r, kickoff)
        if collected >= kickoff or sha(root / r['path']) != r['archive_sha256']:
            raise ValueError('prior form response or cutoff differs')
        endpoint(r['source_url'], {'www.fotmob.com'}, '/api/data/matchDetails', 'matchId', r['prior_match_id'])
        raw = json.loads(body)
        earlier = {'cohort': fixture['cohort'], 'kickoff_at': history['date']['utcTime'],
                   'fotmob': {'match_id': r['prior_match_id'], 'league_id': fixture['fotmob']['league_id'],
                              'home_id': str(history['home']['id']), 'away_id': str(history['away']['id'])}}
        if aware(earlier['kickoff_at']) >= collected:
            raise ValueError('form must predate its actual receipt')
        score = fotmob(earlier, raw)
        xg = expected_goals(raw)
        if [str(value) for value in score] != [history['tooltipText'][k + 'Score'] for k in ('home', 'away')]:
            raise ValueError('verified regulation score differs from the original team form')
        rows = groups.setdefault(match, {}).setdefault(side, [])
        if any(row['match_id'] == r['prior_match_id'] for row in rows):
            raise ValueError('repeated historical fixture')
        rows.append({'match_id': r['prior_match_id'], 'date': earlier['kickoff_at'][:10],
                     'opponent': history[('away', 'home')[index]]['name'], 'goals': [score[index], score[1-index]],
                     'xg': xg[index], 'xga': xg[1-index], 'source': r})
    output = {}
    for match, sides in groups.items():
        output[match] = {side: {'sample_n': len(rows), 'matches': rows,
            'xg_mean': round(sum(r['xg'] for r in rows) / len(rows), 3),
            'xga_mean': round(sum(r['xga'] for r in rows) / len(rows), 3)} for side, rows in sides.items()}
    return {'scope': 'PRIOR_SAME_VENUE_LEAGUE_FORM_IN_RETAINED_TARGET_SUMMARIES', 'context': output}


def union_coverage(bundle, process):
    mid = 'espn:401884723'
    fixture = load_window(bundle, locked_bindings(bundle))[mid]
    form = same_venue_form(bundle, fixture, locked_summaries(bundle)[mid], 'away')
    root = (bundle / 'recent-process/union-exclusions').resolve()
    kickoff = aware(fixture['kickoff_at'])
    included = {row['match_id'] for row in process['context'][mid]['away']['matches']}
    excluded = {}
    for ref in read(root / 'receipts.json'):
        prior = ref['prior_match_id']
        if prior in included or prior in excluded:
            raise ValueError('overlap in the Union away-form scope')
        endpoint(ref['source_url'], {'www.fotmob.com'}, '/api/data/matchDetails', 'matchId', prior)
        body, collected = retained(root, ref, kickoff)
        history = form[prior]
        raw = json.loads(body)
        general, header = raw['general'], raw['header']
        date = aware(history['date']['utcTime'])
        teams = [str(history[side]['id']) for side in ('home', 'away')]
        league = str(general['leagueId'])
        if (not date <= aware(ref['requested_at']) <= collected < kickoff
                or general['gender'] != 'male' or str(general['matchId']) != prior
                or league == fixture['fotmob']['league_id']
                or not general['leagueName'].strip()
                or [str(general[side + 'Team']['id']) for side in ('home', 'away')] != teams
                or [str(team['id']) for team in header['teams']] != teams
                or aware(general['matchTimeUTCDate']) != date or aware(header['status']['utcTime']) != date):
            raise ValueError('Union exclusion is not an identified previous match outside the Bundesliga')
        excluded[prior] = {'league_id': league, 'league_name': general['leagueName'],
                           'opponent': history['home']['name'], 'source': ref}
    if (included | excluded.keys()) != form.keys():
        raise ValueError('Union exclusions do not account for the complete frozen away-form list')
    return {'match_id': mid, 'qualification': 'UNION_AWAY_BUNDESLIGA',
            'original_same_venue_count': len(form), 'included_match_ids': sorted(included),
            'excluded': excluded}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--union-coverage-out', type=Path)
    args = parser.parse_args()
    bundle = Path(__file__).resolve().parent
    root = bundle / 'recent-process'
    lock = verify(read(root / 'review-freeze.json'))
    artifacts = lock['payload']['artifact_sha256']
    if sha(root / 'receipts.json') != artifacts['receipts.json']:
        raise ValueError('recent form receipts differ from the review freeze')
    process = build(bundle)
    write_new(args.out, process)
    if sha(args.out) != artifacts['verified.json']:
        raise ValueError('recent form replay differs from the review freeze')
    if args.union_coverage_out:
        root = root / 'union-exclusions'
        lock = verify(read(root / 'review-freeze.json'))
        artifacts = lock['payload']['artifact_sha256']
        if sha(root / 'receipts.json') != artifacts['receipts.json'] or sha(args.out) != artifacts['process_verified.json']:
            raise ValueError('Union form scope differs from its review freeze')
        write_new(args.union_coverage_out, union_coverage(bundle, process))
        if sha(args.union_coverage_out) != artifacts['verified.json']:
            raise ValueError('Union form scope replay differs from its review freeze')
