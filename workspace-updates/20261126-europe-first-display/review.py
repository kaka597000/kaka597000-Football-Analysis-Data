"""Settle the original European score displays from retained 90-minute results."""

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
from hashlib import sha256
import json
from pathlib import Path
from urllib.parse import urlsplit

import benchmarks
import prepare
import result_intake
from research.analysis_freeze import aware
from research_program.display_window_review import summary_kickoff
from research_program.nov25_first_review import seats
from research_program.paired_kpi_inference import _decisions, compare
from research_program.three_arm_review import _certify


SEASON_TYPES = {v[0]: v[2] for v in prepare.COMPETITIONS.values()}
SCOPE_SUFFIX = ':NEW_FORMAT:league_phase'
KICKOFF_CONFLICT = 'conflicting verified actual kickoffs'


def espn_kickoff(body, reference, fixture):
    captured = aware(reference['captured_at'])
    kickoff_fixture = dict(fixture, competition=fixture['cohort'])
    start = summary_kickoff(body, reference['source_url'], kickoff_fixture, captured)
    return dict(match_id=fixture['match_id'], competition=fixture['cohort'], home=fixture['home'], away=fixture['away'],
                identity_verified=True, actual_kickoff_at=start.astimezone(prepare.BEIJING).isoformat(),
                observed_at=reference['captured_at'], raw_file=reference['path'],
                source_sha256=reference['sha256'], source_url=reference['source_url'])


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
    body = gzip.decompress(raw) if file.suffix == '.gz' else raw
    if sha256(body).hexdigest() != reference['sha256']:
        raise ValueError('result raw source checksum mismatch')
    document = json.loads(body)
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
    result = _certify(aligned, fixture, state, at)
    try:
        evidence = espn_kickoff(raw, reference, fixture)
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        return dict(result, provider='espn', actual_kickoff=None, kickoff_issue=str(error))
    return dict(result, provider='espn', actual_kickoff=evidence, kickoff_issue=None)


def results(state, fixtures, at, official=None):
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
                if urlsplit(row.get('source_url', '')).hostname == 'match.uefa.com':
                    if official is None:
                        official = result_intake.official_bindings(fixtures)
                    verified = result_intake.certify_official(row, fixtures[mid], official[mid], state, at)
                else:
                    verified = certify_result(row, fixtures[mid], state, at)
                pending[mid].append(verified)
            except result_intake.EVIDENCE_ERRORS as error:
                issues[mid].append(str(error))
    accepted = {}
    for mid, versions in pending.items():
        if len({(r['home'], r['away']) for r in versions}) != 1:
            issues[mid].append('conflicting verified regulation scores')
            continue
        ordered = sorted(versions, key=lambda r: (aware(r['source']['captured_at']), r['source']['sha256']))
        providers = {}
        for result in ordered:
            providers.setdefault(result['provider'], result['source'])
        first = dict(ordered[0], confirmed_result_sources=providers)
        starts = [r['actual_kickoff'] for r in ordered if r['actual_kickoff'] is not None]
        if len({r['actual_kickoff_at'] for r in starts}) > 1:
            first = dict(first, actual_kickoff=None, kickoff_issue=KICKOFF_CONFLICT)
        elif starts:
            first = dict(first, actual_kickoff=starts[0], kickoff_issue=None)
        accepted[mid] = first
    return accepted, dict(issues)


def verify_kickoffs(state, fixtures, finalized, at):
    """Reconcile retained in-play clocks with clocks from certified full-time summaries."""
    if state is None or not (state/'intake.json').is_file():
        return {}
    starts, issues = defaultdict(list), {}
    observations = prepare.read(state/'intake.json')['matches']
    for mid in fixtures.keys() & observations.keys():
        fixture = fixtures[mid]
        for row in observations[mid]:
            if row['provider'] != 'espn' or row['status'] in ('STATUS_SCHEDULED', 'STATUS_FULL_TIME'):
                continue
            try:
                ref = row['source']
                if aware(ref['captured_at']) > at:
                    continue
                if result_intake.endpoint(ref['source_url']) != ('espn', fixture['cohort'], mid):
                    raise ValueError('ESPN in-play capture points to a different event')
                body = result_intake.raw_result(state, ref['path'], ref['sha256'])
                document = json.loads(body)
                game, = document['header']['competitions']
                status = game['status']['type']
                if status['state'] != 'in' or status['completed'] is not False:
                    continue
                name, _ = result_intake.espn_score(document, fixture)
                if name != row['status'] or aware(game['date']) != aware(fixture['kickoff_at']):
                    raise ValueError('ESPN in-play status or scheduled kickoff differs')
                starts[mid].append(espn_kickoff(body, ref, fixture))
            except result_intake.EVIDENCE_ERRORS as error:
                issues.setdefault(mid, str(error))

    reconciled = {}
    for mid in starts.keys() | issues.keys():
        final = finalized.get(mid, {})
        candidates = starts[mid]
        if final.get('actual_kickoff') is not None:
            candidates.append(final['actual_kickoff'])
        conflict = final.get('kickoff_issue') == KICKOFF_CONFLICT
        if conflict or len({row['actual_kickoff_at'] for row in candidates}) > 1:
            reconciled[mid] = dict(actual_kickoff=None, kickoff_issue=KICKOFF_CONFLICT)
        elif candidates:
            first = min(candidates, key=lambda row: (aware(row['observed_at']), row['source_sha256']))
            reconciled[mid] = dict(actual_kickoff=first, kickoff_issue=None)
        else:
            reconciled[mid] = dict(actual_kickoff=None, kickoff_issue=issues[mid])
    return reconciled


def grade(group, observed, benchmark=None, *, kickoffs=None):
    kickoffs = kickoffs or {}
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
        kickoff = kickoffs.get(mid, verified or {})
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
                             result_source=verified['source'] if verified else None,
                             confirmed_result_sources=verified.get('confirmed_result_sources', {}) if verified else {},
                             actual_kickoff=kickoff.get('actual_kickoff'), kickoff_issue=kickoff.get('kickoff_issue'))
    report = dict(registered=len(group), verified_results=len(actuals), pending=len(group) - len(actuals),
                verified_actual_kickoffs=sum(row['actual_kickoff'] is not None for row in outcomes.values()),
                verified_actual_kickoffs_awaiting_result=sum(row['actual_kickoff'] is not None and row['actual'] is None
                                                           for row in outcomes.values()),
                dual_source_results=sum(row['confirmed_result_sources'].keys() >= {'espn', 'uefa'} for row in outcomes.values()),
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
    if benchmark is not None:
        report['original_r10_comparison'] = benchmarks.grade(rows, benchmark)
    return report


def review(state=None, *, at=None):
    now = datetime.now(timezone.utc)
    cutoff = aware(at) if at else now
    if cutoff > now:
        raise ValueError('review cutoff is in the future')
    original = prepare.scores(prepare.register(False))
    published = prepare.publication(original, False)
    if any(aware(ref['recorded_at']) > cutoff for ref in published.values()):
        raise ValueError('review cutoff predates the frozen score tables')
    comparisons = benchmarks.locks(original, published, at=cutoff)
    fixtures = {entry['fixture']['match_id']: entry['fixture']
                for group in original.values() for entry in group['rows']}
    verified, issues = results(state, fixtures, cutoff)
    kickoffs = verify_kickoffs(state, fixtures, verified, cutoff)
    return dict(as_of=cutoff.astimezone(prepare.BEIJING).isoformat(),
                scope='R13 original pregame research forecasts',
                formal_display_status='INDEPENDENT_READBACK_PENDING',
                timed_market_verified=0, result_issues=issues,
                competitions={short: dict(display=published[short],
                                          **grade(group['rows'], verified, comparisons.get(short), kickoffs=kickoffs))
                              for short, group in original.items()})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--result-state', type=Path)
    parser.add_argument('--at')
    options = parser.parse_args()
    print(json.dumps(review(options.result_state, at=options.at), ensure_ascii=False, indent=2, allow_nan=False))
