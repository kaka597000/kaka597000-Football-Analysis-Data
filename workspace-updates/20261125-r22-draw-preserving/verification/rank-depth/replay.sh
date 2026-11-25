#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  printf 'Usage %s SOURCE_CHECKOUT\n' "$0" >&2
  exit 2
fi

source_checkout=$(cd -- "$1" && pwd)
diagnostic=$(cd -- "$(dirname -- "$0")" && pwd)
data_checkout=$(git -C "$diagnostic" rev-parse --show-toplevel)
scratch=$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/r22-rank-depth.XXXXXX")
trap 'rm -rf -- "$scratch"' EXIT

mkdir "$scratch/data"
git -C "$data_checkout" archive 64efb374fb598b39c1c14048573c3e8754633c76 -- \
  workspace-updates/20261123-all-scope-kpi \
  workspace-updates/20261123-prematch-literature \
  workspace-updates/20261125-r21-score-dependence \
  workspace-updates/20261125-r22-draw-preserving | tar -xf - -C "$scratch/data"

for mode in history forward; do
  PYTHONHASHSEED=0 python -B "$diagnostic/rank_depth.py" "$mode" \
    --source "$source_checkout" --data-root "$scratch/data" --out-dir "$scratch/$mode"
  for file in summary.json by-league.csv fixtures.csv; do
    cmp "$diagnostic/$mode/$file" "$scratch/$mode/$file"
  done
done

python -B - "$diagnostic/matrix-jsonl-sha256.txt" "$scratch" <<'PY'
import gzip
import hashlib
import sys
from pathlib import Path

checksums, rebuilt = map(Path, sys.argv[1:])
expected = {}
for line in checksums.read_text(encoding="ascii").splitlines():
    digest, name = line.split()
    expected[name] = digest

for mode in ("history", "forward"):
    name = f"{mode}/r7-grids.jsonl"
    with gzip.open(rebuilt / f"{name}.gz", "rb") as matrix:
        actual = hashlib.file_digest(matrix, "sha256").hexdigest()
    if actual != expected[name]:
        raise SystemExit(f"Matrix JSONL SHA-256 differs for {mode}")
    print(f"Verified {name} SHA-256 {actual}")
PY
