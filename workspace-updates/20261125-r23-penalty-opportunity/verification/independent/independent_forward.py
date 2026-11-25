"""Check the original R23 forward issues against existing R7 grids and independent exposure math."""
import argparse
from collections import defaultdict
from datetime import datetime
import gzip
import json
from pathlib import Path

import numpy as np
from research.analysis_freeze import verify
from independent_scores import get_features, histories, require, verify_score


def read(path):
    return json.loads(path.read_bytes())


def receipt(folder, item):
    doc = read(folder / item['file'])
    verify(doc)
    require(doc['record_sha256'] == item['sha256'] and doc['recorded_at'] == item['recorded_at'], 'receipt identity')
    return doc


def run(study, forward, ranks, r22, grids_path, events):
    events_index = histories(events)
    manifest = read(forward / 'receipts.json')
    parent = read(r22 / 'receipts.json')
    reg = receipt(forward, manifest['registration'])
    rank = receipt(ranks, read(ranks / 'plan.json'))
    require(rank['payload']['identity']['source_registration'] == reg['record_sha256'], 'ranking source')
    original = {mid: receipt(r22, entry) for mid,entry in parent['matches'].items()}
    with gzip.open(grids_path,'rt') as stream:
        grids = {}
        for row in map(json.loads,stream):
            require(row['match_id'] not in grids,'duplicate prior')
            grids[row['match_id']] = np.asarray(row['matrix'])
    require(set(original)==set(grids),'R22 populations for original R7 matrices')
    candidates = defaultdict(list)
    picks = {}
    total_lines = 0
    for mid,entry in manifest['matches'].items():
        new = receipt(forward, entry)
        old = original[mid]
        code=new['fixture']['cohort']
        require(new['match_id']==mid and new['revision']==1, 'first issue identity')
        require(new['payload']['registration_sha256']==reg['record_sha256'], 'R23 registration')
        require(datetime.fromisoformat(new['recorded_at']) < datetime.fromisoformat(new['fixture']['kickoff_at']), 'prematch issue')
        current = new['payload']
        require(current['r22_first_issue'] == old['record_sha256'], 'R22 issue')
        require(current['r7_first_issue'] == old['payload']['r7_first_issue'], 'R7 issue')
        require(current['line'] == old['payload']['line'], 'market line')
        total_lines += current['line'] is not None
        fitted = read(study / 'main' / code / 'forward.json')
        x = get_features(code,current['process'],events_index)
        require(np.allclose(x,current['features'],rtol=0,atol=1e-12),'exposure '+mid)
        expected = current['forecasts']['candidate']
        p,pt = verify_score(grids[mid],x,fitted['fitted']['beta'],fitted['dose'],expected,mid)
        require(abs(p-current['quality']['p_first'])<1e-12 and abs(pt-current['quality']['p_three'])<1e-12,
                'issued probabilities '+mid)
        control=old['payload']['forecasts']['r7']
        require(all(expected.get(k)==control.get(k) for k in ('wdl','total_line','total_side')), 'R7 directions '+mid)
        candidates[code].append((-p,datetime.fromisoformat(new['fixture']['kickoff_at']),mid))
        picks[mid]=(code,expected,control,entry['sha256'])
    ranked_count=0
    for code,seats in rank['payload']['identity']['selected'].items():
        ordered=[v[2] for v in sorted(candidates.get(code,()))[:3]]
        require(ordered==[s['match_id'] for s in seats],'ranked seats '+code)
        for s in seats:
            _,pick,_,sha=picks[s['match_id']]
            require(s['first_issue']['sha256']==sha and s['top3']==pick['top3'] and s['primary']==pick['primary'],'seat to issue')
        ranked_count+=len(seats)
    return dict(r22_population=len(original), checked_firsts=len(picks), checked_seats=ranked_count,
                actual_lines=total_lines, first_changed=sum(p['primary']!=c['primary'] for _,p,c,_ in picks.values()),
                ordered_three_changed=sum(p['top3']!=c['top3'] for _,p,c,_ in picks.values()),
                registration=reg['record_sha256'],ranking=rank['record_sha256'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for field in ('study','forward','ranks','r22','grids','events'):
        parser.add_argument('--'+field,type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(run(args.study,args.forward,args.ranks,args.r22,args.grids,args.events),sort_keys=True,indent=2))
