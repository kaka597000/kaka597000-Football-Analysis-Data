"""Audit observed DraftKings prices and their score-only reference on the original slate."""

from html import unescape
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from research.analysis_freeze import aware
from research_program import all_scope_model as model
from research_program import europe_score_dispersion as archives
from research_program.display_window_review import _decimal_from_american, _raw_market_clock

import prepare
import result_intake


HERE = prepare.HERE
BOOK = 'DraftKings'
OPENING = 'espn:401915816'
SIDES = {'moneyline': ('home', 'draw', 'away'), 'total': ('over', 'under')}


def capture(source_url, observed, sha256):
    return dict(url=source_url, received=aware(observed).astimezone(prepare.BEIJING).isoformat(), sha256=sha256)


def selected_price(line, prices):
    total = dict(line=line, over=prices['total']['over'], under=prices['total']['under'])
    return dict(h2h=prices['moneyline'], total=total)


def extract(odds):
    aligned = [value for value in (odds or ()) if value and (value.get('provider') or {}).get('name') == BOOK]
    if not aligned:
        return None
    book, = aligned
    rows = {market: {side: (((book.get(market) or {}).get(side) or {}).get('close') or {}) for side in sides}
            for market, sides in SIDES.items()}
    values = {market: {} for market in SIDES}
    for market, sides in rows.items():
        for side, quote in sides.items():
            raw = quote.get('odds')
            value = _decimal_from_american(int(raw)) if str(raw).lstrip('+-').isdigit() else None
            if value is None:
                return None
            values[market][side] = round(value, 6)
    line = model.actual_line({'total': {'line': book.get('overUnder')}})
    if line is None or any(float(rows['total'][side]['line'][1:]) != line for side in SIDES['total']):
        raise ValueError('total quotes must be for the same stated goal line')
    times = dict(book=_raw_market_clock(book))
    for market, sides in rows.items():
        times[market] = dict(market=_raw_market_clock(book[market]),
                             options={side: _raw_market_clock(quote) for side, quote in sides.items()})
    return dict(prices=selected_price(line, values), time_fields=times, provider=BOOK, snapshot_label='close')


def reference(price):
    total = price['total']
    home_draw_away = tuple(price['h2h'][side] for side in SIDES['moneyline'])
    over_under = tuple(total[side] for side in SIDES['total'])
    return model.pick(model._full_market(home_draw_away, total['line'], over_under), total['line'])


def original_price(row, root):
    mid = row['fixture']['match_id']
    signed, ref, _ = prepare.original(root / 'issued', mid)
    if ref != row['odds_source_first'] or signed['fixture']['cutoff_at'] != row['source_odds_cutoff_at']:
        raise ValueError('original price reference differs: ' + mid)
    payload = signed['payload']
    evidence = payload['market_evidence']
    if not row['market'].get('primary'):
        return None
    h2h, total = evidence['h2h'], evidence['total']
    keys = ('bookmaker', 'source_url', 'source_sha256', 'observed_at', 'snapshot_label')
    if (any(h2h.get(key) != total.get(key) for key in keys) or h2h['bookmaker'] != BOOK
            or aware(h2h['observed_at']) > aware(row['source_odds_cutoff_at'])
            or reference(payload['prices']) != row['market']):
        raise ValueError('signed same-cutoff market prices differ: ' + mid)
    return dict(prices=payload['prices'], provider=BOOK, snapshot_label=h2h['snapshot_label'],
                observed=capture(h2h['source_url'], h2h['observed_at'], h2h['source_sha256']),
                quoted_at=dict(h2h=h2h['quoted_at'], total=total['quoted_at']), forecast=row['market'], freeze=ref)


def summarize(rows):
    paired = [row['difference'] for row in rows.values() if row['difference'] is not None]
    same_line = [row for row in paired if row['same_line']]
    return dict(registered=len(rows), compared=len(paired), same_line=len(same_line),
                line_changed=len(paired) - len(same_line),
                same_line_total_prices_changed=sum(row['total_prices_changed'] for row in same_line),
                moneyline_prices_changed=sum(row['moneyline_prices_changed'] for row in paired),
                score_first_changed=sum(row['first_changed'] for row in paired),
                score_three_members_changed=sum(row['three_members_changed'] for row in paired),
                same_line_total_side_changed=sum(row['total_side_changed'] for row in same_line))


def difference(previous, current):
    first, later = previous['prices'], current['prices']
    a, b = previous['forecast'], current['forecast']
    return dict(same_line=first['total']['line'] == later['total']['line'],
                total_prices_changed=first['total'] != later['total'], moneyline_prices_changed=first['h2h'] != later['h2h'],
                first_changed=a['primary'] != b['primary'], three_members_changed=set(a['top3']) != set(b['top3']),
                total_side_changed=a['total_side'] != b['total_side'])


def opening_summary(fixture, row):
    folder = HERE / 'prematch/venue-opening'
    meta = prepare.read(folder / 'captures.json')['espn']
    received = aware(meta['captured_at'])
    if (meta['http_status'] != 200 or result_intake.endpoint(meta['url']) != ('espn', fixture['cohort'], OPENING)
            or not aware(row['scoreboard']['observed']['received']) < received < aware(fixture['kickoff_at'])):
        raise ValueError('opening summary is outside the identified pregame timeline')
    body = json.loads(result_intake.raw_result(folder, meta['path'], meta['sha256']))
    status, _ = result_intake.espn_score(body, fixture)
    late = extract(body['pickcenter'])
    if status != 'STATUS_SCHEDULED' or late is None:
        raise ValueError('the last opening-game summary does not supply named pregame prices')
    late['observed'] = capture(meta['url'], meta['captured_at'], meta['sha256'])
    late['forecast'] = reference(late['prices'])
    return dict(match_id=OPENING, row=row, last_summary=late,
                from_original_to_last=difference(row['original'], late))


def public_checks(opening):
    folder = HERE / 'market-sensitivity/public-probes'
    metadata = prepare.read(folder / 'captures.json')
    endpoints = {'https://www.aiscore.com/': 200, 'https://www.nowgoal.com/': 503,
                 'https://www.aiscore.com/today-matches/football': 200}
    if len(metadata) != len(endpoints) or {item['url']: item['http_status'] for item in metadata} != endpoints:
        raise ValueError('public source attempts differ from the three retained requests')
    bodies = {}
    for meta in metadata:
        data = result_intake.raw_result(folder, meta['path'], meta['sha256'])
        if (len(data) != meta['bytes'] or meta['url'] != meta['final_url']
                or not aware(meta['requested_at']) <= aware(meta['captured_at']) < aware(opening['kickoff_at'])):
            raise ValueError('public source probe chronology or endpoint differs')
        bodies[meta['url']] = unescape(data.decode()).casefold()
    index = bodies['https://www.aiscore.com/']
    day = bodies['https://www.aiscore.com/today-matches/football']
    if ('/today-matches/football' not in index or 'kairat almaty u19' not in day
            or any(name in day for name in ('mjällby', 'mjallby'))):
        raise ValueError('retained AiScore pages do not support the recorded fixture coverage')
    return dict(captures=metadata, aiscore_youth_fixture_present=True, aiscore_registered_senior_fixture_present=False,
                qualified_90_minute_market_pairs=0)


def audit():
    scopes = prepare.register(False)
    original = prepare.scores(scopes)
    captures = prepare.read(HERE / 'calendar/captures.json')
    rounds = {}
    with TemporaryDirectory(prefix='europe-observed-markets-') as directory:
        path, digest = prepare.ARCHIVES['r5']
        root = Path(directory)
        archives.unpack(HERE.parents[1], dict(path=path, sha256=digest), root)
        for short, group in original.items():
            meta = captures[short][prepare.SLATES[0]]
            rows = {}
            for row in group['rows']:
                mid = row['fixture']['match_id']
                signed = original_price(row, root)
                recent = extract(scopes[short]['today'][mid]['markets'])
                if recent is not None:
                    recent['observed'] = capture(meta['url'], meta['observed_at'], meta['source_sha256'])
                    recent['forecast'] = reference(recent['prices'])
                if signed is not None and recent is not None and not (
                        aware(row['source_odds_cutoff_at']) < aware(recent['observed']['received']) < aware(row['fixture']['kickoff_at'])):
                    raise ValueError('comparison scoreboard must be after the original price cutoff and before kickoff')
                rows[mid] = dict(teams=row['names_zh'], original=signed, scoreboard=recent,
                                 difference=difference(signed, recent) if signed and recent else None)
            rounds[short] = rows
    first = scopes['uecl']['today'][OPENING]['fixture']
    return dict(scope='Observed-price sensitivity; original R13 market cutoff and first freeze govern settlement',
                summary={short: summarize(rows) for short, rows in rounds.items()}, matches=rounds,
                opening=opening_summary(first, rounds['uecl'][OPENING]), public_checks=public_checks(first))


if __name__ == '__main__':
    print(json.dumps(audit(), ensure_ascii=False, indent=2, allow_nan=False))
