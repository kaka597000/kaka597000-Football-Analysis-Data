"""Pure independent projection on signed R21 inputs using the separately validated R22 doses."""
import argparse
from datetime import timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from research.analysis_freeze import aware
from research_program import continuation_forward as r7
from research_program import r10_shot_model, score_dependence, territory_forward
from research_program import r9_score_study
from research_program.three_arm_model import top_three_scores
from r22_independent import projection, mixed


def independent(updates, historical, earlier, doses):
    r5_dir=updates/'20261123-all-scope-kpi'
    r7_dir=updates/'20261123-prematch-literature'
    def manifest(root):
        return json.loads((root/'manifest.json').read_bytes())
    old=territory_forward.FirstIssues.load(earlier)
    output={}
    with TemporaryDirectory() as temp:
        work=Path(temp)
        r9_score_study.verified_archive(r5_dir,manifest(r5_dir),'forward-first-issues.tar.gz',work/'raw')
        r9_score_study.verified_archive(r7_dir,manifest(r7_dir),'first-issues.tar.gz',work/'seven')
        raw_records=territory_forward.FirstIssues.load(work/'raw/issued')
        r7_records=territory_forward.FirstIssues.load(work/'seven')
        models={}
        for code in doses:
            r9_score_study.verified_archive(r7_dir,manifest(r7_dir),'models/'+code+'.tar.gz',work/code)
            models[code]=json.loads((work/code/'main/forward.json').read_bytes())
        for mid,entry in old.matches.items():
            first=territory_forward.ledger._read(earlier,entry)
            fx=first['fixture']; code=fx['cohort']; p=first['payload']
            t=aware(first['recorded_at'])
            old.match(fx,t)
            original=r7_records.match(fx,t); market=raw_records.match(fx,t)
            op=original['payload']['forecasts']['candidate']
            if (p['r7_first_issue']!=original['record_sha256'] or p['odds_source_first_issue']!=market['record_sha256']
                    or p['forecasts']['r7']!=op or p['line']!=market['payload']['line']):
                raise ValueError('parent differs '+mid)
            game=r7.frozen_game(fx,market['payload'])
            game['date']=aware(fx['kickoff_at']).astimezone(timezone.utc).date().isoformat()
            prior=r7.matrix(game,models[code])
            fit=json.loads((historical/'main'/code/'forward.json').read_bytes())
            context=score_dependence.matrix(prior,p['features'],fit['fitted']['context'])
            ctrl,_=r10_shot_model.decisions(prior,context,fit['doses']['context'],p['line'],op)
            if ctrl != p['forecasts']['candidate']:
                raise ValueError('R21 signed choices differ '+mid)
            dose=doses[code]['dose']
            grid=mixed(prior,projection(prior,context),dose)
            scores=top_three_scores(grid) if dose else op['top3']
            cell=tuple(map(int,scores[0].split('-')))
            output[mid]=dict(competition=code,kickoff=fx['kickoff_at'],r21_record=first['record_sha256'],
                             r7=op['top3'],r21=ctrl['top3'],r22=scores,wdl=op['wdl'],
                             total=op.get('total_side'),line=p['line'],p_first=float(grid[cell]))
    return output


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('updates','historical','forward','doses','output'):
        parser.add_argument(name,type=Path)
    a=parser.parse_args()
    rows=independent(a.updates,a.historical,a.forward,json.loads(a.doses.read_bytes()))
    with a.output.open('x') as f:
        json.dump(rows,f,ensure_ascii=False,sort_keys=True,indent=2)
        f.write('\n')
    print('independent pre-issue research comparison',len(rows),'changed vs R7 first',
          sum(r['r22'][0]!=r['r7'][0] for r in rows.values()),'ordered three',
          sum(r['r22']!=r['r7'] for r in rows.values()))
