#!/usr/bin/env python3
"""Extract the review tables from the R23 replays and original research freezes."""

import argparse
import csv
import json
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
CODES = ("eng.1", "esp.1", "ger.1", "ita.1", "fra.1")
WINDOWS = ("validation_2024_25", "evaluation", "recent", "november_extension")
ARMS = ("r7", "r22", "market", "candidate", "full_dose")
METRICS = ("score_top1", "score_top3", "wdl", "actual_ou")


def dump_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read(path):
    return json.loads(path.read_bytes())


def paired_values(pair):
    low, high = pair["date_cluster_ci"] or (None, None)
    return {
        "paired_eligible": pair["eligible"],
        "gained": pair["gained"],
        "lost": pair["lost"],
        "tied": pair["tied"],
        "net_hits": pair["net_hits"],
        "net_rate": pair["net_rate"],
        "matchday_clusters": pair["matchday_clusters"],
        "date_cluster_95_low": low,
        "date_cluster_95_high": high,
    }


def league_weights(replay, weights):
    rows = []
    for code in CODES:
        fit = read(replay / "main" / code / "fit.json")
        row = weights[code]
        rows.append({
            "competition": code,
            "dose": row["dose"],
            "beta_for": row["beta"][0],
            "beta_against": row["beta"][1],
            "training_games": row["training_games"],
            "training_through": row["training_through"],
            "training_outside_grid": row["training_outside_grid"],
            "validation_games": fit["validation_games"],
            "validation_through": row["validation_through"],
            "validation_trials": json.dumps(fit["validation_trials"], sort_keys=True, separators=(",", ":")),
            "refit_beta_for": row["forward_beta"][0],
            "refit_beta_against": row["forward_beta"][1],
            "refit_games": row["forward_games"],
            "refit_through": row["forward_through"],
            "refit_outside_grid": row["forward_outside_grid"],
        })
    return rows


def write_report(replay, output):
    data = read(replay / "metrics.json")
    summary, settlements, paired, coverage, seats = [], [], [], [], []
    for code in (*CODES, "all"):
        league = data["overall"] if code == "all" else data["competitions"][code]
        for window in WINDOWS:
            block = league[window]
            key = {"competition": code, "window": window, "population": block["population"]}
            for arm in ARMS:
                track = block["tracks"][arm]
                for metric in METRICS:
                    summary.append(dict(key, track=arm, metric=metric, **track["metrics"][metric]))
                settlements.append(dict(key, track=arm, **track["total_settlements"]))
                batch = block["three_seat_sweep"][arm]
                seats.append(dict(
                    key, track=arm, full_batches=batch["full_batches"], short_batches=batch["short_batches"],
                    three_first_sweeps=batch["three_first_sweeps"], three_score_sweeps=batch["three_score_sweeps"],
                    occupied_slots=batch["occupied_slots"], planned_slots=batch["planned_slots"],
                ))
            for comparison, metrics in sorted(block["paired"].items()):
                for metric in METRICS[:2]:
                    paired.append(dict(key, comparison=comparison, metric=metric, **paired_values(metrics[metric])))
            signal = block["coverage"]
            coverage.append(dict(
                key, both_clubs=signal["both_clubs"], one_club=signal["one_club"],
                neither_club=signal["neither_club"], both_club_coverage=signal["both_club_coverage"],
                neutral_fallback_matches=signal["neutral_fallback_matches"],
                neutral_feature_vectors=signal["neutral_feature_vectors"],
                home_missing_identity=signal["sides"]["home"]["missing_identity"],
                away_missing_identity=signal["sides"]["away"]["missing_identity"],
                home_valid_observations=signal["sides"]["home"]["valid_observations"],
                away_valid_observations=signal["sides"]["away"]["valid_observations"],
                certified_market_as_of=signal["certified_market_as_of"],
                market_time_basis=json.dumps(signal["market_time_basis"], sort_keys=True, separators=(",", ":")),
            ))
    output.mkdir(parents=True, exist_ok=True)
    dump_csv(output / "league-weights.csv", league_weights(replay, data["weights"]))
    dump_csv(output / "historical-metrics.csv", summary)
    dump_csv(output / "totals-settlement.csv", settlements)
    dump_csv(output / "paired-results.csv", paired)
    dump_csv(output / "historical-coverage.csv", coverage)
    dump_csv(output / "three-seat-batches.csv", seats)


def write_forward(firsts, ranked, output):
    index = read(firsts / "receipts.json")
    rows = []
    for mid, ref in sorted(index["matches"].items()):
        record = read(firsts / ref["file"])
        fixture, payload = record["fixture"], record["payload"]
        r7, r22, r23 = (payload["forecasts"][arm] for arm in ("r7", "r22", "candidate"))
        rows.append(dict(
            match_id=mid, competition=fixture["cohort"], home=payload["home_name"], away=payload["away_name"],
            kickoff_at=fixture["kickoff_at"], cutoff_at=fixture["cutoff_at"], recorded_at=record["recorded_at"],
            freeze_id=record["freeze_id"], record_sha256=record["record_sha256"],
            r7_first_issue=payload["r7_first_issue"], r22_first_issue=payload["r22_first_issue"],
            r7_ordered_three="|".join(r7["top3"]), r22_ordered_three="|".join(r22["top3"]),
            r23_ordered_three="|".join(r23["top3"]), first_probability=payload["quality"]["p_first"],
            wdl=r23["wdl"], total_side=r23["total_side"], actual_line=payload["line"],
            market_gaps="|".join(payload["market_gaps"]),
            home_valid_observations=payload["process"]["home"]["n"],
            away_valid_observations=payload["process"]["away"]["n"],
        ))
    dump_csv(output / "research-firsts.csv", rows)

    plan = read(ranked / "plan.json")
    record = read(ranked / plan["file"])
    seats = []
    for code, league in sorted(record["payload"]["identity"]["selected"].items()):
        for position, pick in enumerate(league, 1):
            seats.append(dict(
                competition=code, seat=position, match_id=pick["match_id"], home=pick["home"], away=pick["away"],
                kickoff_at=pick["kickoff_at"], first_probability=pick["first_probability"],
                ordered_three="|".join(pick["top3"]), first_issue_sha256=pick["first_issue"]["sha256"],
                rank_sha256=plan["sha256"],
            ))
    dump_csv(output / "research-ranked-seats.csv", seats)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay", type=Path, default=PACKAGE / "replay/reference")
    parser.add_argument("--output-dir", type=Path, default=PACKAGE / "reports")
    args = parser.parse_args()
    write_report(args.replay, args.output_dir)
    write_forward(PACKAGE / "forward", PACKAGE / "ranked", args.output_dir)
