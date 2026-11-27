#!/usr/bin/env python3
"""Build the portable R16 package from the pinned source and original inputs."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

import verify


ROOT = Path(__file__).resolve().parent
R7_MANIFEST_SHA = "e2ed191e29150ba59bf9623ce2a44b265e8b71c9e777d9197ec869975a957df3"


def _write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build(source, r7, final_verified, final_repeat, forward_root):
    source, commit, source_hashes = verify.check_source(source)
    r7, manifest_sha = verify.check_r7(r7)
    if manifest_sha != R7_MANIFEST_SHA:
        raise ValueError("unexpected original R7 archive manifest")
    final_verified, final_repeat = Path(final_verified), Path(final_repeat)
    forward_root = Path(forward_root).resolve()

    with tempfile.TemporaryDirectory(prefix="r16-build-a-") as first, tempfile.TemporaryDirectory(
        prefix="r16-build-b-"
    ) as second:
        first = verify._run_study(source, r7, first)
        second = verify._run_study(source, r7, second)
        if any(
            (final_verified / name).read_bytes() != (final_repeat / name).read_bytes()
            for name in verify.ARTIFACTS
        ):
            raise ValueError("retained historic repeat artifacts are not byte-identical")
        verify.compare_artifacts(first, second)
        verify.compare_artifacts(first, final_verified)
        verify.compare_artifacts(first, final_repeat)
        artifact_hashes = {}
        refit_hashes = {"refit_1": {}, "refit_2": {}, "historic_verified": {}, "historic_repeat": {}}
        for name in verify.ARTIFACTS:
            verified_bytes = (final_verified / name).read_bytes()
            refit_hashes["refit_1"][name] = hashlib.sha256((first / name).read_bytes()).hexdigest()
            refit_hashes["refit_2"][name] = hashlib.sha256((second / name).read_bytes()).hexdigest()
            refit_hashes["historic_verified"][name] = hashlib.sha256(verified_bytes).hexdigest()
            refit_hashes["historic_repeat"][name] = hashlib.sha256((final_repeat / name).read_bytes()).hexdigest()
            target = ROOT / "replay" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(verified_bytes)
            artifact_hashes[name] = hashlib.sha256(verified_bytes).hexdigest()

    pointer = verify.read_json(forward_root / "plan.json")
    lock = forward_root / pointer["file"]
    freeze = verify.read_json(lock)
    _, _, _, _, verify_freeze = verify._source_modules(source)
    if verify_freeze(freeze).get("record_sha256") != pointer["sha256"]:
        raise ValueError("forward freeze digest does not match its plan pointer")
    (ROOT / "forward").mkdir(exist_ok=True)
    shutil.copyfile(forward_root / "plan.json", ROOT / "forward/plan.json")
    shutil.copyfile(lock, ROOT / "forward" / pointer["file"])

    forward_report = verify.check_forward(source, r7, ROOT / "replay", ROOT / "forward")
    _write_json(ROOT / "evidence/source-provenance.json", {
        "source_commit": commit,
        "source_files": source_hashes,
        "r7_manifest_sha256": manifest_sha,
        "r7_package": "workspace-updates/20261123-prematch-literature",
        "historical_training_before": "2026-11-25",
    })
    _write_json(ROOT / "evidence/retry-rebuild.json", {
        "source_commit": commit,
        "r7_manifest_sha256": manifest_sha,
        "inputs": ["r16-final-verified", "r16-final-repeat"],
        "independent_refits": 2,
        "all_four_artifacts_byte_identical": True,
        "rebuild_comparison": "discrete fields exact; floating-point values atol=1e-9, rtol=1e-7",
        "artifacts": refit_hashes,
        "package_artifact_sha256": artifact_hashes,
    })
    _write_json(ROOT / "evidence/forward-verification.json", forward_report)

    import build_tables
    build_tables.build(ROOT)
    files = {}
    for path in sorted(ROOT.rglob("*")):
        if (path.is_file() and path.name != "manifest.json" and ".git" not in path.parts
                and "__pycache__" not in path.parts and path.suffix != ".pyc"):
            files[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    _write_json(ROOT / "manifest.json", {
        "schema": "WCPP-R16-SELECTION-PACKAGE-1",
        "version": "R16-R7-first-score-seat-order-1",
        "source_commit": commit,
        "r7_manifest_sha256": manifest_sha,
        "files": files,
    })
    print(json.dumps({"files": len(files), "artifacts": artifact_hashes,
                      "forward": forward_report}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--r7", type=Path, required=True)
    parser.add_argument("--final-verified", type=Path, required=True)
    parser.add_argument("--final-repeat", type=Path, required=True)
    parser.add_argument("--forward", type=Path, required=True)
    args = parser.parse_args()
    build(args.source, args.r7, args.final_verified, args.final_repeat, args.forward)


if __name__ == "__main__":
    main()
