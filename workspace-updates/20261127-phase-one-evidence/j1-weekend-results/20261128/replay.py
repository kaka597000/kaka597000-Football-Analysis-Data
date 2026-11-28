"""Settle the original J1 weekend forecasts using retained public match responses."""

import argparse
from datetime import timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

from research.analysis_freeze import aware
from research_program import display_window_review as display
from research_program import goal_state_forward as ledger
from research_program import j1_window_intake as intake
from research_program.goal_state_study import write_new
from research_program.nov25_first_review import seats
from research_program.paired_kpi_inference import compare

WINDOW = 'nov28_29'
RESEARCH = (
    '20261126-r28-j1-process-forward',
    '20261127-r42-j1-fixed-first-backups',
    '20261127-r46-j1-process-at-fixed-total',
    '20261127-r49-j1-season-chance-rates',
)
METRICS = ('score_top1', 'score_top3')


def authored_review(original, window, report):
    native = window['native_pair_scores']
    publication = ledger._read(original, intake.read(original / 'publication.json'))
    identity = publication['payload']['identity']
    if publication['freeze_id'] != '3ef75900d3e06bb1-v000001':
        raise ValueError('different original publication')
    if not window['repository_batch_body_audit']['prepared_batch_verified']:
        raise ValueError('original authored report did not reconstruct')

    actuals, picks, paired_rows = {}, {}, []
    for mid, row in identity['rows'].items():
        authored = ledger._read(original, row['authored'])
        saved = row['displayed_scores']
        picks[mid] = dict(primary=saved[0], top3=saved, wdl=row['wdl'])
        key = native['per_match'][mid]
        if key['status'] == 'SETTLED':
            evidence = report['match_evidence'][mid]
            start = aware(evidence['actual_start']['earliest'])
            if not aware(authored['recorded_at']) <= aware(publication['recorded_at']) < start:
                raise ValueError('the authored issue was not pregame: ' + mid)
            actuals[mid] = tuple(map(int, key['actual'].split('-')))
        day = aware(row['kickoff_at']).astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat()
        paired_rows.append(dict(id=mid, cohort='jpn.1', actual=actuals.get(mid), date=day,
                                forecast=dict(key['forecasts'], authored=dict(primary=saved[0], top3=saved))))
    pair = {role: compare(paired_rows, baseline=role, candidate='authored')
            for role in ('current', 'test')}
    return dict(
        evidence='ORIGINAL_FROZEN_BODY',
        publication=publication['freeze_id'],
        registered=len(paired_rows),
        settled=len(actuals),
        scores={metric: pair['current']['tracks']['authored']['metrics'][metric] for metric in METRICS},
        wdl_hits=sum(picks[mid]['wdl'] == (
            '主胜' if h > a else '客胜' if a > h else '平局') for mid, (h, a) in actuals.items()),
        wdl_eligible=sum(picks[mid]['wdl'] in ('主胜', '客胜', '平局') for mid in actuals),
        versus_native={role: {metric: comparison['paired'][metric] for metric in METRICS}
                       for role, comparison in pair.items()},
        selected=seats(identity['selected'], picks, actuals),
        per_match={r['id']: dict(actual=r['actual'], **picks[r['id']]) for r in paired_rows},
    )


def replay(original_data, wave_bundle, checkpoint_bundle, output, at):
    files = original_data / 'workspace-updates'
    registration = files / '20261125-j1-stage-windows/registration'
    plan = registration / intake.read(registration / 'plan.json')['file']
    binding = files / '20261127-j1-official-kickoff/kickoff-packet.json'
    original = files / '20261126-r26-j1-first-stage' / WINDOW
    checkpoint_names = ('market-t24-wave-1400', 'market-t24-wave-1500', 'market-t24-wave-1500-close')
    intake.intake(plan, WINDOW, binding, wave_bundle, output, tuple(files / n / 'issued' for n in RESEARCH),
                  at, checkpoint_folders=tuple(checkpoint_bundle / name for name in checkpoint_names))
    inputs = intake.read(output / 'review.json')
    with TemporaryDirectory(prefix='j1-first-display-') as tmp:
        batch = Path(tmp)
        (batch / 'registration').symlink_to(registration, target_is_directory=True)
        (batch / 'evidence').symlink_to(original.parent / 'evidence', target_is_directory=True)
        (batch / WINDOW).symlink_to(original, target_is_directory=True)
        result = display.review(intake.read(plan), ledger_root=original, result_state=output,
                                evidence_root=output, batch_root=batch,
                                jleague_kickoffs=intake.read(output / 'jleague-kickoffs.json'),
                                actual_kickoffs=intake.read(output / 'actual-kickoffs.json'), at=at)
    window = result['windows'][WINDOW]
    window['repository_batch_body_audit'].pop('path', None)
    authored = authored_review(original, window, inputs)
    if (inputs['registered'] != 10 or window['native_pair_scores']['bound_original_pairs'] != 10
            or authored['settled'] != inputs['settled']
            or any(row['official_result_agreement'] != 'official_and_espn_ft_agree'
                   for row in inputs['match_evidence'].values() if row['status'] == 'verified_regulation')):
        raise ValueError('the original whole-window scope or score settlement differs')
    write_new(output / 'first-window.json', dict(
        at=at.astimezone(timezone.utc).isoformat(), window=WINDOW,
        verified_regulation=inputs['settled'], pending=inputs['pending'],
        native=window['native_pair_scores'], original_frozen_comprehensive=authored,
        formal=dict(registered=window['registered_n'],
                    confirmed_display_completed=window['completed_n'],
                    confirmed_first_score=window['confirmed_first_score_n'], blockers=window['blockers'],
                    strictly_eligible_market=window['actual_bookmaker_quote']['strict_quote_issues_n'],
                    nonpush=window['actual_bookmaker_quote']['nonpush_settled_n'],
                    independent_first_delivery=window['confirmed_first_score_n'] > 0,
                    verified_body=window['repository_batch_body_audit']),
    ))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original-data', required=True, type=Path)
    parser.add_argument('--wave-bundle', required=True, type=Path)
    parser.add_argument('--checkpoint-bundle', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--at', required=True)
    args = parser.parse_args()
    replay(args.original_data.resolve(), args.wave_bundle.resolve(), args.checkpoint_bundle.resolve(),
           args.out.resolve(), aware(args.at))
