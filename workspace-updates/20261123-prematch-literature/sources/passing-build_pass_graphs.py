#!/usr/bin/env python3
"""Build strictly adjacent, same-team successful-pass graph snapshots from Wyscout 2017/18."""
import collections, datetime, hashlib, json, math, pathlib, re

BASE = pathlib.Path('/workspace/WCPP/reports/kpi-optimization-20261123-r4/events')
RAW = BASE / 'raw'
OUT = pathlib.Path(__file__).resolve().parent
LEAGUES = {
    'England': ('eng.1', 'E0'), 'Spain': ('esp.1', 'SP1'), 'Germany': ('ger.1', 'D1'),
    'Italy': ('ita.1', 'I1'), 'France': ('fra.1', 'F1'),
}
COMP_IDS = {'eng.1': 364, 'esp.1': 795, 'ger.1': 426, 'ita.1': 524, 'fra.1': 412}

def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()

def stats_for(evs, team_id):
    passes=[(i,e) for i,e in enumerate(evs) if e.get('eventName')=='Pass' and int(e.get('teamId',-1))==team_id]
    counts=collections.Counter(); edge_positions=collections.defaultdict(list)
    for i,e in passes:
        tags={x['id'] for x in e.get('tags',[])}
        if 1801 not in tags or i+1>=len(evs): continue
        n=evs[i+1]
        if (n.get('matchPeriod') != e.get('matchPeriod') or n.get('teamId') != e.get('teamId')
            or not n.get('playerId') or not e.get('playerId') or int(n['playerId'])==int(e['playerId'])): continue
        a,b=int(e['playerId']),int(n['playerId']); counts[(a,b)]+=1
        ps=e.get('positions') or []; ns=n.get('positions') or []
        if ps and len(ps)>1:
            # Retain actual pass origin/destination and the inferred receiver action location.
            edge_positions[(a,b)].append({'pass_from':[ps[0].get('x'),ps[0].get('y')],
              'pass_to':[ps[-1].get('x'),ps[-1].get('y')],
              'inferred_receiver_event_start':[ns[0].get('x'),ns[0].get('y')] if ns else None})
    nodes=sorted({x for ab in counts for x in ab}); m=sum(counts.values()); out=collections.Counter(); inc=collections.Counter()
    for (a,b),w in counts.items(): out[a]+=w; inc[b]+=w
    active=len(nodes); norm_entropy=[]
    for node in nodes:
        degree=out[node]
        if degree:
            h=-sum((w/degree)*math.log(w/degree) for (a,_),w in counts.items() if a==node)
            norm_entropy.append(h/math.log(active) if active>1 else 0.0)
    reciprocal=sum(min(w,counts.get((b,a),0)) for (a,b),w in counts.items())/m if m else None
    coords=[p for arr in edge_positions.values() for p in arr if p['pass_from'][0] is not None and p['pass_to'][0] is not None]
    forward=sum(p['pass_to'][0]>p['pass_from'][0] for p in coords)/len(coords) if coords else None
    final=sum(p['pass_to'][0]>=66.67 for p in coords)/len(coords) if coords else None
    return {
      'pass_volume':len(passes), 'successful_passes':sum(1 for _,e in passes if 1801 in {x['id'] for x in e.get('tags',[])}),
      'eligible_edge_count':m, 'active_nodes':active, 'density':(len(counts)/(active*(active-1))) if active>1 else 0.0,
      'weighted_outgoing_entropy_normalized':(sum(norm_entropy)/len(norm_entropy)) if norm_entropy else None,
      'largest_sender_share':max(out.values())/m if m else None, 'largest_receiver_share':max(inc.values())/m if m else None,
      'reciprocity':reciprocal, 'forward_edge_share':forward, 'final_third_edge_share':final,
      'coordinate_definition':'forward means numeric x increases; final third means pass destination x>=66.67; coordinate orientation retained as source-native',
      'edges':[{'from_player_id':a,'to_player_id':b,'weight':w,'recipient_inference':'next_adjacent_event_same_team_player','positions':edge_positions.get((a,b),[])} for (a,b),w in sorted(counts.items())]
    }

def main():
    manifest=json.load(open(BASE/'source-manifest.json',encoding='utf8'))
    byname={x['file'].split('/')[-1]:x for x in manifest['files']}
    teams={int(x['wyId']):x['name'] for x in json.load(open(RAW/'teams.json',encoding='utf8'))}
    fd={}
    for line in open(BASE/'events.jsonl',encoding='utf8'):
        x=json.loads(line)
        m=re.search(r'source match ID (\d+)',x.get('source',{}).get('event_source',''))
        if m: fd[int(m.group(1))]=x
    srcs=['teams.json','competitions.json','eventid2name.csv','tags2name.csv','source-manifest.json','build_events.py']
    for country,(competition,_) in LEAGUES.items():
        mf='matches_'+country+'.json'; ef='events_'+country+'.json'
        matches=json.load(open(RAW/mf,encoding='utf8')); events=json.load(open(RAW/ef,encoding='utf8'))
        grouped=collections.defaultdict(list)
        for e in events: grouped[int(e['matchId'])].append(e)
        out=[]
        for m in matches:
            if m.get('status')!='Played' or m.get('duration')!='Regular': continue
            sides={v['side']:int(v['teamId']) for v in m['teamsData'].values()}
            if 'home' not in sides or 'away' not in sides: continue
            evs=grouped.get(int(m['wyId']),[]); mt=fd.get(int(m['wyId']),{})
            dt=datetime.datetime.strptime(m['dateutc'],'%Y-%m-%d %H:%M:%S').replace(tzinfo=datetime.timezone.utc)
            home,away=sides['home'],sides['away']
            out.append({'competition':competition,'id':{'namespace':'wyscout','value':int(m['wyId'])},'football_data_match_id':mt.get('match_id'),
              'date':{'utc':dt.isoformat().replace('+00:00','Z'),'beijing':dt.astimezone(datetime.timezone(datetime.timedelta(hours=8))).isoformat()},
              'home':{'name':teams.get(home),'id':home},'away':{'name':teams.get(away),'id':away},
              'score_90':{'home':int(m['teamsData'][str(home)]['score']),'away':int(m['teamsData'][str(away)]['score'])},'stage':'regular',
              'home_stats':stats_for(evs,home),'away_stats':stats_for(evs,away),
              'source_sha256':{'events':byname[ef]['sha256'],'matches':byname[mf]['sha256'],'teams':byname['teams.json']['sha256'],'catalog':byname['competitions.json']['sha256'],'event_catalog':byname['eventid2name.csv']['sha256'],'tag_catalog':byname['tags2name.csv']['sha256'],'extraction_script':sha(pathlib.Path(__file__))},
              'score_provenance':'Wyscout matches teamsData.score; duration=Regular; stage regular'})
        with open(OUT/'graph-matches.jsonl','a' if country!='England' else 'w',encoding='utf8') as f:
            for x in out: f.write(json.dumps(x,ensure_ascii=False,separators=(',',':'))+'\n')
        print(country,len(out),sum(x['home_stats']['eligible_edge_count']+x['away_stats']['eligible_edge_count'] for x in out))
    print('output sha256',sha(OUT/'graph-matches.jsonl'))

if __name__=='__main__': main()
