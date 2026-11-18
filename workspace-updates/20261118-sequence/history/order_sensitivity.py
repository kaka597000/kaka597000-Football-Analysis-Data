"""Reorder held-out games within each team's real events, keeping masks, baseline probabilities and scores fixed."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

import numpy as np


def reverse_games(sequence):
    result = np.array(sequence, copy=True)
    for side in result:
        valid = side[:, 3].astype(bool)
        side[valid] = side[valid][::-1].copy()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--inputs', type=Path, default=Path(__file__).parent)
    parser.add_argument('--out', type=Path, default=Path(__file__).parent)
    args = parser.parse_args()
    sys.path[:0] = [str(args.source.resolve() / 'runtime'), str(args.source.resolve())]
    from research_program import sequence_models as model
    from research_program.sequence_history import prepare_rows
    from research_program.three_arm_model import score_picks

    train, samples = (args.inputs / n for n in ('season-training-artifact.json', 'samples-2526.jsonl.gz'))
    artifact = json.loads(train.read_bytes())
    rows = prepare_rows(samples)
    differences = {arm: [] for arm in ('lstm', 'lightgbm')}
    changed = {arm: Counter(primary=0, wdl=0, total=0) for arm in differences}
    both_full = 0
    for row in rows:
        seq, matrix = np.asarray(row['sequence']), row['baseline_matrix']
        both_full += int(np.all(seq[:, :, 3]))
        directions, predictions = [], []
        for ordering in (seq, reverse_games(seq)):
            panels, context, _ = model._features(ordering, matrix)
            inputs = np.column_stack((panels.reshape(2, -1), context))
            directions.append({'lstm': model._lstm_forward(artifact['lstm'], panels, context),
                               'lightgbm': model._tree_forward(artifact['lightgbm']['trees'], inputs)})
            arms = model.apply(artifact, matrix, ordering)
            predictions.append({arm: score_picks(arms[arm], line=row['market']['total']['line'])
                                for arm in differences})
        for arm, values in differences.items():
            values.extend(np.abs(directions[0][arm] - directions[1][arm]))
            real, reversed_ = (p[arm] for p in predictions)
            changed[arm]['primary'] += int(real['primary'] != reversed_['primary'])
            changed[arm]['wdl'] += int(real['wdl'] != reversed_['wdl'])
            changed[arm]['total'] += int(real['total']['direction'] != reversed_['total']['direction'])
    report = {'status': 'POST_FIT_DIAGNOSTIC_NOT_USED_FOR_SELECTION', 'holdout_matches': len(rows),
              'both_full_histories': both_full, 'team_sides': 2 * len(rows),
              'procedure': 'Reverse the real events independently within each team. Keep the same events and '
                           'padding slots, home/away, baseline matrix, quote and line, and all fitted parameters.',
              'reproduce_from_data_root': 'python workspace-updates/20261118-sequence/history/order_sensitivity.py '
                                            '--source /path/to/Football-Analysis --out /tmp/sequence-sensitivity',
              'inputs_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (samples, train)},
              'arms': {name: {'mean_abs_log_rate_change': float(np.mean(values)),
                              'max_abs_log_rate_change': float(np.max(values)),
                              'changed_calls': dict(changed[name])} for name, values in differences.items()}}
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / 'order-sensitivity.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(report['arms'], sort_keys=True))


if __name__ == '__main__':
    main()
