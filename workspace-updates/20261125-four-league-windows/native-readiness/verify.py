#!/usr/bin/env python3
"""Offline, portable cross-check of the archived two-pass native receipts."""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import tarfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
WINDOW_ROOT = HERE.parent
ARCHIVE = HERE / "europe-native-readiness-de2fbd292081209a.tar.gz"
ARCHIVE_SHA256 = "de2fbd292081209afda55ec6e447ff813ffdc270c8f2f9c6bd24f8c7cc7b477c"
LEAGUES = ("esp.1", "fra.1", "ger.1", "ita.1")
ROLES = ("current", "test")


def fail(message: str) -> None:
    raise SystemExit("FAIL: " + message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        fail("execution receipt has a naive timestamp")
    return parsed.astimezone(timezone.utc)


def canonical_record_hash(record: dict) -> str:
    unsigned = dict(record)
    unsigned.pop("record_sha256", None)
    encoded = json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return digest(encoded)


def read_archive() -> dict[str, bytes]:
    raw = ARCHIVE.read_bytes()
    if digest(raw) != ARCHIVE_SHA256:
        fail("readiness archive SHA-256 changed")
    files: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        for member in archive.getmembers():
            if not member.isfile() or member.name.startswith("/") or ".." in Path(member.name).parts:
                fail("unsafe or unexpected archive member: " + member.name)
            stream = archive.extractfile(member)
            if stream is None:
                fail("cannot read archive member: " + member.name)
            files[member.name] = stream.read()
    if "SHA256SUMS" not in files:
        fail("archive has no SHA256SUMS")
    listed = {}
    for line in files["SHA256SUMS"].decode().splitlines():
        if not line.strip():
            continue
        value, name = line.split(maxsplit=1)
        listed[name.strip()] = value
    if set(listed) != set(files) - {"SHA256SUMS"}:
        fail("archive checksum inventory differs from members")
    for name, expected in listed.items():
        if digest(files[name]) != expected:
            fail("archive member SHA-256 mismatch: " + name)
    return files


def json_file(files: dict[str, bytes], name: str):
    try:
        return json.loads(files[name])
    except (KeyError, json.JSONDecodeError) as exc:
        fail(f"missing or invalid archive JSON {name}: {exc}")


def load_registration(code: str, league_manifest: dict):
    ref = league_manifest["registration"]
    folder = WINDOW_ROOT / code / "registration"
    matches = list(folder.glob(ref["id"] + ".json"))
    if len(matches) != 1:
        fail(f"{code}: expected exactly one original registration {ref['id']}")
    path = matches[0]
    body = path.read_bytes()
    if digest(body) != ref["file_sha256"]:
        fail(f"{code}: original registration file hash mismatch")
    record = json.loads(body)
    if record.get("record_sha256") != ref["record_sha256"] or canonical_record_hash(record) != ref["record_sha256"]:
        fail(f"{code}: original registration record hash mismatch")
    if (record.get("freeze_id") != ref["id"] or record.get("track") != ref["track"]
            or record.get("model_promotion") is not False
            or record.get("payload", {}).get("track") != ref["track"].removesuffix("-registration")):
        fail(f"{code}: registration identity or research-only flag mismatch")
    model_inputs = record.get("payload", {}).get("identity", {}).get("model_inputs", {})
    if not model_inputs.get("registry_sha256"):
        fail(f"{code}: registration lacks original model registry binding")
    return record


def verify_weights(code: str, league_manifest: dict, registration: dict, registry: dict) -> None:
    registered_models = registration["payload"]["identity"]["model_inputs"]["native_models"]
    for role in ROLES:
        reference = league_manifest["weights"][role]
        path = WINDOW_ROOT / "model-evidence" / code / f"{role}.json.gz"
        compressed = path.read_bytes()
        if digest(compressed) != reference["archive_sha256"]:
            fail(f"{code}/{role}: retained weight archive hash mismatch")
        raw = gzip.decompress(compressed)
        if digest(raw) != reference["artifact_sha256"]:
            fail(f"{code}/{role}: native weight artifact hash mismatch")
        entry = json.loads(raw)
        reg_key = "Current" if role == "current" else "Test"
        reg_model = registered_models[reg_key]
        if reg_model["sha256"] != digest(raw) or reg_model["version"] != entry.get("version"):
            fail(f"{code}/{role}: original registration weight binding mismatch")
        if entry.get("cohort") != code:
            fail(f"{code}/{role}: weight cohort mismatch")
        registry_entry = registry["models"][code]
        registry_hash = registry_entry["artifact_sha256"] if role == "current" else registry_entry["test_artifact_sha256"]
        if digest(raw) != registry_hash:
            fail(f"{code}/{role}: registry artifact binding mismatch")
        if entry.get("version") != reference["bound_version"]:
            fail(f"{code}/{role}: unexpected native weight version")


def main() -> None:
    files = read_archive()
    manifest = json_file(files, "manifest.json")
    fixture_rows = [json.loads(line) for line in files["fixtures.jsonl"].decode().splitlines() if line.strip()]
    passes = [json_file(files, "execution.json"), json_file(files, "repeat-execution.json")]
    if manifest.get("schema") != "europe-native-readiness-v1":
        fail("unexpected package schema")
    if manifest.get("total", {}).get("matches") != 40 or manifest["total"].get("clubs") != 76:
        fail("package does not declare the 40-match / 76-club scope")
    if len(fixture_rows) != 40:
        fail("expected 40 archived fixture evidence rows")

    registry_path = WINDOW_ROOT / "model-evidence" / "registry.json"
    registry_bytes = registry_path.read_bytes()
    if digest(registry_bytes) != manifest["registry_sha256"]:
        fail("original model registry hash mismatch")
    registry = json.loads(registry_bytes)

    registration_ids: set[str] = set()
    registration_by_code = {}
    league_id_sets = {}
    for code in LEAGUES:
        if code not in manifest["leagues"]:
            fail("missing league in evidence manifest: " + code)
        block = manifest["leagues"][code]
        record = load_registration(code, block)
        registration_by_code[code] = record
        registered_registry_sha = record["payload"]["identity"]["model_inputs"]["registry_sha256"]
        if registered_registry_sha != manifest["registry_sha256"]:
            fail(f"{code}: registration registry binding mismatch")
        registrations = record.get("payload", {}).get("fixtures", {})
        if not registrations:
            fail(f"{code}: registration has no frozen fixture payload")
        ids = set(registrations)
        if len(ids) < block.get("counts", {}).get("matches"):
            fail(f"{code}: original registration is missing first-window fixtures")
        league_id_sets[code] = ids
        if registration_ids & ids:
            fail(f"duplicate match IDs across original registrations: {registration_ids & ids}")
        registration_ids |= ids
        verify_weights(code, block, record, registry)

    if len({row.get("match_id") for row in fixture_rows}) != 40:
        fail("archived fixture evidence does not contain 40 unique IDs")
    fixture_ids = {row["match_id"] for row in fixture_rows}
    if not fixture_ids <= registration_ids:
        fail("archive includes IDs absent from the original registrations")

    by_id = {row["match_id"]: row for row in fixture_rows}
    for code, registered_ids in league_id_sets.items():
        window_rows = [row for row in fixture_rows if row.get("competition") == code]
        if len(window_rows) != manifest["leagues"][code]["counts"]["matches"]:
            fail(f"{code}: archived first-window fixture count mismatch")
        for row in window_rows:
            match_id = row["match_id"]
            if match_id not in registered_ids:
                fail(f"{match_id}: not present in original registration")
            block = manifest["leagues"][code]
            reg = registration_by_code[code]
            if (row.get("competition") != code or row.get("registration_id") != reg["freeze_id"]
                    or row.get("registration_sha256") != reg["record_sha256"]):
                fail(f"{match_id}: fixture-to-registration identity differs")
            if row.get("registry_sha256") != manifest["registry_sha256"]:
                fail(f"{match_id}: fixture registry binding differs")
            registered_fixture = reg["payload"]["fixtures"][match_id]
            if (registered_fixture.get("match_id") != match_id
                    or registered_fixture.get("cohort") != code
                    or registered_fixture.get("stage") != "regular"
                    or registered_fixture.get("home") != row.get("teams", {}).get("home")
                    or registered_fixture.get("away") != row.get("teams", {}).get("away")
                    or parse_utc(registered_fixture.get("kickoff_at")) != parse_utc(row.get("kickoff_utc"))):
                fail(f"{match_id}: teams or kickoff differ from original registration")
            if row.get("status") != "SUCCESS":
                fail(f"{match_id}: fixture status is not SUCCESS")
            roles = row.get("roles", {})
            if set(roles) != set(ROLES):
                fail(f"{match_id}: missing Current/Test execution proof")
            for role in ROLES:
                proof = roles[role]
                ref = block["weights"][role]
                if (proof.get("status") != "SUCCESS" or proof.get("matrix_valid") is not True
                        or proof.get("prior_sides") != []):
                    fail(f"{match_id}/{role}: failure, prior fallback, or invalid matrix recorded")
                if proof.get("artifact_sha256") != ref["artifact_sha256"]:
                    fail(f"{match_id}/{role}: bound artifact differs from retained original weight")

    run_summaries = []
    for run_no, run in enumerate(passes, start=1):
        records = run.get("per_match", [])
        if len(records) != 40 or {r.get("match_id") for r in records} != fixture_ids:
            fail(f"execution pass {run_no}: not exactly the same 40 registered IDs")
        if len({r.get("match_id") for r in records}) != 40:
            fail(f"execution pass {run_no}: duplicate per-match execution record")
        if run.get("manifest_sha256") != digest(files["manifest.json"]):
            fail(f"execution pass {run_no}: manifest digest mismatch")
        pass_start = parse_utc(run["actual_wall_start_utc"])
        pass_end = parse_utc(run["actual_wall_end_utc"])
        if pass_end <= pass_start:
            fail(f"execution pass {run_no}: invalid wall-clock interval")
        for receipt in records:
            mid = receipt["match_id"]
            if receipt.get("fixture_sha256") != by_id[mid].get("fixture_sha256"):
                fail(f"execution pass {run_no}/{mid}: fixture binding mismatch")
            if receipt.get("roles") != {"current": "SUCCESS", "test": "SUCCESS"}:
                fail(f"execution pass {run_no}/{mid}: both roles did not succeed")
            clocks = receipt.get("native_generated_at", {})
            if set(clocks) != set(ROLES) or not all(clocks.values()):
                fail(f"execution pass {run_no}/{mid}: missing native role clock")
            match_start = parse_utc(receipt["started_utc"])
            match_end = parse_utc(receipt["ended_utc"])
            if not (pass_start <= match_start <= match_end <= pass_end):
                fail(f"execution pass {run_no}/{mid}: per-match clock outside run interval")
            for role_clock in clocks.values():
                native_time = parse_utc(role_clock)
                if not (match_start <= native_time <= match_end):
                    fail(f"execution pass {run_no}/{mid}: native timestamp outside per-match interval")
        run_summaries.append({"pass": run_no, "start_utc": run.get("actual_wall_start_utc"),
                              "end_utc": run.get("actual_wall_end_utc"), "fixture_ids": len(records),
                              "role_receipts": sum(len(r["roles"]) for r in records)})

    if parse_utc(passes[0]["actual_wall_end_utc"]) >= parse_utc(passes[1]["actual_wall_start_utc"]):
        fail("the two execution passes are not separate chronological runs")
    print(json.dumps({"status": "PASS", "registrations": len(LEAGUES), "unique_fixture_ids": len(fixture_ids),
                      "distinct_clubs": 76, "weight_artifacts_verified": len(LEAGUES) * len(ROLES),
                      "fixture_role_pairs_per_pass": 80, "prior_or_fallback_receipts": 0,
                      "runs": run_summaries}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
