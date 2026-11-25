"""Compare a regenerated aggregate and its independent audit to their frozen versions."""
import argparse
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'20261125-r14-territory-press'))
from verify import compare_value


def read(path):
    return json.loads(path.read_bytes())


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--aggregate',type=Path,required=True)
    parser.add_argument('--audit',type=Path,required=True)
    args=parser.parse_args()
    compare_value(read(ROOT/'aggregate.json'),read(args.aggregate),'independent aggregate')
    compare_value(read(ROOT/'early-audit.json'),read(args.audit),'independent paired and feature audit')
    print('Verified the independent score counts, weights, five-way settlements and paired date intervals.')
