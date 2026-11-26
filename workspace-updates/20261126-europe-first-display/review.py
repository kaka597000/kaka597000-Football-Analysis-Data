"""Settle the original European score displays from retained 90-minute results."""

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path

import prepare
from research.analysis_freeze import aware
from research_program.nov25_first_review import seats
from research_program.paired_kpi_inference import _decisions, compare
from research_program.three_arm_review import _certify


SEASON_TYPES = {v[0]: v[2] for v in prepare.COMPETITIONS.values()}
SCOPE_SUFFIX = ':NEW_FORMAT:league_phase'


def certify_result(row, fixture, state, at):
    """Confirm the provider phase before adapting a normalized result to the frozen fixture."""
    code = fixture['cohort']
    if (row.get('cohort') not in (code, code + SCOPE_SUFFIX)
            or row.get('stage') not in (fixture['stage'], 'league_phase', 'NEW_FORMAT:league_phase')
            or row.get('event_status') != 'FT'):
        raise ValueError('result is outside its registered league phase or is still unresolved')

    reference = row['raw_reference']
    file = (state / reference['path']).resolve()
    if not file.is_relative_to(state):
        raise ValueError('result evidence outside retained state')
    raw = file.read_bytes()
    document = json.loads(gzip.decompress(raw) if file.suffix == '.gz' else raw)
    header = document['header']
    game, = header['competitions']
    metadata = header['season']
    if (header['league']['slug'] != code or metadata['year'] != 2026 or metadata['type'] != SEASON_TYPES[code]
            or game['status']['type']['state'] != 'post'):
        raise ValueError('raw response is outside the registered league phase or is still unresolved')
    for team in game['competitors']:
        halves = team.get('linescores')
        if (team.get('shootoutScore') not in (None, '', '0', 0)
                or (halves is not None and (len(halves) != 2 or sum(int(h['displayValue']) for h in halves)
                                           != row[team['homeAway'] + '_goals']))):
            raise ValueError('extra periods or regulation half scores conflict')
    aligned = dict(row, cohort=code, stage=fixture['stage'])
    return _certify(aligned, fixture, state, at)


def results(state, fixtures, at):
    if state is None:
        return {}, {}
    state = state.resolve()
    pending = defaultdict(list)
    issues = defaultdict(list)
    stream = state / 'normalized-results.jsonl'
    for line in stream.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        mid = row['match_id']
        if mid in fixtures:
            try:
                pending[mid].append(certify_result(row, fixtures[mid], state, at))
            except (ValueError, TypeError, KeyError, EOFError, OSError) as error:
                issues[mid].append(str(error))
    accepted = {}
    for mid, versions in pending.items():
        if len({(r['home'], r['away']) for r in versions}) != 1:
            issues[mid].append('conflicting verified regulation scores')
        else:
            accepted[mid] = min(versions, key=lambda r: (aware(r['source']['captured_at']), r['source']['sha256']))
    return accepted, dict(issues)


def grade(group, observed):
    rows = []
    picks = {}
    outcomes = {}
    actuals = {}
    selected = {}
    for record in group:
        fixture = record['fixture']
        mid = fixture['match_id']
        original, control = record['forecast'], record['r7']
        line = original['total_line']
        verified = observed.get(mid)
        actual = [verified['home'], verified['away']] if verified else None
        day = aware(fixture['kickoff_at']).astimezone(prepare.BEIJING).date().isoformat()
        rows.append(dict(id=mid, date=day, cohort=fixture['cohort'], actual=actual, line=line,
                         forecast=dict(r13=original, r7=control, market=record['market'])))
        picks[mid] = original
        if record['rank'] is not None:
            selected[record['rank']] = mid
        if actual is not None:
            actuals[mid] = actual
        _, metrics, settlement = _decisions(original, actual, line)
        exact = '-'.join(map(str, actual)) if actual is not None else None
        rank = original['top3'].index(exact) + 1 if metrics['score_top3'] else None
        outcomes[mid] = dict(actual=actual, original_first=record['first'], original_forecast=original,
                             hit=metrics, hit_rank=rank, research_line_settlement=settlement,
                             result_source=verified['source'] if verified else None)
    return dict(registered=len(group), verified_results=len(actuals), pending=len(group) - len(actuals),
                first_choices=dict(sorted(Counter(pick['primary'] for pick in picks.values()).items())),
                first_different_from_r7=sum(r['forecast']['r13']['primary'] != r['forecast']['r7']['primary']
                                            for r in rows),
                three_members_different_from_r7=sum(set(r['forecast']['r13']['top3']) != set(r['forecast']['r7']['top3'])
                                                    for r in rows),
                matched_market_firsts=sum(bool(r['forecast']['market'].get('primary')) for r in rows),
                research_lines=sum(r['line'] is not None for r in rows),
                selected=seats([selected[rank] for rank in sorted(selected)], picks, actuals),
                against_r7=compare(rows, baseline='r7', candidate='r13'),
                against_market=compare(rows, baseline='market', candidate='r13'), per_match=outcomes)


def review(state=None, *, at=None):
    now = datetime.now(timezone.utc)
    cutoff = aware(at) if at else now
    if cutoff > now:
        raise ValueError('review cutoff is in the future')
    original = prepare.scores(prepare.register(False))
    published = prepare.publication(original, False)
    if any(aware(ref['recorded_at']) > cutoff for ref in published.values()):
        raise ValueError('review cutoff predates the frozen score tables')
    fixtures = {entry['fixture']['match_id']: entry['fixture']
                for group in original.values() for entry in group['rows']}
    verified, issues = results(state, fixtures, cutoff)
    return dict(as_of=cutoff.astimezone(prepare.BEIJING).isoformat(),
                scope='R13 original pregame research forecasts',
                formal_display_status='INDEPENDENT_READBACK_PENDING',
                timed_market_verified=0, result_issues=issues,
                competitions={short: dict(display=published[short], **grade(group['rows'], verified))
                              for short, group in original.items()})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--result-state', type=Path)
    parser.add_argument('--at')
    options = parser.parse_args()
    print(json.dumps(review(options.result_state, at=options.at), ensure_ascii=False, indent=2, allow_nan=False))
