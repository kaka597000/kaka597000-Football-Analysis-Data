#!/usr/bin/env python3
"""Verify historical refits, descriptive tables, and the signed R16 forward lock."""

import argparse
import hashlib
import json
import gzip
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parent
ARTIFACTS = ("inputs.json", "weights.json", "ranked-slates.jsonl.gz", "metrics.json")
SOURCE_FILES = (
    "runtime/research_program/first_score_ranking.py",
    "runtime/research_program/first_score_ranking_study.py",
    "runtime/research_program/first_score_ranking_forward.py",
    "runtime/research_program/test_first_score_ranking.py",
    "research/20261125-r16-selection/protocol.json",
    "configs/analysis-scope.json",
)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_bytes())


def check_source(source):
    source = Path(source).resolve()
    expected_commit = (ROOT / "source-commit.txt").read_text(encoding="utf-8").strip()
    if len(expected_commit) != 40 or any(c not in "0123456789abcdef" for c in expected_commit):
        raise ValueError("source-commit.txt must contain a full pinned source commit")
    actual_commit = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
    ).strip()
    if actual_commit != expected_commit:
        raise ValueError(f"source checkout {actual_commit} differs from pinned {expected_commit}")
    hashes = {}
    for name in SOURCE_FILES:
        path = source / name
        if not path.is_file():
            raise ValueError(f"pinned source file is missing: {name}")
        hashes[name] = sha256(path)
    if sha256(source / "research/20261125-r16-selection/protocol.json") != sha256(ROOT / "protocol.json"):
        raise ValueError("packaged protocol differs from pinned source protocol")
    return source, expected_commit, hashes


def check_r7(r7):
    r7 = Path(r7).resolve()
    manifest_path = r7 / "manifest.json"
    manifest_sha = sha256(manifest_path)
    expected = read_json(ROOT / "r7-manifest.sha256").get("sha256")
    if manifest_sha != expected:
        raise ValueError("original R7 package manifest SHA-256 differs")
    manifest = read_json(manifest_path)
    for relative, expected_hash in manifest["files"].items():
        path = (r7 / relative).resolve()
        if not path.is_relative_to(r7) or not path.is_file() or sha256(path) != expected_hash:
            raise ValueError(f"original R7 package file differs: {relative}")
    return r7, manifest_sha


def _source_modules(source):
    source = Path(source).resolve()
    runtime = str(source / "runtime")
    if runtime not in sys.path:
        sys.path.insert(0, runtime)
    from research_program import first_score_ranking_forward as forward
    from research_program import first_score_ranking_study as study
    from research_program.goal_state_study import sha
    from research.analysis_freeze import aware, verify as verify_freeze
    return forward, study, sha, aware, verify_freeze


def _run_study(source, r7, out):
    _, study, _, _, _ = _source_modules(source)
    destination = Path(out) / "study"
    study.run(Path(r7), destination, "2026-11-25")
    return destination


def _artifact_value(path, name):
    path = Path(path)
    if name == "ranked-slates.jsonl.gz":
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            return [json.loads(line) for line in stream if line.strip()]
    return read_json(path)


def _same_value(left, right, path="$", *, atol=1e-9, rtol=1e-7):
    if isinstance(left, dict) or isinstance(right, dict):
        if not isinstance(left, dict) or not isinstance(right, dict) or set(left) != set(right):
            return False, f"{path}: object keys differ"
        for key in left:
            same, reason = _same_value(left[key], right[key], f"{path}.{key}", atol=atol, rtol=rtol)
            if not same:
                return same, reason
        return True, None
    if isinstance(left, list) or isinstance(right, list):
        if not isinstance(left, list) or not isinstance(right, list) or len(left) != len(right):
            return False, f"{path}: list shape differs"
        for index, (a, b) in enumerate(zip(left, right, strict=True)):
            same, reason = _same_value(a, b, f"{path}[{index}]", atol=atol, rtol=rtol)
            if not same:
                return same, reason
        return True, None
    if type(left) is bool or type(right) is bool:
        return (type(left) is type(right) and left == right, f"{path}: boolean differs")
    if type(left) in (float, int) and type(right) in (float, int):
        if type(left) is int and type(right) is int:
            return left == right, f"{path}: integer differs"
        if not math.isfinite(float(left)) or not math.isfinite(float(right)):
            return left == right, f"{path}: non-finite number differs"
        same = math.isclose(float(left), float(right), rel_tol=rtol, abs_tol=atol)
        return same, f"{path}: numeric value exceeds tolerance"
    same = type(left) is type(right) and left == right
    return same, f"{path}: discrete value differs"


def compare_artifacts(left_root, right_root):
    for name in ARTIFACTS:
        left = _artifact_value(Path(left_root) / name, name)
        right = _artifact_value(Path(right_root) / name, name)
        same, reason = _same_value(left, right, name)
        if not same:
            raise ValueError(f"artifact mismatch: {reason}")


def check_forward(source, r7, replay, forward_root):
    forward, _, sha, aware, verify_freeze = _source_modules(source)
    forward_root = Path(forward_root).resolve()
    pointer = read_json(forward_root / "plan.json")
    lock_path = forward_root / pointer["file"]
    freeze = verify_freeze(read_json(lock_path))
    if (freeze.get("record_sha256") != pointer["sha256"]
            or freeze.get("freeze_id") != pointer["id"]
            or freeze.get("track") != "research-r16-first-score-seats-20261125"
            or freeze.get("stage") != "prematch"
            or freeze.get("evaluation_slot") != "FIRST_PREMATCH"):
        raise ValueError("forward item is not the registered first signed R16 allocation")

    with tempfile.TemporaryDirectory(prefix="r16-r7-issues-") as tmp:
        issued, inputs, weights = forward._load(Path(r7), Path(replay), Path(tmp))
        rebuilt = forward.payload(
            issued,
            inputs,
            weights,
            aware(freeze["fixture"]["cutoff_at"]),
            sha(Path(replay) / "weights.json"),
        )
    if rebuilt != freeze["payload"]:
        raise ValueError("forward seats, training cutoff, or original R7 issue references differ")
    included = freeze["payload"]["included"]
    fixture_count = sum(slate["size"] for slate in included)
    if (len(included), fixture_count, freeze["payload"]["source_population"]) != (39, 150, 192):
        raise ValueError("forward lock population differs from the registered 39 slates / 150 matches")
    return {
        "track": freeze["track"],
        "freeze_id": freeze["freeze_id"],
        "record_sha256": freeze["record_sha256"],
        "recorded_at": freeze["recorded_at"],
        "cutoff_at": freeze["fixture"]["cutoff_at"],
        "earliest_eligible_kickoff": min(slate["earliest"] for slate in included),
        "timezone": freeze["payload"]["timezone"],
        "training_before": freeze["payload"]["training_before"],
        "r7_manifest_sha256": freeze["payload"]["r7_manifest_sha256"],
        "source_registration_sha256": freeze["payload"]["source_registration"],
        "weights_sha256": freeze["payload"]["weights_sha256"],
        "registered_r7_fixtures": freeze["payload"]["source_population"],
        "eligible_slates": len(included),
        "eligible_fixtures": fixture_count,
        "excluded_started_slates": len(freeze["payload"]["excluded"]),
        "selection_recomputed_against_original_signed_r7_issues": True,
    }


def _compare_replay(source, r7, canonical):
    with tempfile.TemporaryDirectory(prefix="r16-rebuild-a-") as left, tempfile.TemporaryDirectory(
        prefix="r16-rebuild-b-"
    ) as right:
        left, right = _run_study(source, r7, left), _run_study(source, r7, right)
        hashes = {}
        compare_artifacts(left, right)
        compare_artifacts(left, canonical)
        for name in ARTIFACTS:
            hashes[name] = sha256(Path(canonical) / name)
    return hashes


def _check_tables(source):
    import importlib.util

    path = ROOT / "build_tables.py"
    spec = importlib.util.spec_from_file_location("r16_build_tables", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory(prefix="r16-tables-") as tmp:
        temp_root = Path(tmp)
        (temp_root / "replay").mkdir()
        for name in ("metrics.json", "weights.json"):
            (temp_root / "replay" / name).write_bytes((ROOT / "replay" / name).read_bytes())
        module.build(temp_root)
        for name in ("competition-seat.csv", "same-fixture-market-coverage.csv",
                     "fallback-by-competition.csv", "uncertainty.json"):
            if (temp_root / "replay" / name).read_bytes() != (ROOT / "replay" / name).read_bytes():
                raise ValueError(f"descriptive table does not rebuild exactly: {name}")


def _check_metrics():
    metrics = read_json(ROOT / "replay/metrics.json")["aggregate"]
    expected = (2686, 750, 416, 201, 215, 0, 0, 416)
    paired = metrics["paired"]
    observed = (
        metrics["fixtures"], metrics["batches"], metrics["full_batches"],
        metrics["rules"]["raw"]["first_hits"], metrics["rules"]["calibrated"]["first_hits"],
        metrics["rules"]["raw"]["complete_sweeps"], metrics["rules"]["calibrated"]["complete_sweeps"],
        paired["tied"],
    )
    if observed != expected or paired["gained"] != 0 or paired["lost"] != 0:
        raise ValueError(f"R16 aggregate counts differ from registered targets: {observed}")
    if metrics["descriptive_paired_seat_first"]["eligible"] != 1720:
        raise ValueError("descriptive filled-seat denominator differs")


def verify_package(source, r7, forward_root):
    source, commit, source_hashes = check_source(source)
    r7, manifest_sha = check_r7(r7)
    package_manifest = read_json(ROOT / "manifest.json")
    for relative, expected in package_manifest["files"].items():
        if sha256(ROOT / relative) != expected:
            raise ValueError(f"R16 package file checksum differs: {relative}")
    provenance = read_json(ROOT / "evidence/source-provenance.json")
    if (provenance["source_commit"] != commit or provenance["source_files"] != source_hashes
            or provenance["r7_manifest_sha256"] != manifest_sha):
        raise ValueError("source or R7 provenance differs from package evidence")
    replay_hashes = _compare_replay(source, r7, ROOT / "replay")
    retry = read_json(ROOT / "evidence/retry-rebuild.json")
    evidence_artifacts = retry["artifacts"]
    if (retry["package_artifact_sha256"] != replay_hashes or retry["source_commit"] != commit
            or evidence_artifacts["historic_verified"] != replay_hashes
            or evidence_artifacts["historic_repeat"] != replay_hashes
            or any(set(evidence_artifacts[name]) != set(ARTIFACTS) for name in ("refit_1", "refit_2"))
            or any(len(value) != 64 for name in ("refit_1", "refit_2")
                   for value in evidence_artifacts[name].values())):
        raise ValueError("recorded repeat-rebuild evidence differs")
    _check_tables(source)
    _check_metrics()
    forward_report = check_forward(source, r7, ROOT / "replay", forward_root)
    if forward_report != read_json(ROOT / "evidence/forward-verification.json"):
        raise ValueError("recorded forward verification differs from the signed lock")
    return {
        "source_commit": commit,
        "r7_manifest_sha256": manifest_sha,
        "historical_artifacts_rebuilt_and_reconciled": len(replay_hashes),
        "forward_slates": forward_report["eligible_slates"],
        "forward_fixtures": forward_report["eligible_fixtures"],
        "status": "PASS",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="checkout at source-commit.txt")
    parser.add_argument("--r7", type=Path, required=True, help="complete original R7 package")
    parser.add_argument("--forward", type=Path, required=True, help="folder containing plan.json and signed lock")
    args = parser.parse_args()
    print(json.dumps(verify_package(args.source, args.r7, args.forward), indent=2))


if __name__ == "__main__":
    main()
