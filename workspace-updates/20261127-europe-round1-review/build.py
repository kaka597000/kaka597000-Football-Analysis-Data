"""Reproduce the original European first-round settlement from retained sources."""

import argparse
from collections import Counter
import csv
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from research.analysis_freeze import aware, verify
from research_program.goal_state_study import sha


HERE = Path(__file__).resolve().parent
ORIGINAL = HERE.parent / '20261126-europe-first-display'
COMPETITIONS = ('uecl', 'uel')
sys.path.insert(0, str(ORIGINAL))

import prepare
import result_intake


def original_review():
    # Some model imports place their own review module earlier on sys.path.
    spec = spec_from_file_location('europe_original_round_review', ORIGINAL / 'review.py')
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def process_evidence(state, fixture, match):
    ref = match['confirmed_result_sources'].get('espn')
    if ref is None:
        return None
    raw = json.loads(result_intake.raw_result(state, ref['path'], ref['sha256']))
    stats = {'totalShots', 'shotsOnTarget', 'expectedGoals', 'possessionPct', 'redCards', 'saves'}
    sources = {str(item['team']['id']): item.get('statistics', [])
               for item in (raw.get('boxscore') or {}).get('teams', [])}
    by_side = {}
    for side in ('home', 'away'):
        team = fixture[side].removeprefix('espn:')
        by_side[side] = {item['name']: item['displayValue'] for item in sources.get(team, [])
                         if item.get('name') in stats and isinstance(item.get('displayValue'), str)}
    events = [dict(clock=event.get('clock', {}).get('displayValue'), type=event['type']['type'], detail=event.get('text'))
              for event in raw.get('keyEvents', []) if event.get('scoringPlay') is True
              or 'red-card' in event.get('type', {}).get('type', '')]
    return dict(source=ref, stats=by_side, events=events)


def path_summary(rows, bands):
    completed = [row for row in rows.values() if row['actual'] is not None]
    actual = Counter(format_score(row['actual']) for row in completed)
    choices = [row for row in completed if row['original_forecast']['primary'] == '1-1']
    return dict(actual_scores=dict(sorted(actual.items())), actual_mean_goals=(
        round(sum(sum(row['actual']) for row in completed)/len(completed), 8) if completed else None),
        raw_expected_first_hits=bands['model_expected_first_hits'], raw_expected_three_hits=bands['model_expected_three_hits'],
        first_score_one_all_issued=len(choices), first_score_one_all_hits=sum(row['actual'] == [1, 1] for row in choices),
        actual_one_all=actual['1-1'], actual_first_alternate=sum(row['hit_rank'] == 2 for row in completed),
        actual_second_alternate=sum(row['hit_rank'] == 3 for row in completed))


def format_score(score):
    return '-'.join(map(str, score)) if score is not None else ''


def scorecard(report, original, path):
    header = ('赛事', '计划开球（北京时间）', '实际开球（北京时间）', '对阵', '原首选', '原备选一', '原备选二',
              '90分钟赛果', '命中顺位', '胜平负命中', '原观察盘线结算', '原矩阵名次', '赛果来源')
    with path.open('x', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream, lineterminator='\n')
        writer.writerow(header)
        for short in COMPETITIONS:
            results = report['competitions'][short]['per_match']
            for row in original[short]['rows']:
                fixture = row['fixture']
                result = results[fixture['match_id']]
                kickoff = (result['actual_kickoff'] or {}).get('actual_kickoff_at')
                rank = (result.get('score_grid_diagnosis') or {}).get('matrix_rank')
                writer.writerow((prepare.COMPETITIONS[short][3], aware(fixture['kickoff_at']).astimezone(prepare.BEIJING).isoformat(),
                                 kickoff, '–'.join(row['names_zh']), *row['forecast']['top3'], format_score(result['actual']),
                                 result['hit_rank'], result['hit']['wdl'], result['research_line_settlement'], rank,
                                 ' / '.join(sorted(result['confirmed_result_sources']))))


def build(out):
    manifests = [HERE / 'sources' / short / 'captures.json' for short in COMPETITIONS]
    cutoff = max(aware(item['captured_at']) for _, item in result_intake.capture_entries(manifests))
    fixtures = result_intake.registered_fixtures('round1')
    bindings = result_intake.official_bindings(fixtures)
    original = prepare.scores(prepare.register(False))
    bands = prepare.read(ORIGINAL / 'score-paths/round1.json')['summary']
    with TemporaryDirectory(prefix='europe-verified-round1-') as temp:
        state = Path(temp) / 'state'
        intake = result_intake.assemble(manifests, state, fixtures, bindings, cutoff)
        report = original_review().review(state, at=cutoff.isoformat())
        report['capture_intake'] = {key: intake[key] for key in ('candidate_regulation_rows', 'captures_with_errors')}
        for short, group in report['competitions'].items():
            group['paths'] = path_summary(group['per_match'], bands[short])
            group['process_evidence'] = {mid: process_evidence(state, fixtures[mid], match)
                                         for mid, match in group['per_match'].items()}
    out.mkdir(parents=True, exist_ok=False)
    (out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    scorecard(report, original, out / 'scorecard.csv')


def check_review_seal():
    record = verify(prepare.read(HERE / 'review-freeze.json'))
    report = prepare.read(HERE / 'settlement/report.json')
    expected = {short: comp['display']['sha256'] for short, comp in report['competitions'].items()}
    if (record['stage'] != 'review' or record['track'] != 'europe-r13-first-window-settlement'
            or record['payload']['original_display_sha256'] != expected
            or record['payload']['report_sha256'] != sha(HERE / 'settlement/report.json')
            or record['payload']['scorecard_sha256'] != sha(HERE / 'settlement/scorecard.csv')
            or record['payload']['j1_capture_plan_sha256'] != sha(HERE / 'j1-capture-plan.json')
            or record['payload']['review_notes_sha256'] != sha(HERE / 'README.md')
            or not aware(record['fixture']['kickoff_at']) < aware(report['as_of']) <= aware(record['recorded_at'])):
        raise ValueError('archived review seal or original issue reference differs')


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--out', type=Path, required=True)
    cli.add_argument('--verify-seal', action='store_true')
    args = cli.parse_args()
    build(args.out)
    if args.verify_seal:
        check_review_seal()
