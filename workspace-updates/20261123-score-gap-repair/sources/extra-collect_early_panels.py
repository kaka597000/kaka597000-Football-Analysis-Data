#!/usr/bin/env python3
"""Collect pre-R5 early-season scoreboards and normalize to R5 panel fields."""
import hashlib, json, pathlib, re, time, urllib.request, urllib.error

ROOT=pathlib.Path(__file__).resolve().parent
RAW=ROOT/'raw'; RAW.mkdir(parents=True,exist_ok=True)
COMPS=['aus.1','kor.1','jpn.league_cup','afc.champions','uefa.champions','uefa.europa']
YEARS=range(2011,2018)

def get(url):
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (WCPP historical-panel research)','Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=30) as r:return r.status,r.read()
def split_for(comp,date):
    if comp in ('uefa.champions','uefa.europa'):
        if '2016-07-01'<=date<='2017-06-30': return 'test_2016_17'
        if '2015-07-01'<=date<='2016-06-30': return 'validation_2015_16'
        if '2011-07-01'<=date<='2015-06-30': return 'train_dev_2011_15'
    else:
        if date.startswith('2017-'): return 'test_2017'
        if date.startswith('2016-'): return 'validation_2016'
        if '2011-'<=date<'2016-': return 'train_dev_2011_15'
    return None
def classify_stage(comp,season_slug,notes):
    slug=(season_slug or '').lower(); labels=' '.join(n.get('text','') for n in notes).lower()
    allowed={'group-stage':'group-stage','round-of-16':'round-of-16','round-of-32':'round-of-32','quarterfinals':'quarterfinals','quarter-finals':'quarterfinals','semifinals':'semifinals','semi-finals':'semifinals','final':'final',
      'second-round':'round-of-32','third-round':'round-of-16'}
    if re.match(r'^\d{4}-first-round$',slug) or re.match(r'^\d{6}-group-stage$',slug): slug='group-stage'
    if comp in ('uefa.champions','uefa.europa'):
        stage=allowed.get(slug)
        if not stage:return None,None
        leg='leg-1' if labels.startswith('1st leg') else ('leg-2' if labels.startswith('2nd leg') else None)
        return stage+(':'+leg if leg else ''),leg
    if comp=='afc.champions':
        stage=allowed.get(slug)
        if not stage:return None,None
        leg='leg-1' if labels.startswith('1st leg') else ('leg-2' if labels.startswith('2nd leg') else None)
        return 'legacy:'+stage.replace('-','_')+(':'+leg if leg else ''),leg
    if comp=='aus.1':
        if re.match(r'^\d{4}(?:-\d{2})?-australian-a-league$',slug): return 'regular',None
        if slug in ('elimination-finals','semifinals','grand-final','preliminary-final') or slug.startswith('finals---week-'):
            return 'playoffs:'+slug.replace('---','-').replace('-','_'),None
        return 'stage-unresolved',None
    return slug.replace('-','_') or 'stage-unresolved',None
def main():
    rawmeta=[]; rows=[]; failures=[]
    for comp in COMPS:
      for year in YEARS:
        url=f'https://site.api.espn.com/apis/site/v2/sports/soccer/{comp}/scoreboard?dates={year}&limit=1000'
        fn=f'{comp.replace(".","_")}-{year}-scoreboard.json'; p=RAW/fn
        try:
            status,body=get(url); p.write_bytes(body); digest=hashlib.sha256(body).hexdigest()
            rawmeta.append({'competition':comp,'calendar_year':year,'url':url,'http_status':status,'file':'raw/'+fn,'bytes':len(body),'sha256':digest})
            if status!=200: failures.append({'competition':comp,'calendar_year':year,'http_status':status,'url':url}); continue
            data=json.loads(body)
            for e in data.get('events') or []:
                date=(e.get('date') or '')[:10]; phase=split_for(comp,date)
                if not phase: continue
                c=(e.get('competitions') or [{}])[0]; typ=(c.get('status') or e.get('status') or {}).get('type') or {}
                if not typ.get('completed') or typ.get('state')!='post': continue
                tm={z.get('homeAway'):z for z in c.get('competitors') or []}
                if not all(k in tm for k in ('home','away')): continue
                h,a=tm['home'],tm['away']; hg=ag=None
                name=typ.get('name',''); basis='regulation_90'
                if any(x in name for x in ('AET','PEN','AGT','EXTRA')):
                    goals={'home':0,'away':0}; total={'home':0,'away':0}; team_side={z.get('team',{}).get('id'):k for k,z in tm.items()}; valid=True
                    for d in c.get('details') or []:
                        if not d.get('scoringPlay') or d.get('shootout'): continue
                        clock=str((d.get('clock') or {}).get('displayValue') or ''); m=re.match(r'^(\d+)',clock); side=team_side.get((d.get('team') or {}).get('id'))
                        if not m or side not in goals or 'ownGoal' not in d: valid=False; break
                        if d.get('ownGoal'): side='away' if side=='home' else 'home'
                        total[side]+=int(d.get('scoreValue') or 1)
                        if int(m.group(1))<=90: goals[side]+=int(d.get('scoreValue') or 1)
                    try: scoreboard={'home':int(float(h['score'])),'away':int(float(a['score']))}
                    except (KeyError,ValueError,TypeError): scoreboard=None
                    if not valid or scoreboard!=total:
                        # Preserve the event but do not confuse the final (possibly ET) score with FT90.
                        hg=ag=None; basis='regulation_90_unavailable_AET_or_penalties'
                    else: hg,ag=goals['home'],goals['away']; basis='regulation_90_scoring_events_excluding_extra_time_and_shootout'
                else:
                    try: hg=int(float(h['score']));ag=int(float(a['score']))
                    except (KeyError,ValueError,TypeError): continue
                notes=c.get('notes') or []; season_obj=e.get('season') or {}; stage,leg=classify_stage(comp,season_obj.get('slug'),notes)
                if stage is None: continue
                season_year=season_obj.get('year') or year
                season=f'{season_year}-{str(int(season_year)+1)[-2:]}' if comp.startswith('uefa.') else str(season_year)
                venue=c.get('venue') or e.get('venue') or {}
                rows.append({'id':'espn:'+str(e.get('id')),'competition':comp,'stage':stage,'season':season,'split':phase,'date':date,
                    'home':(h.get('team') or {}).get('displayName'),'away':(a.get('team') or {}).get('displayName'),'home_goals':hg,'away_goals':ag,
                    'neutral':bool(c.get('neutralSite') or venue.get('neutralSite')),'sources':[{'url':url,'sha256':digest,'match_url':f'https://www.espn.com/soccer/match/_/gameId/{e.get("id")}'}],
                    'h2h':None,'total':None,'bookmaker':None,'market_time_basis':None,'paired_market':False,'score_basis':basis,
                    'provider_stage_slug':season_obj.get('slug'),'provider_leg':leg,'provider_status':typ.get('detail') or typ.get('shortDetail'),
                    'historical_format':'pre-2024_AFC_Champions_League' if comp=='afc.champions' else None})
        except urllib.error.HTTPError as ex:
            body=ex.read(); fn=f'{comp.replace(".","_")}-{year}-error-{ex.code}.body'; ep=RAW/fn; ep.write_bytes(body)
            failures.append({'competition':comp,'calendar_year':year,'http_status':ex.code,'error_body_file':'raw/'+fn,'error_body_sha256':hashlib.sha256(body).hexdigest(),'error':str(ex),'url':url})
        except Exception as ex:
            failures.append({'competition':comp,'calendar_year':year,'error':str(ex),'url':url})
        time.sleep(.08)
    rows=sorted({r['competition']+':'+r['id']:r for r in rows}.values(),key=lambda r:(r['competition'],r['date'],r['id']))
    (ROOT/'panel.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False,separators=(',',':'))+'\n' for r in rows))
    for comp in COMPS:
        (ROOT/(comp+'.jsonl')).write_text(''.join(json.dumps(r,ensure_ascii=False,separators=(',',':'))+'\n' for r in rows if r['competition']==comp))
    manifest={'provider':'ESPN public Site API','captured_at_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'scope':COMPS,'phase_policy':'Europe: test 2016-07-01..2017-06-30, validation 2015-07-01..2016-06-30, train_dev 2011-07-01..2015-06-30. Calendar competitions: test 2017, validation 2016, train_dev 2011-2015.','capture_files':rawmeta,'failures':failures,'rows':len(rows),'score_policy':'Only status-FT scoreboard values or event-level goal events through minute 90 are scored; AET/PEN with unavailable event detail is retained with null regulation score. Markets null.'}
    (ROOT/'source_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'rows':len(rows),'by_comp':{c:sum(x['competition']==c for x in rows) for c in COMPS},'failures':failures},ensure_ascii=False))
if __name__=='__main__':main()
