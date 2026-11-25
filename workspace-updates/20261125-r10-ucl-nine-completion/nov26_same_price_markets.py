"""Sign a same-fixture market baseline from the exact original authored quote on ten future games."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from research.analysis_freeze import DEFAULT_ROOT, digest, save, verify
from research_program import all_scope_model as model
from research_program.goal_state_study import write_new

S = Path('/workspace/scratch')
UCL = S/'ucl-six-issued'; BRA = S/'brazil-first-issued'
TRACK='same-price-90-market-comparison-20261126'

def read(p): return json.loads(p.read_bytes())
def decimal(v):
    if abs(v)<100:raise ValueError('incorrect American odds')
    return 1+(v/100 if v>0 else 100/-v)

def market(record,raw):
    mid=record['match_id']; q=record['fixture']['total_quote'];d=json.loads(raw)
    if sha256(raw).hexdigest()!=q['source_sha256'] or 'espn:'+d['header']['id']!=mid or d['header']['competitions'][0]['status']['type']['state']!='pre':
        raise ValueError('original forecast and quote have different provenance')
    b=next(book for book in d['pickcenter'] if book['provider']['name']==q['bookmaker']);assert q['over_odds']==decimal(b['overOdds']) and q['under_odds']==decimal(b['underOdds']) and q['line']==float(b['overUnder'])
    h2h=dict(home=decimal(b['homeTeamOdds']['moneyLine']), draw=decimal(b['drawOdds']['moneyLine']), away=decimal(b['awayTeamOdds']['moneyLine']))
    grid=model._full_market(tuple(h2h[side] for side in model.SIDES),q['line'],(q['over_odds'],q['under_odds']))
    return dict(h2h=h2h,quote=q,forecast=model.pick(grid,q['line']),matrix_sha256=digest(grid.tolist()),source_type='same_book_1x2_and_total_score_proxy',
                comprehensive_first_sha256=record['record_sha256'],source_sha256=q['source_sha256'],score_basis='regulation_90')

def sign(rows,out):
    exports=[]
    for ref,path in rows:
        r=verify(read(Path(ref['path'])));assert r['record_sha256']==ref['sha256'] and r['evaluation_slot']=='FIRST_PREMATCH';p=market(r,path.read_bytes())
        f=dict(r['fixture']); mid=r['match_id'];scope=Path(DEFAULT_ROOT)/digest(dict(match_id=mid,track=TRACK,stage='prematch'))/'000001.json'
        if not scope.exists():
            f['cutoff_at']=datetime.now(timezone.utc).isoformat();rec=save(p,f,stage='prematch',track=TRACK,idempotency_key='original-shown-price-'+mid)
        else:
            a=verify(read(scope));rec=dict(freeze_id=a['freeze_id'],path=str(scope),recorded_at=a['recorded_at'],sha256=a['record_sha256'],evaluation_slot=a['evaluation_slot'])
        result=verify(read(Path(rec['path'])));assert result['payload']==p and result['evaluation_slot']=='FIRST_PREMATCH';exports.append(dict(match_id=mid,market=rec,authored_sha=r['record_sha256'],forecast=p['forecast']))
    if not out.exists():write_new(out,exports)
    if read(out)!=exports:raise ValueError('conflicting earlier baseline export')

if __name__=='__main__':
    first3=read(S/'r10-ucl-issued/ranked-firsts.json')['selections'];first6=read(UCL/'six-firsts.json')['rows']
    games=[(r['comprehensive_reference'],S/'r10-ucl-three-evidence/raw'/('espn-summary-'+r['match_id'][5:]+'.json')) for r in first3]
    games.extend((r['comprehensive_reference'], S/'ucl-other-six-intake-20261125/raw/current'/('espn-summary-'+r['match_id'][5:]+'.json')) for r in first6)
    sign(games,UCL/'same-price-markets.json');sign([(read(BRA/'firsts.json')['rows'][0]['comprehensive_reference'],S/'brazil-nov26-20261125/raw/espn/summary-401841319.json')],BRA/'same-price-markets.json')
