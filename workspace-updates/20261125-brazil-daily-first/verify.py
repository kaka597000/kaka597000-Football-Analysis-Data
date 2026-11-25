"""Reproduce the registered Brazilian local-day slate, original displayed first and same-book market."""
from hashlib import sha256
import json
from pathlib import Path
from statistics import mean
import tarfile
from zoneinfo import ZoneInfo

from research.analysis_freeze import aware, digest, verify
from research.display_delivery import delivery_request
from research_program import all_scope_model as model


ROOT = Path(__file__).resolve().parent
MID = 'espn:401841319'
BRAZIL = ZoneInfo('America/Sao_Paulo')


def checked(ok, why):
    if not ok:
        raise ValueError(why)


def unpack():
    index = json.loads((ROOT/'sources.json').read_bytes())
    packed = ROOT/'first-and-sources.tar.gz'
    checked(sha256(packed.read_bytes()).hexdigest() == index['archive_sha256'], 'archive hash differs')
    with tarfile.open(packed) as archive:
        files = {}
        for item in archive:
            checked(item.isfile() and item.name not in files, 'unexpected archive entry')
            files[item.name] = archive.extractfile(item).read()
    checked({k:sha256(v).hexdigest() for k,v in files.items()} == index['members'], 'archived evidence differs')
    return files


def confirm_form(data, board, target, kickoff, captured):
    rows = data('derived/recent-five.json')
    checked(len(rows) == 10, 'expected two sets of five original matches')
    result = {}
    for side in ('home','away'):
        espn_id = target[side]['espn_id']; fm_id = target[side]['fotmob_id']
        group = [r for r in rows if r['team_fotmob_id'] == fm_id]
        prior = sorted((g for g in board if aware(g['date']) < captured and g['status']['type']['name'] == 'STATUS_FULL_TIME'
                        and espn_id in {t['team']['id'] for t in g['competitions'][0]['competitors']}),key=lambda g:aware(g['date']), reverse=True)
        checked([r['espn_event_id'] for r in group] == [g['id'] for g in prior[:5]] and len(group) == 5, 'previous five domestic matches differ')
        for r, event in zip(group, prior[:5], strict=True):
            full = data('raw/fotmob/details/'+r['fotmob_match_id']+'.json'); h = full['header']; teams = h['teams']
            i = next(i for i,t in enumerate(teams) if str(t['id']) == fm_id)
            checked(h['status']['finished'] and h['status']['reason']['short']=='FT' and not h['status']['awarded']
                    and aware(event['date']) == aware(h['status']['utcTime']) == aware(r['kickoff_utc']) < kickoff,
                    'past result status or kickoff differs')
            goals = [t['score'] for t in teams]; scores = {t['homeAway']:int(t['score']) for t in event['competitions'][0]['competitors']}
            checked(goals==[scores['home'],scores['away']] and [r['team_goals'],r['opponent_goals']]==[goals[i],goals[1-i]], 'prior result differs')
            stats = {q['key']:q['stats'] for grp in full['content']['stats']['Periods']['All']['stats'] for q in grp['stats']}
            for dest, name in (('xg','expected_goals'),('sot','ShotsOnTarget')):
                values = stats[name]
                checked([float(r[dest+'_for']),float(r[dest+'_against'])]==[float(values[i]),float(values[1-i])], 'prior source statistic differs')
        result[side] = {k:mean(float(r[k]) for r in group) for k in ('team_goals','opponent_goals','xg_for','xg_against','sot_for','sot_against')}
    return result


def main():
    files = unpack()
    def data(name): return json.loads(files[name])
    records = {k: verify(data('records/'+k+'.json')) for k in ('registration','r10','native','authored','selected','market')}
    plan, native, authored, seats, market = (records[k] for k in ('registration','native','authored','selected','market'))
    cutoff, kickoff = aware(native['fixture']['cutoff_at']), aware(authored['fixture']['kickoff_at'])
    for raw in data('derived/source-manifest.json') + [dict(x,path='raw/fotmob/details/'+x['match_id']+'.json') for x in data('derived/fotmob-details-manifest.json')['sources']]:
        meta = data(raw['path'][:-5] + '.meta.json')
        checked(raw['http_status']==meta['http_status']==200 and raw['sha256']==meta['sha256']==sha256(files[raw['path']]).hexdigest()
                and aware(raw['query_time_utc']) <= aware(raw['retrieval_time_utc']) <= cutoff, 'invalid original source bytes or acquisition time')
    for rec in records.values():
        checked(rec['evaluation_slot']=='FIRST_PREMATCH' and rec['revision']==1 and aware(rec['recorded_at']) < kickoff,'expected original prematch first')
    checked(aware(plan['recorded_at']) <= cutoff <= aware(native['recorded_at']) <= aware(authored['recorded_at']) <= aware(seats['recorded_at']) < aware(market['recorded_at']), 'issue chronology differs')
    checked([native['track'],authored['track'],seats['track'],market['track']]==['current-test-pair','comprehensive','top3-selection','same-price-90-market-comparison-20261126'], 'issued tracks differ')
    ident = plan['payload']['identity']; summary=data('raw/espn/summary-401841319.json'); board=data('raw/espn/season-2026.json')['events']
    target = data('derived/target-event.json'); fm = data('raw/fotmob/details/5103719.json'); fm_all = data('raw/fotmob/league-2026.json')['fixtures']['allMatches']
    local_day = kickoff.astimezone(BRAZIL).date(); on_day=lambda t: aware(t).astimezone(BRAZIL).date()==local_day
    league_round = data('derived/round36-schedule.json'); db={g['id']:g for g in board}; round_fm={str(g['id']):g for g in fm_all if str(g.get('roundName'))=='36'}
    checked(len(league_round)==len(round_fm)==10 and {r['fotmob_match_id'] for r in league_round}==set(round_fm), 'round 36 fixtures differ')
    for r in league_round:
        g=db[r['espn_event_id']]; m=round_fm[r['fotmob_match_id']]; pair={t['homeAway']:t['team']['id'] for t in g['competitions'][0]['competitors']}
        checked(aware(m['status']['utcTime'])==aware(g['date'])==aware(r['kickoff_utc']) and all(r['espn_'+s+'_id']==pair[s] and r[s+'_fotmob_id']==str(m[s]['id']) for s in ('home','away')),'round team or kickoff mismatch')
    checked([g['id'] for g in board if on_day(g['date'])]==[MID[5:]] and [str(g['id']) for g in fm_all if on_day(g['status']['utcTime'])]==['5103719']
            and ident['reserved_ranks']==[MID,None,None] and ident['ordered_fixtures']==[MID] and ident['r10_first']['sha256']==records['r10']['record_sha256'], 'local-date completeness or original ranking differs')
    checked(target['espn_event_id']==MID[5:]==summary['header']['id'] and summary['header']['league']['slug']=='bra.1'
            and aware(summary['header']['competitions'][0]['date'])==aware(fm['header']['status']['utcTime'])==kickoff
            and str(fm['general']['leagueRoundName'])=='36' and not fm['header']['status']['started']
            and summary['header']['competitions'][0]['status']['type']['state']=='pre' and native['fixture']['stage']=='regular', 'target fixture identity differs')
    payload=authored['payload']; reg = data('models/registry.json')['models']['bra.1']; proof=native['payload']['execution_audit']
    checked(proof['registry_sha256']==sha256(files['models/registry.json']).hexdigest(),'native registry differs')
    for role, prefix in (('current',''),('test','test_')):
        checked(proof[role]['artifact_sha256']==reg[prefix+'artifact_sha256']==sha256(files['models/'+role+'.json']).hexdigest(), 'native artifact digest differs')
    checked(payload['team_form']==confirm_form(data,board,target,kickoff,cutoff) and payload['current_test_reference']['sha256']==native['record_sha256']
            and all(sha256(files['derived/'+k]).hexdigest()==v for k,v in payload['source_sha256'].items()),'author evidence differs')
    q=authored['fixture']['total_quote'];b=next(v for v in summary['pickcenter'] if v['provider']['name']==q['bookmaker']); decimal=lambda v: 1 + (v/100 if v>0 else 100/-v)
    odds=tuple(decimal(b[k]['moneyLine']) for k in ('homeTeamOdds','drawOdds','awayTeamOdds')); prices=(decimal(b['overOdds']),decimal(b['underOdds']))
    checked(q['quoted_at'] is None and q['line']==b['overUnder'] and (q['over_odds'],q['under_odds'])==prices
            and sha256(files['raw/espn/summary-401841319.json']).hexdigest()==q['source_sha256'], 'original same-book market differs')
    grid=model._full_market(odds,q['line'],prices); market_body=market['payload']
    checked(market_body['comprehensive_first_sha256']==authored['record_sha256'] and market_body['matrix_sha256']==digest(grid.tolist())
            and model.pick(grid,q['line'])==market_body['forecast'], 'native-price market first differs')
    issued=data('issued/firsts.json'); msg=(ROOT/'first-message.txt').read_bytes(); positions=seats['payload']['top3']; slot=positions[0]
    checked(issued['text'].encode()==msg==files['issued/message.txt'] and seats['payload']['user_facing_text'].encode()==msg
            and delivery_request(authored)['text'] in msg.decode() and sha256(msg).hexdigest()==issued['governing_text_sha256']
            and issued['planned']==seats['payload']['planned_slots']==3 and issued['occupied']==len(positions)==1 and slot['rank']==1
            and slot['match_id']==MID and slot['comprehensive_reference']['sha256']==authored['record_sha256']
            and slot['primary']==payload['primary'] and slot['top3']==payload['displayed_scores'], 'display or single reserved seat differs')
    print(json.dumps(dict(fixtures=1, rounds_checked=len(league_round), original_prior_matches=10, seats=1, planned=3, first=payload['primary'], market=market_body['forecast']),ensure_ascii=False))

if __name__=='__main__':
    main()
