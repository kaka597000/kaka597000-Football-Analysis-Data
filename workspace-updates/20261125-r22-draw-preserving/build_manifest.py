#!/usr/bin/env python3
"""Write a portable SHA-256 file inventory for this release package."""

import hashlib, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXCLUDED = {"manifest.json", "SHA256SUMS"}


def files():
    return {
        p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(ROOT.rglob("*"))
        if p.is_file()
        and p.relative_to(ROOT).as_posix() not in EXCLUDED
        and "__pycache__" not in p.parts
        and p.suffix not in (".pyc", ".pyo")
    }


def main():
    inventory = files()
    (ROOT / "manifest.json").write_text(
        json.dumps({"schema": "r22-evidence-package-manifest-v1", "files": inventory}, indent=2) + "\n",
        encoding="utf-8",
    )
    (ROOT / "SHA256SUMS").write_text(
        "".join(f"{digest}  {name}\n" for name, digest in inventory.items()), encoding="utf-8"
    )
    print(f"wrote {len(inventory)} file hashes")


if __name__ == "__main__":
    main()
