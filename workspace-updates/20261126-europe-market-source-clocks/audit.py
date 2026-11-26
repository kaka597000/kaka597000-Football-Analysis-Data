"""Compare retained European market responses and verify candidate source clocks."""

from collections import Counter
import gzip
from hashlib import sha256
import json
from pathlib import Path
import tarfile
from urllib.parse import urlsplit

from research.analysis_freeze import aware
from research_program.display_window_review import _decimal_from_american, _raw_market_clock


HERE = Path(__file__).resolve().parent
WINDOWS = HERE.parent / '20261126-europe-first-display'
ORIGINAL = HERE.parent / '20261123-all-scope-kpi/forward-observations.tar.gz'
ORIGINAL_SHA = '1744c4f54f67b222ac7296675f48c6954dc98b64edc48aa98244b1060e5ecf59'
COMPETITIONS = {'uecl': ('uefa.europa.conf', 14546), 'uel': ('uefa.europa', 14540)}
CLOCK_NAMES = {'quotetime', 'quotetimestamp', 'quotedat', 'lastupdate', 'lastupdated', 'updatedat', 'updatetime',
               'timestamp', 'asof', 'markettime', 'marketupdatedat', 'oddstimestamp'}


def read(path):
    return json.loads(path.read_bytes())


def checked(raw, digest):
    if sha256(raw).hexdigest() != digest:
        raise ValueError('retained source checksum mismatch')
    return json.loads(raw)


def market_dk(objects):
    source = [v for v in objects if isinstance(v, dict) and (v.get('provider') or {}).get('id') == '100']
    if not source:
        return {'book': None, 'quote_at': None, 'h2h': None, 'total': None}
    entry, = source
    if entry['provider']['name'] != 'DraftKings':
        raise ValueError('market identifier is not its original named book')

    def price(snapshot):
        value = snapshot.get('odds')
        try:
            quoted = _decimal_from_american(int(value))
        except (TypeError, ValueError):
            return None
        return round(quoted, 6) if quoted is not None else None

    h2h = {side: price(entry.get('moneyline', {}).get(side, {}).get('close') or {})
           for side in ('home', 'draw', 'away')}
    total = entry.get('total') or {}
    over = total.get('over', {}).get('close') or {}
    under = total.get('under', {}).get('close') or {}
    line = entry.get('overUnder')
    prices = {side: price(row) for side, row in [('over', over), ('under', under)]}
    two_sided = all(v is not None for v in prices.values())
    if two_sided:
        parsed_lines = [float(row['line'][1:]) for row in (over, under)]
        if parsed_lines != [line, line] or not 0 <= line <= 20 or (line * 4) % 1:
            raise ValueError('unmatched ESPN full-game total lines')
    return dict(book='DraftKings', quote_at=_raw_market_clock(entry), h2h=h2h if all(h2h.values()) else None,
                total=dict(line=line, **prices) if two_sided else None)


def game_for(event, fixture, season, summary=False):
    game, = event['competitions']
    players = {t['homeAway']: 'espn:' + str(t['team']['id']) for t in game['competitors']}
    if ('espn:' + str(event['id']) != fixture['match_id'] or str(game['id']) != str(event['id'])
            or (players['home'], players['away']) != (fixture['home'], fixture['away'])
            or aware(game['date']) != aware(fixture['kickoff_at']) or (not summary and not game['timeValid'])
            or event['season']['type'] != season or event['season']['year'] != 2026
            or (summary and event['league']['slug'] != fixture['cohort'])
            or game['status']['type']['state'] != 'pre'):
        raise ValueError('price source event or ordered teams differ from the registered fixture')
    return game


def board(raw, digest, code):
    document = checked(raw, digest)
    if [item['slug'] for item in document['leagues']] != [code]:
        raise ValueError('different competition scoreboard')
    events = {'espn:' + str(r['id']): r for r in document['events']}
    if len(events) != 18 or len(document['events']) != 18:
        raise ValueError('incomplete registered round')
    return events


def difference(first, second):
    if not first or not second:
        return 'missing'
    if first['line'] != second['line']:
        return 'different_lines'
    return 'same_line_and_prices' if first == second else 'same_line_different_prices'


def h2h_difference(first, second):
    if not first or not second:
        return 'missing'
    return 'same_prices' if first == second else 'different_prices'


def audit_round(short, code, season, original_archive):
    original_meta = next(r for r in json.load(original_archive.extractfile('forward/queries.json'))
                         if (r['competition'], r['query_date']) == (code, '20261126'))
    early = board(original_archive.extractfile('forward/' + original_meta['path']).read(), original_meta['sha256'], code)
    labels = read(WINDOWS/'calendar/captures.json')[short]

    def recorded_board(day):
        return board(gzip.decompress((WINDOWS/'calendar'/f'{short}-{day}.json.gz').read_bytes()),
                     labels[day]['source_sha256'], code)

    latest = recorded_board('2026-11-26')
    following = recorded_board('2026-12-10')
    scorecard = read(WINDOWS/'publication/scorecard.json')[short]['rows']
    manifests = {r['match_id']: r for r in read(WINDOWS/'prematch'/short/'captures.json')}
    if set(early) != set(latest) or set(latest) != set(manifests) or set(latest) != {r['fixture']['match_id'] for r in scorecard}:
        raise ValueError('price sources must retain the full round')
    rows = {}
    for retained in scorecard:
        f = retained['fixture']
        mid = f['match_id']
        before = market_dk(game_for(early[mid], f, season)['odds'])
        current = market_dk(game_for(latest[mid], f, season)['odds'])
        ref = manifests[mid]
        raw = gzip.decompress((WINDOWS/'prematch'/short/ref['file']).read_bytes())
        summary = checked(raw, ref['source_sha256'])
        game_for(summary['header'], f, season, summary=True)
        detail = market_dk(summary.get('odds', []))
        earlier_total = (before.get('total') or {}).get('line')
        if earlier_total != retained['forecast']['total_line']:
            raise ValueError('original selected line differs from source snapshot: ' + mid)
        rows[mid] = dict(early=before, scoreboard=current, detail=detail,
                         early_to_board_total=difference(before['total'], current['total']),
                         board_to_detail_total=difference(current['total'], detail['total']),
                         early_to_board_h2h=h2h_difference(before['h2h'], current['h2h']),
                         board_to_detail_h2h=h2h_difference(current['h2h'], detail['h2h']),
                         detail_observed_at=ref['observed_at'], detail_sha256=ref['source_sha256'])

    coverage = {}
    for key in ('early', 'scoreboard', 'detail'):
        values = [r[key] for r in rows.values()]
        coverage[key] = dict(full_book=sum(bool(r['h2h'] and r['total']) for r in values),
                             book_clock=sum(bool(r['quote_at']) and not r['quote_at'].startswith(
                                 ('INVALID_TIMEZONE:', 'CONFLICTING_SOURCE_CLOCKS')) for r in values))
    return dict(fixtures=len(rows), original_scoreboard_sha256=original_meta['sha256'],
                original_observed_at=original_meta['query_observed_at'], latest_scoreboard=labels['2026-11-26'],
                coverage=coverage, transitions={key: dict(Counter(r[key] for r in rows.values())) for key in
                                                ('early_to_board_total', 'board_to_detail_total', 'early_to_board_h2h',
                                                 'board_to_detail_h2h')},
                next_round=dict(registered=len(following),
                                any_named_dk=sum(bool(market_dk(r['competitions'][0].get('odds', []))['book'])
                                                 for r in following.values())), per_fixture=rows)


def review():
    if sha256(ORIGINAL.read_bytes()).hexdigest() != ORIGINAL_SHA:
        raise ValueError('original observation archive differs')
    with tarfile.open(ORIGINAL) as archive:
        rounds = {short: audit_round(short, code, season, archive)
                  for short, (code, season) in COMPETITIONS.items()}
    return dict(rounds=rounds, espn_core=core_probe())


def clock_paths(value, path=''):
    if isinstance(value, dict):
        for key, entry in value.items():
            name = path + '.' + key if path else key
            if ''.join(ch for ch in key.casefold() if ch.isalnum()) in CLOCK_NAMES:
                yield name
            yield from clock_paths(entry, name)
    elif isinstance(value, list):
        for index, entry in enumerate(value):
            yield from clock_paths(entry, f'{path}[{index}]')


def core_probe():
    directory = HERE/'sources'
    metadata = read(directory/'espn-core.json')
    expected = {('401915506', ''), ('401915506', '/100'), ('401915513', ''), ('401915494', '')}
    captured = []
    for item in metadata:
        mid = item['event_id']
        url = urlsplit(item['url'])
        prefix = f'/v2/sports/soccer/leagues/uefa.europa/events/{mid}/competitions/{mid}/odds'
        base = url.path.removeprefix(prefix)
        if ((url.scheme, url.hostname) != ('https', 'sports.core.api.espn.com')
                or item['competition_id'] != mid or (mid, base) not in expected or item['http_status'] != 200
                or aware(item['request_start_utc']) > aware(item['received_at_utc'])):
            raise ValueError('Core market sample metadata differs')
        expected.remove((mid, base))
        raw = gzip.decompress((directory/item['raw_file']).read_bytes())
        payload = checked(raw, item['response_sha256'])
        quotes = [payload] if base == '/100' else payload['items']
        if not base and len(quotes) != payload['count']:
            raise ValueError('Core sample collection differs')
        for quote in quotes:
            if not urlsplit(quote['$ref']).path.startswith(prefix + '/'):
                raise ValueError('Core odds item does not bind to its source fixture')
        captured.append(dict(event_id=mid, detail=bool(base), captured_at=item['received_at_utc'],
                             providers=[q['provider']['name'] for q in quotes],
                             provider_timestamp_like_paths=list(clock_paths(quotes)),
                             source_sha256=item['response_sha256']))
    if expected:
        raise ValueError('Core source probe is incomplete')
    return captured


if __name__ == '__main__':
    print(json.dumps(review(), ensure_ascii=False, allow_nan=False, indent=2))
