"""Compare locked R7 total-goal dispersion adjustments across the five leagues."""

import argparse
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from research.analysis_freeze import verify
from research_program import all_scope_model as model
from research_program import all_scope_study as study
from research_program import continuation_scores as r7
from research_program import continuation_study as archive
from research_program import europe_score_dispersion as dispersion
from research_program import r8_score_study as control
from research_program.goal_state_study import sha, write_new
from research_program.paired_kpi_inference import compare
from research_program.ucl_zero_goals import IDENTITY, reference_rows

SCORE_METRICS = ('score_top1', 'score_top3')


def verified_grids(folder, code, start, stop):
    panel = folder / 'panel/panel.jsonl'
    stored = folder / 'r7/main'
    fit = control.read(stored / 'fit.json')
    if fit['competition'] != code or sha(panel) != fit['source_panel_sha256'] or fit['bounds'][1] > start:
        raise ValueError('R7 core fit predates the research window and must match the exact panel')
    games = study.check_panel(panel, code)
    refs = reference_rows(stored / 'forecasts.jsonl.gz')
    selected = [i for i, game in enumerate(games) if start <= game['date'] < stop]
    if {games[i]['id'] for i in selected} != {mid for mid, row in refs.items() if start <= row['date'] < stop}:
        raise ValueError('panel and frozen R7 replay have different date-slice coverage')
    all_grids, features, _ = r7.inputs(games, code)
    grids = control.matrices(all_grids[selected], features[selected], fit)
    output = []
    for index, grid in zip(selected, grids, strict=True):
        game = games[index]
        ref = refs[game['id']]
        actual = [game['home_goals'], game['away_goals']]
        line = model.actual_line(game)
        item = dict(game, actual=actual, cohort=code, line=line)
        if (any(item[key] != ref[key] for key in IDENTITY)
                or (game['stage'], game['score_basis']) != ('regular', 'regulation_90')
                or model.pick(grid, line) != ref['forecast']['candidate']
                or abs(grid[tuple(actual)] - ref['quality']['candidate']['p_observed']) > 2e-8):
            raise ValueError('R7 fixture, ordered scores or original probability could not be restored: ' + game['id'])
        output.append(ref)
    return output, grids


def total_outside(scores, actual):
    totals = [sum(map(int, score.split('-'))) for score in scores]
    return not min(totals) <= sum(actual) <= max(totals)


def apply(refs, grids, coeffs, doses):
    tilted, errors = dispersion.adjust(grids, coeffs)
    rows = []
    for ref, prior, updated in zip(refs, grids, tilted, strict=True):
        row = {key: ref[key] for key in IDENTITY}
        root = ref['forecast']['candidate']
        forecasts, losses, outside = {}, {}, {}
        for arm, dose in doses.items():
            matrix = prior if not dose else (1 - dose) * prior + dose * updated
            picks = root['top3'] if not dose else model.top_three_scores(matrix)
            forecasts[arm] = dict(root, primary=picks[0], top3=picks)
            losses[arm] = -np.log(max(1e-300, matrix[tuple(ref['actual'])]))
            outside[arm] = total_outside(picks, ref['actual'])
        rows.append(dict(row, forecast=forecasts, outside_total_range=outside,
                         exact_logloss={k: round(float(value), 12) for k, value in losses.items()}))
    return rows, {key: round(value, 14) for key, value in errors.items()}


def summarize(rows, doses):
    metrics = {}
    for arm in doses:
        if arm == 'r7':
            continue
        pair = compare(rows, baseline='r7', candidate=arm)
        if 'r7' not in metrics:
            metrics['r7'] = {'hits': pair['tracks']['r7']['metrics']}
        metrics[arm] = {'hits': pair['tracks'][arm]['metrics'], 'paired': pair['paired']}
    for arm in doses:
        metrics[arm]['outside_total_range'] = sum(row['outside_total_range'][arm] for row in rows)
        metrics[arm]['exact_logloss'] = round(float(np.mean([row['exact_logloss'][arm] for row in rows])), 12)
        metrics[arm]['primary_changes'] = sum(row['forecast'][arm]['primary'] != row['forecast']['r7']['primary']
                                              for row in rows)
    return metrics


def run(data, bundle, out):
    plan = control.read(bundle / 'protocol.json')
    receipt = verify(control.read(bundle / 'protocol-freeze.json'))
    if receipt['payload']['protocol_sha256'] != sha(bundle / 'protocol.json'):
        raise ValueError('the recorded five-league protocol has changed')
    periods, doses = plan['windows'], plan['arms']
    result = {'mode': plan['evidence_status'], 'registration': receipt['freeze_id'], 'competitions': {}}
    forecasts = []
    with TemporaryDirectory(prefix='big5-total-width-') as scratch:
        tmp = Path(scratch)
        for code, files in plan['archives'].items():
            home = tmp / code
            for name, spec in files.items():
                dispersion.unpack(data, spec, home / name)
            refs, matrices = verified_grids(home, code, periods['fit']['from'], periods['evaluation']['before'])
            indices = {name: [i for i, row in enumerate(refs) if span['from'] <= row['date'] < span['before']]
                       for name, span in periods.items()}
            if any(not group for group in indices.values()) or sum(map(len, indices.values())) != len(refs):
                raise ValueError('the prespecified date cuts must cover the full replay once')
            fit = indices['fit']
            observed = np.asarray([refs[i]['actual'] for i in fit])
            coeffs = dispersion.fit(dispersion.bucket_masses(matrices[fit]), observed)
            reports = {}
            for tag in ('selection', 'evaluation'):
                ix = indices[tag]
                rows, errors = apply([refs[i] for i in ix], matrices[ix], coeffs, doses)
                reports[tag] = {'fixtures': len(rows), 'days': len({row['date'] for row in rows}),
                                'max_numeric_error': errors, 'arms': summarize(rows, doses)}
                forecasts.extend(dict(row, split=tag) for row in rows)
            selection = reports['selection']['arms']
            base = selection['r7']['hits']
            eligible = [arm for arm, trial in selection.items() if all(
                trial['hits'][metric]['hits'] >= base[metric]['hits'] for metric in SCORE_METRICS)]
            chosen = min(eligible, key=lambda arm: (
                *(-selection[arm]['hits'][metric]['hits'] for metric in SCORE_METRICS),
                selection[arm]['exact_logloss'], doses[arm]))
            selected = reports['evaluation']['arms'][chosen]
            gains = [selected.get('paired', {}).get(metric, {}).get('net_hits', 0) for metric in SCORE_METRICS]
            result['competitions'][code] = {'fit_fixtures': len(fit), 'coefficients': coeffs,
                'selected': chosen, 'selected_evaluation_net_hits': dict(zip(SCORE_METRICS, gains, strict=True)),
                'passes_historical_screen': min(gains) >= 0 and max(gains) > 0, **reports}
    out.mkdir(parents=True, exist_ok=False)
    write_new(out / 'verified.json', result)
    archive.put(out / 'fixtures.jsonl.gz', forecasts)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    run(args.data_root, Path(__file__).resolve().parent, args.out)
