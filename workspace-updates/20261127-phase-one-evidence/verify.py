"""Replay the first-stage evidence inputs without reading current scores or rewriting forecasts."""

import argparse
import csv
from datetime import timedelta
from hashlib import sha256
import json
from pathlib import Path
import tarfile
from tempfile import TemporaryDirectory

from research.analysis_freeze import aware, verify
from research_program import club_market_capture as club_market
from research_program import display_window_review as display
from research_program import j1_window_intake as intake
from research_program import nov25_first_review as acquired
from research_program.three_arm_review import _results


AS_OF = aware('2026-11-27T11:50:00+08:00')
RESEARCH = (
    '20261126-r28-j1-process-forward',
    '20261127-r42-j1-fixed-first-backups',
    '20261127-r46-j1-process-at-fixed-total',
    '20261127-r49-j1-season-chance-rates',
)


def historical(data, root, plan_path):
    registered = display._registered(intake.read(plan_path))
    fixtures = {mid: registered[1][mid] for mid in registered[2]['nov25']}
    europe = data / '20261127-europe-round1-review'
    proof = verify(intake.read(europe / 'review-freeze.json'))
    plan_bytes = (europe / 'j1-capture-plan.json').read_bytes()
    if sha256(plan_bytes).hexdigest() != proof['payload']['j1_capture_plan_sha256']:
        raise ValueError('previous J.League capture plan was changed')
    originals = json.loads(plan_bytes)['november_25_start_rehearsal']
    archive_path = data / '20261125-forward-settlement/nov25/evidence.tar.gz'
    if sha256(archive_path.read_bytes()).hexdigest() != originals['archive_sha256']:
        raise ValueError('previous raw archive differs from the signed audit')
    with tarfile.open(archive_path) as archive:
        def rows(file):
            return [json.loads(line) for line in archive.extractfile('snapshot/' + file).read().splitlines()]

        def restore(row):
            path = acquired.file_in(root, row['path'])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(archive.extractfile('intake/' + row['path']).read())

        summaries = [(i, row) for i, row in enumerate(rows('refreshes.jsonl'), 1)
                     if row['league_slug'] == 'jpn.1' and row['kind'] == 'summary']
        for _, row in summaries:
            if row.get('path'):
                restore(row)
        official_rows = rows('jleague-live-captures.jsonl')
        official, bindings = {}, {}
        for code, (event, home, away) in acquired.J1_CARDS.items():
            mid = 'espn:' + event
            bindings[mid] = dict(fixture=fixtures[mid], code=code, url=acquired.J1_URL.format(code),
                                 section=acquired.J1_ROUND, home=list(home), away=list(away))
            finale = max((r for r in official_rows if r['http_status'] == 200 and
                          r.get('jleague_match_code', r.get('match_code')) == code),
                         key=lambda r: aware(r['captured_at_utc']))
            official[mid] = []
            for row in (originals['matches'][mid]['official_kickoff_source'], finale):
                restore(row)
                official[mid].append(dict(row, code=code, raw_file=row['path']))
    replay, results, starts = intake.check(fixtures, bindings, summaries, official, root, AS_OF)
    state = data / '20261126-j1-forward-result-review/nov25-state'
    expected, issues = _results(state, fixtures, AS_OF)
    scores = {row['match_id']: (row['home_goals'], row['away_goals']) for row in results}
    if issues or scores != {mid: (row['home'], row['away']) for mid, row in expected.items()}:
        raise ValueError('different historical regulation outcome')
    for mid, start in starts.items():
        original = originals['matches'][mid]['official_interval']
        if (start['precision'] != 'minute' or aware(start['earliest']) != aware(original['start_inclusive'])
                or aware(start['latest']) != aware(original['end_exclusive'])):
            raise ValueError('the original actual kickoff minute did not reproduce: ' + mid)
    if replay['settled'] != 7 or any(r['official_result_agreement'] != 'official_and_espn_ft_agree'
                                    for r in replay['match_evidence'].values()):
        raise ValueError('expected the seven original dual-source J1 finals')
    return dict(registered=7, official_minutes=len(starts), regulation_results=len(scores))


def forthcoming(data, root, reg, binding, window, research=(), *, binding_root=None):
    out = root / window
    intake.intake(reg, window, binding, root / 'empty-intake', out, research, AS_OF, binding_root=binding_root)
    original = data / '20261126-r26-j1-first-stage' / window
    batch_root = None
    if window == 'nov28_29':
        batch_root = root / 'original-batch'
        batch_root.mkdir()
        (batch_root / 'registration').symlink_to(reg.parent, target_is_directory=True)
        (batch_root / 'evidence').symlink_to(original.parent / 'evidence', target_is_directory=True)
        (batch_root / window).symlink_to(original, target_is_directory=True)
    official = display.review(intake.read(reg), ledger_root=original, result_state=out,
                              evidence_root=out, batch_root=batch_root,
                              jleague_kickoffs=intake.read(out / 'jleague-kickoffs.json'),
                              actual_kickoffs=intake.read(out / 'actual-kickoffs.json'), at=AS_OF)
    settled = official['windows'][window]
    report = intake.read(out / 'review.json')
    research_reads = {tag: dict(freeze_id=group['freeze_id'], registered=group['registered'],
                               settled=group['settled'])
                      for tag, group in report['research'].items()}
    if (report['registered'], report['settled'], report['pending'], report['actual_starts'],
            settled['confirmed_first_score_n'], settled['completed_n']) != (10, 0, 10, 0, 0, 0):
        raise ValueError('a scheduled fixture gained result or first-display credit')
    if any(row['registered'] != 10 or row['settled'] for row in research_reads.values()):
        raise ValueError('a research issue gained credit before kickoff')
    readiness = dict(registered=10, pending=10, actual_starts=0, confirmed_firsts=0, research=research_reads,
                     registration=report['registration'], official_binding=report['binding_freeze'])
    if batch_root:
        body = settled['repository_batch_body_audit']
        market = settled['actual_bookmaker_quote']
        if (not all(body[key] for key in ('available', 'sha256_matches_registered_batch',
                                         'original_blocks_present_once_in_order', 'prepared_batch_verified'))
                or (market['raw_verified_price_snapshots_n'], market['strict_quote_issues_n']) != (10, 0)):
            raise ValueError('expected the original whole body and ten clock-unverified market quotes')
        readiness.update(first_frozen_body_verified=True, market_prices_reproduced=10, original_strict_market=0)
    return readiness


def ranked_europe(data):
    folder = data / '20261127-europe-round1-review'
    seal = verify(intake.read(folder / 'review-freeze.json'))
    body = (folder / 'settlement/report.json').read_bytes()
    if sha256(body).hexdigest() != seal['payload']['report_sha256']:
        raise ValueError('original Europe review differs from its frozen digest')
    report = json.loads(body)
    result = {}
    for code, group in report['competitions'].items():
        rows = group['per_match'].values()
        n = len(rows)
        if n != 18 or group['verified_results'] != n or group['dual_source_results'] != n:
            raise ValueError('incomplete original European review')
        ranks = [row['score_grid_diagnosis']['matrix_rank'] for row in rows]
        result[code] = dict(n=n, displayed_first=sum(row['hit']['score_top1'] for row in rows),
                            displayed_three=sum(row['hit']['score_top3'] for row in rows),
                            **{f'matrix_top_{k}': sum(rank is not None and rank <= k for rank in ranks)
                               for k in (1, 3, 5, 10)},
                            outside_6=sum(rank is None or rank > 6 for rank in ranks))
    return result


def scorecard(data):
    path = data / '20261123-all-scope-kpi/results/scorecard.csv'
    with path.open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    result = {}
    for name in ('evaluation', 'recent'):
        sample = [row for row in rows if row['窗口'] == name]
        if len(sample) != 20 or len({row['代码'] for row in sample}) != 20:
            raise ValueError('expected the 20 original competitions')
        metrics = {}
        for key in ('首选比分', '三选比分', '胜平负', '真实大小球'):
            hits = sum(int(row[key+'命中']) for row in sample)
            denominator = sum(int(row[key+'分母']) for row in sample)
            metrics[key] = dict(hits=hits, denominator=denominator, percent=round(100*hits/denominator, 2))
        result[name] = dict(metrics=metrics, all_four=sum(row['四项全过'] == 'True' for row in sample))
    return result


def market_probe(data, probe, reg):
    _, universe, slates, _ = display._registered(intake.read(reg))
    crosswalk = intake.read(data / '20261127-j1-december-readiness/prepared/team-ids.json')['jpn.1']
    captures = intake.read(probe / 'captures.json')
    events, prices = {}, {}
    for ref in captures:
        path = acquired.file_in(probe, ref['path'])
        body = path.read_bytes()
        if (ref['http_status'] != 200 or sha256(body).hexdigest() != ref['sha256']
                or not aware(ref['requested_at']) <= aware(ref['captured_at']) <= AS_OF):
            raise ValueError('market probe HTTP acquisition or clock differs')
        doc = json.loads(body)
        if 'data' in doc:
            if doc.get('page', {}).get('next_cursor'):
                raise ValueError('market event collection truncated')
            for event in doc['data']:
                if event['id'] in events:
                    raise ValueError('market event duplicated across requested matchdays')
                events[event['id']] = event
        elif ref.get('role') != 'reused historical baseline':
            if doc['event_id'] in prices:
                raise ValueError('market quote response duplicated')
            prices[doc['event_id']] = ref, doc
    mapped = intake.read(probe / 'matched-fixtures.json')
    if (len(mapped) != len(slates['nov28_29']) or {m['match_id'] for m in mapped} != set(slates['nov28_29'])
            or len({m['event_id'] for m in mapped}) != len(mapped)
            or {m['event_id'] for m in mapped} != set(events) or set(events) != set(prices)):
        raise ValueError('market identity must cover the ten original registered slots once')
    pairs, covered = 0, 0
    for match in mapped:
        mid, event_id = match['match_id'], match['event_id']
        fixture, event = universe[mid], events[event_id]
        if ((event['league']['id'], event['league']['name']) != club_market.LEAGUES['jpn.1']
                or event['status'] != 'scheduled' or aware(event['scheduled_at']) != aware(fixture['kickoff_at'])
                or any(event[side+'_team']['id'] != crosswalk[fixture[side]]['provider_id']
                       for side in ('home', 'away'))):
            raise ValueError('market event differs from registered home/away and kickoff: ' + mid)
        ref, doc = prices[event_id]
        capture = aware(ref['captured_at'])
        if capture >= aware(fixture['kickoff_at']):
            raise ValueError('market probe must be prematch')
        rows = club_market.fresh_rows(doc, ref, mid, capture)
        books = [{r['bookmaker'] for r in rows if r['market'] == kind} for kind in ('1x2', 'totals')]
        shared = books[0] & books[1]
        pairs += len(shared)
        covered += bool(shared)
    reported = intake.read(probe / 'coverage.json')
    if (reported['strict_fixture_coverage'], reported['strict_book_pairs']) != (covered, pairs):
        raise ValueError('same-book timed market probe coverage differs')
    return dict(fixtures=len(mapped), fresh_at_capture=covered, same_book_pairs=pairs,
                earliest_capture=min(ref['captured_at'] for ref, _ in prices.values()),
                last_capture=max(ref['captured_at'] for ref, _ in prices.values()))


def first_checkpoint(data, directory, reg):
    _, universe, slates, _ = display._registered(intake.read(reg))
    crosswalk = intake.read(data / '20261127-j1-december-readiness/prepared/team-ids.json')
    rows = intake.read(directory / 'prepared-fixtures.json')
    receipts = intake.read(directory / 'receipts.json')
    if len(rows) != 10 or {row['match_id'] for row in rows} != set(slates['nov28_29']):
        raise ValueError('checkpoint must keep the original whole fixture list')
    for ref in receipts['captures']:
        body = acquired.file_in(directory, ref['file']).read_bytes()
        if (sha256(body).hexdigest() != ref['sha256']
                or aware(ref['requested_at']) > aware(ref['captured_at'])):
            raise ValueError('checkpoint acquisition times or hashes differ')
    clocked, eligible, paired, freshest = [], [], [], {}
    for row in rows:
        mid = row['match_id']
        original = universe[mid]
        acquired.same_fixture(original, row)
        checkpoint = row['market_checkpoint']
        deadline = aware(original['kickoff_at']) - timedelta(hours=24)
        checked = aware(checkpoint['checked_at'])
        clocked.append(checked)
        if checkpoint['name'] != 'T-24h' or aware(checkpoint['deadline']) != deadline:
            raise ValueError('incorrect per-game checkpoint deadline')
        allowed = deadline - timedelta(hours=1) <= checked <= deadline
        if allowed:
            eligible.append(mid)
        proof = row.get('market_evidence')
        if proof is None:
            if 'total_quote' in row or mid not in receipts['failures']:
                raise ValueError('unavailable checkpoint lacks a reason or has an unsupported quote')
            continue
        if (not allowed or any(ref not in receipts['captures'] for key, ref in proof.items() if key != 'event_id')):
            raise ValueError('checkpoint contains out-of-window or unretained market proof')
        replay = club_market.attach(dict(original, stage='regular', competition='jpn.1', score_basis='regulation_90'),
                                    directory, proof, crosswalk, deadline.isoformat())
        for key in ('total_quote', 'market_snapshots', 'market_availability'):
            if row.get(key) != replay.get(key):
                raise ValueError('market at the actual checkpoint failed to reproduce: ' + mid)
        if replay['market_availability'] == 'FRESH_SAME_BOOK_PAIR':
            paired.append(mid)
        raw = intake.read(directory / proof['odds']['file'])
        times = [aware(item['as_of']) for item in raw['odds'] if item.get('as_of')]
        if times:
            latest = max(times)
            freshest[mid] = dict(quoted_at=latest.isoformat(),
                                 age_at_deadline_seconds=(deadline-latest).total_seconds())
    return dict(registered=len(rows), in_time=len(eligible), same_book_pair=len(paired),
                checked_first=min(clocked).isoformat(), checked_last=max(clocked).isoformat(),
                first_wave_match_ids=eligible, fresh_pair_match_ids=paired, latest_source_rows=freshest)


def run(data):
    nov = data / '20261125-j1-stage-windows/registration'
    dec = data / '20261126-j1-december-windows/registration'
    nov_reg = nov / intake.read(nov / 'plan.json')['file']
    dec_reg = dec / intake.read(dec / 'plan.json')['file']
    nov_bind = data / '20261127-j1-official-kickoff/kickoff-packet.json'
    dec_bind = data / '20261127-j1-december-evidence/kickoff-packet.json'
    dec_official = dec_bind.parent / 'official'
    research = tuple(data / name / 'issued' for name in RESEARCH)
    package = Path(__file__).parent
    with TemporaryDirectory(prefix='phase-one-replay-') as tmp:
        root = Path(tmp)
        return dict(as_of=AS_OF.isoformat(), historical_j1=historical(data, root / 'nov25', nov_reg),
                    upcoming={
                        'nov28_29': forthcoming(data, root, nov_reg, nov_bind, 'nov28_29', research),
                        'dec04_06': forthcoming(data, root, dec_reg, dec_bind, 'dec04_06', binding_root=dec_official),
                        'dec12_13': forthcoming(data, root, dec_reg, dec_bind, 'dec12_13', binding_root=dec_official),
                    }, historical_scorecard=scorecard(data), europe_score_ranking=ranked_europe(data),
                    upcoming_market_probe=market_probe(data, package / 'market-probe', nov_reg),
                    market_checkpoint_samples={name: first_checkpoint(data, package / name, nov_reg)
                                               for name in ('market-t24', 'market-t24-recheck')})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, required=True, help='repository containing the pinned original evidence')
    args = parser.parse_args()
    print(json.dumps(run(args.data_root.resolve() / 'workspace-updates'), ensure_ascii=False,
                     indent=2, sort_keys=True, allow_nan=False))
