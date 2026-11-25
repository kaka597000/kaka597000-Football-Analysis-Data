#!/usr/bin/env python3
"""Rebuild and package the registered R17 historical and forward evidence."""

import argparse
import csv
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

# Keep the numerical kernel aligned with the successful Actions host and with
# the reproducible local refits. Set these before importing NumPy or SciPy.
os.environ["NPY_DISABLE_CPU_FEATURES"] = "AVX512F"
os.environ["OPENBLAS_CORETYPE"] = "Haswell"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"

import numpy as np
import scipy
import lightgbm
import verify


ROOT = Path(__file__).resolve().parent
ARTIFACTS = ("inputs.json", "metrics.json")
FLOAT_ATOL = 1e-9
FLOAT_RTOL = 1e-7


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def run_study(source, r5, r7, r10, scope, out):
    runtime = str(Path(source) / "runtime")
    if runtime not in sys.path:
        sys.path.insert(0, runtime)
    from research_program import schedule_density_study

    schedule_density_study.run(Path(r5), Path(r7), Path(r10), Path(scope), Path(out))
    return Path(out)


def replay_files(root):
    root = Path(root)
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


def read_value(path):
    path = Path(path)
    if path.name.endswith(".jsonl.gz"):
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            return [json.loads(line) for line in stream if line.strip()]
    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    return path.read_bytes()


def compare_tree(left, right, *, atol=FLOAT_ATOL, rtol=FLOAT_RTOL):
    left, right = Path(left), Path(right)
    lf, rf = replay_files(left), replay_files(right)
    if lf != rf:
        raise ValueError(f"replay file inventory differs: {left} vs {right}")
    for relative in lf:
        a, b = read_value(left / relative), read_value(right / relative)
        same, reason = verify.same_value(a, b, relative, atol=atol, rtol=rtol)
        if not same:
            raise ValueError(f"replay differs ({left} vs {right}): {reason}")


def package_archive(replay, tables, destination):
    """Write deterministic gzip tar, normalizing metadata but retaining file bytes."""
    replay, tables = Path(replay), Path(tables)
    with open(destination, "wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                for base, label in ((replay, "replay"), (tables, "tables")):
                    for path in sorted(p for p in base.rglob("*") if p.is_file()):
                        relative = f"{label}/{path.relative_to(base).as_posix()}"
                        info = archive.gettarinfo(str(path), arcname=relative)
                        info.uid = info.gid = 0
                        info.uname = info.gname = ""
                        info.mode = 0o644
                        info.mtime = 0
                        with path.open("rb") as stream:
                            archive.addfile(info, stream)


def build_tables(replay):
    replay = Path(replay)
    metrics = json.loads((replay / "metrics.json").read_text(encoding="utf-8"))
    rows, seat_rows, batch_summary_rows, sweep_rows = [], [], [], []
    weight_rows = []
    for window, report in sorted(metrics.items()):
        for code, summary in sorted(report["competitions"].items()):
            for arm, values in sorted(summary["rates"].items()):
                row = {"window": window, "competition": code, "arm": arm, "games": values.get("games")}
                for kpi, pair in values.get("counts", {}).items():
                    row[kpi + "_hits"], row[kpi + "_n"] = pair
                row["score_log_loss"] = values.get("score_log_loss")
                row["wdl_log_loss"] = values.get("wdl_log_loss")
                row["mean_first_probability"] = values.get("mean_first_probability")
                row["actual_lines"] = summary.get("actual_lines")
                for market, count in values.get("issued", {}).items():
                    row["issued_" + market] = count
                for category, count in sorted(values.get("settlements", {}).items()):
                    row["settlement_" + category.lower()] = count
                rows.append(row)
            for relation in ("vs_r7", "vs_market"):
                comparisons = summary.get(relation, {})
                for kpi, values in sorted(comparisons.items()):
                    rows.append({"window": window, "competition": code, "arm": "comparison:" + relation,
                                 "kpi": kpi, **values})
            for arm, selection in sorted(summary.get("ranked", {}).items()):
                batch_summary_rows.append({"window": window, "competition": code, "arm": arm,
                                           **selection})
        for folder in sorted((replay / ("independent2019" if window == "independent2019" else "main")).glob("*")):
            fit_path = folder / "fit.json"
            if not fit_path.is_file():
                continue
            fit = json.loads(fit_path.read_text(encoding="utf-8"))
            fitted = fit.get("fitted", {})
            weight_rows.append({"window": window, "competition": folder.name,
                                "scoring_beta": json.dumps(fitted.get("scoring_beta"), separators=(",", ":")),
                                "additional_beta": json.dumps(fitted.get("additional_beta"), separators=(",", ":")),
                                "doses": json.dumps(fit.get("doses"), sort_keys=True, separators=(",", ":")),
                                "train_games": fit.get("train_games"),
                                "validation_games": fit.get("validation_games"),
                                "through_train": fit.get("through_train"),
                                "through_validation": fit.get("through_validation")})
    out = ROOT / "tables"
    out.mkdir(exist_ok=True)
    batch_hits = {}
    for path in sorted(replay.glob("*-seats.jsonl.gz")):
        window = path.name.removesuffix("-seats.jsonl.gz")
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            for line in stream:
                batch = json.loads(line)
                for arm, seats in sorted(batch.get("seats", {}).items()):
                    batch_hits[(window, batch["cohort"], batch["date"], arm)] = (
                        all(record["first_hit"] for record in seats) if len(seats) == 3 else None)
                    for record in seats:
                        seat_rows.append({"window": window, "competition": batch["cohort"],
                                          "source_date": batch["date"], "population": batch["population"],
                                          "arm": arm, "seat": record["seat"], "match_id": record["id"],
                                          "primary_score": record["primary"],
                                          "first_hit": record["first_hit"],
                                          "ordered_three_hit": record["ordered_three_hit"],
                                          "full_three_match_batch": len(seats) == 3})
    grouped_dates = {}
    for (window, code, day, arm), hit in batch_hits.items():
        grouped_dates.setdefault((window, code, day), {})[arm] = hit
    for window, report in sorted(metrics.items()):
        for code in sorted(report["competitions"]):
            dates = [values for (w, c, _), values in sorted(grouped_dates.items())
                     if (w, c) == (window, code) and "candidate" in values and "r7" in values
                     and all(values[arm] is not None for arm in ("candidate", "r7"))]
            eligible = [(v["candidate"], v["r7"]) for v in dates
                        if isinstance(v["candidate"], bool) and isinstance(v["r7"], bool)]
            if eligible:
                pairs = np.asarray([[int(a), int(b)] for a, b in eligible], dtype=np.int8)
                gains = int(np.sum((pairs[:, 0] == 1) & (pairs[:, 1] == 0)))
                losses = int(np.sum((pairs[:, 0] == 0) & (pairs[:, 1] == 1)))
                rng = np.random.default_rng(20261125)
                draws = rng.integers(0, len(pairs), size=(2000, len(pairs)))
                diffs = (pairs[draws, 0].mean(axis=1) - pairs[draws, 1].mean(axis=1)) * 100
                ci = np.quantile(diffs, [0.025, 0.975]).tolist()
                candidate_hits, r7_hits = map(int, pairs.sum(axis=0))
                sweep_rows.append({"window": window, "competition": code, "full_batches": len(pairs),
                                   "candidate_sweeps": candidate_hits, "r7_sweeps": r7_hits,
                                   "gained": gains, "lost": losses, "net": candidate_hits-r7_hits,
                                   "delta_pp_ci95_low": ci[0], "delta_pp_ci95_high": ci[1],
                                   "ci_method": "paired source-date bootstrap, 2000 resamples, seed 20261125"})
            else:
                sweep_rows.append({"window": window, "competition": code, "full_batches": 0,
                                   "candidate_sweeps": 0, "r7_sweeps": 0, "gained": 0, "lost": 0,
                                   "net": 0, "delta_pp_ci95_low": None, "delta_pp_ci95_high": None,
                                   "ci_method": "not estimable: zero paired complete batches"})
    _write_csv(out / "competition-comparison.csv", rows)
    _write_csv(out / "competition-weights.csv", weight_rows)
    _write_csv(out / "batch-seats.csv", seat_rows)
    _write_csv(out / "competition-batches.csv", batch_summary_rows)
    _write_csv(out / "batch-sweep-comparison.csv", sweep_rows)


def _write_csv(path, rows):
    columns = sorted({key for row in rows for key in row})
    with Path(path).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build(args):
    source, commit, source_hashes = verify.check_source(args.source, args.source_commit)
    data = {name: verify.check_data_package(getattr(args, name), name) for name in ("r5", "r7", "r10")}
    expected_outputs = (Path(args.final).resolve(), Path(args.repeat).resolve())
    for folder in expected_outputs:
        if not folder.is_dir():
            raise ValueError(f"completed replay directory is missing: {folder}")
    args.forward = Path(args.forward).resolve()
    if not (args.forward / "plan.json").is_file():
        raise ValueError("forward lock plan.json is missing")

    with tempfile.TemporaryDirectory(prefix="r17-refit-a-") as a, tempfile.TemporaryDirectory(
        prefix="r17-refit-b-"
    ) as b:
        first = run_study(source, args.r5, args.r7, args.r10, args.scope, Path(a) / "replay")
        second = run_study(source, args.r5, args.r7, args.r10, args.scope, Path(b) / "replay")
        compare_tree(first, second)
        compare_tree(first, expected_outputs[0])
        compare_tree(first, expected_outputs[1])
        first_hashes = {name: verify.sha256(first / name) for name in replay_files(first)}
        second_hashes = {name: verify.sha256(second / name) for name in replay_files(second)}
        final_hashes = {name: verify.sha256(expected_outputs[0] / name) for name in replay_files(expected_outputs[0])}
        repeat_hashes = {name: verify.sha256(expected_outputs[1] / name) for name in replay_files(expected_outputs[1])}
        if first_hashes != second_hashes:
            raise ValueError("two same-machine independent R17 refits are not byte-identical")
        if final_hashes != repeat_hashes:
            raise ValueError("retained final and repeat outputs are not byte-identical")

        target = ROOT / "replay"
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(expected_outputs[0], target)
        refit_hashes = {
            label: {name: verify.sha256(root / name) for name in replay_files(root)}
            for label, root in (("refit_1", first), ("refit_2", second),
                                ("final", expected_outputs[0]), ("repeat", expected_outputs[1]))
        }

    forward_report = verify.check_forward(source, args.r5, args.r7, args.forward, target)
    korean_report = verify.audit_korean_receipts(source, args.r5)
    historical_coverage = verify.check_historical_coverage(source, target)
    (ROOT / "forward").mkdir(exist_ok=True)
    shutil.copyfile(args.forward / "plan.json", ROOT / "forward/plan.json")
    pointer = json.loads((args.forward / "plan.json").read_text(encoding="utf-8"))
    shutil.copyfile(args.forward / pointer["file"], ROOT / "forward" / pointer["file"])
    build_tables(target)
    artifact_hashes = {name: verify.sha256(target / name) for name in replay_files(target)}
    table_hashes = {name: verify.sha256(ROOT / "tables" / name)
                    for name in replay_files(ROOT / "tables")}
    package_archive(target, ROOT / "tables", ROOT / "r17-replay.tar.gz")

    write_json(ROOT / "evidence.json", {
        "source_commit": commit,
        "source_files": source_hashes,
        "numerical_environment": {
            "python": f"{sys.version_info.major}.{sys.version_info.minor}", "numpy": np.__version__,
            "scipy": scipy.__version__, "lightgbm": lightgbm.__version__,
            "NPY_DISABLE_CPU_FEATURES": os.environ["NPY_DISABLE_CPU_FEATURES"],
            "OPENBLAS_CORETYPE": os.environ["OPENBLAS_CORETYPE"],
            "OPENBLAS_NUM_THREADS": os.environ["OPENBLAS_NUM_THREADS"],
            "OMP_NUM_THREADS": os.environ["OMP_NUM_THREADS"],
        },
        "data_manifests": {name: value[1] for name, value in data.items()},
        "historical_inputs": {"final": str(expected_outputs[0]), "repeat": str(expected_outputs[1])},
        "independent_refits": 2,
        "comparison": {"discrete_fields": "exact", "float_atol": FLOAT_ATOL, "float_rtol": FLOAT_RTOL},
        "korean_receipt_audit": korean_report,
        "historical_coverage": historical_coverage,
        "replay_artifact_sha256": artifact_hashes,
        "table_sha256": table_hashes,
        "refit_artifact_sha256": refit_hashes,
        "forward": forward_report,
    })
    (ROOT / "source-commit.txt").write_text(commit + "\n", encoding="ascii")
    manifest_files = {}
    for path in sorted(ROOT.rglob("*")):
        if path.is_file() and path.name != "manifest.json" and "__pycache__" not in path.parts:
            manifest_files[path.relative_to(ROOT).as_posix()] = verify.sha256(path)
    write_json(ROOT / "manifest.json", {"schema": "WCPP-R17-SCHEDULE-EVIDENCE-1",
               "source_commit": commit, "files": manifest_files})
    print(json.dumps({"source_commit": commit, "files": len(manifest_files),
                      "forward": forward_report}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "r5", "r7", "r10", "final", "repeat", "forward"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--scope", type=Path)
    args = parser.parse_args()
    if args.scope is None:
        args.scope = args.source / "configs/analysis-scope.json"
    build(args)


if __name__ == "__main__":
    main()
