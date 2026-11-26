"""Bind retained R13 score grids and diagnose the location of a regulation result."""

from collections import Counter
import json

import numpy as np

from research.analysis_freeze import aware
from research_program import all_scope_model as model
from research_program import goal_state_forward as ledger
from research_program.goal_state_study import sha
from research_program.r9_team_shape import actual_rank

import prepare


RETAINED = {
    'uecl': ('20261126-r34-europe-winning-margin', 'uecl-r34-winning-margin-20261126'),
    'uel': ('20261126-r38-europe-domestic-opponents', 'uel-r38-domestic-opposition-20261126'),
}
TOTAL = model.H + model.A


def retained_grids(original, published, *, at=None):
    grids, references = {}, {}
    for short, group in original.items():
        package, track = RETAINED[short]
        folder = prepare.HERE.parent / package / 'issued'
        display_path = folder / 'display.json'
        if at is not None and not display_path.is_file():
            continue
        display = prepare.read(display_path)
        publication = ledger._read(folder, display)
        if at is not None and aware(publication['recorded_at']) > at:
            continue
        index = prepare.read(folder / 'receipts.json')
        registration = ledger._read(folder, index['registration'])
        fixtures = {row['fixture']['match_id']: row['fixture'] for row in group['rows']}
        end = aware(publication['recorded_at'])
        start = aware(registration['recorded_at'])
        original_display = published[short]
        if (len(fixtures) != 18 or fixtures.keys() != index['matches'].keys()
                or not aware(original_display['recorded_at']) <= start <= end < min(aware(f['kickoff_at']) for f in fixtures.values())
                or registration['payload']['fixtures'] != fixtures or registration['payload']['track'] != track
                or registration['payload']['identity']['original_display'] != original_display['sha256']
                or publication['payload'] != dict(fixtures=fixtures, track=track + '-display', identity=dict(
                    registration=registration['record_sha256'], receipts_sha256=sha(folder / 'receipts.json'),
                    table_sha256=sha(folder / 'scores.md')))):
            raise ValueError('retained score-grid issues differ from the original round: ' + short)
        references[short] = dict(package=package, registration=index['registration'], display=display,
                                 original_display=original_display)
        for row in group['rows']:
            fixture = row['fixture']
            mid = fixture['match_id']
            ref = index['matches'][mid]
            record = ledger._read(folder, ref)
            saved = record['payload']
            grid = np.asarray(saved['grids']['r13'], dtype=float)
            if (record['fixture'] != dict(fixture, cutoff_at=registration['recorded_at']) or record['track'] != track
                    or not start <= aware(record['recorded_at']) <= end
                    or saved['registration_sha256'] != registration['record_sha256']
                    or saved['original_first'] != row['first'] or saved['forecasts']['r13'] != row['forecast']
                    or saved['original_price'] != row['odds_source_first']
                    or saved['original_price_cutoff'] != row['source_odds_cutoff_at']
                    or grid.shape != TOTAL.shape or not np.all(np.isfinite(grid)) or np.any(grid < 0.)
                    or not np.isclose(grid.sum(), 1., rtol=0., atol=2e-12)):
                raise ValueError('retained score grid differs from its first issue: ' + mid)
            grids[mid] = dict(matrix=grid, receipt=ref, recipe_sha256=saved['original_recipe_sha256'])
    return grids, references


def shape(ordered):
    cells = [tuple(map(int, score.split('-'))) for score in ordered]
    return cells, [side for side in range(2) if all(cell[side] > 0 for cell in cells)], max(map(sum, cells))


def pregame(grid, ordered):
    cells, omitted, highest = shape(ordered)
    raw = model.top_three_scores(grid)
    zero = [float(grid[0, :].sum()), float(grid[:, 0].sum())]
    excluded = sum(zero[side] for side in omitted) - (grid[0, 0] if len(omitted) == 2 else 0.)
    return dict(original_scores=ordered, matrix_top_three=raw, same_first=raw[0] == ordered[0],
                same_three_members=set(raw) == set(ordered), probabilities=dict(
                    first=round(float(grid[cells[0]]), 12), three=round(float(sum(grid[cell] for cell in cells)), 12),
                    home_zero=round(zero[0], 12), away_zero=round(zero[1], 12), any_omitted_zero=round(float(excluded), 12),
                    above_displayed_max_total=round(float(grid[TOTAL > highest].sum()), 12)),
                omitted_zero_sides=[('home', 'away')[side] for side in omitted], maximum_displayed_total=highest)


def settled(grid, ordered, actual):
    if actual is None:
        return None
    score = tuple(actual)
    in_grid = all(0 <= value < width for value, width in zip(score, grid.shape, strict=True))
    rank = actual_rank(grid, score) if in_grid else None
    cells, omitted, highest = shape(ordered)
    return dict(matrix_rank=rank, in_grid=in_grid, matrix_probability=round(float(grid[score]), 12) if in_grid else 0.,
                matrix_first_not_displayed_first=rank == 1 and score != cells[0],
                matrix_top_three_omitted=rank is not None and rank <= 3 and score not in cells,
                actual_in_omitted_zero_path=any(score[side] == 0 for side in omitted),
                actual_above_displayed_max_total=sum(score) > highest)


def result_summary(paths):
    settled_paths = [row for row in paths if row is not None]
    rank_counts = Counter(row['matrix_rank'] for row in settled_paths)
    return dict(verified=len(settled_paths),
                matrix_ranks=dict(first=rank_counts[1], second_or_third=rank_counts[2] + rank_counts[3],
                                  fourth_through_sixth=sum(rank_counts[rank] for rank in range(4, 7)),
                                  seventh_or_below=sum(count for rank, count in rank_counts.items() if rank and rank >= 7),
                                  outside_grid=rank_counts[None]),
                **{key: sum(row[key] for row in settled_paths) for key in (
                    'matrix_first_not_displayed_first', 'matrix_top_three_omitted', 'actual_in_omitted_zero_path',
                    'actual_above_displayed_max_total')})


def verify():
    from forward_sources import original_grids

    original = prepare.scores(prepare.register(False))
    displays = prepare.publication(original, False)
    retained, references = retained_grids(original, displays)
    scopes = {}
    for short, group in original.items():
        code = prepare.COMPETITIONS[short][0]
        scopes[short] = {}
        for mid, rebuilt in original_grids(group['rows'], code):
            saved = retained[mid]
            if saved['recipe_sha256'] != rebuilt['original_recipe_sha256']:
                raise ValueError('retained matrix was built with a different R13 recipe: ' + mid)
            np.testing.assert_allclose(saved['matrix'], rebuilt['grid'], rtol=0., atol=2e-12)
            scopes[short][mid] = dict(receipt=saved['receipt'], recipe_sha256=saved['recipe_sha256'],
                                      **pregame(saved['matrix'], rebuilt['forecast']['top3']))
    summary = {}
    for short, rows in scopes.items():
        summary[short] = dict(fixtures=len(rows), matrix_same_first=sum(r['same_first'] for r in rows.values()),
                              matrix_same_three_members=sum(r['same_three_members'] for r in rows.values()),
                              model_expected_first_hits=round(sum(r['probabilities']['first'] for r in rows.values()), 6),
                              model_expected_three_hits=round(sum(r['probabilities']['three'] for r in rows.values()), 6),
                              expected_omitted_zero=round(sum(r['probabilities']['any_omitted_zero'] for r in rows.values()), 6),
                              expected_above_displayed_max_total=round(sum(r['probabilities']['above_displayed_max_total']
                                                                         for r in rows.values()), 6))
    return dict(reconstruction='Retained R13 baseline and original recipe independently matched on the entire score grid',
                sources=references, summary=summary, matches=scopes)


if __name__ == '__main__':
    print(json.dumps(verify(), ensure_ascii=False, indent=2, allow_nan=False))
