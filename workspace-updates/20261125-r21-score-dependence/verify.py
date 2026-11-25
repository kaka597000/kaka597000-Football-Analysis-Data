#!/usr/bin/env python3
"""Rebuild and verify the R21 evidence bundle without creating issued records."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import importlib
import importlib.metadata
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile


HERE = Path(__file__).resolve().parent
SOURCE_COMMIT = "828f7a68daff347dfef4e69185e7761965954582"
EVENTS_SHA = "63f853739198298cbbde9dfce2cb02c582cb9dccb4070215c51453325f553bd5"
PROTOCOL_SHA = "a4eb968e0965882c0844235fb0e9448a25a172f4a4ea8f16ec6d5e490439ed52"
ARCHIVES = {
    "r5": "workspace-updates/20261123-all-scope-kpi",
    "r7": "workspace-updates/20261123-prematch-literature",
    "r10": "workspace-updates/20261125-r10-shot-conversion",
}
COMPETITIONS = ("eng.1", "esp.1", "ger.1", "ita.1", "fra.1")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha(path: Path) -> str:
    return sha(path.read_bytes())


def check(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def inventory(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): file_sha(p) for p in sorted(root.rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts and p.name != "manifest.json"}


def safe_unpack(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:*") as bundle:
        for member in bundle.getmembers():
            name = PurePosixPath(member.name)
            check(not name.is_absolute() and ".." not in name.parts
                  and (member.isfile() or member.isdir()), f"unsafe archive member: {member.name}")
            target = (destination / Path(*name.parts)).resolve()
            check(target.is_relative_to(destination.resolve()), f"archive member escapes: {member.name}")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                stream = bundle.extractfile(member)
                check(stream is not None, f"unreadable archive member: {member.name}")
                target.write_bytes(stream.read())


def tree_hashes(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): file_sha(p) for p in sorted(root.rglob("*")) if p.is_file()}


def compare_trees(left: Path, right: Path, what: str) -> dict[str, str]:
    a, b = tree_hashes(left), tree_hashes(right)
    if a != b:
        different = []
        for name in sorted(set(a) | set(b)):
            if a.get(name) != b.get(name):
                different.append({"path": name, "expected_sha256": b.get(name), "actual_sha256": a.get(name)})
        versions = {}
        for package in ("numpy", "scipy", "lightgbm"):
            try:
                versions[package] = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError:
                versions[package] = None
        context = {
            "python": platform.python_version(), "packages": versions,
            "cpu_environment": {key: os.environ.get(key) for key in (
                "OPENBLAS_NUM_THREADS", "OPENBLAS_CORETYPE", "NPY_DISABLE_CPU_FEATURES",
                "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS")},
            "mismatch_count": len(different), "mismatches": different[:80],
        }
        raise ValueError(f"{what}: archived/fresh tree mismatch diagnostics: "
                         + json.dumps(context, sort_keys=True))
    return a


def verify_source_lock(source: Path) -> dict:
    lock = json.loads((HERE / "source-lock.json").read_bytes())
    check(lock["source_commit"] == SOURCE_COMMIT, "source commit is not the pinned R21 revision")
    check(lock["protocol_sha256"] == PROTOCOL_SHA, "R21 protocol SHA differs")
    check(file_sha(source / "research/20261125-r21-score-dependence/protocol.json") == PROTOCOL_SHA,
          "checked out protocol differs")
    for rel, digest in lock["committed_source_files_sha256"].items():
        check(file_sha(source / rel) == digest, "pinned R21 source bytes differ: " + rel)
    result = subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD"], check=True, text=True,
                            capture_output=True).stdout.strip()
    check(result == SOURCE_COMMIT, "source checkout is not the exact full pinned commit")
    return lock


def verify_package(data_root: Path) -> tuple[dict, dict[str, Path]]:
    manifest = json.loads((HERE / "manifest.json").read_bytes())
    check(manifest["source_commit"] == SOURCE_COMMIT, "package manifest source commit differs")
    check(inventory(HERE) == manifest["files"], "package file inventory/SHA differs from manifest")
    lock = json.loads((HERE / "source-lock.json").read_bytes())
    expected_inputs = json.loads((HERE / "inputs/source-inputs.json").read_bytes())
    paths = {"r5": data_root / ARCHIVES["r5"], "r7": data_root / ARCHIVES["r7"],
             "r10": data_root / ARCHIVES["r10"], "r11": HERE / "inputs/r11"}
    for key, root in paths.items():
        expected_manifest = expected_inputs["manifest_sha256"][key]
        check(file_sha(root / "manifest.json") == expected_manifest, f"{key} original manifest SHA differs")
        for rel, expected_sha in expected_inputs["files"][key].items():
            check(file_sha(root / rel) == expected_sha, f"{key} retained input differs: {rel}")
            if rel != "manifest.json" and key != "r11":
                recorded = json.loads((root / "manifest.json").read_bytes())["files"].get(rel)
                check(recorded == expected_sha, f"{key} input does not match original manifest: {rel}")
    understat_source = data_root / "workspace-updates/20261125-r14-territory-press/inputs/understat.tar.gz"
    understat_copy = HERE / "inputs/understat.tar.gz"
    understat_sha = lock["understat_archive_sha256"]
    check(file_sha(understat_source) == understat_sha == file_sha(understat_copy),
          "R14 #51 Understat original archive SHA differs")
    posthoc = HERE / "diagnostics/actual-ranks.csv"
    check(file_sha(posthoc) == lock["posthoc_actual_ranks_sha256"], "post-hoc actual-ranks CSV SHA differs")
    return lock, paths


def audit_understat(archive: Path, temp: Path) -> Path:
    restored = temp / "understat-restored"
    safe_unpack(archive, restored)
    audit_out = temp / "understat-audit"
    script = HERE / "verification/understat/verify_understat.py"
    subprocess.run([sys.executable, "-B", str(script), "--r14-root", str(restored),
                    "--archive", str(archive), "--out-dir", str(audit_out)], check=True)
    report = json.loads((audit_out / "verification.json").read_bytes())
    check(report["overall"]["events"] == 11031 and report["overall"]["raw_response_files"] == 35,
          "Understat independent raw event/source counts differ")
    check(report["overall"]["passed_all_issue_checks"], "Understat raw audit reports an issue")
    for name in ("events.jsonl", "sources.jsonl", "reports/coverage.json"):
        (restored / name).unlink(missing_ok=True)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    subprocess.run([sys.executable, "-B", "extract.py"], cwd=restored, env=env, check=True,
                   stdout=subprocess.DEVNULL)
    events = restored / "events.jsonl"
    check(file_sha(events) == EVENTS_SHA, "offline Understat extraction differs from fixed R14 event bytes")
    return events


def run_study(source: Path, data_paths: dict[str, Path], events: Path, destination: Path,
              cwd: Path, env: dict[str, str]) -> None:
    command = [sys.executable, "-B", "-m", "research_program.score_dependence_study",
               "--r5", str(data_paths["r5"]), "--r7", str(data_paths["r7"]),
               "--r10", str(data_paths["r10"]), "--r11", str(data_paths["r11"]),
               "--events", str(events), "--out", str(destination)]
    subprocess.run(command, cwd=cwd, env=env, check=True)


def rebuild_frozen_payloads(source: Path, paths: dict[str, Path], study: Path, events: Path,
                            temp: Path) -> dict:
    sys.path.insert(0, str(source / "runtime"))
    from research_program import score_dependence_forward as forward
    from research_program import score_dependence as model
    from research_program import territory_forward as territory
    from research_program.r9_score_study import verified_archive
    from research.analysis_freeze import aware

    protocol = source / "research/20261125-r21-score-dependence/protocol.json"
    archives = dict(paths)
    recipes, identity, manifests = forward.configure(study, events, protocol, archives)
    extracted = temp / "upstream-first-issues"
    r5_dir, r7_dir, r10_dir = extracted / "r5", extracted / "r7", extracted / "r10"
    verified_archive(paths["r5"], manifests["r5"], "forward-first-issues.tar.gz", r5_dir)
    verified_archive(paths["r7"], manifests["r7"], "first-issues.tar.gz", r7_dir)
    verified_archive(paths["r10"], manifests["r10"], "forward/first-issues.tar.gz", r10_dir)
    parents = [territory.FirstIssues.load(r5_dir / "issued"),
               territory.FirstIssues.load(r7_dir), territory.FirstIssues.load(r10_dir)]
    leagues = territory._leagues(temp / "league-inputs", archives, manifests, events, recipes,
                                 history_type=model.Design)
    forward_index = json.loads((HERE / "forward/receipts.json").read_bytes())
    registration = territory.ledger._read(HERE / "forward", forward_index["registration"])
    cutoff = aware(registration["recorded_at"])
    fixtures = registration["payload"]["fixtures"]
    rebuilt = {}
    by_comp = Counter()
    for match_id, fixture in fixtures.items():
        expected_record = territory.ledger._read(HERE / "forward", forward_index["matches"][match_id])
        actual = forward.forecast(fixture, parents, leagues[fixture["cohort"]],
                                  recipes[fixture["cohort"]], identity, cutoff)
        actual["registration_sha256"] = registration["record_sha256"]
        check(actual == expected_record["payload"], "frozen R21 first-issue payload differs: " + match_id)
        rebuilt[match_id] = actual
        by_comp[fixture["cohort"]] += 1

    # Re-select every seat from the freshly recomputed probabilities, without invoking
    # any ledger/register/issue writer or touching the preserved freeze directories.
    ranked_index = json.loads((HERE / "ranked/plan.json").read_bytes())
    ranked = territory.ledger._read(HERE / "ranked", ranked_index)
    selected = ranked["payload"]["identity"]["selected"]
    seat_counts = {}
    for code in forward.source.CODES:
        candidates = []
        for match_id, fixture in fixtures.items():
            if fixture["cohort"] != code:
                continue
            payload = rebuilt[match_id]
            candidates.append({
                "match_id": match_id, "kickoff_at": fixture["kickoff_at"],
                "first_probability": payload["quality"]["p_first"],
                "primary": payload["forecasts"]["candidate"]["primary"],
                "top3": payload["forecasts"]["candidate"]["top3"],
                "home": payload["home_name"], "away": payload["away_name"],
                "first_issue": forward_index["matches"][match_id],
            })
        expected_seats = forward.ranked.rank(candidates)
        check(selected[code] == expected_seats, "recomputed R21 ranked seats differ: " + code)
        seat_counts[code] = len(expected_seats)
    summary = {
        "schema": "r21-frozen-payload-rebuild-v1",
        "method": "Pure forecast and rank functions at the original registration clock; no registration or issue writer called.",
        "forecast_payloads_recomputed": len(rebuilt), "seats_recomputed": sum(seat_counts.values()),
        "competition_forecasts": dict(sorted(by_comp.items())),
        "competition_seats": seat_counts,
        "registration_sha256": registration["record_sha256"],
        "ranked_plan_sha256": ranked["record_sha256"],
    }
    out = HERE / "verification/frozen-payload-rebuild.json"
    out.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    return summary


def verify(source: Path, data_root: Path) -> None:
    source = source.resolve()
    data_root = data_root.resolve()
    lock, paths = verify_package(data_root)
    verify_source_lock(source)
    versions = {name: importlib.metadata.version(name) for name in ("numpy", "scipy", "lightgbm")}
    expected_versions = {name: lock["runtime"][name] for name in versions}
    check(versions == expected_versions, "installed numeric package versions differ from source-lock.json: "
          + json.dumps({"expected": expected_versions, "actual": versions}, sort_keys=True))
    check(platform.python_version_tuple()[:2] == tuple(lock["runtime"]["python"].split(".")),
          "Python major/minor differs from source lock: " + platform.python_version())
    reproducibility_env = lock["runtime"]["reproducibility_environment"]
    actual_env = {key: os.environ.get(key) for key in reproducibility_env}
    check(actual_env == reproducibility_env, "CPU/thread environment differs from source lock: "
          + json.dumps({"expected": reproducibility_env, "actual": actual_env}, sort_keys=True))
    freeze_command = [sys.executable, "-B", str(HERE / "verify_freezes.py")]
    subprocess.run(freeze_command, cwd=HERE, check=True, stdout=subprocess.DEVNULL)
    r14_archive = data_root / "workspace-updates/20261125-r14-territory-press/inputs/understat.tar.gz"

    env = dict(os.environ, **reproducibility_env, PYTHONPATH=str(source / "runtime"),
               PYTHONDONTWRITEBYTECODE="1")
    with tempfile.TemporaryDirectory(prefix="r21-verify-") as raw_temp:
        temp = Path(raw_temp)
        events = audit_understat(r14_archive, temp)
        a, b = temp / "study-a", temp / "study-b"
        run_study(source, paths, events, a, temp, env)
        run_study(source, paths, events, b, temp, env)
        compare_trees(a, b, "two fresh deterministic R21 training runs")
        reference = HERE / "replay/reference"
        repeat = HERE / "replay/repeat"
        archived = compare_trees(reference, repeat, "Dalton's two retained R21 output directories")
        compare_trees(a, reference, "fresh R21 training vs retained historical output")
        check(tree_hashes(a) == archived, "fresh R21 training differs from retained repeat output")
        metrics = json.loads((a / "metrics.json").read_bytes())
        check(metrics["overall"]["evaluation"]["population"] == 1752,
              "2025/26 fixed evaluation population differs")
        import tables
        tables.build(HERE, temp / "tables")
        for name in ("competition-window-coverage.csv", "paired-gains.csv", "fitted-weights-and-doses.csv"):
            check((temp / "tables" / name).read_bytes() == (HERE / "reports" / name).read_bytes(),
                  "recomputed report table differs: " + name)
        actual_ranks = temp / "actual-ranks.csv"
        subprocess.run([sys.executable, "-B", str(HERE / "diagnostics/actual_ranks.py"),
                        str(data_root / "workspace-updates"), str(reference), str(actual_ranks)],
                       cwd=temp, env=env, check=True)
        check(file_sha(actual_ranks) == lock["posthoc_actual_ranks_sha256"]
              and actual_ranks.read_bytes() == (HERE / "diagnostics/actual-ranks.csv").read_bytes(),
              "post-hoc actual-rank CSV differs from the archived calculation")
        forecast_summary = rebuild_frozen_payloads(source, paths, a, events, temp)
        check(forecast_summary["forecast_payloads_recomputed"] == 45
              and forecast_summary["seats_recomputed"] == 15,
              "not all frozen forward payloads and seats were recomputed")
    print("R21 raw Understat audit, two full train/replay runs, report tables, frozen payloads and seats verified.",
          flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, default=HERE.parents[2])
    args = parser.parse_args()
    verify(args.source, args.data_root)
