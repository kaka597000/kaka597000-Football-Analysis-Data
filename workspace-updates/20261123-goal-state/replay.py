"""Restore retained inputs; refit, reselect, and repeat all four KPI counts in a clean directory."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory

import numpy as np


def read(p):
    return json.loads(p.read_bytes())


def sha(p):
    with p.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def restore(archive, member, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as bundle:
        with target.open('xb') as out:
            out.write(bundle.extractfile(member).read())


def main(data, code):
    folder = data/'workspace-updates/20261123-goal-state'
    manifest = read(folder/'manifest.json')
    head = subprocess.check_output(['git','-C',str(code),'rev-parse','HEAD'], text=True).strip()
    if head != manifest['source_commit']:
        raise ValueError('research source revision differs from archived run')
    for name, expected in manifest['files'].items():
        if sha(folder/name) != expected:
            raise ValueError('archive mismatch: '+name)
    sys.path.insert(0, str(code/'runtime'))
    from research_program import goal_state_forward, goal_state_study
    from argparse import Namespace
    expected = read(folder/'results.json')
    with TemporaryDirectory() as temp:
        root = Path(temp)
        out = root/'study'
        panels = root/'panels.jsonl'
        events = root/'events.jsonl'
        b = folder/'training-and-panels.tar.gz'
        restore(b, 'events/locked-training.jsonl', events)
        restore(b, 'new-panels/normalized.jsonl', panels)
        big = root/'modern-market-paths.jsonl'
        restore(folder.parent/'20261123-kpi-ranking/round2-market-sources.tar.gz', big.name, big)
        recent = root/'recent.json'
        restore(folder.parent/'20261123-team-strength/research-and-freezes.tar.gz', 'study/updates.json', recent)
        def run(phase, data_file):
            goal_state_study.command(Namespace(phase=phase, inputs=data_file, out=out))
        run('fit', events)
        artifact = read(out/'artifact.json')
        np.testing.assert_allclose(artifact['factors'], expected['artifact']['factors'], atol=1e-11, rtol=0)
        assert artifact['n'] == expected['artifact']['n']
        run('selection', big)
        choice = read(out/'choice.json')
        assert choice['selected'] == expected['choice']['selected'] and choice['heads'] == expected['choice']['heads']
        for phase, path in [('known',big), ('dutch',panels), ('english_second',panels),
                            ('portuguese',panels), ('recent',recent)]:
            run(phase, path)
            report = read(out/(phase+'-report.json'))
            for pair, counts in expected['panels'][phase]['comparisons'].items():
                rerun = report['comparisons'][pair]
                for arm, values in counts['tracks'].items():
                    metrics = rerun['tracks'][arm]['metrics']
                    for key, old in values.items():
                        assert [metrics[key]['hits'],metrics[key]['eligible'],metrics[key]['resolved_gate_denominator']] == old
                assert rerun['population'] == counts['population']
            print(phase, 'four KPI counts reproduced')
        for cohort, meta in manifest['prospective'].items():
            if not meta.get('registration'):
                continue
            issued = root/cohort
            issued.mkdir()
            receipts_member = cohort+'/receipts.json'
            archive = folder/'research-and-freezes.tar.gz'
            restore(archive, receipts_member, issued/'receipts.json')
            index = read(issued/'receipts.json')
            references = [index['registration'], *index['matches'].values()]
            with tarfile.open(archive) as bundle:
                for ref in references:
                    (issued/ref['file']).write_bytes(bundle.extractfile(cohort+'/'+ref['file']).read())
            summaries = goal_state_forward.review(issued, [], root)
            for result in summaries.values():
                assert result['population'] == result['pending'] == meta['registered']
            print(cohort, meta['registered'], 'first issues verified')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--code', type=Path, required=True)
    args = parser.parse_args()
    main(args.data.resolve(), args.code.resolve())
