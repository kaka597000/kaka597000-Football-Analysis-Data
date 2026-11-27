"""Reproduce the review of the 32 original briefing fixtures from archived evidence."""
import argparse
import csv
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from optimization.evaluate import settle_ou
from research.analysis_freeze import aware, verify
from research_program.selection_review import compare
from research_program.three_arm_review import _certify
from v5.paired_review import review as review_pairs

ROOT = Path(__file__).resolve().parent
DIRECTIONS = {'主胜': 'home', '客胜': 'away', '平': 'draw', '平局': 'draw'}
SIDES = {'大': 'over', '小': 'under'}
OUTCOMES = ('FULL_WIN', 'HALF_WIN', 'PUSH', 'HALF_LOSS', 'FULL_LOSS')
UTC = timezone.utc


def read(path):
    return json.loads(path.read_bytes())


def original(freeze_id):
    record = verify(read(ROOT / 'originals' / (freeze_id + '.json')))
    assert record['freeze_id'] == freeze_id
    return record


def first(record, match_id, track, actual_start):
    fixture = record['fixture']
    assert record['match_id'] == fixture['match_id'] == match_id
    assert record['track'] == track and record['stage'] == 'prematch'
    assert record['revision'] == 1 and record['evaluation_slot'] == 'FIRST_PREMATCH'
    assert record['previous_sha256'] is None
    assert aware(fixture['cutoff_at']) <= aware(record['recorded_at']) < min(
        aware(fixture['kickoff_at']), actual_start)
    return fixture


def sources():
    meta = read(ROOT / 'sources.json')
    body = {}
    for name, entry in meta.items():
        if 'file' not in entry:
            continue
        path = (ROOT / entry['file']).resolve()
        assert path.is_relative_to(ROOT)
        raw = gzip.decompress(path.read_bytes())
        assert hashlib.sha256(raw).hexdigest() == entry['body_sha256']
        body[name] = json.loads(raw)
    return meta, body


def fotmob_finals(meta, body):
    rows = {}
    for key in ('fotmob-20261124', 'fotmob-20261125', 'fotmob-20261126'):
        for league in body[key]['leagues']:
            for match in league['matches']:
                status = match['status']
                if not status.get('finished') or status.get('reason', {}).get('short') != 'FT':
                    continue
                match_id = str(match['id'])
                actual = (match['home']['score'], match['away']['score'])
                if match_id in rows:
                    assert rows[match_id][0] == actual
                rows[match_id] = actual, match, meta[key]['url']
    return rows


def results(raw, fixture, meta, now, fotmob):
    event = raw['header']['competitions'][0]
    es_score = {team['homeAway']: int(team['score']) for team in event['competitors']}
    goals, secondary, second_url = fotmob
    assert goals == (es_score['home'], es_score['away'])
    listed = aware(secondary['status']['utcTime'])
    assert listed == aware(fixture['kickoff_at'])
    # FotMob shows both scheduled and actual starts on the same display clock.
    # Infer its per-fixture UTC offset from that row's explicit scheduled UTC.
    displayed = datetime.strptime(secondary['time'], '%d.%m.%Y %H:%M')
    start = datetime.strptime(secondary['status']['halfs']['firstHalfStarted'], '%d.%m.%Y %H:%M:%S')
    actual_start = listed + (start - displayed)
    assert abs(actual_start - listed) < timedelta(hours=2)
    result = {key: fixture[key] for key in ('match_id', 'cohort', 'stage', 'home', 'away', 'kickoff_at')}
    result.update(status='FT', event_status='FT', score_basis='regulation_90',
                  home_goals=es_score['home'], away_goals=es_score['away'], source_url=meta['url'],
                  known_at=meta['captured_at'], observed_at=meta['captured_at'],
                  raw_reference={'source_url': meta['url'], 'captured_at': meta['captured_at'],
                                 'sha256': meta['body_sha256'], 'path': meta['file']})
    certified = _certify(result, fixture, ROOT, now)
    assert (certified['home'], certified['away']) == goals
    assert aware(result['known_at']) >= actual_start + timedelta(minutes=90)
    result.update(secondary_url=second_url, actual_start_at=actual_start.isoformat())
    return result, actual_start


def grade(tip, actual):
    h, a = actual['home_goals'], actual['away_goals']
    score = f'{h}-{a}'
    wdl = 'home' if h > a else 'away' if h < a else 'draw'
    scores = tip['top3']
    if scores:
        assert len(scores) == len(set(scores)) == 3
    assert tip['primary'] is None or scores[0] == tip['primary']
    line, side = tip['total_line'], tip['total_side']
    assert (line is None) == (side is None)
    return dict(tip, first_hit=None if tip['primary'] is None else score == tip['primary'],
                three_hit=None if not scores else score in scores,
                observed_rank=(scores.index(score) + 1 if score in scores else None),
                wdl_hit=None if tip['wdl'] is None else wdl == tip['wdl'],
                settlement=None if line is None else settle_ou(h + a, line, side))


def model_tip(model):
    total = model.get('total') or {}
    side = total.get('reference_direction')
    return {'primary': model.get('primary'), 'top3': [v['score'] for v in model.get('top3') or []],
            'wdl': DIRECTIONS.get(model.get('wdl_reference')), 'total_side': side,
            'total_line': total['quote']['line'] if side else None, 'version': model['version'],
            'training_data_cutoff': model.get('training_data_cutoff')}


def summarize(grades):
    counts = Counter(row['settlement'] for row in grades)
    result = {}
    for key in ('first_hit', 'three_hit', 'wdl_hit'):
        vals = [row[key] for row in grades if row[key] is not None]
        result[key] = [sum(vals), len(vals)]
    result['total_full_win'] = [counts['FULL_WIN'], sum(counts[k] for k in OUTCOMES if k != 'PUSH')]
    result['total_outcomes'] = {key: counts[key] for key in OUTCOMES}
    result['observed_score_ranks'] = dict(sorted(Counter(
        str(row['observed_rank'] or 'outside') for row in grades if row['three_hit'] is not None
    ).items()))
    return result


def batch_order(record):
    payload = record['payload']
    if record['track'] == 'top3-selection':
        assert [r['rank'] for r in payload['top3']] == list(range(1, len(payload['top3']) + 1))
        return [r['match_id'] for r in payload['top3']], payload['planned_slots']
    assert record['track'] == 'j1-comprehensive-windows-20261125-nov25-registration'
    identity = payload['identity']
    slots = identity['slots']
    return identity['selected'], slots if isinstance(slots, int) else len(slots)


def make_review():
    meta, body = sources()
    as_of = max(aware(v['captured_at']) for v in meta.values() if 'captured_at' in v)
    assert as_of <= datetime.now(UTC)
    schedule = read(ROOT / 'inputs.json')
    assert len(schedule) == len({r['match_id'] for r in schedule}) == 32
    fotmob = fotmob_finals(meta, body)
    uefa = {row['id']: row for row in body['uefa-2026-11-25']}
    mapping = {row['espn_event_id']: row for row in read(ROOT / 'uefa-identity.json')}
    rows, entries, first_pairs, paired_results = [], [], [], []
    selected = defaultdict(list)
    tracks = defaultdict(list)
    for row in schedule:
        mid = row['match_id']
        espn_id = mid.removeprefix('espn:')
        espn = 'espn-' + espn_id
        rec = original(row['original'])
        f = rec['fixture']
        assert aware(f['kickoff_at']) == aware(row['kickoff_scheduled_bjt'])
        assert f['cohort'].split(':')[0] == row['competition_code']
        actual, start = results(body[espn], f, meta[espn], as_of, fotmob[row['fotmob_match_id']])
        if row['window'] == '20261126_ucl':
            ref = mapping[espn_id]
            official = uefa[ref['uefa_match_id']]
            assert official['status'] == 'FINISHED'
            assert official['homeTeam']['id'] == ref['uefa_home_id']
            assert official['awayTeam']['id'] == ref['uefa_away_id']
            assert aware(official['kickOffTime']['dateTime']) == aware(f['kickoff_at'])
            assert official['score']['regular'] == {'home': actual['home_goals'], 'away': actual['away_goals']}
            actual['official_url'] = ref['uefa_public_match_url']

        p = rec['payload']
        is_formal = 'paired_first' in row
        prefix = '' if is_formal else 'research_'
        hash_key, time_key = (('freeze_sha256', 'freeze_recorded_bjt') if is_formal
                              else ('research_sha256', 'research_recorded_bjt'))
        verify_fields = (row[prefix + 'freeze_id'], row[hash_key], row[time_key])
        assert verify_fields == (rec['freeze_id'], rec['record_sha256'], rec['recorded_at'])
        group = 'comprehensive' if is_formal else 'R7'
        first(rec, mid, 'comprehensive' if is_formal else row['research_track_id'], start)
        if is_formal:
            displayed = p.get('authored_display')
            if displayed is None:
                assert row['competition_code'] == 'afc.champions'
                assert [p['primary'], *p['ordered_alternatives']] == p['top3']
            else:
                assert displayed['status'] == 'ISSUED'
                assert p['displayed_scores'] == [displayed['first'], *displayed['alternatives']] == p['top3']
            tip = dict(primary=p['primary'], top3=p['top3'], wdl=DIRECTIONS[p['wdl']],
                       total_side=SIDES.get(p['total_direction'], p['total_direction']), total_line=p['total_line'])
        else:
            tip = p['forecasts']['candidate']
        assert tip['top3'] == [row[prefix + field] for field in ('primary', 'alternate_1', 'alternate_2')]
        assert tip['wdl'] == DIRECTIONS[row[prefix + 'wdl']]
        assert tip['total_side'] == SIDES.get(row[prefix + 'ou_direction'])
        line = row[prefix + 'ou_line']
        assert tip['total_line'] == (float(line) if line else None)
        item = dict(window=row['window'], competition=row['competition_code'], track=group, match_id=mid,
                    home=row['home_zh'], away=row['away_zh'], kickoff_bjt=row['kickoff_scheduled_bjt'],
                    reported_actual_start=actual['actual_start_at'], result=f"{actual['home_goals']}-{actual['away_goals']}",
                    source_url=actual.get('official_url', actual['source_url']), second_result_url=actual['secondary_url'],
                    first_issue=rec['freeze_id'], first_clock=rec['recorded_at'], first_sha256=rec['record_sha256'],
                    first_source_url=row[prefix+'freeze_evidence_url'] if is_formal else row['research_evidence_url'],
                    grade=grade(tip, actual), result_evidence=actual)
        rows.append(item)
        tracks[(group, 'all')].append(item['grade'])
        tracks[(group, row['competition_code'])].append(item['grade'])
        if is_formal:
            pair, reference = original(row['paired_first']), original(row['paired_reference'])
            first(pair, mid, 'current-test-pair', start)
            assert aware(pair['recorded_at']) <= aware(reference['recorded_at'])
            paired_results.append(actual)
            first_pairs.append(pair['payload'])
            entries.append(dict(comprehensive=rec, pair=reference))
            item.update(pair_first=pair['freeze_id'], pair_clock=pair['recorded_at'],
                        pair_sha256=pair['record_sha256'], referenced_pair=reference['freeze_id'])
            item['model_grades'] = {}
            for model in ('current_model', 'test_model'):
                decision = grade(model_tip(pair['payload'][model]), actual)
                tracks[(model, row['competition_code'] + ' / ' + decision['version'])].append(decision)
                item['model_grades'][model] = decision
            batch = row['selection_batch_freeze_id']
            if batch and row['original_top3_rank']:
                selected[batch].append((int(row['original_top3_rank']), mid, item['grade']))
        else:
            assert tip['total_line'] == p['line']
            forecast = p['forecasts']['market']
            market = grade(dict(primary=None, top3=[], wdl=None, total_line=None, total_side=None) | forecast, actual)
            item['r7_market_grade'] = market
            tracks[('R7 market', 'all')].append(market)
            tracks[('R7 market', row['competition_code'])].append(market)

    batch_summary = {}
    for batch, picks in selected.items():
        ordered = sorted(picks)
        rec = original(batch)
        f = rec['fixture']
        first(rec, rec['match_id'], rec['track'], min(
            aware(item['reported_actual_start']) for item in rows if item['match_id'] in {p[1] for p in picks}))
        match_ids, seats = batch_order(rec)
        assert seats == 3 and [m for _, m, _ in ordered] == match_ids
        grades = [g for _, _, g in ordered]
        batch_summary[batch] = dict(seats=seats, occupied=len(ordered), matches=match_ids,
                                    all_three_firsts_hit=(all(g['first_hit'] for g in grades)
                                                          if len(ordered) == seats else None),
                                    **summarize(grades))
    return {'as_of': as_of.isoformat(), 'matches': rows,
            'summaries': {f'{track} | {league}': summarize(grades) for (track, league), grades in sorted(tracks.items())},
            'original_ranked_batches': batch_summary, 'first_pair_strict_review': review_pairs(first_pairs, paired_results),
            'comprehensive_vs_cited_pair': compare(entries, paired_results)}


def export(report, output):
    output.mkdir(parents=True, exist_ok=True)
    (output / 'results.json').write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + '\n')
    rows = []
    for item in report['matches']:
        g = item['grade']
        row = {k: item[k] for k in ('window','competition','track','match_id','home','away','kickoff_bjt',
                                    'result','first_issue','first_clock','first_sha256','first_source_url',
                                    'source_url','second_result_url')}
        row.update(primary=g['primary'], alternate_1=g['top3'][1], alternate_2=g['top3'][2],
                   first_hit=g['first_hit'], three_hit=g['three_hit'], rank_of_result=g['observed_rank'],
                   wdl=g['wdl'], wdl_hit=g['wdl_hit'], total_line=g['total_line'], total_side=g['total_side'],
                   total_settlement=g['settlement'])
        rows.append(row)
    with (output / 'settlements.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT)
    args = parser.parse_args()
    export(make_review(), args.out)
