"""Rebuild research inputs from issued Current PMFs and retained FT responses."""
import argparse
import gzip
import hashlib
import io
import json
import math
import tarfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEADLINE = datetime(2026, 11, 18, tzinfo=timezone.utc)


def canon(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()


def sha(b):
    return hashlib.sha256(b).hexdigest()


def time(stamp):
    d = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
    if d.utcoffset() is None:
        raise ValueError(stamp)
    return d.astimezone(timezone.utc)


def require(cond, msg):
    if not cond:
        raise ValueError(msg)


def verified_pair(freeze_bytes, raw, observed, origin, result_score=None, espn_identity=None):
    freeze = json.loads(freeze_bytes)
    fx, current = freeze['fixture'], freeze['payload']['current_model']
    mid = freeze['match_id']
    require(mid == fx['match_id'] == freeze['payload']['match_id'], mid)
    require(freeze['stage'] == 'prematch' and freeze['evaluation_slot'] == 'FIRST_PREMATCH'
            and freeze['track'] == 'current-test-pair' and freeze['revision'] == 1, mid + ' freeze')
    pmf = current['matrix']
    require(sha(canon({k: v for k, v in freeze.items() if k != 'record_sha256'})) == freeze['record_sha256'], mid + ' record digest')
    require(sha(canon(pmf)) == current['matrix_hash'], mid + ' matrix digest')
    require(all(len(r) == len(pmf) and all(math.isfinite(v) and v >= 0 for v in r) for r in pmf)
            and abs(math.fsum(math.fsum(r) for r in pmf) - 1) < 1e-8, mid + ' PMF')
    head = json.loads(espn_identity if espn_identity is not None else raw)['header']
    comp = head['competitions'][0]
    status = comp['status']['type']
    require(head['id'] == comp['id'] == mid.split(':')[1] and head['league']['slug'] == fx['competition'], mid + ' identity')
    by_side = {t['homeAway']: t for t in comp['competitors']}
    require(all(fx[s] == 'espn:' + str(by_side[s]['team']['id']) for s in ('home', 'away')), mid + ' teams')
    require(fx['neutral'] is comp['neutralSite'] and fx['identity_verified'], mid + ' neutral')
    kickoff = time(fx['kickoff_at'])
    require(time(comp['date']) == kickoff and time(fx['cutoff_at']) <= time(current['generated_at'])
            <= time(freeze['recorded_at']) < kickoff, mid + ' forecast chronology')
    require(kickoff + timedelta(minutes=90) <= time(observed) < DEADLINE, mid + ' result chronology')
    if espn_identity is None:
        require(status['completed'] and status['name'] == 'STATUS_FULL_TIME' and status['shortDetail'] == 'FT', mid + ' nonregulation')
        score = [int(by_side[s]['score']) for s in ('home', 'away')]
    else:
        # Brazil's 19 Oct retained ESPN identity snapshot was still at 71 minutes.
        exact = [m for league in json.loads(raw)['leagues'] if league['ccode'] == 'BRA' and league['primaryId'] == 268
                 for m in league['matches'] if time(m['status']['utcTime']) == kickoff
                 and m['home']['name'] == fx['display_home'] and m['away']['name'] == fx['display_away']]
        require(len(exact) == 1 and fx['cohort'] == 'bra.1' and fx['stage'] == 'regular', mid + ' FotMob event')
        m = exact[0]
        ft = m['status']
        require(ft['finished'] and not ft['awarded'] and not ft['cancelled'] and ft['periodLength'] == 45
                and ft['reason']['shortKey'] == 'fulltime_short', mid + ' FotMob regulation')
        score = [m[side]['score'] for side in ('home', 'away')]
        require(ft['scoreStr'] == f'{score[0]} - {score[1]}', mid + ' FotMob score')
        origin.update(fotmob_match_id=m['id'], identity_raw_sha256=sha(espn_identity),
                      identity_basis='ESPN event and venue; FotMob league, exact kickoff plus both oriented club names')
    require(result_score is None or result_score == score, mid + ' disputed result')
    record = dict(match_id=mid, cohort=fx['cohort'], kickoff_at=fx['kickoff_at'], cutoff_at=fx['cutoff_at'],
                  observed_at=observed, home_goals=score[0], away_goals=score[1], current_matrix=pmf, market=None)
    ledger = dict(match_id=mid, cohort=fx['cohort'], stage=fx['stage'], neutral=fx['neutral'], home=fx['home'],
                  away=fx['away'], freeze_id=freeze['freeze_id'], freeze_record_sha256=freeze['record_sha256'],
                  freeze_file_sha256=sha(freeze_bytes), matrix_sha256=current['matrix_hash'], model_hash=current['model_hash'],
                  version=current['version'], fixture_cutoff_at=fx['cutoff_at'], recorded_at=freeze['recorded_at'],
                  raw_result_sha256=sha(raw), observed_at=observed, **origin)
    return record, ledger


def archive_existing(wcpp, path):
    """Retain original Brazil source inputs absent from the common future bundle."""
    report = 'reports/'
    relpaths = []
    for f in (wcpp / 'forecasts/issued-analyses').glob('*/000001.json'):
        r = json.loads(f.read_bytes())
        if (r['fixture'].get('cohort') == 'bra.1' and r['track'] == 'current-test-pair'
                and r['stage'] == 'prematch' and time(r['recorded_at']) < DEADLINE):
            relpaths.append(f.relative_to(wcpp).as_posix())
    relpaths.extend(report + s for s in (
        'review-kashiwa-20261115-1540/verified-results.json',
        'review-kashiwa-20261115-1540/results/raw/espn-summary-401841311.json',
        'review-kashiwa-20261115-1540/results/raw/espn-summary-401841175.json',
        'review-jingcai-20261017-1400/results/espn-summary-周五011-401841275.meta.json',
        'review-jingcai-20261017-1400/results/espn-summary-周五011-401841275.json',
        'jingcai-20261020-2115/facts-a/evidence_manifest.json',
        'jingcai-20261020-2115/facts-a/raw/fotmob_matches_20261019.json',
        'review-20261020-0832/results/raw-manifest.json',
        'review-20261020-0832/results/raw/espn-summary-401841272-latest.json',
        'jingcai-remaining-20261024-1902/review-25/summary.json',
        'jingcai-remaining-20261024-1902/review-25/周六030.json',
        'jingcai-20261026/review-20261027-0908/summary.json',
        'jingcai-20261026/review-20261027-0908/周一004.json'))
    with path.open('wb') as dest, gzip.GzipFile(fileobj=dest, filename='', mode='wb', mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode='w') as out:
            for name in sorted(relpaths):
                data = (wcpp / name).read_bytes()
                item = tarfile.TarInfo(name)
                item.size = len(data)
                out.addfile(item, io.BytesIO(data))


def paired_markets(data, fixture, fxrow, lg):
    """Check both originally attached prices against archived provider bytes and ESPN mapping."""
    bundle_path = Path('workspace-updates/20261115-remaining-nations-brazil/remaining-evidence.tar.gz')
    prefix = 'recovered-workspace-20261102/WCPP/reports/remaining-nations-brazil-20261115-0240/validated-market-brazil/'
    with tarfile.open(data / bundle_path, 'r:gz') as bundle:
        raw = bundle.extractfile(prefix + 'odds.json').read()
        meta = json.load(bundle.extractfile(prefix + 'source-metadata.json'))['odds']
        channel = json.load(bundle.extractfile(prefix + 'market-channel.json'))
    mid = fxrow['match_id']
    ident = next(x for x in channel['identity_mappings'] if x['match_id'] == mid)
    require(ident['home_id'] == fixture['home'] and ident['away_id'] == fixture['away'], mid + ' quote identity')
    event = next(x for x in json.loads(raw) if x['id'] == ident['provider_match_id'])
    require(time(event['commence_time']) == time(fxrow['kickoff_at']), mid + ' quote kickoff')
    entries = {s['market']: s for s in fixture['market_snapshots']}
    book = entries['1x2']['bookmaker']
    require(book == entries['totals']['bookmaker'] and sha(raw) == meta['sha256'], mid + ' quote evidence')
    bookmaker = next(b for b in event['bookmakers'] if b['key'] == book)
    props = {m['key']: m for m in bookmaker['markets']}
    for key, archived_key in [('h2h', '1x2'), ('totals', 'totals')]:
        archived, original = entries[archived_key], props[key]
        require(archived['match_id'] == mid and archived['source_sha256'] == meta['sha256'], mid + ' quote match')
        require(time(original['last_update']) == time(archived['quoted_at']) <= time(meta['captured_at'])
                == time(archived['query_time']) <= time(fixture['cutoff_at']), mid + ' quote time')
        prices = {v['name']: v['price'] for v in original['outcomes']}
        if key == 'h2h':
            odds = {'home': prices[event['home_team']], 'away': prices[event['away_team']], 'draw': prices['Draw']}
        else:
            odds = {s: prices[s.title()] for s in ['under', 'over']}
            require(all(v['point'] == archived['line'] for v in original['outcomes']), mid + ' line')
        require(archived['decimal_odds'] == odds, mid + ' quote price')
    fxrow['market'] = dict(h2h=entries['1x2']['decimal_odds'],
                          total=dict(line=entries['totals']['line'], **entries['totals']['decimal_odds']),
                          h2h_quoted_at=entries['1x2']['quoted_at'], total_quoted_at=entries['totals']['quoted_at'],
                          quoted_at=max(entries['1x2']['quoted_at'], entries['totals']['quoted_at'], key=time))
    lg.update(market_raw_path=str(bundle_path) + '!' + prefix + 'odds.json',
              market_provider='the-odds-api', bookmaker=book, market_raw_sha256=meta['sha256'],
              provider_match_id=event['id'], captured_at=meta['captured_at'])


def build(data, bundle):
    base, state = data / 'future/bundle-v2', data / 'future/state'
    manifest = json.loads((base / 'manifest.json').read_bytes())
    packages = {p['match_id']: p for p in manifest['packages'] + json.loads((state / 'state.json').read_bytes())['packages']}
    output = []
    for result in json.loads((state / 'results.json').read_bytes()):
        if time(result['observed_at']) >= DEADLINE:
            continue
        r = packages[result['match_id']]['current_receipt']
        name = r['path']
        if name in manifest['aliases']:
            obj = manifest['objects'][manifest['aliases'][name]]
            fp = base / obj['path']
            require(sha(fp.read_bytes()) == obj['sha256'], name)
        else:
            fp = state / name.split('/future/state/')[1]
        ev = result['evidence']
        rp = state / ev['file']
        raw = rp.read_bytes()
        require(sha(raw) == ev['sha256'] and ev['identity_verified'] and result['score_basis'] == 'regulation_90', str(rp))
        require(json.loads(fp.read_bytes())['record_sha256'] == r['sha256'], name)
        output.append(verified_pair(fp.read_bytes(), raw, result['observed_at'],
                      dict(freeze_path=str(fp.relative_to(data)), raw_result_path=str(rp.relative_to(data)),
                           result_url=ev['url'], observation_basis='verified retained final response'),
                      [result['home_goals'], result['away_goals']]))
    normalized = {r['match_id']: r for line in (data / 'normalized-results.jsonl').read_bytes().splitlines()
                  if (r := json.loads(line))['cohort'] == 'bra.1'}
    with tarfile.open(bundle, 'r:gz') as tar:
        blobs = {m.name: tar.extractfile(m).read() for m in tar if m.isfile()}
    verified = {r['match_id']: r for r in json.loads(blobs['reports/review-kashiwa-20261115-1540/verified-results.json'])}
    for fn, fb in blobs.items():
        if not fn.startswith('forecasts/'):
            continue
        fixture = json.loads(fb)['fixture']
        mid = fixture['match_id']
        eid = mid.split(':')[1]
        score = None
        url = f'https://site.api.espn.com/apis/site/v2/sports/soccer/bra.1/summary?event={eid}'
        basis = 'verification of retained final response'
        hash_expected = None
        meta = None
        espn_identity = None
        identity_path = None
        if mid in verified:
            v = verified[mid]
            p = v['source_path'].split('/WCPP/')[1]
            raw = blobs[p]
            obs, hash_expected, basis = v['observed_at'], v['source_sha256'], v['observation_basis']
            score = [v['home_goals'], v['away_goals']]
            require(v['score_basis'] == 'regulation_90' and url == v['source_url'], mid)
            meta = 'reports/review-kashiwa-20261115-1540/verified-results.json'
        elif mid in normalized:
            v = normalized[mid]
            ref = v['raw_reference']
            p = ref['path']
            raw = gzip.decompress((data / p).read_bytes())
            obs, hash_expected, basis = v['known_at'], ref['sha256'], v['known_at_policy']
            score = [v['home_goals'], v['away_goals']]
            require(v['score_basis'] == 'regulation_90' and url == ref['source_url'], mid)
            meta = 'normalized-results.jsonl'
        elif eid == '401841275':
            meta = 'reports/review-jingcai-20261017-1400/results/espn-summary-周五011-401841275.meta.json'
            v = json.loads(blobs[meta])
            p = v['file'].split('/WCPP/')[1]
            raw, obs, hash_expected = blobs[p], v['fetched_at_utc'], v['sha256']
            require(v['url'] == url, mid)
            basis = 'HTTP response captured'
        elif eid == '401841272':
            meta = 'reports/review-20261020-0832/results/raw-manifest.json'
            v = json.loads(blobs[meta])
            ref = next(f for f in v['files'] if f['path'] == 'raw/espn-summary-401841272-latest.json')
            identity_path = str(Path(meta).parent / ref['path'])
            espn_identity = blobs[identity_path]
            require(sha(espn_identity) == ref['sha256'], mid + ' ESPN identity digest')
            meta = 'reports/jingcai-20261020-2115/facts-a/evidence_manifest.json'
            ref = next(r for r in json.loads(blobs[meta])['raw_files'] if r['path'] == 'raw/fotmob_matches_20261019.json')
            p = str(Path(meta).parent / ref['path'])
            raw, obs, hash_expected = blobs[p], ref['fetched_at_utc'], ref['sha256']
            url, basis = ref['url'], 'archived FotMob HTTP 200 final after original ESPN response at 71 minutes'
            require(ref['http_status'] == 200, mid + ' HTTP receipt')
        else:
            p = {'401841282': 'reports/jingcai-remaining-20261024-1902/review-25/周六030.json',
                 '401841286': 'reports/jingcai-20261026/review-20261027-0908/周一004.json'}[eid]
            meta = str(Path(p).parent / 'summary.json')
            raw, obs = blobs[p], json.loads(blobs[meta])['captured_at']
            basis = 'retained batch review time'
        require(hash_expected is None or sha(raw) == hash_expected, mid + ' raw digest')
        output.append(verified_pair(fb, raw, obs, dict(freeze_path='brazil_retained_inputs.tar.gz!' + fn,
                      raw_result_path=('brazil_retained_inputs.tar.gz!' if p in blobs else '') + p,
                      observation_metadata=('brazil_retained_inputs.tar.gz!' if meta in blobs else '') + meta,
                      observation_basis=basis, result_url=url), score, espn_identity))
        if identity_path:
            output[-1][1]['identity_raw_path'] = 'brazil_retained_inputs.tar.gz!' + identity_path
        if fixture.get('market_snapshots'):
            paired_markets(data, fixture, *output[-1])
    require(len({r['match_id'] for r, _ in output}) == len(output), 'duplicate training identities')
    return sorted(output, key=lambda pair: (time(pair[0]['kickoff_at']), pair[0]['match_id']))


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--data-root', type=Path, default=HERE.parents[2])
    cli.add_argument('--bundle-from-workspace', type=Path, help='optional: recreate retained inputs from restored WCPP')
    cli.add_argument('--out', type=Path, default=HERE)
    args = cli.parse_args()
    dest = args.out
    dest.mkdir(parents=True, exist_ok=True)
    bundle = HERE / 'brazil_retained_inputs.tar.gz'
    if args.bundle_from_workspace:
        archive_existing(args.bundle_from_workspace, bundle)
    pairs = build(args.data_root, bundle)
    with (dest / 'actual_current.jsonl.gz').open('wb') as stream, gzip.GzipFile(fileobj=stream, filename='', mode='wb', mtime=0) as gz:
        for row, _ in pairs:
            gz.write(canon(row) + b'\n')
    ledger = dict(deadline_exclusive=DEADLINE.isoformat(), input_bundle_sha256=sha(bundle.read_bytes()),
                  selection='All previously settled domestic Current rows in future state, plus all issued pre-deadline Brazil Current first freezes in the restored ledger. FT outcomes, league, kickoff, team home/away and neutral venue checked against original ESPN responses; for one Oct19 match the archived ESPN identity and an independently captured FotMob FT response were joined by league, kickoff and both oriented teams. Two originally attached complete Brazil h2h/total pairs checked against archived provider prices and timestamps. Other records retain missing market.', excluded=[], rows=[lg for _, lg in pairs])
    (dest / 'actual_current_sources.json').write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n')
    print(len(pairs), 'verified actual Current rows')
