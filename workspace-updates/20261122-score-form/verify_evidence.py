"""Verify the frozen cases and reproduce the league fits from source snapshots in a clean checkout."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import tarfile
from tempfile import TemporaryDirectory

import numpy as np

HERE=Path(__file__).resolve().parent

def read(path):
    return json.loads(Path(path).read_bytes())

def validate(source):
    sys.path[:0]=[str(source/'runtime'),str(source/'runtime/v5'),str(source/'scripts')]
    from research.analysis_freeze import aware, verify
    from research_program.live_score_form import candidate
    from research_program.score_form import select_scores, rerank_issued
    from train_score_form import LEAGUES, load_seasons, train

    meta=read(HERE/'manifest.json')
    archive=HERE/'evidence.tar.gz'
    assert hashlib.sha256(archive.read_bytes()).hexdigest()==meta['archive_sha256']
    with TemporaryDirectory() as td:
        root=Path(td)
        with tarfile.open(archive,'r:gz') as bundle:
            files=bundle.getmembers()
            assert len(files)==len(meta['files']) and all(f.isfile() for f in files)
            assert {f.name for f in files}==set(meta['files'])
            bundle.extractall(root,filter='data')
        for name,h in meta['files'].items():
            assert hashlib.sha256((root/name).read_bytes()).hexdigest()==h
        check=read(HERE/'training/evaluation.json')
        holdout={(v['cohort'],v['id']):v for v in map(json.loads,(root/'holdout/predictions.jsonl').read_bytes().splitlines())}
        reproduced=0
        for cohort,lg in LEAGUES.items():
            games,sources=load_seasons(root/'understat',lg)
            old=read(HERE/'training'/(cohort+'.json'))
            model,rows,metrics=train(cohort,games,sources,old['built_at'])
            assert model['weight']==old['weight'] and sources==check['sources'][cohort]
            for k in ('goals','xg'):
                assert model[k]['features']==old[k]['features']
                np.testing.assert_allclose(model[k]['coefficients'],old[k]['coefficients'],rtol=1e-6,atol=1e-7)
                np.testing.assert_allclose(model[k]['intercept'],old[k]['intercept'],rtol=1e-6,atol=1e-7)
            np.testing.assert_allclose(model['cell_factors'],old['cell_factors'],rtol=1e-6,atol=1e-7)
            for row in rows:
                target=holdout[(cohort,row['id'])]
                assert row['date']==target['date'] and row['actual']==target['actual']
                for k,v in row['arms'].items():
                    a=target['arms'][k]
                    assert all(a[field]==v[field] for field in ('scores','wdl','primary_hit','three_hit','wdl_hit'))
                    assert abs(a['score_log_loss']-v['score_log_loss'])<1e-6
                reproduced+=1
        assert reproduced==len(holdout)==1752

        evaluated={r['id']:r for r in read(root/'latest/evaluated.json')}
        results=read(root/'latest/results.json')
        snapshots={s['match_id']:s for s in read(root/'latest/form-inputs.json')}
        count=Counter();verified_cases=0
        for key in sorted(evaluated):
            old=evaluated[key]
            comp=verify(read(root/'latest/comprehensive'/(key+'.json')))
            f=comp['fixture']; assert aware(comp['recorded_at'])<aware(f['kickoff_at'])
            assert [results[key]['home_goals'],results[key]['away_goals']]==old['goals']
            if comp['match_id'] not in snapshots:continue
            snap=snapshots[comp['match_id']]; cohort=f['cohort']; pair=verify(read(root/'latest/pairs'/(key+'.json')))
            assert comp['record_sha256']==snap['comprehensive_sha256']
            assert pair['record_sha256']==snap['pair_sha256']==comp['payload']['current_test_reference']['sha256']
            fitted=read(HERE/'training'/(cohort+'.json')) if cohort in LEAGUES else None
            res=candidate(f,pair['payload']['test_model'],read(root/'native-fits'/(cohort+'.json')),snap['form'],fitted,historical_replay=True)
            choice=select_scores(res,comp['payload']['primary'])
            ordered=rerank_issued(old['arms']['issued']['scores'],choice['primary'])
            assert choice==old['selection'] and ordered==old['arms']['rerank']['scores']
            assert [choice['primary'],*choice['alternates']]==old['arms']['proposal_check']['scores']
            assert res['pooled']['wdl']==old['arms']['proposal_check']['wdl']
            assert res['pooled']['total']['line']==old['arms']['proposal_check']['line']
            assert {'over':'大','under':'小'}[res['pooled']['total']['direction']]==old['arms']['proposal_check']['direction']
            count['old_first']+=old['arms']['issued']['scores'][0]==old['actual']
            count['new_first']+=ordered[0]==old['actual'];count['new_three']+=old['actual'] in ordered
            verified_cases+=1
        assert len(evaluated)==51 and verified_cases==40 and count=={'old_first':4,'new_first':5,'new_three':11}

        receipt=read(HERE/'forward-receipts.json');plan=verify(read(root/'forward/plan.json'))
        assert plan['record_sha256']==receipt['plan']['sha256'] and plan['stage']=='prematch'
        assert plan['payload']['source_commit']==meta['source_commit'] and plan['payload']['ids']==read(HERE/'protocol.json')['forward_plan_ids']
        for i,r in receipt['matches'].items():
            c=verify(read(root/'forward/registered'/(i+'.json'))); pair=verify(read(root/'forward/pairs'/(i+'.json')))
            assert c['record_sha256']==r['candidate_receipt']['sha256'] and c['payload']['paired_reference']['sha256']==pair['record_sha256']
            assert c['payload']['plan_reference']['sha256']==plan['record_sha256'] and c['match_id'] in plan['payload']['ids']
            assert aware(plan['recorded_at'])<=aware(pair['recorded_at'])<=aware(c['recorded_at'])<aware(c['fixture']['kickoff_at'])
            f=pair['fixture'];s={'match_id':f['match_id'],'cohort':f['cohort'],'home':f['home_form'],'away':f['away_form']}
            model=read(HERE/'training/eng.1.json')
            z=candidate(f,pair['payload']['test_model'],read(root/'native-fits/eng.1.json'),s,model)
            q=c['payload']['candidate']
            assert z['pooled_top3']==q['pooled_top3'] and z['pooled']['wdl']==q['pooled']['wdl']
            assert z['pooled']['total']['direction']==q['pooled']['total']['direction']
            assert z['fit_sha256']==q['fit_sha256']==plan['payload']['fit_hash']
            assert z['form_counts']==q['form_counts'] and all(x['n']==x['xg_n']==6 for x in z['form_counts'].values())
            assert c['payload']['result_status']=='PENDING'
    print(json.dumps({'verified_archive_files':len(meta['files']),'holdout_predictions':reproduced,'eligible_frozen_cases':verified_cases,
                      'forward_first_issues':len(receipt['matches']),'rerank':dict(count)}))

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--source',type=Path,required=True)
    validate(ap.parse_args().source.resolve())
