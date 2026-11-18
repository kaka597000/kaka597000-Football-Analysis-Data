"""Reconstruct the two complete residual artifacts with a pre-season label cutoff."""
import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parents[1] / '20261118-sequence/history'
CUTOFF = '2026-08-01T00:00:00Z'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--out', type=Path, default=HERE)
    args = parser.parse_args()
    sys.path[:0] = [str(args.source.resolve() / 'runtime'), str(PREVIOUS)]
    from research_program import sequence_models, transformer_score, sequence_history
    from run_models import encoded, sha
    from publication import deliver

    args.out.mkdir(parents=True, exist_ok=True)
    rows = [r for season in ('2425','2526') for r in sequence_history.prepare_rows(PREVIOUS / f'samples-{season}.jsonl.gz')]
    assert max(r['game_date'] for r in rows) == '2026-05-24' and len(rows) == 3036
    receipt = {'cutoff': CUTOFF, 'n': len(rows), 'last_training_date': max(r['game_date'] for r in rows), 'artifacts': {}}
    for tag, model, prior in [('transformer', transformer_score, HERE.parent/'history/artifact.json'),
                              ('sequence', sequence_models, PREVIOUS/'artifact.json')]:
        artifact = model.fit(rows, cutoff_at=CUTOFF)
        retained = json.loads(prior.read_bytes())
        if {k:v for k,v in artifact.items() if k != 'cutoff_at'} != {k:v for k,v in retained.items() if k != 'cutoff_at'}:
            raise ValueError('preseason refit differs from the retained weights: '+tag)
        path = args.out / (tag+'-before-season.json')
        deliver(path, encoded(artifact))
        receipt['artifacts'][tag] = {'refit_sha256':sha(path),'retained_sha256':sha(prior),
                                     'sample_sha256':artifact['sample_sha256'],
                                     'all_fields_except_cutoff_identical':True}
    deliver(args.out/'refit-receipt.json',encoded(receipt))

if __name__ == '__main__':
    main()
