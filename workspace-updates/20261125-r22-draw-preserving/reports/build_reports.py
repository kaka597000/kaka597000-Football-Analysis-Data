#!/usr/bin/env python3
"""Build compact R22 dose, paired-result, fixture-rank and receipt tables."""

import argparse, csv, gzip, json, tarfile, hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
CODES = ("eng.1", "esp.1", "ger.1", "ita.1", "fra.1")
WINDOWS = ("validation_2024_25", "evaluation", "recent", "november_extension")


def dump_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def readgz(p):
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return [json.loads(x) for x in f]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=HERE / "reports")
    args = parser.parse_args()
    outdir = args.output_dir
    metrics = json.loads((HERE / "replay/reference/metrics.json").read_bytes())
    r21 = ROOT / "workspace-updates/20261125-r21-score-dependence/replay/reference"
    doses = []
    pairs = []
    summary = []
    ranks = []
    for code in CODES:
        r22fit = json.loads((HERE / "replay/reference/main" / code / "fit.json").read_bytes())
        parent = json.loads((r21 / "main" / code / "fit.json").read_bytes())
        for arm in ("context", "constant"):
            model = parent["fitted"][arm]
            doses.append(
                {
                    "competition": code,
                    "weight_owner": "R21 pinned parent",
                    "arm": arm,
                    "features": json.dumps(model.get("features", []), separators=(",", ":")),
                    "coefficients": json.dumps(model.get("beta", []), separators=(",", ":")),
                    "full_weight_record": json.dumps(model, sort_keys=True, separators=(",", ":")),
                    "r21_fit_sha256": r22fit["r21_fit_sha256"],
                    "r21_training_through": parent.get("training_through"),
                    "r21_validation_through": parent.get("validation_through"),
                    "r22_dose": r22fit["dose"],
                    "r22_validation_games": r22fit["validation_games"],
                    "r22_validation_trials": json.dumps(
                        r22fit["validation_trials"], sort_keys=True, separators=(",", ":")
                    ),
                    "r21_original_context_score_dose": r22fit["r21_original_score_dose"],
                }
            )
        for window in WINDOWS:
            block = metrics["competitions"][code][window]
            summary.append(
                {
                    "competition": code,
                    "window": window,
                    "population": block["population"],
                    "r22_first_hits": block["comparisons"]["r7_vs_candidate"]["tracks"]["candidate"][
                        "metrics"
                    ]["score_top1"]["hits"],
                    "r22_top3_hits": block["comparisons"]["r7_vs_candidate"]["tracks"]["candidate"][
                        "metrics"
                    ]["score_top3"]["hits"],
                    "r7_first_hits": block["comparisons"]["r7_vs_candidate"]["tracks"]["r7"]["metrics"][
                        "score_top1"
                    ]["hits"],
                    "r7_top3_hits": block["comparisons"]["r7_vs_candidate"]["tracks"]["r7"]["metrics"][
                        "score_top3"
                    ]["hits"],
                    "full_batches": block["three_seat_sweep"]["full_batches"],
                    "short_batches": block["three_seat_sweep"]["short_batches"],
                    "occupied_slots": block["three_seat_sweep"]["occupied_slots"],
                    "planned_slots": block["three_seat_sweep"]["planned_slots"],
                }
            )
            for stratum in ("all", "draw", "non_draw"):
                if stratum == "all":
                    comparisons = block["comparisons"]
                else:
                    comparisons = (
                        block["outcome_strata"].get("draw" if stratum == "draw" else "non_draw") or {}
                    ).get("comparisons", {})
                for comparison, detail in comparisons.items():
                    for metric, value in detail["paired"].items():
                        ci = value.get("date_cluster_ci")
                        pairs.append(
                            {
                                "competition": code,
                                "window": window,
                                "outcome_stratum": stratum,
                                "comparison": comparison,
                                "metric": metric,
                                "eligible": value.get("eligible"),
                                "gained": value.get("gained"),
                                "lost": value.get("lost"),
                                "tied": value.get("tied"),
                                "net_hits": value.get("net_hits"),
                                "net_rate": value.get("net_rate"),
                                "date_cluster_count": value.get("matchday_clusters"),
                                "date_cluster_95_low": ci[0] if ci else None,
                                "date_cluster_95_high": ci[1] if ci else None,
                                "fixed_population_net_hits": value.get("fixed_population_net_hits"),
                                "fixed_population_net_rate": value.get("fixed_population_net_rate"),
                            }
                        )
        for archive in ("validation.jsonl.gz", "forecasts.jsonl.gz"):
            for x in readgz(HERE / "replay/reference/main" / code / archive):
                ranks.append(
                    {
                        "competition": code,
                        "window": x["window"],
                        "match_id": x["id"],
                        "date": x["date"],
                        "home": x["home"],
                        "away": x["away"],
                        "actual": "-".join(map(str, x["actual"])),
                        "candidate_first": x["forecast"]["candidate"]["primary"],
                        "candidate_ordered_three": "|".join(x["forecast"]["candidate"]["top3"]),
                        "r7_ordered_three": "|".join(x["forecast"]["r7"]["top3"]),
                        "r21_ordered_three": "|".join(x["forecast"]["r21"]["top3"]),
                        "market_ordered_three": "|".join(x["forecast"]["market"]["top3"]),
                        "first_probability": x["quality"]["candidate"]["p_first"],
                        "three_probability": x["quality"]["candidate"]["p_three"],
                        "batch_rank": x.get("batch_rank"),
                        "batch_size": x.get("batch_size"),
                        "seat": x.get("seat"),
                    }
                )
    coverage = {
        "source_commit": json.loads((HERE / "source-lock.json").read_bytes())["final_source_commit"],
        "protocol_sha256": json.loads((HERE / "source-lock.json").read_bytes())["protocol_sha256"],
        "r21_parent_pr61_head": json.loads((HERE / "source-lock.json").read_bytes())[
            "current_public_data_pr61_head"
        ],
        "historical_reference_repeat_files": 38,
        "historical_reference_repeat_tree_sha256": json.loads((HERE / "source-lock.json").read_bytes())[
            "r22_historical_tree_sha256"
        ],
        "windows": {
            w: {
                "population": metrics["overall"][w]["population"],
                "candidate_first_hits": metrics["overall"][w]["comparisons"]["r7_vs_candidate"]["tracks"][
                    "candidate"
                ]["metrics"]["score_top1"]["hits"],
                "candidate_top3_hits": metrics["overall"][w]["comparisons"]["r7_vs_candidate"]["tracks"][
                    "candidate"
                ]["metrics"]["score_top3"]["hits"],
                "r7_first_hits": metrics["overall"][w]["comparisons"]["r7_vs_candidate"]["tracks"]["r7"][
                    "metrics"
                ]["score_top1"]["hits"],
                "r7_top3_hits": metrics["overall"][w]["comparisons"]["r7_vs_candidate"]["tracks"]["r7"][
                    "metrics"
                ]["score_top3"]["hits"],
                "short_batches": metrics["overall"][w]["three_seat_sweep"]["short_batches"],
                "full_batches": metrics["overall"][w]["three_seat_sweep"]["full_batches"],
            }
            for w in WINDOWS
        },
    }
    dump_csv(outdir / "league-weights.csv", doses)
    dump_csv(outdir / "historical-window-summary.csv", summary)
    dump_csv(outdir / "paired-results.csv", pairs)
    dump_csv(outdir / "per-fixture-ranks.csv", ranks)
    (outdir / "coverage.json").write_text(json.dumps(coverage, ensure_ascii=False, indent=2) + "\n")
    # Official first receipt index and 15 ranked seats, preserving record-level and byte-level hashes.
    idx = json.loads((HERE / "forward/receipts.json").read_bytes())
    reg = idx["registration"]
    firsts = []
    for mid, item in sorted(idx["matches"].items()):
        b = (HERE / "forward" / item["file"]).read_bytes()
        record = json.loads(b)
        p = record["payload"]
        c = p["forecasts"]["candidate"]
        r7 = p["forecasts"]["r7"]
        firsts.append(
            {
                "match_id": mid,
                "competition": record["fixture"]["cohort"],
                "kickoff_at": record["fixture"]["kickoff_at"],
                "cutoff_at": record["fixture"]["cutoff_at"],
                "freeze_id": record["freeze_id"],
                "recorded_at": record["recorded_at"],
                "record_sha256": record["record_sha256"],
                "raw_file_sha256": hashlib.sha256(b).hexdigest(),
                "registration_sha256": p.get("registration_sha256", record["idempotency_key"]),
                "r7_first_issue": p["r7_first_issue"],
                "r21_first_issue": p["r21_first_issue"],
                "r7_primary": r7["primary"],
                "r22_primary": c["primary"],
                "r7_top3": "|".join(r7["top3"]),
                "r22_top3": "|".join(c["top3"]),
                "wdl": c["wdl"],
                "total_side": c.get("total_side"),
                "total_line": p.get("line"),
            }
        )
    dump_csv(outdir / "official-firsts.csv", firsts)
    ranked_plan = json.loads((HERE / "ranked/plan.json").read_bytes())
    rankrec = json.loads((HERE / "ranked" / ranked_plan["file"]).read_bytes())
    selected = rankrec["payload"]["identity"]["selected"]
    seats = []
    for code, rows2 in selected.items():
        for row in rows2:
            seats.append({"competition": code, **row})
    dump_csv(outdir / "official-ranked-seats.csv", seats)
    print(json.dumps(coverage, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
