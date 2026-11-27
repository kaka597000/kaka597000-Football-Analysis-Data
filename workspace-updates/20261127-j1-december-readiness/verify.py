"""Build the December J1 market inputs from independently matched schedule evidence."""

import argparse
from datetime import timedelta, timezone
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import tarfile
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlsplit
from unittest.mock import Mock, patch

from automation.infer_market_snapshot import BASE, read_evidence
from automation.market_identity import scheduled_competition
from competition_scope import CONFIG
from research.analysis_freeze import aware
from research.display_delivery import check_issue_scope
from research_program import club_market_capture as market
from research_program import display_window_review as display
from research_program import goal_state_forward as ledger
from research_program import jleague_kickoff_proof


HERE = Path(__file__).resolve().parent
ARCHIVES = HERE.parent
NOVEMBER = ARCHIVES / '20261125-j1-stage-windows/registration'
ESPN = ARCHIVES / '20261126-r26-j1-first-stage/evidence'
DECEMBER = ARCHIVES / '20261126-j1-december-windows/registration'
OFFICIAL = ARCHIVES / '20261127-j1-december-evidence'
CLOCKED_EVENT = 'espn:401877523'
ALIASES = {
    '21361': ('Kyoto Sanga', 'K.P.Sanga'),
    '3385': ('Urawa Red Diamonds', 'Urawa Red Diamond'),
    '7111': ('JEF United Ichihara-Chiba', 'J.U.Ichihara'),
    '7114': ('Sanfrecce Hiroshima', 'Hiroshima Sanfrecce'),
    '131701': ('Mito Hollyhock', 'M.Hollyhock'),
    '7116': ('Yokohama F. Marinos', 'Yokohama F Marinos'),
    '7112': ('Kawasaki Frontale', 'Kawasaki.F'),
    '7102': ('Gamba Osaka', 'Gamba.O'),
    '7108': ('Nagoya Grampus', 'Nagoya Grampus Eight'),
    '22167': ('Machida Zelvia', 'Machida.Z'),
    '3393': ('Tokyo Verdy 1969', 'T.Verdy'),
}


def read(path):
    return json.loads(path.read_bytes())


def read_capture(root, ref, endpoint):
    return read_evidence(root, ref, cutoff=ref['captured_at'], expected=endpoint)


def public_receipt(path):
    receipt = read(path)
    if (receipt['http_status'] != 200 or receipt['authorization_header_sent'] is not False
            or receipt['redirects_followed'] != 0):
        raise ValueError('expected a direct public InferSports response')
    return dict(file=receipt['raw_file'], url=receipt['url'], sha256=receipt['response_sha256'],
                captured_at=receipt['response_received_at_utc'], requested_at=receipt['request_started_at_utc'])


def provider_captures():
    existing = OFFICIAL / 'market-probe'
    saturday, = [x for x in read(existing / 'captures.json') if x['request_id'] == 'control-2026-11-28-utc']
    before = dict(file=saturday['path'], url=saturday['url'], sha256=saturday['sha256'],
                  captured_at=saturday['received_at_utc'], requested_at=saturday['requested_at_utc'])
    if saturday['http_status'] != 200:
        raise ValueError('Saturday provider schedule is unavailable')
    schedule = public_receipt(HERE / 'captures/schedule.json')
    odds = public_receipt(HERE / 'captures/odds.json')
    return [(existing, before), (HERE, schedule)], odds


def registered(root, expected):
    plan = ledger._read(root, read(root / 'plan.json'))
    if plan['freeze_id'] != expected:
        raise ValueError(f'expected the original registration {expected}')
    return display._registered(plan)


def matches(boards):
    _, universe, slates, _ = registered(NOVEMBER, '99791e2c015d1473-v000001')
    team_ids, provider_ids, by_fixture = {}, set(), {}
    manifest = read(ESPN / 'calendar-manifest.json')
    with tarfile.open(ESPN / 'public-source-snapshots.tar.gz') as pack:
        for label, (root, source) in zip(('target_1128', 'target_1129'), boards, strict=True):
            info, = [x for x in manifest if x['label'] == label]
            body = pack.extractfile(info['raw_file']).read()
            if sha256(body).hexdigest() != info['sha256']:
                raise ValueError('ESPN schedule bytes differ')
            provider = read_capture(root, source, BASE + '/v1/events')
            entries = json.loads(body)
            if [row['slug'] for row in entries['leagues']] != ['jpn.1']:
                raise ValueError('expected ESPN J1')
            for event in entries['events']:
                mid = 'espn:' + event['id']
                fixture = universe[mid]
                _, teams = scheduled_competition(event)
                names = {side: team['displayName'] for side, team in teams.items()}
                if (event['season']['slug'] != 'regular-season' or event['status']['type']['state'] != 'pre'
                        or any('espn:' + team['id'] != fixture[side] for side, team in teams.items())
                        or aware(event['date']) != aware(fixture['kickoff_at'])
                        or max(aware(info['retrieved_at_utc']), aware(source['captured_at'])) >= aware(event['date'])):
                    raise ValueError(f'expected the original regular J1 fixture {mid}')
                expected = {side: ALIASES.get(team['id'], (names[side], names[side])) for side, team in teams.items()}
                if any(pair[0] != names[side] for side, pair in expected.items()):
                    raise ValueError(f'an archived ESPN alias has changed for {mid}')
                matched, = [item for item in provider['data']
                            if (item['league']['id'], item['league']['name']) == market.LEAGUES['jpn.1']
                            and item['sport'] == 'football' and item['status'] == 'scheduled'
                            and aware(item['scheduled_at']) == aware(fixture['kickoff_at'])
                            and all(item[side + '_team']['name'] == pair[1] for side, pair in expected.items())]
                for side in teams:
                    provider_id = matched[side + '_team']['id']
                    if fixture[side] in team_ids or provider_id in provider_ids:
                        raise ValueError('registered round must identify twenty distinct teams')
                    provider_ids.add(provider_id)
                    team_ids[fixture[side]] = dict(espn_name=names[side], provider_name=expected[side][1],
                                                   provider_id=provider_id)
                by_fixture[mid] = dict(fixture=fixture, event_id=matched['id'], espn_metadata=info,
                                      espn_body=body, event_root=root, events=source)
    if set(by_fixture) != set(slates['nov28_29']) or len({r['event_id'] for r in by_fixture.values()}) != len(by_fixture):
        raise ValueError('provider must cover every registered November 28–29 fixture exactly once')
    return team_ids, by_fixture


def window_inputs(team_ids):
    plan, fixtures, slates, specs = registered(DECEMBER, '836802cb5ce13a38-v000001')
    packet = read(OFFICIAL / 'kickoff-packet.json')
    bindings = jleague_kickoff_proof.bindings(packet, plan, fixtures, OFFICIAL / 'official',
                                             aware(packet['binding_record']['recorded_at']))
    if set(bindings) != set(fixtures) or sha256(CONFIG.read_bytes()).hexdigest() != plan['payload']['identity']['scope_sha256']:
        raise ValueError('official match cards and the original approved scope are required')
    outputs, scopes, counts = {}, {}, {}
    for name, mids in slates.items():
        rows = [dict(fixtures[mid], competition='jpn.1', stage='regular', score_basis='regulation_90',
                     identity_verified=True, stage_verified=True,
                     provider_competition='jpn.1', provider_stage='2026-27 Japanese J1 League, Regular Season')
                for mid in mids]
        teams = {f[side] for f in rows for side in ('home', 'away')}
        if teams != set(team_ids):
            raise ValueError(f'not every {name} team has an independently bound source key')
        scope = dict(competition='jpn.1', cohort='jpn.1',
                     stages=[plan['payload']['identity']['protocol']['competition_stage']])
        for fixture in rows:
            check_issue_scope(fixture, scope)
        outputs[name] = sorted(rows, key=lambda row: (aware(row['kickoff_at']), row['match_id']))
        scopes[name] = {f['match_id']: scope for f in rows}
        counts[name] = dict(fixtures=len(rows), teams_with_provider_ids=len(teams),
                            official_sections=sorted({bindings[mid]['section'] for mid in mids}),
                            first_scheduled_at=outputs[name][0]['kickoff_at'],
                            minimum_strict_quotes=specs[name]['minimum_strict_line_issues'])
    return plan, outputs, scopes, counts


def quote_check(teams, source, odds):
    fixture = dict(source['fixture'], competition='jpn.1', stage='regular', score_basis='regulation_90')
    cutoff = aware(odds['captured_at'])
    raw = read_capture(HERE, odds, BASE + f"/v1/events/{source['event_id']}/odds")
    loader = spec_from_file_location('club_market_collector', CONFIG.parents[1] / 'scripts/capture_public_club_markets.py')
    collector = module_from_spec(loader)
    loader.loader.exec_module(collector)
    board = source['espn_metadata']
    sources = {
        '/apis/site/v2/sports/soccer/jpn.1/scoreboard': (source['espn_body'], dict(
            url=board['url'], sha256=board['sha256'], captured_at=board['retrieved_at_utc'])),
        '/v1/events': ((source['event_root'] / source['events']['file']).read_bytes(), source['events']),
        f"/v1/events/{source['event_id']}/odds": ((HERE / odds['file']).read_bytes(), odds),
    }

    def saved_response(url, path):
        body, original = sources[urlsplit(url).path]
        path.write_bytes(body)
        return dict(original, file=path.name)

    with TemporaryDirectory(prefix='j1-quote-preflight-') as directory:
        root = Path(directory) / 'evidence'
        replays = []
        with (patch.object(collector, 'board_fetch', lambda url, _, path: saved_response(url, path)),
              patch.object(collector, 'provider_fetch', saved_response),
              patch.object(collector, 'datetime', Mock(now=Mock(return_value=cutoff))),
              patch.object(collector, 'sleep')):
            for window in ('replay-first', 'replay-second'):
                bound, = collector.collect([fixture], {'jpn.1': teams}, root / window, archive_root=root)
                recorded = bound['market_evidence']
                if any(Path(recorded[key]['file']).parent.as_posix() != window for key in ('espn', 'events', 'odds')):
                    raise ValueError('window raw paths must resolve from the common archive')
                market.bound_odds(bound, root, recorded, {'jpn.1': teams}, odds['captured_at'])
                replays.append(bound)
    clocks = [aware(row['as_of']) for row in raw['odds']]
    newer_envelope = cutoff - aware(raw['as_of'])
    newest_row = max(clocks)
    if (raw['stale'] is not False or not timedelta() <= newer_envelope <= market.MAXIMUM_QUOTE_AGE
            or cutoff - newest_row <= market.MAXIMUM_QUOTE_AGE
            or any('total_quote' in f or f['market_snapshots'] for f in replays)):
        raise ValueError('the live envelope cannot substitute for the original bookmaker quote times')
    by_market = {kind: {row['bookmaker'] for row in raw['odds'] if row['market_type'] == kind}
                 for kind in ('1x2', 'totals')}
    return dict(match_id=fixture['match_id'], event_id=source['event_id'], bookmaker_rows=len(clocks),
                named_same_book_pairs=len(by_market['1x2'] & by_market['totals']), stale=raw['stale'],
                captured_at=odds['captured_at'], envelope_age_seconds=newer_envelope.total_seconds(),
                newest_bookmaker_row_age_seconds=(cutoff - newest_row).total_seconds(),
                strict_snapshot_rows=len(replays[0]['market_snapshots']), strict_total='total_quote' in replays[0],
                nested_archive_paths_replayed=len(replays))


def december_schedule_probe(windows, teams):
    league_id, league_name = market.LEAGUES['jpn.1']
    all_fixtures = [fixture for window in windows.values() for fixture in window]
    output = {}
    for day in ('2026-12-04', '2026-12-12'):
        meta = public_receipt(HERE / f'captures/{day}.json')
        expected = dict(sport=['football'], league=[league_id], date=[day], timezone=['UTC'],
                        status=['scheduled'], limit=['200'])
        if parse_qs(urlsplit(meta['url']).query) != expected:
            raise ValueError(f'the targeted league query differs for {day}')
        raw = read_capture(HERE, meta, BASE + '/v1/events')
        if raw['page']['next_cursor'] or any((event['league']['id'], event['league']['name']) !=
                                            (league_id, league_name) for event in raw['data']):
            raise ValueError(f'expected the complete league-specific page for {day}')
        eligible = [f for f in all_fixtures if aware(f['kickoff_at']).astimezone(timezone.utc).date().isoformat() == day]
        matched = {}
        for fixture in eligible:
            h, a = [teams[fixture[k]]['provider_id'] for k in ('home', 'away')]
            rows = [event for event in raw['data'] if event['sport'] == 'football' and event['status'] == 'scheduled'
                    and aware(event['scheduled_at']) == aware(fixture['kickoff_at'])
                    and (event['home_team']['id'], event['away_team']['id']) == (h, a)]
            if len(rows) > 1:
                raise ValueError(f'duplicate provider event for {fixture["match_id"]}')
            if rows:
                matched[fixture['match_id']] = rows[0]['id']
        output[day] = dict(registered=len(eligible), provider_events=len(raw['data']), verified_event_ids=matched,
                           captured_at=meta['captured_at'])
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    sources, odds = provider_captures()
    team_ids, by_fixture = matches(sources)
    plan, windows, scopes, counts = window_inputs(team_ids)
    quote = quote_check(team_ids, by_fixture[CLOCKED_EVENT], odds)
    results = {'team-ids.json': {'jpn.1': team_ids}, 'approved-scopes.json': scopes,
               'readiness.json': dict(registration=plan['freeze_id'], reviewed_prior_round=len(by_fixture),
                                      windows=counts, quote_sample=quote,
                                      december_schedule_probe=december_schedule_probe(windows, team_ids))}
    results.update({f'market-fixtures-{name}.json': rows for name, rows in windows.items()})
    args.out.mkdir(parents=True, exist_ok=False)
    for name, document in results.items():
        (args.out / name).write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + '\n')
