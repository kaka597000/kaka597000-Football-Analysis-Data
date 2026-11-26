"""Check accessible named prices and provider quote-clock coverage."""

import csv
from datetime import datetime
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo


HERE = Path(__file__).resolve().parent
SOURCES = HERE/'sources'
FIVE = SOURCES/'fivedollar'
BEIJING = ZoneInfo('Asia/Shanghai')
DOMESTIC = ('eng.1', 'esp.1', 'fra.1', 'ger.1', 'ita.1', 'jpn.1', 'jpn.2')
PHASES = ('opening', 'closing', 'inplay')
TIME_KEYS = {'openedat', 'closedat', 'quotedat', 'quotetime', 'lastupdate', 'lastupdated', 'updatedat', 'timestamp'}


def read(path):
    return json.loads(path.read_bytes())


def stamp(value):
    at = datetime.fromisoformat(value)
    if at.utcoffset() is None:
        raise ValueError('source time needs a timezone')
    return at


def prices(row, keys):
    return isinstance(row, dict) and all(isinstance(row.get(key), (int, float)) and not isinstance(row[key], bool)
                                         and isfinite(row[key]) and row[key] > 1 for key in keys)


def clock_fields(row):
    return sorted(key for key, value in (row or {}).items()
                  if value is not None and key.casefold().replace('_', '') in TIME_KEYS)


def five_markets(body, url):
    packet = body['data']
    route = urlsplit(url)
    book, = packet['bookmakers']
    if ((route.scheme, route.netloc, route.path) != ('https', 'api.5dollarfootballapi.com',
            f"/v1/fixtures/{packet['fixture_id']}/odds") or body['success'] != 1 or book['slug'] != 'bet365'):
        raise ValueError('expected the original single-event Bet365 response')
    observed = {}
    for phase in PHASES:
        wdl, total = (book['odds'][market][phase] for market in ('1x2', 'goal_line'))
        valid_total = (prices(total, ('under', 'over')) and type(total.get('line')) in (int, float)
                       and isfinite(total['line']) and total['line'] >= 0 and (4.*total['line']).is_integer())
        observed[phase] = dict(full_1x2=prices(wdl, ('home', 'draw', 'away')), full_goal_line=valid_total,
                               line=total['line'] if valid_total else None, h2h_clock_fields=clock_fields(wdl),
                               total_clock_fields=clock_fields(total))
    return packet['fixture_id'], observed


def archived_five():
    rows = []
    for code in DOMESTIC:
        path = FIVE/'legacy'/f'{code}-odds-check.json'
        saved = read(path)
        if saved['http_status'] != 200:
            raise ValueError('archived sample must have had a successful response')
        fixture, markets = five_markets(saved['response'], saved['url'])
        rows.append(dict(competition=code, fixture=fixture, archived_sha256=sha256(path.read_bytes()).hexdigest(),
                         observed_at=stamp(saved['query_time']).astimezone(BEIJING).isoformat(), phases=markets))
    return dict(rows=rows, both_price_samples=sum(any(phase['full_1x2'] and phase['full_goal_line']
                     for phase in row['phases'].values()) for row in rows),
                quote_time_field_samples=sum(any(phase['h2h_clock_fields'] or phase['total_clock_fields']
                     for phase in row['phases'].values()) for row in rows))


def verified_reply(folder, metadata, response):
    meta = read(folder/metadata)
    raw = (folder/response).read_bytes()
    if (meta['http_status'] != 200 or not meta['authenticated'] or not meta['api_success']
            or meta['response_file_sha256'] != sha256(raw).hexdigest()):
        raise ValueError('sanitized authenticated response differs from its acquisition record')
    return meta, json.loads(raw)


def recent_five():
    folder = FIVE/'recent'
    status = read(folder/'01-status.json')
    fixtures, roster = verified_reply(folder, '02-community-fixtures-metadata.json', '02-community-fixtures-response.json')
    quote, body = verified_reply(folder, '03-odds-metadata.json', '03-bet365-single-event-odds-response.json')
    fixture_id, markets = five_markets(body, quote['url'])
    selected, = (row for row in roster['data'] if row['id'] == fixture_id)
    publication = HERE.parent/'20261126-r26-j1-first-stage/nov28_29'
    with (publication/'frozen-scorecard.csv').open(encoding='utf-8', newline='') as stream:
        original, = (row for row in csv.DictReader(stream) if row['match_id'] == 'espn:401877542')
    received = stamp(quote['received_utc'])
    scheduled = stamp(selected['kickoff_utc'])
    cutoff = stamp(read(publication/'publication.json')['recorded_at'])
    names = [selected['teams'][side]['name'] for side in ('home', 'away')]
    if (status['http_status'] != 200 or status['plan_fields']['plan'] != 'community' or not status['authenticated']
            or len(roster['data']) != 5 or selected['league']['id'] != 3836571083
            or selected['status'] != 'scheduled' or names != ['Kashima Antlers', 'Fagiano Okayama']
            or scheduled.astimezone(BEIJING).strftime('%m-%d %H:%M') != original['kickoff_bjt']
            or parse_qs(urlsplit(quote['url']).query) != {'bookmakers': ['bet365']}
            or not cutoff < stamp(fixtures['received_utc']) < received < scheduled):
        raise ValueError('the independently checked J1 fixture or its source chronology differs')
    opened = stamp(body['data']['bookmakers'][0]['odds']['1x2']['opening']['opened_at'])
    return dict(match_id=original['match_id'], provider_event_id=fixture_id, teams=names, tier='community',
                scheduled=scheduled.astimezone(BEIJING).isoformat(), observed=received.astimezone(BEIJING).isoformat(),
                original_display_at=cutoff.astimezone(BEIJING).isoformat(),
                first_price_opened_at=opened.astimezone(BEIJING).isoformat(),
                first_price_age_seconds=(received-opened).total_seconds(), phases=markets)


def sporty():
    page = read(SOURCES/'sportytrader-besiktas.json')
    record, = (row for row in read(HERE.parent/'20261126-europe-first-display/publication/scorecard.json')['uel']['rows']
               if row['fixture']['match_id'] == page['match_id'])
    capture = page['capture']
    received, kickoff = stamp(capture['captured_at']), stamp(record['fixture']['kickoff_at'])
    if (capture['http_status'] != 200 or len(capture['sha256']) != 64 or capture['url'] != capture['final_url']
            or not stamp(record['first']['recorded_at']) < received < kickoff
            or any(page[key] is not None for key in ('page_kickoff', 'provider_quote_at'))
            or any(page['time_field_occurrences'].values())):
        raise ValueError('public page scope or time-field evidence differs')
    wdl = {name for name, row in page['full_time_1x2'].items() if prices(row, ('home', 'draw', 'away'))}
    overlaps = {line: sorted(wdl & {name for name, row in quotes.items() if prices(row, ('under', 'over'))})
                for line, quotes in page['full_time_goals'].items()}
    return dict(match_id=page['match_id'], scheduled=kickoff.astimezone(BEIJING).isoformat(),
                observed=received.astimezone(BEIJING).isoformat(), original_line=record['forecast']['total_line'],
                exact_kickoff_from_page=None, explicit_quote_clock=None,
                named_result_coverage=len(wdl), same_named_book_by_line=overlaps)


if __name__ == '__main__':
    print(json.dumps(dict(fivedollar_archive=archived_five(), fivedollar_recent=recent_five(), sportytrader=sporty()),
                     ensure_ascii=False, indent=2, allow_nan=False))
