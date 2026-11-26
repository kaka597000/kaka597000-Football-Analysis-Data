"""Compare the frozen J1 authored and native score selections on the original ten fixtures."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from research.analysis_freeze import aware
from research_program import display_windows as windows, goal_state_forward as ledger
from research_program.paired_kpi_inference import compare
from research_program.r9_team_shape import actual_rank
from research_program.three_arm_model import _matrix, top_three_scores
from research_program.three_arm_review import _results, read


BEIJING = ZoneInfo('Asia/Shanghai')
PACKAGE = Path(__file__).resolve().parents[1]
PRIOR = PACKAGE.parent / '20261125-j1-stage-windows'
SECOND = PACKAGE / 'nov28_29'
ROLES = ('current', 'test')
METRICS = ('score_top1', 'score_top3')


def cells(scores):
    return [tuple(map(int, score.split('-'))) for score in scores]


def native_scores(model, ordered):
    matrix = _matrix(model['matrix'])
    scores = top_three_scores(matrix)
    signed = model['top3']
    if (scores != [item['score'] for item in signed] or scores[0] != model['primary']
            or any(abs(matrix[cell] - item['probability']) > 2e-12
                   for cell, item in zip(cells(scores), signed, strict=True))):
        raise ValueError('native score picks differ from their retained matrix')
    displayed = cells(ordered)
    return matrix, dict(model_version=model['version'], matrix_sha256=model['matrix_hash'], scores=scores,
                        displayed_ranks=[actual_rank(matrix, cell) for cell in displayed],
                        displayed_first_probability=round(float(matrix[displayed[0]]), 12),
                        displayed_three_probability=round(float(sum(matrix[cell] for cell in displayed)), 12),
                        native_first_probability=round(float(matrix[cells(scores)[0]]), 12),
                        native_three_probability=round(float(sum(item['probability'] for item in signed)), 12),
                        same_first=ordered[0] == scores[0], same_three_members=set(ordered) == set(scores),
                        native_first_covered=scores[0] in ordered)


def load():
    entries = read(SECOND / 'entries.json')
    message = (SECOND / 'message.txt').read_text(encoding='utf-8')
    plan, fixtures, identity = windows.prepared_batch(PRIOR / 'registration', 'nov28_29', entries, message, SECOND)
    display_ref = read(SECOND / 'publication.json')
    display = ledger._read(SECOND, display_ref)
    by_id = {f['match_id']: f for f in fixtures}
    if (len(by_id) != 10 or display['payload']['fixtures'] != by_id or display['payload']['identity'] != identity
            or aware(display['recorded_at']) >= min(aware(f['kickoff_at']) for f in fixtures)):
        raise ValueError('complete archived J1 first display required')

    rows, grids = {}, {}
    for fixture in sorted(fixtures, key=lambda f: (aware(f['kickoff_at']), f['match_id'])):
        mid = fixture['match_id']
        entry, original = entries[mid], identity['rows'][mid]
        author = ledger._read(SECOND, entry['authored'])
        pair = ledger._read(SECOND, entry['pair'])
        if aware(author['recorded_at']) > aware(display['recorded_at']):
            raise ValueError('J1 authored forecast followed its display lock: ' + mid)
        ordered = original['displayed_scores']
        grids[mid], native = {}, {}
        for role in ROLES:
            grids[mid][role], native[role] = native_scores(pair['payload'][role + '_model'], ordered)
        current, test = (native[role]['scores'] for role in ROLES)
        missed = [score for score in current if score in test and score not in ordered]
        market = author['payload']['baseline_comparison']['market']['forecast']['top3']
        rows[mid] = dict(fixture=fixture, names=author['payload']['team_names_zh'], frozen=entry, authored=ordered,
                         selected_rank=identity['selected'].index(mid) + 1 if mid in identity['selected'] else None,
                         native=native, native_first_disagrees=current[0] != test[0],
                         both_native_firsts_covered=all(n['native_first_covered'] for n in native.values()),
                         agreed_native_scores_omitted=missed, observed_market_scores=market,
                         strict_market_status=pair['payload']['market_baseline']['status'])
    return by_id, rows, grids, dict(plan=plan['freeze_id'], display=display_ref, selected=identity['selected'])


def summarize(rows):
    natives = {role: [row['native'][role] for row in rows.values()] for role in ROLES}
    return dict(fixtures=len(rows), native_first_disagreements=sum(row['native_first_disagrees'] for row in rows.values()),
                both_native_firsts_covered=sum(row['both_native_firsts_covered'] for row in rows.values()),
                authored_differs_from_shared_first=sum(not row['native_first_disagrees'] and not row['native']['current']['same_first']
                                                      for row in rows.values()),
                agreed_native_score_omissions=sum(bool(row['agreed_native_scores_omitted']) for row in rows.values()),
                native={role: dict(**{key: sum(row[key] for row in items) for key in ('same_first', 'same_three_members')},
                                   **{key.replace('_probability', '_expected_hits'): round(sum(row[key] for row in items), 6)
                                      for key in ('displayed_first_probability', 'displayed_three_probability',
                                                  'native_first_probability', 'native_three_probability')})
                        for role, items in natives.items()})


def review(fixtures, rows, grids, state, cutoff):
    state = state.resolve()
    if (state / 'normalized-results.jsonl').is_file():
        actuals, issues = _results(state, fixtures, cutoff)
    else:
        actuals, issues = {}, {mid: ['normalized result archive missing'] for mid in fixtures}
    comparison_rows, diagnostics = [], {}
    for mid, row in rows.items():
        found = actuals.get(mid)
        actual = (found['home'], found['away']) if found else None
        orders = dict(authored=row['authored'], observed_market=row['observed_market_scores'],
                      **{role: row['native'][role]['scores'] for role in ROLES})
        fixture = fixtures[mid]
        day = aware(fixture['kickoff_at']).astimezone(BEIJING).date().isoformat()
        comparison_rows.append(dict(id=mid, cohort=fixture['cohort'], date=day, actual=actual, line=None,
                                    forecast={role: dict(primary=scores[0], top3=scores) for role, scores in orders.items()}))
        if actual is not None:
            score = f'{actual[0]}-{actual[1]}'
            ranks = {role: actual_rank(matrix, actual) if all(g < n for g, n in zip(actual, matrix.shape, strict=True))
                     else None for role, matrix in grids[mid].items()}
            diagnostics[mid] = dict(actual=actual, matrix_ranks=ranks, source=found['source'],
                                    scores={role: dict(first_hit=score == values[0], three_hit=score in values)
                                            for role, values in orders.items()},
                                    agreed_omitted_score_realized=score in row['agreed_native_scores_omitted'])
    comparisons = {}
    for baseline in (*ROLES, 'observed_market'):
        paired = compare(comparison_rows, baseline=baseline, candidate='authored')
        comparisons[baseline] = dict(tracks={track: {key: group['metrics'][key] for key in METRICS}
                                            for track, group in paired['tracks'].items()},
                                     paired={key: paired['paired'][key] for key in METRICS})
    return dict(as_of=cutoff.astimezone(BEIJING).isoformat(), verified=len(actuals), pending=len(fixtures)-len(actuals),
                observed_market_role='QUOTE_CLOCK_UNVERIFIED', comparisons=comparisons,
                per_match=diagnostics, result_issues=issues)


def report(result_state=None, *, at=None):
    fixtures, rows, grids, sources = load()
    output = dict(sources=sources, summary=summarize(rows), matches=rows)
    if result_state is not None:
        now = datetime.now(timezone.utc)
        cutoff = aware(at) if at else now
        if not aware(sources['display']['recorded_at']) <= cutoff <= now:
            raise ValueError('result cutoff is outside the archived first-display timeline')
        output['score_review'] = review(fixtures, rows, grids, result_state, cutoff)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--result-state', type=Path)
    parser.add_argument('--at')
    args = parser.parse_args()
    print(json.dumps(report(args.result_state, at=args.at), ensure_ascii=False, indent=2, allow_nan=False))
