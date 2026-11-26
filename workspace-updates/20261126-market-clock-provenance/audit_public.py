"""Extract a field-preserving quote sample from retained public website responses."""

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo


ARCHIVE = Path(__file__).resolve().parent.parent / '20261126-europe-first-display'
MATCH = 'espn:401915513'
BEIJING = ZoneInfo('Asia/Shanghai')
BLOCK = re.compile(r'<!--(\{"repub":.*?\})-->', re.DOTALL)


def retained(path, digest):
    body = path.read_bytes()
    if sha256(body).hexdigest() != digest:
        raise ValueError('public probe response checksum differs: ' + path.name)
    return body


def winner_quotes(state, market_id, captured):
    rows = {bet['betName']: state['odds'][key] for key, bet in state['bets']['entities'].items()
            if bet['marketId'] == market_id}
    if rows.keys() != {'Sunderland', 'Draw', 'Bialystok'}:
        raise ValueError('three regulation outcomes from the identified fixture are required')
    codes = set.intersection(*(set(book_quotes) for book_quotes in rows.values()))
    books = state['bookmakers']['entities']
    complete = []
    for code in sorted(codes):
        selections = {outcome: quoted[code] for outcome, quoted in rows.items()}
        if not all(row['status'] == 'ACTIVE' and row['notExpired'] and not row['expired']
                   and row['betFeedTimestamp'] and row['bookmakerCode'] == code for row in selections.values()):
            continue
        odds = {}
        for outcome, row in selections.items():
            when = datetime.fromisoformat(row['betFeedTimestamp'])
            if when.utcoffset() is None or when > captured or row['oddsDecimal'] <= 1:
                raise ValueError('inadmissible individual feed clock or price')
            odds[outcome] = dict(oddsDecimal=row['oddsDecimal'], feed_time_raw=row['betFeedTimestamp'],
                                 feed_time_beijing=when.astimezone(BEIJING).isoformat(),
                                 age_seconds=round((captured-when).total_seconds(), 6))
        complete.append(dict(bookmaker=books[code]['bookmakerName'], bookmaker_code=code,
                             bookmaker_type=books[code]['bookmakerType'], outcomes=odds))
    return complete


def oddschecker(probe, fixture):
    metadata = json.loads((probe/'request-manifest.json').read_bytes())
    url = 'https://www.oddschecker.com/football/europa-league/sunderland-v-bialystok/winner'
    response, = (item for item in metadata if item['url'] == url and item['http_status'] == 200)
    body = retained(probe/response['raw_file'], response['response_sha256']).decode('utf-8')
    states = [json.loads(match.group(1)) for match in BLOCK.finditer(body)]
    identity, = (part for part in states if part.get('subeventName') == 'Sunderland vs Bialystok'
                 and part.get('subeventStartTime'))
    expected = datetime.fromisoformat(fixture['fixture']['kickoff_at'])
    observed = datetime.fromisoformat(response['received_at_utc'])
    if (identity['eventName'] != 'Europa League Matches' or 'https://www.oddschecker.com/' + identity['subeventUrl'] != url
            or datetime.fromisoformat(identity['subeventStartTime']) != expected or observed >= expected
            or fixture['names'] != ['Sunderland', 'Jagiellonia Bialystok']):
        raise ValueError('Oddschecker page differs from the signed ESPN fixture')
    state, = (part for part in states if part.get('bestOdds', {}).get('odds'))
    book_markets = state['bestOdds']['markets']['entities'].values()
    supported = {item['marketTypeName']: item for item in book_markets if item['marketTypeName'] in (
        'Win Market', 'Total Goals Over/Under', 'Asian Total')}
    if len({item['ocMarketSiblingId'] for item in supported.values()}) != 1:
        raise ValueError('listed markets refer to multiple events')
    win = supported['Win Market']
    quotes = winner_quotes(state['bestOdds'], win['ocMarketId'], observed)
    fresh = [book['bookmaker'] for book in quotes if book['bookmaker_type'] == 'traditional'
             and all(r['age_seconds'] <= 3600 for r in book['outcomes'].values())]
    totals = {}
    for label in ('Total Goals Over/Under', 'Asian Total'):
        market = supported[label]
        bets = [row for row in state['bestOdds']['bets']['entities'].values() if row['marketId'] == market['ocMarketId']]
        totals[label] = dict(market_id=market['ocMarketId'], price_rows_loaded=len(bets))
    browser_bytes = (probe/'browser-ui-validation.json').read_bytes()
    browser = json.loads(browser_bytes)
    browser_error, = set(re.findall(r'net::ERR_[A-Z_]+', browser['stopped_reason']))
    frozen = json.loads((ARCHIVE/'publication/56d1e48eafbc04d2-v000001.json').read_bytes())
    if datetime.fromisoformat(frozen['recorded_at']) >= observed:
        raise ValueError('this source probe must remain an observation after the registered display freeze')
    return dict(match_id=MATCH, kickoff=expected.astimezone(BEIJING).isoformat(), url=url,
                status=response['http_status'], observed_at=response['received_at_beijing'],
                body_sha256=response['response_sha256'], response_bytes=response['response_bytes'],
                display_freeze_id=frozen['freeze_id'], display_frozen_at=frozen['recorded_at'],
                page_last_updated=datetime.fromtimestamp(state['lastUpdated']/1000, timezone.utc).astimezone(BEIJING).isoformat(),
                feed_time_field='betFeedTimestamp', provider_time_semantics='not independently confirmed',
                match_winner=dict(catalog_market_id=win['ocMarketId'], complete_active_1x2=len(quotes),
                                  traditional_books=sum(r['bookmaker_type'] == 'traditional' for r in quotes),
                                  traditional_books_all_fields_within_one_hour=fresh, quotes=quotes),
                totals=totals, normal_browser=dict({key: browser[key] for key in (
                    'started_beijing', 'finished_beijing', 'page_open_count', 'click_count')},
                    error=browser_error, evidence_sha256=sha256(browser_bytes).hexdigest()))


def run(root):
    card = json.loads((ARCHIVE/'publication/scorecard.json').read_bytes())
    fixture, = (row for row in card['uel']['rows'] if row['fixture']['match_id'] == MATCH)
    betexplorer = root/'betexplorer-nov26'
    details = json.loads((betexplorer/'competition.http.json').read_bytes())
    retained(betexplorer/'competition.html', details['sha256'])
    check = {key: details[key] for key in ('requested_url', 'final_url', 'http_status', 'sha256', 'bytes')}
    check['received_at'] = datetime.fromisoformat(details['response_received_at_utc']).astimezone(BEIJING).isoformat()
    return dict(evidence_scope='Retained public website source probes', betexplorer=check,
                oddschecker=oddschecker(root/'oddschecker-nov26', fixture))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe-root', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.probe_root), ensure_ascii=False, indent=2, allow_nan=False))
