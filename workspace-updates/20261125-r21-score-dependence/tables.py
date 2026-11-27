#!/usr/bin/env python3
"""Build transparent R21 coverage, coefficient and paired-gain tables."""
from __future__ import annotations

import csv
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
WINDOWS = ("evaluation", "recent", "november_extension")
COMPS = ("eng.1", "esp.1", "ger.1", "ita.1", "fra.1")
PAIRS = ("candidate_vs_r7", "candidate_vs_market", "candidate_vs_constant", "candidate_vs_constant_matched")
METRICS = ("score_top1", "score_top3", "wdl", "actual_ou")


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def build(root: Path = HERE, output_dir: Path | None = None) -> None:
    replay = root / "replay/reference"
    metrics = json.loads((replay / "metrics.json").read_bytes())
    coverage, gains, weights = [], [], []
    for code in COMPS:
        for window in WINDOWS:
            part = metrics["competitions"][code][window]
            exposure = part["side_exposure"]
            two_sides = int(exposure.get("2", 0))
            one_or_more = two_sides + int(exposure.get("1", 0))
            coverage.append({
                "competition": code, "window": window, "fixtures": part["population"],
                "both_sides_with_prior_history": two_sides,
                "at_least_one_side_with_prior_history": one_or_more,
                "no_side_with_prior_history": int(exposure.get("0", 0)),
                "registered_batch_seats": part["batch_results"]["occupied_slots"],
                "planned_batch_seats": part["batch_results"]["planned_slots"],
            })
            for pair in PAIRS:
                for metric in METRICS:
                    result = part["paired"][pair][metric]
                    ci = result.get("date_cluster_ci")
                    gains.append({
                        "competition": code, "window": window, "comparison": pair, "metric": metric,
                        "eligible": result["eligible"], "gained": result["gained"], "lost": result["lost"],
                        "net_hits": result["net_hits"], "net_rate": result["net_rate"],
                        "date_cluster_95_low": ci[0] if ci else None,
                        "date_cluster_95_high": ci[1] if ci else None,
                        "fixed_population_net_hits": result["fixed_population_net_hits"],
                        "fixed_population_net_rate": result["fixed_population_net_rate"],
                    })
        fit = json.loads((replay / "main" / code / "fit.json").read_bytes())
        for arm in ("context", "constant"):
            f = fit["fitted"][arm]
            doses = fit["doses"][arm]
            weights.append({
                "competition": code, "arm": arm, "features": ";".join(f["features"]),
                "coefficients": ";".join(format(float(x), ".12g") for x in f["beta"]),
                "training_rows": f["training_rows"], "training_through": fit["training_through"],
                "validation_rows": fit["validation_n"], "validation_through": fit["validation_through"],
                "dose_score": doses["score"], "dose_wdl": doses["wdl"], "dose_total": doses["total"],
            })
    out = output_dir or (root / "reports")
    out.mkdir(exist_ok=True)
    write_csv(out / "competition-window-coverage.csv", coverage, list(coverage[0]))
    write_csv(out / "paired-gains.csv", gains, list(gains[0]))
    write_csv(out / "fitted-weights-and-doses.csv", weights, list(weights[0]))

    lines = [
        "# R21 score-dependence historical and frozen-slate evidence",
        "",
        "Research replay only; no model promotion or formal KPI eligibility. R21 preserves the R7 score marginals and fits a bounded dependence term from prior-match npxG concordance and chance volume.",
        "",
        "## Historical windows",
        "",
        "The evaluation window is the fixed 2025/26 holdout; recent and November-extension windows remain separate. Coverage is by competition and window in [competition-window-coverage.csv](competition-window-coverage.csv). Fit coefficients, validation doses and time bounds are in [fitted-weights-and-doses.csv](fitted-weights-and-doses.csv).",
        "",
        "Paired same-fixture gains and losses, net hits/rates and date-clustered 95% intervals are in [paired-gains.csv](paired-gains.csv). `candidate_vs_r7` is the preferred selected R21 recipe against R7; `candidate_vs_market` is the same-game market ablation; `candidate_vs_constant` compares against the intercept-only model at its own selected doses; `candidate_vs_constant_matched` holds the contextual dose while using intercept-only weights. All four outcome definitions are retained, including total settlement eligibility.",
        "",
        "## Frozen forward slate",
        "",
        "The 45 first issues retain the 2026-11-25 21:17:21.555419 +08 registration; 3 started fixtures are excluded from the original R7 population of 48. The exact registration and ranked-plan SHA values, per-league market/history coverage, and independently reconstructed 15 seats are in [frozen-forward-rank.json](../verification/frozen-forward-rank.json) and [forward-coverage.csv](../verification/forward-coverage.csv). The verifier only reads and hashes the frozen receipts; it does not issue or overwrite records.",
        "",
        "## Raw npxG audit",
        "",
        "[Understat raw verification](../verification/understat/reports/verification.json) independently recalculates all 11,031 fixed R14 events from 35 original getLeagueData responses. npxG/npxGA live in nested `source_history_sides`, separate from the top-level all-shot xG/xGA columns. Competition sums are reconciled against the global totals.",
    ]
    (out / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    build()
