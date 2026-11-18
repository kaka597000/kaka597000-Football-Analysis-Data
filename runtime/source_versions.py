"""Resolve immutable source revisions from the shared data-repository contract."""
import argparse
import json
from pathlib import Path
import re


def versions(root, *, include_replay=False):
    contract = json.loads((root / 'config/source-contract.json').read_text())
    pins = contract['workflow_pins']
    expected = {'code', 'collector-code', 'three-arm-code', 'sequence-code', 'transformer-code', 'market-signal-code'}
    if set(pins) != expected or any(not re.fullmatch('[0-9a-f]{40}', v) for v in pins.values()):
        raise ValueError('six immutable source revisions required')
    result = {key.replace('-', '_'): value for key, value in pins.items()}
    if include_replay:
        revision = contract['frozen_replay_revision']
        if not re.fullmatch('[0-9a-f]{40}', revision):
            raise ValueError('immutable original replay revision required')
        result['frozen_replay'] = revision
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--github-output', type=Path, required=True)
    parser.add_argument('--include-replay', action='store_true')
    args = parser.parse_args()
    pins = versions(Path(__file__).resolve().parents[1], include_replay=args.include_replay)
    with args.github_output.open('a') as output:
        output.writelines(f'{key}={value}\n' for key, value in pins.items())
