"""Read the original R13 score grids for full-slate European research comparisons."""

from datetime import timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from research.analysis_freeze import aware
from research_program import continuation_forward as continuation
from research_program import domestic_form
from research_program import europe_score_dispersion as replay
from research_program import r10_shot_model as decisions
from research_program.goal_state_study import sha

import prepare


def original_grids(rows, code):
    spec = prepare.read(replay.PROTOCOL)
    data = Path(__file__).resolve().parents[2]
    with TemporaryDirectory(prefix='europe-r13-original-') as directory:
        root = Path(directory)
        for kind in ('r5', 'r13'):
            path, checksum = prepare.ARCHIVES[kind]
            replay.unpack(data, dict(path=path, sha256=checksum), root/kind)
        replay.unpack(data, spec['archives']['r13'], root/'recipe')
        replay.unpack(data, spec['archives'][code]['r7'], root/'r7')
        recipe_path = root/'recipe'/code/'forward.json'
        baseline_path = root/'r7/main/forward.json'
        recipe, baseline = map(prepare.read, (recipe_path, baseline_path))
        recipe_sha = sha(recipe_path)
        if (recipe['competition'] != code or baseline['competition'] != code
                or sha(baseline_path) != recipe['baseline_sha256']):
            raise ValueError('the original R13 recipe references a different baseline')
        for row in rows:
            fixture = row['fixture']
            mid = fixture['match_id']
            original, ref, _ = prepare.original(root/'r13', mid)
            odds, odds_ref, _ = prepare.original(root/'r5/issued', mid)
            payload = original['payload']
            game = continuation.frozen_game(fixture, odds['payload'])
            cutoff = aware(original['fixture']['cutoff_at'])
            if (ref != row['first'] or odds_ref != row['odds_source_first']
                    or payload['recipe_sha256'] != recipe_sha or recipe['doses'] != payload['doses']
                    or game['stage'] != 'league-phase' or replay.base.actual_line(game) != payload['line']
                    or max(recipe['through'], baseline['through'], payload['domestic_through'])
                    >= cutoff.astimezone(timezone.utc).date().isoformat()):
                raise ValueError('original recipe, price or source date differs: ' + mid)
            prior = continuation.matrix(game, baseline)
            full = domestic_form.adjust(prior, np.asarray(payload['features']), recipe['fitted'])
            pick, heads = decisions.decisions(prior, full, recipe['doses'], payload['line'], row['r7'])
            grid = heads['score']
            cells = [tuple(map(int, score.split('-'))) for score in pick['top3']]
            if (pick != row['forecast'] or abs(grid[cells[0]] - payload['quality']['p_first']) > 2e-10
                    or abs(sum(grid[cell] for cell in cells) - payload['quality']['p_three']) > 2e-10):
                raise ValueError('restored score head differs from its frozen picks: ' + mid)
            yield mid, dict(forecast=pick, grid=grid, line=payload['line'], original_first=ref, original_price=odds_ref,
                            original_price_cutoff=row['source_odds_cutoff_at'], original_recipe_sha256=recipe_sha,
                            domestic_sha256=payload['domestic_sha256'], domestic_through=payload['domestic_through'])
