"""Settle the locked Big Five scores with retained regulation and actual-start evidence."""

import argparse
from datetime import datetime, timezone
import gzip
from hashlib import sha256
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from research.analysis_freeze import aware, verify
from research_program.goal_state_study import sha, write_new
from research_program.paired_kpi_inference import compare

from result_evidence import verify_results


MODEL_ARMS = ('Current', 'Test', '综合')
RESEARCH_ARMS = ('R7', 'R8', 'R14', 'R21', 'R22', 'R23')
ARMS = RESEARCH_ARMS + MODEL_ARMS
SCORE_KEYS = ('primary', 'top3', 'wdl')
DIRECTIONS = {'主胜': 'home', '平局': 'draw', '客胜': 'away'}
LOCAL = ZoneInfo('Asia/Shanghai')


def read(path):
    return json.loads(path.read_bytes())


def first_opening(bundle, fixtures):
    records = {}
    mid = 'espn:401882796'
    active_path = bundle / 'opening/first-model-pair.json.gz'
    authors_path = bundle / 'opening/first-comprehensive.json.gz'
    original = read(bundle / 'opening-comparator.json')
    followup = read(bundle / 'opening-lineups.json')
    if sha(active_path) != original['complete_receipt_sha256'] or sha(authors_path) != followup['complete_receipt']['archive_sha256']:
        raise ValueError('compressed opening receipts differ')
    for source in followup['sources']:
        path = bundle / source['file']
        if sha(path) != source['archive_sha256'] or sha256(gzip.decompress(path.read_bytes())).hexdigest() != source['sha256']:
            raise ValueError('opening lineup or process evidence differs')
    for path, ref, expected_track in (
        (active_path, original['first_model_pair'], 'current-test-pair'),
        (authors_path, followup['first_comprehensive'], 'comprehensive'),
    ):
        record = verify(json.loads(gzip.decompress(path.read_bytes())))
        fixture, locked = record['fixture'], fixtures[mid]
        if (record['record_sha256'] != ref['sha256'] or record['freeze_id'] != ref['freeze_id']
                or record['recorded_at'] != ref['recorded_at'] or record['track'] != expected_track
                or record['stage'] != 'prematch' or record['revision'] != 1 or record['previous_sha256']
                or any(fixture[key] != locked[key] for key in ('match_id', 'cohort', 'home', 'away'))
                or aware(fixture['kickoff_at']) != aware(locked['kickoff_at'])
                or not aware(fixture['cutoff_at']) <= aware(record['recorded_at']) < aware(locked['kickoff_at'])):
            raise ValueError('opening match first-model or comprehensive receipt differs from the fixture')
        payload = record['payload']
        if expected_track == 'current-test-pair':
            forecasts = {}
            for arm, key in (('Current', 'current_model'), ('Test', 'test_model')):
                pick = payload[key]
                # A modeled outcome distribution alone is not a displayed direction.
                direction = pick.get('wdl_direction')
                forecasts[arm] = {'primary': pick['primary'],
                                  'top3': [entry['score'] for entry in pick['top3']],
                                  'wdl': DIRECTIONS.get(direction)}
        else:
            if payload['current_test_reference']['sha256'] != original['first_model_pair']['sha256']:
                raise ValueError('comprehensive first did not bind the original model pair')
            forecasts = {'综合': {'primary': payload['primary'], 'top3': payload['displayed_scores'],
                                 'wdl': DIRECTIONS.get(payload['wdl'])}}
        for arm, pick in forecasts.items():
            records[arm] = {'freeze_id': record['freeze_id'], 'sha256': record['record_sha256'],
                            'recorded_at': record['recorded_at'], 'forecast': pick}
    return {mid: records}


def grade(fixtures, results, additions=None):
    """Retain the schedule even when its first issues or actual clocks are incomplete."""
    additions = additions or {}
    if results.keys() - fixtures.keys() or additions.keys() - fixtures.keys():
        raise ValueError('result or first issue lies outside the fixed fixture window')
    reports, per_match, rows = {}, {}, {}
    for mid, fixture in fixtures.items():
        evidence = results.get(mid, {})
        actual = evidence.get('actual')
        kickoff = evidence.get('actual_kickoff_at')
        frozen = dict(fixture.get('first_issues', {}), **additions.get(mid, {}))
        withheld, eligible = {}, {}
        for arm, item in frozen.items():
            if actual is not None:
                if kickoff is None:
                    withheld[arm] = 'ACTUAL_KICKOFF_UNVERIFIED'
                    continue
                if not aware(item['recorded_at']) < aware(kickoff):
                    withheld[arm] = 'FIRST_ISSUE_NOT_BEFORE_ACTUAL_START'
                    continue
            eligible[arm] = {key: item['forecast'].get(key) for key in SCORE_KEYS}
        cohort = fixture['cohort']
        rows.setdefault(cohort, []).append({'id': mid, 'cohort': cohort,
            'date': aware(fixture['kickoff_at']).astimezone(LOCAL).date().isoformat(),
            'actual': actual, 'line': None, 'forecast': eligible})
        per_match[mid] = {'cohort': cohort, 'actual': actual, 'actual_kickoff_at': kickoff,
                          'source_evidence': evidence, 'eligibility_exclusions': withheld,
                          'registered_firsts': sorted(frozen), 'score_and_direction': eligible}
    for code, scope in rows.items():
        paired = {arm: compare(scope, baseline='R7', candidate=arm) for arm in ARMS if arm != 'R7'}
        reports[code] = {'registered': len(scope), 'verified_finals': sum(row['actual'] is not None for row in scope),
            'verified_actual_starts': sum(per_match[row['id']]['actual_kickoff_at'] is not None for row in scope),
            'two_source_finals': sum(per_match[row['id']]['source_evidence'].get('both_providers', False) for row in scope),
            'strict_market': {'verified_quote_coverage': 0, 'effective_nonpush': 0, 'full_wins': 0,
                              'rate': None, 'source': 'no independently timed bookmaker quotes in this frozen packet'},
            'tracks': {'R7': paired['R8']['tracks']['R7'],
                       **{arm: report['tracks'][arm] for arm, report in paired.items()}},
            'paired_vs_R7': {arm: report['paired'] for arm, report in paired.items()}}
    return {'registered': len(fixtures), 'verified_finals': sum(report['verified_finals'] for report in reports.values()),
            'scope': 'FIRST_FROZEN_RESEARCH_AND_LOCAL_MODEL_OR_COMPREHENSIVE',
            'formal_display_eligibility': 'INDEPENDENT_DELIVERY_NOT_CERTIFIED_BY_THIS_REPLAY',
            'competitions': reports, 'per_match': per_match}


def load_window(bundle, links):
    registered = verify(read(bundle / 'weekend-freeze.json'))
    scope = bundle / 'weekend.json'
    if registered['payload']['weekend_sha256'] != sha(scope):
        raise ValueError('settlement scope differs from the original pre-kickoff freeze')
    fixtures = read(scope)['fixtures']
    if len(fixtures) != registered['payload']['registered'] or links.keys() - fixtures.keys():
        raise ValueError('settlement evidence contains an out-of-window fixture')
    return {mid: dict(row, fotmob=links.get(mid)) for mid, row in fixtures.items()}


def locked_bindings(bundle):
    folder = bundle / 'schedule'
    binding_path = folder / 'fotmob-bindings.json'
    source_path = folder / 'fotmob-sources.json'
    lock = verify(read(folder / 'fotmob-bindings-freeze.json'))
    original = verify(read(bundle / 'weekend-freeze.json'))
    signed = lock['payload']
    bindings = read(binding_path)
    if (lock['stage'] != 'prematch' or not aware(lock['recorded_at']) < aware(lock['fixture']['kickoff_at'])
            or signed['weekend_freeze_sha256'] != original['record_sha256']
            or signed['bindings_sha256'] != sha(binding_path)
            or signed['capture_index_sha256'] != sha(source_path)
            or signed['covered_fixtures'] != len(bindings)):
        raise ValueError('FotMob identity links differ from the pre-kickoff freeze')
    for source in read(source_path):
        path = bundle / source['file']
        body = path.read_bytes()
        if (sha256(body).hexdigest() != source['archive_sha256']
                or sha256(gzip.decompress(body)).hexdigest() != source['sha256']):
            raise ValueError('bound FotMob calendar bytes differ')
    return bindings


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('evidence-root', 'receipts', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--at', required=True)
    args = parser.parse_args()
    at = aware(args.at)
    if at > datetime.now(timezone.utc):
        raise ValueError('review cutoff must be an actual time')
    bundle = Path(__file__).resolve().parent
    fixtures = load_window(bundle, locked_bindings(bundle))
    evidence = verify_results(fixtures, args.evidence_root, read(args.receipts), at)
    write_new(args.out, grade(fixtures, evidence, first_opening(bundle, fixtures)))
