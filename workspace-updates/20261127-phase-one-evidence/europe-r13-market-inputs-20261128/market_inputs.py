"""Prepare the two registered UEL R13 research price inputs from retained captures."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from research.analysis_freeze import aware, verify
from research_program.club_market_capture import attach
from research_program.future_validation import quote_audit, write_new
from research_program.market_baseline import _paired_capture


ARM_FULL = 'r13_full_market'
ARM_1X2 = 'r13_wdl_only'
IDENTITY = ('match_id', 'cohort', 'competition', 'stage', 'home', 'away', 'score_basis',
            'provider_season', 'market_provider_event_id')
SCOPE = 'uefa.europa'


def read(path):
    return json.loads(path.read_bytes())


def locked_population(registration, fixtures):
    receipt = verify(registration)
    payload = receipt['payload']
    planned = payload['fixtures']
    if (receipt['stage'] != 'prematch' or receipt['revision'] != 2
            or payload['cohort'] != SCOPE or payload['original_eligibility_denominator'] != len(planned)
            or len(fixtures) != len(planned) or {row['match_id'] for row in fixtures} != planned.keys()
            or set(payload['arms']) != {ARM_FULL, ARM_1X2}):
        raise ValueError('expected the complete original UEL research registration')
    for fixture in fixtures:
        record = planned[fixture['match_id']]
        if (fixture['cohort'] != SCOPE or fixture['home'] != record['home'] or fixture['away'] != record['away']
                or aware(fixture['kickoff_at']) != aware(record['kickoff_at'])):
            raise ValueError('registered research fixture or schedule changed')
    return receipt


def model_prices(attached):
    """Retain complete pairs and, separately, independently eligible 1X2 rows."""
    audit = quote_audit(attached)
    pair, reason = _paired_capture(attached, audit['quote']) if audit['eligible'] else (None, None)
    if pair and pair['total']['line'] > 0:
        h2h, total = pair['h2h'], pair['total']
        return dict(arms={
            ARM_FULL: dict(h2h=h2h['decimal_odds'], total=dict(total['decimal_odds'], line=total['line']),
                           paired_market=True),
            ARM_1X2: dict(h2h=h2h['decimal_odds'], total=None, paired_market=False),
        }, selected_quotes={'h2h': h2h, 'total': total}, market_state='SAME_BOOK_PAIR')
    if pair:
        reason = 'TOTAL_LINE_OUTSIDE_R13_DOMAIN'
    candidates = [row for row in attached['market_snapshots'] if row['market'] == '1x2']
    if candidates:
        row = min(candidates, key=lambda quote: (-aware(quote['quoted_at']).timestamp(), quote['bookmaker']))
        return dict(arms={ARM_1X2: dict(h2h=row['decimal_odds'], total=None, paired_market=False)},
                    selected_quotes={'h2h': row}, market_state='1X2_ONLY',
                    full_market_missing_reason=reason or 'NO_FRESH_SAME_BOOK_PAIR')
    return dict(arms={}, selected_quotes={}, market_state='NO_FRESH_1X2',
                full_market_missing_reason=reason or 'NO_FRESH_SAME_BOOK_PAIR')


def prepare(registration, fixtures, observed, root, team_ids, cutoff):
    """Reread raw source bytes at the intended model cutoff; retain all 18 fixtures."""
    receipt = locked_population(registration, fixtures)
    cutoff = aware(cutoff)
    if not aware(receipt['recorded_at']) <= cutoff <= datetime.now(timezone.utc):
        raise ValueError('actual cutoff must follow registration and cannot be in the future')
    supplied = {row['match_id']: row for row in observed}
    if (len(supplied) != len(observed)
            or supplied.keys() - {row['match_id'] for row in fixtures}):
        raise ValueError('duplicate or out-of-window market evidence')
    output = []
    for fixture in fixtures:
        mid = fixture['match_id']
        capture = supplied.get(mid, {})
        source = capture.get('market_evidence')
        summary = dict(fixture=fixture, source_cutoff_at=cutoff.isoformat(),
                       quote_time_basis='SUPPLIER_MARKET_ROW_AS_OF',
                       bookmaker_native_quote_time_verified=False, arms={}, selected_quotes={})
        if capture and (any(capture.get(key) != fixture[key] for key in IDENTITY)
                        or aware(capture['kickoff_at']) != aware(fixture['kickoff_at'])):
            raise ValueError('unmatched market fixture: ' + mid)
        if cutoff >= aware(fixture['kickoff_at']):
            summary['market_state'] = 'PASSED_PLANNED_KICKOFF'
        elif not source:
            summary['market_state'] = 'NO_RETAINED_CAPTURE'
        else:
            try:
                attached = attach(fixture, root, source, team_ids, cutoff.isoformat())
                summary.update(model_prices(attached), market_evidence=source)
            except (OSError, KeyError, ValueError, TypeError) as error:
                summary.update(market_state='RAW_EVIDENCE_REJECTED', rejection=str(error))
        output.append(summary)
    return {'status': 'RESEARCH_PRICE_INPUTS_ONLY', 'registration_sha256': receipt['record_sha256'],
            'registered': len(fixtures),
            'eligible': {name: sum(name in row['arms'] for row in output) for name in (ARM_FULL, ARM_1X2)},
            'same_fixture_pairs': sum(set(row['arms']) == {ARM_FULL, ARM_1X2} for row in output),
            'fixtures': output}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('registration', 'registered-fixtures', 'prepared-fixtures', 'raw-root', 'team-ids', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--cutoff', required=True)
    args = parser.parse_args()
    value = prepare(read(args.registration), read(args.registered_fixtures), read(args.prepared_fixtures),
                    args.raw_root, read(args.team_ids), args.cutoff)
    write_new(args.out, value)
