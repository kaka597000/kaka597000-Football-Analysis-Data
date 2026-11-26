"""Replay known J1 finishes and the pending R28 slate from retained evidence."""

import hashlib
import json
from pathlib import Path

from research_program import display_window_review, j1_process_review


ROOT = Path(__file__).resolve().parent
DATA = ROOT.parents[1]
UPDATES = ROOT.parent
ORIGINAL = UPDATES / '20261125-j1-stage-windows'
STATE = ROOT / 'nov25-state'
ISSUED = UPDATES / '20261126-r28-j1-process-forward/issued'
AT = '2026-11-26T14:40:00+08:00'


def read(path):
    return json.loads(path.read_bytes())


def verify_market_probe():
    evidence = ROOT / 'bsd'
    requests = read(evidence / 'request-audit.json')
    if [r['http_status'] for r in requests] != [302, 200, 200, 403]:
        raise ValueError('BSD request record differs')
    for meta, name in zip(requests[2:], ('bookmakers.json', 'pinnacle-response.json'), strict=True):
        body = (evidence / name).read_bytes()
        if (len(body) != meta['response_bytes'] or
                hashlib.sha256(body).hexdigest() not in {meta.get('response_sha256'), meta.get('retained_sha256')}):
            raise ValueError('BSD retained response differs')
    doc = read(evidence / 'schema-excerpt.json')['routes']
    if not any(p['name'] == 'bookmaker_slug' for p in doc['/api/v2/odds/']['parameters']):
        raise ValueError('official documentation lacks the recorded filter')
    denial = read(evidence / 'pinnacle-response.json')
    if denial['code'] != 'bookmakers_not_entitled' or 'Football Unlimited' not in denial['detail']:
        raise ValueError('BSD entitlement response differs')
    return dict(provider='BSD', bookmaker='Pinnacle', event_id=212344, status=403, code=denial['code'])


def verify():
    plan = read(ORIGINAL / 'registration/99791e2c015d1473-v000001.json')
    report = display_window_review.review(plan, ledger_root=ORIGINAL / 'nov25', batch_root=ORIGINAL,
                                          result_state=STATE, evidence_root=STATE, at=AT)
    first = report['windows']['nov25']
    results = {r['match_id']: r['actual_result'] for r in first['per_match']}
    if len(results) != 7 or None in results.values() or first['completed_n'] != 7 or first['confirmed_first_score_n']:
        raise ValueError('coverage or display certification differs for the seven original matches')
    r28 = j1_process_review.review(DATA, ISSUED, STATE, at=AT)
    seats = {arm: s['pending'] for arm, s in r28['selected'].items()}
    if r28['registered'] != 10 or r28['settled'] or r28['pending'] != 10 or seats != {
            'common_prior': 3, 'goals_history': 3, 'xg_history': 3}:
        raise ValueError('R28 review must retain all unplayed matches and ranked seats')
    return dict(as_of=AT, nov25_verified_regulation=results, nov25_confirmed_first_display=0,
                r28_registration=r28['original_registration'], r28_pending=r28['pending'],
                ranked_seats_pending=seats, bsd_named_probe=verify_market_probe())


if __name__ == '__main__':
    print(json.dumps(verify(), ensure_ascii=False, indent=2))
