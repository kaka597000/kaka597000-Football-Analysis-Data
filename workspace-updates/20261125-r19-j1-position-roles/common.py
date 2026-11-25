"""Deterministic helpers for the R19 J1 position evidence package."""

import gzip
import hashlib
import json
import math
import csv
import re
from pathlib import Path

SOURCE_COMMIT = "f17c40be7a611998db3b755c65c1d2ebb1f39dc8"
R15_SOURCE_COMMIT = "993686077a360705fb02c0667de96fc32b590e3b"
R19_PROTOCOL_SHA256 = "79c475cc0311ddc605071bd579103c91c6e41e9fc89f773e7f30a6248adfe3ef"
R15_BUNDLE_SHA256 = "f56f8308cb3741e17340ecb6802579d401b6280b98feb24773f506fdf1bad7f7"
R15_RECEIPTS_SHA256 = "6ee26b469e23febecde863caf0f4f07bcf96b5e42362a4ed66a7e3400e86bb52"
R19_REGISTRATION_ID = "5b57e12c31bd8634-v000001"
R19_REGISTRATION_SHA256 = "1eeebfe6c0e0e11d4144500919fe570fafaa4fb80fba8ce4daa57a0342217ce1"
R19_RECORDED_AT = "2026-11-25T19:41:38.627109+08:00"
ATOL = 1e-9
RTOL = 1e-7
NUMERICAL_VERSIONS = {"numpy": "2.3.5", "scipy": "1.17.0", "lightgbm": "4.6.0"}
NUMERICAL_ENV = {"NPY_DISABLE_CPU_FEATURES": "AVX512F", "OPENBLAS_CORETYPE": "Haswell",
                 "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(body):
    return hashlib.sha256(body).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                          encoding="utf-8")


def inventory(root):
    root = Path(root)
    return {p.relative_to(root).as_posix(): sha(p) for p in sorted(root.rglob("*")) if p.is_file()}


def read_value(path):
    path = Path(path)
    if path.name.endswith(".jsonl.gz"):
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            return [json.loads(line) for line in stream if line.strip()]
    if path.suffix == ".json":
        return read_json(path)
    if path.suffix == ".csv":
        def scalar(value):
            if value == "":
                return None
            if value == "True":
                return True
            if value == "False":
                return False
            if value[:1] in ("[", "{"):
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    pass
            if re.fullmatch(r"-?(0|[1-9][0-9]*)", value):
                return int(value)
            try:
                return float(value)
            except ValueError:
                return value
        with path.open("r", encoding="utf-8", newline="") as stream:
            return [{key: scalar(value) for key, value in row.items()} for row in csv.DictReader(stream)]
    return path.read_bytes()


def same_value(a, b, where="$", atol=ATOL, rtol=RTOL):
    if isinstance(a, bool) or isinstance(b, bool):
        ok = type(a) is type(b) and a == b
        return ok, None if ok else f"{where}: boolean differs"
    if isinstance(a, dict) or isinstance(b, dict):
        if not isinstance(a, dict) or not isinstance(b, dict) or set(a) != set(b):
            return False, f"{where}: object keys differ"
        for key in a:
            ok, why = same_value(a[key], b[key], f"{where}.{key}", atol, rtol)
            if not ok:
                return ok, why
        return True, None
    if isinstance(a, list) or isinstance(b, list):
        if not isinstance(a, list) or not isinstance(b, list) or len(a) != len(b):
            return False, f"{where}: list length differs"
        for i, (x, y) in enumerate(zip(a, b)):
            ok, why = same_value(x, y, f"{where}[{i}]", atol, rtol)
            if not ok:
                return ok, why
        return True, None
    if type(a) is int or type(b) is int:
        ok = type(a) is int and type(b) is int and a == b
        return ok, None if ok else f"{where}: discrete integer differs ({a!r} vs {b!r})"
    if isinstance(a, float) and isinstance(b, float):
        if not math.isfinite(float(a)) or not math.isfinite(float(b)) or not math.isclose(a, b, abs_tol=atol, rel_tol=rtol):
            return False, f"{where}: numeric differs ({a!r} vs {b!r})"
        return True, None
    ok = type(a) is type(b) and a == b
    return ok, None if ok else f"{where}: value differs ({a!r} vs {b!r})"


def compare_trees(left, right, *, exact=False):
    left, right = Path(left), Path(right)
    li, ri = inventory(left), inventory(right)
    if set(li) != set(ri):
        raise ValueError(f"artifact file inventories differ: left={len(li)}, right={len(ri)}")
    if exact:
        if li != ri:
            raise ValueError("same-host independent output files are not byte-identical")
        return
    for root in (left, right):
        recipe_path = root / "forward.json"
        fit_path, inputs_path = root / "fit.json", root / "inputs.json"
        if recipe_path.is_file() and fit_path.is_file() and inputs_path.is_file():
            recipe = read_json(recipe_path)
            if recipe.get("fit_sha256") != sha(fit_path) or recipe.get("study_inputs_sha256") != sha(inputs_path):
                raise ValueError(f"{root}: forward recipe does not bind its own fit and inputs")
    for name in sorted(li):
        a, b = read_value(left / name), read_value(right / name)
        if name == "forward.json" and isinstance(a, dict) and isinstance(b, dict):
            a, b = dict(a), dict(b)
            a.pop("fit_sha256", None)
            b.pop("fit_sha256", None)
        ok, why = same_value(a, b, name)
        if not ok:
            raise ValueError(f"cross-run artifact mismatch: {why}")


def flatten(value, prefix=""):
    out = {}
    if isinstance(value, dict):
        for key, child in value.items():
            out.update(flatten(child, f"{prefix}.{key}" if prefix else key))
    elif isinstance(value, list):
        out[prefix] = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    else:
        out[prefix] = value
    return out
