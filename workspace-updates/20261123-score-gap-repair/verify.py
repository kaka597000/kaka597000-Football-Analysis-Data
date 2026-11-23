"""Reproduce fixed decisions and numeric fits from archived inputs in a blank directory."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from hashlib import file_digest
import json
import math
from pathlib import Path
import sys
import shutil
import tarfile
import tempfile


def obj(p):
    return json.loads(p.read_bytes())


def sha(p):
    with p.open('rb') as f:
        return file_digest(f,'sha256').hexdigest()


def extract(src,dest):
    with tarfile.open(src) as t:
        t.extractall(dest,filter='data')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for k in ('archive','prior','code'):
        ap.add_argument('--'+k,type=Path,required=True)
    ap.add_argument('--workers',type=int,default=2)
    a=ap.parse_args()
    sys.path.insert(0,str(a.code.resolve()/'runtime'))
    from research_program import score_gap_study as study,score_gap_forward as future
    from research_program.goal_state_study import read_lines
    from research_program import goal_state_forward as ledger
    from research_program.all_scope_study import _score
    from research_program.score_gap_first import decisions
    archive=a.archive
    manifest=obj(archive/'manifest.json')
    for path,expected in manifest['files'].items():
        assert sha(archive/path)==expected,path
    scope=[c['code'] for c in obj(a.code/'configs/analysis-scope.json')['competitions']]
    assert scope==manifest['competitions']
    scorecard=obj(archive/'results/scorecard.json')
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        extract(archive/'inputs.tar.gz',root)
        process=study.index(read_lines(root/'inputs/replay-input.jsonl'))
        old_process=study.index(read_lines(root/'inputs/early-input.jsonl'))
        totals=study.index(read_lines(root/'inputs/totals-sidecar.jsonl'))
        assembled=root/'raw-sources.tar.gz'
        with assembled.open('wb') as destination:
            for part in sorted(archive.glob('raw-sources.tar.gz.part-*')):
                with part.open('rb') as src:shutil.copyfileobj(src,destination)
        assert sha(assembled)==manifest['raw_archive_sha256']
        refs=obj(archive/'source-index.json')
        parent_refs=obj(a.prior/'evidence/source-index.json')
        for h,info in refs.items():
            if info.get('prior'):assert h in parent_refs,h
        required={info['member']:h for h,info in refs.items() if not info.get('prior')}
        with tarfile.open(assembled,mode='r|gz') as raw:
            for member in raw:
                expected=required.pop(member.name)
                with raw.extractfile(member) as f:
                    assert file_digest(f,'sha256').hexdigest()==expected,member.name
        assert not required, list(required)[:3]

        def check(code):
            cd=root/code;cd.mkdir()
            extract(a.prior/'models'/(code+'.tar.gz'),cd/'r5')
            extract(archive/'models'/(code+'.tar.gz'),cd/'stored')
            summary={}
            for mode in ('replay','early'):
                stored=cd/'stored'/mode
                if not stored.exists():
                    assert mode=='early' and code not in scorecard['early']['competitions']
                    continue
                new=cd/mode
                panel=cd/'r5/panel.jsonl' if mode=='replay' else cd/'stored/early-panel.jsonl'
                study.run(panel,code,new,process if mode=='replay' else old_process,
                          previous=cd/'r5/study',early=mode=='early',totals=totals if mode=='early' else None)
                actual=study.index(read_lines(new/'predictions.jsonl'))
                expected=study.index(read_lines(stored/'predictions.jsonl'))
                assert actual.keys()==expected.keys(),(mode,code)
                extra=study.index(read_lines(stored/'first-policy.jsonl'))
                assert extra.keys()==actual.keys()
                for mid,r in actual.items():
                    e=expected[mid]
                    assert (r['forecast'],r['actual'],r['line'],r['window'])==(e['forecast'],e['actual'],e['line'],e['window']),(mode,code,mid)
                    for arm,q in r['quality'].items():
                        for k,v in q.items():
                            assert math.isclose(v,e['quality'][arm][k],rel_tol=2e-6,abs_tol=2e-6),(mode,code,mid,arm,k)
                    rule=decisions(r['forecast'],r['quality'])
                    assert rule==extra[mid]['forecast'],(mode,code,mid,'first rule')
                    r['forecast'].update(rule)
                fit=obj(new/'fit.json'); prior_fit=obj(stored/'fit.json')
                for key in ('training_matches','training_through','panel_sha256','process_fixture_digest','r5_control'):
                    assert fit[key]==prior_fit[key],(code,mode,key)
                for arm,beta in fit['coefficients'].items():
                    assert all(abs(x-y)<2e-5 for x,y in zip(beta,prior_fit['coefficients'][arm])),(code,mode,arm)
                for window in (['early'] if mode=='early' else ['evaluation','recent']):
                    score=scorecard[window]['competitions'][code]['scores']
                    group=[r for r in actual.values() if r['window']==window]
                    for arm,metrics in score.items():assert _score(group,arm)==metrics,(code,window,arm)
                    summary[window]=len(group)
            print(code,summary,flush=True)
        with ThreadPoolExecutor(a.workers) as pool:list(pool.map(check,scope))

        extract(a.prior/'forward-first-issues.tar.gz',root/'previous')
        extract(archive/'first-issues.tar.gz',root)
        report=ledger.review(root/'issued',[],root,by_competition=True)
        old=root/'previous/issued';price=root/'previous/market-priority'
        old_index=obj(old/'receipts.json');price_index=obj(price/'receipts.json')
        index=obj(root/'issued/receipts.json')
        assert set(report)==set(scope) and sum(g['registered'] for g in report.values())==len(index['matches'])
        secondary=obj(root/'agreement-issued/receipts.json')
        ledger.review(root/'agreement-issued',[],root,by_competition=True)
        assert secondary['matches'].keys()==index['matches'].keys()
        candidates={c:obj(root/c/'stored/replay/forward-model.json') for c in scope}
        for mid,ref in index['matches'].items():
            f=ledger._read(root/'issued',ref)
            src=ledger._read(old,old_index['matches'][mid])
            ctl=ledger._read(price,price_index['matches'][mid])
            payload=f['payload'];code=f['fixture']['cohort']
            picks,_,_=future.predict_fixture(f['fixture'],src['payload'],candidates[code])
            for role,row in picks.items():assert row==payload['forecasts'][role],(mid,role)
            assert payload['previous_sha256']==src['record_sha256'] and payload['price_control_sha256']==ctl['record_sha256']
            assert payload['forecasts']['r5']==src['payload']['forecasts']['neighbor']
            assert payload['forecasts']['market_priority']==ctl['payload']['forecasts']['market_priority']
            alt=ledger._read(root/'agreement-issued',secondary['matches'][mid])['payload']
            assert alt['conditional_first_issue']==f['record_sha256']
            for arm,pick in decisions(payload['forecasts'],payload['quality']).items():
                assert pick==alt['forecasts'][arm],(mid,arm)
        print('All twenty competitions replayed, all',len(index['matches']),'first issues verified.',flush=True)

if __name__=='__main__':main()
