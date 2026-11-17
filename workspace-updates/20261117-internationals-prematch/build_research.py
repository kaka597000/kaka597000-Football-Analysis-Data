"""Reproducible one-off friendly research; no active model or registry writes."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
from scipy.optimize import least_squares


def read(p):
    return json.loads(Path(p).read_text())


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def write(p, value):
    with Path(p).open('x') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', required=True)
    ap.add_argument('--root', default=str(Path(__file__).parent))
    ap.add_argument('--assets', default='/workspace/WCPP')
    a = ap.parse_args()
    root, assets, source = Path(a.root), Path(a.assets), Path(a.source)
    sys.path.insert(0, str(source/'runtime'))
    from v2.model import digest, aware, validate_history, fit_strength, rates, matrix, probabilities, total_settlement, research_predict
    from prediction_engine import predict_models
    from research.score_distribution_audit import audit_prediction

    derived = root/'derived'
    derived.mkdir(exist_ok=False)
    cutoff = datetime.now(timezone.utc).isoformat()
    old_rows = read(assets/'data/v2/fifa.friendly-history.json')
    retained = read(assets/'reports/model-upgrade-v2/fifa.friendly-artifact.json')
    assert digest(validate_history(old_rows)) == retained['dataset_hash']
    shutil.copy2(assets/'data/v2/fifa.friendly-history.json', derived/'retained-history.json')
    shutil.copy2(assets/'reports/model-upgrade-v2/fifa.friendly-artifact.json', derived/'retained-artifact.json')
    rows = {r['match_id']: r for r in old_rows}
    edits, completed = [], {}
    aliases = {'China PR': 'China', 'USA': 'United States', 'United States of America': 'United States', 'Korea Republic': 'South Korea'}
    for path in sorted((root/'team-evidence').glob('espn-*-schedule-raw.json')):
        meta = read(path.with_name(path.name.replace('-raw', '-meta')))
        assert sha(path) == meta['sha256'] and aware(meta['query_time_utc']) <= aware(cutoff)
        body = read(path)
        for event in body['events']:
            c = event['competitions'][0]
            if not c['status']['type'].get('completed'):
                continue
            assert c['status']['type']['name'] == 'STATUS_FULL_TIME', c['status']
            assert aware(event['date']) < aware(cutoff)
            sides = {t['homeAway']: t for t in c['competitors']}
            home, away = sides['home']['team']['displayName'], sides['away']['team']['displayName']
            scores = [sides[x]['score']['value'] for x in ('home', 'away')]
            assert all(float(s).is_integer() and 0 <= s <= 30 for s in scores)
            venue = c.get('venue', {})
            country = venue.get('address', {}).get('country')
            country = aliases.get(country, country)
            neutral = bool(c.get('neutralSite'))
            rule = 'provider_neutral_flag'
            if country and country not in (home, away):
                neutral, rule = True, 'venue_country_differs_from_both_teams'
            key = 'fifa.friendly:'+event['id']
            row = {'match_id': key, 'cohort': 'fifa.friendly', 'home': home, 'away': away,
                   'date': event['date'][:10], 'kickoff_at': event['date'],
                   'home_goals': int(scores[0]), 'away_goals': int(scores[1]),
                   'neutral': neutral, 'score_basis': 'regulation_90',
                   'source_url': meta['url'], 'observed_at': meta['query_time_utc'],
                   'first_known_at': None, 'raw_file': str(path.relative_to(root)),
                   'raw_sha256': meta['sha256'], 'raw_neutral': c.get('neutralSite'),
                   'venue': venue, 'neutral_rule': rule}
            if key in completed:
                assert all(completed[key][k] == row[k] for k in ('home','away','date','home_goals','away_goals','neutral'))
                continue
            completed[key] = row
            old = rows.get(key)
            changed = {k: {'old': old.get(k), 'new': row[k]} for k in ('home','away','date','home_goals','away_goals','neutral') if old and old.get(k) != row[k]}
            edits.append({'match_id': key, 'new_match': old is None, 'changed_fields': changed})
            rows[key] = row
    history = validate_history(list(rows.values()))
    assert max(r['date'] for r in history) < '2026-11-17'
    refreshed = fit_strength(history, half_life=retained['half_life_days'], ridge=retained['ridge'])
    for key in ('nuisance', 'selected_family', 'temperature', 'market_policy'):
        refreshed[key] = retained[key]
    refreshed.update(research_status='FIXED_RECIPE_REFRESH_NOT_PROMOTED',
                     parent_artifact_sha256=sha(derived/'retained-artifact.json'),
                     generated_at=datetime.now(timezone.utc).isoformat(),
                     recipe_note='Strength parameters refitted; half-life/ridge/family/rho/temperature/market alpha unchanged. Current schedules update scores/venues; no xG feature available.')
    write(derived/'refreshed-history.json', history)
    write(derived/'history-update-audit.json', edits)
    write(derived/'refreshed-artifact.json', refreshed)
    market = read(root/'markets-fallback/markets-fallback-extracted.json')
    eventlist = read(root/'markets-fallback/infersports-events-raw.json')['data']
    forecasts, availability = [], []
    for market_fixture in market['fixtures']:
        eid = market_fixture['espn_event_id']
        summary_file = root/f'fixtures-market/espn-{eid}-summary-raw.json'
        smeta = read(summary_file.with_name(summary_file.name.replace('-raw','-meta')))
        summary = read(summary_file)
        c = summary['header']['competitions'][0]
        assert c['status']['type']['state'] == 'pre' and not c['status']['type']['completed']
        sides = {t['homeAway']: t for t in c['competitors']}
        home, away = sides['home']['team']['displayName'], sides['away']['team']['displayName']
        event = next(r for r in eventlist if r['id'] == market_fixture['provider_event_id'])
        assert (event['home_team']['name'], event['away_team']['name']) == (home, away)
        assert aware(event['scheduled_at']) == aware(c['date'])
        assert event['status'] == 'scheduled' and event['league']['name'] == 'INFri'
        raw_market_file = root/f'markets-fallback/infersports-{eid}-odds-raw.json'
        raw_market = read(raw_market_file)
        assert raw_market['event_id'] == event['id'] and raw_market['stale'] is False
        assert sha(raw_market_file) == market_fixture['response_sha256']
        raw_quotes = raw_market['odds']
        line = {'401930880':2.25, '401916336':2.5, '401916335':5.25}[eid]
        total = next(q for q in raw_quotes if q['bookmaker']=='m8bet' and q['market_type']=='totals' and q['line']==line and q['status']=='open')
        one = next(q for q in raw_quotes if q['bookmaker']==('crown' if home=='Singapore' else 'm8bet') and q['market_type']=='1x2' and q['status']=='open')
        for quote in (total,one):
            assert quote['period']=='full_time' and quote['format']=='decimal'
            assert all(float(v)>1 for v in quote['prices'].values())
            assert 0 <= (aware(cutoff)-aware(quote['as_of'])).total_seconds() <= 3600
        fixture = {'match_id':'fifa.friendly:'+eid, 'competition':'fifa.friendly', 'cohort':'fifa.friendly',
                   'home':home,'away':away,'home_id':sides['home']['id'],'away_id':sides['away']['id'],
                   'phase':'PreMatch','stage':'international-friendly','score_basis':'regulation_90',
                   'kickoff_at':c['date'],'cutoff_at':cutoff,'neutral':home=='Japan',
                   'venue':summary['gameInfo']['venue'],'provider_neutral_site':c.get('neutralSite'),
                   'neutral_evidence':'JFA official confirms Singapore venue' if home=='Japan' else 'Host national team plays in own country',
                   'total_line':line, 'total_quote':dict(total, source_url=market_fixture['source_url'],
                       query_time=market_fixture['query_time_utc'], source_quote_time=total['as_of'],
                       provider='InferSports', source_sha256=market_fixture['response_sha256']),
                   'wdl_quote':dict(one, source_url=market_fixture['source_url'],query_time=market_fixture['query_time_utc']),
                   'sources':[{'source_url':smeta.get('url',smeta.get('source_url')), 'query_time':smeta.get('query_time_utc',smeta.get('query_time'))},
                              {'source_url':market_fixture['source_url'],'query_time':market_fixture['query_time_utc']}],
                   'confirmed_starting_lineup':False,'xg_status':'NO_VERIFIED_NATIONAL_TEAM_XG_OBTAINED'}
        write(derived/f'{eid}-fixture.json',fixture)
        try:
            active = predict_models(fixture, assets/'runtime/active-model.json')
            availability.append({'match_id':fixture['match_id'],'status':'AVAILABLE','unexpected':True})
            raise RuntimeError('Unexpected active friendly route; review before publishing')
        except ValueError as exc:
            availability.append({'match_id':fixture['match_id'], 'current_status':'UNAVAILABLE','test_status':'UNAVAILABLE', 'actual_load_error':str(exc)})
        output = {'fixture':fixture, 'research_models':{}, 'formal_kpi_eligible':False}
        for name,model in [('retained',retained),('refreshed',refreshed)]:
            pred = research_predict(model,fixture,model['selected_family'],model['temperature'])
            pred['research_role'] = name
            pred['artifact_sha256'] = sha(derived/f'{name}-artifact.json')
            pred['training_data_cutoff'] = model['train_end']
            pred['score_distribution_audit'] = audit_prediction(pred)
            pred['top_scores'] = [{'score':f'{idx//len(pred["matrix"])}-{idx%len(pred["matrix"])}', 'p':float(np.asarray(pred['matrix']).ravel()[idx])} for idx in np.argsort(np.asarray(pred['matrix']).ravel())[-8:][::-1]]
            output['research_models'][name] = pred
        # Independent market-implied reference: no trained weighting and no
        # mixture with either history model. Quarter lines use half-win/loss.
        inv = np.array([1/one['prices'][s] for s in ('home','draw','away')]); target_wdl=inv/inv.sum()
        total_inv = np.array([1/total['prices'][s] for s in ('over','under')]); target_over=total_inv[0]/total_inv.sum()
        def over_share(m):
            s=total_settlement(m,line,'over')
            w=s['win']+.5*s['half_win']; loss=s['loss']+.5*s['half_loss']
            return w/(w+loss)
        def residual(log_rates):
            m=matrix(*np.exp(log_rates))
            return np.r_[probabilities(m)-target_wdl, over_share(m)-target_over]
        fit=least_squares(residual,np.log([.4,5.2] if home=='Singapore' else [1.5,1.0]),bounds=(np.log([.01,.01]),np.log([11.9,11.9])))
        assert fit.success
        mr=np.exp(fit.x); mm=matrix(*mr)
        mode=np.unravel_index(mm.argmax(),mm.shape)
        output['market_implied_reference']={'method':'Unweighted least squares of no-vig 1X2 probabilities and quarter-line effective over-share under independent Poisson; descriptive only, not trained or independently calibrated.',
            'source_wdl_probabilities':target_wdl.tolist(),'source_over_effective_share':float(target_over),
            'fitted_goal_rates':mr.tolist(),'residuals':residual(fit.x).tolist(),
            'primary':f'{mode[0]}-{mode[1]}','primary_probability':float(mm[mode]),
            'wdl':dict(zip(['主胜','平局','客胜'],map(float,probabilities(mm)))),
            'over':total_settlement(mm,line,'over'),'under':total_settlement(mm,line,'under'),
            'matrix':mm.tolist(),'matrix_hash':digest(mm.tolist()),
            'top_scores':[{'score':f'{idx//len(mm)}-{idx%len(mm)}','p':float(mm.ravel()[idx])} for idx in np.argsort(mm.ravel())[-8:][::-1]]}
        forecasts.append(output)
        write(derived/f'{eid}-research.json',output)
    write(derived/'active-load-status.json',availability)
    write(derived/'run-manifest.json', {'schema':'WCPP-FRIENDLY-RESEARCH-20261117-1','cutoff_at':cutoff,
         'executed_source_commit':subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip(),
         'analysis_script_sha256':sha(__file__), 'numerical_source_sha256':sha(source/'runtime/v2/model.py'),
         'active_registry_sha256':sha(assets/'runtime/active-model.json'),
         'old_history_n':len(old_rows),'new_history_n':len(history),'current_schedule_verified_n':len(completed),
         'new_matches':sum(e['new_match'] for e in edits),'changed_existing_rows':sum(bool(e['changed_fields']) for e in edits),
         'train_end':history[-1]['date'],'data_validation':'Source-backed date-isolated research. Historical first-known chronology not certified; untouched older venue flags retain source uncertainty.',
         'future_validation':'Three targets genuinely future at inference; no outcomes used.',
         'model_changes':'No active parameter/registry writes; no automatic promotion.'})
    for out in forecasts:
        print(out['fixture']['home'],out['fixture']['away'],out['fixture']['total_line'])
        for name,p in out['research_models'].items():
            print(name, 'rates',p['rates'],'top',p['top_scores'][:4],'WDL',p['wdl'],'over',p['over'])
        p=out['market_implied_reference']; print('market',p['fitted_goal_rates'],p['top_scores'][:4],p['wdl'],'over',p['over'])
    print('manifest',read(derived/'run-manifest.json'))


if __name__=='__main__':
    main()
