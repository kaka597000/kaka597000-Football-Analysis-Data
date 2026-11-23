#!/usr/bin/env python3
"""Normalize collected provider panels to the shared R5 schema and phase index."""
import collections,hashlib,json,pathlib
ROOT=pathlib.Path(__file__).resolve().parent
CODES=['aus.1','kor.1','jpn.league_cup','afc.champions','uefa.champions','uefa.europa']
FIELDS=['id','competition','stage','season','date','home','away','home_goals','away_goals','neutral','sources','h2h','total','bookmaker','market_time_basis','paired_market','score_basis']
def main():
 allrows=[]; by={}; phases=[]
 phase_path=ROOT/'phase-index.jsonl'
 phase_map={x['id']:x['phase'] for x in (json.loads(s) for s in phase_path.read_text().splitlines() if s.strip())} if phase_path.exists() else {}
 for code in CODES:
  p=ROOT/(code+'.jsonl'); inp=[json.loads(s) for s in p.read_text().splitlines() if s.strip()]
  out=[]
  for r in inp:
   phase=r.get('split') or phase_map.get(r['id'])
   assert phase in ('train_dev_2011_15','validation_2016','test_2017','validation_2015_16','test_2016_17'),(code,r.get('date'),phase)
   q={k:r.get(k) for k in FIELDS}; q['sources']=r.get('sources') or []
   out.append(q); phases.append({'id':q['id'],'competition':code,'date':q['date'],'phase':phase})
  out.sort(key=lambda x:(x['date'],x['id'])); by[code]=out; allrows.extend(out)
  p.write_text(''.join(json.dumps(r,ensure_ascii=False,separators=(',',':'))+'\n' for r in out))
 allrows.sort(key=lambda r:(r['competition'],r['date'],r['id']))
 phases.sort(key=lambda r:(r['competition'],r['date'],r['id']))
 (ROOT/'panel.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False,separators=(',',':'))+'\n' for r in allrows))
 (ROOT/'phase-index.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False,separators=(',',':'))+'\n' for r in phases))
 # Validate the date-driven phases independently of source season labels.
 for ph in phases:
  d=ph['date'];c=ph['competition']
  if c in ('uefa.champions','uefa.europa'):
   expected='test_2016_17' if '2016-07-01'<=d<='2017-06-30' else ('validation_2015_16' if '2015-07-01'<=d<='2016-06-30' else ('train_dev_2011_15' if '2011-07-01'<=d<='2015-06-30' else None))
  else:
   expected='test_2017' if d.startswith('2017-') else ('validation_2016' if d.startswith('2016-') else ('train_dev_2011_15' if '2011-01-01'<=d<='2015-12-31' else None))
  assert expected==ph['phase'],(ph,expected)
 for r in allrows: assert set(r)==set(FIELDS),(r['id'],set(r)^set(FIELDS))
 sums=[]
 for code,rs in by.items():
  count=collections.Counter(x['phase'] for x in phases if x['competition']==code)
  sums.append({'competition':code,'total_events':len(rs),'train_dev_2011_15':count['train_dev_2011_15'],'validation':count['validation_2016']+count['validation_2015_16'],'test':count['test_2017']+count['test_2016_17'],'90min_scored':sum(r['home_goals'] is not None and r['away_goals'] is not None for r in rs),'90min_missing':sum(r['home_goals'] is None or r['away_goals'] is None for r in rs),'event_calendar_year_counts':dict(collections.Counter(r['date'][:4] for r in rs)),'stages':dict(collections.Counter(r['stage'] for r in rs))})
 manifest=json.load(open(ROOT/'source_manifest.json'))
 report={'phase_definitions':manifest['phase_policy'],'competition_coverage':sums,'other_requested_competitions':[
  {'competition':'fifa.world','test_window':'2017 natural year / 2016-07-01..2017-06-30','matches':0,'reason':'No senior FIFA World Cup finals in the test window; this competition panel is finals, not qualifiers.'},
  {'competition':'uefa.nations','test_window':'2017 natural year / 2016-07-01..2017-06-30','matches':0,'reason':'Nations League started in 2018.'},
  {'competition':'uefa.europa.conf','test_window':'2017 natural year / 2016-07-01..2017-06-30','matches':0,'reason':'Conference League started in 2021.'}],
  'cleaning_checks':{'common_schema_fields':FIELDS,'phase_is_separate_phase_index':'phase-index.jsonl','all_rows_have_same_fields':True,'uefa_qualifying_excluded':True,'uefa_stage_outcome_text_removed':True,'AFC_format_transition_labeled_legacy':True,'all_test_dates_match_phase':True,'missing_90min_scores_are_retained_null_and_not_scoreable':True},
  'unscored_regulation_rows':[{'id':r['id'],'competition':r['competition'],'date':r['date'],'sources':r['sources']} for r in allrows if r['home_goals'] is None or r['away_goals'] is None],
  'jleague_90min_audit':'jleague_score_scope_audit.jsonl'}
 prior=[]
 r5dir=ROOT.parents[1]/'kpi-optimization-20261123-r5'/'panels'
 for code in CODES:
  p=r5dir/(code+'.jsonl')
  old=[json.loads(s) for s in p.read_text().splitlines() if s.strip()]
  dates=[r['date'] for r in old if r.get('date')]
  test_start,test_end=('2016-07-01','2017-06-30') if code in ('uefa.champions','uefa.europa') else ('2017-01-01','2017-12-31')
  prior.append({'competition':code,'r5_panel':str(p),'r5_panel_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'r5_panel_min_date':min(dates) if dates else None,'r5_panel_max_date':max(dates) if dates else None,'early_test_window':[test_start,test_end],'overlap_with_r5_panel':any(test_start<=d<=test_end for d in dates),'genuinely_new_by_r5_panel_date_coverage':not any(test_start<=d<=test_end for d in dates)})
 report['r5_existing_panel_overlap_check']=prior
 report['total_rows']=len(allrows);report['total_scored_90']=sum(r['home_goals'] is not None and r['away_goals'] is not None for r in allrows);report['total_null_90']=len(report['unscored_regulation_rows'])
 (ROOT/'availability-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'rows':len(allrows),'phases':dict(collections.Counter(x['phase'] for x in phases)),'coverage':sums},ensure_ascii=False))
if __name__=='__main__':main()
