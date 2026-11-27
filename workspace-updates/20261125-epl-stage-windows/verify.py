"""Recover the two EPL registration windows and their existing native firsts from retained bytes."""

from datetime import timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import tarfile
from urllib.parse import parse_qs, urlsplit

from research.analysis_freeze import aware, verify
from research_program import goal_state_forward as ledger
from research_program.goal_state_study import sha


ROOT = Path(__file__).resolve().parent
TRACK = "eng1-comprehensive-windows-20261125"


def read(path):
    return json.loads(path.read_bytes())


def population(root):
    spec = read(root/"protocol.json")
    calendar = read(root/"acquisitions.json")
    start = aware(spec["windows"][0]["from"])
    end = aware(spec["windows"][-1]["until"])
    dates = set()
    day = start.astimezone(timezone.utc).date()
    until = (end - timedelta(microseconds=1)).astimezone(timezone.utc).date()
    while day <= until:
        dates.add(day.strftime("%Y%m%d"))
        day += timedelta(days=1)
    if dates != set(calendar) or aware(spec["windows"][0]["until"]) != aware(spec["windows"][1]["from"]):
        raise ValueError("registration lacks a UTC date board or its intervals are not consecutive")
    fixtures = {}
    for key, evidence in sorted(calendar.items()):
        body = (root/"schedule"/(key+".json")).read_bytes()
        url = urlsplit(evidence["url"])
        if (sha256(body).hexdigest() != evidence["sha256"] or len(body) != evidence["bytes"]
                or url.scheme != "https" or url.netloc != "site.api.espn.com"
                or url.path != "/apis/site/v2/sports/soccer/eng.1/scoreboard" or parse_qs(url.query) != {"dates":[key]}
                or aware(evidence["requested_at"]) > aware(evidence["observed_at"]) or aware(evidence["observed_at"]) >= start):
            raise ValueError("original EPL calendar source or timestamp differs")
        doc = json.loads(body)
        if [q["slug"] for q in doc["leagues"]] != ["eng.1"]:
            raise ValueError("unexpected league board")
        for event in doc["events"]:
            game, = event["competitions"]
            kickoff = aware(event["date"])
            if kickoff.astimezone(timezone.utc).strftime("%Y%m%d") != key:
                raise ValueError("fixture appears on the wrong UTC board")
            if not start <= kickoff < end:
                continue
            mid = "espn:"+str(event["id"])
            sides = {s["homeAway"]:s["team"] for s in game["competitors"]}
            if (mid in fixtures or str(game["id"]) != str(event["id"]) or len(game["competitors"]) != 2
                    or set(sides) != {"home","away"} or sides["home"]["id"] == sides["away"]["id"]
                    or event["season"] != {"year":2026,"type":14308,"slug":"2026-27-english-premier-league"}
                    or aware(game["date"]) != kickoff or not game["timeValid"]
                    or event["status"]["type"]["name"] != "STATUS_SCHEDULED"):
                raise ValueError("EPL fixture identity, stage or scheduled status differs: "+mid)
            fixtures[mid] = dict(match_id=mid, cohort="eng.1", stage="regular", kickoff_at=kickoff.isoformat(),
                                 home="espn:"+str(sides["home"]["id"]), away="espn:"+str(sides["away"]["id"]))
    slates = {}
    for window in spec["windows"]:
        ids = sorted(mid for mid,g in fixtures.items() if aware(window["from"]) <= aware(g["kickoff_at"]) < aware(window["until"]))
        if len(ids) != window["expected"]:
            raise ValueError("window size differs from its registration")
        slates[window["name"]] = ids
    return fixtures, slates


def bindings(root, fixtures):
    slots = read(root/"earlier-firsts.json")
    models = read(root/"model-inputs.json")["native_models"]
    if set(slots) != set(fixtures):
        raise ValueError("every fixture requires an earlier-slot check")
    for mid, tracks in slots.items():
        if set(tracks) != {"current-test-pair","comprehensive"}:
            raise ValueError("both native and comprehensive slots must be recorded")
        for track, value in tracks.items():
            if value is None:
                continue
            if value["file"] != mid.split(":")[1]+"-"+track+".json":
                raise ValueError("unexpected native first filename")
            r = verify(read(root/"earlier"/value["file"]))
            f = r["fixture"]
            if (r["record_sha256"] != value["sha256"] or r["track"] != track or r["revision"] != 1
                    or r["evaluation_slot"] != "FIRST_PREMATCH" or r["previous_sha256"] is not None
                    or r["recorded_at"] != value["recorded_at"] or aware(r["recorded_at"]) >= aware(f["kickoff_at"])
                    or any(f[k] != fixtures[mid][k] for k in ("match_id","cohort","stage","home","away"))
                    or aware(f["kickoff_at"]) != aware(fixtures[mid]["kickoff_at"])):
                raise ValueError("earlier first, kickoff or native teams differ: "+mid)
            if track == "current-test-pair":
                audit = r["payload"]["execution_audit"]
                if any(audit[arm.lower()]["artifact_sha256"] != models[arm]["sha256"] for arm in models):
                    raise ValueError("registered weights differ from earlier native executions: "+mid)
    return slots


def identity(root, fixtures, slates):
    independent = read(root/"paired-schedule.json")
    if (set(independent) != set(fixtures) or any(not r["exact_fixture_found"]
            or "espn:"+r["home_id"] != fixtures[mid]["home"] or "espn:"+r["away_id"] != fixtures[mid]["away"]
            or aware(r["kickoff_utc"]) != aware(fixtures[mid]["kickoff_at"]) for mid,r in independent.items())):
        raise ValueError("the independent fixture crosswalk does not match the full schedule")
    return dict(version=read(root/"protocol.json")["version"], protocol=read(root/"protocol.json"),
                protocol_sha256=sha(root/"protocol.json"), acquisitions_sha256=sha(root/"acquisitions.json"),
                independent_pair_crosswalk_sha256=sha(root/"paired-schedule.json"), model_inputs=read(root/"model-inputs.json"),
                roadmap=read(root/"goals.json"), slates=slates, earlier_firsts=bindings(root, fixtures))


def earlier_team_study(root, fixtures):
    folder = root.parent/"20261123-team-strength"
    package = folder/"research-and-freezes.tar.gz"
    expected = "7165ba80bbd0801a4de0fc13d452b0a283fa4e2988642f728335b63b77ae3efc"
    if sha(package) != expected or read(folder/"manifest.json")["files"][package.name] != expected:
        raise ValueError("prior team-strength archive differs")
    with tarfile.open(package) as archive:
        refs = json.load(archive.extractfile("forward/receipts.json"))
        def original(ref):
            value = verify(json.load(archive.extractfile("issued/"+ref["freeze_id"]+".json")))
            if (value["record_sha256"] != ref["sha256"] or value["freeze_id"] != ref["freeze_id"]
                    or value["revision"] != 1 or value["evaluation_slot"] != "FIRST_PREMATCH"):
                raise ValueError("prior team-strength first differs")
            return value
        plan = original(refs["register"])
        if set(refs["matches"]) != set(plan["payload"]["fixtures"]) or plan["track"] != "kpi-preregistration":
            raise ValueError("earlier team-strength calendar differs")
        records = {}
        for mid in sorted(set(fixtures) & refs["matches"].keys()):
            record = original(refs["matches"][mid])
            row, payload = record["fixture"], record["payload"]
            for f in (row, plan["payload"]["fixtures"][mid]):
                if (any(f[k] != fixtures[mid][k] for k in ("match_id","home","away","stage","cohort"))
                        or aware(f["kickoff_at"]) != aware(fixtures[mid]["kickoff_at"])):
                    raise ValueError("older team-strength input differs from calendar: "+mid)
            candidate = payload["candidate"]
            if (record["track"] != "kpi-first-forecast" or payload["plan_sha256"] != plan["record_sha256"]
                    or candidate["version"] != "WCPP-PRIOR-TEAM-STRENGTH-1"
                    or candidate["artifact_sha256"] != plan["payload"]["candidate"]["artifact_sha256"]
                    or not aware(plan["recorded_at"]) <= aware(record["recorded_at"]) < aware(row["kickoff_at"])):
                raise ValueError("prior team-strength track, weights or time differs: "+mid)
            records[mid] = dict(first_sha256=record["record_sha256"], track=record["track"], recorded_at=record["recorded_at"],
                                candidate=candidate, market=payload["market_baseline"])
    return dict(source_archive_sha256=expected, registration=plan["record_sha256"], matches=records)


def verify_package(root=ROOT):
    fixtures, slates = population(root)
    record = ledger._read(root/"registration", read(root/"registration/plan.json"))
    expected = identity(root, fixtures, slates)
    if record["payload"] != dict(track=TRACK, identity=expected, fixtures=fixtures):
        raise ValueError("registered population, prior versions or research protocol changed")
    recorded = aware(record["recorded_at"])
    observations = [aware(e["observed_at"]) for e in read(root/"acquisitions.json").values()]
    observations += [aware(e["sky_page_query_utc"]) for e in read(root/"paired-schedule.json").values()]
    if not max(observations) <= recorded < min(aware(f["kickoff_at"]) for f in fixtures.values()):
        raise ValueError("registration and source clocks are inconsistent")
    for tracks in expected["earlier_firsts"].values():
        if any(r and aware(r["recorded_at"]) > recorded for r in tracks.values()):
            raise ValueError("referenced earlier first is too late")
    research = earlier_team_study(root, fixtures)
    if research != read(root/"prior-team-strength.json"):
        raise ValueError("prior research choices or market reference differ")
    return {"windows":{k:len(v) for k,v in slates.items()}, "prior_native_pairs":sum(
        bool(v["current-test-pair"]) for v in expected["earlier_firsts"].values()),
        "previous_team_strength_issues":len(research["matches"]), "registered_at":record["recorded_at"]}


if __name__ == "__main__":
    print(json.dumps(verify_package(), indent=2))
