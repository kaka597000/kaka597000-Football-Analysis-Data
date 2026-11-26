"""Freeze and review the complete R38 Europa League research comparison."""

import argparse
from datetime import datetime, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

import numpy as np

from publication import atomic_json, deliver
from research.analysis_freeze import aware
from research_program import europe_domestic_opponents as model
from research_program import europe_score_dispersion as replay
from research_program import goal_state_forward as ledger
from research_program import r9_team_shape as shape
from research_program.goal_state_study import read_lines, sha, write_new
from research_program.paired_kpi_inference import compare
from storage_lock import exclusive_lock

HERE = Path(__file__).resolve().parent
ORIGINAL = HERE.parent/'20261126-europe-first-display'
sys.path.insert(0, str(ORIGINAL))
import prepare
from forward_sources import original_grids


CODE = 'uefa.europa'
TRACK = 'uel-r38-domestic-opposition-20261126'
ISSUED = HERE/'issued'


def contract():
    protocol_path = HERE/'forward-protocol.json'
    summary_path = HERE/'replay/summary.json'
    protocol, summary = map(prepare.read, (protocol_path, summary_path))
    screened = summary['competitions'][CODE]
    if (sha(summary_path) != protocol['historical_summary_sha256'] or protocol['competition'] != CODE
            or protocol['matchday'] != prepare.COMPETITIONS['uel'][4] or not screened['forward_screen_passed']
            or screened['selected'] == 'r13' or model.ARMS[screened['selected']] != protocol['dose']
            or summary['protocol_sha256'] != sha(model.PROTOCOL) or summary['protocol_sha256'] != sha(HERE/'protocol.json')):
        raise ValueError('the independent recipe did not pass its registered historical screen')
    scopes = prepare.register(False)
    rounds = prepare.scores(scopes)
    receipt = prepare.publication(rounds, False)['uel']
    rows = rounds['uel']['rows']
    fixtures = {row['fixture']['match_id']: row['fixture'] for row in rows}
    if len(rows) != len(fixtures) or len(fixtures) != 18 or fixtures.keys() != scopes['uel']['today'].keys():
        raise ValueError('the complete original 18-fixture round is required')
    source = prepare.read(model.PROTOCOL)['archives']['domestic']
    identity = dict(version=protocol['version'], protocol_sha256=sha(protocol_path),
                    historical_summary_sha256=sha(summary_path), original_window=scopes['uel']['plan']['sha256'],
                    original_display=receipt['sha256'], domestic_archive=source, dose=protocol['dose'],
                    beta=screened['beta'], pairs=dict(vs_r13=['r13', 'r38'], vs_market=['market', 'r38']))
    return rows, fixtures, identity


def restore(rows, identity, fixtures):
    with TemporaryDirectory(prefix='r38-uel-domestic-') as directory:
        root = Path(directory)
        replay.unpack(HERE.parents[1], identity['domestic_archive'], root)
        domestic = root/'domestic/domestic.jsonl'
        digest = sha(domestic)
        records = model.regulation_domestic(read_lines(domestic))
    through = max(row['date'] for row in records)
    history = model.OppositionHistory(records)
    for row, (mid, source) in zip(rows, original_grids(rows, CODE), strict=True):
        fixture = fixtures[mid]
        day = aware(fixture['kickoff_at']).astimezone(timezone.utc).date().isoformat()
        if digest != source['domestic_sha256'] or through > source['domestic_through'] or through >= day:
            raise ValueError('domestic evidence differs from the original R13 pregame input: ' + mid)
        teams = [fixture[side].removeprefix('espn:') for side in ('home', 'away')]
        features, exposure = history.context(teams, day)
        original, grid = source['forecast'], source['grid']
        alternative = shape.adjust(grid, features, identity['beta'], identity['dose'])
        ordered = original['top3'] if alternative is grid else replay.base.top_three_scores(alternative)
        keys = ('line', 'original_first', 'original_price', 'original_price_cutoff', 'original_recipe_sha256')
        yield mid, dict({key: source[key] for key in keys}, domestic_sha256=digest, domestic_through=through,
                        forecasts=dict(r13=original, market=row['market'], r38=dict(original, primary=ordered[0], top3=ordered)),
                        exposure=exposure, correction_design=features.round(12).tolist(),
                        grids=dict(r13=grid.tolist(), r38=alternative.tolist()))


def table(rows, forecasts):
    lines = ['# 欧联 R38 赛前研究对照', '',
             '原赛前首版与精选按原登记结算。R38 使用原 R13 国内归档和原盘口。', '',
             '| 北京时间 | 对阵 | 原 R13 三选 | R38 首选 | R38 备选一 | R38 备选二 |',
             '|---|---|---|---:|---:|---:|']
    for row in rows:
        fixture = row['fixture']
        when = aware(fixture['kickoff_at']).astimezone(prepare.BEIJING).strftime('%m-%d %H:%M')
        picks = forecasts[fixture['match_id']]['forecasts']
        lines.append('| '+' | '.join([when, '–'.join(row['names_zh']), ' / '.join(picks['r13']['top3']),
                                      *picks['r38']['top3']])+' |')
    return ('\n'.join(lines)+'\n').encode()


def display_identity(plan):
    return dict(registration=plan['sha256'], receipts_sha256=sha(ISSUED/'receipts.json'),
                table_sha256=sha(ISSUED/'scores.md'))


def verify(rows, fixtures, identity, forecasts):
    index, display = (prepare.read(ISSUED/name) for name in ('receipts.json', 'display.json'))
    plan = index['registration']
    registered, published = (ledger._read(ISSUED, ref) for ref in (plan, display))
    opened = min(aware(f['kickoff_at']) for f in fixtures.values())
    start, end = map(aware, (registered['recorded_at'], published['recorded_at']))
    if (registered['payload'] != dict(identity=identity, fixtures=fixtures, track=TRACK)
            or published['payload'] != dict(identity=display_identity(plan), fixtures=fixtures, track=TRACK+'-display')
            or index['matches'].keys() != fixtures.keys() or not start <= end < opened
            or (ISSUED/'scores.md').read_bytes() != table(rows, forecasts)):
        raise ValueError('R38 registration, archived table or pregame chronology differs')
    for mid, ref in index['matches'].items():
        record = ledger._read(ISSUED, ref)
        expected = dict(forecasts[mid], registration_sha256=plan['sha256'])
        if (record['fixture'] != dict(fixtures[mid], cutoff_at=registered['recorded_at']) or record['track'] != TRACK
                or not start <= aware(record['recorded_at']) <= end
                or {k: v for k, v in record['payload'].items() if k != 'grids'} != {k: v for k, v in expected.items() if k != 'grids'}):
            raise ValueError('R38 first issue differs from the locked proposal: ' + mid)
        for role, grid in expected['grids'].items():
            np.testing.assert_allclose(record['payload']['grids'][role], grid, rtol=0., atol=2e-12)
    return display


def issue(rows, fixtures, identity):
    ISSUED.mkdir(exist_ok=True)
    with exclusive_lock(HERE/'.issue.lock'):
        slate = list(fixtures.values())
        plan = ledger.register(slate, identity, TRACK, ISSUED)
        forecasts = dict(restore(rows, identity, fixtures))
        if not (ISSUED/'display.json').exists():
            matches = {mid: ledger.issue(plan, dict(fixture, cutoff_at=plan['recorded_at']), forecasts[mid], TRACK, ISSUED)
                       for mid, fixture in fixtures.items()}
            atomic_json(ISSUED/'receipts.json', dict(registration=plan, matches=matches))
            deliver(ISSUED/'scores.md', table(rows, forecasts))
            display = ledger.register(slate, display_identity(plan), TRACK+'-display', ISSUED)
            atomic_json(ISSUED/'display.json', display)
        return verify(rows, fixtures, identity, forecasts)


def review(fixtures, identity, forecasts, state):
    spec = spec_from_file_location('europe_first_display_review', ORIGINAL/'review.py')
    first_review = module_from_spec(spec)
    spec.loader.exec_module(first_review)
    at = datetime.now(timezone.utc)
    confirmed, issues = first_review.results(state, fixtures, at)
    paired = []
    for mid, fixture in fixtures.items():
        result = confirmed.get(mid)
        pair = forecasts[mid]
        paired.append(dict(id=mid, cohort=CODE, line=pair['line'], forecast=pair['forecasts'],
                           date=aware(fixture['kickoff_at']).astimezone(prepare.BEIJING).date().isoformat(),
                           actual=[result['home'], result['away']] if result else None))
    return dict(as_of=at.astimezone(prepare.BEIJING).isoformat(), registered=len(fixtures), verified=len(confirmed),
                result_issues=issues, verified_sources={mid: item['confirmed_result_sources'] for mid, item in confirmed.items()},
                comparisons={name: compare(paired, baseline=arms[0], candidate=arms[1])
                             for name, arms in identity['pairs'].items()})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('issue', 'verify', 'review'))
    parser.add_argument('--result-state', type=Path)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    rows, fixtures, identity = contract()
    if args.mode == 'issue':
        print(issue(rows, fixtures, identity))
    else:
        forecasts = dict(restore(rows, identity, fixtures))
        print(verify(rows, fixtures, identity, forecasts))
        if args.mode == 'review':
            if not args.out:
                parser.error('review requires --out')
            write_new(args.out, review(fixtures, identity, forecasts, args.result_state))
