#!/usr/bin/env python3
"""Build complete World Cup edition panels from retained ESPN and OpenFootball raw files."""
import json,hashlib,pathlib,re,unicodedata,collections,datetime
ROOT=pathlib.Path('/workspace/WCPP/reports/kpi-optimization-20261123-r6/world-early'); RAW=ROOT/'raw'
YEARS=[1994,1998,2002,2006,2010,2014]
SPLITS={1994:'training',1998:'training',2002:'training',2006:'training',2010:'development',2014:'blind_test'}
ALIASES={'usa':'usa','unitedstates':'usa','cotedivoire':'ivorycoast','ivorycoast':'ivorycoast','korearepublic':'southkorea','southkorea':'southkorea','northkorea':'koreadpr','koreadpr':'koreadpr','turkey':'turkiye','turkiye':'turkiye','czechrepublic':'czechia','czechia':'czechia','iriran':'iran','iran':'iran','republicofireland':'ireland','ireland':'ireland','serbiaandmontenegro':'serbiamontenegro','serbiamontenegro':'serbiamontenegro','trinidadtobago':'trinidadandtobago','trinidadandtobago':'trinidadandtobago','yugoslavia':'yugoslavia','republicofkorea':'southkorea'}
def norm(s):
    s=unicodedata.normalize('NFKD',str(s)).encode('ascii','ignore').decode().lower()
    s=re.sub(r'[^a-z0-9]','',s)
    return ALIASES.get(s,s)
def norm_stage(s):
    z=str(s).lower()
    if 'group' in z: return 'group-stage'
    if 'round of 16' in z: return 'round-of-16'
    if 'round of 32' in z: return 'round-of-32'
    if 'quarter' in z: return 'quarterfinals'
    if 'semi' in z: return 'semifinals'
    if 'third' in z or '3rd' in z: return '3rd-place-match'
    if 'final' in z: return 'final'
    return 'stage-unresolved'
def minute90(v):
    m=re.match(r'^(\d+)',str(v or ''))
    return bool(m) and int(m.group(1))<=90
def score_goal_list(goals):
    if goals is None:return None
    return sum(1 for g in goals if minute90(g.get('minute')))
def source_sha(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
rows=[]; excluded=[]; validation=collections.Counter(); edition_counts={}
for year in YEARS:
    ofpath=RAW/'openfootball'/str(year)/'worldcup-full.json'; espnpath=RAW/'espn'/f'fifa.world-{year}-scoreboard.json'
    if not ofpath.exists() or not espnpath.exists():
        excluded.append({'season':str(year),'reason':'missing retained raw source'});continue
    of=json.loads(ofpath.read_text()); em=json.loads(espnpath.read_text()); ofsha=source_sha(ofpath); esha=source_sha(espnpath)
    blobmeta=json.loads((ofpath.with_suffix('.json.meta.json')).read_text()) if ofpath.with_suffix('.json.meta.json').exists() else {}
    ofurl=blobmeta.get('url'); espmeta=json.loads(espnpath.with_suffix(espnpath.suffix+'.meta.json').read_text()); espurl=espmeta.get('url')
    event_index=collections.defaultdict(list)
    for ev in em.get('events',[]):
        c=ev.get('competitions',[{}])[0]; teams={x.get('homeAway'):x.get('team',{}).get('displayName') for x in c.get('competitors',[])}
        if set(teams)=={'home','away'}: event_index[(norm(teams['home']),norm(teams['away']))].append((ev,c))
    for idx,m in enumerate(of.get('matches',[]),start=1):
        # OpenFootball team1/2 may not equal venue home/away; match the unordered pair against ESPN's explicit homeAway fields.
        a,b=norm(m.get('team1')),norm(m.get('team2')); candidates=[]
        match_day=datetime.date.fromisoformat(m['date'])
        for (eh,ea),vals in event_index.items():
            if not ((a==eh and b==ea) or (a==ea and b==eh)): continue
            for candidate in vals:
                event_day=datetime.date.fromisoformat(candidate[0].get('date','')[:10])
                if abs((event_day-match_day).days)<=1: candidates.append(candidate)
        # If old edition date labels differ by UTC/local boundary, unique team pair is still a stable identity.
        if len(candidates)!=1:
            excluded.append({'season':str(year),'date':m.get('date'),'team1':m.get('team1'),'team2':m.get('team2'),'source_stage':m.get('round'),'reason':'could not uniquely reconcile teams to ESPN home/away event','candidate_count':len(candidates)}); continue
        ev,c=candidates[0]; comps={x.get('homeAway'):x for x in c.get('competitors',[])}; hid=norm(comps['home'].get('team',{}).get('displayName')); aid=norm(comps['away'].get('team',{}).get('displayName'))
        if (a,b)==(hid,aid): team1_side='home'; team2_side='away'
        elif (a,b)==(aid,hid): team1_side='away'; team2_side='home'
        else:
            excluded.append({'season':str(year),'id':'fifa.world:'+ev['id'],'reason':'team order reconciliation failed'});continue
        score=m.get('score'); is_et=isinstance(score,dict) and 'et' in score
        if not is_et and isinstance(score,list) and len(score)==2:
            vals={team1_side:int(score[0]),team2_side:int(score[1])}; hg,ag=vals['home'],vals['away']; score_method='OpenFootball full-time score (no extra-time marker)'
        elif is_et:
            g1=score_goal_list(m.get('goals1')); g2=score_goal_list(m.get('goals2'))
            # Parse ESPN scoring-event minutes where present, collapsing duplicate alternate descriptions for the same goal.
            goals={'home':0,'away':0}; seen=set(); side={x.get('team',{}).get('id'):s for s,x in comps.items()}; valid=True; scoring_events=0
            for d in c.get('details',[]):
                if not d.get('scoringPlay') or d.get('shootout'):continue
                scoring_events+=1; tm=d.get('team',{}).get('id'); disp=d.get('clock',{}).get('displayValue'); minute=re.match(r'^(\d+)',str(disp or ''))
                if not minute or tm not in side:valid=False;break
                if int(minute.group(1))>90:continue
                k=(int(minute.group(1)),tm,int(d.get('scoreValue',1)))
                if k in seen:continue
                seen.add(k);goals[side[tm]]+=int(d.get('scoreValue',1))
            if not valid:
                excluded.append({'season':str(year),'id':'fifa.world:'+ev['id'],'date':m.get('date'),'team1':m.get('team1'),'team2':m.get('team2'),'reason':'ET result lacks parseable ESPN scoring-event time/team'});continue
            if g1 is not None and g2 is not None:
                vals={team1_side:g1,team2_side:g2}; hg,ag=vals['home'],vals['away']; score_method='OpenFootball goals through minute 90; extra-time events excluded'
                if scoring_events:
                    if goals['home']!=hg or goals['away']!=ag:
                        excluded.append({'season':str(year),'id':'fifa.world:'+ev['id'],'reason':'OpenFootball and ESPN regulation goal-minute scores disagree','openfootball_90':[hg,ag],'espn_event_90':[goals['home'],goals['away']]});continue
                    validation['et_regulation_goal_minutes_crosschecked']+=1
            elif scoring_events:
                hg,ag=goals['home'],goals['away']; score_method='ESPN goal events through minute 90; ET and shootout excluded'
            elif score.get('et')==[0,0]:
                hg,ag=0,0; score_method='OpenFootball post-ET 0-0 proves no regulation or extra-time goals'
            else:
                excluded.append({'season':str(year),'id':'fifa.world:'+ev['id'],'date':m.get('date'),'team1':m.get('team1'),'team2':m.get('team2'),'reason':'ET result lacks regulation goal-minute evidence'});continue
        else:
            excluded.append({'season':str(year),'id':'fifa.world:'+ev['id'],'date':m.get('date'),'reason':'unsupported OpenFootball score shape'});continue
        # For regulation-only score arrays, reconcile to ESPN final result. For ET scores, OpenFootball full-time result must match ESPN final score in home/away order.
        if not is_et:
            if int(comps['home'].get('score',-999))!=hg or int(comps['away'].get('score',-999))!=ag:
                excluded.append({'season':str(year),'id':'fifa.world:'+ev['id'],'reason':'OpenFootball FT score differs from ESPN scoreboard','openfootball_90':[hg,ag],'espn_ft':[comps['home'].get('score'),comps['away'].get('score')]});continue
            validation['ordinary_ft_reconciled']+=1
        else:
            et=score.get('et')
            if isinstance(et,list) and len(et)==2:
                vals={team1_side:int(et[0]),team2_side:int(et[1])}
                if int(comps['home'].get('score',-999))!=vals['home'] or int(comps['away'].get('score',-999))!=vals['away']:
                    excluded.append({'season':str(year),'id':'fifa.world:'+ev['id'],'reason':'OpenFootball post-ET result differs from ESPN final scoreboard','openfootball_et':[vals['home'],vals['away']],'espn_final':[comps['home'].get('score'),comps['away'].get('score')]});continue
                validation['post_et_result_reconciled']+=1
        source_stage=m.get('round') or c.get('altGameNote') or ev.get('season',{}).get('slug','')
        rows.append({'id':'fifa.world:'+ev['id'],'competition':'fifa.world','season':str(year),'date':ev.get('date','')[:10],'home':comps['home']['team'].get('displayName'),'away':comps['away']['team'].get('displayName'),'home_goals':hg,'away_goals':ag,'neutral':c.get('neutralSite'),'stage':norm_stage(source_stage),'source_stage':source_stage,'split':SPLITS[year],'leg':None,'score_basis':'regulation_90_openfootball_goal_minutes_excluding_extra_time_and_shootout' if is_et else 'regulation_90_openfootball_ft_score_reconciled_to_espn','h2h':None,'total':None,'bookmaker':None,'market_time_basis':None,'paired_market':False,'sources':[{'url':espurl,'sha256':esha},{'url':ofurl,'sha256':blobmeta.get('sha256')},{'provider':'retained openfootball source file','file':str(ofpath.relative_to(ROOT)),'sha256':ofsha}],'source_sha256':ofsha,'score_method':score_method,'source_status':c.get('status',{}).get('type',{}).get('name'),'neutral_basis':'ESPN neutralSite field; null retained when not explicitly supplied'})
    edition_counts[str(year)]=sum(r['season']==str(year) for r in rows)
# Stable order and strict uniqueness.
rows.sort(key=lambda r:(r['season'],r['date'],r['id']))
ids=[r['id'] for r in rows]
if len(ids)!=len(set(ids)): raise SystemExit('duplicate ids detected')
(ROOT/'fifa.world.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n' for r in rows))
(ROOT/'excluded-rows.json').write_text(json.dumps(excluded,ensure_ascii=False,indent=2)+'\n')
# Preserve actual HTTP metadata for every ESPN, GitHub tree, and per-year blob request.
requests=[]
for p in sorted((RAW).rglob('*.meta.json')):
    try:m=json.loads(p.read_text())
    except Exception:continue
    requests.append(m)
index={'records':len(rows),'editions':YEARS,'edition_counts':edition_counts,'split_counts':dict(collections.Counter(r['split'] for r in rows)),'stage_counts':{y:dict(collections.Counter(r['stage'] for r in rows if r['season']==str(y))) for y in YEARS},'score_basis':{'normal_time':sum(r['score_basis'].endswith('reconciled_to_espn') for r in rows),'extra_time_or_penalty':sum('excluding_extra_time' in r['score_basis'] for r in rows),'ordinary_ft_reconciled_to_espn':validation['ordinary_ft_reconciled'],'post_et_result_reconciled_to_espn':validation['post_et_result_reconciled'],'et_regulation_goal_minutes_crosschecked':validation['et_regulation_goal_minutes_crosschecked']},'unique_ids':len(set(ids)),'duplicates':len(ids)-len(set(ids)),'excluded_count':len(excluded),'excluded_by_reason':dict(collections.Counter(x.get('reason','unknown') for x in excluded)),'request_statuses':requests,'neutral':'ESPN neutralSite copied only where supplied; null otherwise. No inferred host/neutral labels.','markets':'No odds collected; all market fields null.'}
(ROOT/'index.json').write_text(json.dumps(index,ensure_ascii=False,indent=2)+'\n')
# Raw file manifest for auditable and reproducible inputs.
manifest=[]
for p in sorted(RAW.rglob('*')):
    if p.is_file():manifest.append({'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':source_sha(p)})
(ROOT/'raw-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'records':len(rows),'edition_counts':edition_counts,'excluded':len(excluded),'excluded_by_reason':dict(collections.Counter(x.get('reason','unknown') for x in excluded)),'reconciliation':dict(validation)},ensure_ascii=False))
