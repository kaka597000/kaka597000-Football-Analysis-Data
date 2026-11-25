"""Independently reconcile the German club dossier with the registered ids and original responses."""
from collections import Counter, defaultdict
import csv
from datetime import datetime
from decimal import Decimal
from functools import lru_cache
import gzip
from hashlib import sha256
from html import unescape
from io import StringIO
import json
from pathlib import Path, PurePosixPath
import re
import tarfile

HERE = Path(__file__).resolve().parent
SCOPES = ('all_competitions', 'bundesliga')
FIELDS = ('ft90_for','ft90_against','xg_for','xg_against','sot_for','sot_against')
NORMALIZED = ('availability.csv','club-status.csv','coverage.json','delivery.json','fixtures-coverage.csv',
              'last-five-fixtures.csv','last-five-metrics.csv','medical-news.json','nine-fixtures.jsonl',
              'prices.csv','projected-lineups.csv')


def check(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(value):
    return sha256(value).hexdigest()


def signature(record):
    body = {k:v for k,v in record.items() if k!='record_sha256'}
    return sha(json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode())


def at(value):
    d = datetime.fromisoformat(value)
    check(d.utcoffset() is not None, 'unknown time zone')
    return d


def csv_rows(value):
    return list(csv.DictReader(StringIO(value.decode('utf-8-sig'))))


def source_reader(read):
    metas = [json.loads(v) for v in read('source-manifest.jsonl').splitlines()]
    by_key = {m['key']:m for m in metas}
    check(len(by_key)==len(metas), 'duplicate source label')
    @lru_cache(maxsize=8)
    def body(mpath, expected):
        data = gzip.decompress(read(mpath))
        check(sha(data)==expected, 'original response '+mpath)
        return data
    for m in metas:
        if m.get('requested_utc') and m.get('received_utc'):
            check(at(m['requested_utc'])<=at(m['received_utc']), 'invalid collection interval')
        if m.get('raw_path'):
            check(m['raw_path']=='raw/'+m['sha256']+'.gz' and len(body(m['raw_path'],m['sha256']))==m['bytes'],
                  'content-addressed source')
    @lru_cache(maxsize=12)
    def doc(key):
        m = by_key[key]
        check(m['http_status']==200, 'unavailable data was used: '+key)
        b = body(m['raw_path'],m['sha256'])
        return json.loads(gzip.decompress(b) if b.startswith(b'\x1f\x8b') else b)
    return by_key, doc


def raw_metrics(match, reference, evidence):
    """Return regulation scores and team stats. Penalties/extra time do not enter the totals."""
    h = match['header']
    status = h['status']
    check(status['finished'] and not status.get('cancelled') and not status.get('awarded'), 'history final status')
    if status['reason']['short']=='FT':
        score = [t['score'] for t in h['teams']]
        periods = ['All']
    else:
        final, = [v for v in match['content']['matchFacts']['events']['events'] if v.get('type')=='Half'
                  and v.get('time')==90 and v.get('halfStrShort')=='FT']
        score = [final['homeScore'],final['awayScore']]
        periods = ['FirstHalf','SecondHalf']
    stats = match['content'].get('stats',{}).get('Periods',{})
    values = {'ft90':score}
    for field,raw_key in (('xg','expected_goals'),('sot','ShotsOnTarget')):
        per_side=[]
        for side in (0,1):
            numbers=[]
            for per in periods:
                vals={Decimal(str(s['stats'][side])) for group in (stats.get(per) or {}).get('stats',[])
                      for s in group['stats'] if s['key']==raw_key and s['stats'][side] not in (None,'','-')}
                check(len(vals)<=1, 'conflicting raw stat')
                if vals:
                    numbers.append(vals.pop())
            per_side.append(float(sum(numbers)) if len(numbers)==len(periods) else None)
        values[field]=per_side
    es = reference['espn']
    board = evidence(es['source']['key'])
    if 'events' in board:
        e, = [e for e in board['events'] if e['id']==es['espn_event_id']]
        c, = e['competitions']
    else:
        c, = board['header']['competitions']
    check(str(c['id'])==es['espn_event_id'] and at(c['date'])==at(status['utcTime']) and c['status']['type']['completed'],
          'second full-time source')
    competitors = {t['homeAway']:t for t in c['competitors']}
    check(all(str(competitors[s]['id'])==es[s+'_id'] for s in ('home','away')), 'ESPN historical clubs')
    if c['status']['type']['name']=='STATUS_FULL_TIME':
        dual = [int(competitors[s]['score']) for s in ('home','away')]
    elif c['status']['type']['name'] in ('STATUS_FINAL_AET','STATUS_FINAL_PEN','STATUS_FULL_TIME_EXTRA_TIME'):
        dual = [sum(int(v['displayValue']) for v in competitors[s]['linescores'][:2]) for s in ('home','away')]
    else:
        dual = None
    check(es['ft90']==dual and reference['score_crosschecked']==(score==dual) and
          all(values[k]==reference[k] for k in values), 'original regulation score, xG or shots on target')
    return values


def histories(read, registry, teams, sources, doc, cutoff):
    catalog = json.loads(read('history-fixtures.json'))
    rows = csv_rows(read('last-five-fixtures.csv'))
    projection = {(r['fotmob_team_id'],r['scope'],int(r['recency'])):r for r in rows}
    agg_rows = csv_rows(read('last-five-metrics.csv'))
    aggs = {(r['fotmob_team_id'],r['scope']):r for r in agg_rows}
    check(len(projection)==len(rows) and len(aggs)==len(agg_rows), 'duplicate normalized history rows')
    original={}
    seen=set()
    counts={s:Counter() for s in SCOPES}
    for team,r in teams.items():
        mid = 'espn:'+r['target_event_id']
        signed = registry['payload']['fixtures'][mid]
        check('espn:'+r['espn_team_id'] in (signed['home'],signed['away']), 'historical team ID')
        calendar = doc(r['load']['team_calendar']['key'])
        check(str(calendar['details']['id'])==team and calendar['details']['primaryLeagueId']==54, 'club calendar')
        completed = [g for g in calendar['fixtures']['allFixtures']['fixtures'] if g['status'].get('finished')
                     and not (g['status'].get('cancelled') or g['status'].get('awarded'))
                     and 'friendl' not in g['tournament']['name'].lower() and at(g['status']['utcTime'])<cutoff]
        completed.sort(key=lambda g:(at(g['status']['utcTime']),int(g['id'])), reverse=True)
        for scope in SCOPES:
            selected=[g for g in completed if scope=='all_competitions' or g['tournament']['leagueId']==54][:5]
            team_rows = r[scope]['matches']
            check(len(team_rows)==len(selected)==5 and [v['fotmob_id'] for v in team_rows]==[str(g['id']) for g in selected],
                  'chronological previous five '+team+scope)
            stats=defaultdict(list)
            for sequence,(g,v) in enumerate(zip(selected,team_rows),1):
                hist=str(g['id'])
                ref=catalog[hist]
                row=projection[team,scope,sequence]
                if hist not in original:
                    match=doc(ref['source']['key'])
                    check(str(match['general']['matchId'])==hist and
                          [str(t['id']) for t in match['header']['teams']]==[ref['home_id'],ref['away_id']] and
                          at(match['header']['status']['utcTime'])==at(ref['kickoff_utc']), 'historical match key')
                    original[hist]=raw_metrics(match,ref,doc)
                side=0 if ref['home_id']==team else 1
                check(team in (ref['home_id'],ref['away_id']) and row['fotmob_id']==hist and
                      row['espn_match_id']==r['target_event_id'] and row['fotmob_match_id']==r['target_fotmob_id']
                      and row['espn_event_id']==ref['espn']['espn_event_id'] and at(row['kickoff_utc'])==at(ref['kickoff_utc'])
                      and row['fotmob_sha256']==sources[ref['source']['key']]['sha256'] and
                      row['espn_sha256']==sources[ref['espn']['source']['key']]['sha256'] and
                      row['fotmob_received_utc']==sources[ref['source']['key']]['received_utc'] and
                      row['espn_received_utc']==sources[ref['espn']['source']['key']]['received_utc'] and
                      max(at(row[k]) for k in ('fotmob_received_utc','espn_received_utc'))<at(signed['kickoff_at']) and
                      (row['score_crosschecked']=='True')==ref['score_crosschecked'], 'historical source identity')
                for col in FIELDS:
                    metric, direction=col.split('_')
                    val=original[hist][metric][side if direction=='for' else 1-side]
                    check((float(row[col]) if row[col] else None)==v[col]==val, 'raw team stat '+col)
                    if val is not None:
                        stats[col].append(val)
                seen.add(hist)
                counts[scope]['slots']+=1
                counts[scope]['dual_ft90']+=int(ref['score_crosschecked'])
                for field in ('xg','sot'):
                    counts[scope][field+'_for_and_against']+=int(None not in original[hist][field])
            for col in FIELDS:
                vals=stats[col]
                for k,expect in [('available',len(vals)),('total',round(sum(vals),3) if vals else None),
                                 ('mean',round(sum(vals)/len(vals),3) if vals else None)]:
                    value=aggs[team,scope][col+'_'+k]
                    check((float(value) if value else None)==expect, 'last-five aggregate')
    check(len(rows)==len(teams)*len(SCOPES)*5 and len(aggs)==len(teams)*len(SCOPES) and seen==catalog.keys(),
          'full team/history denominators')
    return len(seen), counts


def personnel(read, registry, fields, sources, doc):
    profiles=json.loads(read('match-personnel.json'))
    avail_rows=csv_rows(read('availability.csv'))
    projected_rows=csv_rows(read('projected-lineups.csv'))
    absences={(r['espn_match_id'],r['side'],r['fotmob_person_id']):r for r in avail_rows}
    projs={(r['espn_match_id'],r['side'],r['dfl_player_id']):r for r in projected_rows}
    check(len(absences)==len(avail_rows) and len(projs)==len(projected_rows),'duplicate personnel row')
    found, listed, notes, conflicts, statuses = set(),set(),Counter(),[],[]
    for mid,f in fields.items():
        signed=registry['payload']['fixtures']['espn:'+mid]
        p=profiles[mid]
        kickoff=at(signed['kickoff_at'])
        target=doc('fotmob-target-'+p['fotmob_match_id'])
        summary=doc('espn-refresh-'+mid)
        comp,=summary['header']['competitions']
        check(comp['id']==mid and at(comp['date'])==at(target['header']['status']['utcTime'])==kickoff
              and target['general']['parentLeagueId']==54 and str(target['general']['matchId'])==p['fotmob_match_id']==f['fotmob_source_match_id'],
              'target lineups/availability identity')
        for side,t in p['sides'].items():
            tid=t['fotmob_team_id']
            raw_team=(target['content'].get('lineup') or {}).get(side+'Team') or {}
            check(tid==f['fotmob_'+side+'_id']==str(target['general'][side+'Team']['id'])
                  and (not raw_team or str(raw_team['id'])==tid) and 'espn:'+t['espn_team_id']==signed[side],
                  'source personnel team')
            a=t['reported_unavailable_source']
            source=sources[a['key']]
            check(a['sha256']==source['sha256'] and at(source['received_utc'])<kickoff, 'availability provenance')
            rawlist=raw_team.get('unavailable')
            league=t.get('projected_XI') or {}
            lineup_source=league.get('api')
            if lineup_source is None:
                # The official DFL match endpoint is still indexed even when its predicted XI is not published.
                lineup_source=next((v for v in sources.values() if v.get('http_status')==200 and
                                   p['dfl_match_id'] in v['url'] and v['url'].rstrip('/').endswith('/lineup')),None)
            api=(doc(lineup_source['key']).get(side) or {}) if lineup_source else {}
            if lineup_source:
                check(p['dfl_match_id'] in lineup_source['url'] and
                      sources[lineup_source['key']]['sha256']==lineup_source['sha256'] and at(lineup_source['received_utc'])<kickoff,
                      'DFL match-specific lineup source')
            posted=api.get('startingElevenPredicted') or {}
            projected=posted.get('persons') or []
            check(len(projected)==len(league.get('persons') or []), 'published/unpublished predicted count')
            for player in projected:
                k=(mid,side,player['dflDatalibraryObjectId'])
                csvrow=projs[k]
                check(csvrow['classification']==league['status']=='league_published_prediction'
                      and csvrow['official_matchday_confirmed']=='False' and csvrow['player']==player['name']
                      and csvrow['sha256']==lineup_source['sha256'] and csvrow['provider_updated_at']==posted['lastUpdateDateTime']
                      and at(csvrow['provider_updated_at'])<=at(lineup_source['received_utc'])<kickoff, 'league projection provenance')
                found.add(k)
            projected_fm={str(z.get('fotmob_player_id')) for z in league.get('persons',[]) if z.get('fotmob_player_id')}
            confirmed=(api.get('startingElevenConfirmed') or api.get('startingEleven') or {}).get('persons') or []
            esp_teams=[v for v in summary.get('rosters',[]) if str((v.get('team') or {}).get('id'))==t['espn_team_id']]
            esp_confirmed=[v for group in esp_teams for v in group.get('roster',[]) if v.get('starter') is True]
            check(bool(t.get('confirmed_matchday_XI'))==bool(confirmed or esp_confirmed), 'official release status')
            esp_bench=[v for group in esp_teams for v in group.get('roster',[]) if v.get('starter') is False]
            documented_squad=bool(api.get('matchdaySquad') or (confirmed and (api.get('substitutes') or api.get('substitutesConfirmed')))
                                  or (esp_confirmed and esp_bench))
            check(bool(t.get('confirmed_matchday_squad'))==documented_squad, 'published/unpublished matchday squad')
            raw_ids=[str(v['id']) for v in (rawlist or [])]
            normalized={v['fotmob_player_or_staff_id']:v for v in t['reported_unavailable']}
            check(len(raw_ids)==len(set(raw_ids)) and set(raw_ids)==normalized.keys(), 'complete provider absence list')
            for v in rawlist or []:
                key=(mid,side,str(v['id']))
                export=absences[key]
                full=normalized[key[2]]
                check(export['person']==v['name']==full['name'] and json.loads(export['provider_raw_detail'])==v['unavailability']
                      and export['provider_category']==v['unavailability']['type'] and export['sha256']==a['sha256']
                      and export['role']==full['person_role'] and export['provider_expected_return']==str(v['unavailability'].get('expectedReturn') or ''),
                      'raw availability category and reported return')
                overlap=key[2] in projected_fm
                check((export['also_projected']=='True')==overlap==full['also_in_projected_XI'],'conflicting sources retained')
                if overlap:
                    conflicts.append(export['person'])
                notes[export['role']+'_'+export['provider_category']]+=1
                listed.add(key)
            direct_pages=set()
            for article in t['article_notes']:
                ref=article['source']
                m=sources[ref['key']]
                check(ref['sha256']==m['sha256'] and ref['url']==m['url'] and at(m['received_utc'])<kickoff,
                      'club, federation or secondary note provenance')
                if article['publisher']=='official_source' and article['scope'] in ('target_match_preview','target_preparation'):
                    direct_pages.add(ref['key'])
            statuses.append(dict(match_id='espn:'+mid,side=side,team=t['name'],fotmob_team_id=tid,
                                 dfl_predicted_people=len(projected),confirmed_xi=bool(confirmed or esp_confirmed),
                                 confirmed_matchday_squad=bool(t.get('confirmed_matchday_squad')),
                                 fotmob_availability=('unpublished' if rawlist is None else 'published' if rawlist else 'published_empty'),
                                 named_unavailable_reports=len(raw_ids),direct_target_preview_or_preparation_pages=len(direct_pages),
                                 source_sha256=a['sha256']))
    check(profiles.keys()==fields.keys() and found==projs.keys() and listed==absences.keys(), 'personnel denominators')
    return statuses,notes,conflicts


def medical_reports(read, sources, teams, registry):
    def plain(value):
        return ' '.join(re.sub(r'<[^>]*>', ' ', unescape(value)).split()).casefold()
    articles=json.loads(read('medical-news.json'))
    for item in articles:
        note=item['source']
        m=sources[note['key']]
        club=teams[item['team_fotmob_id']]
        kickoff=at(registry['payload']['fixtures']['espn:'+club['target_event_id']]['kickoff_at'])
        body=gzip.decompress(read(m['raw_path']))
        check(sha(body)==m['sha256']==note['sha256'] and note['url']==m['url'] and at(m['received_utc'])<kickoff,
              'secondary article source')
        text=plain((gzip.decompress(body) if body.startswith(b'\x1f\x8b') else body).decode('utf-8',errors='replace'))
        check(item['source_role'].startswith('secondary') and plain(item['title_original']) in text and
              all(plain(line)[:45] in text for line in item['body_original'] if plain(line)), 'secondary article text')
        published=item.get('publication_as_supplied')
        if published and len(published)>10:
            check(at(published)<=at(m['received_utc']), 'article publication clock')
    return len(articles)


def verify_bundle(read):
    regdir=HERE.parent/'registration'
    plan=json.loads((regdir/'plan.json').read_bytes())
    reg_bytes=(regdir/plan['file']).read_bytes()
    reg=json.loads(reg_bytes)
    check(signature(reg)==plan['sha256']==reg['record_sha256'] and reg['revision']==1 and not reg['previous_sha256']
          and read('registration/'+plan['file'])==reg_bytes,'original first registration')
    nine=json.loads(read('registered-nine.json'))
    fields={r['espn_source_match_id']:r for r in nine['fixtures']}
    joined=read('registration/first-window-40.jsonl')
    pool=[json.loads(v) for v in joined.splitlines()]
    check(sha(joined)==nine['join_file_sha256'] and len(pool)==40 and
          {r['espn_source_match_id']:r for r in pool if r['competition']=='ger.1'}==fields, 'original four-league identity join')
    early,=(HERE.parent/'early-prices').glob('*.tar.gz')
    check(sha(read('companion/'+early.name))==sha(early.read_bytes()), 'same early control as the published archive')
    ids=reg['payload']['identity']['slates']['nov27_dec04']
    check(['espn:'+k for k in fields]==ids and len(ids)==len(set(ids))==9 and
          nine['record_sha256']==reg['record_sha256'],'full registered first window')
    sources,doc=source_reader(read)
    teams=json.loads(read('team-last-five.json'))
    check(set(teams)=={r['fotmob_'+s+'_id'] for r in fields.values() for s in ('home','away')} and len(teams)==18,
          '18 registered clubs')
    cutoff=at(json.loads(read('execution.json'))['snapshot_started_utc'])
    check(at(reg['recorded_at'])<=cutoff<min(at(r['kickoff_utc']) for r in fields.values()), 'registered prospective history cutoff')
    distinct,hist=histories(read,reg,teams,sources,doc,cutoff)
    statuses,availability,conflicts=personnel(read,reg,fields,sources,doc)
    known_intervening=csv_rows((HERE.parent/'market-checkpoints/intervening-competitions.csv').read_bytes())
    original_intervening={(r['target'],r['event'],at(r['kickoff_bjt'])) for r in known_intervening}
    current_intervening={('espn:'+t['target_event_id'],'fotmob:'+v['fotmob_id'],at(v['kickoff_utc']))
                         for t in teams.values() for v in t['load']['scheduled_before_target']}
    check(current_intervening==original_intervening, 'intervening games from the existing #57 calendar')
    markets=json.loads(read('markets.json'))
    for mid in fields:
        first=markets[mid]['signed_R5']
        for ref in (first,first['source_contract_record']):
            raw=read(ref['file'])
            record=json.loads(raw)
            registered=reg['payload']['fixtures']['espn:'+mid]
            check(sha(raw)==ref['file_sha256'] and record['record_sha256']==ref['record_sha256']==signature(record)
                  and record['previous_sha256'] is None and record['revision']==1 and record['match_id']=='espn:'+mid
                  and all(record['fixture'][s]==registered[s] for s in ('home','away'))
                  and at(record['recorded_at'])<at(record['fixture']['kickoff_at'])==at(registered['kickoff_at']),
                  'existing R5 first or its source-contract record')
    cov=json.loads(read('coverage.json'))
    check(cov['early_infersports_companion']==json.loads((HERE.parent/'early-prices/readback.json').read_bytes()),
          'early observation metrics and source times')
    check((len(fields),len(teams),distinct,len(markets))==(cov['fixtures'],cov['teams'],cov['unique_historical_fixtures'],cov['verified_signed_R5_firsts'])
          and hist==cov['history'] and availability==cov['availability'] and sorted(conflicts)==sorted(cov['simultaneous_predicted_and_reported_unavailable'])
          and sum(s['dfl_predicted_people'] for s in statuses)==cov['dfl_projected']
          and sum(s['confirmed_xi'] for s in statuses)==cov['confirmed_matchday_xi_teams']
          and sum(s['confirmed_matchday_squad'] for s in statuses)==cov['confirmed_matchday_squad_teams'],'independent dossier counts')
    check(len(current_intervening)==cov['pending_intermediate_fixtures'] and
          len(sources)==cov['source_response_or_attempts'] and sum(bool(v.get('raw_path')) for v in sources.values())==cov['with_raw_bytes'],
          'source and intervening denominators')
    check(medical_reports(read,sources,teams,reg)==cov['secondary_medical_articles'], 'secondary evidence coverage')
    return statuses,dict(fixtures=len(fields),clubs=len(teams),unique_history=distinct,history=hist,
                         signed_R5=len(markets),named_availability=availability,conflicts=conflicts)


def status_csv(rows):
    out=StringIO(newline='')
    writer=csv.DictWriter(out,fieldnames=list(rows[0]),lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode()


def main():
    index=json.loads((HERE/'bundle.json').read_bytes())
    archive=HERE/index['archive']
    check(sha(archive.read_bytes())==index['sha256'] and archive.stat().st_size==index['bytes'], 'Dalton archive SHA')
    check((HERE/(archive.name+'.sha256')).read_text()==index['sha256']+'  '+archive.name+'\n','detached handoff SHA')
    members={}
    with tarfile.open(archive,'r|*') as tar:
        for m in tar:
            if m.isdir():
                continue
            path=PurePosixPath(m.name)
            check(m.isfile() and not path.is_absolute() and '..' not in path.parts and m.name not in members,'archive member')
            members[m.name]=tar.extractfile(m).read()
    marker,=[p for p in members if PurePosixPath(p).name=='registered-nine.json']
    root=marker.removesuffix('registered-nine.json')
    def read(name):
        return members[root+name]
    sums=read('SHA256SUMS')
    lines=sums.decode('utf-8').splitlines()
    pinned={name:h for h,name in (line.split('  ',1) for line in lines)}
    check(sha(sums)==index['upstream_member_manifest_sha256'] and len(lines)==len(pinned) and
          len(members)==index['member_count'] and set(members)=={root+'SHA256SUMS'}|{root+n for n in pinned}
          and all(sha(read(n))==expected for n,expected in pinned.items()), 'all delivered archive members')
    check(sha(read('source-manifest.jsonl'))==index['upstream_source_manifest_sha256'], 'source manifest pin')
    statuses,metrics=verify_bundle(read)
    receipt=json.loads(read('registration/plan.json'))
    check(index['independent_readback']==metrics and index['registration_id']==receipt['id']
          and index['registration_record_sha256']==receipt['sha256'],'delivery receipt metrics and plan')
    check(set(index['normalized_sha256'])==set(NORMALIZED),'complete normalized file inventory')
    for name,expected in index['normalized_sha256'].items():
        content=status_csv(statuses) if name=='club-status.csv' else read(name)
        check(content==(HERE/name).read_bytes() and sha(content)==expected,'normalized evidence '+name)
    print(json.dumps(metrics,ensure_ascii=False,sort_keys=True))


if __name__=='__main__':
    main()
