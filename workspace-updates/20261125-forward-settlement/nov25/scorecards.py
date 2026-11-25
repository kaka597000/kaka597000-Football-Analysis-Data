"""Publish the original nine firsts, signed native tracks, market and every reserved seat."""
import argparse
import csv
from hashlib import sha256
from io import BytesIO, StringIO
import json
from pathlib import Path
import tarfile

from research.analysis_freeze import aware
from research_program.display_market import WDL
from research_program.kpi_validation import _first
from research_program.paired_kpi_inference import compare

import package_review
import afc_finals


def native_pairs(archive, prefix):
    result = {}
    for member in archive:
        if not member.name.startswith(prefix) or not member.name.endswith('-v000001.json'):
            continue
        record = json.load(archive.extractfile(member))
        if record['track'] == 'current-test-pair':
            record = _first(record, 'current-test-pair')
            if record['match_id'] in result:
                raise ValueError('duplicate original native first')
            result[record['match_id']] = record
    return result


def native_pick(model, line):
    tips = dict(primary=model['primary'], top3=[r['score'] for r in model['top3']], wdl=WDL[model['wdl_reference']])
    total = model.get('total') or {}
    side = total.get('reference_direction')
    if side in ('over', 'under'):
        if total['quote']['line'] != line:
            raise ValueError('native total reference uses a different original line')
        tips.update(total_side=side, total_line=line)
    return tips


def as_csv(rows):
    stream = StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=rows[0], lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def observed_ranks(rows, arm):
    counts = dict(first=0, second=0, third=0, outside_three=0, unissued=0, pending=0)
    ranks = ('first', 'second', 'third')
    for row in rows:
        scores = (row['forecast'].get(arm) or {}).get('top3') or []
        if row['actual'] is None:
            counts['pending'] += 1
        elif len(scores) != 3 or len(set(scores)) != 3:
            counts['unissued'] += 1
        else:
            actual = '-'.join(map(str, row['actual']))
            key = ranks[scores.index(actual)] if actual in scores else 'outside_three'
            counts[key] += 1
    return counts


def report_from(archive_path):
    with tarfile.open(archive_path) as archive:
        report = json.load(archive.extractfile('snapshot/ft-review.json'))
        pairs = native_pairs(archive, 'updates/20261125-j1-stage-windows/nov25/')
        nested = archive.extractfile('updates/20261125-r10-shot-conversion/formal/nov25-issues-and-evidence.tar.gz').read()
        with tarfile.open(fileobj=BytesIO(nested)) as second:
            pairs.update(native_pairs(second, 'canonical/'))
    if set(pairs) != set(report['J1']['rows']) | set(report['AFC']['rows']):
        raise ValueError('expected a signed pair for every original fixture')
    fixtures, seats, summaries = [], [], {}
    afc_checks = afc_finals.crosscheck(report['AFC']['rows'], report['at'])
    for comp in ('J1', 'AFC'):
        batch = report[comp]
        slate = batch['archived_seats']
        metrics_rows = []
        for mid, row in batch['rows'].items():
            fx, tips, actual = row['fixture'], row['candidate'], row['actual']
            pair = pairs[mid]
            if (pair['record_sha256'] != row['pair'] or pair['fixture']['match_id'] != mid
                    or aware(pair['recorded_at']) >= aware(fx['kickoff_at'])):
                raise ValueError('native first or original kickoff differs')
            arms = {role: native_pick(pair['payload'][role + '_model'], tips['total_line']) for role in ('current', 'test')}
            arms.update(authored=tips, market=row['market'])
            metrics_rows.append(dict(id=mid, cohort=fx['cohort'], date=fx['date'], actual=actual,
                                     forecast=arms, line=tips['total_line']))
            outcome = row['archived_first_outcomes']
            check = report['result_crosscheck'][mid]
            fixtures.append(dict(competition=comp, id=mid, home=fx['display_home'], away=fx['display_away'],
                kickoff=fx['kickoff_at'], first=tips['primary'], second=tips['top3'][1], third=tips['top3'][2],
                wdl=tips['wdl'], line=tips['total_line'], side=tips['total_side'],
                regulation_score='-'.join(map(str, actual)) if actual is not None else '',
                first_hit=outcome['score_top1'], three_hit=outcome['score_top3'], wdl_hit=outcome['wdl'],
                total_settlement=row['archived_total_settlement'], current_first=arms['current']['primary'],
                test_first=arms['test']['primary'], market_first=arms['market']['primary'], first_sha256=row['first'],
                native_pair_sha256=row['pair'], strict_quote=row['strict_quote'], delivery_verified=row['channel_first_verified'],
                crosscheck=afc_checks.get(mid, check)['verdict']))
        for seat in range(1, slate['planned'] + 1):
            slot = next((s for s in slate['seats'] if s['seat'] == seat), {})
            seats.append(dict(competition=comp, seat=seat, occupied=bool(slot), match_id=slot.get('match_id'),
                              primary=slot.get('primary'), actual=slot.get('actual'), first_hit=slot.get('first_hit'),
                              three_hit=slot.get('top3_hit')))
        tracks, paired = {}, {}
        for name in ('current', 'test', 'authored'):
            scored = compare(metrics_rows, baseline='market', candidate=name)
            tracks.update(scored['tracks'])
            paired[name] = scored['paired']
        summaries[comp] = dict(registered=batch['registered'], settled=batch['completed'], original=batch['registration'],
            publication=batch['publication'], body_sha256=batch['body_sha256'], observed_lines=batch['observed_lines'],
            strict_lines=batch['strict_lines'], archived_selected=slate, channel_certification=batch['certified_channel'],
            comparison=tracks, market_paired=paired,
            actual_score_ranks={name: observed_ranks(metrics_rows, name) for name in ('current', 'test', 'market', 'authored')})
        if comp == 'AFC':
            summaries[comp]['independent_final_sources'] = afc_checks
    research = {}
    for name, info in report['research'].items():
        research[name] = {k: info[k] for k in ('registration', 'original_population', 'cumulative_settled', 'tonight_registered',
                                                'tonight_settled', 'pending', 'original_seats')}
        research[name]['tracks'] = info['original_first_vs_market']['tracks']
    summary = dict(as_of=report['at'], certified_ft90=report['certified_ft90'], pending=report['pending'], competitions=summaries,
                   research=research)
    return {'fixtures.csv': as_csv(fixtures), 'selected.csv': as_csv(seats), 'results.json': package_review.review.encoded(summary)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--write-new', type=Path)
    args = parser.parse_args()
    integrity = package_review.verify(args.archive)
    root = args.write_new or Path(__file__).resolve().parent
    if args.write_new:
        root.mkdir(parents=True, exist_ok=True)
    for name, body in report_from(args.archive).items():
        path = root / name
        if args.write_new and not path.exists():
            with path.open('xb') as dest:
                dest.write(body)
        if sha256(path.read_bytes()).digest() != sha256(body).digest():
            raise ValueError('published scorecard differs from signed records: ' + name)
    print(json.dumps(integrity, ensure_ascii=False))


if __name__ == '__main__':
    main()
