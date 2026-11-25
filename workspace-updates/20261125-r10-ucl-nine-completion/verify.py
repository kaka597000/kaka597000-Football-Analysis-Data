#!/usr/bin/env python3
"""Verify the immutable R10 nine-fixture supplemental registration and original evidence."""
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
R10 = REPO / "workspace-updates/20261125-r10-shot-conversion"
REG = json.loads((ROOT / "registration.json").read_text(encoding="utf-8"))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical_digest(value):
    return sha(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                         allow_nan=False).encode("utf-8"))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_tar_json(archive, member):
    with tarfile.open(archive, "r:gz") as tar:
        return json.load(tar.extractfile(member))


def verify_parent_r10():
    spec = importlib.util.spec_from_file_location("r10_parent_verifier", R10 / "verify.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    files = module.verify_files()
    rows = module.verify_replay()
    forwards = module.verify_forward()
    return {"parent_files": files, "replay_rows": rows, "forward_first_issues": forwards}


def verify():
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    manifest_files = manifest.get("files", {})
    actual_files = {p.relative_to(ROOT).as_posix(): sha(p.read_bytes())
                    for p in ROOT.rglob("*") if p.is_file() and p.name != "manifest.json"}
    require(manifest.get("schema") == "R10-UCL-NINE-SUPPLEMENT-1" and
            manifest_files == actual_files, "supplement package manifest differs")
    reg_path = ROOT / "registration.json"
    expected_sha = (ROOT / "registration.sha256").read_text(encoding="ascii").split()[0]
    require(sha(reg_path.read_bytes()) == expected_sha, "immutable registration SHA differs")
    require(REG["schema"] == "R10-UCL-NINE-SUPPLEMENT-REGISTRATION-1", "schema differs")
    require(REG["parent_pull_request"] == 47 and REG["parent_head_at_registration"] ==
            "c17f983d279c64518ccb2392465fdf66e3f0bdbb", "R10 parent pin differs")
    require(REG["no_new_forecast_or_top3_created"] is True, "registration must not create forecasts")
    require(len(REG["slots"]) == 9 and len({s["match_id"] for s in REG["slots"]}) == 9,
            "nine unique fixture slots required")
    parent = verify_parent_r10()

    first_archive = R10 / "forward/first-issues.tar.gz"
    with tarfile.open(first_archive, "r:gz") as tar:
        first_receipts = json.load(tar.extractfile("receipts.json"))
        source_records = first_receipts["matches"]

    fixture_rows = list(csv.DictReader(io.StringIO(load_archive_text(
        R10 / "formal/nov26-ucl-three.tar.gz", "evidence/espn-nine-fixtures.csv"))))
    ranking_rows = list(csv.DictReader(io.StringIO(load_archive_text(
        R10 / "formal/nov26-ucl-three.tar.gz", "evidence/r10-nine-match-ranking.csv"))))
    firsts = json.loads((R10 / "formal/nov26-ucl-firsts.json").read_text(encoding="utf-8"))
    selected = {item["match_id"]: item for item in firsts["selections"]}
    require(len(fixture_rows) == len(ranking_rows) == 9, "source slate is not nine fixtures")
    require([s["match_id"].removeprefix("espn:") for s in REG["slots"]] ==
            [r["event_id"] for r in ranking_rows], "registration rank order differs from frozen ranking")
    fixture_map = {row["ESPN ID"]: row for row in fixture_rows}
    for i, (slot, ranking) in enumerate(zip(REG["slots"], ranking_rows), 1):
        eid = slot["match_id"].removeprefix("espn:")
        fixture = fixture_map[eid]
        original_ref = source_records[slot["match_id"]]
        original_raw = load_archive_bytes(first_archive, original_ref["file"])
        original = json.loads(original_raw)
        require(slot["rank_in_nine"] == i and slot["home_name"] == fixture["Home"] and
                slot["away_name"] == fixture["Away"] and slot["ranking_source"]["score"] == ranking["score"] and
                slot["ranking_source"]["p_first"] == float(ranking["p_first"]),
                f"fixture/ranking mismatch: {slot['match_id']}")
        require(sha(original_raw) == slot["r10_forward_issue"]["raw_file_sha256"] and
                original["freeze_id"] == slot["r10_forward_issue"]["freeze_id"] and
                original["recorded_at"] == slot["r10_forward_issue"]["recorded_at"] and
                original["record_sha256"] == slot["r10_forward_issue"]["record_sha256"] == original_ref["sha256"] and
                original["match_id"] == slot["match_id"] and
                original["payload"]["quality"]["p_first"] == slot["ranking_source"]["p_first"] and
                original["payload"]["forecasts"]["candidate"]["primary"] == slot["ranking_source"]["score"],
                f"R10 live model source mismatch: {slot['match_id']}")
        if slot["match_id"] in selected:
            item = selected[slot["match_id"]]
            ref = slot["comprehensive_first_issue"]
            require(ref and ref["status"] == "already-issued" and slot["original_seat"] == item["rank"] and
                    ref["freeze_id"] == item["comprehensive_reference"]["freeze_id"] and
                    ref["reference_sha256"] == item["comprehensive_reference"]["sha256"],
                    f"original selected seat changed: {slot['match_id']}")
        else:
            require(slot["comprehensive_first_issue"] is None and slot["original_seat"] is None and
                    slot["status"] == "NOT_ISSUED_AT_REGISTRATION" and slot["unissued_reason"],
                    f"unissued slot was filled or substituted: {slot['match_id']}")

    public = REG["public_source"]
    raw_scoreboard = load_archive_bytes(R10 / "formal/nov26-ucl-three.tar.gz", public["raw_archive_member"])
    require(sha(raw_scoreboard) == public["raw_sha256"], "public scoreboard raw SHA differs")
    scoreboard = json.loads(raw_scoreboard)
    ids = {str(event["id"]) for day in scoreboard.get("events", []) for event in [day]}
    require({s["match_id"].removeprefix("espn:") for s in REG["slots"]}.issubset(ids),
            "ESPN scoreboard does not contain all registered fixtures")

    for item in REG["inputs"]:
        path = REPO / item["path"] if not item["path"].startswith("/") else None
        if path is not None:
            require(path.is_file() and sha(path.read_bytes()) == item["sha256"],
                    f"embedded source digest differs: {item['name']}")
    return {"status": "PASS", "registration_sha256": expected_sha,
            "fixtures": 9, "original_selected_seats": 3, "unissued_comprehensive_slots": 6,
            **parent}


def load_archive_bytes(archive, member):
    with tarfile.open(archive, "r:gz") as tar:
        return tar.extractfile(member).read()


def load_archive_text(archive, member):
    return load_archive_bytes(archive, member).decode("utf-8")


if __name__ == "__main__":
    print(json.dumps(verify(), ensure_ascii=False, indent=2))
