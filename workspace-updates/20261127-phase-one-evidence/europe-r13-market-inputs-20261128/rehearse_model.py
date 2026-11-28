"""Apply locked R13 research recipes to the two distinct market input shapes."""

import argparse
from datetime import timezone
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
from research_program.goal_state_study import read_lines, sha, write_new
from research_program.r8_score_study import read

FULL = 'r13_full_market'
WDL = 'r13_wdl_only'


def forecasts(game, markets, anchor, recipe, design):
    if not game['competition'] == anchor['competition'] == recipe['competition'] == 'uefa.europa':
        raise ValueError('forecast input belongs to a different competition')
    if markets.keys() - {FULL, WDL} or (FULL in markets and (
            WDL not in markets or markets[FULL]['h2h'] != markets[WDL]['h2h'])):
        raise ValueError('R13 market comparison requires the same 1X2 in both arms')
    output = {}
    for arm, observed in markets.items():
        if set(observed) != {'h2h', 'total', 'paired_market'} or type(observed['paired_market']) is not bool:
            raise ValueError('an arm changed fields outside the permitted prices')
        trial = dict(game, **observed)
        line = base.actual_line(trial)
        if (not base._prices(observed['h2h'], base.SIDES)
                or (arm == FULL and (
                    not observed['paired_market'] or line is None
                    or not base._prices(observed['total'], ('over', 'under'))))
                or (arm == WDL and (observed['paired_market'] or observed['total'] is not None))):
            raise ValueError('incomplete or unexpected market fields for fixed input arm')
        prior = r7.matrix(trial, anchor)
        full = r13.adjust(prior, design, recipe['fitted'])
        output[arm], _ = heads.decisions(prior, full, recipe['doses'], line, base.pick(prior, line))
    return output


def replay(data, bundle):
    ablation = bundle / 'europe-market-fallback-study-20261128'
    protocol = read(ablation / 'protocol.json')
    locked = verify(read(ablation / 'protocol-freeze.json'))
    review = verify(read(ablation / 'review-freeze.json'))
    if (locked['payload']['protocol_sha256'] != sha(ablation / 'protocol.json')
            or review['payload']['artifact_sha256']['verified.json'] != sha(ablation / 'verified.json')):
        raise ValueError('original settled market replay differs from its freeze')
    old = read(ablation / 'verified.json')['rows']['uefa.europa']
    specs = protocol['inputs']
    keys = ('r7_uel_estimator', 'r13_complete_recipes', 'r13_actual_domestic', 'r13_actual_firsts', 'r5_actual_prices')
    with TemporaryDirectory(prefix='uel-fixed-r13-price-replay-') as folder:
        root = Path(folder)
        for key in keys:
            archive.unpack(data, specs[key], root / key)
        anchor_path = root / 'r7_uel_estimator/main/forward.json'
        anchor = read(anchor_path)
        recipe = read(root / 'r13_complete_recipes/uefa.europa/forward.json')
        if recipe['baseline_sha256'] != sha(anchor_path):
            raise ValueError('the fixed R13 recipe or its anchor differs')
        original = root / 'r13_actual_firsts'
        prices = root / 'r5_actual_prices/issued'
        original_index, prices_index = (read(path / 'receipts.json')['matches'] for path in (original, prices))
        history = r13.DomesticHistory(read_lines(root / 'r13_actual_domestic/domestic/domestic.jsonl'))
        differences = []
        for case in old:
            mid = case['id']
            issued = ledger._read(original, original_index[mid])
            quote = ledger._read(prices, prices_index[mid])
            fixture = issued['fixture']
            if (issued['record_sha256'] != case['first_issue_sha256']
                    or quote['record_sha256'] != issued['payload']['odds_source_first_issue']):
                raise ValueError('original forecast or price freeze differs')
            game = r7.frozen_game(fixture, quote['payload'])
            cutoff_date = aware(fixture['cutoff_at']).astimezone(timezone.utc).date().isoformat()
            design, _ = history.context([r13.team_id(fixture[key].split(':')[1]) for key in ('home', 'away')],
                                        case['date'], cutoff=cutoff_date)
            if not np.allclose(design, issued['payload']['features'], rtol=0, atol=1e-14):
                raise ValueError('rehearsal does not reproduce historical domestic features')
            original_market = {key: game[key] for key in ('h2h', 'total', 'paired_market')}
            fallback = dict(h2h=original_market['h2h'], total=None, paired_market=False)
            rebuilt = forecasts(game, {FULL: original_market, WDL: fallback}, anchor, recipe, design)
            if rebuilt != {FULL: case['forecast']['first_issue'], WDL: case['forecast']['wdl_only']}:
                differences.append(mid)
    if differences or len(old) != 18:
        raise ValueError(f'the two market arms failed to reproduce the original 18 matches: {differences}')
    return {'mode': 'SETTLED_OLD_WINDOW_MODEL_REHEARSAL', 'reproduced_pairs': len(old),
            'input_cutoff': 'ORIGINAL_PER_FIXTURE_FREEZE',
            'reference_results_sha256': sha(ablation / 'verified.json')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    write_new(args.out, replay(args.data_root, Path(__file__).resolve().parent.parent))
