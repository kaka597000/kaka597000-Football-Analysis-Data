#!/usr/bin/env python3
"""Build R19 J1 position-role evidence from R15 raw history and signed first issues."""

import argparse
import csv
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

from common import (NUMERICAL_ENV, NUMERICAL_VERSIONS, R15_BUNDLE_SHA256, R15_RECEIPTS_SHA256,
                    R15_SOURCE_COMMIT, R19_PROTOCOL_SHA256, R19_RECORDED_AT,
                    R19_REGISTRATION_ID, R19_REGISTRATION_SHA256, SOURCE_COMMIT,
                    compare_trees, flatten, inventory, read_json, sha, write_json)

OUTPUT_FILES = {"coverage.json", "fit.json", "forecasts.jsonl.gz", "forward.json", "inputs.json",
                "metrics.json", "r15-comparison.json", "roster-coverage.jsonl.gz", "selected-days.jsonl.gz"}


def pinned_source(source, destination):
    actual = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if actual != SOURCE_COMMIT:
        raise ValueError(f"R19 source HEAD {actual} differs from pin {SOURCE_COMMIT}")
    archive = subprocess.check_output(["git", "-C", str(source), "archive", SOURCE_COMMIT,
                                       "runtime", "research/20261125-r19-j1-positions",
                                       "research/20261125-r18-j1-cutoff",
                                       "research/20261125-r15-j1"])
    Path(destination).mkdir(parents=True, exist_ok=True)
    archive_path = Path(destination).parent / "r19-source.tar"
    archive_path.write_bytes(archive)
    with tarfile.open(archive_path) as tar:
        tar.extractall(destination, filter="data")
    archive_path.unlink()
    protocol = Path(destination) / "research/20261125-r19-j1-positions/protocol.json"
    if sha(protocol) != R19_PROTOCOL_SHA256:
        raise ValueError("R19 registered protocol bytes differ")
    return Path(destination)


def check_tree(folder, expected):
    actual = inventory(folder)
    if actual != expected:
        raise ValueError(f"source archive inventory differs: {folder}")
    return actual


def verify_r15_package(package, workflow):
    manifest = read_json(package / "manifest.json")
    if manifest.get("source_commit") != R15_SOURCE_COMMIT or manifest.get("source", {}).get("commit") != R15_SOURCE_COMMIT:
        raise ValueError("embedded R15 package source pin differs")
    listed = manifest.get("files")
    if not isinstance(listed, dict) or not listed:
        raise ValueError("R15 manifest has no original package files")
    for relative, expected in listed.items():
        path = (package / relative).resolve()
        if not path.is_relative_to(package.resolve()) or not path.is_file() or sha(path) != expected:
            raise ValueError(f"R15 original package checksum differs: {relative}")
    if sha(workflow) != manifest["workflow_sha256"]:
        raise ValueError("R15 workflow differs from its original package manifest")
    return manifest


def prospective_receipt(package, data_root, bundle):
    if sha(bundle) != R15_BUNDLE_SHA256:
        raise ValueError("original R15 prospective bundle SHA differs")
    with tarfile.open(bundle, "r:gz") as archive:
        receipts = archive.extractfile("firsts/receipts.json").read()
    if __import__("hashlib").sha256(receipts).hexdigest() != R15_RECEIPTS_SHA256:
        raise ValueError("original R15 receipts SHA differs")
    command = [sys.executable, "-B", str(package / "prospective.py"), "verify",
               "--study-package", str(package), "--data-root", str(data_root),
               "--bundle", str(bundle), "--receipts-sha256", R15_RECEIPTS_SHA256]
    result = subprocess.run(command, cwd=data_root, check=True, text=True, capture_output=True)
    report = json.loads(result.stdout)
    if (report.get("issued") != 10 or report.get("registered") != 17 or report.get("started") != 7
            or report.get("registration_sha256") != "45804bc3636bac38293bf037b887e8cb1e385fd93d981dbdafde419c15336fb0"):
        raise ValueError("original R15 ten-fixture first bundle did not verify")
    return report


def write_csv(path, rows):
    columns = sorted({key for row in rows for key in row})
    with Path(path).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def make_tables(replay, r15_package, out):
    metrics = read_json(replay / "metrics.json")
    r15_coverage = read_json(r15_package / "replay/coverage.json")
    score_rows, paired_rows, coverage_rows = [], [], []
    for window, summary in sorted(metrics.items()):
        for arm, score in sorted(summary["scores"].items()):
            score_rows.append({"window": window, "arm": arm,
                               **flatten(score["metrics"], "metrics"),
                               **flatten(score["total_settlements"], "settlement")})
        for arm, comparison in sorted(summary["paired"].items()):
            paired_rows.append({"window": window, "comparison": "model:" + arm, **flatten(comparison)})
        for comparison, result in sorted(read_json(replay / "r15-comparison.json")[window].items()):
            paired_rows.append({"window": window, "comparison": "r15:" + comparison, **flatten(result)})

        old = r15_coverage["folds"][window]
        new = summary["coverage"]
        for side in ("home", "away"):
            old_status = old["sides"][side]["source_status"]
            new_status = new["sides"][side]["source_status"]
            coverage_rows.append({"window": window, "side": side,
                                  "r15_registered_xi": old_status.get("complete", 0),
                                  "r19_corrected_xi": new_status.get("complete", 0),
                                  "r15_missing_or_rejected": old["fixtures"] - old_status.get("complete", 0),
                                  "r19_missing_or_rejected": new["fixtures"] - new_status.get("complete", 0),
                                  "r15_both_xi": old["both_complete_rosters"],
                                  "r19_both_xi": new["both_complete_rosters"],
                                  "r15_both_prior_xi": old["both_prior_rosters"],
                                  "r19_both_prior_xi": new["both_prior_rosters"],
                                  "r19_role_corrected_rows": new["source_rows"],
                                  "r19_rejected_source_rows": new["rejected_source_rows"]})
    write_csv(out / "window-kpis.csv", score_rows)
    write_csv(out / "paired-comparisons.csv", paired_rows)
    write_csv(out / "xi-coverage.csv", coverage_rows)

    selections = []
    import gzip
    with gzip.open(replay / "selected-days.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            day = json.loads(line)
            for seat in day["selected"]:
                selections.append({"window": day["window"], "date": day["date"],
                                   "fixtures": day["fixtures"],
                                   "full_three": day["fixtures"] >= 3,
                                   "three_primary_sweep": day["three_first_sweep"], **seat})
    write_csv(out / "selected-seats.csv", selections)

    market_rows = []
    for window, summary in sorted(metrics.items()):
        for arm in ("candidate", "r15", "fixed_full", "fixed_form", "market"):
            if arm not in summary["scores"]:
                continue
            score = summary["scores"][arm]["metrics"]
            market_rows.append({"window": window, "arm": arm,
                                "same_fixture_wdl_issued": score["wdl"]["issued"],
                                "same_fixture_wdl_eligible": score["wdl"]["eligible"],
                                "same_fixture_total_line_issued": score["actual_ou"]["issued"],
                                "same_fixture_total_line_eligible": score["actual_ou"]["eligible"],
                                "measured_actual_total_lines": summary["measured_lines"],
                                **{f"total_{k.lower()}": v for k, v in
                                   summary["scores"][arm]["total_settlements"].items()}})
    write_csv(out / "same-fixture-market.csv", market_rows)


def build(args):
    source = args.source.resolve()
    data_root = args.data_root.resolve()
    r5, r7, r10 = (data_root / f"workspace-updates/{name}" for name in
                   ("20261123-all-scope-kpi", "20261123-prematch-literature", "20261125-r10-shot-conversion"))
    out = args.out.resolve()
    if args.from_package is not None:
        package_input = args.from_package.resolve()
        if out == package_input or out.is_relative_to(package_input):
            raise ValueError("--out must be outside --from-package")
        r15_package = package_input / "reference/r15/package"
        r15_bundle = package_input / "reference/r15/first-issues.tar.gz"
        r15_workflow = package_input / "reference/r15/r15-j1-lineups.yml"
        hist = package_input / "reference/r19/historical-final"
        repeat = package_input / "reference/r19/historical-repeat"
        forward = package_input / "forward/issued"
    else:
        r15_package = (args.r15_package or Path("/workspace/scratch/r15-data/workspace-updates/20261125-r15-j1-lineups")).resolve()
        r15_bundle = (args.r15_bundle or Path("/workspace/scratch/r15-data/workspace-updates/20261125-r15-j1-lineups-forward/first-issues.tar.gz")).resolve()
        r15_workflow = (args.r15_workflow or Path("/workspace/scratch/r15-data/.github/workflows/r15-j1-lineups.yml")).resolve()
        hist = (args.historical or Path("/workspace/scratch/r19-historical")).resolve()
        repeat = (args.repeat or Path("/workspace/scratch/r19-historical-repeat")).resolve()
        forward = (args.forward or Path("/workspace/scratch/r19-forward")).resolve()
    if out.exists():
        raise FileExistsError(out)
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError("R19 numerical replay requires Python 3.12; patch version is not pinned")
    for key, value in NUMERICAL_ENV.items():
        os.environ[key] = value
    import numpy, scipy, lightgbm
    actual_versions = {"numpy": numpy.__version__, "scipy": scipy.__version__, "lightgbm": lightgbm.__version__}
    if actual_versions != NUMERICAL_VERSIONS:
        raise RuntimeError(f"R19 numerical dependencies differ: {actual_versions}")

    r15_manifest = verify_r15_package(r15_package, r15_workflow)
    r15_prospective = prospective_receipt(r15_package, data_root, r15_bundle)
    hist_inventory, repeat_inventory = inventory(hist), inventory(repeat)
    if hist_inventory != repeat_inventory or set(hist_inventory) != OUTPUT_FILES:
        raise ValueError("R19 historical and repeat must preserve the same nine original files byte for byte")
    forward_inventory = inventory(forward)
    receipts = read_json(forward / "receipts.json")
    registration = receipts["registration"]
    if (registration["id"] != R19_REGISTRATION_ID or registration["sha256"] != R19_REGISTRATION_SHA256
            or registration["recorded_at"] != R19_RECORDED_AT or len(receipts["matches"]) != 10):
        raise ValueError("R19 original ten-match issue receipt differs")

    with tempfile.TemporaryDirectory(prefix="r19-build-") as td:
        td = Path(td)
        source_tree = pinned_source(source, td / "source")
        runtime = source_tree / "runtime"
        outputs = (td / "new-run-1", td / "new-run-2")
        worker = Path(__file__).resolve().parent / "replay_worker.py"
        command = [sys.executable, "-B", str(worker), str(r15_package), str(data_root), str(runtime), str(td),
                   str(r5), str(r7), str(r10), *(str(p) for p in outputs), str(r15_package / "manifest.json")]
        subprocess.run(command, check=True, env=os.environ.copy())
        compare_trees(outputs[0], outputs[1], exact=True)
        compare_trees(outputs[0], hist)
        compare_trees(outputs[0], repeat)

        out.mkdir(parents=True)
        tool_root = Path(__file__).resolve().parent
        for name in ("build.py", "verify.py", "common.py", "replay_worker.py", "DELIVERY.md"):
            shutil.copyfile(tool_root / name, out / name)
        shutil.copyfile(tool_root / "DELIVERY.md", out / "README.md")
        replay = out / "replay"
        shutil.copytree(hist, replay)
        shutil.copytree(hist, out / "reference/r19/historical-final")
        shutil.copytree(repeat, out / "reference/r19/historical-repeat")

        ref = out / "reference/r15"
        ref.mkdir(parents=True)
        shutil.copytree(r15_package, ref / "package")
        shutil.copyfile(r15_workflow, ref / "r15-j1-lineups.yml")
        shutil.copyfile(r15_bundle, ref / "first-issues.tar.gz")
        write_json(out / "reference/r15/bundle-receipt.json", r15_prospective)
        shutil.copytree(forward, out / "forward/issued")
        protocol = source_tree / "research/20261125-r19-j1-positions/protocol.json"
        shutil.copyfile(protocol, out / "protocol.json")
        (out / "source-commit.txt").write_text(SOURCE_COMMIT + "\n", encoding="ascii")

        tables = out / "tables"
        tables.mkdir()
        make_tables(replay, r15_package, tables)
        fit = read_json(replay / "fit.json")
        metrics = read_json(replay / "metrics.json")
        r15_inputs = read_json(r15_package / "replay/inputs.json")
        provenance = {
            "schema": "WCPP-R19-J1-POSITION-EVIDENCE-1", "source_commit": SOURCE_COMMIT,
            "protocol_sha256": R19_PROTOCOL_SHA256,
            "numerical_environment": {"python": "3.12", **NUMERICAL_VERSIONS, **NUMERICAL_ENV},
            "comparison": {"same_host_refits": "byte-identical", "cross_platform_discrete": "exact",
                           "float_atol": 1e-9, "float_rtol": 1e-7},
            "r15": {"package_manifest_sha256": sha(r15_package / "manifest.json"),
                    "roster_sha256": r15_manifest["rosters_sha256"],
                    "roster_snapshot_manifest_sha256": r15_inputs["roster_manifest_sha256"],
                    "prospective_bundle_sha256": sha(r15_bundle),
                    "prospective_receipts_sha256": R15_RECEIPTS_SHA256,
                    "prospective_registration_sha256": r15_prospective["registration_sha256"],
                    "original_first_issue_count": 10},
            "r19_historical_final_inventory": hist_inventory,
            "r19_historical_repeat_inventory": repeat_inventory,
            "r19_forward": {"inventory": forward_inventory, "registration_id": registration["id"],
                            "registration_sha256": registration["sha256"], "recorded_at": registration["recorded_at"],
                            "fixture_count": len(receipts["matches"]), "recalculation": "prepare(retry=original), isolated temp only"},
            "windows": {w: {"matches": value["population"], "measured_total_lines": value["measured_lines"],
                            "xi_coverage": value["coverage"]} for w, value in metrics.items()},
            "doses": fit["doses"],
            "forward_verification": "verified by bundled verify.py using prepare(retry=original); no re-sign performed",
        }
        write_json(out / "evidence.json", provenance)
        write_json(out / "manifest.json", {"schema": provenance["schema"], "files": inventory(out)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("/workspace/scratch/r19-source"))
    parser.add_argument("--data-root", type=Path, default=Path("/workspace/scratch/r19-data"))
    parser.add_argument("--from-package", type=Path,
                        help="rebuild using the embedded R15, historical, and R19 forward inputs")
    parser.add_argument("--r15-package", type=Path)
    parser.add_argument("--r15-bundle", type=Path)
    parser.add_argument("--r15-workflow", type=Path)
    parser.add_argument("--historical", type=Path)
    parser.add_argument("--repeat", type=Path)
    parser.add_argument("--forward", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    build(parser.parse_args())


if __name__ == "__main__":
    main()
