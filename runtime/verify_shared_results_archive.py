"""Verify the retained November 19 evidence offline, without running the older models."""

from datetime import datetime
import gzip
import hashlib
import json
from pathlib import Path
import re


ARCHIVE = Path(__file__).resolve().parents[1] / "workspace-updates/20261119-shared-results"
MANIFEST_SHA256 = "8f1aaf3fd4122d6f99de902dd6c6e5366791491ac0c550342b3ddb801e57c35b"


def verify(archive=ARCHIVE):
    manifest_bytes = (archive / "manifest.json").read_bytes()
    if hashlib.sha256(manifest_bytes).hexdigest() != MANIFEST_SHA256:
        raise ValueError("historical manifest checksum mismatch")
    manifest = json.loads(manifest_bytes)
    files = {p.relative_to(archive).as_posix() for p in archive.rglob("*") if p.is_file()}
    if files != set(manifest) | {"manifest.json"}:
        raise ValueError("archive inventory differs from the historical manifest")
    for name, expected in manifest.items():
        if hashlib.sha256((archive / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"historical member checksum mismatch: {name}")

    for path in sorted(archive.rglob("validation.json")):
        record = json.loads(path.read_bytes())
        if (record["before"] != record["after"] or len(record["before"]) != record["protected_count"]
                or not record["protected_old_and_rsi_unchanged"]):
            raise ValueError(f"inconsistent protected inventory in {path.name}")
        for run in record["runs"]:
            log = gzip.decompress((path.parent / (run["name"] + ".log.gz")).read_bytes()).decode()
            tests = sum(map(int, re.findall(r"^Ran (\d+) tests? in ", log, re.MULTILINE)))
            skips = sum(map(int, re.findall(r"^OK \(skipped=(\d+)\)$", log, re.MULTILINE)))
            if (tests != run["tests"] or skips != run["skips"] or run["exit_code"] != 0
                    or datetime.fromisoformat(run["start"]) > datetime.fromisoformat(run["end"])):
                raise ValueError(f"run metadata disagrees with {run['name']}")
            print(f"{record['source_commit']} {run['name']}: {tests} historical tests, {skips} skips")
    print(f"Verified {len(manifest)} retained files and their original logs.")


if __name__ == "__main__":
    verify()
