"""Lock the comparison of existing R10, R13, R7 and market first issues."""

import argparse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import tarfile
from tempfile import TemporaryDirectory

from publication import atomic_json
from research.analysis_freeze import aware
from research_program import goal_state_forward as ledger
from research_program.goal_state_study import sha
from research_program.nov25_first_review import seats
from research_program.paired_kpi_inference import _decisions, compare

import prepare


DIRECTORY = prepare.HERE / 'benchmarks'
INPUTS = {
    'firsts': ('20261125-r10-shot-conversion/forward/first-issues.tar.gz',
               'f2f44fa476bfd0645bbdfa5f218782716683857b7d4ba407e64442e1a54fc602'),
    'ranks': ('20261125-r10-shot-conversion/forward/ranked.tar.gz',
              'b20064dab9bd826f590babce135ba10462c35f95f3071265990e3b66be682d0e'),
    'r13': prepare.ARCHIVES['r13'],
}
METHOD = {
    'scope': 'Both complete November league-phase rounds',
    'reference': 'Previously issued R10, R13, R7 and original R5 market before the first kickoff',
    'first_relationship': 'Same first, R10 first appears as a R13 alternate, or R10 first is outside R13 three',
    'exact_distance': 'Minimum sum of absolute home and away goal differences across the three scores',
    'settlement': 'Verified regulation scores, paired fixed-fixture hits and original ranked three per competition',
}


def first_relationship(r10, r13):
    if r10['primary'] == r13['primary']:
        return 'same_first'
    if r10['primary'] in r13['top3'][1:]:
        return 'r10_first_is_r13_alternate'
    return 'r10_first_outside_r13_three'


def build(rounds):
    output = {}
    with TemporaryDirectory(prefix='euro-r10-original-') as path:
        root = Path(path)
        for name, (relative, expected) in INPUTS.items():
            source = prepare.HERE.parent / relative
            if sha(source) != expected:
                raise ValueError('fixed benchmark archive differs: ' + name)
            with tarfile.open(source) as archive:
                archive.extractall(root/name, filter='data')
        ranking = ledger._read(root/'ranks', prepare.read(root/'ranks/plan.json'))
        for short, round_ in rounds.items():
            code = prepare.COMPETITIONS[short][0]
            r10_seats = ranking['payload']['identity']['selected'][code]
            original_rows = {entry['fixture']['match_id']: entry for entry in round_['rows']}
            records = {}
            for mid, original in original_rows.items():
                older, ref, plan = prepare.original(root/'firsts', mid)
                newer, newref, _ = prepare.original(root/'r13', mid)
                fixture = original['fixture']
                r10, r13 = older['payload'], newer['payload']
                archived_scope = {key for key, entry in plan['payload']['fixtures'].items() if entry['cohort'] == code}
                if (archived_scope != original_rows.keys()
                        or any(older['fixture'][key] != value for key, value in fixture.items())
                        or ranking['payload']['identity']['source_registration'] != plan['record_sha256']
                        or ranking['payload']['fixtures'][mid] != {key: older['fixture'][key] for key in fixture}
                        or not aware(older['recorded_at']) <= aware(ranking['recorded_at']) < aware(fixture['kickoff_at'])
                        or not aware(older['recorded_at']) <= aware(newer['recorded_at']) < aware(fixture['kickoff_at'])
                        or newref != original['first'] or r13['r10_first_issue'] != older['record_sha256']
                        or r10['forecasts']['r7'] != original['r7'] or r10['forecasts']['market'] != original['market']
                        or r10['line'] != original['forecast']['total_line']
                        or r10['odds_source_first_issue'] != original['odds_source_first']['sha256']
                        or aware(r10['archived_cutoff_at']) != aware(original['source_odds_cutoff_at'])):
                    raise ValueError('R10 benchmark differs from the original fixture, comparison or price: ' + mid)
                pick = r10['forecasts']['candidate']
                _decisions(pick, None, r10['line'])
                if len(pick['top3']) != 3 or pick['wdl'] is None or pick['total_line'] != r10['line']:
                    raise ValueError('incomplete original R10 scores or direction: ' + mid)
                records[mid] = dict(first_issue=ref, forecast=pick, first_probability=r10['quality']['p_first'],
                                    shot_ready=r10['shot_ready'], first_relationship=first_relationship(pick, original['forecast']),
                                    same_three_members=set(pick['top3']) == set(original['forecast']['top3']))
            sorted_ids = sorted(records, key=lambda mid: (-records[mid]['first_probability'],
                                 aware(original_rows[mid]['fixture']['kickoff_at']), mid))[:3]
            if len(r10_seats) != 3 or [row['match_id'] for row in r10_seats] != sorted_ids:
                raise ValueError('the archived R10 seats differ from their original full-round ranking')
            for seat in r10_seats:
                item = records[seat['match_id']]
                if (seat['first_issue'] != item['first_issue'] or seat['first_probability'] != item['first_probability']
                        or any(seat[key] != item['forecast'][key] for key in ('primary', 'top3'))):
                    raise ValueError('archived R10 seat differs from its signed first')
            output[short] = dict(r10_ranking_sha256=ranking['record_sha256'], r10_seats=sorted_ids, rows=records)
    return output


def locks(rounds, published, *, issue=False, at=None):
    if not issue and not DIRECTORY.exists():
        return {}
    earliest = min(aware(row['fixture']['kickoff_at']) for group in rounds.values() for row in group['rows'])
    if issue and datetime.now(timezone.utc) >= earliest:
        raise ValueError('benchmark registration closed at the first European kickoff')
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    material = DIRECTORY/'scorecard.json'
    sources = build(rounds)
    if issue and not material.exists():
        atomic_json(material, sources)
    if prepare.read(material) != sources:
        raise ValueError('the fixed benchmark scorecard differs')
    evidence = {}
    for short, group in rounds.items():
        fixtures = [row['fixture'] for row in group['rows']]
        identity = dict(version='EUROPE-ORIGINAL-BENCHMARKS-1', method=METHOD, source_archives={
                        name: list(value) for name,value in INPUTS.items()}, scorecard_sha256=sha(material),
                        original_window_sha256=group['window']['sha256'],
                        original_display_sha256=published[short]['sha256'])
        track = short + '-original-benchmarks-20261126'
        index = DIRECTORY/(short + '.json')
        if issue and not index.exists():
            atomic_json(index, ledger.register(fixtures, identity, track, DIRECTORY))
        ref = prepare.read(index)
        stored = ledger._read(DIRECTORY, ref)
        stamp = aware(stored['recorded_at'])
        if (stored['payload']['identity'] != identity or stored['payload']['track'] != track
                or stored['payload']['fixtures'] != {f['match_id']: f for f in fixtures}
                or not aware(published[short]['recorded_at']) <= stamp < earliest):
            raise ValueError('benchmark lock is different or outside its pregame interval')
        if at is None or stamp <= at:
            evidence[short] = dict(lock=ref, **sources[short])
    return evidence


def score_path(ordered, actual):
    if actual is None:
        return None
    score = '-'.join(map(str, actual))
    home, away = actual
    cells = [tuple(map(int, candidate.split('-'))) for candidate in ordered]
    gaps = [abs(h-home) + abs(a-away) for h,a in cells]
    directions = [(h > a, h < a) for h,a in cells]
    return dict(rank=ordered.index(score)+1 if score in ordered else None, minimum_goal_distance=min(gaps),
                actual_wdl_in_three=(home > away, home < away) in directions)


def grade(rows, benchmark):
    control = benchmark['rows']
    if {row['id'] for row in rows} != control.keys():
        raise ValueError('R10 comparisons require the entire original round')
    paired, per_match, groups = [], {}, {}
    for row in rows:
        mid = row['id']
        old = control[mid]
        r10 = old['forecast']
        forecast = dict(row['forecast'], r10=r10)
        item = dict(row, forecast=forecast)
        paired.append(item)
        groups.setdefault(old['first_relationship'], []).append(item)
        per_match[mid] = dict(first_issue=old['first_issue'], first_relationship=old['first_relationship'],
                              same_three_members=old['same_three_members'], forecasts={
                                  arm: forecast[arm] for arm in ('r7', 'r10', 'r13')}, paths={
                                  arm: score_path(forecast[arm]['top3'], row['actual']) for arm in ('r7', 'r10', 'r13')})
    actuals = {row['id']: row['actual'] for row in paired if row['actual'] is not None}
    return dict(lock=benchmark['lock'], r10_shot_exposure=sum(row['shot_ready'] for row in control.values()),
                first_relationships=dict(Counter(row['first_relationship'] for row in control.values())),
                three_members_changed=sum(not row['same_three_members'] for row in control.values()),
                r10_selected=seats(benchmark['r10_seats'], {mid: row['forecast'] for mid,row in control.items()}, actuals),
                r13_against_r10=compare(paired, baseline='r10', candidate='r13'),
                r10_against_r7=compare(paired, baseline='r7', candidate='r10'),
                r10_against_market=compare(paired, baseline='market', candidate='r10'),
                first_relationship_comparisons={key: compare(values, baseline='r10', candidate='r13')
                                                for key,values in groups.items()}, per_match=per_match)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('lock', 'verify'))
    args = parser.parse_args()
    rounds = prepare.scores(prepare.register(False))
    publication = prepare.publication(rounds, False)
    for short, proof in locks(rounds, publication, issue=args.mode=='lock').items():
        print(short, len(proof['rows']), proof['lock']['id'], proof['lock']['recorded_at'])
