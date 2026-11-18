"""Transfer the fixed European sequence recipes to earlier genuine Brazilian Current freezes."""

import argparse
from datetime import datetime
import gzip
import hashlib
import json
from pathlib import Path
import sys

from run_models import encoded, evaluate, sha, summarize

TRANSFER_CUTOFF = "2026-10-01T00:00:00Z"


def instant(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--source", type=Path, required=True)
    cli.add_argument("--history", type=Path, default=Path(__file__).resolve().parent)
    cli.add_argument("--out", type=Path, default=Path(__file__).resolve().parent)
    args = cli.parse_args()
    sys.path[:0] = [str(args.source.resolve()), str(args.source.resolve() / "runtime")]
    from research_program import sequence_history, sequence_models, three_arm_model

    history, out = args.history.resolve(), args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    prior = history.parents[1] / "20261118-three-arm" / "training"
    original = prior / "actual_current.jsonl.gz"
    source_ledger = json.loads((history / "brazil" / "sequences.json").read_bytes())
    real = [json.loads(line) for line in gzip.decompress(original.read_bytes()).splitlines()]
    training = []
    for season in sequence_history.SEASONS:
        training.extend(sequence_history.prepare_rows(history / f"samples-{season}.jsonl.gz"))
    artifact = sequence_models.fit(training, cutoff_at=TRANSFER_CUTOFF)
    (out / "brazil-transfer-artifact.json").write_bytes(encoded(artifact))

    eligible, inventory = [], []
    for row in real:
        if row["cohort"] != "bra.1":
            continue
        mid = row["match_id"]
        evidence = source_ledger[mid]
        cutoff, kickoff = instant(row["cutoff_at"]), instant(row["kickoff_at"])
        if (evidence["population"] != "archived_current" or instant(evidence["cutoff_at"]) != cutoff
                or instant(evidence["kickoff_at"]) != kickoff or cutoff >= kickoff):
            raise ValueError(f"original forecast or feature cutoff disagrees for {mid}")
        sequence = evidence["sequence"]
        for side in evidence["lineage"].values():
            for match in side["matches"]:
                if match is not None and (instant(match["observed_at"]) > cutoff
                        or instant(match["kickoff_at"]).date() >= kickoff.date()):
                    raise ValueError(f"late prior state for {mid}")
        info = {"match_id": mid, "freeze_cutoff": row["cutoff_at"], "eligible": row["market"] is not None,
                "valid_steps": [sum(step[3] for step in side) for side in sequence]}
        if row["market"] is None:
            info["reason"] = "original forecast lacks a complete matched h2h and Asian total pair"
        else:
            current = three_arm_model._matrix(row["current_matrix"])
            quote = three_arm_model._quote_values(row["market"], cutoff)
            baseline = three_arm_model._market_matrix(current, quote)
            eligible.append(dict(row, game_date=kickoff.date().isoformat(), sequence=sequence,
                                 baseline_matrix=baseline))
        inventory.append(info)

    results = evaluate(artifact, eligible)
    (out / "brazil-transfer-rows.jsonl.gz").write_bytes(
        gzip.compress(b"".join(json.dumps(r, sort_keys=True, separators=(",", ":")).encode() + b"\n"
                             for r in results), mtime=0))
    report = {
        "mode": "Historical transfer replay. All score labels used for fitting were European, through May 24, 2026.",
        "cutoff": TRANSFER_CUTOFF, "fit_n": artifact["training_matches"],
        "baseline": "Original frozen Current PMF projected once onto its complete timestamped original market panel.",
        "scope": "Retained Brazilian Serie A Current freezes; only rows with paired market are eligible. "
                 "Historical state is reconstructed from evidence already observed at the original cutoff. "
                 "Later schedules check the sequence of fixture identities only.",
        "inventory": inventory, "summary": summarize(results),
        "source_sha256": {p.name: sha(p) for p in [original, history / "brazil/sequences.json",
                          out / "brazil-transfer-artifact.json", out / "brazil-transfer-rows.jsonl.gz"]},
    }
    (out / "brazil-transfer-validation.json").write_bytes(encoded(report))
    print(json.dumps(report["summary"]["arms"]))


if __name__ == "__main__":
    main()
