#!/usr/bin/env python3
"""Independently replay and validate a compiled R18 historical evidence package."""

import argparse
import json
from pathlib import Path
import tempfile

from build import make_tables, read_gzip_rows
from common import (ENV, NUMERICAL_VERSIONS, PROTOCOL_SHA256, R15_MANIFEST, R15_SLUG, SOURCE_COMMIT,
                    check_r15, compare_trees, inventory, json_read, plain_rosters, replay_twice, sha)


def verify(args):
    package = args.package.resolve()
    evidence = json_read(package / "evidence.json")
    manifest = json_read(package / "manifest.json")
    if manifest.get("schema") != "WCPP-R18-J1-CUTOFF-1":
        raise ValueError("R18 package schema differs")
    expected_files = manifest["files"]
    actual_files = inventory(package)
    actual_files.pop("manifest.json", None)
    if actual_files != expected_files:
        raise ValueError("R18 package files fail SHA-256 verification")
    if evidence["source_commit"] != SOURCE_COMMIT or evidence["protocol_sha256"] != PROTOCOL_SHA256:
        raise ValueError("R18 source or registration pin differs")
    expected_env = {"python": "3.12", **NUMERICAL_VERSIONS, **ENV}
    if evidence["numerical_environment"] != expected_env:
        raise ValueError("package numerical environment receipt differs")

    reference = package / "reference/r15"
    r15_study = reference
    final_inventory = inventory(reference / "run-final")
    repeat_inventory = inventory(reference / "run-repeat")
    if (final_inventory != repeat_inventory or final_inventory != evidence["inputs"]["r15_final_inventory"]
            or repeat_inventory != evidence["inputs"]["r15_repeat_inventory"]):
        raise ValueError("embedded R15 final and repeat histories are not byte-identical")
    r18_final = inventory(package / "reference/r18/run-final")
    r18_repeat = inventory(package / "reference/r18/run-repeat")
    if (r18_final != r18_repeat or r18_final != evidence["r18_historical_final_inventory"]
            or r18_repeat != evidence["r18_historical_repeat_inventory"]
            or r18_final != inventory(package / "replay")):
        raise ValueError("R18 historical captures or packaged replay differ")
    for name, expected in evidence["r15_originals"].items():
        if sha(reference / name) != expected:
            raise ValueError(f"embedded original R15 evidence changed: {name}")
    for name in ("fit.json", "inputs.json", "forward.json", "forecasts.jsonl.gz"):
        if sha(reference / "run-final" / name) != evidence["r15_originals"][name]:
            raise ValueError(f"R15 final output and retained original evidence disagree: {name}")
    count = len(read_gzip_rows(reference / "forecasts.jsonl.gz"))
    if count != 530:
        raise ValueError(f"original R15 prediction count is {count}, expected 530")
    if sha(args.r5 / "manifest.json") != evidence["inputs"]["r5"]["manifest_sha256"]:
        raise ValueError("R5 package manifest differs from build input")
    if sha(args.r7 / "manifest.json") != evidence["inputs"]["r7"]["manifest_sha256"]:
        raise ValueError("R7 package manifest differs from build input")
    if evidence["inputs"]["rosters"]["snapshot_manifest_sha256"] != sha(reference / "snapshot-manifest.json"):
        raise ValueError("embedded roster snapshot manifest differs from build input")
    forward = evidence["forward_bundle"]
    if inventory(package / "forward/received") != forward["files"]:
        raise ValueError("preserved forward bundle differs from its receipt inventory")

    with tempfile.TemporaryDirectory(prefix="r18-verify-") as td:
        td = Path(td)
        rosters = plain_rosters(reference / "events.jsonl.gz", td)
        roster_sha = sha(rosters)
        if roster_sha != evidence["inputs"]["rosters"]["sha256"]:
            raise ValueError("original roster snapshot differs after decompression")
        if evidence["inputs"]["r15_package_manifest_sha256"] is not None:
            if evidence["inputs"]["r15_package_manifest_sha256"] != R15_MANIFEST:
                raise ValueError("wrong R15 publication checksum")
            check_r15(args.r15_package or args.r5.resolve().parent / R15_SLUG, final_inventory,
                      roster_sha, sha(rosters.parent / "snapshot-manifest.json"))
        first = replay_twice(args.source, SOURCE_COMMIT, td, args.r5, args.r7, r15_study, rosters)
        compare_trees(first, package / "replay")
        tables = td / "tables"
        tables.mkdir()
        make_tables(package / "replay", reference / "forecasts.jsonl.gz", tables)
        compare_trees(tables, package / "tables", exact_bytes=True)

    replay_metrics = json_read(package / "replay/metrics.json")
    if {k: v["population"] for k, v in replay_metrics.items()} != {"evaluation": 380, "recent": 150}:
        raise ValueError("registered R18 historical windows are incomplete")
    if {k: v["updated_features"] for k, v in replay_metrics.items()} != {"evaluation": 268, "recent": 112}:
        raise ValueError("R18 registered changed-feature counts differ")
    full_doses = json_read(reference / "fit.json")["doses"]["full"]
    if full_doses != {"score": 0.0, "wdl": 0.0, "total": 0.0}:
        raise ValueError("frozen R15 full-arm doses are not all zero")
    rows = read_gzip_rows(package / "replay/forecasts.jsonl.gz")
    if len(rows) != 530 or any(row["forecast"]["current"] != row["forecast"]["lagged"] for row in rows):
        raise ValueError("R18 two cutoff arms do not retain identical formal predictions")
    for window in ("evaluation", "recent"):
        seats = json_read(package / "replay" / f"{window}-seats.json")
        if seats["current"] != seats["lagged"]:
            raise ValueError(f"R18 current and lagged selected seats differ in {window}")
    market = {w: m["comparisons"]["market"]["tracks"]["market"]["metrics"]["wdl"]["eligible"]
              for w, m in replay_metrics.items()}
    if market != {"evaluation": 270, "recent": 76} or evidence["market_wdl_coverage"] != market:
        raise ValueError("same-fixture market WDL coverage differs from the identified original quotes")
    if any(m["actual_lines"] for m in replay_metrics.values()):
        raise ValueError("historical J1 windows contain no observed totals line")
    if (evidence["windows"] != {k: v["population"] for k, v in replay_metrics.items()}
            or evidence["feature_changes"] != {k: v["updated_features"] for k, v in replay_metrics.items()}
            or evidence["r15_full_doses"] != full_doses or evidence["same_machine_refits_byte_identical"] is not True
            or evidence["historical_predictions_unchanged_by_cutoff"] is not True):
        raise ValueError("historical evidence summary differs from replay")
    return {"status": "PASS", "source_commit": SOURCE_COMMIT,
            "historical_matches": 530, "windows": {k: v["population"] for k, v in replay_metrics.items()},
            "same_machine_refits_byte_identical": True,
            "package_comparison": "discrete fields exact; floats atol=1e-9, rtol=1e-7",
            "feature_changes": {k: v["updated_features"] for k, v in replay_metrics.items()},
            "r15_full_doses": full_doses,
            "formal_options_identical": True, "market_wdl_coverage": market,
            "forward_bundle": evidence["forward_bundle"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--r5", required=True, type=Path)
    parser.add_argument("--r7", required=True, type=Path)
    parser.add_argument("--r15-package", type=Path, help="published R15 package (defaults to the R5 sibling)")
    print(json.dumps(verify(parser.parse_args()), indent=2))


if __name__ == "__main__":
    main()
