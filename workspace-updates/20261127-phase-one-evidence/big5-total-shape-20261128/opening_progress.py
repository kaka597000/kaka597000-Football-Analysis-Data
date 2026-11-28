"""Replay the retained opening-match observations against the 31-match ledger."""

import argparse
import json
from pathlib import Path

from research.analysis_freeze import aware, verify
from research_program.goal_state_study import sha, write_new
from result_evidence import endpoint, espn_event, retained, verify_results
from settlement import grade, load_window, locked_bindings, read
from settlement_additions import added_firsts


def opening(bundle):
    root = (bundle / 'opening-live').resolve()
    receipts = sorted(read(root / 'receipts.json'), key=lambda ref: aware(ref['captured_at']))
    at = max(aware(row['captured_at']) for row in receipts)
    matches = load_window(bundle, locked_bindings(bundle))
    mid = 'espn:401882796'
    fixture = matches[mid]
    observations, admissible = [], []
    for ref in receipts:
        provider = ref['provider']
        if ref['match_id'] != mid or provider not in ('espn', 'fotmob'):
            raise ValueError('opening rehearsal must use its registered match and provider')
        source, captured = retained(root, ref, at)
        body = json.loads(source)
        if provider == 'espn':
            endpoint(ref['source_url'], {'site.api.espn.com'}, '/apis/site/v2/sports/soccer/esp.1/summary', 'event', '401882796')
            status = espn_event(fixture, body)['status']['type']
            label, state = status['name'], status['state']
            if state in ('in', 'post'):
                admissible.append(ref)
        else:
            bound = fixture['fotmob']
            endpoint(ref['source_url'], {'www.fotmob.com'}, '/api/data/matchDetails', 'matchId', bound['match_id'])
            general, header = body['general'], body['header']
            status = header['status']
            if (str(general['matchId']) != bound['match_id'] or str(general['leagueId']) != bound['league_id']
                    or [str(team['id']) for team in header['teams']] != [bound['home_id'], bound['away_id']]
                    or aware(status['utcTime']) != aware(fixture['kickoff_at'])):
                raise ValueError('opening FotMob observation differs from its original identity')
            if status['started'] is False and status['finished'] is False:
                label, state = 'NOT_STARTED', 'pre'
            elif status['started'] is True and status['finished'] is False:
                label, state = 'STARTED', 'in'
            elif status['finished'] is True:
                label, state = 'ENDED', 'post'
                admissible.append(ref)
            else:
                raise ValueError('ambiguous FotMob observation status')
        observations.append({'observed_at': captured.isoformat(), 'provider': provider, 'provider_status': label,
                             'state': state, 'sha256': ref['sha256'], 'path': ref['path']})
    outcomes = verify_results(matches, root, admissible, at)
    report = grade(matches, outcomes, added_firsts(bundle, matches))
    live = report['per_match'][mid]
    began = live['actual_kickoff_at']
    return {'scope': 'REGISTERED_BIG_FIVE_OPENING_KICKOFF_OBSERVATION', 'observed_at': at.isoformat(),
            'registered': report['registered'], 'verified_finals': report['verified_finals'],
            'verified_actual_starts': sum(outcome['actual_kickoff_at'] is not None for outcome in outcomes.values()),
            'opening': {'match_id': mid, 'scheduled': fixture['kickoff_at'], 'actual_kickoff_at': began,
                        'delay_seconds': (aware(began) - aware(fixture['kickoff_at'])).total_seconds() if began else None,
                        'observations': observations, 'kickoff_evidence': outcomes[mid]['kickoff_receipts'],
                        'issues': outcomes[mid]['issues']}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    bundle = Path(__file__).resolve().parent
    root = bundle / 'opening-live'
    lock = verify(read(root / 'review-freeze.json'))
    payload = lock['payload']
    if (sha(root / 'receipts.json') != payload['artifact_sha256']['receipts.json']
            or sha(bundle / 'weekend-freeze.json') != payload['weekend_freeze_sha256']):
        raise ValueError('opening receipts or weekend window differ from the review freeze')
    write_new(args.out, opening(bundle))
    if sha(args.out) != payload['artifact_sha256']['verified.json']:
        raise ValueError('opening replay differs from the review freeze')
