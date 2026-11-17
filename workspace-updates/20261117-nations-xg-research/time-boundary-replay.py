from pathlib import Path
from nations_league import repair, xg_research as xg
p=Path(__file__).parent
history=repair.read(p/'canonical-history.json')
indexed=xg.index_xg(repair.read(p/'data/xg-records.json')['rows'],history)
quotes={r['match_id']:r for r in repair.read(p/'archived-quotes.json')}
lookup={r['match_id']:r for r in history};count=0
for level in 'ABCD':
 for arm in xg.ARMS:
  old=repair.read(p/'experiment'/level/(arm['id']+'-predictions.json'))
  last=None
  for expected in old:
   row=lookup[expected['match_id']]
   if last!=row['date']:
    core=xg.fit(xg.training_before(history,row),indexed,arm);last=row['date']
   actual=xg.historical_record(core,row,quotes.get(row['match_id']))
   assert actual==expected,(level,arm['id'],row['match_id'])
   count+=1
result={'checked_at':xg.now(),'historical_predictions_identical':count,'archived_prematch_quotes':len(quotes),'late_quotes_in_actual_experiment':0,'original_forecasts_unchanged':True,'engine_sha256':repair.sha(xg.__file__),'source_dependencies':xg.dependency_identity()}
repair.write(p/'time-boundary-verification.json',result)
print(result)
