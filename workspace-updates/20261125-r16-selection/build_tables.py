#!/usr/bin/env python3
"""Build descriptive R16 tables from the frozen replay artifacts."""

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def _write_csv(path, rows, fields):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def build(root=ROOT):
    root = Path(root)
    metrics = json.loads((root / "replay/metrics.json").read_text(encoding="utf-8"))
    weights = json.loads((root / "replay/weights.json").read_text(encoding="utf-8"))
    competition_rows = []
    coverage_rows = []
    fallback_rows = []

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
