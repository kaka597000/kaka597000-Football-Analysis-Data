"""Replay the first-stage evidence inputs without reading current scores or rewriting forecasts."""

import argparse
import csv
from datetime import timedelta
from hashlib import sha256
import json
from math import fsum, isfinite, log
from pathlib import Path
import tarfile
from tempfile import TemporaryDirectory

from research.analysis_freeze import aware, digest, verify
from research_program import club_market_capture as club_market
from research_program import display_window_review as display
from research_program import goal_state_forward as ledger
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
    capture_dir = root / 'captures' / 'previous-results'
    capture_dir.mkdir(parents=True)
    with tarfile.open(archive_path) as archive:
        def rows(file):
            return [json.loads(line) for line in archive.extractfile('snapshot/' + file).read().splitlines()]

        def restore(row):
            path = acquired.file_in(capture_dir, row['path'])
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
    (capture_dir / 'espn.jsonl').write_text(''.join(json.dumps(row) + '\n' for _, row in summaries),
                                           encoding='utf-8')
    (capture_dir / 'official-captures.json').write_text(json.dumps(official), encoding='utf-8')
    summaries, official = intake.acquisitions(root, AS_OF)
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
        source = report['score_grid_sources'][code]
        if source['original_display']['sha256'] != seal['payload']['original_display_sha256'][code]:
            raise ValueError('score grid source omits the original Europe display identity')
        result[code]['total_and_split'] = europe_total_and_split(data, source, group['per_match'])
    return result


def probability_rank(probabilities, index):
    probability = probabilities[index]
    return 1 + sum(value > probability or (i < index and value == probability)
                   for i, value in enumerate(probabilities))


def score_path(grid, actual):
    home, away = actual
    size = len(grid)
    cells = [value for row in grid for value in row]
    if (not size or any(len(row) != size for row in grid)
            or not all(isfinite(value) and value >= 0 for value in cells)
            or abs(fsum(cells) - 1) > 2e-12 or not (0 <= home < size and 0 <= away < size)
            or grid[home][away] <= 0):
        raise ValueError('invalid retained score support or probability of the recorded result')
    total = home + away
    split_groups = [[grid[h][t-h] for h in range(max(0, t-size+1), min(size-1, t)+1)]
                    for t in range(2*size-1)]
    totals = [fsum(group) for group in split_groups]
    diagnostic = dict(actual_total=total, actual_total_rank=probability_rank(totals, total),
                      split_rank_given_total=probability_rank(split_groups[total], home-max(0, total-size+1)),
                      actual_total_probability=totals[total],
                      actual_split_probability_given_total=grid[home][away]/totals[total])
    return probability_rank(cells, home*size + away), totals, diagnostic


def europe_total_and_split(data, source, rows):
    folder = data / source['package'] / 'issued'
    original = ledger._read(data / '20261126-europe-first-display/publication', source['original_display'])
    registration = ledger._read(folder, source['registration'])
    publication = ledger._read(folder, source['display'])
    fixtures = original['payload']['fixtures']
    index_path = folder / 'receipts.json'
    index = intake.read(index_path)
    identity = publication['payload']['identity']
    if (registration['payload']['fixtures'] != fixtures or publication['payload']['fixtures'] != fixtures
            or index['registration'] != source['registration']
            or index['matches'].keys() != fixtures.keys() or fixtures.keys() != rows.keys()
            or identity['receipts_sha256'] != sha256(index_path.read_bytes()).hexdigest()
            or identity['registration'] != registration['record_sha256']
            or registration['payload']['identity']['original_display'] != original['record_sha256']):
        raise ValueError('the retained European R13 grids differ from the original full slate')
    read_at = aware(publication['recorded_at'])
    baseline, candidate = registration['payload']['identity']['pairs']['vs_r13']
    if baseline != 'r13':
        raise ValueError('expected the original R13 control')
    ranks, variant = {}, {}
    first_changes, three_changes = 0, 0
    for mid, settled in rows.items():
        ref = index['matches'][mid]
        issue = ledger._read(folder, ref)
        saved = issue['payload']
        actual_start = aware(settled['actual_kickoff']['actual_kickoff_at'])
        if (issue['fixture'] != dict(fixtures[mid], cutoff_at=registration['recorded_at'])
                or issue['track'] != registration['payload']['track']
                or saved['registration_sha256'] != registration['record_sha256']
                or saved['original_first'] != settled['original_first']
                or saved['forecasts']['r13'] != settled['original_forecast']
                or not aware(original['recorded_at']) <= aware(registration['recorded_at'])
                <= aware(issue['recorded_at']) <= read_at < min(actual_start, aware(fixtures[mid]['kickoff_at']))):
            raise ValueError('score distribution differs from the original European first: ' + mid)
        rank, totals, ranks[mid] = score_path(saved['grids'][baseline], settled['actual'])
        if rank != settled['score_grid_diagnosis']['matrix_rank']:
            raise ValueError('original joint score rank differs from its settled audit: ' + mid)
        new_rank, new_totals, choice = score_path(saved['grids'][candidate], settled['actual'])
        variant[mid] = dict(choice, joint_score_rank=new_rank,
                            maximum_total_probability_change=max(abs(before-after) for before, after in
                                                                 zip(totals, new_totals, strict=True)))
        before, after = (saved['forecasts'][track] for track in (baseline, candidate))
        first_changes += before['primary'] != after['primary']
        three_changes += set(before['top3']) != set(after['top3'])
    first_misses = [ranks[mid] for mid, row in rows.items() if not row['hit']['score_top1']]
    three_misses = [ranks[mid] for mid, row in rows.items() if not row['hit']['score_top3']]
    rank_changes = [variant[mid]['split_rank_given_total'] - row['split_rank_given_total'] for mid, row in ranks.items()]
    log_loss = {arm: round(-fsum(log(row['actual_split_probability_given_total']) for row in group.values()) / len(group), 9)
                for arm, group in ((baseline, ranks), (candidate, variant))}
    per_match = {mid: {key: round(item, 12) if isinstance(item, float) else item
                       for key, item in row.items()} for mid, row in ranks.items()}
    return dict(per_match=per_match, paired_variant=dict(
                    baseline=baseline, candidate=candidate, n=len(rows), first_changes=first_changes,
                    three_membership_changes=three_changes, conditional_log_loss=log_loss,
                    split_rank_improved=sum(delta < 0 for delta in rank_changes),
                    split_rank_worsened=sum(delta > 0 for delta in rank_changes),
                    maximum_total_probability_change=round(max(row['maximum_total_probability_change']
                                                               for row in variant.values()), 12)),
                first_misses=dict(n=len(first_misses),
                                  total_rank_above_3=sum(row['actual_total_rank'] > 3 for row in first_misses),
                                  split_rank_above_1=sum(row['split_rank_given_total'] > 1 for row in first_misses)),
                three_misses=dict(n=len(three_misses),
                                  total_rank_above_3=sum(row['actual_total_rank'] > 3 for row in three_misses),
                                  split_rank_above_3=sum(row['split_rank_given_total'] > 3 for row in three_misses)))


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


def result_wave_rehearsal(package, root, registration, binding, research):
    plan, fixtures, slates, _ = display._registered(intake.read(registration))
    source = root / 'retained-waves'
    source.mkdir()
    with tarfile.open(package / 'result-wave-rehearsal/captures.tar.gz') as archive:
        archive.extractall(source, filter='data')
    scopes, received = {}, []
    for folder in sorted((source / 'captures').iterdir()):
        receipt = intake.read(folder / 'capture.json')
        schedule = aware(receipt['scheduled_at'])
        expected = {mid for mid in slates['nov28_29'] if aware(fixtures[mid]['kickoff_at']) == schedule}
        if (receipt['registration'] != plan['freeze_id'] or receipt['window'] != 'nov28_29'
                or receipt['blocked'] or expected != set(receipt['fixtures']) or len(expected) != 2
                or schedule in scopes):
            raise ValueError('retained wave differs from the original registration')
        scopes[schedule] = sorted(expected)
        official = intake.read(folder / 'official-captures.json')
        summaries = [json.loads(line) for line in (folder / 'espn.jsonl').read_text().splitlines()]
        if ({'espn:' + row['event_id']: row for row in summaries}
                != {mid: row['espn'] for mid, row in receipt['fixtures'].items()}
                or official != {mid: [row['jleague']] for mid, row in receipt['fixtures'].items()}):
            raise ValueError('capture manifests disagree with their original receipt')
        for sources in receipt['fixtures'].values():
            for item in sources.values():
                arrival = aware(item['captured_at_utc'])
                if (item['http_status'] != 200 or not item.get('sha256')
                        or not aware(item['requested_at_utc']) <= arrival < schedule):
                    raise ValueError('expected the actual prematch capture clocks')
                received.append(arrival)
    if len(scopes) != 2:
        raise ValueError('expected both retained original kickoff waves')
    at = max(received)
    out = root / 'wave-results'
    intake.intake(registration, 'nov28_29', binding, source, out, research, at)
    review = intake.read(out / 'review.json')
    governed = {mid for mids in scopes.values() for mid in mids}
    scheduled = {mid for mid, row in review['match_evidence'].items() if row['official_state'] == 'scheduled'}
    if (scheduled != governed or (review['registered'], review['actual_starts'], review['settled'], review['pending'])
            != (10, 0, 0, 10) or any(r['settled'] for r in review['research'].values())):
        raise ValueError('a genuine prematch capture gained result credit or changed the original denominator')
    return dict(waves={stamp.isoformat(): mids for stamp, mids in scopes.items()}, at=at.isoformat(),
                response_captures=len(received), observed_scheduled=len(scheduled),
                registered=review['registered'], actual_starts=0, pending=10)


def hkjc_probe(package, registration):
    folder = package / 'hkjc-clock-check'
    ref = intake.read(folder / 'request-metadata.json')
    browser = intake.read(folder / 'browser-failure.json')
    body = (folder / 'raw/hkjc-public-football-home.html').read_bytes()
    _, fixtures, slates, _ = display._registered(intake.read(registration))
    earliest = min(aware(fixtures[mid]['kickoff_at']) for mid in slates['nov28_29'])
    original = {mid for mid in slates['nov28_29'] if aware(fixtures[mid]['kickoff_at']) == earliest}
    targets = intake.read(folder / 'targets.json')
    if ({row['espn_match_id'] for row in targets} != original or len(targets) != len(original)
            or any(aware(row['kickoff_utc']) != earliest
                   or (row['home_espn_id'], row['away_espn_id']) !=
                   (fixtures[row['espn_match_id']]['home'], fixtures[row['espn_match_id']]['away'])
                   for row in targets)):
        raise ValueError('HKJC probe does not refer to the original first wave')
    if (ref['http_status'] != 200 or ref['response_bytes'] != len(body)
            or sha256(body).hexdigest() != ref['response_sha256'] or b'<div id="root"></div>' not in body
            or browser['navigation_url'] != ref['url'] or browser['tls_verification'] != 'default enabled'):
        raise ValueError('HKJC page format or original browser observation differs')
    return dict(targets=len(targets), matched_market_rows=0,
                http_status=ref['http_status'], retrieved_at=ref['response_received_utc'],
                browser_error=browser['error'])


def compare_frozen_scores(rows, baseline, candidate, seats):
    """List exactly which future scores could change a registered pair's hit count."""
    first_pairs, list_pairs, orders, first, members = 0, 0, 0, {}, {}
    for mid, arms in rows.items():
        before, after = (arms[name] for name in (baseline, candidate))
        old_first, new_first = before.get('primary'), after.get('primary')
        if old_first is not None and new_first is not None:
            first_pairs += 1
            if old_first != new_first:
                first[mid] = dict(gain_if=new_first, loss_if=old_first)
        old_list, new_list = before.get('top3'), after.get('top3')
        if old_list is not None and new_list is not None:
            list_pairs += 1
            orders += old_list != new_list
            added, removed = set(new_list) - set(old_list), set(old_list) - set(new_list)
            if added or removed:
                members[mid] = dict(gain_if=sorted(added), loss_if=sorted(removed))
    return dict(baseline=baseline, candidate=candidate, first_comparable=first_pairs,
                three_comparable=list_pairs, ordered_three_changes=orders, first_differences=first,
                three_membership_differences=members, baseline_seats=seats.get(baseline),
                candidate_seats=seats.get(candidate))


def frozen_differences(folders, registration):
    _, fixtures, slates, _ = display._registered(intake.read(registration))
    population = set(slates['nov28_29'])
    reports = {}
    for folder in folders:
        index = intake.read(folder / 'receipts.json')
        plan = ledger._read(folder, index['registration'])
        identity = plan['payload']['identity']
        track = plan['payload']['track']
        if (track in reports or set(index['matches']) != population
                or set(identity['forecast_sha256']) != population):
            raise ValueError('expected each frozen comparison with the complete weekend population')
        rows = {}
        for mid, ref in index['matches'].items():
            record = ledger._read(folder, ref)
            acquired.same_fixture(fixtures[mid], record['fixture'])
            payload = dict(record['payload'])
            if (payload.pop('registration_sha256') != plan['record_sha256']
                    or digest(payload) != identity['forecast_sha256'][mid]
                    or not aware(plan['recorded_at']) <= aware(record['recorded_at']) <= AS_OF):
                raise ValueError('original pregame forecast or its clock differs: ' + mid)
            rows[mid] = payload['forecasts']
        compared = {pair: compare_frozen_scores(rows, *arms, identity.get('selected', {}))
                    for pair, arms in identity['pairs'].items()}
        reports[track] = dict(freeze_id=plan['freeze_id'], registered=len(rows), pairs=compared)
    return reports


def score_review_freeze(package, data, registration, ranked, differences):
    record = verify(intake.read(package / 'score-review-freeze.json'))
    previous = verify(intake.read(data / '20261127-europe-round1-review/review-freeze.json'))
    _, fixtures, slates, _ = display._registered(intake.read(registration))
    first_kickoff = min(aware(fixtures[mid]['kickoff_at']) for mid in slates['nov28_29'])
    payload = record['payload']
    if (record['stage'] != 'review' or record['track'] != 'first-stage-score-review'
            or payload['original_europe_review_sha256'] != previous['record_sha256']
            or payload['european_total_and_split_sha256'] != digest(ranked)
            or payload['j1_frozen_score_differences_sha256'] != digest(differences)
            or payload['j1_research_registrations'] != {track: row['freeze_id'] for track, row in differences.items()}
            or not aware(previous['recorded_at']) <= aware(record['recorded_at']) < first_kickoff
            or aware(record['fixture']['kickoff_at']) != first_kickoff):
        raise ValueError('score review decision differs from the verified European and pregame J1 evidence')
    return dict(freeze_id=record['freeze_id'], recorded_at=record['recorded_at'])


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
    ranked = ranked_europe(data)
    differences = frozen_differences(research, nov_reg)
    review_freeze = score_review_freeze(package, data, nov_reg, ranked, differences)
    with TemporaryDirectory(prefix='phase-one-replay-') as tmp:
        root = Path(tmp)
        return dict(as_of=AS_OF.isoformat(), historical_j1=historical(data, root / 'nov25', nov_reg),
                    upcoming={
                        'nov28_29': forthcoming(data, root, nov_reg, nov_bind, 'nov28_29', research),
                        'dec04_06': forthcoming(data, root, dec_reg, dec_bind, 'dec04_06', binding_root=dec_official),
                        'dec12_13': forthcoming(data, root, dec_reg, dec_bind, 'dec12_13', binding_root=dec_official),
                    }, historical_scorecard=scorecard(data), europe_score_ranking=ranked,
                    upcoming_market_probe=market_probe(data, package / 'market-probe', nov_reg),
                    jleague_espn_wave_rehearsal=result_wave_rehearsal(package, root, nov_reg, nov_bind, research),
                    hkjc_probe=hkjc_probe(package, nov_reg),
                    frozen_score_differences=differences, score_review_freeze=review_freeze,
                    market_checkpoint_samples={name: first_checkpoint(data, package / name, nov_reg)
                                               for name in ('market-t24', 'market-t24-recheck')})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, required=True, help='repository containing the pinned original evidence')
    args = parser.parse_args()
    print(json.dumps(run(args.data_root.resolve() / 'workspace-updates'), ensure_ascii=False,
                     indent=2, sort_keys=True, allow_nan=False))
