"""Bounded, read-only validation of the seven explicitly configured repository secrets.

Use existing audited provider adapters. Never persist account profiles or keys;
market adapters retain verified sports evidence in their normal format.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
import time

BINDINGS={
    'bsd':('BSD','WCPP_BSD_API_KEY'),
    'football-data':('FOOTBALLDATA','WCPP_FOOTBALL_DATA_API_KEY'),
    'infersports':('INFER','WCPP_INFERSPORTS_KEY'),
    'openfoot':('OPENFOOT','WCPP_OPENFOOT_API_KEY'),
    'the-odds-api':('THEODDSAPI','WCPP_ODDS_API_KEY'),
    '5dollar':('WCPP_5DOLLAR_API_KEY','WCPP_5DOLLAR_API_KEY'),
    'api-football':('WCPP_API_FOOTBALL_KEY','WCPP_API_FOOTBALL_KEY'),
}


def now():return datetime.now(timezone.utc).isoformat()


def write(path,value):
    body=json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)
    for _,binding in BINDINGS.values():
        secret=os.environ.get(binding)
        if secret and (secret in body or json.dumps(secret)[1:-1] in body):
            raise ValueError('credential echo rejected; value omitted')
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as f:f.write(body+'\n')


def records(response):
    if isinstance(response,list):return response
    if isinstance(response,dict):
        for key in ('response','data','results','matches','competitions','leagues'):
            if isinstance(response.get(key),list):return response[key]
    return []


def overview(response,provider,path):
    rows=records(response)
    result={'object_type':type(response).__name__,'record_count':len(rows),
            'top_level_fields':sorted(response) if isinstance(response,dict) else None,
            'sample_record_fields':sorted(rows[0]) if rows and isinstance(rows[0],dict) else None,
            'response_values_retained':'No account/profile bodies; schema and counts only'}
    if provider=='api-football' and path=='/status' and isinstance(response,dict):
        data=response.get('response',{})
        if isinstance(data,dict):
            result['subscription']={k:data.get('subscription',{}).get(k) for k in ('plan','active','end')}
            result['requests']={k:data.get('requests',{}).get(k) for k in ('current','limit_day')}
    return result


def generic_probe(provider,root,day,*,call=None,sleeper=time.sleep):
    from data_sources import clients
    call=call or clients.fetch
    secret_name,binding=BINDINGS[provider]
    result={'provider':provider,'secret_name':secret_name,'credential_bound':bool(os.environ.get(binding)),
            'calls':[],'automatic_model_ingestion':False}
    if not result['credential_bound']:
        return dict(result,status='MISSING_CREDENTIAL',requests=0)
    def request(path,params=None):
        if result['calls'] and provider in ('api-football','football-data'):sleeper(10)
        value=call(provider,path,params or {},credential_binding=binding)
        summary={'call':value['call'],'response_summary':overview(value['response'],provider,path)}
        result['calls'].append(summary);write(root/f'call-{len(result["calls"]):02}.json',summary)
        return value
    if provider=='bsd':request('/events/',{'date':day,'limit':20})
    elif provider=='openfoot':request('/matches',{'date':day})
    elif provider=='football-data':
        end=(datetime.fromisoformat(day)+timedelta(days=7)).date().isoformat()
        request('/matches',{'dateFrom':day,'dateTo':end})
    elif provider=='5dollar':
        status=request('/status')
        if status['call'].get('api_success') and not clients.service_blocked(status['call']):
            leagues=request('/leagues',{'per_page':50,'page':1})
            if leagues['call'].get('api_success') and not clients.service_blocked(leagues['call']):
                candidates=[x for x in records(leagues['response']) if isinstance(x,dict) and
                            x.get('name') in ('UEFA Nations League','England Premier League') and x.get('id')]
                candidates.sort(key=lambda x:x['name']!='UEFA Nations League')
                if candidates:
                    chosen=candidates[0];start=datetime.fromisoformat(day).replace(tzinfo=timezone.utc)
                    result['sample_competition']={k:chosen.get(k) for k in ('id','name')}
                    request('/leagues/'+str(chosen['id'])+'/fixtures',
                            {'start_time':int(start.timestamp()),'end_time':int((start+timedelta(days=7)).timestamp()),
                             'status':'all','per_page':10,'page':1,'order':'asc','include':'events,stats'})
    elif provider=='api-football':
        status=request('/status')
        if status['call'].get('api_success') and not clients.service_blocked(status['call']):
            leagues=request('/leagues',{'name':'UEFA Nations League'})
            if leagues['call'].get('api_success') and not clients.service_blocked(leagues['call']):
                exact=[x for x in records(leagues['response']) if isinstance(x,dict) and
                       x.get('league',{}).get('name')=='UEFA Nations League' and x['league'].get('id')]
                if len(exact)==1:
                    lid=exact[0]['league']['id'];result['sample_competition']=exact[0]['league']
                    fixture=request('/fixtures',{'league':lid,'season':int(day[:4]),'date':day})
                    if (not clients.service_blocked(fixture['call']) and fixture['call'].get('failure_kind')=='PROVIDER_PLAN_OR_PERMISSION_REJECTION'):
                        request('/fixtures',{'league':lid,'season':2024,'date':'2024-11-16'})
    else:raise ValueError('unsupported configured provider')
    calls=[v['call'] for v in result['calls']]
    result.update(requests=len(calls),credential_accepted=any(c.get('authenticated') is True for c in calls),
        status='RESPONSES_AVAILABLE' if any(c.get('api_success') for c in calls) else 'NO_USABLE_RESPONSE',
        scope_failures=[{'url':c['url'],'http_status':c.get('http_status'),'failure_kind':c.get('failure_kind'),
                        'error_code':c.get('error_code')} for c in calls if not c.get('api_success')])
    return result


def market_probe(provider,root,day,bundle):
    secret_name,binding=BINDINGS[provider]
    result={'provider':provider,'secret_name':secret_name,'credential_bound':bool(os.environ.get(binding)),
            'automatic_model_ingestion':False}
    if not result['credential_bound']:return dict(result,status='MISSING_CREDENTIAL',requests=0)
    if provider=='the-odds-api':
        from automation import market_snapshot as adapter
        value=adapter.collect(root,date=day.replace('-',''),market_max_age_seconds=3600)
    else:
        from automation import infer_market_snapshot as adapter
        from research.analysis_freeze import verify
        plan=verify(json.loads((Path(bundle)/'plan.json').read_text()))['payload']
        upcoming=[f for f in plan['fixtures_identity'] if f['league_level'] in ('A','C')
                  and datetime.fromisoformat(f['kickoff_at'].replace('Z','+00:00'))>datetime.now(timezone.utc)]
        if not upcoming:
            return dict(result,status='NO_SUPPORTED_FUTURE_TARGET',requests=0,credential_accepted=False)
        selected_day=min(f['kickoff_at'][:10] for f in upcoming)
        fixtures=[f for f in upcoming if f['kickoff_at'][:10]==selected_day]
        value=adapter.collect(root,fixtures,limit=100,max_events=1)
        result['requested_fixture_date_utc']=selected_day
        result['fixture_sampling_limit']=1
    result.update({k:v for k,v in value.items() if k not in ('snapshots','identity_mappings','identity_alias_review')})
    result['source_time_inferred']=False
    rows=[r for s in value.get('snapshots',[]) for r in s['observations']]
    result['markets']=sorted({r['value']['market'] for r in rows})
    result['bookmakers']=sorted({r['value']['bookmaker'] for r in rows})
    times=sorted(r['value']['quoted_at'] for r in rows)
    result['quote_time_range']=[times[0],times[-1]] if times else None
    result['coverage_by_market']={market:len({r['match_id'] for r in rows if r['value']['market']==market})
                                  for market in result['markets']}
    evidence=Path(root)/('odds.json' if provider=='the-odds-api' else 'events.json')
    result['protected_response_retained']=evidence.is_file()
    result['credential_accepted']=evidence.is_file() and value.get('status') not in ('MISSING_CREDENTIAL','COLLECTION_FAILED')
    result['quota_headers_retained']=False
    result['quota_remaining']=None
    return result


def run(code,state,out,day):
    code=Path(code).resolve();sys.path.insert(0,str(code));sys.path.insert(0,str(code/'runtime'))
    state=Path(state).resolve();out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    results={}
    def one(provider):
        root=out/provider
        try:
            value=(market_probe(provider,root,day,state/'future/nations-repair-bundle')
                   if provider in ('infersports','the-odds-api') else generic_probe(provider,root,day))
            write(out/(provider+'-summary.json'),value);return value
        except Exception as exc:
            value={'provider':provider,'secret_name':BINDINGS[provider][0],
                   'credential_bound':bool(os.environ.get(BINDINGS[provider][1])),
                   'status':'PROBE_ERROR','error_type':type(exc).__name__,'automatic_model_ingestion':False}
            write(out/(provider+'-summary.json'),value);return value
    with ThreadPoolExecutor(max_workers=7) as executor:
        tasks={executor.submit(one,p):p for p in BINDINGS}
        for task in as_completed(tasks):results[tasks[task]]=task.result()
    summary={'schema':'WCPP-CONFIGURED-API-VERIFICATION-1','completed_at':now(),'fixture_date_utc':day,
             'providers':results,'automatic_model_promotion':False,'tls_verification_disabled':False,
             'scope':'bounded authenticated endpoints and actual data samples; not all-competition certification'}
    write(out/'summary.json',summary)
    for provider,value in sorted(results.items()):
        print(json.dumps({'provider':provider,'secret_name':value['secret_name'],'status':value['status'],
                          'credential_bound':value['credential_bound'],'verified_quote_count':value.get('verified_quote_count')}))
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--code',required=True);p.add_argument('--state',required=True)
    p.add_argument('--out',required=True);p.add_argument('--date',default=datetime.now(timezone.utc).date().isoformat())
    a=p.parse_args();datetime.strptime(a.date,'%Y-%m-%d');run(a.code,a.state,a.out,a.date)
