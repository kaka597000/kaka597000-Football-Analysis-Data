"""Shared deterministic helpers for the R18 J1 cutoff evidence package."""

import gzip
import hashlib
from importlib import metadata
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

ATOL = 1e-9
RTOL = 1e-7
SOURCE_COMMIT = "102e4c5b4b9e3897c36686a227374d36a68c484b"
PROTOCOL_SHA256 = "b639ff78f360e4f7ad458b3df285cb0253ee164ea8524cb6c9ee0c4a4755d915"
R15_SLUG = "20261125-r15-j1-lineups"
R15_MANIFEST = "97a3cdc153035f4c1bea4f292cbb5a2cec7351deec2cbf4c92f199ec4f09f243"
ENV = {
    "NPY_DISABLE_CPU_FEATURES": "AVX512F",
    "OPENBLAS_CORETYPE": "Haswell",
    "OPENBLAS_NUM_THREADS": "1",
    "OMP_NUM_THREADS": "1",
}
NUMERICAL_VERSIONS = {"numpy": "2.3.5", "scipy": "1.17.0", "lightgbm": "4.6.0"}


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def json_read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def json_write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                          encoding="utf-8")


def inventory(root):
    root = Path(root)
    return {p.relative_to(root).as_posix(): sha(p) for p in sorted(root.rglob("*")) if p.is_file()}


def check_r15(package, final_inventory, roster_sha, snapshot_sha):
    if sha(package / "manifest.json") != R15_MANIFEST:
        raise ValueError("published R15 manifest differs")
    manifest = json_read(package / "manifest.json")
    files = inventory(package)
    files.pop("manifest.json")
    if files != manifest["files"] or inventory(package / "replay") != final_inventory:
        raise ValueError("R15 package or original eight-file replay differs from its publication")
    inputs = json_read(package / "replay/inputs.json")
    if (roster_sha, snapshot_sha) != (manifest["rosters_sha256"], inputs["roster_manifest_sha256"]):
        raise ValueError("R15 roster bytes or snapshot clock differ from the published fit")


def plain_rosters(path, tmp):
    if path.suffix != ".gz":
        return path
    directory = tmp / "rosters"
    directory.mkdir()
    output = directory / "events.jsonl"
    with gzip.open(path, "rb") as source, output.open("xb") as target:
        shutil.copyfileobj(source, target)
    shutil.copyfile(path.parent / "snapshot-manifest.json", directory / "snapshot-manifest.json")
    return output


def replay_twice(source, commit, tmp, r5, r7, study, rosters):
    actual = subprocess.check_output(["git", "-C", str(source), "rev-parse", "--verify", commit + "^{commit}"],
                                     text=True).strip()
    if actual != commit or commit != SOURCE_COMMIT:
        raise ValueError("R18 numerical source pin differs")
    if sys.version_info[:2] != (3, 12) or any(metadata.version(k) != v for k, v in NUMERICAL_VERSIONS.items()):
        raise RuntimeError(f"R18 requires Python 3.12 and {NUMERICAL_VERSIONS}")
    code = tmp / "source"
    archive = tmp / "source.tar"
    with archive.open("xb") as stream:
        subprocess.run(["git", "-C", str(source), "archive", commit, "runtime", "research/20261125-r18-j1-cutoff"],
                       stdout=stream, check=True)
    with tarfile.open(archive) as tar:
        tar.extractall(code, filter="data")
    if sha(code / "research/20261125-r18-j1-cutoff/protocol.json") != PROTOCOL_SHA256:
        raise ValueError("pinned R18 registration protocol differs")
    env = dict(os.environ, **ENV, PYTHONHASHSEED="0", PYTHONDONTWRITEBYTECODE="1",
               PYTHONPATH=str(code / "runtime"), MPLCONFIGDIR=str(tmp / "mpl"))
    first, second = tmp / "run-1", tmp / "run-2"
    for out in (first, second):
        subprocess.run([sys.executable, "-B", "-m", "research_program.lineup_cutoff",
                        "--r5", str(r5.resolve()), "--r7", str(r7.resolve()), "--study", str(study.resolve()),
                        "--rosters", str(rosters.resolve()), "--out", str(out)], cwd=tmp, env=env, check=True)
    compare_trees(first, second, exact_bytes=True)
    return first


def read_value(path):
    path = Path(path)
    if path.name.endswith(".jsonl.gz"):
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            return [json.loads(line) for line in stream if line.strip()]
    if path.suffix == ".json":
        return json_read(path)
    return path.read_bytes()


def compare_value(a, b, where="$", atol=ATOL, rtol=RTOL):
    if type(a) is not type(b):
        return False, f"{where}: type differs ({type(a).__name__} vs {type(b).__name__})"
    if isinstance(a, dict):
        if not isinstance(b, dict) or set(a) != set(b):
            return False, f"{where}: object keys differ"
        for key in a:
            ok, why = compare_value(a[key], b[key], f"{where}.{key}", atol, rtol)
            if not ok:
                return ok, why
        return True, None
    if isinstance(a, list):
        if not isinstance(b, list) or len(a) != len(b):
            return False, f"{where}: list length differs"
        for i, (x, y) in enumerate(zip(a, b)):
            ok, why = compare_value(x, y, f"{where}[{i}]", atol, rtol)
            if not ok:
                return ok, why
        return True, None
    if isinstance(a, float):
        if not math.isfinite(float(a)) or not math.isfinite(float(b)) or not math.isclose(a, b, abs_tol=atol, rel_tol=rtol):
            return False, f"{where}: numeric value differs ({a!r} vs {b!r})"
        return True, None
    return (a == b), (None if a == b else f"{where}: value differs ({a!r} vs {b!r})")


def compare_trees(left, right, exact_bytes=False):
    left, right = Path(left), Path(right)
    li, ri = inventory(left), inventory(right)
    if set(li) != set(ri):
        raise ValueError(f"artifact inventories differ: left-only={sorted(set(li)-set(ri))[:5]}, "
                         f"right-only={sorted(set(ri)-set(li))[:5]}")
    if exact_bytes:
        if li != ri:
            raise ValueError("same-machine independent outputs are not byte-identical")
        return
    for name in sorted(li):
        if li[name] == ri[name]:
            continue
        ok, reason = compare_value(read_value(left / name), read_value(right / name), name)
        if not ok:
            raise ValueError(f"artifact mismatch: {reason}")
