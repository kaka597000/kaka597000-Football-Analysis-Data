"""Cross-check the preregistered draw projection and its validation doses on locked R21 inputs."""
import argparse
from collections import Counter, defaultdict
import gzip
from hashlib import sha256
import json
from pathlib import Path
import tarfile
import tempfile

import numpy as np

from research_program import continuation_forward, continuation_scores, r8_score_study, score_dependence
from research_program.territory_study import extensions
from research_program.three_arm_model import top_three_scores
from research_program.r9_team_shape import actual_rank


DOSES = (0., .5, 1.)


def member(path, name, expected=None):
    with tarfile.open(path) as t:
        raw=t.extractfile(name).read()
    if expected and sha256(raw).hexdigest()!=expected:
        raise ValueError(str(path) + ':' + name)
    return raw


def projection(reference, contextual):
    score = reference.copy()
    i, j = np.indices(reference.shape)
    for group in (i < j, i > j):
        old = reference[group]
        new = contextual[group]
        if new.sum() > 0:
            score[group] = (new / new.sum()) * old.sum()
    if not np.array_equal(score.diagonal(), reference.diagonal()):
        raise ValueError('different draw cells')
    return score


def mixed(reference, alternate, dose):
    return reference + (alternate - reference) * dose


def compute(archive, prior_run, r11_root):
    locked = json.loads((prior_run/'inputs.json').read_bytes())
    raw_archive = r11_root / 'extension.tar.gz'
    if sha256(raw_archive.read_bytes()).hexdigest() != locked['extension_sha256']:
        raise ValueError('R11 source checksum differs')
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name in ('fixture-panels.jsonl', 'market-rows.csv'):
            (root/name).write_bytes(member(raw_archive, name))
        extra = extensions(root)
    output={}
    for code, hashes in sorted(locked['competitions'].items()):
        r5 = archive/'20261123-all-scope-kpi/models'/(code+'.tar.gz')
        r7 = archive/'20261123-prematch-literature/models'/(code+'.tar.gz')
        panel = [json.loads(line) for line in member(r5,'panel.jsonl',hashes['panel']).splitlines()]
        settings = json.loads(member(r7,'main/fit.json',hashes['r7_fit']))
        next_fit = json.loads(member(r7,'main/forward.json',hashes['r7_forward']))
        folder=prior_run/'main'/code
        trained=json.loads((folder/'fit.json').read_bytes())
        with gzip.open(folder/'exposure.jsonl.gz','rt') as f:
            design={r['id']:r['features'] for r in map(json.loads,f)}
        with gzip.open(folder/'forecasts.jsonl.gz','rt') as f:
            reports={r['id']:r for r in map(json.loads,f)}
        first,second,_=settings['bounds']
        start=sum(row['date']<first for row in panel)
        anchors,features,_=continuation_scores.inputs(panel,code)
        r7_grids=r8_score_study.matrices(anchors[start:],features[start:],settings)
        history=list(zip(panel[start:],r7_grids,strict=True))
        history.extend((game,continuation_forward.matrix(game,next_fit)) for game in extra[code])
        counts={d:Counter() for d in DOSES}
        heldout=[]
        for game,reference in history:
            mid=game['id']
            score=(game['home_goals'],game['away_goals'])
            full=score_dependence.matrix(reference,design[mid],trained['fitted']['context'])
            frozen=projection(reference,full)
            if game['date']<second:
                for dose in DOSES:
                    matrix=mixed(reference,frozen,dose)
                    rank=actual_rank(matrix,score)
                    counts[dose].update({'n':1,'first':int(rank==1),'three':int(rank<=3),'nll':-np.log(matrix[score])})
                continue
            row=reports[mid]
            if (list(score)!=row['actual'] or not np.isclose(reference[score],row['quality']['r7']['p_observed'],rtol=0,atol=1e-12)):
                raise ValueError('different archive fixture '+mid)
            heldout.append((row,reference,frozen))
        winner=min(DOSES,key=lambda d:(-counts[d]['first'],-counts[d]['three'],counts[d]['nll'],d))
        totals=defaultdict(Counter)
        for row,prior,alternative in heldout:
            actual='-'.join(map(str,row['actual']))
            picks=top_three_scores(mixed(prior,alternative,winner)) if winner else row['forecast']['r7']['top3']
            for pos,n in [('first',1),('three',3)]:
                new=actual in picks[:n]
                old=actual in row['forecast']['r7']['top3'][:n]
                totals[row['window']].update({pos:int(new),pos+'_gained':int(new and not old),pos+'_lost':int(old and not new)})
            totals[row['window']]['n']+=1
        output[code]={'dose':winner,'validation':{str(k):dict(v) for k,v in counts.items()},'windows':dict(totals)}
    return output


if __name__=='__main__':
    arg=argparse.ArgumentParser(description=__doc__)
    for name in ('data_updates','r21_study','r11','output'):
        arg.add_argument(name,type=Path)
    a=arg.parse_args()
    report=compute(a.data_updates,a.r21_study,a.r11)
    with a.output.open('x') as f:
        json.dump(report,f,sort_keys=True,indent=2,allow_nan=False)
        f.write('\n')
    print({league:r['dose'] for league,r in report.items()})
    for window in ('evaluation','recent','november_extension'):
        totals=Counter()
        for report_row in report.values():totals.update(report_row['windows'][window])
        print(window,dict(totals))
