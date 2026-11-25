#!/usr/bin/env python3
"""Build and check the portable file inventory for the R23 release."""

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHEMA = "r23-evidence-package-manifest-v1"
INVENTORY_FILES = {"manifest.json", "SHA256SUMS"}


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def file_hashes(root):
    hashes = {}
    for path in root.rglob("*"):
        if path.is_file():
            hashes[path.relative_to(root).as_posix()] = sha(path)
    return dict(sorted(hashes.items()))


def tree_sha(hashes):
    return hashlib.sha256(json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def inventories(root):
    files = {name: digest for name, digest in file_hashes(root).items() if name not in INVENTORY_FILES}
    manifest = (json.dumps({"schema": SCHEMA, "files": files}, indent=2) + "\n").encode()
    sums = "".join(f"{digest}  {name}\n" for name, digest in files.items()).encode()
    return {"manifest.json": manifest, "SHA256SUMS": sums}


def verify(root):
    expected = json.loads((root / "manifest.json").read_bytes())
    actual = json.loads(inventories(root)["manifest.json"])
    if actual != expected:
        left, right = actual["files"], expected["files"]
        differing = [name for name in sorted(left.keys() | right.keys()) if left.get(name) != right.get(name)]
        raise ValueError(f"R23 package inventory differs: {differing[:20]}")
    checksum_list = "".join(f"{digest}  {name}\n" for name, digest in actual["files"].items()).encode()
    if (root / "SHA256SUMS").read_bytes() != checksum_list:
        raise ValueError("R23 package SHA256SUMS differs")


if __name__ == "__main__":
    for name, data in inventories(HERE).items():
        (HERE / name).write_bytes(data)
