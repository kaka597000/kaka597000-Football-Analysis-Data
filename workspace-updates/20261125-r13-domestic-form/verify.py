"""Verify source bytes, recalculate scores, and independently read the frozen rankings."""

import argparse
from collections import Counter, defaultdict
from datetime import datetime
import gzip
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parent
METRICS = ('score_top1','score_top3','wdl','actual_ou')


def check(condition, message):
    if not condition:
        raise ValueError(str(message))


def read(path):
    return json.loads(path.read_bytes())


def lines(path):
    with (gzip.open(path, 'rt', encoding='utf8') if path.suffix == '.gz' else path.open(encoding='utf8')) as f:
        return [json.loads(line) for line in f if line.strip()]


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def unpack(path, dest):
    with tarfile.open(path) as t:
        t.extractall(dest, filter='data')


def receipt(folder, ref):
    obj = read(folder/ref['file'])
    raw = {k:v for k,v in obj.items() if k != 'record_sha256'}
    digest = hashlib.sha256(json.dumps(raw, sort_keys=True, ensure_ascii=False, separators=(',',':'),
                                      allow_nan=False).encode()).hexdigest()
    check(obj['record_sha256'] == ref['sha256'] == digest and obj['freeze_id'] == ref['id'], ref)
    check(obj['revision'] == 1 and obj['previous_sha256'] is None and obj['evaluation_slot'] == 'FIRST_PREMATCH', ref)
    return obj


def asian(goals, line, side):
    ticks = round(4*line)
    check(ticks == 4*line and side in ('over','under'), (goals,line,side))
    legs = [ticks-1,ticks+1] if ticks%2 else [ticks,ticks]
    direction = 1 if side == 'over' else -1
    delta = [direction*(4*goals-leg) for leg in legs]
    result = sum((value>0)-(value<0) for value in delta)
    return {2:'FULL_WIN',1:'HALF_WIN',0:'PUSH',-1:'HALF_LOSS',-2:'FULL_LOSS'}[result]


def inspect_replay(folder):
    metrics = read(folder/'metrics.json')
    counts = defaultdict(lambda: {k:[0,0] for k in METRICS})
    totals = defaultdict(Counter)
    seen = set()
    for path in sorted(folder.glob('*/forecasts.jsonl.gz')):
        for row in lines(path):
            code, win, mid = row['cohort'], row['window'], row['id']
            check((code,mid) not in seen, 'duplicate replay '+mid)
            seen.add((code,mid))
            h,a = row['actual']
            score = f'{h}-{a}'
            direction = 'home' if h>a else 'away' if a>h else 'draw'
            for arm, pred in row['forecast'].items():
                top = pred.get('top3')
                if top:
                    check(len(top) == len(set(top)) == 3 and top[0] == pred['primary'], (arm,mid))
                pay = None
                if pred.get('total_side'):
                    check(pred['total_line'] == row['line'], (arm,mid,'line'))
                    pay = asian(h+a, row['line'], pred['total_side'])
                vals = [score==pred['primary'] if pred.get('primary') else None,
                        score in top if top else None, direction==pred['wdl'] if pred.get('wdl') else None,
                        pay=='FULL_WIN' if pay and pay!='PUSH' else None]
                for c in (code, 'ALL'):
                    k = win,c,arm
                    for name, v in zip(METRICS,vals,strict=True):
                        if v is not None:
                            counts[k][name][0] += int(v)
                            counts[k][name][1] += 1
                    if pay:
                        totals[k][pay] += 1
    for w, window in metrics.items():
        for c, summary in [('ALL',window['overall']),*window['competitions'].items()]:
            for arm, scores in summary['scores'].items():
                key = w,c,arm
                check(counts[key] == scores['counts'] and totals[key] == scores['settlements'], key)
    return len(seen)


def compare(trained, reference):
    for p in sorted(reference.glob('*/forecasts.jsonl.gz')):
        code = p.parent.name
        actual = lines(trained/code/p.name)
        expected = lines(p)
        for row, orig in zip(actual, expected, strict=True):
            keys = ('id','date','cohort','window','actual','line','domestic_games')
            check(all(row[k] == orig[k] for k in keys) and row['forecast']['candidate'] == orig['forecast']['candidate'],
                  ('retrained forecast', code, orig['id']))
        for name in ('fit.json','forward.json'):
            real, src = read(trained/code/name), read(p.parent/name)
            check(real['doses'] == src['doses'] and real['fitted']['games_with_signal'] == src['fitted']['games_with_signal'],
                  ('retrained policy',code,name))
            check(all(math.isclose(x,y,abs_tol=1e-6,rel_tol=1e-6) for x,y in
                      zip(real['fitted']['beta'],src['fitted']['beta'],strict=True)), ('retrained coefficients', code))


def inspect_forward(root):
    f, k = root/'forward', root/'ranked'
    idx = read(f/'receipts.json')
    reg = receipt(f,idx['registration'])
    fixtures = reg['payload']['fixtures']
    by_code = defaultdict(list)
    check(set(fixtures) == set(idx['matches']), 'incomplete forward population')
    parent = ROOT.parent/'20261125-r10-shot-conversion'
    raw_parent = ROOT.parent/'20261123-all-scope-kpi'
    unpack(parent/'forward/first-issues.tar.gz', root/'r10')
    unpack(raw_parent/'forward-first-issues.tar.gz', root/'r5')
    old_idx = read(root/'r10/receipts.json')
    raw_idx = read(root/'r5/issued/receipts.json')
    source = receipt(root/'r10', old_idx['registration'])
    identities = reg['payload']['identity']
    check(identities['r10_registration'] == source['record_sha256'], 'R10 population link')
    eligible = {mid for mid,g in source['payload']['fixtures'].items() if g['cohort'] in identities['competitions']}
    check(set(fixtures) | set(identities['already_started']) == eligible, 'partial continental registration')
    for mid, ref in idx['matches'].items():
        record = receipt(f, ref)
        old = receipt(root/'r10', old_idx['matches'][mid])
        raw = receipt(root/'r5/issued', raw_idx['matches'][mid])
        g, p = record['fixture'], record['payload']
        check(all(g[t] == raw['fixture'][t] == old['fixture'][t] == fixtures[mid][t]
                  for t in ('match_id','cohort','stage','home','away','kickoff_at')), mid)
        stamps = [datetime.fromisoformat(v) for v in (raw['recorded_at'],old['recorded_at'],
                  reg['recorded_at'],g['cutoff_at'],record['recorded_at'],g['kickoff_at'])]
        check(stamps == sorted(stamps) and stamps[-2] < stamps[-1] and
              p['registration_sha256'] == reg['record_sha256'] and p['r10_first_issue'] == old['record_sha256']
              and p['odds_source_first_issue'] == raw['record_sha256'] and p['line'] == raw['payload']['line'],mid)
        check(p['forecasts']['r10'] == old['payload']['forecasts']['candidate'] and
              p['forecasts']['r7'] == old['payload']['forecasts']['r7'], mid)
        chosen = p['forecasts']['candidate']
        check(len(chosen['top3']) == len(set(chosen['top3'])) == 3 and chosen['primary'] == chosen['top3'][0], mid)
        by_code[g['cohort']].append((-p['quality']['p_first'], stamps[-1], mid, chosen['top3'], ref['sha256']))
    plan = receipt(k,read(k/'plan.json'))
    check(plan['payload']['fixtures'] == fixtures and
          plan['payload']['identity']['source_registration'] == reg['record_sha256'], 'ranked parent identity')
    slots = 0
    for code, group in plan['payload']['identity']['selected'].items():
        expected = sorted(by_code[code])[:3]
        check([(r['match_id'],r['top3'],r['first_issue']['sha256']) for r in group] ==
              [(x[2],x[3],x[4]) for x in expected], code)
        check(all(datetime.fromisoformat(r['first_issue']['recorded_at']) <= datetime.fromisoformat(plan['recorded_at'])
                  < datetime.fromisoformat(r['kickoff_at']) for r in group), code)
        slots += len(group)
    return len(fixtures), slots


def run(args, tmp):
    manifest = read(ROOT/'manifest.json')
    for name, expected in manifest['files'].items():
        check(sha(ROOT/name) == expected, 'checksum '+name)
    unpack(ROOT/'replay/forecasts.tar.gz', tmp/'replay')
    unpack(ROOT/'replay/regular-stages.tar.gz', tmp/'regular')
    if args.compare:
        compare(args.compare, tmp/('regular' if args.regular else 'replay'))
        print('Retrained selections and weights agree with archive.')
        return
    inputs = args.extract or tmp/'inputs'
    inputs.mkdir(parents=True, exist_ok=False)
    for path in sorted((ROOT/'inputs').glob('*.tar.gz')):
        unpack(path,inputs)
    for name, artifacts in [('domestic',('domestic.jsonl','domestic-regular.jsonl')),
                            ('continental',('identities.jsonl','extension.jsonl'))]:
        folder = inputs/name
        before = {p:sha(folder/p) for p in artifacts}
        subprocess.run([sys.executable,str(folder/'extract.py')],cwd=folder,check=True,stdout=subprocess.DEVNULL)
        check(all(sha(folder/p)==s for p,s in before.items()), 'reconstructed source '+name)
    inputs_hashes = read(tmp/'replay/inputs.json')
    for name, path in [('domestic','domestic/domestic.jsonl'),('identities','continental/identities.jsonl'),
                       ('extension','continental/extension.jsonl')]:
        check(sha(inputs/path) == inputs_hashes[name+'_sha256'], name)
    n = inspect_replay(tmp/'replay')
    check(inspect_replay(tmp/'regular') == n and read(tmp/'regular/inputs.json')['domestic_sha256'] ==
          sha(inputs/'domestic/domestic-regular.jsonl'), 'narrower domestic history or fixture population')
    unpack(ROOT/'forward/first-issues.tar.gz',tmp/'forward')
    unpack(ROOT/'forward/ranked.tar.gz',tmp/'ranked')
    future, slots = inspect_forward(tmp)
    print(json.dumps(dict(verified=True, domestic=len(lines(inputs/'domestic/domestic.jsonl')),
                          continental_ids=len(lines(inputs/'continental/identities.jsonl')),
                          evaluated=n, prospective=future, ranked_slots=slots)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--extract',type=Path)
    mode.add_argument('--compare',type=Path)
    parser.add_argument('--regular',action='store_true',help='compare the narrower domestic stage sensitivity')
    with tempfile.TemporaryDirectory() as temp:
        run(parser.parse_args(),Path(temp))
