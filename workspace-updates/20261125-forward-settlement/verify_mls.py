"""Rebuild the R7 schedule-revision decision from three previously published archives."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile
from tempfile import TemporaryDirectory

from research.analysis_freeze import aware
from research_program import goal_state_forward as ledger
from research_program.kpi_validation import _actual
from research_program.result_schedule_revision import revised_actual


THIS = Path(__file__).resolve().parent
UPDATES = THIS.parent
CASE = 'espn:401933728'
ORIGINALS = {
    'schedule': ('20261123-all-scope-kpi/forward-observations.tar.gz', '1744c4f54f67b222ac7296675f48c6954dc98b64edc48aa98244b1060e5ecf59'),
    'firsts': ('20261123-prematch-literature/first-issues.tar.gz', '52f1dd07d146a93ba9cec41ce9e1c9cdf75b3db43f8a65da7ffea222467f385d'),
    'review': ('20261125-r9-team-score/review/evidence.tar.gz', '9af2dc0530f0a5c8cdf978a97a047066efbc3063ce0cea879416bc7dac0fc3fd'),
    'previous_issue': ('20261125-r9-team-score/review/R7/unresolved.json', '29999261b49f61d9dab587c4109a267276a110a415a9fd6c2f3a03ffc2ac2d4a'),
}


def source(name):
    relative, expected = ORIGINALS[name]
    path = UPDATES / relative
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError(f'original archive checksum differs for {relative}')
    return path


def ref(file):
    return dict(file=file.name, sha256=hashlib.sha256(file.read_bytes()).hexdigest())


def prepare(root):
    issues = root / 'issues'
    with tarfile.open(source('firsts')) as tar:
        tar.extractall(issues, filter='data')
    with tarfile.open(source('review')) as tar:
        for member in tar:
            if member.name.startswith('R7/evidence/') or member.name == 'R7/results.json':
                tar.extract(member, root, filter='data')
    main = root / 'R7'
    evidence = main / 'evidence'
    with tarfile.open(source('schedule')) as tar:
        event_file = 'forward/raw/usa_1_20261123.json'
        for name in (event_file, 'forward/queries.json'):
            (evidence / Path(name).name).write_bytes(tar.extractfile(name).read())
    old_rows = json.loads((main / 'results.json').read_bytes())
    missing, = json.loads(source('previous_issue').read_bytes())
    if missing['match_id'] != CASE or missing['source']['strict_reason'] != 'retained kickoff conflict':
        raise ValueError('unexpected earlier unresolved fixture')
    info = missing['source']
    f = missing['fixture']
    checks = {k: info[k] for k in ('url', 'file', 'sha256', 'query_time', 'identity_verified')}
    checks['schedule_revision'] = dict(scoreboard=ref(evidence / Path(event_file).name), queries=ref(evidence / 'queries.json'))
    goals = {side['side'] + '_goals': int(side['score']) for side in info['teams']}
    label = dict(f, **goals, score_basis='regulation_90', event_status='FT', observed_at=info['query_time'], evidence=checks)
    return issues, evidence, old_rows, label


def counts(report):
    paired = report['vs_market']
    return dict(registered=paired['population'], settled=paired['settled_population'], pending=paired['pending'],
                candidate={k: [v['hits'], v['eligible']] for k, v in paired['tracks']['candidate']['metrics'].items()},
                market={k: [v['hits'], v['eligible']] for k, v in paired['tracks']['market']['metrics'].items()})


def calculate(root):
    issues, evidence, labels, label = prepare(root)
    index = json.loads((issues / 'receipts.json').read_bytes())
    first = ledger._read(issues, index['matches'][CASE])
    f = first['fixture']
    cutoff = max(aware(r['observed_at']) for r in [*labels, label])
    try:
        _actual(label, f, evidence, cutoff)
    except ValueError as exc:
        if str(exc) != 'retained kickoff conflict':
            raise
    else:
        raise ValueError('the original schedule discrepancy was not reproduced')
    goals = revised_actual(label, first, evidence, cutoff)
    doc = json.loads((evidence / label['evidence']['file']).read_bytes())
    game, = doc['header']['competitions']
    start, = [e['wallclock'] for e in doc['keyEvents'] if e['type'].get('type') == 'kickoff' and e['period']['number'] == 1]
    old = ledger.review(issues, labels, evidence)
    updated = ledger.review(issues, [*labels, label], evidence)
    return dict(match_id=CASE, registration=index['registration'], original_issue=index['matches'][CASE],
                frozen_at=first['recorded_at'], original_schedule=f['kickoff_at'], updated_schedule=game['date'],
                first_period_kickoff=start, regulation_90=list(goals), original_decisions=first['payload']['forecasts'],
                result_evidence=label['evidence'], earlier_exact_schedule_only=counts(old), reconciled=counts(updated),
                prospective_stage_certified=False)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--write', action='store_true', help='create the first readout')
    args = p.parse_args()
    with TemporaryDirectory() as tmp:
        result = calculate(Path(tmp))
    target = THIS / 'r7-mls-reconciled.json'
    if args.write:
        with target.open('x', encoding='utf8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
            f.write('\n')
    elif json.loads(target.read_bytes()) != result:
        raise ValueError('recomputed R7 review differs')
    print(json.dumps(result['reconciled'], ensure_ascii=False))
