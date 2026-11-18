"""Offline independent replay of the registered four-arm football comparison."""
import argparse
from collections import Counter, defaultdict
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import numpy as np


EXPERIMENT = Path(__file__).resolve().parent
DATA = EXPERIMENT.parents[1]
SEQUENCE = EXPERIMENT.with_name('20261118-sequence')
PROTOCOL_SHA256 = '45c837cc29554033ea0248acbee31895c36381d7acddadb105fa23426bfe3412'
TRANSFER_PROTOCOL_SHA256 = '3bd5f95fe82aba1428d38694cf95a4bc827cd6503a9a39ec93ce15b74bc33191'
ARMS = ('baseline', 'lightgbm', 'lstm', 'transformer')
METRICS = ('score_top1', 'wdl', 'total_strict_full_win')
QUALITY = ('score_log_loss', 'wdl_log_loss', 'wdl_brier', 'over_full_win_brier_excluding_push')


def load_module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prior = load_module(SEQUENCE / 'verify.py')


def paired(rows, reference, metric):
    """Resample whole dated blocks; weight each draw by its number of eligible games."""
    by_date = defaultdict(list)
    for row in rows:
        base = row['outcomes'][reference][metric]
        candidate = row['outcomes']['transformer'][metric]
        if base is not None and candidate is not None:
            by_date[row['matchday']].append(int(candidate) - int(base))
    days = [by_date[day] for day in sorted(by_date)]
    values = [value for group in days for value in group]
    interval = None
    if len(days) > 1:
        sampled = np.random.default_rng(20261118).integers(0, len(days), (2000, len(days)))
        sums = np.asarray([sum(day) for day in days])
        sizes = np.asarray([len(day) for day in days])
        interval = np.quantile(sums[sampled].sum(axis=1) / sizes[sampled].sum(axis=1), [.025, .975]).tolist()
    return {'eligible': len(values), 'gained': values.count(1), 'lost': values.count(-1),
            'net_hits': sum(values), 'net_rate': sum(values) / len(values) if values else None,
            'matchday_blocks': len(days), 'date_block_bootstrap_95pct_rate': interval}


def summarize(rows):
    arms = {}
    for arm in ARMS:
        outcomes = [row['outcomes'][arm] for row in rows]
        probability_quality = {}
        for metric in QUALITY:
            values = [r[metric] for r in outcomes if r[metric] is not None]
            probability_quality[metric] = float(np.mean(values)) if values else None
        arms[arm] = {'hits': {m: sum(r[m] is True for r in outcomes) for m in METRICS},
                     'denominators': {m: sum(r[m] is not None for r in outcomes) for m in METRICS},
                     'probability_quality': probability_quality,
                     'settlement_counts': dict(Counter(r['total_settlement'] for r in outcomes))}
    changed = Counter(primary=0, wdl=0, total=0)
    deltas = []
    for row in rows:
        picks, diagnostic = row['forecasts']['transformer'], row['sensitivity']
        for key, new in diagnostic['reversed_picks'].items():
            observed = picks['total']['direction'] if key == 'total' else picks[key]
            changed[key] += observed != new
        deltas.extend(abs(np.subtract(diagnostic['reversed_log_rate_residuals'], diagnostic['chronological_log_rate_residuals'])))
    comparisons = {'transformer_minus_' + arm: {m: paired(rows, arm, m) for m in METRICS} for arm in ARMS[:-1]}
    return {'population': len(rows), 'arms': arms, 'paired': comparisons,
            'order_sensitivity': {'changed_calls': dict(changed), 'team_sides': len(deltas),
                                  'mean_abs_log_rate_change': float(np.mean(deltas)), 'max_abs_log_rate_change': float(max(deltas))}}


def verify_historical(protocol):
    from research_program import sequence_history, transformer_score, three_arm_model, three_arm_review

    old, new = SEQUENCE / 'history', EXPERIMENT / 'history'
    report = prior.read(new / 'season-validation.json')
    for name, digest in protocol['original_europe_sources'].items():
        prior.checked(old / name, digest)
    for name, digest in report['outputs_sha256'].items():
        prior.checked(new / name, digest)
    for name, digest in report['inputs_sha256'].items():
        prior.checked(old / name, digest)
    prior.checked(new / 'run_study.py', report['source_sha256']['run_study.py'])
    prior.checked(Path(transformer_score.__file__), report['source_sha256']['transformer_score.py'])
    train = prior.records(old / 'samples-2425.jsonl.gz')
    holdout = sequence_history.prepare_rows(old / 'samples-2526.jsonl.gz')
    prior.require(len(train) == report['fit_n'] == 1299 and len(holdout) == report['evaluation_n'] == 1737
                  and len({r['match_id'] for r in train + holdout}) == report['forward_fit_n'] == 3036
                  and report['same_input_coverage'] == 1, 'paired populations changed')
    prior.require(max(r['game_date'] for r in train) < report['fit_cutoff'][:10] < min(r['game_date'] for r in holdout)
                  and max(r['game_date'] for r in holdout) < report['forward_cutoff'][:10], 'temporal split differs')
    for row in train + holdout:
        if any(info and info[-1] >= row['game_date'] for team in row['sequence_sources'] for info in team):
            raise ValueError('same-day or later evidence enters sequence for ' + row['match_id'])
    for name, count, cutoff in (('season-training-artifact.json', 1299, '2025-08-01T00:00:00Z'),
                                ('artifact.json', 3036, '2026-11-18T00:00:00Z')):
        artifact = prior.read(new / name)
        previous_fit = prior.read(old / name)
        prior.require(artifact['training_matches'] == count and artifact['cutoff_at'] == cutoff
                      and artifact['sample_sha256'] == previous_fit['sample_sha256']
                      and artifact['config'] == transformer_score.CONFIG and artifact['seed'] == protocol['model']['seed']
                      and artifact['parameter_count'] == sum(np.size(v) for v in artifact['weights'].values())
                      and artifact['max_native_replay_error'] < 1e-10 and not artifact['active_model_changed']
                      and artifact['max_abs_tilt'] == .35 and artifact['ridge'] == 2,
                      'different Transformer recipe, training population or weights: ' + name)

    reference_fit = prior.read(old / 'season-training-artifact.json')
    evaluation_fit = prior.read(new / 'season-training-artifact.json')
    old_runner = load_module(old / 'run_models.py')
    replay = old_runner.evaluate(reference_fit, holdout)
    prior.compare(replay, prior.records(old / 'season-holdout.jsonl.gz'), 'reference forecasts and outcomes')
    new_rows = prior.records(new / 'season-holdout.jsonl.gz')
    for row, reference, saved in zip(holdout, replay, new_rows, strict=True):
        mid, matrix, sequence = row['match_id'], row['baseline_matrix'], np.asarray(row['sequence'])
        pmf = transformer_score.apply(evaluation_fit, matrix, sequence)
        prior.require(np.isfinite(pmf).all() and pmf.min() >= 0 and abs(1 - pmf.sum()) < 1e-12, mid + ': invalid matrix')
        line, (h, a) = reference['line'], reference['actual']
        forecast = three_arm_model.score_picks(pmf, line=line)
        observed = three_arm_review._outcome(dict(forecast, matrix=pmf), {'home': h, 'away': a})
        direction = 'home' if h > a else 'away' if a > h else 'draw'
        observed['wdl_log_loss'] = float(-np.log(max(1e-15, forecast['wdl_probabilities'][direction])))
        # The registered European closing-total data use a half line with no pushes or splits.
        prior.require(line == 2.5, mid + ': changed original 2.5 line')
        over = forecast['total']['settlements']['over']['win']
        observed['over_full_win_brier_excluding_push'] = float((over - int(h + a > line)) ** 2)
        upside = sequence.copy()
        for team in upside:
            valid = team[:, 3].astype(bool)
            team[valid] = team[valid][::-1]
        rev = three_arm_model.score_picks(transformer_score.apply(evaluation_fit, matrix, upside), line=line)
        diagnostic = {'reversed_picks': {'primary': rev['primary'], 'wdl': rev['wdl'], 'total': rev['total']['direction']},
                      'chronological_log_rate_residuals': transformer_score.residuals(evaluation_fit, matrix, sequence).tolist(),
                      'reversed_log_rate_residuals': transformer_score.residuals(evaluation_fit, matrix, upside).tolist()}
        complete = dict(reference, forecasts=dict(reference['forecasts'], transformer=forecast),
                        outcomes=dict(reference['outcomes'], transformer=observed), sensitivity=diagnostic)
        prior.compare(complete, saved, mid)
    prior.compare(summarize(new_rows), report['study'], 'full paired metrics')
    cohorts = {r['cohort'] for r in new_rows}
    prior.require(cohorts == set(report['by_cohort']), 'missing cohort')
    for cohort in sorted(cohorts):
        prior.compare(summarize([r for r in new_rows if r['cohort'] == cohort]), report['by_cohort'][cohort], cohort)
    return {'historical_training': len(train), 'heldout_matches': len(new_rows), 'league_reports': len(cohorts),
            'independently_replayed_historical_arm_rows': len(new_rows) * len(ARMS)}



def check_selections(rows):
    from optimization.evaluate import settle_ou

    for row in rows:
        home, away = row['actual']
        label = 'home' if home > away else 'away' if away > home else 'draw'
        for arm in ARMS:
            picks, observed = row['forecasts'][arm], row['outcomes'][arm]
            total = picks['total']
            settlement = settle_ou(home + away, row['line'], total['direction'])
            truth = (picks['primary'] == f'{home}-{away}', picks['wdl'] == label,
                     None if settlement == 'PUSH' else settlement == 'FULL_WIN')
            prior.require(tuple(observed[k] for k in METRICS) == truth and total['line'] == row['line']
                          and observed['total_settlement'] == settlement, 'incorrect settlement: ' + row['match_id'])


def verify_transfer(source):
    transfer = EXPERIMENT / 'transfer'
    prior.checked(transfer / 'transfer-protocol.json', TRANSFER_PROTOCOL_SHA256)
    receipt = prior.read(transfer / 'refit-receipt.json')
    original = {'sequence': SEQUENCE / 'history/artifact.json', 'transformer': EXPERIMENT / 'history/artifact.json'}
    for model, path in original.items():
        metadata = receipt['artifacts'][model]
        saved = json.loads(prior.checked(path, metadata['retained_sha256']))
        refit = json.loads(prior.checked(transfer / f'{model}-before-season.json', metadata['refit_sha256']))
        prior.require(refit.pop('cutoff_at') == receipt['cutoff'] == '2026-08-01T00:00:00Z' and
                      saved.pop('cutoff_at') == '2026-11-18T00:00:00Z' and refit == saved and
                      refit['training_matches'] == receipt['n'] == 3036 and refit['sample_sha256'] == metadata['sample_sha256'],
                      'preseason and retained weights disagree for ' + model)

    europe_file = 'europe-2627-predictions.jsonl.gz'
    europe_report = 'europe-2627-validation.json'
    study = prior.read(transfer / europe_report)
    prior.checked(transfer / europe_file, study['prediction_archive_sha256'])
    european = prior.records(transfer / europe_file)
    brazil_report = prior.read(transfer / 'brazil/report.json')
    brazil = prior.records(transfer / 'brazil/rows.jsonl.gz')
    with tempfile.TemporaryDirectory() as tmp:
        temp = Path(tmp)
        for script in (transfer / 'evaluate.py', transfer / 'brazil/replay.py'):
            subprocess.run([sys.executable, str(script), '--source', str(source.resolve()), '--out', tmp],
                           check=True, stdout=sys.stderr)
        # The archived hashes commit exact bytes; cross-platform numerical replays use float tolerances.
        computed = prior.read(temp / europe_report)
        prior.compare({k: v for k, v in computed.items() if k != 'prediction_archive_sha256'},
                      {k: v for k, v in study.items() if k != 'prediction_archive_sha256'}, 'European transfer report')
        for expected, actual in zip(european, prior.records(temp / europe_file), strict=True):
            prior.require(expected['sequence_sources'] == actual.pop('sequence_sources') and
                          all(s is None or s[-1] < expected['matchday'] for team in expected['sequence_sources'] for s in team),
                          'later-season historical feature identity or chronology')
            prior.compare(actual, {k: v for k, v in expected.items() if k != 'sequence_sources'}, expected['match_id'])
        prior.compare(prior.records(temp / 'rows.jsonl.gz'), brazil, 'replayed original Brazil Current')
        prior.compare(prior.read(temp / 'report.json'), brazil_report, 'Brazil transfer report')

    check_selections(european + brazil)
    check_ids = {r['match_id'] for r in european}
    excluded = [r for r in study['exclusions'] if 'match_id' in r]
    prior.require(len(check_ids) == len(european) == study['evaluated'] and
                  len({r['match_id'] for r in excluded}) == len(excluded) and
                  check_ids.isdisjoint(r['match_id'] for r in excluded) and
                  len(european) + len(excluded) == study['population_played_in_source'] and
                  study['last_model_training_game'] == receipt['last_training_date'] == '2026-05-24' and
                  all(receipt['cutoff'][:10] < r['matchday'] <= '2026-11-17' for r in european),
                  'transfer denominators or calendar dates changed')
    prior.compare(summarize(european), study['comparison'], 'later-season paired results')
    for cohort, group in study['by_cohort'].items():
        selected = [r for r in european if r['cohort'] == cohort]
        prior.require(len(selected) == study['inventory'][cohort]['evaluated'], 'per-league transfer coverage')
        prior.compare(summarize(selected), group, cohort + ' later-season paired results')
    original_current = prior.records(EXPERIMENT.parent / '20261118-three-arm/training/actual_current.jsonl.gz')
    nine = [r for r in original_current if r['cohort'] == 'bra.1']
    eligible = {r['match_id'] for r in nine if r['market'] is not None}
    prior.require(brazil_report['registered_archived_forecasts'] == len(nine) == 9 and
                  eligible == {r['match_id'] for r in brazil} and len(brazil) == len(eligible) == 2 and
                  {r['match_id'] for r in nine if r['market'] is None} == set(brazil_report['missing_paired_market']) and
                  {r['matchday'] for r in brazil} == {'2026-11-14'} and brazil_report['real_forward'] is False,
                  'Brazil original market and date coverage')
    prior.compare(summarize(brazil), brazil_report['summary'], 'Brazil paired results')
    return {'later_season_eligible': len(european), 'later_season_played': study['population_played_in_source'],
            'brazil_current_eligible': len(eligible), 'brazil_current_archived': len(nine)}


def verify(source):
    sys.path[:0] = [str(source.resolve()), str(source.resolve() / 'runtime')]
    from research.analysis_freeze import aware, verify as verify_record
    from research_program import transformer_forward

    protocol = json.loads(prior.checked(EXPERIMENT / 'registration/protocol.json', PROTOCOL_SHA256))
    result = verify_historical(protocol)
    batch = EXPERIMENT / 'forward'
    plan = verify_record(prior.read(batch / 'plan.json'))
    prior.require(plan['payload']['binding']['registration'] == PROTOCOL_SHA256 and
                  plan['payload']['arms'] == protocol['arms'] and plan['payload']['automatic_promotion'] is False,
                  'forward arms or registration differ')
    ids = {r['match_id'] for r in protocol['fixtures']}
    cutoff = aware(plan['fixture']['cutoff_at'])
    for fixture in protocol['fixtures']:
        prior.require(aware(protocol['recorded_at']) <= cutoff < aware(fixture['kickoff_at']), 'not a future forecast')
    prior.require(len(ids) == 6 and {r['match_id'] for r in plan['payload']['fixtures']} == ids, 'forward population differs')
    replay = transformer_forward.replay(DATA, batch)
    prior.require(replay == {'population': 6, 'first_issues': 6, 'restored_current': 6, 'market_pairs': 6,
                            'matrix_and_selection_replays': 24, 'plan_sha256': plan['record_sha256']},
                  'missing registered original scores, markets or estimates')
    return {**result, 'forward_replay': replay, 'transfer': verify_transfer(source)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.source), sort_keys=True, indent=2))
