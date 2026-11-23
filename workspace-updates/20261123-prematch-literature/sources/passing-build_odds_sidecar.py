#!/usr/bin/env python3
"""Join source match IDs and extract cached official football-data odds rows."""
import csv, datetime, hashlib, json, pathlib, re

HERE=pathlib.Path(__file__).resolve().parent
BASE=pathlib.Path('/workspace/WCPP/reports/kpi-optimization-20261123-r4/events')
RAW=BASE/'raw'; OUT=HERE/'odds'; OUT.mkdir(exist_ok=True)
LEAGUES={'eng.1':'1718_E0.csv','esp.1':'1718_SP1.csv','ger.1':'1718_D1.csv','ita.1':'1718_I1.csv','fra.1':'1718_F1.csv'}
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def num(v):
 try:return float(v) if v not in (None,'','NA','N/A') else None
 except ValueError:return None

def main():
 # Existing event table carries both source Wyscout match ID and exact source CSV line.
 aligned={}
 for line in open(BASE/'events.jsonl',encoding='utf8'):
  e=json.loads(line); match=re.search(r'source match ID (\d+)',e.get('source',{}).get('event_source',''))
  if not match: continue
  wid=int(match.group(1)); src=e['source']
  aligned[wid]={'fdid':e['match_id'],'date':e['game_date'],'home':e['home'],'away':e['away'],'hg':e['home_goals'],'ag':e['away_goals'],
    'file':pathlib.Path(src['football_data_file']).name,'line':int(src['football_data_line']),'cohort':e['cohort']}
 byrow={(v['file'],v['line']):(wid,v) for wid,v in aligned.items()}
 rows_by_comp={}; source_info=[]
 for comp,filename in LEAGUES.items():
  raw=RAW/filename; rows=[]
  with open(raw,encoding='utf-8-sig',newline='') as f:
   for lineno,r in enumerate(csv.DictReader(f),2):
    if not r.get('FTHG') or not r.get('FTAG'): continue
    pair=byrow.get((filename,lineno))
    if not pair: raise RuntimeError(f'missing audited match alignment for {filename}:{lineno}')
    wid,e=pair
    fmt='%d/%m/%Y' if len(r['Date'].split('/')[-1])==4 else '%d/%m/%y'
    date=datetime.datetime.strptime(r['Date'],fmt).date().isoformat()
    if (date,r['HomeTeam'],r['AwayTeam'],int(r['FTHG']),int(r['FTAG'])) != (e['date'],e['home'],e['away'],e['hg'],e['ag']):
     raise RuntimeError(f'fixture/date/score conflict {filename}:{lineno}')
    rows.append({'competition':comp,'wyscout_match_id':wid,'football_data_match_id':e['fdid'],'date':date,'home':r['HomeTeam'],'away':r['AwayTeam'],
      'score_90':{'home':int(r['FTHG']),'away':int(r['FTAG'])},'source_file':filename,'source_line':lineno,'source_sha256':sha(raw),
      'bet365_1x2':{'home':num(r.get('B365H')),'draw':num(r.get('B365D')),'away':num(r.get('B365A'))},
      'bbav_1x2':{'home':num(r.get('BbAvH')),'draw':num(r.get('BbAvD')),'away':num(r.get('BbAvA'))},
      'bet365_ou25':{'over':num(r.get('B365>2.5')),'under':num(r.get('B365<2.5'))},
      'bbav_ou25':{'over':num(r.get('BbAv>2.5')),'under':num(r.get('BbAv<2.5'))},'quote_time_utc':None,
      'quote_timing_note':'CSV gives no per-quote timestamp or documented quote-time basis.'})
  rows_by_comp[comp]=rows
  cols=['wyscout_match_id','football_data_match_id','source_line','date','home','away','FTHG','FTAG','B365H','B365D','B365A','BbAvH','BbAvD','BbAvA','B365>2.5','B365<2.5','BbAv>2.5','BbAv<2.5']
  replay=OUT/(filename+'.replay.csv')
  with open(raw,encoding='utf-8-sig',newline='') as f: rawrows={i:r for i,r in enumerate(csv.DictReader(f),2)}
  with open(replay,'w',encoding='utf8',newline='') as f:
   w=csv.DictWriter(f,fieldnames=cols);w.writeheader()
   for q in rows:
    r=rawrows[q['source_line']]
    w.writerow({'wyscout_match_id':q['wyscout_match_id'],'football_data_match_id':q['football_data_match_id'],'source_line':q['source_line'],'date':q['date'],'home':q['home'],'away':q['away'],'FTHG':r['FTHG'],'FTAG':r['FTAG'],**{k:r.get(k,'') for k in cols[8:]}})
  source_info.append({'source_file':filename,'source_url':f'https://www.football-data.co.uk/mmz4281/1718/{filename[5:-4]}.csv','sha256':sha(raw),'bytes':raw.stat().st_size,'replay_file':replay.name,'replay_sha256':sha(replay),'rows':len(rows),'source':'football-data.co.uk 2017/18 historical results and odds CSV'})
 with open(OUT/'odds-matches.jsonl','w',encoding='utf8') as f:
  for comp in LEAGUES:
   for q in rows_by_comp[comp]: f.write(json.dumps(q,ensure_ascii=False,separators=(',',':'))+'\n')
 # Stream patch graph IDs and source row provenance without holding 147 MB JSONL as Python objects.
 script_hash=sha(pathlib.Path(__file__)); tmp=HERE/'graph-matches.jsonl.tmp'
 with open(HERE/'graph-matches.jsonl',encoding='utf8') as src,open(tmp,'w',encoding='utf8') as dst:
  for line in src:
   x=json.loads(line); wid=int(x['id']['value']); e=aligned.get(wid)
   x['football_data_match_id']=e['fdid'] if e else None
   if e:
    x['football_data_source_row']={'file':e['file'],'line':e['line']}
    x['source_sha256']['football_data_join_script']=script_hash
    x['source_sha256']['football_data_csv']=sha(RAW/e['file'])
   dst.write(json.dumps(x,ensure_ascii=False,separators=(',',':'))+'\n')
 tmp.replace(HERE/'graph-matches.jsonl')
 flat=[q for comp in LEAGUES for q in rows_by_comp[comp]]
 manifest={'source':'football-data.co.uk five domestic leagues 2017/18','source_files':source_info,
  'quote_fields':{'Bet365':'B365H/B365D/B365A and B365>2.5/B365<2.5, named bookmaker','BbAv':'BbAvH/BbAvD/BbAvA and BbAv>2.5/BbAv<2.5, multi-bookmaker average and not a single institution'},
  'time_basis':'No per-quote timestamps or explicit quote-time basis in these CSV columns; quote_time_utc null; no open/close label assigned.',
  'alignment':'All 1,826 Wyscout IDs connect through source file and source line in r4/events/events.jsonl. Date, home, away, FTHG and FTAG checked against that audited row.',
  'records':len(flat),'competition_counts':{c:len(v) for c,v in rows_by_comp.items()},'jsonl_sha256':sha(OUT/'odds-matches.jsonl'),'jsonl_bytes':(OUT/'odds-matches.jsonl').stat().st_size,
  'graph_jsonl_sha256':sha(HERE/'graph-matches.jsonl'),'graph_jsonl_bytes':(HERE/'graph-matches.jsonl').stat().st_size,'join_script_sha256':script_hash}
 json.dump(manifest,open(OUT/'source-manifest.json','w'),ensure_ascii=False,indent=2)
 print('rows',len(flat),'aligned IDs null',sum(not v['fdid'] for v in aligned.values()))
if __name__=='__main__': main()
