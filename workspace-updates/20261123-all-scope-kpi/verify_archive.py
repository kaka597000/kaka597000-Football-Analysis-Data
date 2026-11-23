"""Verify locked bytes, replay every competition, and authenticate all prospective first issues."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def obj(p):
    return json.loads(p.read_bytes())


def main():
    cli=argparse.ArgumentParser()
    cli.add_argument('--archive',type=Path,required=True);cli.add_argument('--code',type=Path,required=True)
    cli.add_argument('--workers',type=int,default=3);args=cli.parse_args()
    archive=args.archive.resolve();code=args.code.resolve();locks=obj(archive/'registration/all-20-corrected-input-locks.json')
    scores=obj(archive/'results/scorecard.json')
    scope=[v['code'] for v in obj(code/'configs/analysis-scope.json')['competitions']]
    assert scope==locks['scope'] and len(scope)==len(set(scope))==20 and len(scores)==40
    for k,v in obj(archive/'manifest.json')['files'].items():
        assert sha(archive/k)==v,k
    sys.path.insert(0,str(code/'runtime'))
    from research_program.goal_state_forward import review
    env=dict(os.environ,PYTHONPATH=str(code/'runtime'),OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        def verify(c):
            d=root/c;d.mkdir()
            with tarfile.open(archive/'models'/(c+'.tar.gz')) as t:t.extractall(d,filter='data')
            files=d/'study';panel=d/'panel.jsonl';out=d/'replay';out.mkdir()
            for name,expected in [('artifact.json',locks['competitions'][c]['primary']['artifact_sha256']),
                                  ('neighbor-artifact.json',locks['competitions'][c]['local_challenger']['artifact_sha256'])]:
                assert sha(files/name)==expected,(c,name)
            assert sha(panel)==locks['competitions'][c]['panel_sha256']
            for n in ('lock.json','artifact.json','neighbor-lock.json','neighbor-artifact.json'):shutil.copyfile(files/n,out/n)
            for module in ('all_scope_study','all_scope_neighbors'):
                subprocess.run([sys.executable,'-m','research_program.'+module,'evaluate','--competition',c,'--panel',str(panel),'--out',str(out)],check=True,env=env)
            for name in ('report.json','neighbor-report.json'):
                actual,archived=obj(out/name),obj(files/name)
                # Floating intervals are descriptive. All hits, denominators and policy choices are exact.
                for window in ('evaluation','recent'):
                    assert archived[window]['metrics']==actual[window]['metrics'],(c,window,name)
            for window in ('evaluation','recent'):
                for n in (window+'.jsonl','neighbor-'+window+'.jsonl'):
                    assert sha(files/n)==sha(out/n),(c,n)
            print('Reproduced '+c,flush=True)
        with ThreadPoolExecutor(args.workers) as pool:list(pool.map(verify,scope))
        with tarfile.open(archive/'forward-first-issues.tar.gz') as t:t.extractall(root,filter='data')
        audits=review(root/'issued',[],root)
        receipt=obj(root/'issued/receipts.json')
        assert len(receipt['matches'])==len(list((archive/'results/forward.csv').open(encoding='utf-8-sig')))-1
        assert audits and all(x['evidence']['first_issue_integrity_verified'] for x in audits.values())
        for name in ('issued','original-issued','market-priority'):
            groups=review(root/name,[],root,by_competition=True)
            assert set(groups)==set(scope) and sum(x['registered'] for x in groups.values())==len(receipt['matches'])
        original=obj(archive/'registration/all-20-selection-locks.json')
        for f in (archive/'original').glob('*.tar.gz'):
            c=f.name.removesuffix('.tar.gz')
            with tarfile.open(f) as t:
                old=t.extractfile('study/artifact.json').read()
                assert hashlib.sha256(old).hexdigest()==original['competitions'][c]['primary']['artifact_sha256']
        print('Verified first issues:',len(receipt['matches']),'competitions:',len(scope))

if __name__=='__main__':main()
