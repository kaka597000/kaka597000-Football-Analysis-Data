"""Train one fixed score Transformer and compare it with the three published forecasts."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import sys

import numpy as np


REFERENCE = Path(__file__).resolve().parents[2] / '20261118-sequence' / 'history'
REFERENCE_REPORT = 'a200287f3a23b1da8b1cbb14177f7bcc3a87036bad39be29b9aa70d1078eccc2'
ARMS = ('baseline', 'lstm', 'lightgbm', 'transformer')
METRICS = ('score_top1', 'wdl', 'total_strict_full_win')
QUALITY = ('score_log_loss', 'wdl_log_loss', 'wdl_brier', 'over_full_win_brier_excluding_push')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    from publication import deliver

    deliver(path, (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode())


def prior_matches(inputs):
    from research_program.sequence_history import prepare_rows

    report_file = inputs / 'season-validation.json'
    if sha(report_file) != REFERENCE_REPORT:
        raise ValueError('previous published evaluation identity differs')
    study = json.loads(report_file.read_bytes())
    files = ('samples-2425.jsonl.gz', 'samples-2526.jsonl.gz', 'season-holdout.jsonl.gz')
    inputs_sha = {name: sha(inputs / name) for name in files}
    if any(checksum != study['sources_sha256'][name] for name, checksum in inputs_sha.items()):
        raise ValueError('published sequence inputs or reference predictions differ')
    training, holdout = (prepare_rows(inputs / name) for name in files[:2])
    with gzip.open(inputs / files[2], 'rt', encoding='utf-8') as stream:
        old = [json.loads(line) for line in stream]
    mid = [r['match_id'] for r in training + holdout]
    if len(set(mid)) != len(mid) or len(training) != study['fit_n'] or len(holdout) != study['evaluation_n']:
        raise ValueError('training and evaluation must retain their original disjoint populations')
    if not max(r['game_date'] for r in training) < study['fit_cutoff'][:10] < min(r['game_date'] for r in holdout):
        raise ValueError('overlapping date cohorts')
    if max(r['game_date'] for r in holdout) >= study['forward_cutoff'][:10]:
        raise ValueError('final training includes a future game')
    return training, holdout, old, study, dict(inputs_sha, **{'season-validation.json': REFERENCE_REPORT})


def select(picks):
    return {'primary': picks['primary'], 'wdl': picks['wdl'], 'total': picks['total']['direction']}


def apply_holdout(artifact, row, old):
    from optimization.evaluate import settle_ou
    from research_program import transformer_score
    from research_program.three_arm_model import score_picks
    from research_program.three_arm_review import _outcome

    line = row['market']['total']['line']
    home, away = row['home_goals'], row['away_goals']
    if (row['match_id'] != old['match_id'] or old['actual'] != [home, away] or old['line'] != line
            or old['matchday'] != row['game_date'] or row['cohort'] != old['cohort']
            or set(old['forecasts']) != set(ARMS[:-1]) or set(old['outcomes']) != set(ARMS[:-1])):
        raise ValueError('paired forecast differs from the historical input fixture')
    seq = np.asarray(row['sequence'])
    base = row['baseline_matrix']
    matrix = transformer_score.apply(artifact, base, seq)
    picks = score_picks(matrix, line=line)
    result = _outcome(dict(picks, matrix=matrix), {'home': home, 'away': away})
    direction = 'home' if home > away else 'away' if home < away else 'draw'
    result['wdl_log_loss'] = float(-np.log(max(1e-15, picks['wdl_probabilities'][direction])))
    settlement = settle_ou(home + away, line, 'over')
    over = picks['total']['settlements']['over']
    result['over_full_win_brier_excluding_push'] = None
    if settlement != 'PUSH':
        over_p = over['win'] / max(1e-15, 1. - over['push'])
        result['over_full_win_brier_excluding_push'] = float((over_p - (settlement == 'FULL_WIN')) ** 2)
    reversed_seq = seq.copy()
    for team in reversed_seq:
        valid = team[:, 3].astype(bool)
        team[valid] = team[valid][::-1].copy()
    reversed_matrix = transformer_score.apply(artifact, base, reversed_seq)
    sensitivity = {
        'reversed_picks': select(score_picks(reversed_matrix, line=line)),
        'chronological_log_rate_residuals': transformer_score.residuals(artifact, base, seq).tolist(),
        'reversed_log_rate_residuals': transformer_score.residuals(artifact, base, reversed_seq).tolist(),
    }
    return dict(old, forecasts=dict(old['forecasts'], transformer=picks),
                outcomes=dict(old['outcomes'], transformer=result), sensitivity=sensitivity)


def summarize(rows):
    from research_program.three_arm_review import _paired

    arms = {}
    for name in ARMS:
        metrics = [r['outcomes'][name] for r in rows]
        quality = {}
        for key in QUALITY:
            observed = [p[key] for p in metrics if p[key] is not None]
            quality[key] = float(np.mean(observed)) if observed else None
        arms[name] = {
            'hits': {key: sum(bool(v[key]) for v in metrics) for key in METRICS},
            'denominators': {key: sum(v[key] is not None for v in metrics) for key in METRICS},
            'settlement_counts': dict(Counter(v['total_settlement'] for v in metrics)),
            'probability_quality': quality,
        }
    paired = {'transformer_minus_' + name: {key: _paired(rows, name, 'transformer', key) for key in METRICS}
              for name in ARMS[:-1]}
    observed_change = Counter(primary=0, wdl=0, total=0)
    residuals = []
    for row in rows:
        diag = row['sensitivity']
        real = select(row['forecasts']['transformer'])
        for key, value in real.items():
            observed_change[key] += int(diag['reversed_picks'][key] != value)
        residuals.extend(np.abs(np.subtract(diag['chronological_log_rate_residuals'], diag['reversed_log_rate_residuals'])))
    sensitivity = {'changed_calls': dict(observed_change), 'team_sides': len(residuals),
                   'mean_abs_log_rate_change': float(np.mean(residuals)), 'max_abs_log_rate_change': float(max(residuals))}
    return {'population': len(rows), 'arms': arms, 'paired': paired, 'order_sensitivity': sensitivity}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--inputs', type=Path, default=REFERENCE)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    sys.path[:0] = [str(args.source.resolve() / 'runtime'), str(args.source.resolve())]
    from publication import deliver
    from research_program import transformer_score

    out = args.out.resolve()
    out.mkdir(exist_ok=True, parents=True)
    training, holdout, old, previous, provenance = prior_matches(args.inputs)
    first = transformer_score.fit(training, cutoff_at=previous['fit_cutoff'])
    save(out / 'season-training-artifact.json', first)
    print('development model trained', len(training), flush=True)
    rows = [apply_holdout(first, row, original) for row, original in zip(holdout, old, strict=True)]
    body = b''.join((json.dumps(r, sort_keys=True, allow_nan=False, separators=(',', ':')) + '\n').encode() for r in rows)
    deliver(out / 'season-holdout.jsonl.gz', gzip.compress(body, mtime=0))
    final = transformer_score.fit(training + holdout, cutoff_at=previous['forward_cutoff'])
    save(out / 'artifact.json', final)
    data = summarize(rows)
    for arm in ARMS[:-1]:
        if data['arms'][arm] != previous['study']['arms'][arm]:
            raise ValueError('reference outcome summary changed for ' + arm)
    report = {'schema': 'SCORE-TRANSFORMER-TEMPORAL-COMPARISON-1', 'fit_n': len(training), 'evaluation_n': len(rows),
              'forward_fit_n': len(training) + len(holdout), 'fit_cutoff': previous['fit_cutoff'],
              'forward_cutoff': previous['forward_cutoff'], 'evaluation_date_range': previous['evaluation_date_range'],
              'evidence': previous['evidence'], 'common_baseline': previous['common_baseline'],
              'recipe': 'One fixed research configuration. Reversing the observation order is a post-fit sensitivity diagnostic.',
              'study': data, 'by_cohort': {league: summarize([r for r in rows if r['cohort'] == league])
                                           for league in sorted({r['cohort'] for r in rows})},
              'same_input_coverage': len(rows) / len(holdout), 'inputs_sha256': provenance,
              'source_sha256': {p.name: sha(p) for p in (Path(__file__), Path(transformer_score.__file__))},
              'outputs_sha256': {name: sha(out / name) for name in ('season-training-artifact.json', 'artifact.json', 'season-holdout.jsonl.gz')}}
    save(out / 'season-validation.json', report)
    print(json.dumps({a: m['hits'] for a, m in data['arms'].items()}, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
