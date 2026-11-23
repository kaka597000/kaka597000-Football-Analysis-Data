"""Restore the source data and reproduce registered predictions on the fixed sets of games."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
import gzip
import hashlib
import io
import json
import math
import os
from pathlib import Path
import sys
import tarfile
import tempfile


def read(p):
    return json.loads(p.read_bytes())


def sha(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()


def extract(archive,destination):
    with tarfile.open(archive) as tar:
        tar.extractall(destination,filter='data')


def equal(a,b):
    if isinstance(a,dict):
        assert a.keys()==b.keys()
        for k in a:equal(a[k],b[k])
    elif isinstance(a,(list,tuple)):
        assert len(a)==len(b)
        for x,y in zip(a,b):equal(x,y)
    elif isinstance(a,float):
        assert math.isclose(a,b,rel_tol=2e-6,abs_tol=2e-7),(a,b)
    else:
        assert a==b,(a,b)


def authenticate_inputs(root):
    for item in read(root/'raw/receipts.json'):
        assert sha(root/item['raw_path'])==item['sha256']
    for path in (root/'panels').glob('*.jsonl'):
        rows=[json.loads(l) for l in path.open()]
        assert len(rows)==len({g['id'] for g in rows})
        raw={}
        for g in rows:
            evidence=g['sources'][0];h=evidence['sha256']
            if h not in raw:
                file=next(x['raw_path'] for x in read(root/'raw/receipts.json') if x['sha256']==h)
                raw[h]=list(csv.DictReader((root/file).read_text(encoding='cp1252').splitlines()))
            r=raw[h][evidence['row']-2]
            assert (r['HomeTeam'].strip(),r['AwayTeam'].strip(),int(r['FTHG']),int(r['FTAG']))==(
                g['home'],g['away'],g['home_goals'],g['away_goals'])
            if g['h2h']:
                assert [g['h2h'][s] for s in ('home','draw','away')]==[float(r[k]) for k in ('B365H','B365D','B365A')]
            if g['total']:
                assert g['total']['line']==2.5 and min(g['total']['over'],g['total']['under'])>1


def private_panels(here,dest,with_key):
    meta=read(here/'inputs/phoenix.json')
    parts=[]
    for part in meta['parts']:
        path=here/'inputs'/part['file']
        assert sha(path)==part['sha256'] and path.stat().st_size==part['bytes']
        parts.append(path.read_bytes())
    if not with_key:return
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    key=hashlib.scrypt(b'wcpp/phoenix/literature-replay/v1\0'+os.environ['fenghuangtest'].strip().encode(),
        salt=bytes.fromhex(meta['salt']),n=32768,r=8,p=1,maxmem=128<<20,dklen=32)
    body=AESGCM(key).decrypt(bytes.fromhex(meta['nonce']),b''.join(parts),b'wcpp/phoenix/literature-replay/v1')
    assert hashlib.sha256(body).hexdigest()==meta['plain_sha256']
    with tarfile.open(fileobj=io.BytesIO(body),mode='r:gz') as tar:tar.extractall(dest,filter='data')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for k in ('source','prior'):ap.add_argument('--'+k,required=True,type=Path)
    ap.add_argument('--workers',type=int,default=2)
    ap.add_argument('--phoenix',action='store_true',help='also refit the four protected Phoenix panels using the original trial key')
    args=ap.parse_args()
    here=Path(__file__).resolve().parent
    sys.path.insert(0,str(args.source.resolve()/'runtime'))
    from research_program import continuation_study as study,continuation_forward as forward,continuation_report as report
    from research_program import lagged_pass_study as graph,goal_state_forward as ledger,score_gap_study as r6
    from research_program.goal_state_study import read_lines
    from research.analysis_freeze import aware
    from research_program.kpi_validation import fixture_identity
    scores=read(here/'results/scores.json');manifest=read(here/'manifest.json')
    for f,signature in manifest['files'].items():assert sha(here/f)==signature,f
    r5=args.prior/'20261123-all-scope-kpi';prior=args.prior/'20261123-score-gap-repair'
    codes=manifest['scope']
    assert codes==[c['code'] for c in read(args.source/'configs/analysis-scope.json')['competitions']]
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp)
        for name in ('independent','pre2010','passing'):
            extract(here/'inputs'/(name+'.tar.gz'),root/name)
            if name!='passing':authenticate_inputs(root/name)
        private_panels(here,root/'private',args.phoenix)
        extract(prior/'inputs.tar.gz',root/'prior')
        totals=r6.index(read_lines(root/'prior/inputs/totals-sidecar.jsonl'))
        ext={w:r6.index(read_lines(root/n/'process.jsonl')) for w,n in [('additional','independent'),('pre2010','pre2010')]}
        def fit_all(c):
            bundle=root/'bundle'/c
            extract(here/'models'/(c+'.tar.gz'),bundle)
            source=root/'r5'/c;prev=root/'r6'/c
            extract(r5/'models'/(c+'.tar.gz'),source);extract(prior/'models'/(c+'.tar.gz'),prev)
            for w in ('main','early','additional','pre2010','t24','t1'):
                if w in ('t24','t1'):
                    if not args.phoenix or c not in ('eng.1','esp.1'):continue
                    stored=root/'private/studies'/w/c
                    panel=root/'private/panels'/w/(c+'.jsonl')
                else:
                    stored=bundle/w
                    if not stored.exists():
                        assert (w=='early' and c not in scores['early']['competitions']) or (w in ext and c not in scores[w]['competitions'])
                        continue
                    if w=='main':panel=source/'panel.jsonl'
                    elif w=='early':panel=prev/'early-panel.jsonl'
                    else:panel=root/('independent' if w=='additional' else w)/'panels'/(c+'.jsonl')
                fit=read(stored/'fit.json');actual=root/'refits'/w/c
                assert sha(panel)==fit['source_panel_sha256']
                control=prev/('replay' if w=='main' else 'early') if w in ('main','early') else None
                study.run(panel,c,actual,bounds=fit['bounds'],mode=w,control=control,
                    totals=totals if w=='early' else None,observations=ext.get(w))
                reproduced=read(actual/'fit.json')
                for k in ('competition','training_games','training_through','selection','bounds','source_panel_sha256'):
                    equal(fit[k],reproduced[k])
                old=study.read_gzip(stored/'forecasts.jsonl.gz');new=study.read_gzip(actual/'forecasts.jsonl.gz')
                equal(old,new)
                if w=='main':
                    forward_fit=read(stored/'forward.json')
                    assert forward_fit['fit_sha256']==sha(stored/'fit.json')
            print(c,'numerical replay passed',flush=True)
        with ThreadPoolExecutor(args.workers) as pool:list(pool.map(fit_all,codes))
        graph.run(root/'passing/panel.jsonl.gz',root/'refits/passing')
        extract(here/'models/passing.tar.gz',root/'stored-passing')
        equal(study.read_gzip(root/'stored-passing/forecasts.jsonl.gz'),study.read_gzip(root/'refits/passing/forecasts.jsonl.gz'))
        groups=report.collect(root/'refits')
        assert set(groups)==set(scores)-({'t24','t1'} if not args.phoenix else set())
        for w,rows in groups.items():equal(scores[w],report.result(rows))
        extract(here/'first-issues.tar.gz',root/'new')
        extract(r5/'forward-first-issues.tar.gz',root/'base')
        extract(prior/'first-issues.tar.gz',root/'old')
        prev=root/'old/agreement-issued';orig=root/'base/issued';new=root/'new'
        pidx=read(prev/'receipts.json');oidx=read(orig/'receipts.json');idx=read(new/'receipts.json')
        plan=ledger._read(new,idx['registration']);ident=plan['payload']['identity']
        assert ident['protocol_sha256']==sha(here/'protocol.json') and ident['old_registration_sha256']==pidx['registration']['sha256']
        assert (set(idx['matches'])|set(ident['already_started_at_registration']))==set(oidx['matches'])==set(pidx['matches'])
        for mid,entry in idx['matches'].items():
            r=ledger._read(new,entry);earlier=ledger._read(prev,pidx['matches'][mid]);source=ledger._read(orig,oidx['matches'][mid])
            f=r['fixture'];p=r['payload'];d=source['payload'];c=f['cohort']
            assert fixture_identity(f)==fixture_identity(earlier['fixture'])==fixture_identity(source['fixture'])
            assert aware(r['recorded_at'])<aware(f['kickoff_at'])
            assert p['r6_first_issue']==earlier['record_sha256'] and p['input_sha256']==source['record_sha256']
            path=root/'bundle'/c/'main/forward.json';assert sha(path)==p['model_sha256']==ident['recipe_sha256'][c]
            g=dict(id=mid,competition=c,date=aware(f['kickoff_at']).date().isoformat(),home=d['model_teams'][0],away=d['model_teams'][1],
                stage=d['model_stage'],neutral=d['neutral'],paired_market=d['market_mode']=='paired',**d['prices'])
            picks,quality=forward.predict(g,read(path))
            equal(picks,p['forecasts']['candidate']);equal(quality,p['quality'])
            assert p['forecasts']['r6']==earlier['payload']['forecasts']['agreement']
        print('Verified all stored first issues:',len(idx['matches']),flush=True)


if __name__=='__main__':main()
