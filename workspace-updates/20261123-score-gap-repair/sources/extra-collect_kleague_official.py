#!/usr/bin/env python3
"""Fetch official K League 1 schedule/result API monthly archive, 2011-2017."""
import hashlib,json,pathlib,time,urllib.request,http.cookiejar
ROOT=pathlib.Path(__file__).resolve().parent; RAW=ROOT/'raw/kleague-official'; RAW.mkdir(parents=True,exist_ok=True)
BASE='https://www.kleague.com'; COMP='kor.1'
def main():
    jar=http.cookiejar.CookieJar(); opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar)); meta=[];rows=[];fail=[]
    for y in range(2011,2018):
      page=f'{BASE}/schedule.do?year={y}&leagueId=1'
      try: opener.open(urllib.request.Request(page,headers={'User-Agent':'Mozilla/5.0 (WCPP research)'}),timeout=20).read()
      except Exception as e: fail.append({'year':y,'error':'schedule page: '+str(e)}); continue
      for m in range(1,13):
        url=BASE+'/getScheduleList.do'; body=json.dumps({'leagueId':1,'teamId':None,'ticketStatus':'','year':str(y),'month':f'{m:02d}','ticketYn':'N'}).encode()
        req=urllib.request.Request(url,data=body,headers={'User-Agent':'Mozilla/5.0 (WCPP research)','Content-Type':'application/json; charset=utf-8','Referer':page,'Origin':BASE})
        fn=f'kor1-{y}-{m:02d}.json'
        try:
          raw=opener.open(req,timeout=20).read(); digest=hashlib.sha256(raw).hexdigest(); (RAW/fn).write_bytes(raw); obj=json.loads(raw)
          meta.append({'year':y,'month':m,'url':url,'request_body':json.loads(body),'http_status':200,'file':'raw/kleague-official/'+fn,'bytes':len(raw),'sha256':digest})
          if obj.get('resultCode')!='200': fail.append({'year':y,'month':m,'error':obj.get('resultMsg'),'source_file':'raw/kleague-official/'+fn}); continue
          for q in obj.get('data',{}).get('scheduleList',[]):
            if q.get('endYn')!='Y' or q.get('homeGoal') is None or q.get('awayGoal') is None: continue
            date=q['gameDate'].replace('.','-'); split='test_2017' if date.startswith('2017-') else ('validation_2016' if date.startswith('2016-') else ('train_dev_2011_15' if date[:4] in [str(z) for z in range(2011,2016)] else None))
            if split is None: continue
            # The official K League schedule API records senior first-team league results;
            # separate knockout/playoff events are excluded when explicitly identified.
            if q.get('isSemiPlayOff')=='Y' or q.get('gameType') not in (0,'0',None): continue
            hg,ag=int(q['homeGoal']),int(q['awayGoal'])
            rows.append({'id':f"kleague:{y}:{q.get('gameId')}:{date}",'competition':COMP,'stage':'regular','season':str(y),'split':split,'date':date,
              'home':q.get('homeTeamName'),'away':q.get('awayTeamName'),'home_goals':hg,'away_goals':ag,'neutral':False,
              'sources':[{'url':url,'sha256':digest,'provider':'K League official schedule/result API','schedule_page':page}],
              'h2h':None,'total':None,'bookmaker':None,'market_time_basis':None,'paired_market':False,'score_basis':'official_K_League_completed_match_result_regulation_90',
              'provider_stage_label':q.get('codeName'),'provider_round':q.get('roundId'),'provider_game_status':q.get('gameStatus'),'venue':q.get('fieldNameFull')})
        except Exception as e: fail.append({'year':y,'month':m,'url':url,'error':str(e)})
        time.sleep(.04)
    rows=sorted({r['id']:r for r in rows}.values(),key=lambda r:(r['date'],r['id']))
    (ROOT/'kor.1.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False,separators=(',',':'))+'\n' for r in rows))
    (ROOT/'kleague_manifest.json').write_text(json.dumps({'provider':'K League official public schedule/result API','provider_url':'https://www.kleague.com/schedule.do','retrieved_at_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'scope':'K League 1, calendar years 2011-2017','phase_policy':'2017 test; 2016 validation; 2011-2015 train/development','capture_files':meta,'failures':fail,'rows':len(rows),'score_policy':'Completed official first-team league result; explicit playoff rows excluded; scores treated as regulation results.'},ensure_ascii=False,indent=2)+'\n')
    print(f'K League official rows: {len(rows)}; months captured={len(meta)}; failures={len(fail)}')
if __name__=='__main__':main()
