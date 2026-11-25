#!/usr/bin/env python3
"""Verify the immutable R10 nine-fixture supplemental registration and original evidence."""
import csv
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
from datetime import datetime, timezone

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
    evidence_archive = R10 / "formal/nov26-ucl-three.tar.gz"
    raw_scoreboard = load_archive_bytes(evidence_archive, public["raw_archive_member"])
    require(sha(raw_scoreboard) == public["raw_sha256"], "public scoreboard raw SHA differs")
    scoreboard = json.loads(raw_scoreboard)
    ids = {str(event["id"]) for day in scoreboard.get("events", []) for event in [day]}
    require({s["match_id"].removeprefix("espn:") for s in REG["slots"]}.issubset(ids),
            "ESPN scoreboard does not contain all registered fixtures")
    request_log = json.loads(load_archive_bytes(evidence_archive, "evidence/request-log.json"))
    scoreboard_request = next(row for row in request_log if row["name"] == public["request_name"])
    require(scoreboard_request["url"] == public["url"] and
            scoreboard_request["accessed_at_utc"] == public["accessed_at_utc"] and
            scoreboard_request["status"] == public["http_status"] and
            scoreboard_request["sha256"] == public["raw_sha256"],
            "public schedule source time or receipt differs")

    live_index = json.loads((ROOT / "current-test-live-supplement.json").read_text(encoding="utf-8"))
    live_archive = ROOT / live_index["source_archive"]
    require(live_index["schema"] == "R10-UCL-LIVE-PAIRS-1" and
            live_index["registration_sha256"] == expected_sha and
            sha(live_archive.read_bytes()) == live_index["archive_sha256"],
            "live dual-model archive or registration binding differs")
    six_reserved = {s["match_id"] for s in REG["slots"] if s["comprehensive_first_issue"] is None}
    require(live_index["fixture_count"] == 6 and
            {row["match_id"] for row in live_index["entries"]} == six_reserved and
            live_index["contains_comprehensive_first_issues"] is False,
            "live dual-model records must cover the six reserved slots only")
    with tarfile.open(live_archive, "r:gz") as tar:
        members = set(tar.getnames())
        for row in live_index["entries"]:
            indexed = {entry["archive_member"]: entry for entry in row["source_files"]}
            fixture_name = f"live-pairs/{row['match_id'].split(':', 1)[1]}.fixture.json"
            pair_name = f"live-pairs/{row['match_id'].split(':', 1)[1]}.pair.json"
            publication_name = pair_name + ".publication.json"
            require({fixture_name, pair_name, publication_name}.issubset(members),
                    f"live issue archive incomplete: {row['match_id']}")
            for member, detail in indexed.items():
                raw = tar.extractfile(member).read()
                require(sha(raw) == detail["sha256"] and len(raw) == detail["bytes"],
                        f"live original byte hash differs: {member}")
            fixture = json.loads(tar.extractfile(fixture_name).read())
            pair = json.loads(tar.extractfile(pair_name).read())
            publication = json.loads(tar.extractfile(publication_name).read())
            receipt = publication["receipt"]
            require(pair["match_id"] == fixture["match_id"] == row["match_id"] and
                    publication["status"] == "DELIVERED" and
                    receipt["freeze_id"] == row["publication"]["freeze_id"] and
                    receipt["recorded_at"] == row["publication"]["recorded_at"] and
                    receipt["sha256"] == row["publication"]["receipt_sha256"] and
                    receipt["evaluation_slot"] == "SEPARATE_REVISION_OR_STAGE",
                    f"live pair is not the retained separate dual-model issue: {row['match_id']}")
            for track in ("current_model", "test_model"):
                require(track in pair and pair[track]["generated_at"] == row["models"][track]["generated_at"],
                        f"missing or changed model track: {row['match_id']} {track}")
            for source in row["public_sources"]:
                raw = tar.extractfile(source["raw_archive_member"]).read()
                meta = json.loads(tar.extractfile(source["meta_archive_member"]).read())
                require(sha(raw) == source["response_sha256"] == meta["sha256"] ==
                        meta["readback_sha256"] and meta["readback_verified"] is True,
                        f"public input raw response/readback differs: {row['match_id']}")

    verify_nine_canonical_records(expected_sha)
    verify_observed_inputs(expected_sha)
    verify_post_issue_pages(expected_sha)

    ranked_archive = R10 / "forward/ranked.tar.gz"
    archived_sources = {
        "ranked_batch_plan": load_archive_bytes(ranked_archive, "plan.json"),
        "ranked_batch_scorecard": load_archive_bytes(ranked_archive, "scorecard.json"),
        "nine_match_ranking": load_archive_bytes(evidence_archive, "evidence/r10-nine-match-ranking.csv"),
        "nine_fixture_source": load_archive_bytes(evidence_archive, "evidence/espn-nine-fixtures.csv"),
        "original_three_ranked_firsts": load_archive_bytes(evidence_archive, "issuance/ranked-firsts.json"),
        "r10_forward_receipts": load_archive_bytes(first_archive, "receipts.json"),
    }
    for item in REG["inputs"]:
        if item["name"] in archived_sources:
            actual = sha(archived_sources[item["name"]])
        else:
            path = REPO / item["path"]
            require(path.is_file(), f"embedded source is missing: {item['name']}")
            actual = sha(path.read_bytes())
        require(actual == item["sha256"], f"registered source digest differs: {item['name']}")
    first_index = json.loads((ROOT / "nine-firsts-index.json").read_text(encoding="utf-8"))
    market_index = json.loads((ROOT / "same-price-market-index.json").read_text(encoding="utf-8"))
    return {"status": "PASS", "registration_sha256": expected_sha,
            "fixtures": 9, "original_selected_seats": 3,
            "at_registration_unissued": 6,
            "issued_now": len(first_index["rows"]),
            "pending_comprehensive_now": sum(
                s["comprehensive_first_issue"] is None for s in REG["slots"]
                if s["match_id"] not in {r["match_id"] for r in first_index["rows"]}),
            "market_same_price": len(market_index["rows"]),
            **parent}


def verify_nine_canonical_records(registration_sha):
    """Bind all nine genuine first issues and market-only records to archived bytes."""
    first_index = json.loads((ROOT / "nine-firsts-index.json").read_text(encoding="utf-8"))
    market_index = json.loads((ROOT / "same-price-market-index.json").read_text(encoding="utf-8"))
    require(first_index["schema"] == "R10-UCL-NINE-FIRST-ISSUES-1" and
            first_index["registration_sha256"] == registration_sha and
            first_index["conversation_text_display_reported_by_user"] is True and
            first_index["independent_platform_readback_receipt"] == "not included" and
            len(first_index["rows"]) == 9, "nine first-issue index or receipt status differs")
    require(market_index["schema"] == "R10-UCL-SAME-PRICE-MARKETS-1" and
            market_index["registration_sha256"] == registration_sha and
            market_index["same_comprehensive_source_quote"] is True and
            market_index["provider_quote_time_available"] is False and
            len(market_index["rows"]) == 9, "nine same-price market index differs")
    with tarfile.open(ROOT / "canonical-records.tar.gz", "r:gz") as tar:
        names = set(tar.getnames())
        require({"six-firsts.json", "message.txt", "same-price-markets.json"}.issubset(names),
                "canonical archive missing original issue text or source indexes")
        six = json.load(tar.extractfile("six-firsts.json"))
        six_ids = {row["match_id"] for row in six["rows"]}
        six_ids_expected = {s["match_id"] for s in REG["slots"]
                            if s["comprehensive_first_issue"] is None}
        require(six_ids == six_ids_expected and
                six["registration_sha256"] == registration_sha and
                sha(tar.extractfile("message.txt").read()) ==
                "f10ca4a0fd821841334fb7e1827d4d0996d502721176786e8d37892fda7588b6",
                "six actual first issues or original displayed message changed")
        market_exports = json.load(tar.extractfile("same-price-markets.json"))
        require(len(market_exports) == 9, "same-price market exports must cover all nine fixtures")
        by_first = {r["match_id"]: r for r in first_index["rows"]}
        by_market = {r["match_id"]: r for r in market_index["rows"]}
        exports = {r["match_id"]: r for r in market_exports}
        original_first_archive = R10 / "formal/nov26-ucl-three.tar.gz"
        def first_canonical(match_id):
            eid = match_id.split(":", 1)[1]
            member = f"canonical/comprehensive/espn-{eid}.json"
            if member in names:
                return json.load(tar.extractfile(member))
            selected_row = by_first[match_id]
            with tarfile.open(original_first_archive, "r:gz") as original:
                return json.load(original.extractfile(
                    f"canonical/{selected_row['freeze_id']}.json"))
        require(set(by_first) == set(by_market) == set(exports) ==
                {s["match_id"] for s in REG["slots"]}, "nine canonical indexes have different fixture sets")
        for match_id in by_first:
            eid = match_id.split(":", 1)[1]
            first = first_canonical(match_id)
            market = json.load(tar.extractfile(f"canonical/same-price-market/espn-{eid}.json"))
            first_meta, market_meta = by_first[match_id], by_market[match_id]
            payload = first["payload"]
            primary = payload.get("primary", payload.get("forecasts", {}).get("candidate", {}).get("primary"))
            displayed = payload.get("displayed_scores")
            quote = first["fixture"].get("total_quote", payload.get("bookmaker"))
            require(first["match_id"] == market["match_id"] == match_id and
                    first["evaluation_slot"] == market["evaluation_slot"] == "FIRST_PREMATCH" and
                    first["record_sha256"] == first_meta["record_sha256"] and
                    canonical_digest(first) == first_meta["raw_canonical_sha256"] and
                    first["freeze_id"] == first_meta["freeze_id"] and
                    first["recorded_at"] == first_meta["recorded_at"] and
                    payload["authored_display"]["first"] == first_meta["primary"] and
                    displayed == first_meta["displayed_scores"] and primary == first_meta["primary"] and
                    first["fixture"]["kickoff_at"] == first_meta["kickoff_at"],
                    f"comprehensive first canonical differs: {match_id}")
            from datetime import datetime
            issue = datetime.fromisoformat(first["recorded_at"])
            kickoff = datetime.fromisoformat(first["fixture"]["kickoff_at"])
            require(issue < kickoff, f"first issue not pre-kickoff: {match_id}")
            require(market["record_sha256"] == market_meta["record_sha256"] and
                    canonical_digest(market) == market_meta["canonical_raw_sha256"] and
                    market["freeze_id"] == market_meta["freeze_id"] and
                    market["recorded_at"] == market_meta["recorded_at"] and
                    market["payload"]["comprehensive_first_sha256"] == first["record_sha256"] and
                    market["payload"]["source_sha256"] == quote["source_sha256"] and
                    market["fixture"]["total_quote"]["quoted_at"] is None and
                    market["fixture"]["total_quote"]["query_time"] == market_meta["market_source_query_time"] and
                    exports[match_id]["authored_sha"] == first["record_sha256"] and
                    exports[match_id]["market"]["sha256"] == market["record_sha256"] and
                    exports[match_id]["forecast"] == market["payload"]["forecast"],
                    f"same-price market canonical differs or quote was relabeled: {match_id}")
            require(market["recorded_at"] > first["recorded_at"],
                    f"same-price comparison chronology invalid: {match_id}")
        review_rows = list(csv.DictReader((ROOT / "nine-match-review.csv").open(
            encoding="utf-8", newline="")))
        require(len(review_rows) == 9 and {r["match_id"] for r in review_rows} == set(by_first),
                "nine-match review table fixture coverage differs")
        for row in review_rows:
            mid = row["match_id"]
            eid = mid.split(":", 1)[1]
            first = first_canonical(mid)
            market = json.load(tar.extractfile(f"canonical/same-price-market/espn-{eid}.json"))
            slot = next(s for s in REG["slots"] if s["match_id"] == mid)
            fi, mi = by_first[mid], by_market[mid]
            fixture = first["fixture"]
            require(row["home"] == (fixture.get("display_home") or fixture.get("home_display_name")) and
                    row["away"] == (fixture.get("display_away") or fixture.get("away_display_name")) and
                    row["kickoff_utc"] == fixture["kickoff_at"] and
                    row["r10_rank"] == str(slot["rank_in_nine"]) and
                    row["comprehensive_first_id"] == fi["freeze_id"] and
                    row["comprehensive_first_at"] == fi["recorded_at"] and
                    row["comprehensive_primary"] == fi["primary"] and
                    row["same_price_market_id"] == mi["freeze_id"] and
                    row["same_price_market_at"] == mi["recorded_at"] and
                    row["same_price_baseline_primary"] == market["payload"]["forecast"]["primary"] and
                    row["market_quote_clock"] == "query_time only; provider quoted_at absent",
                    f"nine-match review table row differs from source: {mid}")
        # Re-execute the pinned implementation against the exact preserved ESPN response.
        source_pin = json.loads((ROOT / "same-price-market-source-pin.json").read_text())
        require(source_pin["runtime_archive_sha256"] == sha((ROOT / "same-price-market-runtime.tar.gz").read_bytes()) and
                source_pin["script_sha256"] == sha((ROOT / "nov26_same_price_markets.py").read_bytes()),
                "same-price source/runtime pin differs")
        with tempfile.TemporaryDirectory(prefix="r10-market-verify-") as tmp:
            tmp = Path(tmp)
            with tarfile.open(ROOT / "same-price-market-runtime.tar.gz", "r:gz") as runtime:
                runtime.extractall(tmp, filter="data")
            runtime_path = tmp / "runtime"
            for rel, expected in source_pin.get("additional_runtime_files", {}).items():
                require(sha((tmp / rel).read_bytes()) == expected,
                        f"pinned runtime dependency differs: {rel}")
            script = tmp / "nov26_same_price_markets.py"
            source_script = (ROOT / "nov26_same_price_markets.py").read_bytes()
            # The pinned file's CLI imports a writer unrelated to market(); omit that
            # unused import so replay does not load its unrelated CLI dependency tree.
            source_script = source_script.replace(
                b"from research_program.goal_state_study import write_new\n", b"")
            script.write_bytes(source_script)
            sys.path.insert(0, str(runtime_path))
            sys.path.insert(0, str(tmp))
            try:
                spec = importlib.util.spec_from_file_location("r10_pinned_market", script)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                with tarfile.open(ROOT / "observed-inputs.tar.gz", "r:gz") as observed, \
                     tarfile.open(R10 / "formal/nov26-ucl-three.tar.gz", "r:gz") as original:
                    for match_id, first_row in by_first.items():
                        eid = match_id.split(":", 1)[1]
                        first = first_canonical(match_id)
                        if match_id in six_ids_expected:
                            raw = observed.extractfile(f"intake/raw/current/espn-summary-{eid}.json").read()
                        else:
                            raw = original.extractfile(f"evidence/raw/espn-summary-{eid}.json").read()
                        actual = module.market(first, raw)
                        expected = json.load(tar.extractfile(f"canonical/same-price-market/espn-{eid}.json"))["payload"]
                        require(actual == expected, f"pinned market replay differs: {match_id}")
            finally:
                sys.path.remove(str(runtime_path))
                sys.path.remove(str(tmp))


def verify_observed_inputs(registration_sha):
    archive = ROOT / "observed-inputs.tar.gz"
    classification_path = ROOT / "source-time-classification.csv"
    rows = list(csv.DictReader(classification_path.open(encoding="utf-8", newline="")))
    earliest = datetime.fromisoformat("2026-11-25T12:45:40.368501+00:00")
    registered = datetime.fromisoformat("2026-11-25T12:30:35+00:00")
    with tarfile.open(archive, "r:gz") as tar:
        manifest = json.load(tar.extractfile("intake/pre-issue-capture-manifest.json"))
        entries = {Path(r["path"]).name: r for r in manifest["captures"]}
        require(manifest["schema"] == "ucl-other-six-capture-manifest-v1" and
                len(rows) == len(manifest["captures"]) == 142,
                "pre-issue source capture inventory count differs")
        for row in rows:
            is_meta_path = row["path"].endswith(".meta.json")
            if is_meta_path:
                prefix = row["path"][:-10]
                body_rel = prefix if prefix.endswith(".json") else prefix + ".json"
            else:
                body_rel = row["path"]
            meta_rel = row["path"] if is_meta_path else row["path"] + ".meta.json"
            body_path = "intake/" + body_rel
            body = tar.extractfile(body_path).read()
            meta_path = "intake/" + meta_rel
            meta = json.loads(tar.extractfile(meta_path).read())
            capture = next((c for c in manifest["captures"]
                            if c["path"] in {body_rel, meta_rel}), None)
            require(capture is not None and sha(body) == row["sha256"] == meta["sha256"] ==
                    meta["readback_sha256"] == capture["sha256"] and
                    row["observed_request_start_utc"] == meta["observed_request_start_utc"] ==
                    capture["observed_request_start_utc"] and meta["readback_verified"] is True,
                    f"source metadata or readback differs: {row['path']}")
            observed = datetime.fromisoformat(meta["observed_response_end_utc"].replace("Z", "+00:00"))
            require(observed < earliest, f"post-issue input was included as pre-issue: {row['path']}")
            expected_class = "pre_registration" if observed <= registered else "later_than_registration_pre_first_issue"
            require(row["classification"] == expected_class,
                    f"source capture classification differs: {row['path']}")
        require(sum(r["classification"] == "later_than_registration_pre_first_issue" for r in rows) == 114,
                "later-than-registration pre-issue source count differs")
        # The six canonical availability payloads cite these exact pre-issue FotMob bodies.
        with tarfile.open(ROOT / "canonical-records.tar.gz", "r:gz") as canonical:
            for slot in REG["slots"]:
                if slot["comprehensive_first_issue"] is not None:
                    continue
                eid = slot["match_id"].split(":", 1)[1]
                record = json.load(canonical.extractfile(f"canonical/comprehensive/espn-{eid}.json"))
                avail = record["payload"]["availability"]
                path = f"intake/raw/current/fotmob-target-details/{eid}.json"
                body = tar.extractfile(path).read()
                meta = json.loads(tar.extractfile(path[:-5] + ".meta.json").read())
                require(sha(body) == avail["source_sha256"] == meta["sha256"] and
                        meta["readback_verified"] is True and
                        datetime.fromisoformat(meta["observed_response_end_utc"].replace("Z", "+00:00")) < earliest,
                        f"FotMob target availability provenance differs: {slot['match_id']}")
                for side in ("home", "away"):
                    for item in record["payload"]["source_form"][side]:
                        recent_path = f"intake/raw/current/fotmob-recent-details/{item['id']}.json"
                        recent_raw = tar.extractfile(recent_path).read()
                        recent_meta = json.loads(tar.extractfile(
                            f"intake/raw/current/fotmob-recent-details/{item['id']}.meta.json").read())
                        require(sha(recent_raw) == item["source_sha256"] == recent_meta["sha256"] and
                                recent_meta["observed_response_end_utc"] == item["query"] and
                                datetime.fromisoformat(recent_meta["observed_response_end_utc"].replace("Z", "+00:00")) < earliest,
                                f"recent-match source provenance differs: {slot['match_id']} {item['id']}")


def verify_post_issue_pages(registration_sha):
    index = json.loads((ROOT / "post-issue-club-pages.json").read_text(encoding="utf-8"))
    require(index["schema"] == "R10-UCL-POST-ISSUE-CLUB-SOURCES-1" and
            index["registration_sha256"] == registration_sha and
            index["model_input_use"].startswith("none;") and len(index["pages"]) == 10,
            "post-issue club source index differs")
    earliest = datetime.fromisoformat(index["earliest_comprehensive_first_utc"])
    with tarfile.open(ROOT / "post-issue-club-pages.tar.gz", "r:gz") as tar:
        for page in index["pages"]:
            body = tar.extractfile("official-news/" + page["body_file"]).read()
            meta_raw = tar.extractfile("official-news/" + page["meta_file"]).read()
            meta = json.loads(meta_raw)
            observed = datetime.fromisoformat(meta["observed_response_end_utc"].replace("Z", "+00:00"))
            require(sha(body) == page["body_sha256"] == meta["sha256"] == meta["readback_sha256"] ==
                    page["source_sha256"] and sha(meta_raw) == page["meta_sha256"] and
                    page["url"] == meta["url"] and
                    page["observed_response_end_utc"] == meta["observed_response_end_utc"] and
                    observed > earliest and page["status"] == "post_issue_only" and
                    page["pre_match_inputs_used"] is False,
                    f"post-issue club page body/meta receipt differs: {page['body_file']}")
        for orphan in index["orphan_metadata"]:
            raw = tar.extractfile("official-news/" + orphan["meta_file"]).read()
            meta = json.loads(raw)
            observed = datetime.fromisoformat(meta["observed_response_end_utc"].replace("Z", "+00:00"))
            require(sha(raw) == orphan["meta_sha256"] and
                    meta["sha256"] == orphan["source_sha256"] and observed > earliest and
                    orphan["body_available_with_matching_sha256"] is False and
                    orphan["included_in_model_or_preissue_evidence"] is False,
                    "orphan post-issue metadata was incorrectly used")


def load_archive_bytes(archive, member):
    with tarfile.open(archive, "r:gz") as tar:
        return tar.extractfile(member).read()


def load_archive_text(archive, member):
    return load_archive_bytes(archive, member).decode("utf-8")


if __name__ == "__main__":
    print(json.dumps(verify(), ensure_ascii=False, indent=2))
