from collections import defaultdict
from pathlib import Path
import json
import tarfile
import numpy as np

root=Path(__file__).resolve().parent
with tarfile.open(root/'evidence.tar.gz', 'r:gz') as archive:
    samples=[json.loads(line) for line in archive.extractfile('holdout/predictions.jsonl')]
summary={}
for metric in ('primary_hit','three_hit','wdl_hit'):
    dates=defaultdict(lambda: [0,0]); gained=lost=0
    for row in samples:
        old,new=[int(row['arms'][k][metric]) for k in ('goals','xg_calibrated')]
        dates[row['date']][0]+=new-old; dates[row['date']][1]+=1
        gained+=new>old;lost+=new<old
    groups=np.array([dates[k] for k in sorted(dates)])
    rng=np.random.default_rng(20261122)
    res=groups[rng.integers(0,len(groups),size=(5000,len(groups)))].sum(axis=1)
    summary[metric]={'gains':gained,'losses':lost,'net_hits':gained-lost,'dates':len(groups),'n':len(samples),
                     'net_percentage_points':100*(gained-lost)/len(samples),'date_cluster_bootstrap95_pp':(100*np.quantile(res[:,0]/res[:,1],[.025,.975])).tolist()}
(root/'holdout-intervals.json').write_text(json.dumps(summary,indent=2)+'\n')
print(summary)
