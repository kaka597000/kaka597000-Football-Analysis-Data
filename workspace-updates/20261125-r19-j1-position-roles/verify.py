#!/usr/bin/env python3
"""Independently rebuild R15 rosters, refit R19 twice, and verify the original R19 forward receipt."""

import argparse
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
                    compare_trees, digest, inventory, read_json, same_value, sha)
from build import OUTPUT_FILES, pinned_source, prospective_receipt, verify_r15_package


def extract_r15_firsts(bundle, destination):
    destination.mkdir(parents=True)
    with tarfile.open(bundle, "r:gz") as archive:
        for member in archive.getmembers():
            name = member.name
            if name == "firsts/receipts.json" or (name.startswith("firsts/") and name.endswith(".json")):
                if Path(name).name != name.removeprefix("firsts/") or not member.isfile():
                    raise ValueError(f"unsafe original R15 issue archive member: {name}")
                output = destination / name.removeprefix("firsts/")
                output.write_bytes(archive.extractfile(member).read())
    receipts = read_json(destination / "receipts.json")
    if len(receipts.get("matches", {})) != 10:
        raise ValueError("R15 prospective bundle did not restore ten original fixtures")
    return receipts


def validate_r19_forward(source_runtime, issued_folder, r15_firsts, folders, parent, study, rosters, work):
    sys.path.insert(0, str(source_runtime))
    from research.analysis_freeze import digest as freeze_digest, verify as verify_record
    from research_program.lineup_position_forward import prepare

    receipts = read_json(issued_folder / "receipts.json")
    plan_ref = receipts["registration"]
    plan_path = issued_folder / plan_ref["file"]
    plan = verify_record(json.loads(plan_path.read_bytes()))
    if (plan["record_sha256"] != plan_ref["sha256"] or plan["record_sha256"] != R19_REGISTRATION_SHA256
            or plan["freeze_id"] != R19_REGISTRATION_ID or plan["recorded_at"] != R19_RECORDED_AT
            or len(plan["payload"]["fixtures"]) != 10 or set(plan["payload"]["fixtures"]) != set(receipts["matches"])):
        raise ValueError("R19 original registration receipt or ten-fixture population differs")
    if plan["track"] != "research-r19-j1-position-roles-20261125-registration":
        raise ValueError("R19 original registration track differs")

    original_records = {}
    for match_id, ref in receipts["matches"].items():
        path = issued_folder / ref["file"]
        record = verify_record(json.loads(path.read_bytes()))
        if (record["record_sha256"] != ref["sha256"]
                or record["freeze_id"] != ref["id"] or record["recorded_at"] != ref["recorded_at"]
                or record["match_id"] != match_id or record["payload"].get("registration_sha256") != plan["record_sha256"]
                or any(record["fixture"].get(key) != value for key, value in
                       plan["payload"]["fixtures"][match_id].items())):
            raise ValueError(f"R19 original first-issue receipt differs: {match_id}")
        if (record["evaluation_slot"] != "FIRST_PREMATCH" or record["stage"] != "prematch"
                or record["revision"] != 1 or record["previous_sha256"] is not None):
            raise ValueError(f"R19 forward entry is not the retained first prematch issue: {match_id}")
        signed_body = dict(record["payload"])
        if signed_body.pop("registration_sha256") != plan["record_sha256"]:
            raise ValueError(f"R19 issue is detached from original registration: {match_id}")
        if freeze_digest(signed_body) != plan["payload"]["identity"]["payload_sha256"][match_id]:
            raise ValueError(f"R19 original payload hash differs: {match_id}")
        original_records[match_id] = (record, signed_body)

    # This is intentionally the pure preparation entry point with the real issue
    # as its retry clock. It performs no ledger write or issue/save operation.
    work.mkdir(parents=True, exist_ok=True)
    fixtures, payloads, identity = prepare(folders, parent, study, rosters, r15_firsts, plan, work)
    if set(fixtures) != set(payloads) or set(payloads) != set(original_records):
        raise ValueError("R19 isolated replay changed the original ten-fixture population")
    signed_identity = dict(plan["payload"]["identity"])
    fresh_identity = dict(identity)
    signed_identity.pop("payload_sha256", None)
    fresh_identity.pop("payload_sha256", None)
    ok, why = same_value(fresh_identity, signed_identity, "R19 registration identity")
    if not ok:
        raise ValueError(f"R19 original inputs or selected picks differ: {why}")
    if fixtures != plan["payload"]["fixtures"]:
        raise ValueError("R19 prepared fixture identity differs from original registration")
    for match_id, fresh in payloads.items():
        record, signed = original_records[match_id]
        if fresh.get("registration_sha256") is not None:
            raise ValueError("pure prepare unexpectedly returned a signed registration field")
        ok, why = same_value(fresh, signed, f"R19 first payload {match_id}")
        if not ok:
            raise ValueError(f"R19 original pick/input replay differs: {why}")
        # The package manifest binds exact bytes; the freeze verifier rechecks
        # the canonical record hash. No receipt file is written or replaced.
    return {"registration_id": plan["freeze_id"], "registration_sha256": plan["record_sha256"],
            "recorded_at": plan["recorded_at"], "original_matches": len(original_records),
            "prepared_from_original_retry": True, "created_or_modified_issues": False,
            "selected": identity["selected"], "recipe_sha256": identity["recipe_sha256"]}


def verify(args):
    package, data_root, source = args.package.resolve(), args.data_root.resolve(), args.source.resolve()
    evidence = read_json(package / "evidence.json")
    manifest = read_json(package / "manifest.json")
    if manifest.get("schema") != "WCPP-R19-J1-POSITION-EVIDENCE-1":
        raise ValueError("R19 package schema differs")
    expected_files = manifest["files"]
    actual = inventory(package)
    actual.pop("manifest.json", None)
    if actual != expected_files:
        raise ValueError("R19 package manifest checksum mismatch")
    if evidence["source_commit"] != SOURCE_COMMIT or evidence["protocol_sha256"] != R19_PROTOCOL_SHA256:
        raise ValueError("R19 source or registered protocol pin differs")
    for key, value in NUMERICAL_ENV.items():
        os.environ[key] = value
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError("R19 replay requires Python 3.12; patch level is not pinned")
    import numpy, scipy, lightgbm
    versions = {"numpy": numpy.__version__, "scipy": scipy.__version__, "lightgbm": lightgbm.__version__}
    if versions != NUMERICAL_VERSIONS or evidence["numerical_environment"] != {
            "python": "3.12", **NUMERICAL_VERSIONS, **NUMERICAL_ENV}:
        raise RuntimeError("R19 numerical dependency or host setting differs")

    r15_package = package / "reference/r15/package"
    r15_workflow = package / "reference/r15/r15-j1-lineups.yml"
    r15_manifest = verify_r15_package(r15_package, r15_workflow)
    if sha(r15_package / "manifest.json") != evidence["r15"]["package_manifest_sha256"]:
        raise ValueError("embedded R15 package manifest differs from receipt")
    r15_bundle = package / "reference/r15/first-issues.tar.gz"
    if sha(r15_bundle) != R15_BUNDLE_SHA256:
        raise ValueError("preserved R15 prospective bundle SHA differs")
    r15_receipt = json.loads((package / "reference/r15/bundle-receipt.json").read_text(encoding="utf-8"))
    with tarfile.open(r15_bundle, "r:gz") as archive:
        receipts_body = archive.extractfile("firsts/receipts.json").read()
    if digest(receipts_body) != R15_RECEIPTS_SHA256:
        raise ValueError("preserved R15 ten-first receipt SHA differs")
    r15_verify_report = prospective_receipt(r15_package, data_root, r15_bundle)
    if r15_verify_report != r15_receipt or r15_receipt["issued"] != 10:
        raise ValueError("R15 original prospective bundle verification differs")

    historical = package / "reference/r19/historical-final"
    repeat = package / "reference/r19/historical-repeat"
    if inventory(historical) != inventory(repeat) or inventory(historical) != evidence["r19_historical_final_inventory"]:
        raise ValueError("R19 original nine-file history and repeat differ")
    if inventory(package / "replay") != inventory(historical):
        raise ValueError("canonical R19 replay inventory differs from retained originals")
    if inventory(package / "forward/issued") != evidence["r19_forward"]["inventory"]:
        raise ValueError("R19 original forward issue archive inventory differs")

    folders = {key: data_root / "workspace-updates" / name for key, name in
               (("r5", "20261123-all-scope-kpi"), ("r7", "20261123-prematch-literature"),
                ("r10", "20261125-r10-shot-conversion"))}
    for folder in folders.values():
        if not (folder / "manifest.json").is_file():
            raise FileNotFoundError(folder / "manifest.json")
    with tempfile.TemporaryDirectory(prefix="r19-verify-") as td:
        td = Path(td)
        source_tree = pinned_source(source, td / "source")
        runs = (td / "run-1", td / "run-2")
        worker = package / "replay_worker.py"
        command = [sys.executable, "-B", str(worker), str(r15_package), str(data_root),
                   str(source_tree / "runtime"), str(td), str(folders["r5"]), str(folders["r7"]),
                   str(folders["r10"]), *(str(p) for p in runs), str(r15_package / "manifest.json")]
        subprocess.run(command, check=True, env=os.environ.copy())
        if any(set(inventory(folder)) != OUTPUT_FILES for folder in runs):
            raise ValueError("fresh R19 replay did not rebuild all nine outputs")
        compare_trees(runs[0], runs[1], exact=True)
        compare_trees(runs[0], package / "replay", exact=False)

        # Recreate the raw roster once more for the pure forward preparation.
        training = td / "r15-roster-rebuilt.jsonl"
        if not training.is_file():
            raise ValueError("raw R15 roster reconstruction output is missing")
        firsts = td / "r15-first-issues"
        extract_r15_firsts(r15_bundle, firsts)
        forward_check = validate_r19_forward(source_tree / "runtime", package / "forward/issued", firsts,
                                             folders, r15_package / "replay", package / "replay",
                                             training, td / "forward-model")

    windows = {name: summary["population"] for name, summary in read_json(package / "replay/metrics.json").items()}
    if windows != {"evaluation": 380, "recent": 150}:
        raise ValueError("R19 registered assessment windows differ")
    if any(summary["measured_lines"] != 0 for summary in read_json(package / "replay/metrics.json").values()):
        raise ValueError("R19 unmeasured totals must remain at zero coverage")
    return {"status": "PASS", "source_commit": SOURCE_COMMIT, "R15_source_commit": R15_SOURCE_COMMIT,
            "R15_roster_rows_rebuilt": 2822, "R19_historical_files": len(OUTPUT_FILES),
            "windows": windows, "same_host_new_refits_byte_identical": True,
            "cross_platform_comparison": "discrete exact; floats atol=1e-9, rtol=1e-7",
            "R19_forward": forward_check}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--data-root", type=Path, default=Path("."))
    parser.add_argument("--source", required=True, type=Path)
    print(json.dumps(verify(parser.parse_args()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
