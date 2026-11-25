#!/usr/bin/env python3
"""Refit the pinned R23 history and check the research firsts and seats offline."""

import argparse
from datetime import timezone
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import runpy
import subprocess
import sys
import tarfile
import tempfile

import package_manifest
from package_manifest import file_hashes, sha, tree_sha

HERE = Path(__file__).resolve().parent
INDEPENDENT = HERE / "verification/independent"
DATA_COMMIT = "64efb374fb598b39c1c14048573c3e8754633c76"
STACK_BASE = "7f2ea66f23ba512178a66de7761c6b4ed6b5f370"
PREREGISTRATION = "c43eb3dc678028994a85da5d94340f16f1a74cce"
PROTOCOL = "research/20261125-r23-penalty-opportunity/protocol.json"
PROTOCOL_SHA = "c6c3672cc729f18ba3233cba005e604153e1da08a30d4693491b5e521e94d654"
EVENTS_SHA = "63f853739198298cbbde9dfce2cb02c582cb9dccb4070215c51453325f553bd5"
UPSTREAM = {
    "r5": "workspace-updates/20261123-all-scope-kpi",
    "r7": "workspace-updates/20261123-prematch-literature",
    "r10": "workspace-updates/20261125-r10-shot-conversion",
    "r14": "workspace-updates/20261125-r14-territory-press",
    "r21": "workspace-updates/20261125-r21-score-dependence",
    "r22": "workspace-updates/20261125-r22-draw-preserving",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_bytes())


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args])


def verify_source(source, lock):
    head = git(source, "rev-parse", "HEAD").decode().strip()
    require(head == lock["source_commit"], "R23 source checkout differs from the locked revision")
    preregistration = {"commit": PREREGISTRATION, "path": PROTOCOL, "sha256": PROTOCOL_SHA}
    require(lock["preregistration"] == preregistration, "R23 preregistration lock differs")
    git(source, "merge-base", "--is-ancestor", PREREGISTRATION, head)
    registered = git(source, "show", f"{PREREGISTRATION}:{PROTOCOL}")
    require(hashlib.sha256(registered).hexdigest() == PROTOCOL_SHA, "preregistered protocol SHA differs")
    require((source / PROTOCOL).read_bytes() == registered, "checked-out protocol differs from preregistration")
    for rel, digest in lock["source_files_sha256"].items():
        require(sha(source / rel) == digest, f"locked source bytes differ: {rel}")
    return head


def restore_pinned(data, destination, lock):
    require(lock["input_data_commit"] == DATA_COMMIT, "R23 original data commit differs")
    require(lock["stack_base"] == STACK_BASE, "R23 stacked base commit differs")
    git(data, "merge-base", "--is-ancestor", DATA_COMMIT, STACK_BASE)
    git(data, "merge-base", "--is-ancestor", STACK_BASE, "HEAD")
    destination.mkdir()
    archive = ["git", "-C", str(data), "archive", "--format=tar", DATA_COMMIT, "--", *UPSTREAM.values()]
    with subprocess.Popen(archive, stdout=subprocess.PIPE) as process:
        with tarfile.open(fileobj=process.stdout, mode="r|") as bundle:
            bundle.extractall(destination, filter="data")
        # Drain Git's final tar padding before waiting for its exit status.
        while process.stdout.read(1024 * 1024):
            pass
        if process.wait():
            raise subprocess.CalledProcessError(process.returncode, archive)

    paths = {name: destination / rel for name, rel in UPSTREAM.items()}
    for name, path in paths.items():
        metadata = lock["upstream"][name]
        hashes = file_hashes(path)
        require(metadata["path"] == UPSTREAM[name], f"{name} upstream path differs")
        require(len(hashes) == metadata["files"], f"{name} pinned upstream file count differs")
        require(tree_sha(hashes) == metadata["tree_sha256"], f"{name} pinned upstream tree differs")
        require(hashes["manifest.json"] == metadata["manifest_sha256"], f"{name} upstream manifest differs")
    return paths


def verify_understat(paths, temp, lock):
    archive = paths["r14"] / "inputs/understat.tar.gz"
    require(lock["understat"]["archive_path"] == f"{UPSTREAM['r14']}/inputs/understat.tar.gz",
            "Understat archive path differs")
    require(sha(archive) == lock["understat"]["archive_sha256"], "original R14 Understat archive differs")
    audit_understat = runpy.run_path(str(paths["r21"] / "verify.py"))["audit_understat"]
    events = audit_understat(archive, temp)
    require(sha(events) == lock["understat"]["events_sha256"] == EVENTS_SHA, "reconstructed event bytes differ")
    command = [sys.executable, "-B", str(INDEPENDENT / "audit_signal.py"), str(events)]
    reproduced = subprocess.check_output(command, cwd=temp)
    require(reproduced == (INDEPENDENT / "audit_signal.json").read_bytes(), "independent signal audit differs")
    return events


def verify_runtime(lock):
    runtime = lock["runtime"]
    require(platform.python_version() == runtime["python"], f"Python version differs: {platform.python_version()}")
    actual = {name: version(name) for name in runtime["packages"]}
    require(actual == runtime["packages"], f"numerical dependencies differ: {actual}")
    os.environ.update(runtime["environment"])


def compare_trees(actual, expected, description):
    paths = actual.keys() | expected.keys()
    differences = [name for name in sorted(paths) if actual.get(name) != expected.get(name)]
    require(not differences, f"{description} differs in {len(differences)} files: {differences[:20]}")


def verify_history(pinned, events, temp, lock, env):
    archived = {name: file_hashes(HERE / "replay" / name) for name in ("reference", "repeat")}
    compare_trees(archived["reference"], archived["repeat"], "archived historical reference and repeat")
    metadata = lock["historical"]
    require(len(archived["reference"]) == metadata["files"], "historical output file count differs")
    require(tree_sha(archived["reference"]) == metadata["tree_sha256"], "historical tree SHA differs")
    common = [sys.executable, "-B", "-m", "research_program.penalty_opportunity_study",
              "--data-root", str(pinned), "--events", str(events)]
    runs = {name: temp / name for name in archived}
    fresh = {}
    for name, out in runs.items():
        print(f"Refitting R23 history ({name}) from the pinned inputs", flush=True)
        subprocess.run([*common, "--out", str(out)], cwd=temp, env=env, check=True)
        fresh[name] = file_hashes(out)
    compare_trees(fresh["reference"], fresh["repeat"], "two fresh R23 refits")
    for name in runs:
        compare_trees(fresh[name], archived[name], f"fresh refit vs archived {name}")
    study = runs["reference"]
    windows = read(study / "metrics.json")["overall"]
    expected_population = {"validation_2024_25": 1752, "evaluation": 1752,
                           "recent": 500, "november_extension": 48}
    require({key: row["population"] for key, row in windows.items()} == expected_population,
            "registered historical window population differs")
    return study


def verify_independent(pinned, events, study, temp, env):
    command = [sys.executable, "-B", str(INDEPENDENT / "independent_scores.py"),
               "--study", str(study), "--data-root", str(pinned), "--events", str(events)]
    actual = subprocess.check_output(command, cwd=temp, env=env)
    require(actual == (INDEPENDENT / "expected.json").read_bytes(), "independent score audit differs")
    print("Independently reproduced the score ranks and probabilities for all 2,300 held-out fixtures", flush=True)


def verify_forward(source, pinned, events, study, temp, lock):
    sys.path.insert(0, str(source / "runtime"))
    from research.analysis_freeze import aware
    from research_program import penalty_opportunity_forward as forward
    from research_program.future_identity import fixture_identity

    firsts, ranks = HERE / "forward", HERE / "ranked"
    index = read(firsts / "receipts.json")
    receipt = index["registration"]
    registration = forward.ledger._read(firsts, receipt)
    stamp = registration["recorded_at"]
    registration_sha = registration["record_sha256"]
    meta = lock["forward"]
    require(stamp == meta["recorded_at"] and stamp == receipt["recorded_at"], "registration clock differs")
    require(registration_sha == meta["registration_sha256"], "registration SHA differs")
    require(registration["track"] == forward.TRACK + "-registration", "registration track differs")

    # Consume the first refit's weights. The source helpers here only read inputs and forecast.
    locked = forward._locked(pinned, events, temp / "forward-inputs")
    trained = forward._recipes(study, locked)
    cutoff = aware(stamp).astimezone(timezone.utc)
    coverage, fixtures, forecasts = forward._prepare(locked, cutoff, trained)
    require(len(coverage) == forward.R22_POPULATION == meta["original_fixtures"], "coverage population differs")
    require(len(fixtures) == meta["issued_firsts"], "eligible first count differs")
    identity = dict(
        locked.identity, **trained[2], original_population=len(coverage), coverage=coverage,
        already_started=[mid for mid, row in coverage.items() if row["disposition"] == "already_started"],
    )
    expected_registration = {"identity": identity, "fixtures": fixtures, "track": forward.TRACK}
    require(registration["payload"] == expected_registration, "recomputed registration scope or provenance differs")
    expected_coverage = dict(registration=receipt, **forward._report(coverage, forecasts, stamp))
    require(read(firsts / "coverage.json") == expected_coverage, "archived forward coverage differs")

    require(set(index["matches"]) == set(fixtures), "archived first issues do not cover the eligible population")
    codes = [competition["code"] for competition in read(source / "configs/analysis-scope.json")["competitions"]]
    groups = {code: [] for code in codes}
    for mid, fixture in fixtures.items():
        ref = index["matches"][mid]
        original = forward.ledger._read(firsts, ref)
        require(original["track"] == forward.TRACK and original["match_id"] == mid, f"first identity differs: {mid}")
        require(fixture_identity(original["fixture"]) == fixture_identity(fixture), f"fixture identity differs: {mid}")
        issue_time = aware(original["recorded_at"])
        require(original["recorded_at"] == ref["recorded_at"] and cutoff == aware(original["fixture"]["cutoff_at"])
                and cutoff <= issue_time < aware(fixture["kickoff_at"]), f"first issue clock differs: {mid}")
        payload = forecasts[mid]
        require(original["payload"] == dict(payload, registration_sha256=registration_sha),
                f"recomputed first issue differs: {mid}")
        candidate = payload["forecasts"]["candidate"]
        groups[fixture["cohort"]].append(dict(
            match_id=mid, kickoff_at=fixture["kickoff_at"], first_probability=payload["quality"]["p_first"],
            primary=candidate["primary"], top3=candidate["top3"], home=payload["home_name"],
            away=payload["away_name"], first_issue=ref,
        ))

    plan = read(ranks / "plan.json")
    rank_record = forward.ledger._read(ranks, plan)
    require(rank_record["record_sha256"] == meta["rank_sha256"], "rank registration SHA differs")
    require(rank_record["recorded_at"] == plan["recorded_at"] == meta["rank_recorded_at"], "rank clock differs")
    require(rank_record["track"] == forward.ranked.TRACK + "-registration", "rank registration track differs")
    rank_payload = rank_record["payload"]
    require(rank_payload["track"] == forward.ranked.TRACK and rank_payload["fixtures"] == fixtures,
            "rank registered fixtures differ")
    rank_identity = rank_payload["identity"]
    require(rank_identity["source_registration"] == registration_sha and rank_identity["source_track"] == forward.TRACK
            and rank_identity["slots_per_competition"] == 3, "rank is bound to a different source or seat count")
    require(rank_identity["stages"] == read(source / "project-goals.json")["research_roadmap_20261124"]["stages"],
            "rank stages differ from their pinned definitions")
    selected = {code: forward.ranked.rank(rows) for code, rows in groups.items()}
    require(selected == rank_identity["selected"], "recomputed ranked seats differ")
    seat_count = sum(map(len, selected.values()))
    require(seat_count == meta["ranked_seats"], "ranked seat count differs")
    rank_time = aware(rank_record["recorded_at"])
    require(all(aware(ref["recorded_at"]) <= rank_time for ref in index["matches"].values()),
            "rank cutoff preceded an archived research first")
    return {"original_fixtures": len(coverage), "first_issues": len(fixtures), "ranked_seats": seat_count,
            "registration_sha256": registration_sha, "rank_sha256": rank_record["record_sha256"]}


def verify_reports(study, temp, env):
    reports = HERE / "reports"
    output = temp / "reports"
    subprocess.run([sys.executable, "-B", str(reports / "build_reports.py"), "--replay", str(study),
                    "--output-dir", str(output)], cwd=temp, env=env, check=True)
    expected = file_hashes(reports)
    del expected["build_reports.py"]
    compare_trees(file_hashes(output), expected, "recomputed report tables")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="checkout of the locked R23 source SHA")
    parser.add_argument("--data-root", type=Path, default=HERE.parents[1], help="data git checkout")
    parser.add_argument("--work-root", type=Path, help="optional parent directory for temporary working files")
    args = parser.parse_args()
    source, data = args.source.resolve(), args.data_root.resolve()
    require(data == HERE.parents[1], "data root must contain this release package")
    lock = read(HERE / "source-lock.json")
    package_manifest.verify(HERE)
    head = verify_source(source, lock)
    verify_runtime(lock)
    with tempfile.TemporaryDirectory(prefix="r23-release-", dir=args.work_root) as directory:
        temp = Path(directory).resolve()
        os.environ["MPLCONFIGDIR"] = str(temp / "matplotlib")
        env = dict(os.environ, PYTHONPATH=str(source / "runtime"), TMPDIR=str(temp))
        pinned = temp / "pinned-data"
        paths = restore_pinned(data, pinned, lock)
        events = verify_understat(paths, temp, lock)
        study = verify_history(pinned, events, temp, lock, env)
        verify_independent(pinned, events, study, temp, env)
        forward = verify_forward(source, pinned, events, study, temp, lock)
        verify_reports(study, temp, env)
    package_manifest.verify(HERE)
    print(json.dumps({"source_commit": head, "input_data_commit": DATA_COMMIT, "historical_refits": 2,
                      "historical": lock["historical"], "forward": forward}, indent=2))


if __name__ == "__main__":
    main()
