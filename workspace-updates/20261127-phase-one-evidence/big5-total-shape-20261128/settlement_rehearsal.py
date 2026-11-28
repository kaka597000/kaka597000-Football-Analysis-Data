"""Validate evidence and common denominators on earlier real finals and the pending window."""

import argparse
from copy import deepcopy
from pathlib import Path

from research.analysis_freeze import aware, verify
from research_program.goal_state_study import write_new
from result_evidence import verify_results
from settlement import first_opening, grade, load_window, locked_bindings, read
from weekend import first_issues


METRICS = ('score_top1', 'score_top3', 'wdl')


def describe(report):
    leagues = {}
    for code, league in report['competitions'].items():
        tracks = {arm: {label: {field: track['metrics'][label][field] for field in ('hits', 'eligible', 'issued')}
                        for label in METRICS}
                  for arm, track in league['tracks'].items()}
        leagues[code] = {key: league[key] for key in
                         ('registered', 'verified_finals', 'verified_actual_starts', 'two_source_finals', 'strict_market')}
        leagues[code]['tracks'] = tracks
    return {'registered': report['registered'], 'verified_finals': report['verified_finals'], 'competitions': leagues}


def rehearsal(data, bundle):
    root = bundle / 'settlement-check'
    reference = read(root / 'morning-reference.json')
    fixtures = reference['fixtures']
    at = aware(reference['as_of'])
    labels = verify_results(fixtures, root, read(root / 'morning-receipts.json'), at)
    for mid, old in reference['expected'].items():
        new = labels[mid]
        if (not new['both_providers'] or new['issues'] or new['actual'] != old['actual']
                or aware(new['actual_kickoff_at']) != aware(old['actual_kickoff_at'])):
            raise ValueError('settlement evidence did not reproduce the preceding result audit')
    tracks = read(bundle / 'schedule/manifest.json')['first_issue_inputs']
    for arm, path in tracks.items():
        for mid, record in first_issues(data / 'workspace-updates' / path, fixtures).items():
            fixtures[mid].setdefault('first_issues', {})[arm] = record
    control = grade(fixtures, labels)
    projected = deepcopy(fixtures)
    absent_clock = deepcopy(labels)
    first = next(iter(projected))
    projected[first]['first_issues']['R8']['recorded_at'] = labels[first]['actual_kickoff_at']
    absent_clock[first]['actual_kickoff_at'] = None
    late = grade(projected, labels)['per_match'][first]
    absent = grade(fixtures, absent_clock)['per_match'][first]
    assert late['eligibility_exclusions']['R8'] == 'FIRST_ISSUE_NOT_BEFORE_ACTUAL_START'
    assert set(absent['eligibility_exclusions'].values()) == {'ACTUAL_KICKOFF_UNVERIFIED'}

    prospective = load_window(bundle, locked_bindings(bundle))
    opening = first_opening(bundle, prospective)
    locked = verify(read(bundle / 'schedule/fotmob-bindings-freeze.json'))
    pending = verify_results(prospective, root, read(root / 'pending-receipts.json'), locked['recorded_at'])
    fresh = grade(prospective, pending, opening)
    if control['verified_finals'] != 5 or fresh['registered'] != 31 or fresh['verified_finals'] != 0:
        raise ValueError('past result evidence or pending fixed-window denominator differs')
    return {'earlier_completed_fixtures_only': describe(control), 'verified_starts_and_finals': labels,
            'registered_pending_window': describe(fresh),
            'rehearsal_conditions': {'cutoff_at_actual_start_is_ineligible': True,
                                      'missing_actual_start_withheld_from_scoring': True,
                                      'pending_window_contains_no_regulation_labels': True}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    write_new(args.out, rehearsal(args.data_root, Path(__file__).resolve().parent))
