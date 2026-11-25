"""Read the frozen early market originals and reproduce their nine-game denominators offline."""
import csv
from datetime import datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
import tarfile

HERE = Path(__file__).resolve().parent
BUNDLE_SHA = '70f2c00ae86331b66981bd8a2e65c75adcf4099c5ad4afed0e013e7ce5b4270d'
NORMALIZED = ('fixtures.json', 'quotes.csv', 'same-book.csv', 'fixture-coverage.csv', 'readback.json')


def check(ok, why):
    if not ok:
        raise ValueError(why)


def csv_rows(path):
    with path.open(encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream))


def canonical(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def verify():
    name = 'bundesliga-nine-early-' + BUNDLE_SHA[:16] + '.tar.gz'
    path = HERE / name
    check(sha256(path.read_bytes()).hexdigest() == BUNDLE_SHA, 'early source archive')
    sums = (HERE / 'SHA256SUMS').read_text().splitlines()
    check(sums == [sha256((HERE / n).read_bytes()).hexdigest() + '  ' + n for n in sorted((name, *NORMALIZED))],
          'normalized file checksums')
    with tarfile.open(path) as tar:
        def raw(member):
            return tar.extractfile(member).read()
        for file in NORMALIZED:
            check((HERE / file).read_bytes() == raw('derived/' + file), file)
        bindings = {'registration/plan.json': HERE.parent/'registration/plan.json',
                    'registration/quote-times.csv': HERE.parent/'market-checkpoints/quote-times.csv',
                    'registration/ger.1.csv': HERE.parents[1]/'data/leagues/ger.1.csv'}
        plan = json.loads(bindings['registration/plan.json'].read_bytes())
        bindings['registration/' + plan['file']] = HERE.parent/'registration'/plan['file']
        check(all(file.read_bytes() == raw(member) for member, file in bindings.items()), 'PR #57 original bindings')
        reg = json.loads(bindings['registration/' + plan['file']].read_bytes())
        sig = reg.pop('record_sha256')
        check(sig == plan['sha256'] == canonical(reg) and reg['revision'] == 1 and reg['previous_sha256'] is None,
              'registration SHA')
        fixtures = json.loads((HERE/'fixtures.json').read_bytes())
        ids = reg['payload']['identity']['slates']['nov27_dec04']
        check(ids == [f['match_id'] for f in fixtures] and len(set(ids)) == 9, 'nine registered slots')
        quotes = csv_rows(HERE/'quotes.csv')
        exported = {(r['match_id'], int(r['row_index'])): r for r in quotes}
        coverage = {r['match_id']: r for r in csv_rows(HERE/'fixture-coverage.csv')}
        expected_pairs, source_keys = {}, set()
        opened = suspended = 0
        for f in fixtures:
            mid = f['match_id']
            signed = reg['payload']['fixtures'][mid]
            kickoff = datetime.fromisoformat(signed['kickoff_at'])
            ie = f['infer_event_id']
            label = 'raw/infersports/' + ie + '-odds'
            data, meta = raw(label + '.json'), json.loads(raw(label + '.meta.json'))
            source = json.loads(data)
            receipt = datetime.fromisoformat(meta['response_received_utc'])
            daily = json.loads(raw(f['source_calendar_path']))
            event, = [e for e in daily['data'] if e['id'] == ie]
            check(f['registration_sha256'] == sig and signed['cohort'] == f['competition'] == 'ger.1'
                  and datetime.fromisoformat(event['scheduled_at']) == kickoff == datetime.fromisoformat(f['kickoff_utc'])
                  and event['league'] == f['infer_league'] == {'id': 'lg_PGYWSDEA', 'name': 'GER'} and event['status'] == 'scheduled'
                  and all(signed[s] == 'espn:' + f['sides'][s]['espn_id'] and
                          event[s+'_team'] == {'id': f['sides'][s]['infer_id'], 'name': f['sides'][s]['infer_name']}
                          for s in ('home', 'away')), mid + ' source identity')
            check(coverage[mid]['control'] == 'early_prospective' and source['event_id'] == ie and source['stale'] is False
                  and meta['http_status'] == 200 and meta['sha256'] == sha256(data).hexdigest() and
                  meta['url'] == 'https://api.infersports.dev/v1/events/' + ie + '/odds?period=full_time&format=decimal'
                  and datetime.fromisoformat(meta['request_started_utc']) <= receipt < kickoff - timedelta(hours=24),
                  mid + ' response and cutoff')
            money, totals = {}, []
            for i, q in enumerate(source['odds']):
                r = exported[mid, i]
                age = (receipt - datetime.fromisoformat(q['as_of'])).total_seconds()
                source_keys.add((mid, i))
                check(r['quote_as_of_utc'] == q['as_of'] and r['raw_sha256'] == meta['sha256'] and r['row_sha256'] == canonical(q)
                      and r['bookmaker'] == q['bookmaker'] and r['market'] == q['market_type'] and r['status'] == q['status']
                      and float(r['quote_age_seconds_at_receipt']) == age and age >= 0 and
                      r['response_received_utc'] == meta['response_received_utc'] and r['response_as_of_utc'] == source['as_of']
                      and (None if r['line'] == '' else float(r['line'])) == q['line'] and
                      json.loads(r['split_components']) == q['handicap_components'] and
                      all(float(r[s+'_price']) == v for s, v in q['prices'].items()), 'actual quote data and source age')
                if q['status'] == 'open':
                    opened += 1
                    check(r['eligible'] == 'True' and all(v > 1 for v in q['prices'].values()), 'complete live row')
                    if q['market_type'] == '1x2':
                        check(q['bookmaker'] not in money and set(q['prices']) == {'home','draw','away'}, 'three-way')
                        money[q['bookmaker']] = (i, q['as_of'], age)
                    if q['market_type'] == 'totals':
                        check(set(q['prices']) == {'over','under'}, 'two-sided total')
                        totals.append((i, q, age))
                else:
                    check(q['status'] == 'suspended' and r['eligible'] == 'False', 'explicit suspended row')
                    suspended += 1
            for j, t, age in totals:
                h = money.get(t['bookmaker'])
                if h:
                    expected_pairs[mid, h[0], j] = (t['bookmaker'], float(t['line']), h[1], t['as_of'], max(h[2], age) <= 3600)
        pair_rows = csv_rows(HERE/'same-book.csv')
        published_pairs = {(r['match_id'], int(r['moneyline_raw_index']), int(r['total_raw_index'])):
                           (r['bookmaker'], float(r['total_line']), r['moneyline_quote_utc'], r['total_quote_utc'],
                            r['both_within_one_hour'] == 'True') for r in pair_rows}
        check(len(exported) == len(quotes) == len(source_keys) and exported.keys() == source_keys and
              len(pair_rows) == len(expected_pairs) and published_pairs == expected_pairs, 'native market denominator')
        fresh = {k[0] for k, p in expected_pairs.items() if p[-1]}
        synced = {k[0] for k, p in expected_pairs.items() if p[-1] and p[2] == p[3]}
        check((len(quotes), opened, suspended, len(expected_pairs), len(fresh), len(synced)) == (352,333,19,144,7,7),
              'frozen coverage')
        print('early_prospective: 9/9 registered, 352 source rows, 333 open, 19 suspended, 144 pairs, 7/9 time-fresh.')


if __name__ == '__main__':
    verify()
