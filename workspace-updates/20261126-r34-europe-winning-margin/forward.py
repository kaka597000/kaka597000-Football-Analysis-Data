"""Freeze and review the independent R34 Conference League comparison."""

import argparse
from datetime import datetime, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

import numpy as np

from publication import atomic_json, deliver
from research.analysis_freeze import aware
from research_program import continuation_forward as continuation
from research_program import domestic_form, europe_winning_margin as margins
from research_program import europe_score_dispersion as replay
from research_program import goal_state_forward as ledger
from research_program import r10_shot_model as decisions
from research_program.goal_state_study import sha, write_new
from research_program.paired_kpi_inference import compare
from storage_lock import exclusive_lock

HERE = Path(__file__).resolve().parent
ORIGINAL = HERE.parent/'20261126-europe-first-display'
sys.path.insert(0, str(ORIGINAL))
import prepare


CODE = 'uefa.europa.conf'
TRACK = 'uecl-r34-winning-margin-20261126'
ISSUED = HERE/'issued'


def inputs():
    protocol = prepare.read(HERE/'forward-protocol.json')
    summary = HERE/'replay/summary.json'
    if (sha(summary) != protocol['historical_summary_sha256'] or protocol['competition'] != CODE
            or protocol['matchday'] != prepare.COMPETITIONS['uecl'][4]):
        raise ValueError('independent comparison source differs')
    outcome = prepare.read(summary)['competitions'][CODE]
    coefficients = [outcome['coefficients'][name] for name in ('intercept', 'advantage')]
    if not outcome['forward_screen_passed'] or margins.DOSES[outcome['selected']] != protocol['dose']:
        raise ValueError('candidate does not match the registered historical screen')
    windows = prepare.register(False)
    rounds = prepare.scores(windows)
    publication = prepare.publication(rounds, False)['uecl']
    rows = rounds['uecl']['rows']
    fixtures = [row['fixture'] for row in rows]
    if len(fixtures) != 18 or {f['match_id'] for f in fixtures} != windows['uecl']['today'].keys():
        raise ValueError('the complete original Conference League round is required')
    identity = dict(version=protocol['version'], protocol_sha256=sha(HERE/'forward-protocol.json'),
                    historical_summary_sha256=sha(summary), original_window=rounds['uecl']['window']['sha256'],
                    original_display=publication['sha256'], dose=protocol['dose'], coefficients=coefficients,
                    comparison='INDEPENDENT_RESEARCH',
                    pairs={'vs_r13': ['r13', 'r34'], 'vs_market': ['market', 'r34']})
    return rows, fixtures, identity


def restore(rows, identity):
    """Recover each original score head from its exact prior inputs and signed recipe."""
    spec = prepare.read(replay.PROTOCOL)
    data = HERE.parents[1]
    with TemporaryDirectory(prefix='r34-uecl-original-') as directory:
        root = Path(directory)
        for kind in ('r5', 'r13'):
            path, checksum = prepare.ARCHIVES[kind]
            replay.unpack(data, dict(path=path, sha256=checksum), root/kind)
        replay.unpack(data, spec['archives']['r13'], root/'recipe')
        replay.unpack(data, spec['archives'][CODE]['r7'], root/'r7')
        recipe_path = root/'recipe'/CODE/'forward.json'
        baseline_path = root/'r7/main/forward.json'
        recipe, baseline = map(prepare.read, (recipe_path, baseline_path))
        if (recipe['competition'] != CODE or baseline['competition'] != CODE
                or sha(baseline_path) != recipe['baseline_sha256']):
            raise ValueError('the Conference League recipe references a different baseline')
        for row in rows:
            fixture = row['fixture']
            mid = fixture['match_id']
            original, ref, _ = prepare.original(root/'r13', mid)
            odds, odds_ref, _ = prepare.original(root/'r5/issued', mid)
            payload = original['payload']
            game = continuation.frozen_game(fixture, odds['payload'])
            if (ref != row['first'] or odds_ref != row['odds_source_first']
                    or payload['recipe_sha256'] != sha(recipe_path) or recipe['doses'] != payload['doses']
                    or game['stage'] != 'league-phase' or replay.base.actual_line(game) != payload['line']
                    or max(recipe['through'], baseline['through'], payload['domestic_through'])
                    >= aware(original['fixture']['cutoff_at']).astimezone(timezone.utc).date().isoformat()):
                raise ValueError('original recipe, price or source date differs: ' + mid)
            prior = continuation.matrix(game, baseline)
            full = domestic_form.adjust(prior, np.asarray(payload['features']), recipe['fitted'])
            original_pick, heads = decisions.decisions(prior, full, recipe['doses'], payload['line'], row['r7'])
            grid = heads['score']
            cells = [tuple(map(int, pick.split('-'))) for pick in original_pick['top3']]
            if (original_pick != row['forecast']
                    or abs(grid[cells[0]] - payload['quality']['p_first']) > 2e-10
                    or abs(sum(grid[cell] for cell in cells) - payload['quality']['p_three']) > 2e-10):
                raise ValueError('restored score head differs from its frozen picks: ' + mid)
            calibrated = grid
            ordered = original_pick['top3']
            if replay.base.top_three_scores(grid) == ordered:
                coefficients = identity['dose'] * np.asarray(identity['coefficients'])
                calibrated = margins.adjust(grid, margins.group_masses(grid), coefficients)
                ordered = replay.base.top_three_scores(calibrated)
            yield mid, dict(forecasts=dict(r13=original_pick, market=row['market'],
                                     r34=dict(original_pick, primary=ordered[0], top3=ordered)),
                            line=payload['line'], original_first=ref, original_price=odds_ref,
                            original_price_cutoff=row['source_odds_cutoff_at'],
                            original_recipe_sha256=sha(recipe_path),
                            grids={'r13': grid.tolist(), 'r34': calibrated.tolist()})


def table(rows, payloads):
    lines = ['# 欧协联 R34 赛前研究对照', '',
             '18 场使用原 R13 数据截止及市场观察。原赛前首版、精选和第一阶段继续按原登记结算。', '',
             '| 北京时间 | 对阵 | 原 R13 三选 | R34 首选 | R34 备选一 | R34 备选二 |',
             '|---|---|---|---:|---:|---:|']
    for row in rows:
        fixture = row['fixture']
        when = aware(fixture['kickoff_at']).astimezone(prepare.BEIJING).strftime('%m-%d %H:%M')
        forecasts = payloads[fixture['match_id']]['forecasts']
        scores = [' / '.join(forecasts['r13']['top3']), *forecasts['r34']['top3']]
        lines.append('| ' + ' | '.join([when, ' – '.join(row['names_zh']), *scores]) + ' |')
    return ('\n'.join(lines)+'\n').encode()


def verify(rows, fixtures, identity, payloads):
    index = prepare.read(ISSUED/'receipts.json')
    reg = ledger._read(ISSUED, index['registration'])
    rendered = table(rows, payloads)
    display = prepare.read(ISSUED/'display.json')
    archive = ledger._read(ISSUED, display)
    start = min(aware(f['kickoff_at']) for f in fixtures)
    publication_identity = dict(registration=reg['record_sha256'], receipts_sha256=sha(ISSUED/'receipts.json'),
                                table_sha256=sha(ISSUED/'scores.md'))
    expected_fixtures = {f['match_id']: f for f in fixtures}
    if (reg['payload'] != dict(identity=identity, fixtures=expected_fixtures, track=TRACK)
            or archive['payload'] != dict(identity=publication_identity, fixtures=expected_fixtures,
                                          track=TRACK+'-display')
            or index['matches'].keys() != expected_fixtures.keys() or (ISSUED/'scores.md').read_bytes() != rendered
            or not aware(reg['recorded_at']) <= aware(archive['recorded_at']) < start):
        raise ValueError('first published comparison or source registration differs')
    for mid, receipt in index['matches'].items():
        issue = ledger._read(ISSUED, receipt)
        fixture = dict(expected_fixtures[mid], cutoff_at=reg['recorded_at'])
        expected = dict(payloads[mid], registration_sha256=reg['record_sha256'])
        payload = issue['payload']
        if (issue['fixture'] != fixture or issue['track'] != TRACK
                or not aware(reg['recorded_at']) <= aware(issue['recorded_at']) <= aware(archive['recorded_at'])
                or {key: value for key, value in payload.items() if key != 'grids'}
                != {key: value for key, value in expected.items() if key != 'grids'}):
            raise ValueError('R34 first record differs: ' + mid)
        for role, grid in expected['grids'].items():
            np.testing.assert_allclose(payload['grids'][role], grid, rtol=0., atol=2e-12)
    return display


def issue(rows, fixtures, identity):
    ISSUED.mkdir(exist_ok=True)
    with exclusive_lock(ISSUED.parent/'.issue.lock'):
        plan = ledger.register(fixtures, identity, TRACK, ISSUED)
        payloads = dict(restore(rows, identity))
        if not (ISSUED/'display.json').exists():
            matches = {}
            for fixture in fixtures:
                mid = fixture['match_id']
                first = dict(fixture, cutoff_at=plan['recorded_at'])
                matches[mid] = ledger.issue(plan, first, payloads[mid], TRACK, ISSUED)
            atomic_json(ISSUED/'receipts.json', dict(registration=plan, matches=matches))
            deliver(ISSUED/'scores.md', table(rows, payloads))
            publication_identity = dict(registration=plan['sha256'], receipts_sha256=sha(ISSUED/'receipts.json'),
                                        table_sha256=sha(ISSUED/'scores.md'))
            display = ledger.register(fixtures, publication_identity, TRACK+'-display', ISSUED)
            atomic_json(ISSUED/'display.json', display)
        return verify(rows, fixtures, identity, payloads)


def review(fixtures, identity, payloads, state):
    spec = spec_from_file_location('europe_first_display_review', ORIGINAL/'review.py')
    first_review = module_from_spec(spec)
    spec.loader.exec_module(first_review)
    by_id = {f['match_id']: f for f in fixtures}
    at = datetime.now(timezone.utc)
    verified, issues = first_review.results(state, by_id, at)
    pairs = []
    for mid, fixture in by_id.items():
        labels = verified.get(mid)
        pairs.append(dict(id=mid, date=aware(fixture['kickoff_at']).astimezone(prepare.BEIJING).date().isoformat(),
                          cohort=CODE, line=payloads[mid]['line'], forecast=payloads[mid]['forecasts'],
                          actual=[labels['home'], labels['away']] if labels else None))
    return dict(as_of=at.astimezone(prepare.BEIJING).isoformat(), registered=len(by_id), verified=len(verified),
                result_issues=issues, verified_sources={mid: result['confirmed_result_sources']
                                                       for mid, result in verified.items()},
                comparisons={role: compare(pairs, baseline=arms[0], candidate=arms[1])
                             for role, arms in identity['pairs'].items()})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('issue', 'verify', 'review'))
    parser.add_argument('--result-state', type=Path)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    rows, fixtures, identity = inputs()
    if args.mode == 'issue':
        print(issue(rows, fixtures, identity))
    else:
        payloads = dict(restore(rows, identity))
        print(verify(rows, fixtures, identity, payloads))
        if args.mode == 'review':
            if not args.out:
                parser.error('review requires --out')
            write_new(args.out, review(fixtures, identity, payloads, args.result_state))
