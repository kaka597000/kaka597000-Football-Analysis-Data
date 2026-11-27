"""Rebuild the December J1 official pregame binding and strict market probe."""

import argparse
import json
from pathlib import Path
import tarfile
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlsplit

from research.analysis_freeze import aware, save, verify
from research_program import club_market_capture as market
from research_program import display_window_review as display
from research_program import goal_state_forward as ledger
from research_program import jleague_kickoff_proof as kickoff
from research_program.goal_state_study import sha, write_new
from research_program.nov25_first_review import official_binding


HERE = Path(__file__).resolve().parent
ORIGINAL = HERE.parent / '20261126-r26-j1-first-stage'
REGISTRATION = HERE.parent / '20261126-j1-december-windows/registration'
PLAN = HERE.parent / '20261127-europe-round1-review'
OFFICIAL = HERE / 'official'
MARKET = HERE / 'market-probe'
PACKET = HERE / 'kickoff-packet.json'
CHECK_MATCH = 'espn:401877542'


def read(path):
    return json.loads(path.read_bytes())


def binding_inputs():
    plan = ledger._read(REGISTRATION, read(REGISTRATION / 'plan.json'))
    plan, fixtures, slates, _ = display._registered(plan)
    plan_file = PLAN / 'j1-capture-plan.json'
    review = verify(read(PLAN / 'review-freeze.json'))
    if review['stage'] != 'review' or review['payload']['j1_capture_plan_sha256'] != sha(plan_file):
        raise ValueError('December fixture collection plan does not match the registered evidence')
    existing = read(plan_file)['windows']
    captures = read(OFFICIAL / 'captures.json')
    by_id = {row['match_id']: row for row in captures}
    if len(by_id) != len(captures) or by_id.keys() != fixtures.keys():
        raise ValueError('expected exactly twenty original J1 match cards')
    reused = read(OFFICIAL / 'reused-121302-source-metadata.json')
    previous, = [row for row in captures if row['code'] == '121302']
    if (reused['url'], reused['sha256'], reused['status'], aware(reused['started_utc']),
            aware(reused['received_utc'])) != (previous['url'], previous['sha256'], previous['http_status'],
            aware(previous['requested_at_utc']), aware(previous['captured_at_utc'])):
        raise ValueError('the reused J.League page differs from its original capture metadata')

    entries = {}
    for name, mids in slates.items():
        planned = existing[name]
        originals = [f for wave in planned['waves'] for f in wave['fixtures']]
        if planned['registration'] != plan['freeze_id'] or sorted(f['match_id'] for f in originals) != sorted(mids):
            raise ValueError('official match-card targets differ from the locked December window')
        for game in originals:
            mid = game['match_id']
            ref = by_id[mid]
            names = {s: game['official_' + s] for s in ('home', 'away')}
            if (ref['window'] != name or ref['url'] != game['official_match_url']
                    or aware(ref['requested_at_utc']) > aware(ref['captured_at_utc'])):
                raise ValueError('unexpected J.League match-card capture: ' + mid)
            source = {k: ref[k] for k in ('raw_file', 'url', 'code', 'captured_at_utc', 'http_status', 'sha256')}
            body = kickoff.raw(OFFICIAL, source, aware(fixtures[mid]['kickoff_at']))
            entries[mid] = dict(source=source, identity=official_binding(body, source, fixtures[mid], names))
    return plan, fixtures, slates, dict(registration_sha256=plan['record_sha256'], bindings=entries,
                                        capture_manifest_sha256=sha(OFFICIAL / 'captures.json'),
                                        capture_plan_sha256=sha(plan_file))


def seal(plan, fixtures, payload):
    latest = max(aware(row['source']['captured_at_utc']) for row in payload['bindings'].values())
    earliest = min(aware(f['kickoff_at']) for f in fixtures.values())
    target = dict(match_id='j1-official-kickoff:' + plan['record_sha256'],
                  kickoff_at=earliest.isoformat(), cutoff_at=latest.isoformat())
    receipt = save(payload, target, stage='prematch', track=kickoff.TRACK,
                   idempotency_key=payload['capture_manifest_sha256'])
    record = verify(read(Path(receipt['path'])))
    if record['record_sha256'] != receipt['sha256']:
        raise ValueError('official binding differs from canonical receipt')
    write_new(PACKET, dict(binding_record=record, captures={}))


def official_replay(plan, fixtures, slates, payload):
    packet = read(PACKET)
    record = packet['binding_record']
    cutoff = aware(record['recorded_at'])
    mapping = kickoff.bindings(packet, plan, fixtures, OFFICIAL, cutoff)
    if record['payload'] != payload or packet['captures'] or mapping.keys() != fixtures.keys():
        raise ValueError('packet must preserve every original pregame match card')
    with TemporaryDirectory(prefix='december-j1-bound-') as directory:
        state = Path(directory)
        review = display.review(plan, ledger_root=state, result_state=state, evidence_root=state,
                                kickoff_evidence_root=OFFICIAL, jleague_kickoffs=packet, at=cutoff)
    windows = {}
    for name, mids in slates.items():
        row = review['windows'][name]
        if row['registered_n'] != 10 or row['confirmed_first_score_n'] or row['completed_n'] or row['jleague_kickoff_evidence']:
            raise ValueError('pregame evidence was misclassified as an actual result or confirmed issue')
        windows[name] = dict(bound=len(mids), sections=sorted({mapping[mid]['section'] for mid in mids}),
                             actual_starts_verified=0, pending_results=row['pending_n'])
    return dict(freeze_id=record['freeze_id'], recorded_at=record['recorded_at'], windows=windows)


def market_capture():
    refs = read(MARKET / 'captures.json')
    data = {}
    for ref in refs:
        path = (MARKET / ref['path']).resolve()
        if (not path.is_relative_to(MARKET) or ref['http_status'] != 200
                or sha(path) != ref['sha256'] or path.stat().st_size != ref['bytes']
                or not aware(ref['requested_at_utc']) <= aware(ref['received_at_utc'])):
            raise ValueError('market capture no longer matches its original evidence')
        data[ref['request_id']] = read(path), dict(file=ref['path'], url=ref['url'], sha256=ref['sha256'],
                                                   requested_at=ref['requested_at_utc'],
                                                   captured_at=ref['received_at_utc'])
    if len(refs) != len(data) or len(data) != 5:
        raise ValueError('expected the five bounded market requests')
    return data


def replay_market():
    data = market_capture()
    dates = {}
    for day in ('2026-12-04', '2026-12-12'):
        events, meta = data['schedule-' + day + '-utc']
        if parse_qs(urlsplit(meta['url']).query).get('date') != [day]:
            raise ValueError('market schedule samples differ from their recorded dates')
        dates[day] = dict(events=len(events['data']), j1=sum(
            (e['league']['id'], e['league']['name']) == market.LEAGUES['jpn.1'] for e in events['data']),
            more_pages=bool(events['page']['next_cursor']))
    events, event_meta = data['control-2026-11-28-utc']
    odds, odds_meta = data['control-kashima-okayama-odds']
    provider_id = odds['event_id']
    event, = [e for e in events['data'] if e['id'] == provider_id]
    info, = [r for r in read(ORIGINAL / 'evidence/calendar-manifest.json') if r['label'] == 'target_1128']
    raw_url = info['url']
    with tarfile.open(ORIGINAL / 'evidence/public-source-snapshots.tar.gz') as archive:
        board_raw = archive.extractfile(info['raw_file']).read()
    target, = [e for e in json.loads(board_raw)['events'] if 'espn:' + e['id'] == CHECK_MATCH]
    teams = {t['homeAway']: t['team'] for t in target['competitions'][0]['competitors']}
    fixture = dict(match_id=CHECK_MATCH, home='espn:' + teams['home']['id'], away='espn:' + teams['away']['id'],
                   kickoff_at=target['date'], cutoff_at=info['retrieved_at_utc'],
                   competition='jpn.1', cohort='jpn.1', stage='regular', score_basis='regulation_90')
    crosswalk = {}
    for side in ('home', 'away'):
        matched = event[side + '_team']
        if matched['name'] != teams[side]['displayName']:
            raise ValueError('the representative J1 market event requires an exact side match')
        crosswalk[fixture[side]] = dict(provider_id=matched['id'], provider_name=matched['name'],
                                        espn_name=teams[side]['displayName'])
    with TemporaryDirectory(prefix='december-j1-market-') as directory:
        root = Path(directory)
        (root / 'board.json').write_bytes(board_raw)
        for meta in (event_meta, odds_meta):
            path = root / meta['file']
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((MARKET / meta['file']).read_bytes())
        sources = dict(event_id=provider_id, events=event_meta, odds=odds_meta, espn=dict(
            url=raw_url, captured_at=info['retrieved_at_utc'], sha256=info['sha256'], file='board.json'))
        prepared = market.attach(fixture, root, sources, {'jpn.1': crosswalk}, odds_meta['captured_at'])
        if not odds['stale'] or prepared['market_snapshots'] or 'total_quote' in prepared:
            raise ValueError('the confirmed stale market must retain an unavailable strict price')
    both = {r['bookmaker'] for r in odds['odds'] if r['market_type'] == '1x2'} & {
        r['bookmaker'] for r in odds['odds'] if r['market_type'] == 'totals'}
    latest = max(aware(r['as_of']) for r in odds['odds'])
    core, _ = data['espn-core-j1-kashima-okayama-odds']
    return dict(december_date_samples=dates, control_match=CHECK_MATCH, provider_event=provider_id,
                inferred_quote_rows=len(odds['odds']), named_book_pairs=len(both),
                newest_row_age_seconds=(aware(odds_meta['captured_at']) - latest).total_seconds(),
                infersports_stale=odds['stale'], strict_control_quotes=len(prepared['market_snapshots']),
                espn_core_named_books=len(core['items']),
                espn_core_clocked_books=sum(display._raw_market_clock(r) is not None for r in core['items']))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--issue', action='store_true')
    args = parser.parse_args()
    plan, fixtures, slates, payload = binding_inputs()
    if args.issue and not PACKET.exists():
        seal(plan, fixtures, payload)
    print(json.dumps(dict(official=official_replay(plan, fixtures, slates, payload),
                          market=replay_market()), ensure_ascii=False, indent=2))
