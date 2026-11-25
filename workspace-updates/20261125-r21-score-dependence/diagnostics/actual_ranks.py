"""Reconstruct the actual-score ranks in the original R7 and R21 holdouts."""
import argparse
from collections import Counter
import csv
import gzip
from hashlib import sha256
import json
import math
from pathlib import Path
import sys
import tarfile

from research_program import continuation_scores, r8_score_study, score_dependence
from research_program.r10_shot_model import blend
from research_program.r9_team_shape import published_rank


def original(updates, dataset, competition, member, digest):
    path = updates / dataset / 'models' / (competition + '.tar.gz')
    with tarfile.open(path) as source:
        raw = source.extractfile(member).read()
    if sha256(raw).hexdigest() != digest:
        raise ValueError(f'source member differs: {competition} {member}')
    return raw


def ranks(updates, history):
    locked = json.loads((history / 'inputs.json').read_bytes())
    for competition, digests in sorted(locked['competitions'].items()):
        raw = original(updates, '20261123-all-scope-kpi', competition, 'panel.jsonl', digests['panel'])
        games = [json.loads(line) for line in raw.splitlines()]
        settings = json.loads(original(updates, '20261123-prematch-literature', competition,
                                       'main/fit.json', digests['r7_fit']))
        report = history / 'main' / competition
        fit = json.loads((report / 'fit.json').read_bytes())
        anchors, features, _ = continuation_scores.inputs(games, competition)
        validation_start = sum(game['date'] < settings['bounds'][0] for game in games)
        heldout = r8_score_study.matrices(anchors[validation_start:], features[validation_start:], settings)
        grids = {game['id']: matrix for game, matrix in zip(games[validation_start:], heldout, strict=True)}
        with gzip.open(report / 'forecasts.jsonl.gz', 'rt') as forecasts:
            for line in forecasts:
                row = json.loads(line)
                if row['window'] not in ('evaluation', 'recent'):
                    continue
                prior = grids[row['id']]
                full = score_dependence.matrix(prior, row['features'], fit['fitted']['context'])
                candidate = blend(prior, full, fit['doses']['context']['score'])
                result = dict(window=row['window'], competition=competition, fixture=row['id'],
                              home=row['home'], away=row['away'], actual='-'.join(map(str, row['actual'])))
                actual = tuple(row['actual'])
                for arm, matrix in [('r7', prior), ('candidate', candidate)]:
                    quality = row['quality'][arm]
                    picks = row['forecast'][arm]['top3']
                    if not math.isclose(matrix[actual], quality['p_observed'], rel_tol=0, abs_tol=1e-12):
                        raise ValueError(f'different observed probability: {row["id"]} {arm}')
                    for score, stored in zip(picks, quality['p_ordered'], strict=True):
                        cell = tuple(map(int, score.split('-')))
                        if not math.isclose(matrix[cell], stored, rel_tol=0, abs_tol=1e-12):
                            raise ValueError(f'different ordered probability: {row["id"]} {arm}')
                    result[arm] = published_rank(matrix, actual, picks)
                yield result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('data_updates', type=Path)
    parser.add_argument('historical', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    rows = list(ranks(args.data_updates, args.historical))
    with args.output.open('x', newline='') as out:
        writer = csv.DictWriter(out, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    for window in ('evaluation','recent'):
        batch = [r for r in rows if r['window'] == window]
        lost = [r for r in batch if r['r7'] <= 3 < r['candidate']]
        gained = [r for r in batch if r['candidate'] <= 3 < r['r7']]
        summary = dict(fixtures=len(batch), lost=len(lost), gained=len(gained),
                       lost_to_rank=Counter(r['candidate'] for r in lost),
                       gained_from_rank=Counter(r['r7'] for r in gained),
                       loss_scores=Counter(r['actual'] for r in lost),
                       gain_scores=Counter(r['actual'] for r in gained))
        print(window, json.dumps(summary))
        for arm in ('r7', 'candidate'):
            print(arm, dict(sorted(Counter(min(8, r[arm]) for r in batch).items())))
    return 0


if __name__ == '__main__':
    sys.exit(main())
