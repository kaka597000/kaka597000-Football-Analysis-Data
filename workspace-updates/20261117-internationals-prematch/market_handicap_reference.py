"""Independent two-market diagnostic. No mixture or trained-effect claims."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from scipy.optimize import least_squares


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--source',required=True)
    ap.add_argument('--root',default=str(Path(__file__).parent))
    a=ap.parse_args(); root=Path(a.root)
    sys.path.insert(0,str(Path(a.source)/'runtime'))
    from v2.model import matrix, total_settlement, probabilities, digest, aware
    from research.team_goal_analysis import summarize_prediction
    output=[]
    for eid,ah in [('401930880',-.5),('401916336',-.75),('401916335',4.75)]:
        research=json.loads((root/f'derived/{eid}-research.json').read_text())
        fixture=research['fixture']
        odds=json.loads((root/f'markets-fallback/infersports-{eid}-odds-raw.json').read_text())
        handicap=next(q for q in odds['odds'] if q['bookmaker']=='m8bet' and q['market_type']=='asian_handicap' and q['line']==ah and q['status']=='open')
        total=fixture['total_quote']; line=total['line']
        assert handicap['period']=='full_time' and handicap['format']=='decimal'
        assert 0 <= (aware(fixture['cutoff_at'])-aware(handicap['as_of'])).total_seconds() <= 3600
        assert all(v>1 for v in handicap['prices'].values())
        inv=np.array([1/handicap['prices'][x] for x in ('home','away')]); ah_target=inv[0]/inv.sum()
        inv=np.array([1/total['prices'][x] for x in ('over','under')]); ou_target=inv[0]/inv.sum()
        grid=np.indices((51,51)); difference=grid[0]-grid[1]
        legs=[ah] if (ah*2).is_integer() else [ah-.25,ah+.25]
        # Quote line is from the HOME side: Singapore +4.75, not -4.75.
        result=sum(np.sign(difference+leg) for leg in legs)/len(legs)
        def shares(m):
            w=float((m*np.maximum(result,0)).sum()); loss=float((m*np.maximum(-result,0)).sum())
            s=total_settlement(m,line,'over'); ow=s['win']+.5*s['half_win']; ol=s['loss']+.5*s['half_loss']
            return np.array([w/(w+loss),ow/(ow+ol)])
        fit=least_squares(lambda x:shares(matrix(*np.exp(x)))-[ah_target,ou_target],
                          np.log([.4,5.2] if eid=='401916335' else [1.6,1.0]),
                          bounds=(np.log([.01,.01]),np.log([11.9,11.9])),xtol=1e-12,gtol=1e-12,ftol=1e-12)
        assert fit.success
        lambdas=np.exp(fit.x); m=matrix(*lambdas); mode=np.unravel_index(m.argmax(),m.shape)
        item={'fixture':fixture,'method':'Independent Poisson matching same-bookmaker M8Bet full-time Asian handicap and totals effective win shares after proportional de-vig; zero trained mixture weights; descriptive market reference, not a calibrated forecast.',
              'handicap_quote':handicap,'total_quote':total,'target_effective_shares':[float(ah_target),float(ou_target)],
              'residuals':(shares(m)-[ah_target,ou_target]).tolist(),'rates':lambdas.tolist(),
              'primary':f'{mode[0]}-{mode[1]}','primary_probability':float(m[mode]),
              'matrix':m.tolist(),'matrix_hash':digest(m.tolist()),
              'wdl':dict(zip(['主胜','平局','客胜'],map(float,probabilities(m)))),
              'over':total_settlement(m,line,'over'),'under':total_settlement(m,line,'under'),
              'formal_kpi_eligible':False}
        item['team_goal_analysis']=summarize_prediction(item)
        item['top_scores']=[{'score':f'{idx//len(m)}-{idx%len(m)}','p':float(m.ravel()[idx])} for idx in np.argsort(m.ravel())[-8:][::-1]]
        output.append(item)
        print(eid,'rates',lambdas.tolist(),'WDL',item['wdl'],'top',item['top_scores'][:4],'over',item['over'])
    with (root/'derived/market-handicap-reference.json').open('x') as f:
        json.dump({'analysis_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'fixtures':output},f,ensure_ascii=False,indent=2,allow_nan=False)
        f.write('\n')


if __name__=='__main__':main()
