#!/usr/bin/env python3
"""Build descriptive R16 tables from the frozen replay artifacts."""

import csv
import gzip
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def _write_csv(path, rows, fields):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def batch_score_coverage(replay, competitions):
    """Count how many correct original fixture picks each full pool contained after settlement."""
    fields = ("full_batches", "zero_first", "one_first", "two_first", "at_least_three_first",
              "at_least_three_ordered_scores", "raw_selected_first_sweeps", "calibrated_selected_first_sweeps")
    counts = {code: dict.fromkeys(fields, 0) for code in competitions}
    with gzip.open(replay / "ranked-slates.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            batch = json.loads(line)
            fixtures = batch["fixtures"]
            if len(fixtures) < 3:
                continue
            group = counts[batch["cohort"]]
            first_hits = 0
            ordered_hits = 0
            for fixture in fixtures:
                actual = "-".join(map(str, fixture["actual"]))
                first_hits += fixture["primary"] == actual
                ordered_hits += actual in fixture["top3"]
            group["full_batches"] += 1
            group[("zero_first", "one_first", "two_first", "at_least_three_first")[min(first_hits, 3)]] += 1
            group["at_least_three_ordered_scores"] += ordered_hits >= 3
            for rule, outcome in batch["results"].items():
                group[rule + "_selected_first_sweeps"] += outcome["sweep"]
    counts["ALL"] = {key: sum(row[key] for row in counts.values()) for key in fields}
    return [dict(competition=code, **row) for code, row in sorted(counts.items())]


def build(root=ROOT):
    root = Path(root)
    metrics = json.loads((root / "replay/metrics.json").read_text(encoding="utf-8"))
    weights = json.loads((root / "replay/weights.json").read_text(encoding="utf-8"))
    competition_rows = []
    coverage_rows = []
    fallback_rows = []
    batch_rows = batch_score_coverage(root / "replay", metrics["competitions"])
    _write_csv(root / "replay/batch-score-coverage.csv", batch_rows, list(batch_rows[0]))

    for code, summary in sorted(metrics["competitions"].items()):
        for rule, result in summary["rules"].items():
            for seat in result["seats"]:
                filled = seat["filled"]
                competition_rows.append({
                    "competition": code,
                    "rule": rule,
                    "seat": seat["seat"],
                    "filled": filled,
                    "primary_hits": seat["first_hits"],
                    "primary_hit_rate": seat["first_hits"] / filled if filled else None,
                    "ordered_three_hits": seat["ordered_three_hits"],
                    "ordered_three_hit_rate": seat["ordered_three_hits"] / filled if filled else None,
                })

        paired = summary.get("same_fixtures")
        population = paired["population"] if paired else 0
        for track in ("market", "candidate"):
            track_data = paired["tracks"][track] if paired else None
            metrics_by_name = track_data["metrics"] if track_data else {}
            metric_names = ("score_top1", "score_top3", "wdl", "actual_ou")
            for metric in metric_names:
                value = metrics_by_name.get(metric)
                coverage_rows.append({
                    "competition": code,
                    "track": track,
                    "metric": metric,
                    "issued": value["issued"] if value else 0,
                    "registered_population": population,
                    "coverage": value["registered_coverage"] if value else 0.0,
                    "hits": value["hits"] if value else 0,
                    "eligible": value["eligible"] if value else 0,
                    "eligible_rate": value["eligible_rate"] if value else None,
                })

        recipes = weights[code]
        for period in ("evaluation", "forward"):
            recipe = recipes[period]
            fallback_rows.append({
                "competition": code,
                "period": period,
                "status": recipe["status"],
                "training_rows": recipe["training_rows"],
                "training_hits": recipe["training_hits"],
                "first_date": recipe["first_date"],
                "through": recipe["through"],
            })

    _write_csv(root / "replay/competition-seat.csv", competition_rows, list(competition_rows[0]))
    _write_csv(root / "replay/same-fixture-market-coverage.csv", coverage_rows, list(coverage_rows[0]))
    _write_csv(root / "replay/fallback-by-competition.csv", fallback_rows, list(fallback_rows[0]))

    paired = metrics["aggregate"]["paired"]
    seat = metrics["aggregate"]["descriptive_paired_seat_first"]
    complete_batches = paired["gained"] + paired["lost"] + paired["tied"]
    uncertainty = {
        "paired_complete_sweep": {
            "batches": complete_batches,
            "gained": paired["gained"],
            "lost": paired["lost"],
            "discordant": paired["discordant_complete_batches"],
            "observed_net": paired["net"],
            "date_cluster_bootstrap_95": paired["ci95"],
            "discordance_rate_one_sided_95_upper": (
                1 - 0.05 ** (1 / complete_batches) if complete_batches else None
            ),
            "discordance_rate_two_sided_95_upper": (
                1 - 0.025 ** (1 / complete_batches) if complete_batches else None
            ),
            "interpretation": (
                "All complete batches were concordant (zero/zero sweeps). The degenerate bootstrap "
                "interval reflects no observed discordance and is not evidence of equivalence."
            ),
        },
        "descriptive_selected_primary_by_filled_seat": {
            "gained": seat["gained"],
            "lost": seat["lost"],
            "net": seat["net"],
            "eligible": seat["eligible"],
            "date_cluster_bootstrap_95": seat["ci95"],
            "interpretation": (
                "Descriptive paired primary hits at each selected filled seat. Seat membership changes "
                "across ranking rules, so this is not the complete-slate sweep endpoint."
            ),
        },
    }
    (root / "replay/uncertainty.json").write_text(
        json.dumps(uncertainty, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    build()
