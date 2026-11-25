#!/usr/bin/env python3
"""Build and independently reconcile readable R22 scorecard tables.

Standard-library only. Inputs are immutable R22 history/repeat and forward/ranked
directories. Outputs are written only below --out-dir.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
from typing import Any


COMPETITIONS = ("eng.1", "esp.1", "ger.1", "ita.1", "fra.1")
WINDOWS = {
    "evaluation": "evaluation",
    "recent": "recent",
    "extension": "november_extension",
}
METRICS = ("score_top1", "score_top3", "wdl", "actual_ou")
TRACKS = (
    ("r7_vs_candidate", "r7"),
    ("r21_vs_candidate", "r21"),
    ("market_vs_candidate", "market"),
)
EXPECTED_PROTOCOL = "71ffd263c1d1835ef008d594f39e6e6112c0902b2b872887ab080fb443ea594c"
EXPECTED_R22_VERSION = "R22-five-league-draw-preserving-1"


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def tree_inventory(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): sha_file(p)
            for p in sorted(root.rglob("*")) if p.is_file()}


def tree_digest(inventory: dict[str, str]) -> str:
    body = b"".join(name.encode() + b"\0" + bytes.fromhex(digest)
                    for name, digest in sorted(inventory.items()))
    return sha_bytes(body)


def require(test: bool, message: str) -> None:
    if not test:
        raise ValueError(message)


def canonical_record_sha(record: dict[str, Any]) -> str:
    body = {k: v for k, v in record.items() if k != "record_sha256"}
    raw = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                     allow_nan=False).encode("utf-8")
    return sha_bytes(raw)


def aware(value: str) -> datetime:
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(stamp.tzinfo is not None, f"timestamp lacks timezone offset: {value}")
    return stamp.astimezone(timezone.utc)


def read_json(path: Path) -> Any:
    return json.loads(path.read_bytes())


def verify_freeze_record(folder: Path, ref: dict) -> tuple[dict, str]:
    filename = ref["file"]
    require(Path(filename).name == filename, f"nonlocal receipt path: {filename}")
    raw = (folder / filename).read_bytes()
    record = json.loads(raw)
    digest = canonical_record_sha(record)
    require(record.get("record_sha256") == digest == ref.get("sha256"),
            f"freeze SHA mismatch: {filename}")
    require(record.get("freeze_id") == ref.get("id")
            and record.get("recorded_at") == ref.get("recorded_at"),
            f"freeze reference mismatch: {filename}")
    require(record.get("stage") == "prematch" and record.get("revision") == 1
            and record.get("previous_sha256") is None
            and record.get("evaluation_slot") == "FIRST_PREMATCH",
            f"not a preserved original first prematch receipt: {filename}")
    return record, sha_bytes(raw)


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n", extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def close_num(a: Any, b: Any, tol: float = 1e-12) -> bool:
    if a is None or b is None:
        return a is b
    return math.isclose(float(a), float(b), rel_tol=0.0, abs_tol=tol)


def extract_forward(forward: Path, ranked: Path) -> tuple[list[dict], dict, dict]:
    index_bytes = (forward / "receipts.json").read_bytes()
    index = json.loads(index_bytes)
    reg, reg_raw_sha = verify_freeze_record(forward, index["registration"])
    identity = reg["payload"]["identity"]
    fixtures = reg["payload"]["fixtures"]
    matches = index["matches"]
    require(reg["track"] == "research-r22-draw-preserving-20261125-registration",
            "unexpected R22 first-issue registration track")
    require(identity["version"] == EXPECTED_R22_VERSION and identity["formal_kpi_eligible"] is False,
            "R22 registration version or research-only status differs")
    require(tuple(identity["competitions"]) == COMPETITIONS, "R22 registration competition order differs")
    require(len(fixtures) == 45 and set(fixtures) == set(matches), "R22 slate is not the 45 registered targets")
    require(len(identity.get("already_started", [])) == 3 and len(fixtures) + 3 == 48,
            "R22 slate does not reconcile to the original 48-match R7 population")
    registration_at = reg["recorded_at"]
    registration_sha = reg["record_sha256"]

    plan_ref = read_json(ranked / "plan.json")
    plan, plan_raw_sha = verify_freeze_record(ranked, plan_ref)
    require(plan["track"] == "research-ranked-first-scores-r10-registration",
            "unexpected R22 ranked plan track")
    require(plan["payload"]["identity"]["source_registration"] == registration_sha,
            "ranked plan does not bind to R22 registration")
    require(plan["payload"]["fixtures"] == fixtures, "ranked plan fixture population differs")
    require(aware(registration_at) < aware(plan["recorded_at"]), "ranked plan predates R22 registration")
    selected = plan["payload"]["identity"]["selected"]
    seat_by_id = {}
    for code in COMPETITIONS:
        seats = selected.get(code, [])
        require(len(seats) == 3, f"R22 ranked seats not exactly three for {code}")
        for seat_no, seat in enumerate(seats, 1):
            mid = seat["match_id"]
            require(mid not in seat_by_id, f"duplicate R22 ranked seat for {mid}")
            seat_by_id[mid] = (seat_no, seat)

    rows = []
    raw_hashes = {"forward/receipts.json": sha_bytes(index_bytes),
                  "ranked/plan.json": sha_file(ranked / "plan.json"),
                  f"ranked/{plan_ref['file']}": plan_raw_sha}
    issue_payloads = {}
    for mid, registered in fixtures.items():
        ref = matches[mid]
        record, raw_sha = verify_freeze_record(forward, ref)
        raw_hashes[f"forward/{ref['file']}"] = raw_sha
        fixture = record["fixture"]
        payload = record["payload"]
        require(record["track"] == reg["payload"]["track"] and record["match_id"] == mid
                and payload.get("registration_sha256") == registration_sha,
                f"R22 first issue does not bind to registration: {mid}")
        fields = ("match_id", "cohort", "stage", "home", "away", "kickoff_at")
        require(all(fixture.get(k) == registered.get(k) for k in fields),
                f"R22 frozen fixture identity differs: {mid}")
        require(aware(registration_at) <= aware(fixture["cutoff_at"])
                <= aware(record["recorded_at"]) < aware(fixture["kickoff_at"]),
                f"R22 receipt chronology invalid: {mid}")
        code = fixture["cohort"]
        require(code in COMPETITIONS, f"unexpected R22 competition: {code}")
        forecasts = payload["forecasts"]
        for arm in ("r7", "r21", "candidate"):
            require(arm in forecasts and len(forecasts[arm]["top3"]) == 3
                    and len(set(forecasts[arm]["top3"])) == 3
                    and forecasts[arm]["primary"] == forecasts[arm]["top3"][0],
                    f"invalid ordered forecast for {mid} arm {arm}")
        market_forecast = forecasts.get("market") or {}
        if market_forecast.get("top3"):
            require(len(market_forecast.get("top3", [])) == 3
                    and market_forecast.get("primary") == market_forecast["top3"][0],
                    f"invalid ordered market forecast for {mid}")
        prices = payload.get("prices") or {}
        market_evidence = payload.get("market_evidence") or {}
        total_market = market_evidence.get("total") or {}
        h2h_market = market_evidence.get("h2h") or {}
        seat_no, seat = seat_by_id.get(mid, (None, {}))
        if seat_no:
            require(seat["first_issue"]["sha256"] == record["record_sha256"]
                    and seat["primary"] == forecasts["candidate"]["primary"]
                    and seat["top3"] == forecasts["candidate"]["top3"],
                    f"ranked seat disagrees with preserved first issue: {mid}")
        row = {
            "competition": code,
            "match_id": mid,
            "stage": fixture["stage"],
            "home_id": fixture["home"],
            "away_id": fixture["away"],
            "home": payload["home_name"],
            "away": payload["away_name"],
            "kickoff_at_source": fixture["kickoff_at"],
            "registration_recorded_at": registration_at,
            "first_issue_recorded_at": record["recorded_at"],
            "fixture_cutoff_at": fixture["cutoff_at"],
            "odds_cutoff_at": payload.get("odds_cutoff_at"),
            "ranked_plan_recorded_at": plan["recorded_at"],
            "ranked_seat": seat_no,
            "ranked_first_probability": seat.get("first_probability"),
            "total_line": payload.get("line"),
            "market_total_line": (prices.get("total") or {}).get("line"),
            "market_h2h_home": (prices.get("h2h") or {}).get("home"),
            "market_h2h_draw": (prices.get("h2h") or {}).get("draw"),
            "market_h2h_away": (prices.get("h2h") or {}).get("away"),
            "market_total_over": (prices.get("total") or {}).get("over"),
            "market_total_under": (prices.get("total") or {}).get("under"),
            "market_h2h_bookmaker": h2h_market.get("bookmaker"),
            "market_h2h_observed_at": h2h_market.get("observed_at"),
            "market_total_bookmaker": total_market.get("bookmaker"),
            "market_total_observed_at": total_market.get("observed_at"),
            "market_source_url": h2h_market.get("source_url"),
            "market_source_sha256": h2h_market.get("source_sha256"),
            "market_total_source_url": total_market.get("source_url"),
            "market_total_source_sha256": total_market.get("source_sha256"),
            "r7_primary": forecasts["r7"]["primary"],
            "r7_ordered_top3": "|".join(forecasts["r7"]["top3"]),
            "r21_primary": forecasts["r21"]["primary"],
            "r21_ordered_top3": "|".join(forecasts["r21"]["top3"]),
            "r22_primary": forecasts["candidate"]["primary"],
            "r22_ordered_top3": "|".join(forecasts["candidate"]["top3"]),
            "market_primary": market_forecast.get("primary"),
            "market_ordered_top3": "|".join(market_forecast.get("top3", [])),
            "market_forecast_missing_reason": "; ".join((payload.get("quality") or {}).get("warnings", []))
            or "market scoreline forecast absent; a WDL pick may still be present"
            if not market_forecast.get("top3") else None,
            "first_issue_sha256": record["record_sha256"],
            "first_issue_file_sha256": raw_sha,
        }
        rows.append(row)
        issue_payloads[mid] = payload

    require(len(seat_by_id) == 15, "R22 ranked plan does not contain 15 seats")
    ordered = sorted(rows, key=lambda r: (COMPETITIONS.index(r["competition"]),
                                           aware(r["kickoff_at_source"]), r["match_id"]))
    forward_report = {
        "registration_sha256": registration_sha,
        "registration_recorded_at": registration_at,
        "registered_matches": len(fixtures),
        "already_started": identity.get("already_started", []),
        "ranked_plan_sha256": plan["record_sha256"],
        "ranked_plan_recorded_at": plan["recorded_at"],
        "ranked_seats": len(seat_by_id),
        "formal_kpi_eligible": False,
        "receipt_file_sha256": dict(sorted(raw_hashes.items())),
    }
    return ordered, forward_report, issue_payloads


def build_scorecard(history: Path, metrics: dict) -> tuple[list[dict], dict]:
    doses = {}
    input_doc = read_json(history / "inputs.json")
    require(input_doc["version"] == EXPECTED_R22_VERSION
            and input_doc["protocol_sha256"] == EXPECTED_PROTOCOL,
            "R22 historical input version/protocol differs")
    require(metrics["version"] == EXPECTED_R22_VERSION
            and metrics["protocol_sha256"] == EXPECTED_PROTOCOL
            and metrics["formal_kpi_eligible"] is False,
            "R22 historical metrics version/protocol/eligibility differs")
    for code in COMPETITIONS:
        fit_path = history / "main" / code / "fit.json"
        fit = read_json(fit_path)
        saved = input_doc["competitions"][code]
        require(fit["competition"] == code and fit["version"] == EXPECTED_R22_VERSION,
                f"R22 fit identity differs: {code}")
        require(fit["r21_fit_sha256"] == saved["r21_fit_sha256"], f"R22 fit R21 parent hash differs: {code}")
        doses[code] = fit

    rows = []
    by_window = {}
    compare_specs = (("r7", "r7_vs_candidate"), ("r21", "r21_vs_candidate"),
                     ("market", "market_vs_candidate"))
    for label, source_window in WINDOWS.items():
        total = metrics["overall"][source_window]
        by_comp = {code: metrics["competitions"][code][source_window] for code in COMPETITIONS}
        require(sum(block["population"] for block in by_comp.values()) == total["population"],
                f"{label}: competition population sum mismatch")
        for baseline, compare_key in compare_specs:
            for metric in METRICS:
                overall = total["comparisons"][compare_key]
                for track in (baseline, "candidate"):
                    league_hits = sum(b["comparisons"][compare_key]["tracks"][track]["metrics"][metric]["hits"]
                                      for b in by_comp.values())
                    league_eligible = sum(b["comparisons"][compare_key]["tracks"][track]["metrics"][metric]["eligible"]
                                          for b in by_comp.values())
                    stats = overall["tracks"][track]["metrics"][metric]
                    require((league_hits, league_eligible) == (stats["hits"], stats["eligible"]),
                            f"{label}/{compare_key}/{track}/{metric}: competition totals mismatch")
                pairs = [b["comparisons"][compare_key]["paired"][metric] for b in by_comp.values()]
                paired = overall["paired"][metric]
                for field in ("eligible", "gained", "lost", "net_hits"):
                    require(sum(int(p[field]) for p in pairs) == int(paired[field]),
                            f"{label}/{compare_key}/{metric}: paired {field} sum mismatch")
                require(paired["net_hits"] == paired["gained"] - paired["lost"],
                        f"{label}/{compare_key}/{metric}: net does not equal gained minus lost")

        seat_fields = ("batches", "full_batches", "short_batches", "planned_slots", "occupied_slots",
                       "three_first_sweeps", "three_score_sweeps")
        for field in seat_fields:
            require(sum(int(b["three_seat_sweep"][field]) for b in by_comp.values())
                    == int(total["three_seat_sweep"][field]), f"{label}: seat {field} sum mismatch")
        for seat_no in ("1", "2", "3"):
            league_occupied = sum(int(b["three_seat_sweep"]["per_seat"][seat_no]["occupied"])
                                  for b in by_comp.values())
            require(league_occupied == int(total["three_seat_sweep"]["per_seat"][seat_no]["occupied"]),
                    f"{label}: seat {seat_no} availability sum mismatch")
        for size in ("1", "2"):
            league_short = sum(int(b["three_seat_sweep"].get("short_batch_sizes", {}).get(size, 0))
                               for b in by_comp.values())
            require(league_short == int(total["three_seat_sweep"].get("short_batch_sizes", {}).get(size, 0)),
                    f"{label}: short-batch size {size} sum mismatch")

        for code, block in [*((c, by_comp[c]) for c in COMPETITIONS), ("overall", total)]:
            seat = block["three_seat_sweep"]
            for metric in METRICS:
                if code == "overall":
                    counts = {
                        "r7": total["comparisons"]["r7_vs_candidate"]["tracks"]["r7"]["metrics"][metric],
                        "r21": total["comparisons"]["r21_vs_candidate"]["tracks"]["r21"]["metrics"][metric],
                        "r22": total["comparisons"]["r7_vs_candidate"]["tracks"]["candidate"]["metrics"][metric],
                        "market": total["comparisons"]["market_vs_candidate"]["tracks"]["market"]["metrics"][metric],
                    }
                else:
                    counts = {
                        "r7": block["comparisons"]["r7_vs_candidate"]["tracks"]["r7"]["metrics"][metric],
                        "r21": block["comparisons"]["r21_vs_candidate"]["tracks"]["r21"]["metrics"][metric],
                        "r22": block["comparisons"]["r7_vs_candidate"]["tracks"]["candidate"]["metrics"][metric],
                        "market": block["comparisons"]["market_vs_candidate"]["tracks"]["market"]["metrics"][metric],
                    }
                row = {"competition": code, "window": label, "metric": metric,
                       "population": block["population"]}
                for name, stats in counts.items():
                    row[f"{name}_hits"] = stats["hits"]
                    row[f"{name}_eligible"] = stats["eligible"]
                row.update({
                    "r22_validation_dose": doses[code]["dose"] if code != "overall" else None,
                    "r21_original_score_dose": doses[code]["r21_original_score_dose"] if code != "overall" else None,
                    "validation_games": doses[code]["validation_games"] if code != "overall" else None,
                    "validation_through": doses[code]["validation_through"] if code != "overall" else None,
                    "batches": seat["batches"], "full_batches": seat["full_batches"],
                    "short_batches": seat["short_batches"],
                    "three_first_sweeps": seat["three_first_sweeps"],
                    "three_score_sweeps": seat["three_score_sweeps"],
                    "planned_seats": seat["planned_slots"],
                    "available_seats": seat["occupied_slots"],
                    "empty_seats": seat["planned_slots"] - seat["occupied_slots"],
                    "short_batch_sizes": json_text(seat.get("short_batch_sizes", {})),
                    "seat1_available": seat["per_seat"]["1"]["occupied"],
                    "seat2_available": seat["per_seat"]["2"]["occupied"],
                    "seat3_available": seat["per_seat"]["3"]["occupied"],
                })
                for baseline, compare_key in compare_specs:
                    paired = block["comparisons"][compare_key]["paired"][metric]
                    prefix = {"r7": "vs_r7", "r21": "vs_r21", "market": "vs_market"}[baseline]
                    ci = paired.get("date_cluster_ci")
                    row.update({f"gained_{prefix}": paired["gained"],
                                f"lost_{prefix}": paired["lost"],
                                f"net_hits_{prefix}": paired["net_hits"],
                                f"net_rate_{prefix}": paired["net_rate"],
                                f"date_cluster_95_low_{prefix}": ci[0] if ci else None,
                                f"date_cluster_95_high_{prefix}": ci[1] if ci else None})
                rows.append(row)
        by_window[label] = total["population"]

    # Keep rows in requested order: competition, then window, then metric.
    comp_order = (*COMPETITIONS, "overall")
    window_order = tuple(WINDOWS)
    metric_order = METRICS
    rows.sort(key=lambda r: (comp_order.index(r["competition"]), window_order.index(r["window"]),
                             metric_order.index(r["metric"])))
    require(len(rows) == (len(COMPETITIONS) + 1) * len(WINDOWS) * len(METRICS),
            f"scorecard row count differs: {len(rows)}")
    return rows, {"window_populations": by_window, "validation_doses": doses}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--historical", type=Path, required=True)
    parser.add_argument("--repeat", type=Path, required=True)
    parser.add_argument("--forward", type=Path, required=True)
    parser.add_argument("--ranked", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    history, repeat, forward, ranked, out = (p.resolve() for p in
        (args.historical, args.repeat, args.forward, args.ranked, args.out_dir))
    out.mkdir(parents=True, exist_ok=True)

    hist_inventory = tree_inventory(history)
    repeat_inventory = tree_inventory(repeat)
    require(hist_inventory == repeat_inventory, "R22 historical and repeat trees differ by path or byte SHA")
    require(len(hist_inventory) == 38, f"expected 38 files in each R22 history tree, got {len(hist_inventory)}")
    metrics = read_json(history / "metrics.json")
    rows, audit = build_scorecard(history, metrics)
    picks, freeze_audit, _ = extract_forward(forward, ranked)

    score_fields = list(rows[0])
    write_csv(out / "scorecard.csv", rows, score_fields)
    pick_fields = list(picks[0])
    write_csv(out / "forward-picks.csv", picks, pick_fields)

    source_roots = {"historical": history, "historical_repeat": repeat,
                    "forward": forward, "ranked": ranked}
    source_inventory = {}
    for label, root in source_roots.items():
        source_inventory[label] = {
            "root_label": label,
            "files": tree_inventory(root),
            "tree_sha256": tree_digest(tree_inventory(root)),
        }
    source_inventory["historical_repeat_matches_reference"] = True
    source_inventory["registration_sha256"] = freeze_audit["registration_sha256"]
    source_inventory["ranked_plan_sha256"] = freeze_audit["ranked_plan_sha256"]
    source_inventory["forward_receipt_file_sha256"] = freeze_audit["receipt_file_sha256"]
    (out / "source-hashes.json").write_text(json.dumps(source_inventory, indent=2, ensure_ascii=False) + "\n",
                                             encoding="utf-8")

    table_hashes = {name: sha_file(out / name) for name in ("scorecard.csv", "forward-picks.csv", "source-hashes.json")}
    script_hash = sha_file(Path(__file__).resolve())
    builder_source = Path(__file__).resolve()
    builder_copy = out / builder_source.name
    if builder_source != builder_copy.resolve():
        shutil.copyfile(builder_source, builder_copy)
    manifest = {
        "schema": "r22-compact-scorecard-v1",
        "r22_version": EXPECTED_R22_VERSION,
        "r22_protocol_sha256": EXPECTED_PROTOCOL,
        "historical_source_tree_sha256": tree_digest(hist_inventory),
        "historical_repeat_tree_sha256": tree_digest(repeat_inventory),
        "historical_files_per_tree": len(hist_inventory),
        "historical_and_repeat_byte_identical": True,
        "forward_registration_sha256": freeze_audit["registration_sha256"],
        "forward_registration_recorded_at": freeze_audit["registration_recorded_at"],
        "ranked_plan_sha256": freeze_audit["ranked_plan_sha256"],
        "ranked_plan_recorded_at": freeze_audit["ranked_plan_recorded_at"],
        "forward_registered_matches": freeze_audit["registered_matches"],
        "forward_ranked_seats": freeze_audit["ranked_seats"],
        "scorecard_rows": len(rows),
        "forward_pick_rows": len(picks),
        "window_populations": audit["window_populations"],
        "r22_validation_doses_by_competition": {c: audit["validation_doses"][c]["dose"] for c in COMPETITIONS},
        "scorecard_files_sha256": table_hashes,
        "builder_sha256": script_hash,
        "sources": {
            "historical": str(history), "historical_repeat": str(repeat),
            "forward": str(forward), "ranked": str(ranked),
        },
        "formal_kpi_eligible": False,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                                        encoding="utf-8")
    readme = f"""# R22 compact scorecard

Research-only readable tables built by `build_scorecard.py` from the original R22 historical and repeat output directories and immutable R22 forward/ranked first records. No model training, tuning, or issue writing occurs in this builder.

## Files

- `scorecard.csv`: exactly {len(rows)} rows: five competitions plus overall × evaluation, recent, extension × four metrics.
- `forward-picks.csv`: all {len(picks)} preserved R22 first issues, sorted by competition, original kickoff timestamp, then match ID. Each row keeps ordered top-three scores for R7, R21, R22 and market, original offset-qualified registration/issue/cutoff/kickoff clocks, total line and source market quote provenance when available.
- `source-hashes.json`: per-file SHA-256 inventories for both historical trees and the frozen forward/ranked roots.
- `manifest.json`: input tree digests, protocol and freeze hashes, output hashes, coverage, doses and row counts.
- `SHA256SUMS`: hashes for the scorecard, forward picks, source inventory, manifest, builder and this README.

## Reading the scorecard

Each row reports R7, R21, R22 candidate and market hits/eligible for one metric. Pairwise `gained_*`, `lost_*`, `net_hits_*`, `net_rate_*`, and `date_cluster_95_*` columns treat R22 as the candidate against that baseline. The confidence intervals are the original date-clustered 95% intervals from R22 metrics. `actual_ou` is retained under the source metric name; its hit and eligible counts are copied from the R22 report without reinterpretation.

`r22_validation_dose` is the fixed score dose selected on the 2024/25 validation sample for that league. `three_first_sweeps` counts complete three-seat batches whose three first choices all hit. Full/short batches, planned/available/empty seat positions, and availability by seat are included on each row. Short-batch size counts are retained as JSON in the CSV cell.

Historical window populations: {json.dumps(audit['window_populations'], sort_keys=True)}. R22 validation doses: {json.dumps(manifest['r22_validation_doses_by_competition'], sort_keys=True)}. The forward registration was recorded at {freeze_audit['registration_recorded_at']}; the ranked plan at {freeze_audit['ranked_plan_recorded_at']}. These forecasts are research-only and are not formally KPI-eligible.

## Rebuild

```bash
python3 build_scorecard.py \\
  --historical /path/to/r22-historical \\
  --repeat /path/to/r22-historical-repeat \\
  --forward /path/to/r22-forward \\
  --ranked /path/to/r22-ranked \\
  --out-dir /path/to/r22-compact-tables
```

Only Python's standard library is required. The builder verifies both history directories file-by-file, reconciles league totals to overall totals, validates frozen record SHAs/identity/chronology, and checks the ranked plan's fixture population and 15 seat bindings before writing outputs.
"""
    (out / "README.md").write_text(readme, encoding="utf-8")
    files = ("scorecard.csv", "forward-picks.csv", "source-hashes.json", "manifest.json",
             "README.md", Path(__file__).name)
    sums = "".join(f"{sha_file(out / name) if name != Path(__file__).name else script_hash}  {name}\n"
                   for name in files)
    (out / "SHA256SUMS").write_text(sums, encoding="utf-8")
    print(json.dumps({
        "scorecard_rows": len(rows), "forward_pick_rows": len(picks),
        "historical_files_per_tree": len(hist_inventory), "historical_trees_equal": True,
        "registration_sha256": freeze_audit["registration_sha256"],
        "registration_recorded_at": freeze_audit["registration_recorded_at"],
        "ranked_plan_sha256": freeze_audit["ranked_plan_sha256"],
        "ranked_seats": freeze_audit["ranked_seats"],
        "scorecard_sha256": table_hashes["scorecard.csv"],
        "forward_picks_sha256": table_hashes["forward-picks.csv"],
        "source_hashes_sha256": table_hashes["source-hashes.json"],
        "manifest_sha256": sha_file(out / "manifest.json"),
        "sha256sums_sha256": sha_file(out / "SHA256SUMS"),
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
