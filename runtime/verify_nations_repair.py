"""Replay retained matrices in a restored environment; never issue a forecast."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np

CODE=Path('/workspace/Football-Analysis-nations-repair-20261116')
sys.path.insert(0,str(CODE/'runtime'));sys.path.insert(0,str(CODE))
from runtime.nations_league import repair,repair_forward
from research.analysis_freeze import verify


def verify_restored(index_path):
    manifest=repair.read(index_path);index=repair.read(manifest['final_index'])
    if index['dependencies']!=repair.dependency_identity():raise ValueError('restored executed source identity')
    if repair.sha(index['database_path'])!=index['database_sha256']:raise ValueError('database identity')
    protocol=repair.read(index['protocol_path'])
    if repair.sha(index['protocol_path'])!=index['protocol_sha256']:raise ValueError('protocol identity')
    old=repair.read(protocol['old_index'])
    if repair.sha(protocol['old_index'])!=protocol['old_index_sha256']:raise ValueError('original index identity')
    artifacts={};training={}
    for level in 'ABCD':
        training[level]=None
        for role,ref in index['routes'][level].items():
            a=repair.read(ref['path'])
            if repair.sha(ref['path'])!=ref['sha256'] or a['dependencies']!=repair.dependency_identity():
                raise ValueError('new artifact identity')
            for key in ('dataset','protocol'):
                if repair.sha(a[key+'_path'])!=a[key+'_sha256']:raise ValueError('artifact dependency identity')
            if training[level] is None:
                training[level]=len(repair.legacy.prepare(repair.read(a['dataset_path'])['rows']))
            artifacts[level,role]=a
        for role,ref in old['routes'][level].items():
            a=repair.read(ref['path'])
            if repair.sha(ref['path'])!=ref['sha256'] or a['engine_sha256']!=repair.sha(repair.legacy.__file__):
                raise ValueError('original core identity')
            for key in ('dataset','protocol'):
                if repair.sha(a[key+'_path'])!=a[key+'_sha256']:raise ValueError('original dependency identity')
            artifacts[level,'old_'+role]=a
    bundle=Path(manifest['final_forward']);report=repair_forward.review(bundle,[]);count=0;max_error=0.;quoted=0
    for path in sorted((bundle/'freezes').glob('*.json')):
        record=verify(repair.read(path));fixture=record['fixture'];level=fixture['league_level']
        if record['payload']['predictions']['fixed_test']['total'] is not None:quoted+=1
        for role,p in record['payload']['predictions'].items():
            a=artifacts[level,role]
            if role.startswith('old_'):
                matrix,_,_=repair.legacy.distribution(a['core'],role.removeprefix('old_'),fixture)
                score=repair.select_score(matrix)
            else:
                matrix,_,_=repair.distribution(a['core'],a['recipe'],fixture,a['numeric_role'],a['temperature'])
                score=repair.select_score(matrix,a['selector'])
            original=np.asarray(p['matrix']);error=float(np.abs(original-matrix).max())
            if not np.allclose(original,matrix,rtol=1e-12,atol=1e-13) or p['primary']!='-'.join(map(str,score)):
                raise ValueError('restored numerical replay differs')
            max_error=max(max_error,error);count+=1
    return {'mode':'RESTORED_HISTORICAL_MATRIX_REPLAY_NO_NEW_FORECAST','training_counts':training,
            'new_artifacts_verified':12,'old_artifacts_verified':8,'matrices_replayed':count,
            'max_absolute_difference':max_error,'population':report['population'],'quoted_population':quoted,
            'settled':0,'active_model_promotion':False,'source_commit':manifest['source_commit']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--index',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();r=verify_restored(a.index);Path(a.out).write_text(json.dumps(r,indent=2));print(json.dumps(r))
