#!/usr/bin/env python3
"""Independently verify the pinned R22 data release without writing issues or seats."""

from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = "workspace-updates/20261125-r22-draw-preserving"
R21PKG = "workspace-updates/20261125-r21-score-dependence"
BASE = "02828b3a726b2338f0880e9383c3f8bdf5c08bab"
SOURCE_COMMIT = "46de33168c093816ac7cd19a57e36e51286b408f"
TREE = "a8f6a23c7e0ee8d48093f8e8c35e9f6e535bd7d5022efd32d9de710a70251c5d"
REG = "4f14e72cce5aa9a29c4faf88c82cc23f6b76ac7b05de967c7fc12dbb9da591bb"
RANK = "45814f434785f55ed592f9d6fa319b064ac6fe59fcf3d4443a9a7ea8f9998857"


def sha(b):
    return hashlib.sha256(b).hexdigest()


def fsha(p):
    return sha(p.read_bytes())


def check(ok, msg):
    if not ok:
        raise ValueError(msg)


def files(root):
    result = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if path.is_file() and "__pycache__" not in relative.parts and path.suffix not in (".pyc", ".pyo"):
            result[relative.as_posix()] = fsha(path)
    return result


def compact_tree(root):
    return sha(json.dumps(files(root), sort_keys=True, separators=(",", ":")).encode())


def run(cmd, **kw):
    subprocess.run([str(x) for x in cmd], check=True, **kw)


def inventory(root):
    return {k: v for k, v in files(root).items() if k not in ("manifest.json", "SHA256SUMS")}


def verify_inventory(root):
    expected = json.loads((root / "manifest.json").read_bytes())
    actual = inventory(root)
    check(
        expected.get("schema") == "r22-evidence-package-manifest-v1", "unexpected package manifest schema"
    )
    check(
        actual == expected.get("files"),
        "a package file is missing, was added, or differs from its listed SHA",
    )
    checksum_list = "".join(f"{digest}  {name}\n" for name, digest in sorted(actual.items()))
    check((root / "SHA256SUMS").read_bytes() == checksum_list.encode(), "package SHA256SUMS differs")


def compare(a, b, label):
    fa, fb = files(a), files(b)
    check(
        fa == fb,
        label
        + " differs: "
        + json.dumps([k for k in sorted(set(fa) | set(fb)) if fa.get(k) != fb.get(k)][:30]),
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--data-root", type=Path, default=HERE.parents[1])
    a = p.parse_args()
    source = a.source.resolve()
    root = a.data_root.resolve()
    pkg = root / PKG
    r21 = root / R21PKG
    lock = json.loads((pkg / "source-lock.json").read_bytes())
    check(pkg == HERE, "--data-root must resolve to package parent; expected " + str(HERE))
    verify_inventory(pkg)
    head = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    check(head == SOURCE_COMMIT, "source checkout SHA differs")
    check(
        subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", BASE, "HEAD"]).returncode
        == 0,
        "data history lacks exact #61 parent",
    )
    check(
        lock["final_source_commit"] == SOURCE_COMMIT and lock["current_public_data_pr61_head"] == BASE,
        "source lock commit/parent differs",
    )
    check(fsha(source / lock["protocol_path"]) == lock["protocol_sha256"], "pinned protocol bytes differ")
    for rel, digest in lock["source_files_sha256"].items():
        check(fsha(source / rel) == digest, "source file SHA differs: " + rel)
    check(compact_tree(pkg / "replay/reference") == TREE, "reference replay tree SHA differs")
    check(
        files(pkg / "replay/reference") == files(pkg / "replay/repeat"), "reference and repeat tree differ"
    )
    check(len(files(pkg / "replay/reference")) == 38, "historical output file count differs")
    ordered_ranks = pkg / "verification/independent/ordered-ranks.csv"
    check(
        fsha(ordered_ranks) == lock["independent_ordered_csv_sha256"],
        "independent ordered-ranks CSV SHA differs",
    )
    # Check source parents through their original manifests, using R21's independently retained input index.
    inp = json.loads((r21 / "inputs/source-inputs.json").read_bytes())
    paths = {
        "r5": root / "workspace-updates/20261123-all-scope-kpi",
        "r7": root / "workspace-updates/20261123-prematch-literature",
        "r10": root / "workspace-updates/20261125-r10-shot-conversion",
        "r11": r21 / "inputs/r11",
    }
    for name, folder in paths.items():
        check(
            fsha(folder / "manifest.json") == inp["manifest_sha256"][name],
            name + " original manifest differs",
        )
        for rel, digest in inp["files"][name].items():
            check(fsha(folder / rel) == digest, name + " retained input differs: " + rel)
    r21lock = json.loads((r21 / "source-lock.json").read_bytes())
    understat = root / "workspace-updates/20261125-r14-territory-press/inputs/understat.tar.gz"
    check(
        fsha(understat)
        == r21lock["understat_archive_sha256"]
        == lock["r21_parent"]["understat_archive_sha256"],
        "Understat archive SHA differs",
    )
    # Verify the R22 official receipt indexes and raw members before any pure recomputation.
    sys.path.insert(0, str(source / "runtime"))
    from research_program import territory_forward as territory
    from research.analysis_freeze import aware, verify as verify_canonical

    ix = json.loads((pkg / "forward/receipts.json").read_bytes())
    reg = ix["registration"]
    check(reg["sha256"] == REG, "registration receipt SHA differs")
    check(
        fsha(pkg / "forward/receipts.json") == lock["official_forward"]["registration_receipts_sha256"],
        "registration index raw SHA differs",
    )
    check(
        fsha(pkg / "forward" / reg["file"]) == lock["official_forward"]["registration_file_sha256"],
        "registration raw file SHA differs",
    )
    first_issues = territory.FirstIssues.load(pkg / "forward")
    rr = territory.ledger._read(pkg / "forward", reg)
    verify_canonical(rr)
    check(
        rr["record_sha256"] == REG and rr["recorded_at"] == lock["official_forward"]["recorded_at"],
        "registration clock/record differs",
    )
    check(len(ix["matches"]) == 45, "official first fixture count differs")
    for mid, item in ix["matches"].items():
        raw = (pkg / "forward" / item["file"]).read_bytes()
        rec = json.loads(raw)
        rec = territory.ledger._read(pkg / "forward", item)
        verify_canonical(rec)
        check(
            rec["record_sha256"] == item["sha256"] and rec["recorded_at"] == item["recorded_at"],
            "official issue receipt differs: " + mid,
        )
        check(
            rec["payload"]["registration_sha256"] == REG and rec["revision"] == 1,
            "issue registration pointer/revision differs: " + mid,
        )
        check(
            rec["payload"]["forecasts"]["candidate"]["primary"]
            and len(rec["payload"]["forecasts"]["candidate"]["top3"]) == 3,
            "issue scoreline payload incomplete: " + mid,
        )
    ri = json.loads((pkg / "ranked/plan.json").read_bytes())
    check(ri["sha256"] == RANK, "rank receipt SHA differs")
    check(
        fsha(pkg / "ranked/plan.json") == lock["official_ranked"]["plan_file_sha256"],
        "rank plan bytes differ",
    )
    rrec = territory.ledger._read(pkg / "ranked", ri)
    verify_canonical(rrec)
    check(
        fsha(pkg / "ranked" / ri["file"]) == lock["official_ranked"]["record_file_sha256"]
        and rrec["record_sha256"] == RANK,
        "rank record bytes differ",
    )
    selected = rrec["payload"]["identity"]["selected"]
    check(sum(map(len, selected.values())) == 15, "ranked seat count differs")
    # Rebuild Understat event bytes from the original R14 archive, then perform two complete R22 runs.
    sys.path.insert(0, str(r21))
    spec = importlib.util.spec_from_file_location("r21verify", r21 / "verify.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    env = dict(
        os.environ,
        PYTHONHASHSEED="0",
        OPENBLAS_NUM_THREADS="1",
        OPENBLAS_CORETYPE="Haswell",
        NPY_DISABLE_CPU_FEATURES="AVX512F",
        OMP_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
        NUMEXPR_NUM_THREADS="1",
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONPATH=str(source / "runtime"),
    )
    r21historical = r21 / "replay/reference"
    r21forward = r21 / "forward"
    r11 = paths["r11"]
    with tempfile.TemporaryDirectory(prefix="r22-release-verify-") as temp_raw:
        temp = Path(temp_raw)
        events = mod.audit_understat(understat, temp)
        common = [
            "--r5",
            paths["r5"],
            "--r7-root",
            paths["r7"],
            "--r10",
            paths["r10"],
            "--r11",
            r11,
            "--r21-data",
            root,
            "--r21-historical",
            r21historical,
            "--events",
            events,
        ]
        aout = temp / "run-a"
        bout = temp / "run-b"
        for out in (aout, bout):
            run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "research_program.draw_preserving_study",
                    *common,
                    "--out",
                    out,
                ],
                cwd=source,
                env=env,
                stdout=subprocess.DEVNULL,
            )
        compare(aout, bout, "two fresh R22 train/replay runs")
        compare(aout, pkg / "replay/reference", "fresh replay vs reference")
        compare(bout, pkg / "replay/repeat", "fresh replay vs repeat")
        metrics = json.loads((aout / "metrics.json").read_bytes())
        expected = {"evaluation": 1752, "recent": 500, "november_extension": 48}
        for w, n in expected.items():
            check(metrics["overall"][w]["population"] == n, "window population mismatch " + w)
        check(
            metrics["overall"]["evaluation"]["comparisons"]["r7_vs_candidate"]["tracks"]["candidate"][
                "metrics"
            ]["score_top1"]["hits"]
            == 229,
            "R22 evaluation first hits differ",
        )
        # Regenerate all compact tables outside the package and compare byte-for-byte.
        reports = temp / "reports"
        run(
            [sys.executable, "-B", str(pkg / "reports/build_reports.py"), "--output-dir", reports],
            env=env,
            stdout=subprocess.DEVNULL,
        )
        run(
            [
                sys.executable,
                "-B",
                pkg / "reports/build_coverage_bottleneck.py",
                "--replay",
                aout,
                "--ordered-ranks",
                ordered_ranks,
                "--output",
                reports / "coverage-bottleneck.json",
            ],
            env=env,
        )
        expected_reports = files(pkg / "reports")
        del expected_reports["build_reports.py"], expected_reports["build_coverage_bottleneck.py"]
        rebuilt_reports = files(reports)
        for name in sorted(expected_reports.keys() | rebuilt_reports.keys()):
            check(
                expected_reports.get(name) == rebuilt_reports.get(name),
                "derived report differs: " + name,
            )
        # Secondary independent projection implementation is re-executed against the same pinned inputs.
        run(
            [
                sys.executable,
                "-B",
                str(pkg / "verification/independent/verify.py"),
                "--data-root",
                root,
                "--source",
                source,
            ],
            env=env,
        )
        # Rebuild all forward payloads at the original recorded cutoff with pure forecast/rank functions only.
        from research_program import draw_preserving_forward as fw, score_dependence
        from research_program.r9_score_study import verified_archive

        recipes, identity, manifests = fw.configure(
            aout,
            events,
            source / lock["protocol_path"],
            paths,
            r21_study=r21historical,
            earlier=territory.FirstIssues.load(r21forward),
        )
        ex = temp / "parents"
        parents = []
        for name, key, manifest_key in [
            ("r5", "forward-first-issues.tar.gz", "r5"),
            ("r7", "first-issues.tar.gz", "r7"),
            ("r10", "forward/first-issues.tar.gz", "r10"),
        ]:
            target = ex / name
            verified_archive(paths[manifest_key], manifests[manifest_key], key, target)
            parents.append(territory.FirstIssues.load(target / ("issued" if name == "r5" else "")))
        leagues = territory._leagues(
            temp / "league-inputs", paths, manifests, events, recipes, history_type=score_dependence.Design
        )
        cutoff = aware(rr["recorded_at"])
        rebuilt = {}
        for mid, fixture in rr["payload"]["fixtures"].items():
            pld = fw.forecast(
                fixture,
                parents,
                leagues[fixture["cohort"]],
                recipes[fixture["cohort"]],
                identity,
                cutoff,
                earlier=territory.FirstIssues.load(r21forward),
            )
            pld["registration_sha256"] = REG
            expected_payload = territory.ledger._read(pkg / "forward", ix["matches"][mid])["payload"]
            check(pld == expected_payload, "pure cutoff forecast differs: " + mid)
            rebuilt[mid] = pld
        for code in fw.source.CODES:
            candidates = []
            for mid, fixture in rr["payload"]["fixtures"].items():
                if fixture["cohort"] == code:
                    q = rebuilt[mid]
                    candidates.append(
                        {
                            "match_id": mid,
                            "kickoff_at": fixture["kickoff_at"],
                            "first_probability": q["quality"]["p_first"],
                            "primary": q["forecasts"]["candidate"]["primary"],
                            "top3": q["forecasts"]["candidate"]["top3"],
                            "home": q["home_name"],
                            "away": q["away_name"],
                            "first_issue": ix["matches"][mid],
                        }
                    )
            check(selected[code] == fw.ranked.rank(candidates), "pure seat rank differs: " + code)
    print(
        json.dumps(
            {
                "verified": True,
                "cli": "python verify.py --source PATH --data-root .",
                "source_commit": head,
                "data_parent": BASE,
                "historical_tree_sha256": TREE,
                "historical_files": 38,
                "training_runs": 2,
                "official_firsts_recomputed": 45,
                "official_ranked_seats_recomputed": 15,
                "registration_sha256": REG,
                "rank_sha256": RANK,
                "promotion": False,
                "method": "pure forecast/rank functions at original cutoff; no issuance writer or seat writer",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
