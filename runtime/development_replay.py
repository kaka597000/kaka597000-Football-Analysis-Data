"""Compare development replay identities exactly and probability metrics to 1e-12."""
import argparse
import gzip
import json
import math
from pathlib import Path

METRICS = {'score_log_loss', 'wdl_brier'}


def compare(expected, actual, path=()):
    if type(expected) is not type(actual):
        raise ValueError('type mismatch: ' + str(path))
    if isinstance(expected, dict):
        if expected.keys() != actual.keys():
            raise ValueError('key mismatch: ' + str(path))
        return max((compare(v, actual[k], (*path,k)) for k,v in expected.items()), default=0.)
    if isinstance(expected, list):
        if len(expected) != len(actual):
            raise ValueError('population mismatch: ' + str(path))
        return max((compare(a,b,(*path,i)) for i,(a,b) in enumerate(zip(expected,actual))),default=0.)
    if isinstance(expected,float) and path and path[-1] in METRICS:
        error=abs(expected-actual)
        if not (math.isfinite(expected) and math.isfinite(actual)) or error>1e-12:
            raise ValueError('probability metric mismatch: ' + str(path))
        return error
    if expected != actual:
        raise ValueError('exact identity/selection/count mismatch: ' + str(path))
    return 0.


def verify(expected, actual):
    error=compare(json.loads((expected/'report.json').read_text()),json.loads((actual/'report.json').read_text()))
    def rows(root):
        with gzip.open(root/'rows.jsonl.gz','rt') as stream:
            return [json.loads(line) for line in stream]
    before,after=rows(expected),rows(actual)
    error=max(error,compare(before,after))
    return {'row_count':len(before),'maximum_probability_metric_absolute_error':error,
            'metric_absolute_tolerance':1e-12,'identities_weights_predictions_counts_exact':True}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('expected',type=Path)
    parser.add_argument('actual',type=Path)
    args=parser.parse_args()
    print(json.dumps(verify(args.expected,args.actual)))
