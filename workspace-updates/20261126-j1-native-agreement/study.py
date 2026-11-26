"""Compare original archived J1 first choices on the fixed eighteen-match archive."""

from collections import Counter
import json
from pathlib import Path
import tarfile
from zoneinfo import ZoneInfo

from research.analysis_freeze import aware, verify
from research_program.paired_kpi_inference import compare
from research_program.three_arm_review import _results


ROOT = Path(__file__).resolve().parent
NOV25 = ROOT.parent / '20261125-j1-stage-windows/nov25'
NOV25_STATE = ROOT.parent / '20261126-j1-forward-result-review/nov25-state'
BEIJING = ZoneInfo('Asia/Shanghai')
FIXTURE_KEYS = ('match_id', 'cohort', 'home', 'away')
STAGES = {'regular', 'regular-season', 'Japanese J1 League'}


def read(path):
    return json.loads(path.read_bytes())


def first(body, reference, fixture, track):
    record = verify(json.loads(body))
    saved = record['fixture']
    if (record['freeze_id'] != reference['id'] or record['record_sha256'] != reference['sha256']
            or record['track'] != track or record['stage'] != 'prematch'
            or record['evaluation_slot'] != 'FIRST_PREMATCH' or record['revision'] != 1
            or record['previous_sha256'] is not None
            or any(saved[k] != fixture[k] for k in FIXTURE_KEYS)
            or saved['stage'] not in STAGES or fixture['cohort'] != 'jpn.1'
            or aware(saved['kickoff_at']) != aware(fixture['kickoff_at'])
            or aware(record['recorded_at']) >= aware(fixture['kickoff_at'])):
        raise ValueError('original J1 first issue differs for ' + fixture['match_id'])
    return record


def choices(payload, *, native=False):
    key = 'top3' if native else 'displayed_scores'
    ordered = [entry['score'] if isinstance(entry, dict) else entry for entry in (payload.get(key) or [])]
    primary = payload.get('primary')
    if ordered and (len(ordered) != 3 or len(set(ordered)) != 3 or ordered[0] != primary):
        raise ValueError('invalid recorded ordered scores')
    return dict(primary=primary, top3=ordered or None)


def original_choices(inventory):
    publication_reference = read(NOV25 / 'publication.json')
    publication = verify(read(NOV25 / publication_reference['file']))
    if publication['record_sha256'] != inventory['first_window_sha256']:
        raise ValueError('original November 25 publication differs')
    published_refs = publication['payload']['identity']['rows']
    observed_published = set()
    with tarfile.open(ROOT / 'older-firsts.tar.gz') as archive:
        for mid, row in inventory['matches'].items():
            fixture = row['fixture']
            if row['source'] == 'nov25':
                observed_published.add(mid)
                if any(published_refs[mid][k]['sha256'] != row[k]['sha256'] for k in ('authored', 'pair')):
                    raise ValueError('inventory differs from original publication: ' + mid)
                body = lambda ref: (NOV25 / ref['file']).read_bytes()
            elif row['source'] == 'canonical':
                body = lambda ref: archive.extractfile('./' + ref['file']).read()
            else:
                raise ValueError('unknown original archive')
            authored = first(body(row['authored']), row['authored'], fixture, 'comprehensive')
            authored_payload = authored['payload']
            forecasts = {'comprehensive': choices(authored_payload)}
            status = {}
            if row['pair']:
                pair = first(body(row['pair']), row['pair'], fixture, 'current-test-pair')
                link = authored_payload.get('current_test_reference') or {}
                if (link.get('sha256') != pair['record_sha256'] or row['original_pair_link'] != pair['record_sha256']
                        or link.get('freeze_id', pair['freeze_id']) != pair['freeze_id']
                        or aware(pair['recorded_at']) > aware(authored['recorded_at'])):
                    raise ValueError('archive pair is not the originally cited first issue for ' + mid)
                for model in ('current', 'test'):
                    value = pair['payload'][model + '_model']
                    forecasts[model] = choices(value, native=True)
                    status[model] = value.get('status')
            yield mid, fixture, forecasts, status
    if observed_published != set(published_refs):
        raise ValueError('an archived November 25 slot is missing')


def verified_results(inventory):
    folders = [ROOT / 'october', ROOT / 'november', NOV25_STATE]
    folders = [p for p in folders if (p / 'normalized-results.jsonl').exists()]
    times = [aware(inventory['locked_at'])]
    for path in folders:
        times.extend(aware(json.loads(line)['known_at'])
                     for line in (path / 'normalized-results.jsonl').read_text().splitlines())
    now = max(times)
    fixtures = {mid: dict(r['fixture'], stage='Japanese J1 League') for mid, r in inventory['matches'].items()}
    results, issues = {}, {}
    for path in folders:
        verified, problems = _results(path.resolve(), fixtures, now)
        if results.keys() & verified.keys():
            raise ValueError('overlapping result archives')
        results.update(verified)
        issues.update(problems)
    return results, issues, now


def agreement(rows):
    cases = []
    counts = Counter()
    for r in rows:
        forecast = r['forecast']
        current = forecast.get('current', {}).get('primary')
        test = forecast.get('test', {}).get('primary')
        authored = forecast['comprehensive']['primary']
        if not current or current != test:
            continue
        counts['both_models_agree'] += 1
        if not authored:
            counts['author_abstained'] += 1
            continue
        actual = '-'.join(map(str, r['actual'])) if r['actual'] else None
        if authored == current:
            counts['author_retained'] += 1
            continue
        counts['author_changed'] += 1
        if actual is None:
            verdict = 'pending'
        elif actual == authored:
            verdict = 'gained'
        elif actual == current:
            verdict = 'lost'
        else:
            verdict = 'both_missed'
        counts[verdict] += 1
        cases.append(dict(match_id=r['id'], model_first=current, authored_first=authored, actual=actual, verdict=verdict))
    keys = ('both_models_agree', 'author_abstained', 'author_retained', 'author_changed',
            'pending', 'gained', 'lost', 'both_missed')
    return dict(counts={key: counts[key] for key in keys}, net_hits=counts['gained']-counts['lost'], changes=cases)


def study():
    inventory = read(ROOT / 'population.json')
    if len(inventory['matches']) != 18:
        raise ValueError('original archival population differs')
    original = list(original_choices(inventory))
    actuals, issues, now = verified_results(inventory)
    rows = []
    for mid, fixture, forecasts, status in original:
        actual = actuals.get(mid)
        day = aware(fixture['kickoff_at']).astimezone(BEIJING).date().isoformat()
        rows.append(dict(id=mid, date=day, cohort=fixture['cohort'],
                         actual=[actual['home'], actual['away']] if actual else None,
                         line=None, forecast=forecasts, native_status=status,
                         result_source_sha256=actual['source']['sha256'] if actual else None))
    comparisons = {model: compare(rows, baseline=model, candidate='comprehensive') for model in ('current', 'test')}
    summary = {arm: dict(first_hits=value['metrics']['score_top1']['hits'],
                         first_eligible=value['metrics']['score_top1']['eligible'],
                         three_hits=value['metrics']['score_top3']['hits'],
                         three_eligible=value['metrics']['score_top3']['eligible'])
               for arm, value in (comparisons['current']['tracks'] | comparisons['test']['tracks']).items()}
    return dict(as_of=now.isoformat(), population=len(rows), settled=len(actuals), metrics=summary,
                agreement=agreement(rows), paired=comparisons, per_match=rows, result_issues=issues)


if __name__ == '__main__':
    print(json.dumps(study(), ensure_ascii=False, indent=2, allow_nan=False))
