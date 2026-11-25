#!/usr/bin/env python3
"""Rebuild the R15 raw roster and run two isolated R19 position fits."""

import json
from pathlib import Path
import shutil
import sys
import tempfile
import tarfile


def main():
    (r15_package, data_root, runtime, work_root, r5, r7, r10,
     first_output, second_output, manifest_path) = map(Path, sys.argv[1:])
    outputs = (first_output, second_output)
    sys.path.insert(0, str(r15_package))
    import verify as r15_verify
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    original_inputs = json.loads((r15_package / "replay/inputs.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="r19-roster-rebuild-") as scratch:
        training, slots, _, counts = r15_verify.reconstruct(r15_package, data_root, Path(scratch))
        if (len(slots) != 2822 or counts["fixture_slots"] != 2822
                or r15_verify.sha(training) != manifest["rosters_sha256"]
                or r15_verify.rows(r15_package / "normalized-starters.jsonl.gz") != slots):
            raise ValueError("R15 raw archive did not independently rebuild its registered 2,822-row roster")
        rebuilt = work_root / "r15-roster-rebuilt.jsonl"
        shutil.copyfile(training, rebuilt)
        with tarfile.open(r15_package / "intake.tar.gz", "r:gz") as archive:
            snapshot = archive.extractfile("snapshot-manifest.json").read()
        snapshot_path = work_root / "snapshot-manifest.json"
        snapshot_path.write_bytes(snapshot)
        if __import__("hashlib").sha256(snapshot).hexdigest() != original_inputs["roster_manifest_sha256"]:
            raise ValueError("raw R15 snapshot manifest hash differs from frozen fit inputs")

    sys.path.insert(0, str(runtime))
    from research_program.lineup_position_study import run
    for destination in outputs:
        run(r5, r7, r10, r15_package / "replay", rebuilt, destination)
    print(json.dumps({"r15_roster_rows": 2822, "r15_roster_sha256": manifest["rosters_sha256"],
                      "r19_runs": [str(p) for p in outputs]}, sort_keys=True))


if __name__ == "__main__":
    main()
