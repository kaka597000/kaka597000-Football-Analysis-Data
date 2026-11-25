#!/usr/bin/env python3
"""Compile the registered R18 historical cutoff replay from original R15 evidence."""

import argparse
import csv
import gzip
import json
from pathlib import Path
import shutil
import tempfile

from common import (ENV, NUMERICAL_VERSIONS, PROTOCOL_SHA256, R15_MANIFEST, R15_SLUG, SOURCE_COMMIT,
                    check_r15, compare_trees, inventory, json_read, json_write, plain_rosters, replay_twice, sha)


def write_csv(path, rows):
    columns = sorted({key for row in rows for key in row})
    with Path(path).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, ensure_ascii=False, separators=(",", ":")) if isinstance(v, (list, dict))
                             else v for k, v in row.items()})


def flatten(value, prefix=""):
    result = {}
    if isinstance(value, dict):
        for key, child in value.items():
            result.update(flatten(child, f"{prefix}.{key}" if prefix else key))
    elif isinstance(value, list):
        result[prefix] = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    else:
        result[prefix] = value
    return result


def read_gzip_rows(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def make_tables(replay, originals, out):
    forecasts = read_gzip_rows(replay / "forecasts.jsonl.gz")
    match_rows = []
    for row, original in zip(forecasts, read_gzip_rows(originals), strict=True):
        identity = ("id", "cohort", "window", "date", "stage", "home", "away", "home_id", "away_id",
                    "kickoff_at", "source_sha256", "actual", "line")
        record = {k: row[k] for k in identity}
        if any(row[k] != original[k] for k in identity) or any(
                row["forecast"][arm] != original["forecast"][arm] for arm in ("r7", "market")):
            raise ValueError(f"R18 match or comparator differs from its R15 original: {row['id']}")
        home, away = row["actual"]
        record.update(actual_home_goals=home, actual_away_goals=away, actual_score=f"{home}-{away}",
                      last_week_changed=row["last_week_changed"])
        for arm in ("current", "lagged", "r7", "market"):
            pick = row["forecast"][arm]
            for field in ("primary", "top3", "wdl", "total_line", "total_side", "settlement"):
                record[f"{arm}_{field}"] = pick.get(field)
        h2h, totals = original["h2h"] or {}, original["total"] or {}
        wdl_priced = all(h2h.get(k) is not None for k in ("home", "draw", "away"))
        if wdl_priced != (record["market_wdl"] is not None) or totals.get("line") != row["line"]:
            raise ValueError(f"market options and observed prices disagree: {row['id']}")
        record.update(market_priced=wdl_priced or bool(totals), bookmaker=original["bookmaker"],
                      market_time_basis=original["market_time_basis"], paired_market=original["paired_market"])
        for side in ("home", "draw", "away"):
            record[f"market_{side}_odds"] = h2h.get(side)
        for side in ("over", "under"):
            record[f"market_{side}_odds"] = totals.get(side)
        for arm in ("current", "lagged"):
            record[f"{arm}_p_first"] = row["primary_p"][arm]
            record[f"features_{arm}"] = row["features"][arm]
            record[f"process_{arm}"] = row["process"][arm]
        match_rows.append(record)
    write_csv(out / "match-level.csv", match_rows)

    seat_rows = []
    coverage_rows = []
    metrics = json_read(Path(replay) / "metrics.json")
    for window, metric in sorted(metrics.items()):
        with open(Path(replay) / f"{window}-seats.json", encoding="utf-8") as stream:
            day_rows = json.load(stream)
        for arm, days in sorted(day_rows.items()):
            for day in days:
                for selection in day["selected"]:
                    seat_rows.append({"window": window, "arm": arm, "date": day["date"],
                                      "fixture_count": day["fixtures"],
                                      "batch_full_three": day["fixtures"] >= 3,
                                      "batch_three_first_sweep": day["three_first_sweep"], **selection})
        for arm, summary in sorted(metric["rankings"].items()):
            for seat, counts in sorted(summary.get("per_seat", {}).items()):
                seat_rows.append({"window": window, "arm": arm, "seat": seat, **counts})
            seat_rows.append({"window": window, "arm": arm, **{f"all.{k}": v for k, v in summary.items()
                                                                    if not isinstance(v, dict)}})
        local = [r for r in match_rows if r["window"] == window]
        market = metric["comparisons"]["market"]["tracks"]["market"]["metrics"]
        wdl_count = sum(r["market_wdl"] is not None for r in local)
        if (len(local), wdl_count, sum(r["line"] is not None for r in local)) != (
                metric["population"], market["wdl"]["eligible"], metric["actual_lines"]):
            raise ValueError(f"row-level market coverage differs in {window}")
        coverage_rows.append({"window": window, "matches": metric["population"],
                              "actual_lines": metric["actual_lines"],
                              "same_fixture_market_matches": sum(r["market_priced"] for r in local),
                              "market_wdl_matches": wdl_count,
                              "updated_features": metric["updated_features"],
                              "current_roster_coverage_home": metric["prior_roster_coverage"]["current"]["home"],
                              "current_roster_coverage_away": metric["prior_roster_coverage"]["current"]["away"],
                              "lagged_roster_coverage_home": metric["prior_roster_coverage"]["lagged"]["home"],
                              "lagged_roster_coverage_away": metric["prior_roster_coverage"]["lagged"]["away"]})
    write_csv(Path(out) / "seat-and-batch.csv", seat_rows)
    write_csv(Path(out) / "window-coverage.csv", coverage_rows)

    paired_rows = []
    for window, metric in sorted(metrics.items()):
        for against, comparison in sorted(metric["comparisons"].items()):
            paired_rows.append({"window": window, "comparison": against, **flatten(comparison)})
    write_csv(Path(out) / "paired-kpis.csv", paired_rows)


def build(args):
    source = Path(args.source).resolve()
    inputs = {label: Path(getattr(args, label)).resolve() for label in
              ("r5", "r7", "r15_final", "r15_repeat", "r18_historical", "r18_repeat", "rosters")}
    if args.r15_package is not None:
        inputs["r15_package"] = Path(args.r15_package).resolve()
    else:
        sibling = inputs["r5"].parent / R15_SLUG
        if sibling.is_dir():
            inputs["r15_package"] = sibling
    destination = Path(args.out).resolve()
    if destination.exists():
        raise FileExistsError(destination)
    for path in inputs.values():
        if not path.exists():
            raise FileNotFoundError(path)
    final_inventory = inventory(inputs["r15_final"])
    repeat_inventory = inventory(inputs["r15_repeat"])
    if final_inventory != repeat_inventory or len(final_inventory) != 8:
        raise ValueError("R15 final and repeat must have the same eight original output files byte for byte")
    historical_inventory = inventory(inputs["r18_historical"])
    historical_repeat_inventory = inventory(inputs["r18_repeat"])
    if historical_inventory != historical_repeat_inventory or len(historical_inventory) != 5:
        raise ValueError("R18 historical captures must have the same five output files byte for byte")
    forward_bundle = Path(args.forward_bundle).resolve() if args.forward_bundle else None
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".r18-build-", dir=destination.parent) as tmp:
        tmp = Path(tmp)
        output = tmp / "package"
        rosters = plain_rosters(inputs["rosters"], tmp)
        first = replay_twice(source, args.source_commit, tmp, inputs["r5"], inputs["r7"], inputs["r15_final"], rosters)
        compare_trees(first, inputs["r18_historical"], exact_bytes=True)
        compare_trees(first, inputs["r18_repeat"], exact_bytes=True)

        output.mkdir()
        tool_dir = Path(__file__).resolve().parent
        for filename in ("build.py", "verify.py", "common.py"):
            shutil.copyfile(tool_dir / filename, output / filename)
        shutil.copyfile(tool_dir / "README.md", output / "README.md")
        replay = output / "replay"
        shutil.copytree(inputs["r18_historical"], replay)
        reference = output / "reference/r15"
        reference.mkdir(parents=True)
        shutil.copytree(inputs["r15_final"], reference / "run-final")
        shutil.copytree(inputs["r15_repeat"], reference / "run-repeat")
        shutil.copytree(inputs["r18_historical"], output / "reference/r18/run-final")
        shutil.copytree(inputs["r18_repeat"], output / "reference/r18/run-repeat")
        snapshot = rosters.parent / "snapshot-manifest.json"
        if "r15_package" in inputs:
            check_r15(inputs["r15_package"], final_inventory, sha(rosters), sha(snapshot))
        for name in ("fit.json", "inputs.json", "forward.json", "forecasts.jsonl.gz"):
            shutil.copyfile(inputs["r15_final"] / name, reference / name)
        with rosters.open("rb") as src, (reference / "events.jsonl.gz").open("xb") as raw:
            with gzip.GzipFile(filename="", fileobj=raw, mode="wb", compresslevel=6, mtime=0) as packed:
                shutil.copyfileobj(src, packed)
        shutil.copyfile(snapshot, reference / "snapshot-manifest.json")
        (output / "tables").mkdir()
        make_tables(replay, reference / "forecasts.jsonl.gz", output / "tables")

        if forward_bundle is not None:
            forward_out = output / "forward/received"
            if forward_bundle.is_dir():
                shutil.copytree(forward_bundle, forward_out)
            elif forward_bundle.is_file():
                forward_out.mkdir(parents=True)
                shutil.copyfile(forward_bundle, forward_out / forward_bundle.name)
            else:
                raise FileNotFoundError(forward_bundle)
            forward_receipt = {"status": "preserved-for-independent-signature-review",
                               "files": inventory(forward_out)}
        else:
            forward_receipt = {"status": "historical-only", "files": {}}

        input_receipts = {
            "r5": {"manifest_sha256": sha(inputs["r5"] / "manifest.json")},
            "r7": {"manifest_sha256": sha(inputs["r7"] / "manifest.json")},
            "r15_final_inventory": final_inventory,
            "r15_repeat_inventory": repeat_inventory,
            "r15_package_manifest_sha256": R15_MANIFEST if "r15_package" in inputs else None,
            "rosters": {"sha256": sha(rosters), "snapshot_manifest_sha256": sha(snapshot)},
        }

        metrics = json_read(replay / "metrics.json")
        provenance = {
            "schema": "WCPP-R18-J1-CUTOFF-1", "source_commit": args.source_commit,
            "protocol_sha256": PROTOCOL_SHA256,
            "numerical_environment": {"python": "3.12", **NUMERICAL_VERSIONS, **ENV},
            "float_comparison": {"atol": 1e-9, "rtol": 1e-7},
            "inputs": input_receipts,
            "r18_historical_final_inventory": historical_inventory,
            "r18_historical_repeat_inventory": historical_repeat_inventory,
            "r15_originals": {name: sha(reference / name) for name in
                              ("fit.json", "inputs.json", "forward.json", "forecasts.jsonl.gz",
                               "events.jsonl.gz", "snapshot-manifest.json")},
            "same_machine_refits_byte_identical": True,
            "windows": {name: value["population"] for name, value in metrics.items()},
            "feature_changes": {name: value["updated_features"] for name, value in metrics.items()},
            "r15_full_doses": json_read(reference / "fit.json")["doses"]["full"],
            "historical_predictions_unchanged_by_cutoff": all(
                row["forecast"]["current"] == row["forecast"]["lagged"]
                for row in read_gzip_rows(replay / "forecasts.jsonl.gz")),
            "market_wdl_coverage": {w: m["comparisons"]["market"]["tracks"]["market"]["metrics"]["wdl"]["eligible"]
                                    for w, m in metrics.items()},
            "forward_bundle": forward_receipt,
        }
        json_write(output / "evidence.json", provenance)
        json_write(output / "manifest.json", {"schema": provenance["schema"], "files": inventory(output)})
        output.rename(destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("source", "r5", "r7", "out"):
        parser.add_argument("--" + arg, required=True, type=Path)
    reference = Path(__file__).resolve().parent / "reference"
    for arg, relative in (("r15-final", "r15/run-final"), ("r15-repeat", "r15/run-repeat"),
                          ("r18-historical", "r18/run-final"), ("r18-repeat", "r18/run-repeat"),
                          ("rosters", "r15/events.jsonl.gz")):
        parser.add_argument("--" + arg, default=reference / relative, type=Path)
    parser.add_argument("--r15-package", type=Path, help="published R15 package (defaults to the R5 sibling)")
    parser.add_argument("--source-commit", default=SOURCE_COMMIT)
    parser.add_argument("--forward-bundle", type=Path,
                        help="optional immutable signed R18 forward package; preserved separately")
    build(parser.parse_args())


if __name__ == "__main__":
    main()
