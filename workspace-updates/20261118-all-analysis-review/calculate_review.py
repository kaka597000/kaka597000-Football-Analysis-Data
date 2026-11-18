"""Settle the locked population and every frozen model version, without refitting."""
import collections,hashlib,json,math,sys
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
R=Path(__file__).parent
S=Path('/workspace/Football-Analysis-xg-research-20261117')
sys.path[:0]=[str(S/'runtime'),str(S/'runtime/v5')]
from research.analysis_freeze import verify,aware
from research.team_goal_analysis import summarize_prediction,review as goal_review
from research_program.future_validation import check_matrix,quote_audit
from v5.paired_review import review as paired_review
from v2.model import total_settlement
from optimization.evaluate import settle_ou
from nations_league.xg_research import review_forward as xg_review
from nations_league.repair_forward import review as repair_review
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(name,x):
 with (R/name).open('x') as f:json.dump(x,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
lock=read(R/'review-scope-lock.json');results=read(R/'verified-results.json');res={r['match_id']:r for r in results}
fixtures={f['match_id']:f for f in lock['fixtures']};assert set(res)<=set(fixtures)
records=[]
for ref in lock['frozen_records']:
 assert sha(ref['archived_path'])==ref['file_sha256'] and sha(ref['original_path'])==ref['file_sha256']
 r=verify(read(ref['archived_path']));records.append((ref,r))
name={r['match_id']:r['payload']['name'] for _,r in records if r['track']=='comprehensive'}
SETTLEMENTS=('win','half_win','push','half_loss','loss')
def settle(mid,line,side):
 if mid not in res or line is None or side not in ('over','under'):return None
 r=res[mid];h,a=r['home_goals'],r['away_goals'];point=np.zeros((51,51));point[h,a]=1
 out=next(k for k,v in total_settlement(point,line,side).items() if v==1)
 assert {'win':'FULL_WIN','half_win':'HALF_WIN','push':'PUSH','half_loss':'HALF_LOSS','loss':'FULL_LOSS'}[out]==settle_ou(h+a,line,side)
 legs=[line] if float(2*line).is_integer() else [line-.25,line+.25]
 score=sum((h+a>q)-(h+a<q) for q in legs)/len(legs)*(1 if side=='over' else -1)
 assert out=={1:'win',.5:'half_win',0:'push',-.5:'half_loss',-1:'loss'}[score]
 return out
def wilson(h,n):
 if not n:return None
 z=1.959963984540054;p=h/n;den=1+z*z/n;rad=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den;center=(p+z*z/(2*n))/den
 return [center-rad,center+rad]
def counts(rows):
 done=[x for x in rows if x['settled']];ps=[x['primary_hit'] for x in done if x['primary_hit'] is not None];ws=[x['wdl_hit'] for x in done if x['wdl_hit'] is not None]
 ts=collections.Counter(x['total_settlement'] for x in done if x['total_settlement'] is not None);n=sum(ts.values());non=n-ts['push']
 return {'population':len(rows),'settled':len(done),'pending':len(rows)-len(done),'primary_n':len(ps),'primary_hits':sum(ps),'primary_accuracy':sum(ps)/len(ps) if ps else None,'primary_wilson95':wilson(sum(ps),len(ps)),'wdl_n':len(ws),'wdl_hits':sum(ws),'wdl_accuracy':sum(ws)/len(ws) if ws else None,'total_n':n,'total_non_push_n':non,'total_strict_full_win_rate':ts['win']/non if non else None,'total_settlements':{k:ts[k] for k in SETTLEMENTS},'coverage':{'primary':sum(x['primary'] is not None for x in rows)/len(rows) if rows else 0,'wdl':sum(x['wdl'] is not None for x in rows)/len(rows) if rows else 0,'total':sum(x['total_eligible'] for x in rows)/len(rows) if rows else 0}}
quote_sources={}
for base in ('/workspace/WCPP/reports/internationals-20261117-1120/markets-fallback','/workspace/WCPP/reports/tonight-20261117-2100/markets'):
 for p in Path(base).rglob('*.json'):quote_sources.setdefault(sha(p),p)
quote_checks=[]
def comp_quote(r):
 f=r['fixture'];q=f['total_quote'];p=r['payload'];assert p['total_line']==q['line']
 if q.get('verified'):
  assert quote_audit(f)['eligible'] and p['actual_quote']==q
  return q
 rawpath=quote_sources[q['source_sha256']];raw=read(rawpath)
 assert any(all(o.get(k)==q.get(k) for k in ('bookmaker','market_type','period','line','prices','status','as_of')) for o in raw['odds'])
 assert raw['event_id'] in q['source_url'] and q['market_type']=='totals' and q['period']=='full_time' and q['status']=='open'
 assert aware(q['source_quote_time'])<=aware(q['query_time'])<=aware(f['cutoff_at']) and (aware(f['cutoff_at'])-aware(q['source_quote_time'])).total_seconds()<=3600
 assert all(q['prices'][k]>1 for k in ('over','under'))
 quote_checks.append({'freeze_id':r['freeze_id'],'source_path':str(rawpath),'sha256':sha(rawpath),'status':'VERIFIED_ORIGINAL_PROVIDER_SCHEMA','no_quote_values_changed':True})
 return q
def row_for(ref,r,p,role,*,comprehensive=False,matrix_only=False):
 mid=r['match_id'];done=mid in res;actual=res.get(mid);actual_score=f"{actual['home_goals']}-{actual['away_goals']}" if done else None
 actual_wdl=('主胜' if actual['home_goals']>actual['away_goals'] else '客胜' if actual['home_goals']<actual['away_goals'] else '平局') if done else None
 if comprehensive:
  q=comp_quote(r);direction={'大':'over','小':'under'}.get(p.get('total_direction'));wdl=p.get('wdl');eligible=direction is not None
 else:
  q=(p.get('total') or {}).get('quote') or {};direction=(p.get('total') or {}).get('reference_direction');wdl=p.get('wdl_reference')
  audit=quote_audit(p.get('input') or {});eligible=audit['eligible'] and direction in ('over','under')
  if eligible:assert q==(p['input']['total_quote'])
 primary=p.get('primary');out={'match_id':mid,'name':name[mid],'competition':fixtures[mid]['competition'],'league_level':fixtures[mid].get('league_level'),'track':r['track'],'role':role,'version':p.get('version') or p.get('decision_policy_version') or p.get('method') or 'UNAVAILABLE','freeze_id':r['freeze_id'],'recorded_at':r['recorded_at'],'record_sha256':r['record_sha256'],'evaluation_role':ref['evaluation_role'],'revision':r['revision'],'settled':done,'actual':actual_score,'primary':primary,'primary_hit':primary==actual_score if done and primary is not None else None,'wdl':wdl,'wdl_hit':wdl==actual_wdl if done and wdl in ('主胜','平局','客胜') else None,'total_line':q.get('line'),'total_direction':direction,'total_eligible':eligible,'total_settlement':settle(mid,q.get('line'),direction) if eligible else None,'quote':q or None}
 if p.get('matrix') is not None:
  m=check_matrix(p)
  if done:
   h,a=actual['home_goals'],actual['away_goals'];g=summarize_prediction(p);gr=goal_review(g,home_goals=h,away_goals=a);total=np.add.outer(np.arange(m.shape[0]),np.arange(m.shape[1]));probs={'主胜':float(np.tril(m,-1).sum()),'平局':float(np.trace(m)),'客胜':float(np.triu(m,1).sum())}
   out['probability_diagnostics']={'mean':[g[s]['mean'] for s in ('home','away')],'actual':[h,a],'mean_error':[gr[s]['mean_error'] for s in ('home','away')],'absolute_error':[gr[s]['absolute_error'] for s in ('home','away')],'interval_hit':[gr[s]['interval_hit'] for s in ('home','away')],'interval':[g[s]['central_interval'] for s in ('home','away')],'p0':[g[s]['p0'] for s in ('home','away')],'observed_zero':[h==0,a==0],'p_total_ge4':float(m[total>=4].sum()),'observed_total_ge4':h+a>=4,'p_total_ge6':float(m[total>=6].sum()),'observed_total_ge6':h+a>=6,'score_log_loss':-math.log(max(float(m[h,a]),1e-15)),'wdl_log_loss':-math.log(max(probs[actual_wdl],1e-15)),'wdl_brier_sum3':sum((v-int(k==actual_wdl))**2 for k,v in probs.items()),'matrix_hash':p['matrix_hash'],'training_cutoff':p.get('training_data_cutoff'),'probability_only_does_not_create_missing_issued_directions':True}
 return out
rows=[];canonical=collections.defaultdict(list);raw_predictions={}
for ref,r in records:
 p=r['payload'];track=r['track'];mid=r['match_id']
 if track=='top3-selection':continue
 if track=='comprehensive':rows.append(row_for(ref,r,p,'comprehensive',comprehensive=True));continue
 preds={}
 if 'predictions' in p:preds.update(p['predictions']);preds.update({'venue:'+k:v for k,v in p.get('venue_sensitivity',{}).items()})
 elif track=='nations-paired-candidates':preds={k:p[k] for k in ('current','test')}
 elif track=='current-test-pair':preds={k:p[k] for k in ('current_model','test_model')}
 elif track=='friendly-independent-research':
  history=p['history_references'] if 'history_references' in p else p['research_models']
  preds={'history:'+k:v for k,v in history.items()};preds.update({k:p[k] for k in ('market_handicap_total_reference','market_wdl_total_reference') if k in p})
 for role,pred in preds.items():
  out=row_for(ref,r,pred,role);rows.append(out);raw_predictions[r['freeze_id'],role]=pred
  if pred.get('matrix') is None or (pred.get('input') is not None and pred.get('generated_at')):
   key=(track,role,ref['evaluation_role'],r['revision']);canonical[key].append({'match_id':mid,'fixture':pred.get('input') or r['fixture'],'current_model':pred,'test_model':pred})
canonical_reports={}
for key,pairs in canonical.items():
 rv=paired_review(pairs,results);canonical_reports['|'.join(map(str,key))]=rv
 for cr in rv['paired_rows']:
  own=next(x for x in rows if x['track']==key[0] and x['role']==key[1] and x['evaluation_role']==key[2] and x['revision']==key[3] and x['match_id']==cr['match_id'])
  for field in ('primary_hit','wdl_hit','total_settlement'):assert own[field]==cr['models']['当前模型'][field],(key,cr['match_id'],field)
groups=collections.defaultdict(list)
for row in rows:groups[(row['track'],row['role'],row['evaluation_role'],row['revision'])].append(row)
summaries=[]
for key,rs in groups.items():
 assert len(rs)==len({x['match_id'] for x in rs})
 summaries.append({'track':key[0],'role':key[1],'evaluation_role':key[2],'revision':key[3],'batch_descriptive':counts(rs),'by_version':{v:counts([x for x in rs if x['version']==v]) for v in sorted({x['version'] for x in rs})}})
first=[x for x in rows if x['track']=='comprehensive' and x['evaluation_role']=='FIRST_PREMATCH'];assert len(first)==11
updates=[x for x in rows if x['track']=='comprehensive' and x['evaluation_role']!='FIRST_PREMATCH']
top=[]
for _,r in records:
 if r['track']!='top3-selection':continue
 chosen=r['payload'].get('research_priorities') or r['payload']['top3'];rs=[]
 for c in chosen:
  x=next(x for x in first if x['match_id']==c['match_id']);assert x['primary']==c['primary'] and x['wdl']==c['wdl'] and x['total_line']==c['total_line']
  assert x['total_direction']=={'大':'over','小':'under'}[c['total_direction']]
  rs.append(dict(x,rank=c['rank']))
 top.append({'batch_id':r['match_id'],'freeze_id':r['freeze_id'],'rows':rs,'summary':counts(rs)})
def net(rs):
 a=sum(x['comprehensive_hit'] and not x['candidate_hit'] for x in rs);b=sum(x['candidate_hit'] and not x['comprehensive_hit'] for x in rs)
 dif=np.array([int(x['comprehensive_hit'])-int(x['candidate_hit']) for x in rs]);rng=np.random.default_rng(20261118);interval=np.quantile(rng.choice(dif,size=(20000,len(rs)),replace=True).mean(axis=1),[.025,.975]).tolist() if rs else None
 return {'n':len(rs),'changed_right':a,'changed_wrong':b,'net_hits':a-b,'descriptive_match_bootstrap95':interval,'single_batch_not_promotion_evidence':True,'rows':rs}
manual={}
comparators=[('nations-paired-candidates','current',2),('nations-paired-candidates','test',2)]+[('nations-fixed-reference-update',k,1) for k in ('fixed_current','fixed_test','challenger')]+[('nations-xg-reference-update','selected',1)]
for tr,role,revision in comparators:
 rs=[]
 for c in first:
  if c['competition']!='uefa.nations' or not c['settled']:continue
  wanted=role
  if role=='selected':wanted=next(r['payload']['locked_selected_arm'] for _,r in records if r['match_id']==c['match_id'] and r['track']==tr)
  p=next(x for x in rows if x['track']==tr and x['role']==wanted and x['revision']==revision and x['match_id']==c['match_id'])
  rs.append({'match_id':c['match_id'],'name':c['name'],'version':p['version'],'comprehensive':c['primary'],'candidate':p['primary'],'actual':c['actual'],'comprehensive_hit':c['primary_hit'],'candidate_hit':p['primary_hit']})
 manual[tr+':'+role]=net(rs)
nations=[r for r in results if r['competition']=='uefa.nations']
xgreport=xg_review('/workspace/WCPP/research/nations-xg-20261117/forward',nations)
old=read('/workspace/WCPP/reports/nations-review-20261117-0818/verified-results.json')
assert not set(res)&{r['match_id'] for r in old}
forward=repair_review('/workspace/kaka597000-Football-Analysis-Data/future/nations-repair-bundle',old+nations)
write('model-rows.json',rows);write('canonical-model-reviews.json',canonical_reports);write('model-summaries.json',summaries)
write('xg-first-forward-review.json',xgreport);write('repair-complete-forward-review.json',forward)
metrics={'calculated_at':datetime.now(timezone.utc).isoformat(),'population':11,'comprehensive_first':{'rows':first,'summary':counts(first),'by_competition':{c:counts([x for x in first if x['competition']==c]) for c in ('uefa.nations','fifa.friendly')}},'comprehensive_revisions':updates,'top3_batches':top,'manual_score_net':manual,'friendly_quote_schema_verifications':quote_checks,'all_forecast_rows':len(rows),'canonical_review_groups':len(canonical_reports),'model_parameters_changed':False,'future_model_promotion':False}
write('metrics.json',metrics)
print(json.dumps({'summary':metrics['comprehensive_first']['summary'],'top3':[(x['batch_id'],x['summary']) for x in top],'manual_net':{k:{n:v[n] for n in ('n','changed_right','changed_wrong','net_hits')} for k,v in manual.items()},'rows':len(rows),'canonical_groups':len(canonical_reports),'forward_pending':forward['pending']},ensure_ascii=False))
