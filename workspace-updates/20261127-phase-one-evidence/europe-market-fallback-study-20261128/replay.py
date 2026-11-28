"""Replay fixed R13 market-availability arms on the original settled European fixtures."""

import argparse
from collections import Counter
from datetime import date, timezone
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from research.analysis_freeze import aware, verify
from research_program import all_scope_model as base
from research_program import continuation_forward as r7
from research_program import domestic_form as r13
from research_program import europe_score_dispersion as archive
from research_program import goal_state_forward as ledger
from research_program import r10_shot_model as heads
from research_program.goal_state_study import read_lines
from research_program.paired_kpi_inference import compare


COMPETITIONS = {'uel': 'uefa.europa', 'uecl': 'uefa.europa.conf'}
ARMS = ('wdl_only', 'no_market')


def read(path):
    return json.loads(path.read_bytes())


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def matchdays(plan):
    return {record['match_id']: dict(record, scheduled=wave['scheduled'])
            for wave in plan['waves'] for record in wave['fixtures']}


def utc_date(value):
    return aware(value).astimezone(timezone.utc).date().isoformat()


def domestic_design(history, fixture, target, cutoff):
    teams = [r13.team_id(fixture[side].removeprefix('espn:')) for side in ('home', 'away')]
    return history.context(teams, target, cutoff=cutoff)


def match_record(original, prices, expected, label, history, recipe, anchor, recipe_hash, baseline_hash, domestic_hash):
    fixture, payload = original['fixture'], original['payload']
    r5 = prices['fixture']
    if (any(fixture[k] != expected[k] or r5[k] != expected[k] for k in ('match_id', 'home', 'away'))
            or fixture['cohort'] != COMPETITIONS[expected['competition']] or fixture['stage'] != r5['stage']
            or aware(fixture['kickoff_at']) != aware(expected['scheduled'])
            or aware(r5['kickoff_at']) != aware(expected['scheduled'])
            or label['original_first']['sha256'] != original['record_sha256']
            or original['freeze_id'] != expected['original_research_first']
            or payload['odds_source_first_issue'] != prices['record_sha256']
            or payload['domestic_sha256'] != domestic_hash or payload['recipe_sha256'] != recipe_hash
            or recipe['baseline_sha256'] != baseline_hash or payload['domestic_through'] != history.through
            or recipe['doses'] != payload['doses']
            or set(label['confirmed_result_sources']) != {'uefa', 'espn'}):
        raise ValueError('original population, label or signed model differs: ' + fixture['match_id'])
    cutoff = fixture['cutoff_at']
    if (not aware(prices['recorded_at']) <= aware(cutoff) <= aware(original['recorded_at'])
            < aware(fixture['kickoff_at'])
            or max(recipe['through'], anchor['through'], history.through) >= utc_date(cutoff)):
        raise ValueError('original forecast input chronology differs')
    game = r7.frozen_game(fixture, prices['payload'])
    design, counts = domestic_design(history, fixture, game['date'], utc_date(cutoff))
    if (counts != payload['domestic_games'] or not np.allclose(design, payload['features'], atol=1e-14, rtol=0)
            or game['stage'] != 'league-phase' or base.actual_line(game) != payload['line']):
        raise ValueError('domestic features, phase or observed line did not reproduce')

    original_line = payload['line']
    prior = r7.matrix(game, anchor)
    control = base.pick(prior, original_line)
    adjusted = r13.adjust(prior, design, recipe['fitted'])
    first, grids = heads.decisions(prior, adjusted, recipe['doses'], original_line, payload['forecasts']['r7'])
    cells = [tuple(map(int, score.split('-'))) for score in first['top3']]
    probabilities = grids['score']
    if (first != payload['forecasts']['candidate'] or control != payload['forecasts']['local_r7']
            or first != label['original_forecast']
            or abs(probabilities[cells[0]] - payload['quality']['p_first']) > 2e-10
            or abs(sum(probabilities[cell] for cell in cells) - payload['quality']['p_three']) > 2e-10):
        raise ValueError('restored R13 selection or published probability differs')

    forecasts = {'first_issue': first}
    for name in ARMS:
        masked = dict(game, total=None, paired_market=False)
        if name == 'no_market':
            masked['h2h'] = None
        next_prior = r7.matrix(masked, anchor)
        next_control = base.pick(next_prior, None)
        next_full = r13.adjust(next_prior, design, recipe['fitted'])
        forecasts[name], _ = heads.decisions(next_prior, next_full, recipe['doses'], None, next_control)
        if forecasts[name]['total_line'] is not None or forecasts[name]['total_side'] is not None:
            raise ValueError('total pick generated without a retained line')
    return {'id': fixture['match_id'], 'date': game['date'], 'cohort': fixture['cohort'],
            'teams': expected['teams'], 'actual': label['actual'], 'line': original_line,
            'domestic_games': counts, 'forecast': forecasts, 'odds_mode_original': prices['payload']['market_mode'],
            'first_issue_sha256': original['record_sha256']}


def pending_coverage(next_plan, short, history, as_of):
    rows, coverage = [], Counter()
    for mid, entry in sorted(next_plan.items()):
        if entry['competition'] != short:
            continue
        target = utc_date(entry['scheduled'])
        x, counts = domestic_design(history, entry, target, as_of)
        covered = sum(n > 0 for n in counts)
        coverage[('neither', 'one', 'both')[covered]] += 1
        recent = []
        for side, count in zip(('home', 'away'), counts, strict=True):
            team = r13.team_id(entry[side].removeprefix('espn:'))
            recent.append(date.fromordinal(history.dates[team][-1]).isoformat() if count else None)
        rows.append({'match_id': mid, 'teams': entry['teams'], 'domestic_games': counts,
                     'latest_archived_domestic_day': recent,
                     'rest_or_14_day_load_difference_present': bool(np.any(x[:, 2:]))})
    return {'fixtures': len(rows), 'coverage': dict(coverage), 'rows': rows,
            'fixture_count_with_rest_or_load_difference': sum(
                row['rest_or_14_day_load_difference_present'] for row in rows)}


def replay(data, bundle):
    protocol_path = bundle / 'protocol.json'
    protocol = read(protocol_path)
    receipt = verify(read(bundle / 'protocol-freeze.json'))
    if (receipt['payload']['protocol_sha256'] != digest(protocol_path)
            or receipt['payload']['inputs'] != protocol['inputs']):
        raise ValueError('ablation protocol is not the one frozen before execution')
    specs = protocol['inputs']
    source = data / 'workspace-updates'
    for spec in specs.values():
        if digest(source / spec['path']) != spec['sha256']:
            raise ValueError('registered input differs: ' + spec['path'])
    population = matchdays(read(source / specs['population']['path']))
    next_population = matchdays(read(source / specs['next_population']['path']))
    reviewed = read(source / specs['regulation_labels']['path'])['competitions']
    if set(population) & set(next_population):
        raise ValueError('historical and next fixture windows overlap')
    with TemporaryDirectory(prefix='r13-market-availability-') as scratch:
        root = Path(scratch)
        for key in ('r13_complete_recipes', 'r13_actual_firsts', 'r13_actual_domestic', 'r5_actual_prices',
                    'r7_uel_estimator', 'r7_uecl_estimator'):
            archive.unpack(data, specs[key], root / key)
        domestic_path = root / 'r13_actual_domestic/domestic/domestic.jsonl'
        domestic_hash = digest(domestic_path)
        if domestic_hash != read(root/'r13_complete_recipes/inputs.json')['domestic_sha256']:
            raise ValueError('R13 source history differs')
        history = r13.DomesticHistory(read_lines(domestic_path))
        firsts = root / 'r13_actual_firsts'
        r5 = root / 'r5_actual_prices/issued'
        r13_index, r5_index = (read(p / 'receipts.json') for p in (firsts, r5))
        reports, all_rows = {}, {}
        for short, cohort in COMPETITIONS.items():
            recipe_path = root / 'r13_complete_recipes' / cohort / 'forward.json'
            baseline_path = root / f'r7_{short}_estimator/main/forward.json'
            recipe, anchor = map(read, (recipe_path, baseline_path))
            hashes = [digest(p) for p in (recipe_path, baseline_path)]
            if recipe['competition'] != cohort or anchor['competition'] != cohort:
                raise ValueError('model artifact belongs to a different competition')
            expected = {mid for mid, match in population.items() if match['competition'] == short}
            labels = reviewed[short]['per_match']
            if set(labels) != expected or len(labels) != protocol['registered_population_n_by_cohort'][cohort]:
                raise ValueError('past population or settled result scope differs')
            rows = []
            for mid in sorted(expected):
                issued = ledger._read(firsts, r13_index['matches'][mid])
                prices = ledger._read(r5, r5_index['matches'][mid])
                rows.append(match_record(issued, prices, population[mid], labels[mid], history, recipe, anchor,
                                         *hashes, domestic_hash))
            all_rows[cohort] = rows
            reports[cohort] = {
                'frozen_r13_reproduced': len(rows), 'recorded_market_modes': dict(
                    Counter(row['odds_mode_original'] for row in rows)),
                'as_issued_versus_masked_market': {arm: compare(rows, baseline='first_issue', candidate=arm) for arm in ARMS},
                'selection_changes': {arm: {
                    'first': sum(row['forecast'][arm]['primary'] != row['forecast']['first_issue']['primary'] for row in rows),
                    'three_membership': sum(set(row['forecast'][arm]['top3']) != set(row['forecast']['first_issue']['top3'])
                                            for row in rows)} for arm in ARMS},
                'prospective_input_coverage_from_archived_history': pending_coverage(
                    next_population, short, history, utc_date(receipt['recorded_at'])),
            }
    return {'evidence_status': protocol['evidence_status'], 'protocol_freeze': receipt['freeze_id'],
            'domestic_history_through': history.through, 'domestic_sha256': domestic_hash,
            'competitions': reports, 'rows': all_rows}


def check_future_plan(data, bundle):
    first = verify(read(bundle / 'round2-uel-research-freeze.json'))
    revised = verify(read(bundle / 'round2-uel-research-cutoff-revision.json'))
    plan = first['payload']
    clarified = revised['payload']
    protocol = read(bundle / 'protocol.json')
    scope = read(data / 'workspace-updates' / protocol['inputs']['next_population']['path'])
    expected = {mid: {'kickoff_at': row['scheduled'], 'home': row['home'], 'away': row['away'],
                      'uefa_id': row['uefa_id'], 'official_matchday': row['official_matchday']}
                for mid, row in matchdays(scope).items() if row['competition'] == 'uel'}
    if (plan['fixtures'] != expected or plan['original_eligibility_denominator'] != len(expected)
            or plan['original_window_registration'] != scope['competitions']['uel']['window_registration']
            or plan['evidence_selection_origin']['ablation_results_sha256'] != digest(bundle / 'verified.json')
            or first['stage'] != 'prematch' or revised['stage'] != 'prematch'
            or first['revision'] != 1 or revised['revision'] != 2
            or revised['previous_sha256'] != first['record_sha256']
            or revised['track'] != first['track'] or revised['fixture'] != first['fixture']
            or not aware(first['recorded_at']) <= aware(revised['recorded_at'])
            < min(aware(row['kickoff_at']) for row in expected.values())):
        raise ValueError('future research scope, quote-cutoff revision or sequence differs')
    equivalent = dict(clarified, arms=dict(clarified['arms'], r13_full_market=plan['arms']['r13_full_market']))
    if equivalent != plan:
        raise ValueError('cutoff language revision changed the registered method')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, required=True)
    args = parser.parse_args()
    bundle = Path(__file__).resolve().parent
    data = args.data_root.resolve()
    result = replay(data, bundle)
    check_future_plan(data, bundle)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False))
