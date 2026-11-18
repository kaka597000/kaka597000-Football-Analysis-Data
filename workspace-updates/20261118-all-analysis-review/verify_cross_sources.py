"""Confirm source identities and the official resolution of the one score conflict."""
import hashlib,json,re,sys
from pathlib import Path
from html.parser import HTMLParser
R=Path(__file__).parent
sys.path.insert(0,'/workspace/Football-Analysis-xg-research-20261117/runtime')
from research.analysis_freeze import aware
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
class Visible(HTMLParser):
 def __init__(self):super().__init__();self.skip=0;self.parts=[]
 def handle_starttag(self,t,a):
  if t in ('script','style'):self.skip+=1
 def handle_endtag(self,t):
  if t in ('script','style'):self.skip=max(0,self.skip-1)
 def handle_data(self,s):
  if not self.skip:self.parts.append(s)
lock=read(R/'review-scope-lock.json');fixtures={f['match_id']:f for f in lock['fixtures']};results={r['match_id']:r for r in read(R/'verified-results.json')}
cross=read(R/'friendly-results/independent-crosscheck.json');assert {x['match_id'] for x in cross}==set(results)
aliases={'Republic of Ireland':'Ireland','Northern Ireland':'Nor.Ireland','Bosnia-Herzegovina':'Bosnia & Herzegovina','China':'China'}
conflicts=[];agreed=[]
for row in cross:
 f=fixtures[row['match_id']];p=Path(row['source_path']);assert sha(p)==row['source_sha256']
 raw=read(p);event=next(x for x in raw['results'] if x['event_id']==row['independent_provider_event_id']);assert event==row['independent_result']
 assert event['event_id'] in f['total_quote']['source_url'] and aware(event['scheduled_at'])==aware(f['kickoff_at'])
 for side in ('home','away'):
  actual=f.get(side+'_name') or f[side];allowed={actual,aliases.get(actual,actual)}
  if actual=='Northern Ireland':allowed.add('Northern Ireland')
  if actual=='Bosnia-Herzegovina':allowed.update(('Bosnia','Bosnia and Herzegovina'))
  assert event[side+'_team'] in allowed,(row['match_id'],side,event[side+'_team'],allowed)
 expected=[results[row['match_id']][s+'_goals'] for s in ('home','away')]
 if [event['score'][s] for s in ('home','away')]==expected:agreed.append(row['match_id'])
 else:conflicts.append(row['match_id'])
assert conflicts==['espn:401861194'] and len(agreed)==10
resolution=read(R/'friendly-results/denmark-conflict-resolution.json');official=resolution['official_source'];assert sha(official['source_path'])==official['source_sha256']
parser=Visible();parser.feed(Path(official['source_path']).read_text());text=re.sub(r'\s+',' ',' '.join(parser.parts))
assert 'Danmark 2 - 3 Pauseresultat: 2 - 1 Norge' in text and '17.11.2026 20:45' in text and 'Parken, København' in text
assert 'På overtid fikk Norge straffespark' in text and '3-2-målet' in text
assert resolution['selected_regulation_score']=={'home':2,'away':3}
audit={'status':'PASS','same_second_provider_score':10,'officially_resolved_conflicts':1,'all_results_corroborated':11,'unresolved_result_conflicts':0,'official_source':official,'provider_discrepancy_reason':'UNKNOWN; conflicting InferSports raw value retained','goal_minute_disagreements':resolution['event_minute_discrepancies'],'regulation_basis':'ESPN two-half FT evidence; secondary final scores corroborate outcome'}
with (R/'cross-source-audit.json').open('x') as f:json.dump(audit,f,ensure_ascii=False,indent=2);f.write('\n')
print(json.dumps({k:audit[k] for k in ('status','same_second_provider_score','officially_resolved_conflicts','all_results_corroborated')},ensure_ascii=False))
