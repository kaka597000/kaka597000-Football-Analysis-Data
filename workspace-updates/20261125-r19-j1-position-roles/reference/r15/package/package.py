"""Build and stage R15 evidence for a specified replay and an immutable source revision."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory

sys.dont_write_bytecode = True

from common import (DEST, NUMERICAL_ENV, OUTPUTS, SLUG, SOURCE_COMMIT, WORKFLOW, digest, inventory,
                    ledger, pretty, read, require, sha)
from intake import freeze
from prospective import COMPANION, DISPLAY_DIR, pack_firsts
from verify import SCHEMA, dependencies, reconstruct, source_pin

HERE = Path(__file__).resolve().parent
SCRATCH = Path('/workspace/scratch')
TOOLS = ('package.py','verify.py','common.py','baselines.py','intake.py','extract_v1.py','starters.py','replay.py',
         'prospective.py','prospective_records.py','data_readme.py')


def stage(args):
    issues = getattr(args, 'forward_issues', None)
    store = getattr(args, 'forward_freeze_root', None)
    require((issues is None) == (store is None), 'supply both --forward-issues and --forward-freeze-root')
    root = args.stage_root.resolve()
    root.mkdir(parents=True,exist_ok=True)
    target = root/DEST
    workflow = root/'.github/workflows'/WORKFLOW
    template = HERE/WORKFLOW
    if not template.is_file():
        template = HERE.parents[1]/'.github/workflows'/WORKFLOW
    workflow_bytes = template.read_bytes()
    pin = source_pin(args.source,args.source_commit)
    inputs = read(args.replay/'inputs.json')
    with TemporaryDirectory(prefix='.r15-stage-',dir=root) as name:
        tmp = Path(name)
        pkg = tmp/SLUG
        pkg.mkdir()
        for name in TOOLS:
            shutil.copyfile(HERE/name,pkg/name)
        guide = HERE/'VERIFYING.md'
        shutil.copyfile(guide if guide.is_file() else HERE/'README.md', pkg/'VERIFYING.md')
        (pkg/'replay').mkdir()
        for name in OUTPUTS:
            shutil.copyfile(args.replay/name,pkg/'replay'/name)
        freeze(args.intake,args.snapshot,inputs,pkg,tmp)
        training,slots,tables,counts = reconstruct(pkg,(args.data_root or root).resolve(),tmp)
        for name,body in tables.items():
            (pkg/name).write_bytes(body)
        (pkg/'normalized-starters.jsonl.gz').write_bytes(ledger(slots))
        manifest = dict(schema=SCHEMA,source_commit=pin['commit'],source=pin,dependencies=dependencies(),
                        rosters_sha256=sha(training),counts=counts,files=inventory(pkg),workflow_sha256=digest(workflow_bytes))
        (pkg/'manifest.json').write_bytes(pretty(manifest))
        require(not workflow.exists() or workflow.read_bytes()==workflow_bytes, ('different existing workflow',str(workflow)))
        target.parent.mkdir(parents=True,exist_ok=True)
        if not target.exists():
            try:
                pkg.rename(target)
            except OSError:
                if not target.is_dir():
                    raise
        if pkg.exists():
            require(inventory(pkg)==inventory(target), ('different existing bundle',str(target)))
        workflow.parent.mkdir(parents=True,exist_ok=True)
        if not workflow.exists():
            staged = tmp/WORKFLOW
            staged.write_bytes(workflow_bytes)
            try:
                os.link(staged,workflow)
            except FileExistsError:
                require(workflow.read_bytes()==workflow_bytes, ('different workflow',str(workflow)))
    result = dict(package=str(target),workflow=str(workflow),manifest_sha256=sha(target/'manifest.json'),**counts)
    if issues is not None:
        data = (args.data_root or root).resolve()
        result['prospective'] = pack_firsts(target, data, data/'workspace-updates'/DISPLAY_DIR, issues, store, root/COMPANION)
    return result


if __name__=='__main__':
    os.environ.update(NUMERICAL_ENV)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage-root',type=Path,required=True,help='root of the data checkout receiving this bundle')
    parser.add_argument('--data-root',type=Path,help='checkout with original R5, R7 and R10 archives (default: stage root)')
    parser.add_argument('--intake',type=Path,default=SCRATCH/'j1-lineups-history-intake')
    parser.add_argument('--snapshot',type=Path,help='directory with the exact frozen manifest, audit and events JSONL')
    parser.add_argument('--replay',type=Path,default=SCRATCH/'r15-final')
    parser.add_argument('--source',type=Path,default=SCRATCH/'r15-source')
    parser.add_argument('--source-commit',default=SOURCE_COMMIT,help=f'final R15 source revision (default: {SOURCE_COMMIT})')
    parser.add_argument('--forward-issues',type=Path,help='also stage the companion for this already-issued R15 directory')
    parser.add_argument('--forward-freeze-root',type=Path,help='independent first store for --forward-issues')
    print(json.dumps(stage(parser.parse_args()),sort_keys=True))
