"""Compare a regenerated aggregate and its independent audit to their frozen versions."""
import argparse
from pathlib import Path
import json
import math
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'20261125-r14-territory-press'))
from verify import compare_value


def read(path):
    return json.loads(path.read_bytes())


def compare_fit_details(expected, rebuilt):
    for league, group in expected['leagues'].items():
        for arm, fit in group['fits'].items():
            other = rebuilt['leagues'][league]['fits'][arm]
            for head in ('scoring_beta', 'positive_beta'):
                for index, (a, b) in enumerate(zip(fit[head], other[head], strict=True)):
                    if not math.isclose(a, b, rel_tol=1e-7, abs_tol=1e-9):
                        raise ValueError(f'{league}/{arm}/{head}[{index}] expected {a:.16g}, '
                                         f'rebuilt {b:.16g}, absolute difference {abs(a-b):.6g}')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--aggregate',type=Path,required=True)
    parser.add_argument('--audit',type=Path,required=True)
    args=parser.parse_args()
    expected, rebuilt = read(ROOT/'aggregate.json'), read(args.aggregate)
    compare_fit_details(expected, rebuilt)
    compare_value(expected,rebuilt,'independent aggregate')
    compare_value(read(ROOT/'early-audit.json'),read(args.audit),'independent paired and feature audit')
    print('Verified the independent score counts, weights, five-way settlements and paired date intervals.')
