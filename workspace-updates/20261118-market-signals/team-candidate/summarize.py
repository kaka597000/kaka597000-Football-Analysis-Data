"""Build the two independent first-issue evidence tables from immutable records."""
import json
from pathlib import Path

from research.analysis_freeze import verify

HERE = Path(__file__).resolve().parent
ARMS = ('frozen_market_baseline','prematch_team_and_btts_adjustment')


def table(batch):
    rows=[]
    for path in (batch/'records').glob('*/*.json'):
        rec=verify(json.loads(path.read_bytes()))
        body=rec['payload']; f=rec['fixture']
        a,b=(body['arms'][name] for name in ARMS)
        features=body.get('features',body.get('feature_probabilities'))
        rows.append({
            'match_id':f['match_id'],'kickoff_at':f['kickoff_at'],'recorded_at':rec['recorded_at'],
            'home':f['home_name'],'away':f['away_name'],'bookmaker':body['quotes'][0]['bookmaker'],
            'reported_three_events':{key:next((feature for feature in features if feature['family']==key and
                                       (key=='btts' or feature['line']==.5)),None) for key in ('home','away','btts')},
            'line':a['total']['line'],
            'picks':{key:{'top1':arm['primary'],'top1_probability':arm['primary_probability'],'top3':arm['top3'],
                          'wdl':arm['wdl'],'total':arm['total']['direction']} for key,arm in zip(ARMS,(a,b))},
            'changed':{'top1':a['primary']!=b['primary'],'top3_order':a['top3']!=b['top3'],
                       'top3_set':set(a['top3'])!=set(b['top3']),'wdl':a['wdl']!=b['wdl'],
                       'total':a['total']['direction']!=b['total']['direction']},
            'leave_one_market_out':body.get('leave_one_out'), 'freeze_sha256':rec['record_sha256'],
            'record':path.relative_to(HERE).as_posix(),
        })
    return sorted(rows,key=lambda r:(r['kickoff_at'],r['match_id']))


if __name__=='__main__':
    result={'brazil':table(HERE),'england':table(HERE/'england')}
    print(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False))
