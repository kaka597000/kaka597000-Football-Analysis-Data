#!/usr/bin/env python3
"""Verify pinned R17 source/data, two historical refits, and the signed forward lock."""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import shutil

os.environ["NPY_DISABLE_CPU_FEATURES"] = "AVX512F"
os.environ["OPENBLAS_CORETYPE"] = "Haswell"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"


ROOT = Path(__file__).resolve().parent
SOURCE_FILES = (
    "runtime/research_program/schedule_density.py",
    "runtime/research_program/schedule_density_study.py",
    "runtime/research_program/schedule_density_forward.py",
    "runtime/research_program/schedule_density_results.py",
    "runtime/research_program/test_schedule_density.py",
    "runtime/research_program/continuation_scores.py",
    "runtime/research_program/continuation_study.py",
    "runtime/research_program/continuation_forward.py",
    "runtime/research_program/r8_score_study.py",
    "runtime/research_program/r9_score_study.py",
    "runtime/research_program/r10_shot_model.py",
    "runtime/research_program/all_scope_model.py",
    "runtime/research_program/all_scope_study.py",
    "research/20261125-r17-schedule/protocol.json",
    "configs/analysis-scope.json",
)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def check_source(source, expected_commit):
    source = Path(source).resolve()
    if len(expected_commit) != 40 or any(c not in "0123456789abcdef" for c in expected_commit):
        raise ValueError("--source-commit must be a full lowercase Git SHA")
    actual = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if actual != expected_commit:
        raise ValueError(f"source HEAD {actual} differs from requested pin {expected_commit}")
    hashes = {}
    for relative in SOURCE_FILES:
        path = source / relative
        if not path.is_file():
            raise ValueError(f"pinned source file missing: {relative}")
        hashes[relative] = sha256(path)
    if sha256(source / "research/20261125-r17-schedule/protocol.json") != sha256(ROOT / "protocol.json"):
        raise ValueError("packaged protocol differs from pinned source protocol")
    return source, actual, hashes


def check_data_package(folder, label):
    folder = Path(folder).resolve()
    manifest_path = folder / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"{label} package manifest missing: {manifest_path}")
    manifest_sha = sha256(manifest_path)
    manifest = read_json(manifest_path)
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError(f"{label} manifest has no file checksums")
    for relative, expected in files.items():
        path = (folder / relative).resolve()
        if not path.is_relative_to(folder) or not path.is_file() or sha256(path) != expected:
            raise ValueError(f"{label} data file mismatch: {relative}")
    return folder, manifest_sha


def audit_korean_receipts(source, r5):
    """Reverify each archived FotMob season receipt once per unique source hash."""
    runtime = str(Path(source).resolve() / "runtime")
    if runtime not in sys.path:
        sys.path.insert(0, runtime)
    from research_program.all_scope_study import check_panel
    from research_program.r8_score_study import read
    from research_program.r9_score_study import verified_archive
    from research_program.schedule_density_results import verify as verify_receipts

    r5 = Path(r5).resolve()
    manifest = read(r5 / "manifest.json")
    with tempfile.TemporaryDirectory(prefix="r17-kor-receipts-") as tmp:
        panel_dir = Path(tmp) / "kor"
        panel_dir.mkdir()
        verified_archive(r5, manifest, "models/kor.1.tar.gz", panel_dir)
        games = check_panel(panel_dir / "panel.jsonl", "kor.1")
        withheld = verify_receipts(games, r5, manifest)
    if len(games) != 1974 or len(withheld) != 1 or withheld.get("fotmob:3524653") != "awarded":
        raise ValueError("K1 original FotMob receipt coverage or awarded exclusion differs")
    excluded = next(g for g in games if g["id"] == "fotmob:3524653")
    if excluded["date"] != "2021-09-18":
        raise ValueError("K1 awarded FotMob fixture date differs")
    hashes = sorted({game["source_sha256"] for game in games})
    if len(hashes) != 9:
        raise ValueError("K1 expected nine unique archived season-source hashes")
    return {
        "competition": "kor.1", "fotmob_rows": len(games),
        "verified_regulation_full_time_rows": len(games) - len(withheld),
        "excluded": [{"match_id": excluded["id"], "source_date": excluded["date"],
                      "reason": withheld[excluded["id"]]}],
        "unique_archived_source_sha256": hashes,
        "unique_archive_hash_count": len(hashes),
        "source_hash_listing_policy": "one entry per distinct archive hash",
    }


def check_historical_coverage(source, replay):
    source = Path(source).resolve()
    replay = Path(replay).resolve()
    scope = read_json(source / "configs/analysis-scope.json")
    codes = [entry["code"] for entry in scope["competitions"]]
    metrics = read_json(replay / "metrics.json")
    if len(codes) != 20 or set(metrics) != {"evaluation", "recent", "independent2019"}:
        raise ValueError("R17 registered historical windows or 20-competition scope differs")
    for window in metrics.values():
        if set(window["competitions"]) != set(codes):
            raise ValueError("R17 window dropped a registered competition, including empty scopes")
    main = replay / "main"
    old = replay / "independent2019"
    if {p.name for p in main.iterdir() if p.is_dir()} != set(codes):
        raise ValueError("main replay does not contain all 20 original competitions")
    old_codes = {"eng.1", "esp.1", "fra.1", "ger.1", "ita.1", "ned.1"}
    if {p.name for p in old.iterdir() if p.is_dir()} != old_codes:
        raise ValueError("independent historic replay is not the six registered old seasons")

    afc = read_json(main / "afc.champions" / "fit.json")
    expected_width = 6
    if (afc["train_games"] != 0
            or afc["fitted"]["scoring_beta"] != [0.] * expected_width
            or afc["fitted"]["additional_beta"] != [0.] * expected_width
            or afc["doses"] != {"score": 0.0, "wdl": 0.0, "total": 0.0}):
        raise ValueError("AFC first-fold empty-data ridge solution is not the unique all-zero fit")
    import gzip
    rows = []
    with gzip.open(main / "afc.champions" / "forecasts.jsonl.gz", "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream if line.strip()]
    if not rows or any(row["forecast"]["candidate"] != row["forecast"]["r7"] for row in rows):
        raise ValueError("AFC empty-fold solution did not retain the complete R7 test outputs")
    return {"scope_competitions": len(codes), "main_windows": ["evaluation", "recent"],
            "independent_old_seasons": sorted(old_codes),
            "afc_champions": {"training_rows_first_fold": 0, "ridge_solution": "unique all-zero",
                              "selected_doses": afc["doses"], "test_rows_preserved": len(rows),
                              "all_test_predictions_equal_original_R7": True}}


def same_value(left, right, path="$", *, atol=1e-9, rtol=1e-7):
    if isinstance(left, dict) or isinstance(right, dict):
        if not isinstance(left, dict) or not isinstance(right, dict) or set(left) != set(right):
            return False, f"{path}: object keys differ"
        for key in left:
            ok, reason = same_value(left[key], right[key], f"{path}.{key}", atol=atol, rtol=rtol)
            if not ok:
                return ok, reason
        return True, None
    if isinstance(left, list) or isinstance(right, list):
        if not isinstance(left, list) or not isinstance(right, list) or len(left) != len(right):
            return False, f"{path}: list shape differs"
        for i, (a, b) in enumerate(zip(left, right)):
            ok, reason = same_value(a, b, f"{path}[{i}]", atol=atol, rtol=rtol)
            if not ok:
                return ok, reason
        return True, None
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right, f"{path}: boolean differs"
    if isinstance(left, (int, float)) or isinstance(right, (int, float)):
        if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
            return False, f"{path}: numeric type differs"
        if isinstance(left, int) and isinstance(right, int):
            return left == right, f"{path}: integer differs"
        if not math.isfinite(float(left)) or not math.isfinite(float(right)):
            return left == right, f"{path}: non-finite numeric value differs"
        ok = math.isclose(float(left), float(right), rel_tol=rtol, abs_tol=atol)
        return ok, f"{path}: float exceeds tolerance ({left!r} vs {right!r})"
    return type(left) is type(right) and left == right, f"{path}: discrete value differs"


def check_forward(source, r5, r7, forward_root, replay):
    source = Path(source).resolve()
    runtime = str(source / "runtime")
    if runtime not in sys.path:
        sys.path.insert(0, runtime)
    from research_program import schedule_density_forward as forward
    from research.analysis_freeze import aware, verify as verify_freeze

    forward_root = Path(forward_root).resolve()
    pointer = read_json(forward_root / "plan.json")
    lock_path = forward_root / pointer["file"]
    record = verify_freeze(read_json(lock_path))
    if (record.get("record_sha256") != pointer.get("sha256")
            or record.get("freeze_id") != pointer.get("id")
            or record.get("track") != forward.TRACK
            or record.get("stage") != "prematch"
            or record.get("evaluation_slot") != "FIRST_PREMATCH"):
        raise ValueError("forward pointer is not the registered first signed R17 allocation")

    with tempfile.TemporaryDirectory(prefix="r17-forward-rebuild-") as tmp:
        fifth, old, recipes, metadata = forward.inputs(Path(r5), Path(r7), Path(replay), Path(tmp))
        cutoff = aware(record["fixture"]["cutoff_at"])
        rebuilt = forward.payload(fifth, old, recipes, metadata, cutoff)
    ok, reason = same_value(rebuilt, record["payload"], "forward.payload")
    if not ok:
        raise ValueError("forward re-selection differs from signed original R5/R7 issues: " + reason)
    included = record["payload"]["included"]
    excluded = record["payload"]["excluded"]
    selected = record["payload"]["matches"]
    count = sum(len(slate["ids"]) for slate in included)
    if not included or not selected or count != len(selected):
        raise ValueError("forward lock has empty or inconsistent eligible slate coverage")
    earliest = min(aware(slate["first_kickoff"]) for slate in included)
    if aware(record["recorded_at"]) >= earliest:
        raise ValueError("forward lock was recorded after an eligible kickoff")
    seats = sum(min(3, len(slate["ids"])) for slate in included)
    market_lines = sum(match.get("line") is not None for match in selected.values())
    if (len(included), count, len(selected), record["payload"]["original_population"], seats,
            market_lines, len(excluded)) != (39, 150, 150, 192, 85, 114, 12):
        raise ValueError("signed R17 forward slates/seats/market coverage differ from registered counts")
    return {
        "track": record["track"], "freeze_id": record["freeze_id"],
        "record_sha256": record["record_sha256"], "recorded_at": record["recorded_at"],
        "cutoff_at": record["fixture"]["cutoff_at"], "earliest_eligible_kickoff": earliest.isoformat(),
        "original_registered_fixtures": record["payload"]["original_population"],
        "eligible_slates": len(included), "eligible_fixtures": count,
        "eligible_seats_per_rule": seats, "fixtures_with_original_real_market_line": market_lines,
        "excluded_started_slates": len(excluded), "source_matches_verified": len(selected),
        "selection_recomputed_from_signed_R5_R7_issues": True,
    }


def verify_package(args):
    source, commit, source_hashes = check_source(args.source, args.source_commit)
    data = {name: check_data_package(getattr(args, name), name) for name in ("r5", "r7", "r10")}
    manifest = read_json(ROOT / "manifest.json")
    for relative, expected in manifest["files"].items():
        path = (ROOT / relative).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file() or sha256(path) != expected:
            raise ValueError(f"R17 package checksum differs: {relative}")
    evidence = read_json(ROOT / "evidence.json")
    if (evidence["source_commit"] != commit or evidence["source_files"] != source_hashes
            or evidence["data_manifests"] != {name: value[1] for name, value in data.items()}):
        raise ValueError("source or original input manifest provenance differs")
    if evidence["korean_receipt_audit"] != audit_korean_receipts(source, args.r5):
        raise ValueError("K1 original FotMob receipt audit differs")
    # The package builder replaces replay/ while assembling a new package.
    # Verify an immutable private snapshot so a concurrent build cannot make
    # rglob observe a mixture of the old and new capture inventories.
    with tempfile.TemporaryDirectory(prefix="r17-capture-snapshot-") as snapshot_tmp:
        captured = Path(snapshot_tmp) / "replay"
        captured_tables = Path(snapshot_tmp) / "tables"
        try:
            shutil.copytree(ROOT / "replay", captured)
            shutil.copytree(ROOT / "tables", captured_tables)
        except OSError as exc:
            raise ValueError("captured replay changed while verification snapshot was copied") from exc
        final_hashes = evidence["replay_artifact_sha256"]
        captured_hashes = {name: sha256(captured / name) for name in build_replay_files(captured)}
        if captured_hashes != final_hashes:
            raise ValueError("captured replay changed during verification; rerun after package build completes")
        table_hashes = {name: sha256(captured_tables / name)
                        for name in build_replay_files(captured_tables)}
        if table_hashes != evidence["table_sha256"]:
            raise ValueError("captured tables changed during verification; rerun after package build completes")
        if evidence["historical_coverage"] != check_historical_coverage(source, captured):
            raise ValueError("R17 registered historical coverage or AFC zero-fit audit differs")

        return _verify_refits_and_outputs(args, source, commit, data, evidence, captured,
                                          captured_tables)


def build_replay_files(root):
    return sorted(path.relative_to(root).as_posix() for path in Path(root).rglob("*") if path.is_file())


def _verify_refits_and_outputs(args, source, commit, data, evidence, captured, captured_tables):
    import build

    # Package checksums are checked before the snapshot; use the immutable copy
    # for every operation that compares or audits the captured replay.
    final_hashes = evidence["replay_artifact_sha256"]
    current_environment = {
        "python": f"{sys.version_info.major}.{sys.version_info.minor}", "numpy": build.np.__version__,
        "scipy": build.scipy.__version__, "lightgbm": build.lightgbm.__version__,
        "NPY_DISABLE_CPU_FEATURES": os.environ["NPY_DISABLE_CPU_FEATURES"],
        "OPENBLAS_CORETYPE": os.environ["OPENBLAS_CORETYPE"],
        "OPENBLAS_NUM_THREADS": os.environ["OPENBLAS_NUM_THREADS"],
        "OMP_NUM_THREADS": os.environ["OMP_NUM_THREADS"],
    }
    if current_environment != evidence["numerical_environment"]:
        raise ValueError("numerical libraries or deterministic host settings differ")
    if final_hashes != {name: sha256(captured / name) for name in build.replay_files(captured)}:
        raise ValueError("stored replay artifacts differ from their evidence checksums")
    for name in ("refit_1", "refit_2", "final", "repeat"):
        if set(evidence["refit_artifact_sha256"][name]) != set(final_hashes):
            raise ValueError(f"{name} artifact inventory differs")
    if evidence["refit_artifact_sha256"]["refit_1"] != evidence["refit_artifact_sha256"]["refit_2"]:
        raise ValueError("recorded same-machine independent refits were not byte-identical")
    if evidence["refit_artifact_sha256"]["final"] != evidence["refit_artifact_sha256"]["repeat"]:
        raise ValueError("retained final and repeat artifacts are not byte-identical")

    with tempfile.TemporaryDirectory(prefix="r17-verify-a-") as a, tempfile.TemporaryDirectory(
        prefix="r17-verify-b-"
    ) as b:
        first = build.run_study(source, args.r5, args.r7, args.r10, args.scope, Path(a) / "replay")
        second = build.run_study(source, args.r5, args.r7, args.r10, args.scope, Path(b) / "replay")
        for folder in (first, second):
            build.compare_tree(folder, captured)
        first_hashes = {name: sha256(first / name) for name in build.replay_files(first)}
        second_hashes = {name: sha256(second / name) for name in build.replay_files(second)}
        if first_hashes != second_hashes:
            raise ValueError("two same-machine independent refits are not byte-identical")

    with tempfile.TemporaryDirectory(prefix="r17-tables-") as tmp:
        previous_root = build.ROOT
        build.ROOT = Path(tmp)
        try:
            build.build_tables(captured)
            table_root = Path(tmp) / "tables"
            rebuilt = {name: sha256(table_root / name) for name in build.replay_files(table_root)}
            if rebuilt != evidence["table_sha256"]:
                raise ValueError("per-competition tables do not rebuild byte for byte")
        finally:
            build.ROOT = previous_root
    with tempfile.TemporaryDirectory(prefix="r17-archive-") as tmp:
        archive_path = Path(tmp) / "r17-replay.tar.gz"
        build.package_archive(captured, captured_tables, archive_path)
        if sha256(archive_path) != sha256(ROOT / "r17-replay.tar.gz"):
            raise ValueError("deterministic replay archive does not rebuild byte for byte")

    forward_report = check_forward(source, args.r5, args.r7, args.forward, captured)
    if forward_report != evidence["forward"]:
        raise ValueError("forward verification evidence differs from original signed lock")
    return {"source_commit": commit, "input_manifest_sha256": {n: v[1] for n, v in data.items()},
            "historical_artifact_count": len(final_hashes), "forward": forward_report, "status": "PASS"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "r5", "r7", "r10", "forward"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--scope", type=Path)
    args = parser.parse_args()
    if args.scope is None:
        args.scope = args.source / "configs/analysis-scope.json"
    print(json.dumps(verify_package(args), indent=2))


if __name__ == "__main__":
    main()
