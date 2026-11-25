"""Recompute the published pregame J1 status at the archived cutoff."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import sys

from research_program.display_window_review import review

ROOT = Path(__file__).resolve().parents[1]
AT = '2026-11-25T17:31:00+08:00'


def read(path):
    return json.loads(path.read_bytes())


def summarize(report):
    result = dict(as_of=report['at'],registration=report['registration'],windows={})
    for name,window in report['windows'].items():
        frozen = window['same_fixture_market']['first_frozen_rows']['tracks']['authored']['metrics']
        market = window['actual_bookmaker_quote']
        seats = window['selected_seats']
        result['windows'][name]=dict(registered=window['registered_n'],settled=window['completed_n'],
            authored_firsts=frozen['score_top1']['issued'],authored_ordered_threes=frozen['score_top3']['issued'],
            original_channel_confirmed=window['confirmed_first_score_n'], original_body_verified=
                window['repository_batch_body_audit']['prepared_batch_verified'],observed_lines=market['raw_verified_price_snapshots_n'],
            fully_timestamped_prices=market['strict_quote_issues_n'],selected=seats['selected_match_ids'],
            selected_firsts_all_hit=seats['all_three_unique_primary_hit_sweep'],
            coverage_blockers=window['blockers'])
    result['both_windows_phases']=report['combined']['phases']
    return result


if __name__=='__main__':
    repo=ROOT/'registration'
    reg=read(repo/read(repo/'plan.json')['file'])
    with TemporaryDirectory() as tmp:
        out=summarize(review(reg,ledger_root=ROOT/'nov25',batch_root=ROOT,result_state=Path(tmp),
              evidence_root=Path(tmp),at=AT))
    if '--write' in sys.argv:
        path=ROOT/'review/20261125T173100+0800.json'
        with path.open('x',encoding='utf8') as out_file:
            json.dump(out,out_file,indent=2,ensure_ascii=False)
            out_file.write('\n')
    elif out!=read(ROOT/'review/20261125T173100+0800.json'):
        raise ValueError('pregame settlement, selected seats or coverage differ')
    print(json.dumps({key:[v['registered'],v['authored_firsts'],v['settled'],v['fully_timestamped_prices']]
                      for key,v in out['windows'].items()}))
