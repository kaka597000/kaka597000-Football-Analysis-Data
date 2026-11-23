#!/usr/bin/env python3
"""Collect official J.League Data Site Levain Cup scores and match-card 90' halves."""
import hashlib,json,pathlib,re,time,urllib.request,urllib.parse,html
from html.parser import HTMLParser
ROOT=pathlib.Path(__file__).resolve().parent; RAW=ROOT/'raw/jleague-official'; RAW.mkdir(parents=True,exist_ok=True)
BASE='https://data.j-league.or.jp'; COMP='jpn.league_cup'
def get(url):
 req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (WCPP historical research)'})
 with urllib.request.urlopen(req,timeout=30) as r:return r.read()
def sha(b):return hashlib.sha256(b).hexdigest()
def text(s):return re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]+>',' ',s))).strip()
def phase(y):return 'test_2017' if y==2017 else ('validation_2016' if y==2016 else 'train_dev_2011_15')
def stage(comp,roundlabel):
 x=(comp+' '+roundlabel).lower()
 if 'グループ' in x or '予選' in x:return 'group-stage'
 if '準々決勝' in x or 'quarter' in x:return 'quarterfinals'
 if '準決勝' in x or 'semi' in x:return 'semifinals'
 if '決勝' in x or 'final' in x:return 'final'
 if 'プレーオフ' in x or 'playoff' in x:return 'playoff-stage'
 return 'main-stage'
def leg(roundlabel):
 x=roundlabel
 return 'leg-1' if re.search(r'(第1戦|第１戦|1st Leg)',x) else ('leg-2' if re.search(r'(第2戦|第２戦|2nd Leg)',x) else None)
def parse_rows(blob,year):
 s=blob.decode('utf-8','replace'); rows=[]
 for tr in re.findall(r'<tr\b[^>]*>(.*?)</tr>',s,re.S|re.I):
  cells=re.findall(r'<td\b[^>]*>(.*?)</td>',tr,re.S|re.I)
  if len(cells)<8:continue
  vals=[text(x) for x in cells]
  if vals[0]!=str(year):continue
  midm=re.search(r'match_card_id=(\d+)',cells[6])
  scorem=re.search(r'(\d+)\s*[-－ー]\s*(\d+)',vals[6])
  datem=re.search(r'(\d{2})/(\d{2})/(\d{2})',vals[3])
  if not midm or not scorem or not datem:continue
  yy,mm,dd=map(int,datem.groups());date=f'{2000+yy:04d}-{mm:02d}-{dd:02d}'
  rows.append({'match_id':midm.group(1),'date':date,'competition_label':vals[1],'round_label':vals[2],
   'table_home':vals[5],'table_score':[int(scorem.group(1)),int(scorem.group(2))],'table_away':vals[7],
   'match_card_url':BASE+'/SFMS02/?match_card_id='+midm.group(1)})
 return rows
def detail(blob):
 s=blob.decode('utf-8','replace')
 names=[]
 for side in ('l','r'):
  m=re.search(r'<th\b[^>]*id="team-name-'+side+r'"[^>]*>(.*?)</th>',s,re.S|re.I);names.append(text(m.group(1)) if m else None)
 m=re.search(r'<td\b[^>]*class="time"[^>]*>(.*?)</td>',s,re.S|re.I); sums={'前半':[None,None],'後半':[None,None]}; extra=False
 if m:
  for pair in re.findall(r'<dd\b[^>]*class="left-area"[^>]*>(.*?)</dd>\s*<dt\b[^>]*>(.*?)</dt>\s*<dd\b[^>]*class="right-area"[^>]*>(.*?)</dd>',m.group(1),re.S|re.I):
   a,l,b=map(text,pair)
   if l in sums:
    try:sums[l]=[int(a),int(b)]
    except ValueError:pass
   if '延長' in l or 'extra' in l.lower():extra=True
 if any(None in z for z in sums.values()):return names,None,extra
 return names,[sums['前半'][0]+sums['後半'][0],sums['前半'][1]+sums['後半'][1]],extra
def main():
 years=[];rows=[];failures=[];detail_meta=[]
 for y in range(2011,2018):
  url=f'{BASE}/SFMS01/search?'+urllib.parse.urlencode({'competition_years':str(y),'competition_frame_ids':'11'})
  try:
   b=get(url); fn=f'leaguecup-{y}-search.html';(RAW/fn).write_bytes(b);items=parse_rows(b,y)
   years.append({'year':y,'url':url,'file':'raw/jleague-official/'+fn,'bytes':len(b),'sha256':sha(b),'events_in_search_page':len(items)})
  except Exception as e:failures.append({'year':y,'url':url,'error':str(e)});continue
  for q in items:
   try:
    b=get(q['match_card_url']); fn=f"match-{q['match_id']}.html";(RAW/fn).write_bytes(b); digest=sha(b); detail_meta.append({'match_id':q['match_id'],'url':q['match_card_url'],'file':'raw/jleague-official/'+fn,'bytes':len(b),'sha256':digest})
    team_names,s90,has_extra=detail(b); ok=s90 is not None
    hg,ag=s90 if ok else (None,None); phase_name=phase(y); st=stage(q['competition_label'],q['round_label']); lg=leg(q['round_label'])
    rows.append({'id':'jleague-official:'+q['match_id'],'competition':COMP,'stage':st+(':'+lg if lg else ''),'season':str(y),'split':phase_name,'date':q['date'],
      'home':team_names[0] or q['table_home'],'away':team_names[1] or q['table_away'],'home_goals':hg,'away_goals':ag,'neutral':None,
      'sources':[{'url':url,'sha256':years[-1]['sha256'],'match_card_url':q['match_card_url'],'match_card_sha256':digest}],
      'h2h':None,'total':None,'bookmaker':None,'market_time_basis':None,'paired_market':False,
      'score_basis':'official_match_card_first_and_second_half_sum_regulation_90' if ok else 'regulation_90_missing_official_half_scores',
      'provider_stage_label':q['competition_label'],'provider_round_label':q['round_label'],'search_table_score':q['table_score'],
      'search_table_score_matches_90':(q['table_score']==s90) if ok else None,'extra_time_detail_present':has_extra})
   except Exception as e:failures.append({'match_id':q['match_id'],'url':q['match_card_url'],'error':str(e)})
   time.sleep(.025)
 rows=sorted({r['id']:r for r in rows}.values(),key=lambda r:(r['date'],r['id']))
 (ROOT/'jpn.league_cup.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False,separators=(',',':'))+'\n' for r in rows))
 (ROOT/'jleague_cup_manifest.json').write_text(json.dumps({'provider':'J.League official Data Site','provider_url':'https://data.j-league.or.jp/SFMS01/','retrieved_at_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'scope':'J.League Levain Cup / League Cup, seasons 2011-2017','phase_policy':'2017 test; 2016 validation; 2011-2015 train/development','score_policy':'Official match-card first-half + second-half goals are used as regulation-90. Rows missing either half are retained with null score and reported; search-table end result is only a cross-check and never substituted.','yearly_search_captures':years,'match_card_captures':detail_meta,'failures':failures,'rows':len(rows),'scored_90':sum(r['home_goals'] is not None for r in rows),'unscored_90':sum(r['home_goals'] is None for r in rows)},ensure_ascii=False,indent=2)+'\n')
 print(f'J.League Cup official rows={len(rows)} scored90={sum(r["home_goals"] is not None for r in rows)}; pages={len(detail_meta)} failures={len(failures)}')
if __name__=='__main__':main()
