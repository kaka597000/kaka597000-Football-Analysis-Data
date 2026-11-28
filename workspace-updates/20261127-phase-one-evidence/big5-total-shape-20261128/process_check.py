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


def build(bundle):
    root = (bundle / 'recent-process').resolve()
    targets = load_window(bundle, locked_bindings(bundle))
    target_sources = bundle / 'first-order/native-firsts.json'
    lock = verify(read(bundle / 'first-order/native-firsts-freeze.json'))
    if lock['payload']['native_firsts_sha256'] != sha(target_sources):
        raise ValueError('the target match summaries differ from their pre-kickoff receipt')
    sources = read(target_sources)
    groups = {}
    for r in read(root / 'receipts.json'):
        match, side = r['target'], r['side']
        fixture, capture = targets[match], sources[match]
        provider_target, = (row for row in capture['sources'] if row['source_url'].startswith('https://www.fotmob.com/'))
        schedule_raw = bundle / provider_target['file']
        kickoff = aware(fixture['kickoff_at'])
        if sha(schedule_raw) != provider_target['archive_sha256'] or aware(provider_target['captured_at']) >= kickoff:
            raise ValueError('target team-form archive differs')
        upcoming = json.loads(gzip.decompress(schedule_raw.read_bytes()))
        index = ('home', 'away').index(side)
        team_form = upcoming['content']['matchFacts']['teamForm'][index]
        history, = (row for row in team_form if row['linkToMatch'].rsplit('#', 1)[-1] == r['prior_match_id'])
        if not history[side]['isOurTeam'] or str(history[side]['id']) != fixture['fotmob'][side + '_id']:
            raise ValueError('the original form list has a different team or venue')
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


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    bundle = Path(__file__).resolve().parent
    root = bundle / 'recent-process'
    lock = verify(read(root / 'review-freeze.json'))
    artifacts = lock['payload']['artifact_sha256']
    if sha(root / 'receipts.json') != artifacts['receipts.json']:
        raise ValueError('recent form receipts differ from the review freeze')
    write_new(args.out, build(bundle))
    if sha(args.out) != artifacts['verified.json']:
        raise ValueError('recent form replay differs from the review freeze')
