"""Re-read raw ESPN period scores and event timelines against the locked fixtures."""
import hashlib,json,re,sys
from pathlib import Path
from datetime import datetime,timezone
R=Path(__file__).parent;S=Path('/workspace/Football-Analysis-xg-research-20261117')
O=Path(sys.argv[1]) if len(sys.argv)>1 else R
sys.path.insert(0,str(S/'runtime'))
from research.analysis_freeze import aware
from research.review_events import normalize_fotmob_goal
from research_program.nations_phase import verify_period_scores,_score_integer
from nations_league.repair_forward import validate_result
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(n,x):
 with (O/n).open('x') as f:json.dump(x,f,ensure_ascii=False,indent=2);f.write('\n')
lock=read(R/'review-scope-lock.json');results=[];process=[];goal_n=0
for f in lock['fixtures']:
 mid=f['match_id'];eid=mid.split(':')[-1];nations=f['competition']=='uefa.nations'
 if nations:
  paths=sorted((R/'nations-results/raw').glob('espn-'+eid+'-*.raw.json'));assert paths
  p=paths[0];meta=read(p.with_suffix('.capture.json'));url=meta['source_url'];observed=meta['observed_at'];expected=meta['source_sha256']
 else:
  p=R/'friendly-results/raw'/('espn-'+eid+'.json');meta=read(R/'friendly-results'/('espn-'+eid+'.json.meta.json'));url=meta['url'];observed=meta['captured_at'];expected=meta['sha256']
 assert meta['http_status']==200 and sha(p)==expected
 assert aware(lock['locked_at'])<aware(observed)
 raw=read(p);assert raw['header']['id']==eid;c=raw['header']['competitions'][0];status=c['status']['type']
 assert status['completed'] is True and status['name']=='STATUS_FULL_TIME' and aware(c['date'])==aware(f['kickoff_at'])
 teams={s:next(t for t in c['competitors'] if t['homeAway']==s) for s in ('home','away')};ids={s:str(teams[s]['team']['id']) for s in teams};names={s:teams[s]['team']['displayName'] for s in teams}
 for side in teams:assert ids[side]==(f[side].removeprefix('espn:') if nations else f[side+'_id'])
 goals=[verify_period_scores(teams[s],c['status'])['regulation'] for s in ('home','away')]
 result={**{k:f[k] for k in ('match_id','competition','cohort','stage','home','away','kickoff_at')},'home_goals':goals[0],'away_goals':goals[1],'status':'completed','event_status':'FT','score_basis':'regulation_90','observed_at':observed,'source_url':url,'source_path':str(p),'source_sha256':sha(p),'source_validation':'RAW_ESPN_FINAL_PERIOD_SCORE_VERIFIED; independent source agreement audited separately'}
 if nations:result['league_level']=f['league_level'];validate_result(result,f)
 athletes={str(p['athlete']['id']):{'team_id':str(ro['team']['id']),'name':p['athlete']['displayName'],'starter':p.get('starter')} for ro in raw.get('rosters',[]) for p in ro['roster']}
 score=[0,0];ht=[0,0];events=[]
 for e in raw.get('keyEvents',[]):
  if not e.get('scoringPlay'):continue
  assert not e.get('shootout') and e['period']['number'] in (1,2)
  aliases={'Bosnia-Herzegovina':'Bosnia and Herzegovina','China':'China PR'}
  text_names={s:aliases.get(names[s],names[s]) for s in names}
  match=re.search(re.escape(text_names['home'])+r' (\d+), '+re.escape(text_names['away'])+r' (\d+)\.',e['text']);assert match,(mid,e['text'])
  after=list(map(int,match.groups()));own=e['type']['type']=='own-goal';actor_id=str(e['participants'][0]['athlete']['id']);actor=athletes[actor_id];beneficiary=str(e['team']['id'])
  adapted={'type':'Goal','homeScore':score[0],'awayScore':score[1],'newScore':after,'ownGoal':own,'isHome':beneficiary==ids['home'],'shotmapEvent':{'isOwnGoal':own,'teamId':actor['team_id']},'timeStr':e['clock']['displayValue'],'fullName':actor['name']}
  norm=normalize_fotmob_goal(adapted,home_team_id=ids['home'],away_team_id=ids['away'])
  events.append({'event_id':e['id'],'minute':e['clock']['displayValue'],'period':e['period']['number'],'text':e['text'],'type':e['type']['type'],'source_provider':'ESPN','ownership_validation_adapter':'Shared score-delta helper; not a FotMob observation','normalized':norm})
  score=after
  if e['period']['number']==1:ht=after
 assert score==goals,(mid,score,goals)
 for i,side in enumerate(('home','away')):assert _score_integer(teams[side]['linescores'][0])==ht[i]
 stats={str(t['team']['id']):{v['name']:v.get('displayValue') for v in t['statistics']} for t in raw['boxscore']['teams']}
 focus={s:{k:stats[ids[s]].get(k) for k in ('totalShots','shotsOnTarget','possessionPct','redCards','expectedGoals','xG')} for s in ('home','away')}
 cards=[{'minute':e['clock']['displayValue'],'type':e['type']['type'],'team_id':e.get('team',{}).get('id'),'text':e['text']} for e in raw.get('keyEvents',[]) if e.get('type',{}).get('type') in ('red-card','second-yellow-card','yellow-red-card')]
 process.append({'match_id':mid,'score':score,'halftime':ht,'stats':focus,'all_stats':stats,'goals':events,'red_cards':cards,'starting_xi':{s:[{'athlete_id':k,**v} for k,v in athletes.items() if v['team_id']==ids[s] and v['starter']] for s in ('home','away')},'source_path':str(p),'source_sha256':sha(p)})
 results.append(result);goal_n+=len(events)
assert len(results)==len({x['match_id'] for x in results})==11
write('verified-results.json',results);write('verified-process.json',process)
write('raw-evidence-audit.json',{'verified_at':datetime.now(timezone.utc).isoformat(),'matches':11,'goal_events_verified':goal_n,'sources':'ESPN final period scores, score progression and roster player identity; independent source audit is separate','own_goals':[{'match_id':p['match_id'],**g} for p in process for g in p['goals'] if g['normalized']['detail']['own_goal']],'xg_match_coverage':sum(any(p['stats'][s]['expectedGoals'] is not None or p['stats'][s]['xG'] is not None for s in ('home','away')) for p in process)})
print(json.dumps({'matches':11,'goals_verified':goal_n,'scores':{r['match_id']:[r['home_goals'],r['away_goals']] for r in results}},ensure_ascii=False))
