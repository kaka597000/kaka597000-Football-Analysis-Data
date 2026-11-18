"""Reproduce the registered temporal development comparison from retained row-level inputs."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ARMS = ('baseline', 'lstm', 'lightgbm')
STUDY_CUTOFF = '2025-08-01T00:00:00Z'
TRIAL_CUTOFF = '2026-11-18T00:00:00Z'
METRICS = ('score_top1', 'wdl', 'total_strict_full_win')


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evaluate(artifact, rows):
    from optimization.evaluate import settle_ou
    from research_program import sequence_models, three_arm_model
    from research_program.three_arm_review import _outcome

    results = []
    for row in rows:
        h, a = row['home_goals'], row['away_goals']
        direction = 'home' if h > a else 'away' if h < a else 'draw'
        line = row['market']['total']['line']
        if row['game_date'] <= artifact['cutoff_at'][:10]:
            raise ValueError('holdout match earlier than training split')
        matrices = sequence_models.apply(artifact, row['baseline_matrix'], row['sequence'])
        item = {'match_id': row['match_id'], 'matchday': row['game_date'], 'cohort': row['cohort'],
                'actual': [h, a], 'line': line, 'forecasts': {}, 'outcomes': {}}
        for arm, matrix in matrices.items():
            forecast = three_arm_model.score_picks(matrix, line=line)
            item['forecasts'][arm] = forecast
            obs = _outcome(dict(forecast, matrix=matrix), {'home': h, 'away': a})
            obs['wdl_log_loss'] = float(-np.log(max(1e-15, forecast['wdl_probabilities'][direction])))
            over = forecast['total']['settlements']['over']
            settlement = settle_ou(h + a, line, 'over')
            obs['over_full_win_brier_excluding_push'] = None
            if settlement != 'PUSH':
                p = over['win'] / max(1e-15, 1. - over['push'])
                obs['over_full_win_brier_excluding_push'] = float((p - (settlement == 'FULL_WIN')) ** 2)
            item['outcomes'][arm] = obs
        results.append(item)
    return results


def summarize(rows):
    from research_program.three_arm_review import _paired
    arms = {}
    for arm in ARMS:
        obs = [r['outcomes'][arm] for r in rows]
        counts = {k: sum(v[k] is not None for v in obs) for k in METRICS}
        hits = {k: sum(bool(v[k]) for v in obs) for k in METRICS}
        scores = {}
        for field in ('score_log_loss', 'wdl_log_loss', 'wdl_brier', 'over_full_win_brier_excluding_push'):
            values = [v[field] for v in obs if v[field] is not None]
            scores[field] = float(np.mean(values)) if values else None
        arms[arm] = {'denominators': counts, 'hits': hits, 'probability_quality': scores,
                     'settlement_counts': dict(Counter(v['total_settlement'] for v in obs))}
    pairs = {}
    for before, after in [('baseline', 'lstm'), ('baseline', 'lightgbm'), ('lightgbm', 'lstm')]:
        pairs[after + '_minus_' + before] = {k: _paired(rows, before, after, k) for k in METRICS}
    return {'population': len(rows), 'arms': arms, 'paired': pairs}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--inputs', type=Path, default=Path(__file__).parent)
    parser.add_argument('--out', type=Path, default=Path(__file__).parent)
    args = parser.parse_args()
    sys.path[:0] = [str(args.source.resolve() / 'runtime'), str(args.source.resolve())]
    from publication import deliver
    from research_program import sequence_history, sequence_models

    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    training_path = args.inputs / 'samples-2425.jsonl.gz'
    holdout_path = args.inputs / 'samples-2526.jsonl.gz'
    training = sequence_history.prepare_rows(training_path)
    holdout = sequence_history.prepare_rows(holdout_path)
    if (len(training), len(holdout)) != (1299, 1737):
        raise ValueError('previously registered European development population differs')
    train_id = {r['match_id'] for r in training}
    test_id = {r['match_id'] for r in holdout}
    if train_id & test_id or len(test_id) != len(holdout):
        raise ValueError('duplicate fixtures across training and holdout')
    if max(r['game_date'] for r in training) >= STUDY_CUTOFF[:10]:
        raise ValueError('training date exceeds prespecified cutoff')

    first = sequence_models.fit(training, cutoff_at=STUDY_CUTOFF)
    deliver(out / 'season-training-artifact.json', encoded(first))
    print('development fit', first['training_matches'], flush=True)
    results = evaluate(first, holdout)
    ledger = b''.join((json.dumps(row, sort_keys=True, allow_nan=False, separators=(',', ':')) + '\n').encode()
                      for row in results)
    deliver(out / 'season-holdout.jsonl.gz', gzip.compress(ledger, mtime=0))
    final = sequence_models.fit(training + holdout, cutoff_at=TRIAL_CUTOFF)
    deliver(out / 'artifact.json', encoded(final))

    report = {'schema': 'SEQUENCE-EUROPE-DEVELOPMENT-1', 'fit_n': len(training), 'evaluation_n': len(holdout),
              'forward_fit_n': final['training_matches'], 'fit_cutoff': STUDY_CUTOFF, 'forward_cutoff': TRIAL_CUTOFF,
              'evaluation_date_range': [min(r['matchday'] for r in results), max(r['matchday'] for r in results)],
              'evidence': 'Previously inspected European seasons; point-in-time odds were unavailable. '
                          'Bet365 closing prices and prior date-only team results are development proxies.',
              'common_baseline': 'Published goals-only match PMF with a fixed, single-book H2H/Asian total projection.',
              'frozen_residual_selection': 'Fixed recipe; no adjustments to hyperparameters on the evaluation season.',
              'active_model_changed': False, 'study': summarize(results),
              'by_cohort': {s: summarize([r for r in results if r['cohort'] == s])
                            for s in sorted({r['cohort'] for r in results})},
              'sources_sha256': {p.name: sha(p) for p in (
                  training_path, holdout_path, Path(sequence_history.__file__), Path(sequence_models.__file__),
                  Path(__file__), out / 'season-training-artifact.json', out / 'season-holdout.jsonl.gz',
                  out / 'artifact.json')}}
    deliver(out / 'season-validation.json', encoded(report))
    print(json.dumps({arm: v['hits'] for arm, v in report['study']['arms'].items()}, sort_keys=True))


if __name__ == '__main__':
    main()
