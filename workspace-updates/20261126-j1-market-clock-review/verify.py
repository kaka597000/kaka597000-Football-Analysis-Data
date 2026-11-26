"""Check J1 market-clock coverage from the original November freezes and raw responses."""

import hashlib
import json
from pathlib import Path

from research.analysis_freeze import aware
from research_program import display_window_review as review


ROOT = Path(__file__).resolve().parent
ORIGINAL = ROOT.parent / '20261125-j1-stage-windows'
WEEKEND = ROOT.parent / '20261126-r26-j1-first-stage'
BSD = ROOT / 'bsd'
BSD_TEAM_ALIASES = {'espn:7111': 'JEF United Chiba', 'espn:21361': 'Kyoto Sanga FC'}


def audit_batch(root, name, plan, fixtures, match_ids):
    folder = root / name
    publication = review._read_ledger_ref(folder, review.read(folder / 'publication.json'))
    issue = publication['payload']['identity']
    if issue['parent'] != plan['record_sha256'] or issue['window'] != name or set(issue['rows']) != set(match_ids):
        raise ValueError('window publication does not bind the original registered slate')
    cache = {}
    result = []
    for mid in match_ids:
        record = review._read_ledger_ref(folder, issue['rows'][mid]['authored'])
        fixture = record['fixture']
        if (record['track'] != review.DISPLAY_TRACK or
                any(fixture[k] != fixtures[mid][k] for k in ('match_id', 'cohort', 'home', 'away')) or
                aware(fixture['kickoff_at']) != aware(fixtures[mid]['kickoff_at'])):
            raise ValueError('wrong first issue for ' + mid)
        quote = review._quote_for(record)
        market = record['payload']['market_snapshot']
        if quote['match_id'] != mid or market['quote'] != quote or set(market['h2h']) != {'home', 'draw', 'away'}:
            raise ValueError('two frozen markets do not use the same captured book for ' + mid)
        ok, error, clock = review._quote_source(quote, fixture, root / 'evidence', cache, market['h2h'])
        if not ok:
            raise ValueError(f'raw quote mismatch for {mid}: {error}')
        clock_ok, clock_error = review._market_clock_match(quote, clock)
        audit = review.quote_audit(dict(fixture, total_quote=quote))
        comp, = json.loads(cache[quote['source_sha256']][0])['header']['competitions']
        teams = {r['homeAway']: r['team']['displayName'] for r in comp['competitors']}
        result.append(dict(match_id=mid, bookmaker=quote['bookmaker'],
                           line=quote['line'], quote_time=clock, capture_time=quote['query_time'],
                           kickoff_at=fixture['kickoff_at'], freeze_at=record['recorded_at'],
                           teams=teams, team_ids={side: fixture[side] for side in teams},
                           raw_sha256=quote['source_sha256'],
                           strict=clock_ok and audit['eligible'], clock_issue=clock_error))
    return dict(registered=len(match_ids), observed_two_market_n=len(result),
                strict_quote_n=sum(row['strict'] for row in result), fixtures=result)


def november():
    registration = ORIGINAL / 'registration'
    initial = review._read_ledger_ref(registration, review.read(registration / 'plan.json'))
    plan, fixtures, slates, _ = review._registered(initial)
    return {name: audit_batch(root, name, plan, fixtures, slates[name])
            for name, root in (('nov25', ORIGINAL), ('nov28_29', WEEKEND))}


def bsd_capture(index, route):
    meta = review.read(BSD / f'request-{index:03d}-metadata.json')
    if (meta['method'] != 'GET' or meta['http_status'] != 200 or meta['request_index'] != index or
            meta['url'] != 'https://sports.bzzoiro.com/api/v2/' + route or meta['redactions']):
        raise ValueError('unexpected BSD capture metadata')
    path = BSD / meta['retained_file']
    if not path.resolve().is_relative_to((BSD / 'raw').resolve()):
        raise ValueError('BSD raw capture outside archive')
    body = path.read_bytes()
    sha = hashlib.sha256(body).hexdigest()
    if (len(body) != meta['received_bytes'] or len(body) != meta['retained_bytes']
            or sha != meta['raw_response_sha256'] or sha != meta['retained_sha256']):
        raise ValueError('BSD retained bytes differ')
    start, end = (aware(meta[f'query_time_{key}_utc']) for key in ('start', 'end'))
    if start > end:
        raise ValueError('invalid BSD capture clock')
    return json.loads(body), start, end


def bsd_probe(fixtures):
    leagues, _, first_end = bsd_capture(1, 'leagues/?limit=100')
    events, second_start, second_end = bsd_capture(2, 'events/?league_id=49&date_from=2026-11-28&date_to=2026-11-28&limit=100')
    odds, third_start, captured = bsd_capture(3, 'odds/?event_id=212344&limit=100')
    if min((second_start - first_end).total_seconds(), (third_start - second_end).total_seconds()) < 3:
        raise ValueError('requests deviate from registered provider pacing')
    league, = (r for r in leagues['results'] if r['id'] == 49)
    if (league['name'], league['country'], league['is_women'], league['current_season']['id']) != ('J1 League', 'Japan', False, 1518):
        raise ValueError('BSD is outside the adult J1 competition')

    given = [r for r in fixtures if aware(r['kickoff_at']).date().isoformat() == '2026-11-28']
    identities = {}
    for row in given:
        home, away = (BSD_TEAM_ALIASES.get(row['team_ids'][s], row['teams'][s]) for s in ('home', 'away'))
        event, = (e for e in events['results'] if (e['home_team'], e['away_team']) == (home, away)
                  and aware(e['event_date']) == aware(row['kickoff_at']))
        if (event['league_id'], event['season_id'], event['stage'], event['status']) != (49, 1518, 'regular-season', 'notstarted'):
            raise ValueError('BSD event does not match the scheduled J1 slate')
        identities[row['match_id']] = event['id']
    if len(given) != 5 or len(set(identities.values())) != events['count'] or events['next'] is not None:
        raise ValueError('BSD fixture results differ from the original 11/28 J1 population')

    match = 'espn:401877542'
    event_id = identities[match]
    rows = odds['results']
    if (event_id != 212344 or odds['count'] != len(rows) or odds['next'] is not None
            or {r['event_id'] for r in rows} != {event_id}
            or {r['bookmaker_slug'] for r in rows} != {'consensus'}):
        raise ValueError('BSD quote rows are outside the observed consensus response')
    quote_time, = {aware(r['updated_at']) for r in rows}
    age = (captured - quote_time).total_seconds()
    first = aware(next(r['freeze_at'] for r in given if r['match_id'] == match))
    if not first < quote_time <= captured or age > 3600:
        raise ValueError('BSD clock or original freeze chronology differs')
    groups = {}
    for market, line, outcomes in (('1x2', None, {'home', 'draw', 'away'}),
                                    ('over_under_25', 2.5, {'over', 'under'})):
        selected = [r for r in rows if r['market'] == market and r['line'] == line]
        prices = {r['outcome'].lower(): r['decimal_odds'] for r in selected}
        if set(prices) != outcomes or len(prices) != len(selected):
            raise ValueError('incomplete or duplicate observed prices')
        books, = {r['bookmaker_count'] for r in selected}
        groups[market] = dict(line=line, prices=prices, aggregated_books=books)
    return dict(schedule_matches=identities, probe_match=match, quote_rows=len(rows), quote_time=quote_time.isoformat(),
                capture_time=captured.isoformat(), age_seconds=age, groups=groups, strict_named_book_pair=False)


if __name__ == '__main__':
    windows = november()
    if [(r['registered'], r['strict_quote_n']) for r in windows.values()] != [(7, 0), (10, 0)]:
        raise ValueError('original November market coverage differs from the documented replay')
    print(json.dumps(dict(november=windows, bsd=bsd_probe(windows['nov28_29']['fixtures'])),
                     ensure_ascii=False, indent=2))
