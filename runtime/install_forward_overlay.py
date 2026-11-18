"""Install the forward polling and accounting files on a disposable locked checkout."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


OVERLAY = (
    'runtime/automation/prospective_cycle.py',
    'runtime/automation/prospective_bundle.py',
    'runtime/automation/market_bridge.py',
    'runtime/automation/result_queue.py',
    'runtime/research_program/future_identity.py',
    'runtime/research_program/promotion_review.py',
    'runtime/v2_test/evaluation.py',
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def revision(path):
    return subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()


def install(base, overlay, future):
    domestic = json.loads((future / 'bundle-v2/manifest.json').read_bytes())
    ucl = json.loads((future / 'ucl-bundle-v2/manifest.json').read_bytes())
    locked = {('runtime/' + k.split('/runtime/', 1)[1]): v
              for k, v in domestic['protocol']['source_files_sha256'].items()}
    locked.update({('runtime/' + k.split('/runtime/', 1)[1]): v for k, v in ucl['protocol']['files_sha256'].items()
                   if '/Football-Analysis/runtime/' in k})
    locked['runtime/research_program/ucl_refresh_review.py'] = ucl['review_source_sha256']

    def verify_locked():
        for path, expected in locked.items():
            if sha(base / path) != expected:
                raise ValueError('locked inference/review source differs from protocol: ' + path)

    verify_locked()
    if set(OVERLAY).intersection(locked):
        raise ValueError('accounting overlay must not replace locked protocol sources')
    expected = {path: sha(overlay / path) for path in OVERLAY}
    for path in OVERLAY:
        shutil.copyfile(overlay / path, base / path)
        if sha(base / path) != expected[path]:
            raise ValueError('installed file differs from collector revision: ' + path)
    verify_locked()
    commit = revision(overlay)
    return {'base_commit': revision(base), 'polling_overlay_commit': commit, 'evaluation_overlay_commit': commit,
            'overlay_files_sha256': expected, 'locked_protocol_sources_verified': True,
            'inference_source_changed': False, 'active_model_changed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('base', 'overlay', 'future', 'receipt'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    result = install(args.base, args.overlay, args.future)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    with args.receipt.open('x', encoding='utf-8') as out:
        json.dump(result, out, indent=2)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
