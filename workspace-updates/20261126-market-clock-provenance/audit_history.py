"""Check the raw source and timing of the two archived November 23 quote cohorts."""

import argparse
from collections import Counter
from datetime import datetime
import gzip
from hashlib import sha256
import json
from pathlib import Path
import tarfile
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent.parent
MAIN = '20261123-kpi-optimization/source-assets.tar.gz'
BRAZIL = '20261115-remaining-nations-brazil/remaining-evidence.tar.gz'
ARCHIVES = {
    MAIN: '7c106ee66a816da84dbbfbf254633b55b7c25e610e7d0f31bf168d68f61d9659',
    BRAZIL: '3f842a58a73eb453d354e8a770c934378785714189c2e73bf190f77596534e49',
}
COHORTS = {'timestamp-certified': 80, 'extension-timestamp-certified': 6}
BEIJING = ZoneInfo('Asia/Shanghai')


def check(condition, message):
    if not condition:
        raise ValueError(message)


def timestamp(value):
    result = datetime.fromisoformat(value)
    check(result.utcoffset() is not None, 'quote evidence requires an explicit timezone')
    return result


def member(bundle, path):
    with bundle.extractfile(path) as file:
        return file.read()


def market_event(board, event_id, book_name):
    event, = (row for row in board if row['id'] == event_id)
    book, = (row for row in event['bookmakers'] if row['key'].casefold() == book_name)
    one_x_two, = (row for row in book['markets'] if row['key'] == 'h2h')
    totals, = (row for row in book['markets'] if row['key'] == 'totals')
    outcomes = {row['name']: row['price'] for row in one_x_two['outcomes']}
    check(len(one_x_two['outcomes']) == len(outcomes) == 3, 'complete raw 1X2 required')
    h2h = dict(home=outcomes[event['home_team']], draw=outcomes['Draw'], away=outcomes[event['away_team']])
    sides = {row['name']: row for row in totals['outcomes']}
    check(len(totals['outcomes']) == 2 and sides.keys() == {'Over', 'Under'}
          and sides['Over']['point'] == sides['Under']['point'], 'same-line raw total sides required')
    total = dict(line=sides['Over']['point'], over=sides['Over']['price'], under=sides['Under']['price'])
    return event, h2h, total, timestamp(one_x_two['last_update']), timestamp(totals['last_update'])


def brazil_market(bundle):
    path, = (name for name in bundle.getnames() if name.endswith('/validated-market-brazil/odds.json'))
    base = path.rsplit('/', 1)[0]
    raw = member(bundle, path)
    board = json.loads(raw)
    meta = json.loads(member(bundle, base + '/source-metadata.json'))
    channel = json.loads(member(bundle, base + '/market-channel.json'))
    identity = member(bundle, base + '/identity.json')
    check(sha256(raw).hexdigest() == meta['odds']['sha256'] and meta['odds']['http_status'] == 200
          and sha256(identity).hexdigest() == meta['identity']['sha256']
          and meta['tls_verification_disabled'] is False
          and channel['quote_time_inferred_from_capture'] is False, 'older Brazil source proof differs')
    proofs = {row['match_id']: row for row in channel['identity_mappings']}
    return board, meta['odds'], proofs


def record(row, freeze, market, board, source, event_id, digest, provenance):
    info = row.get('freeze_reference', {})
    market_quote = freeze['fixture']['total_quote']
    book = market['bookmaker'].casefold()
    fixture = freeze['fixture']
    check(freeze['match_id'] == row['match_id'] == fixture['match_id']
          and freeze['freeze_id'] == row.get('freeze_id', info.get('freeze_id'))
          and freeze['record_sha256'] == row.get('freeze_record_sha256', info.get('sha256'))
          and freeze['evaluation_slot'] == 'FIRST_PREMATCH'
          and all(fixture[field] == row[field] for field in ('home', 'away'))
          and timestamp(fixture['kickoff_at']) == timestamp(row['kickoff_at'])
          and timestamp(fixture['cutoff_at']) == timestamp(row['cutoff_at']),
          'original freeze identity differs')
    event, raw_h2h, raw_total, h2h_time, total_time = market_event(board, event_id, book)
    quote_at = timestamp(market_quote['quoted_at'])
    captured_at = timestamp(market_quote['query_time'])
    cutoff = timestamp(row['cutoff_at'])
    kickoff = timestamp(row['kickoff_at'])
    raw_host = urlsplit(source).hostname
    check(h2h_time == timestamp(market['h2h_quoted_at']) and total_time == timestamp(market['total_quoted_at'])
          and quote_at == total_time and raw_h2h == market['h2h'] and raw_total == market['total']
          and (market_quote['bookmaker'].casefold(), market_quote['source_sha256'], market_quote['source_url'])
          == (book, digest, source)
          and raw_total == dict(line=market_quote['line'], over=market_quote['over_odds'], under=market_quote['under_odds'])
          and timestamp(event['commence_time']) == kickoff
          and max(h2h_time, total_time) <= captured_at <= cutoff < kickoff,
          'raw prices or individual market clocks differ')
    return dict(match_id=row['match_id'], cohort=row['cohort'], bookmaker=book, source_host=raw_host,
                source_archive=provenance, source_sha256=digest, provider_match_id=event_id,
                freeze_id=freeze['freeze_id'], raw_kickoff_offset_seconds=(timestamp(event['commence_time'])-kickoff).total_seconds(),
                h2h_quoted_at=h2h_time.astimezone(BEIJING).isoformat(), total_quoted_at=total_time.astimezone(BEIJING).isoformat(),
                query_at=captured_at.astimezone(BEIJING).isoformat(), cutoff_at=cutoff.astimezone(BEIJING).isoformat(),
                quote_to_query_seconds=round((captured_at-max(h2h_time, total_time)).total_seconds(), 6),
                oldest_quote_to_cutoff_seconds=round((cutoff-min(h2h_time, total_time)).total_seconds(), 6))


def replay(data):
    for path, digest in ARCHIVES.items():
        check(sha256((data/path).read_bytes()).hexdigest() == digest, 'historical archive identity differs: ' + path)
    summary, rows = {}, []
    with tarfile.open(data/MAIN) as main, tarfile.open(data/BRAZIL) as brazil:
        manifest = json.loads(member(main, 'ASSET-MANIFEST.json'))
        captures = {}
        for digest, evidence in manifest['wcpp_pregame_proofs'].items():
            body = member(main, evidence['archive_path'])
            check(sha256(body).hexdigest() == digest, 'raw quote response checksum differs')
            captures[digest] = (json.loads(body), evidence['source_url'])
        old_board, old_meta, old_proofs = brazil_market(brazil)
        for name, expected_count in COHORTS.items():
            captured = gzip.decompress(member(main, f'normalized/{name}.jsonl.gz'))
            records = []
            group = [json.loads(raw) for raw in captured.splitlines()]
            check(len(group) == len({r['match_id'] for r in group}) == expected_count, 'original cohort changed')
            for row in group:
                market, mid = row['market'], row['match_id']
                original = manifest['wcpp_frozen_records'].get(mid)
                if original:
                    freeze = json.loads(member(main, original))
                    digest, event_id = market['market_source_sha256'], market['provider_match_id']
                    board, url = captures[digest]
                    check(url == market['market_source_url'] and any(
                        (snap.get('provider_match_id'), snap.get('source_sha256')) == (event_id, digest)
                        for snap in freeze['fixture']['market_snapshots']), 'provider event is not bound to the original freeze')
                    provenance = MAIN
                else:
                    slot = row['freeze_id'].split('-v')[0]
                    path, = (name for name in brazil.getnames()
                             if name.startswith('WCPP/forecasts/issued-analyses/'+slot) and name.endswith('/000001.json'))
                    freeze = json.loads(member(brazil, path))
                    binding = old_proofs[mid]
                    check((binding['home_id'], binding['away_id']) == (row['home'], row['away'])
                          and timestamp(binding['kickoff_at']) == timestamp(row['kickoff_at']),
                          'older provider identity differs')
                    board, url, digest = old_board, old_meta['url'], old_meta['sha256']
                    event_id, provenance = binding['provider_match_id'], BRAZIL
                records.append(record(row, freeze, market, board, url, event_id, digest, provenance))
            summary[name] = dict(fixtures=len(records), paired_price_clock_records=len(records),
                                 sources=dict(Counter(r['source_host'] for r in records)),
                                 books=dict(Counter(r['bookmaker'] for r in records)),
                                 archived_quote_responses=len({r['source_sha256'] for r in records}),
                                 recovered_from_brazil_archive=sum(r['source_archive'] == BRAZIL for r in records),
                                 max_absolute_kickoff_offset_seconds=max(abs(r['raw_kickoff_offset_seconds']) for r in records),
                                 quote_to_query_seconds=[min(r['quote_to_query_seconds'] for r in records),
                                                         max(r['quote_to_query_seconds'] for r in records)],
                                 within_one_hour_at_cutoff=sum(r['oldest_quote_to_cutoff_seconds'] <= 3600 for r in records))
            rows.extend(dict(row, archive_cohort=name) for row in records)
    check(len(rows) == len({row['match_id'] for row in rows}), 'duplicate fixture across original cohorts')
    return dict(evidence_scope='Offline historical price and market timestamp provenance', archives=ARCHIVES,
                cohorts=summary, records=rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=ROOT)
    args = parser.parse_args()
    print(json.dumps(replay(args.data), ensure_ascii=False, indent=2, allow_nan=False))
