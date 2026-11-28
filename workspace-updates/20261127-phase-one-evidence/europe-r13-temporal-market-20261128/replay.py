"""Replay fixed historical market-input comparisons in chronological European league phases."""

import argparse
from collections import Counter
from datetime import date
from itertools import groupby
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from research.analysis_freeze import verify
from research_program import all_scope_model as base
from research_program import all_scope_study as study
from research_program import continuation_scores as r7
from research_program import continuation_study as archive
from research_program import domestic_form as r13
from research_program import europe_score_dispersion as original
from research_program import r10_shot_model as heads
from research_program import r8_score_study as control
from research_program.goal_state_study import sha, write_new
from research_program.paired_kpi_inference import compare
from research_program.ucl_zero_goals import IDENTITY, reference_rows

MASKS = {
    'without_totals': dict(total=None, paired_market=False),
    'without_any_odds': dict(h2h=None, total=None, paired_market=False),
}
OUTPUTS = ('verified.json', 'fixtures.jsonl.gz')


def pinned(root, entry):
    path = root / entry['path']
    if sha(path) != entry['sha256']:
        raise ValueError('registered evidence changed: ' + entry['path'])
    return control.read(path)


def market_mode(game):
    valid_1x2 = base._prices(game.get('h2h'), base.SIDES) is not None
    valid_total = (base.actual_line(game) is not None
                   and base._prices(game['total'], ('over', 'under')) is not None)
    if valid_1x2 and valid_total:
        return 'paired' if game.get('paired_market') is True else 'unpaired_both'
    if valid_1x2:
        return '1x2_only'
    return 'total_only' if valid_total else 'no_market'


def reconstruct_masked(games, refs, settings, recipe, code):
    """Use the same prior state across all arms and update it after each whole date."""
    state = r7.blank()
    half_life = study.half_life(code)
    inputs = {name: ([], []) for name in MASKS}
    selected, modes = [], []
    selected_ids = {ref['id'] for ref in refs}
    for stamp, same_day in groupby(games, key=lambda game: game['date']):
        if stamp > refs[-1]['date']:
            break
        fixtures = list(same_day)
        day = date.fromisoformat(stamp).toordinal()
        base.advance(state['goals'], day, half_life)
        previous = [r7.prepare(state, fixture, day, half_life)[2] for fixture in fixtures]
        for fixture in fixtures:
            if fixture['id'] not in selected_ids:
                continue
            selected.append(fixture['id'])
            modes.append(market_mode(fixture))
            for name, mask in MASKS.items():
                masked = dict(fixture, **mask)
                prior, features, _ = r7.prepare(state, masked, day, half_life)
                inputs[name][0].append(prior)
                inputs[name][1].append(features)
        r7.update(state, fixtures, previous, day, half_life)
    if selected != [ref['id'] for ref in refs]:
        raise ValueError('masked population or order differs from the verified archive')

    forecasts = {name: control.matrices(np.asarray(priors), np.asarray(features), settings)
                 for name, (priors, features) in inputs.items()}
    rows = []
    for i, (ref, mode) in enumerate(zip(refs, modes, strict=True)):
        arms = {'archive': ref['forecast']['candidate']}
        for name, grids in forecasts.items():
            prior = grids[i]
            full = r13.adjust(prior, np.asarray(ref['features']), recipe['fitted'])
            arms[name], _ = heads.decisions(prior, full, recipe['doses'], None, base.pick(prior, None))
            if arms[name]['total_line'] is not None or arms[name]['total_side'] is not None:
                raise ValueError('a masked arm received a totals selection')
        if mode in ('no_market', '1x2_only'):
            key = 'without_any_odds' if mode == 'no_market' else 'without_totals'
            if any(arms[key][k] != arms['archive'][k] for k in ('primary', 'top3', 'wdl')):
                raise ValueError('unchanged market input changed an archive score or direction')
        rows.append(dict({key: ref[key] for key in IDENTITY}, market_input=mode, forecast=arms))
    return rows


def summarize(rows):
    comparisons, movement = {}, {}
    for name in MASKS:
        comparisons[name] = compare(rows, baseline='archive', candidate=name) if rows else None
        pairs = [(row['forecast']['archive'], row['forecast'][name]) for row in rows]
        movement[name] = {
            'first_changed': sum(a['primary'] != b['primary'] for a, b in pairs),
            'three_members_changed': sum(set(a['top3']) != set(b['top3']) for a, b in pairs),
        }
    return {'n': len(rows), 'comparisons': comparisons, 'movement': movement}


def run(data, bundle, out):
    protocol = control.read(bundle / 'protocol.json')
    receipt = verify(control.read(bundle / 'protocol-freeze.json'))
    if receipt['payload']['protocol_sha256'] != sha(bundle / 'protocol.json'):
        raise ValueError('historical replay registration changed')
    source = data / 'workspace-updates'
    reference = pinned(source, protocol['reference_protocol'])
    excluded = set()
    for plan in protocol['excluded_plans'].values():
        for wave in pinned(source, plan)['waves']:
            excluded.update(fixture['match_id'] for fixture in wave['fixtures'])
    result = {'status': protocol['evidence_status'], 'protocol_freeze': receipt['freeze_id'],
              'excluded_forward_fixtures': len(excluded), 'competitions': {}}
    retained = []
    with TemporaryDirectory(prefix='r13-historical-market-replay-') as scratch:
        root = Path(scratch)
        original.unpack(data, reference['archives']['r13'], root / 'r13')
        for code in reference['competitions']:
            folder = root / code
            for key in ('panel', 'r7'):
                original.unpack(data, reference['archives'][code][key], folder / key)
            panel = folder / 'panel/panel.jsonl'
            fitted = root / 'r13' / code
            settings, recipe = map(control.read, (folder / 'r7/main/fit.json', fitted / 'fit.json'))
            references = reference_rows(fitted / 'forecasts.jsonl.gz')
            refs, _ = original.original_grids(panel, settings, recipe, references, code, reference)
            if max(settings['bounds'][1], settings['training_through'], recipe['validation_through']) >= refs[0]['date']:
                raise ValueError('the frozen R7 or R13 recipe reaches the historical comparison')
            if excluded.intersection(ref['id'] for ref in refs):
                raise ValueError('a registered prospective fixture appeared in development')
            rows = reconstruct_masked(study.check_panel(panel, code), refs, settings, recipe, code)
            reports = {}
            for name, period in protocol['windows'].items():
                subset = [row for row in rows if period['from'] <= row['date'] < period['before']]
                if len(subset) != period[code]:
                    raise ValueError('historical replay did not recover the locked fixture count')
                paired = [row for row in subset if row['market_input'] == 'paired']
                reports[name] = {'first_date': subset[0]['date'], 'last_date': subset[-1]['date'],
                                 'market_inputs': dict(Counter(row['market_input'] for row in subset)),
                                 'all': summarize(subset), 'paired': summarize(paired)}
            if sum(report['all']['n'] for report in reports.values()) != len(rows):
                raise ValueError('locked cuts do not cover the full historical replay')
            retained.extend(rows)
            result['competitions'][code] = reports
    out.mkdir(parents=True, exist_ok=False)
    write_new(out / OUTPUTS[0], result)
    archive.put(out / OUTPUTS[1], retained)
    saved = bundle / 'review-freeze.json'
    if saved.exists():
        review = verify(control.read(saved))
        bound = {'protocol_freeze_sha256': receipt['record_sha256'],
                 'result_sha256': {name: sha(out / name) for name in OUTPUTS}}
        if review['stage'] != 'review' or review['model_promotion'] or review['payload'] != bound:
            raise ValueError('the rebuilt results do not match the frozen development review')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    run(args.data_root, Path(__file__).resolve().parent, args.out)
