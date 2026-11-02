import json,numpy as np
from pathlib import Path

def load():
 root=Path('/workspace/WCPP/models/aus-expert-20261016-v1');ss=[json.load(open(root/(k+'-development.json.predictions.json'))) for k in ['poisson','dc','ml','constant']];ms=[{r['match_id']:r for r in s['predictions']} for s in ss];labels={r['match_id']:r for r in map(json.loads,Path('/workspace/WCPP/reports/aus-expert-20261016/dataset-v1/labels.jsonl').read_text().splitlines())};rows=[]
 for mid in ms[0]:
  rs=[m[mid] for m in ms];arrays=[np.array(r['matrix']) for r in rs];sh=np.max([a.shape for a in arrays],axis=0);arrays=[np.pad(a,[(0,int(sh[i]-a.shape[i])) for i in range(2)]).tolist() for a in arrays]
  rows.append(dict(match_id=mid,cohort='aus.1',date=rs[0]['date'],matrices=arrays,base_fit_ends=[s['fit_end'] for s in ss],home_goals=labels[mid]['home_goals'],away_goals=labels[mid]['away_goals']))
 return sorted(rows,key=lambda r:(r['date'],r['match_id']))
