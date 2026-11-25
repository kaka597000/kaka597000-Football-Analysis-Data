"""Rebuild one append-only November 25 review from local originals and genuine acquisition clocks."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.dont_write_bytecode = True
# Permit direct use next to the named shared checkout or with an installed runtime on PYTHONPATH.
if (Path(__file__).resolve().parents[1]/'r14-source/runtime').is_dir():
    sys.path.append(str(Path(__file__).resolve().parents[1]/'r14-source/runtime'))

from research.analysis_freeze import aware
from research.display_delivery import delivery_request
from research.display_review import review_batch, summarize as display_summary
from research_program import nov25_first_review as core
from research_program.display_window_review import _market_clock_match
from research_program.kpi_validation import _actual, quote_audit
from research_program.paired_kpi_inference import _decisions, compare
from storage_lock import exclusive_lock
import originals
import jleague

HERE = Path(__file__).resolve().parent
INTAKE = HERE.parent/'live-j1-afc-20261125'
UPDATES = HERE.parent/'r14-data/workspace-updates'


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)+'\n').encode()


def matchrow(f, tips, line, actual):
    return dict(id=f['match_id'], date=aware(f['kickoff_at']).astimezone(timezone.utc).date().isoformat(),
                cohort=f['cohort'], line=line, forecast=tips, actual=actual)


def channels(records, statuses, labels, root, tmp, independent, at):
    tmp.mkdir()
    normalized = []
    starts = {}
    for mid, r in records.items():
        f = r['fixture']
        start = statuses[mid]['kickoff']
        official = statuses[mid].get('jleague',{})
        if start and not (official.get('kickoff_interval') or official.get('kickoff_conflict')):
            starts[mid] = dict(match_id=mid, competition=f['competition'], home=f['home'], away=f['away'],actual_kickoff_at=start['at'])
        if mid in labels:
            label = labels[mid]
            evidence = label['evidence']
            raw = core.file_in(root,evidence['file']).read_bytes()
            name = evidence['sha256']+'.json'
            (tmp/name).write_bytes(raw)
            normalized.append(dict(f, known_at=label['observed_at'], score_basis='regulation_90', source_url=evidence['url'],
                     home_goals=label['home_goals'],away_goals=label['away_goals'],event_status='FT',
                     raw_reference=dict(path=name, captured_at=label['observed_at'], source_url=evidence['url'],sha256=evidence['sha256'])))
    (tmp/'normalized-results.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in normalized))
    package = independent or {}
    staged = package.get('staged')
    msg = package.get('message_readback')
    rows = review_batch([r['fixture'] for r in records.values()], records.values(), state=tmp, at=at, staged=staged,
                        room_id=package.get('room_id'), author_id=package.get('author_id'), message_id=package.get('message_id'),
                        read_message=(lambda _:msg) if msg else None, lookup_original=package.get('first_deliveries',{}).get,
                        lookup_actual_kickoff=lambda g: starts.get(g['match_id']),
                        lookup_approved_scope=lambda g: package.get('approved_scopes',{}).get(g['match_id']))
    for row in rows:
        mid = row['match_id']
        interval = statuses[mid].get('jleague',{}).get('kickoff_interval')
        # review_batch emits this reason only after authenticating the delivery, scope and planned deadline.
        if interval and row.get('display_issue') == 'UNVERIFIED_ACTUAL_KICKOFF':
            rec = records[mid]
            receipt = package['first_deliveries'][delivery_request(rec)['slot']]
            apply_channel_interval(row, rec, receipt, interval, at)
    return {r['match_id']:r for r in rows}, display_summary(rows)


def apply_channel_interval(row, record, receipt, interval, at):
    row['actual_kickoff_interval'] = interval
    timing = core.before_official_minute(receipt['delivered_at'],interval)
    if timing != 'before_entire_interval' or aware(interval['end_exclusive']) > at:
        row['display_issue'] = 'DELIVERY_NOT_PROVED_BEFORE_WHOLE_KO_MINUTE'
        return
    payload = record['payload']
    display = payload['authored_display']
    row.pop('display_issue')
    row.update(display_status=display['status'], freeze_sha256=record['record_sha256'],
               delivered_at=receipt['delivered_at'], message_id=receipt['message_id'],
               original_body_sha256=receipt['original_body_sha256'])
    if display['status'] == 'ISSUED':
        row.update(top1_issued=True,top3_issued=True)
        result = row['result']
        if result is not None:
            score = f"{result['home']}-{result['away']}"
            row.update(top1_hit=score==display['first'],top3_hit=score in payload['displayed_scores'])


def authored(group, records, statuses, labels, intake, tmp, evidence, at):
    confirmed, channel = channels(records, statuses, labels, intake, tmp, evidence, at)
    rows, certified_rows, details, actuals = [], [], {}, {}
    for mid, original in group['rows'].items():
        f = original['fixture']
        start = statuses[mid]['kickoff']
        official = statuses[mid].get('jleague',{})
        interval = official.get('kickoff_interval')
        if start and not (interval or official.get('kickoff_conflict')) and aware(original['issued_at']) >= aware(start['at']):
            raise ValueError('archived first follows the verified actual kickoff: ' + mid)
        p, line = original['candidate'], original['quote']['line']
        goals = _actual(labels[mid], f, intake, at) if mid in labels else None
        if goals is not None:
            actuals[mid] = goals
        strict = bool(quote_audit(f)['eligible'] and original['provider_clock']
                      and _market_clock_match(original['quote'], original['provider_clock']))
        row = matchrow(f, dict(authored=p, market=original['market'], issued_market=original['frozen_market']), line, goals)
        rows.append(row)
        c = confirmed[mid]
        public = dict(p) if c['top1_issued'] else {}
        market = dict(original['market'])
        if not strict:
            public.pop('total_side', None)
            market.pop('total_side', None)
        certified_rows.append(dict(row,forecast=dict(authored=public,market=market)))
        _, outcomes, settlement = _decisions(p,goals,line)
        details[mid] = dict(original, actual=goals, ft_source=labels.get(mid,{}).get('evidence'),
                            archived_first_outcomes=outcomes, archived_total_settlement=settlement, strict_quote=strict,
                            channel_first_verified=c['top1_issued'], channel_reason=c.get('display_issue') or
                            (None if c['top1_issued'] else 'no independently verified original first delivery'),
                            kickoff_proof=statuses[mid]['kickoff'])
        if official:
            details[mid].update(official_kickoff_interval=interval,
                archived_issue_vs_official_ko=core.before_official_minute(original['issued_at'],interval) if interval else None,
                official_kickoff_source=official['kickoff_source'], kickoff_conflict=official['kickoff_conflict'])
            if interval:
                details[mid]['batch_publication_at'] = group['published_at']
                details[mid]['batch_publication_vs_official_ko'] = core.before_official_minute(group['published_at'],interval)
                quote_clock = original['quote'].get('query_time')
                if quote_clock:
                    details[mid]['quote_read_vs_official_ko'] = core.before_official_minute(quote_clock,interval)
    picks = {mid:r['candidate'] for mid,r in details.items()}
    selected = group['selected']
    frozen = compare(rows,baseline='market',candidate='authored')
    verified = compare(certified_rows,baseline='market',candidate='authored')
    channel_seats = core.seats(selected,picks,{mid:actuals[mid] for mid in selected if mid in actuals and confirmed[mid]['top1_issued']})
    for seat in channel_seats['seats']:
        seat['channel_first_verified'] = confirmed[seat['match_id']]['top1_issued']
    return dict(registration=group['registration'], publication=group['publication'], archived_source=group['archived_source'],
                body_sha256=group.get('body_sha256'), rows=details, registered=len(rows), completed=len(actuals),
                pending=len(rows)-len(actuals), observed_lines=len(rows), strict_lines=sum(v['strict_quote'] for v in details.values()),
                archived_first_vs_observed_market=frozen, archived_first_vs_issued_market=compare(rows,baseline='issued_market',candidate='authored'),
                archived_seats=core.seats(selected,picks,actuals), certified_channel=channel,
                channel_first_vs_market=verified, channel_seats=channel_seats)


def research(name, batch, prior, fixtures, labels, intake, at, statuses):
    plan, records, ranking = batch
    if aware(plan['recorded_at']) > at:
        raise ValueError('review predates an original research registration')
    rows, tonight, details, actuals, picks = [], [], {}, {}, {}
    for mid, r in records.items():
        f, p = r['fixture'], r['payload']
        if aware(r['recorded_at']) > at:
            raise ValueError('review predates an original research first')
        result = prior.get(mid)
        goals = result['score'] if result else None
        if mid in fixtures:
            core.same_fixture(f, fixtures[mid])
            if mid in labels:
                if result:
                    raise ValueError('double counted older and tonight result: ' + mid)
                # Keep the native research cohort and stage after binding both to the provider stage.
                label = dict(labels[mid], **{k:f[k] for k in ('cohort','stage','kickoff_at')})
                goals = _actual(label, f, intake, at)
        row = matchrow(f,p['forecasts'],p['line'],goals)
        rows.append(row)
        picks[mid] = p['forecasts']['candidate']
        if goals is not None:
            actuals[mid] = goals
        if mid in fixtures:
            tonight.append(row)
            details[mid] = dict(first_sha256=r['record_sha256'], issued_at=r['recorded_at'], fixture=f, line=p['line'],
                                candidate=picks[mid], market=p['forecasts']['market'], actual=goals)
            interval = statuses[mid].get('jleague',{}).get('kickoff_interval')
            if interval:
                details[mid].update(official_kickoff_interval=interval,
                                    issued_vs_official_ko=core.before_official_minute(r['recorded_at'],interval))
                if ranking and mid in ranking['selected'].get(f['cohort'],[]):
                    details[mid].update(ranked_at=ranking['recorded_at'],
                                        rank_vs_official_ko=core.before_official_minute(ranking['recorded_at'],interval))
    def metrics(group):
        return compare(group,baseline='market',candidate='candidate') if group else None
    return dict(track=plan['payload']['track'], registration=plan['record_sha256'], original_population=len(rows),
                prior_settled=len(prior), tonight_registered=len(tonight), tonight_settled=sum(r['actual'] is not None for r in tonight),
                cumulative_settled=len(actuals), pending=len(rows)-len(actuals), original_first_vs_market=metrics(rows),
                tonight_by_competition={code:metrics([v for v in tonight if v['cohort']==code]) for code in core.STAGES},
                tonight_firsts=details, ranking_registration=ranking and ranking['registration'],
                original_seats={c:core.seats(ids,picks,actuals) for c,ids in ranking['selected'].items()} if ranking else None)


def build(intake, updates, at=None, channel_input=None):
    now = datetime.now(timezone.utc)
    ceiling = aware(at).astimezone(timezone.utc) if at else now
    if ceiling > now:
        raise ValueError('review cutoff is in the future')
    captures, log_body = core.refresh_log(intake,ceiling,with_bytes=True)
    if not captures:
        raise ValueError('no genuine local refresh at this cutoff')
    official = jleague.read_asof(intake,ceiling)
    cutoff = ceiling if at else max([*(aware(r['captured_at_utc']) for _,r in captures),*official[3]]).astimezone(timezone.utc)
    as_of = cutoff.isoformat()
    source = originals.Sources(updates)
    j1, jrecords = originals.j1(source)
    afc, arecords = originals.afc(source)
    fixtures = {k:r['fixture'] for k,r in (jrecords|arecords).items()}
    if any(aware(r['recorded_at']) > cutoff for r in (jrecords|arecords).values()):
        raise ValueError('snapshot predates tonight’s original archived firsts')
    reg = core.registration(intake, fixtures)
    intake_files = {'registration.json':core.REGISTRY_SHA}
    pre = []
    for item in reg['preserved_pre_kickoff_sources']:
        data = core.file_in(intake,item['path']).read_bytes()
        stamp = item.get('retrieved_at_utc')
        if (sha256(data).hexdigest() != item['copied_sha256'] or item['copied_sha256'] != item['source_sha256']
                or stamp and aware(stamp) > aware(reg['created_at_utc'])):
            raise ValueError('preserved pregame bytes or date differ')
        intake_files[item['path']] = item['copied_sha256']
        pre.append(dict(path=item['path'],sha256=item['copied_sha256'],retrieved_at_utc=stamp))
    channel_body = channel_input.read_bytes() if channel_input else None
    independent = json.loads(channel_body) if channel_body else {}
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        batches = {k:originals.research_firsts(source,k,root) for k in originals.FIRSTS}
        prior = originals.r7_prior(source,root,batches['R7'][1],cutoff)
        status, labels, raw_files, failures = core.inspect(intake,fixtures,captures,cutoff)
        secondary = 'unverified'
        if official[0]:
            official_files, checks = jleague.inspect(intake,official,reg,status,labels,cutoff)
            raw_files.update(official_files)
            secondary = dict(provider='J.LEAGUE', J1=dict(registered=7, verified_match_pages=sum(bool(c['official_pages']) for c in checks.values()),
                             verified_ko_minutes=sum(bool(c['kickoff_interval']) for c in checks.values()),
                             corroborated_ft90=sum(c['verdict']=='official_and_espn_ft_agree' for c in checks.values())),
                             AFC=dict(registered=2,verified_match_pages=0,corroborated_ft90=0))
        if set(labels) & set(prior):
            raise ValueError('original R7 prior overlaps tonight')
        live = dict(schema='NOV25-KICKOFF-LIVE-1',at=as_of,source='ESPN', independent_official_secondary=secondary,
                    fixtures=status, acquisitions=len(captures), acquisition_failures=failures,
                    verified_kickoffs=sum(r['kickoff'] is not None for r in status.values()))
        report = dict(schema='NOV25-FT90-FIRST-1',at=as_of,registered=len(fixtures),certified_ft90=len(labels),
                      pending=len(fixtures)-len(labels), source='ESPN',independent_official_secondary=secondary,
                      certified_labels=labels, earlier_r7_certified=prior,
                      J1=authored(j1,jrecords,status,labels,intake,root/'j1-channel',independent.get('J1'),cutoff),
                      AFC=authored(afc,arecords,status,labels,intake,root/'afc-channel',independent.get('AFC'),cutoff),
                      research={k:research(k,b,prior if k=='R7' else {},fixtures,labels,intake,cutoff,status)
                                if b else dict(status='original_archive_unavailable') for k,b in batches.items()})
        if official[0]:
            live.update(schema='NOV25-KICKOFF-LIVE-2', fixtures_with_kickoff_evidence=sum(
                not checks[mid]['kickoff_conflict'] and bool(s['kickoff'] or checks[mid]['kickoff_interval']) for mid,s in status.items()))
            report.update(schema='NOV25-FT90-FIRST-2', result_crosscheck=checks)
    inputs = dict(at=as_of, archived_sources=source.files, intake_files=intake_files|raw_files,
                  preserved_pre_capture=pre, acquisition_rows=len(captures),
                  acquisition_log_sha256=sha256(log_body).hexdigest(),
                  channel_input_sha256=sha256(channel_body).hexdigest() if channel_body else None)
    # Keep log entries, including failed HTTP attempts, in source order with their original clocks.
    parts = {'live-status.json':encoded(live), 'ft-review.json':encoded(report), 'inputs.json':encoded(inputs),
             'refreshes.jsonl':log_body}
    if official[0]:
        inputs['official_ledgers'] = {key:dict(intake_path=jleague.SLICES[key],sha256=sha256(body).hexdigest())
                                      for key,body in official[0].items()}
        parts.update(official[0])
        parts['inputs.json'] = encoded(inputs)
    if channel_body is not None:
        parts['channel-input.json'] = channel_body
    return cutoff, parts


def write_snapshot(intake, updates, out, at=None, channel_input=None):
    cutoff, parts = build(intake,updates,at,channel_input)
    manifest = {n:sha256(b).hexdigest() for n,b in parts.items()}
    parts['snapshot-manifest.json'] = encoded(dict(as_of=cutoff.isoformat(),files=manifest))
    if parts.keys() & jleague.SLICES.keys():
        out = out/'jleague'
    out.mkdir(parents=True,exist_ok=True)
    target = out/cutoff.strftime('%Y%m%dT%H%M%S%fZ')
    with exclusive_lock(out/'.review.lock'), TemporaryDirectory(dir=out) as tmp:
        if target.exists():
            if {p.name:p.read_bytes() for p in target.iterdir()} != parts:
                raise ValueError('different evidence or review already exists at this cutoff')
        else:
            earlier = sorted(p for p in out.glob('*Z') if p.is_dir() and p.name < target.name)
            if earlier:
                last = earlier[-1]
                recorded = originals.read(last/'snapshot-manifest.json')['files']
                for name in (set(jleague.LOGS)|{'refreshes.jsonl'}) & recorded.keys():
                    old_log = (last/name).read_bytes()
                    new_lines = iter(parts.get(name,b'').splitlines())
                    if sha256(old_log).hexdigest() != recorded[name] or not all(line in new_lines for line in old_log.splitlines()):
                        raise ValueError('acquisitions from the prior immutable snapshot disappeared or changed')
            stage = Path(tmp)/'complete'
            stage.mkdir()
            for n,b in parts.items():
                (stage/n).write_bytes(b)
            stage.rename(target)
    return target


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--intake',type=Path,default=INTAKE)
    p.add_argument('--updates',type=Path,default=UPDATES)
    p.add_argument('--out',type=Path,default=HERE/'snapshots')
    p.add_argument('--at',help='explicit zoned cutoff, otherwise use the latest genuine local acquisition')
    p.add_argument('--channel-input',type=Path,help='independent existing local readback exports grouped by J1/AFC')
    args = p.parse_args()
    path = write_snapshot(args.intake,args.updates,args.out,args.at,args.channel_input)
    ft = originals.read(path/'ft-review.json')
    live = originals.read(path/'live-status.json')
    print(json.dumps(dict(snapshot=str(path),at=ft['at'],known_starts=live['verified_kickoffs'],
                          ft90=ft['certified_ft90'],pending=ft['pending'],r7_settled=ft['research']['R7']['cumulative_settled'])))
