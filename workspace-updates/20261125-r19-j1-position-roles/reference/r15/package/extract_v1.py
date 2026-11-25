#!/usr/bin/env python3
"""Offline-only ESPN J1 lineup extractor. No network access is performed."""
import argparse,gzip,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def load(p):
 b=Path(p).read_bytes(); return gzip.decompress(b) if str(p).endswith('.gz') else b
def sha(b):return hashlib.sha256(b).hexdigest()
def side_data(d,comp):
 rosters={str((r.get('team') or {}).get('id')):r for r in d.get('rosters',[])}
 out={}
 for c in comp.get('competitors',[]):
  side=c.get('homeAway'); team=c.get('team') or {}; tid=str(team.get('id') or c.get('id'))
  if side not in ('home','away'):continue
  roster=rosters.get(tid,{});players=[]
  for p in roster.get('roster',[]):
   a=p.get('athlete') or {}; pos=p.get('position') or a.get('position') or {}; st=p.get('starter')
   if isinstance(st,str):st=st.casefold()=='true'
   players.append({'player_id':str(a['id']) if a.get('id') is not None else None,'name':a.get('displayName') or a.get('fullName'),
    'starter':st if isinstance(st,bool) else None,'position_id':str(pos['id']) if pos.get('id') is not None else None,
    'position_group':pos.get('displayName') or pos.get('name'),'position_abbreviation':pos.get('abbreviation')})
  out[side]={'team_id':tid,'team':team.get('displayName') or team.get('name'),'score':c.get('score'),'players':players}
 return out
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--out',default=str(ROOT/'events.jsonl'));ap.add_argument('--raw-dir',default=str(ROOT/'raw/sha256'));a=ap.parse_args()
 meta={}
 for p in [ROOT/'checkpoint.jsonl',ROOT/'sources/espn-jpn1-summary-506293.meta.json',ROOT/'sources/espn-jpn1-summary-625842.meta.json']:
  if not p.exists():continue
  for line in p.read_text().splitlines():
   try:
    m=json.loads(line); h=m.get('response_sha256') or m.get('sha256')
    if h:meta[h]=m
   except Exception:pass
 rows=[]
 targets={}
 tp=ROOT/'r5-targets.jsonl'
 if tp.exists():
  for line in tp.read_text().splitlines():
   try:
    t=json.loads(line);targets[str(t['source_match_id'])]=t
   except Exception:pass
 for p in Path(a.raw_dir).glob('*.json.gz'):
  try:
   raw=gzip.decompress(p.read_bytes());d=json.loads(raw);h=sha(raw)
   if p.name != f'{h}.json.gz':raise ValueError(f'content-address mismatch: {p.name}')
   hdr=d.get('header') or {};cs=hdr.get('competitions') or []
   if not cs:continue
   c=cs[0];s=side_data(d,c);home=s.get('home',{});away=s.get('away',{});m=meta.get(h,{})
   status=((c.get('status') or {}).get('type') or {});form=d.get('format') or {};reg=form.get('regulation') or {};periods=reg.get('periods')
   eid=str(hdr.get('id') or c.get('id')); t=targets.get(eid,{})
   expected={'event_id':eid==str(t.get('source_match_id')) if t else None,
    'date':c.get('date')==t.get('date') if t else None,
    'home_id':home.get('team_id')==t.get('home_id') if t else None,
    'away_id':away.get('team_id')==t.get('away_id') if t else None,
    'home_score':str(home.get('score'))==str(t.get('home_goals')) if t else None,
    'away_score':str(away.get('score'))==str(t.get('away_goals')) if t else None}
   matchup_match=all(v is True for v in expected.values()) if t else m.get('identity_match')
   cside=[x.get('homeAway') for x in c.get('competitors',[])]; side_counts={k:cside.count(k) for k in ('home','away')}
   rside=[x.get('homeAway') for x in d.get('rosters',[])]; roster_side_counts={k:rside.count(k) for k in ('home','away')}
   def starter_rows(team):return [x for x in team.get('players',[]) if x.get('starter') is True]
   def sideaudit(team):
    st=starter_rows(team); ids=[x.get('player_id') for x in st if x.get('player_id')]
    return {'starter_count':len(st),'starter_flags_observed':sum(x.get('starter') is not None for x in team.get('players',[])),
      'starter_ids_unique':len(ids)==len(set(ids)),'starter_player_id_complete':len(ids)==len(st),'starter_positions_complete':all(x.get('position_group') for x in st)}
   ke=d.get('keyEvents') or []; explicit_et=any((x.get('period') or {}).get('number',0)>2 and not x.get('shootout') for x in ke)
   explicit_shootout=any(x.get('shootout') is True for x in ke)
   rows.append({'competition':'jpn.1','source_match_id':eid,'date':c.get('date'),
    'event_status':status.get('name'),'completed':status.get('completed'),'home_id':home.get('team_id'),'away_id':away.get('team_id'),
    'home':home.get('team'),'away':away.get('team'),'home_goals':home.get('score'),'away_goals':away.get('score'),
    'regulation_periods':periods,'regulation_final_status':status.get('completed') is True and status.get('state')=='post',
    'extra_time_indicated':True if explicit_et or (periods and periods>2) or form.get('overtime') else (False if ke else None),
    'shootout_indicated':True if explicit_shootout else (False if ke else None),
    'home_starters':starter_rows(home),'away_starters':starter_rows(away),'home_roster':home.get('players',[]),'away_roster':away.get('players',[]),
    'home_lineup_audit':sideaudit(home),'away_lineup_audit':sideaudit(away),'lineup_is_post_match_evidence':status.get('completed') is True,
    'source_url':m.get('url'),'source_query_time_utc':m.get('query_time_utc') or m.get('captured_at_utc') or m.get('attempted_at_utc'),'source_sha256':h,
    'r5_membership_verified':bool(t),'identity_source_url':t.get('scoreboard_url'),'identity_source_query_time_utc':t.get('scoreboard_query_time_utc'),
    'identity_source_sha256':t.get('scoreboard_sha256'),
    'competitor_side_counts':side_counts,'roster_side_counts':roster_side_counts,
    'duplicate_or_missing_sides':any(n!=1 for n in side_counts.values()) or any(n!=1 for n in roster_side_counts.values()),
    'target_match_audit':expected,'identity_match':matchup_match})
  except (ValueError,KeyError,OSError,TypeError):continue
 rows.sort(key=lambda x:(x.get('date') or '',x.get('source_match_id') or ''))
 with open(a.out,'w',encoding='utf-8') as f:
  for r in rows:f.write(json.dumps(r,ensure_ascii=False,separators=(',',':'))+'\n')
 print(json.dumps({'rows':len(rows),'output':a.out},ensure_ascii=False))
if __name__=='__main__':main()
