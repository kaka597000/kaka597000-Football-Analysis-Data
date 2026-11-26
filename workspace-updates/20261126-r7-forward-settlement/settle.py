"""Replay the original R7 firsts with the ten additional verified November 26 results."""

from collections import defaultdict
from datetime import timedelta, timezone
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import tarfile
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

from research.analysis_freeze import aware, verify
from research_program.kpi_validation import _actual
from research_program.nov25_first_review import same_fixture
from research_program.paired_kpi_inference import compare
from research_program.three_arm_review import _certify


ROOT = Path(__file__).resolve().parent
UPDATES = ROOT.parent
PREVIOUS = UPDATES / '20261125-forward-settlement/nov25'
AT = '2026-11-26T14:57:31.629215+08:00'
DAY = '2026-11-26'
BEIJING = ZoneInfo('Asia/Shanghai')
OLD_ARCHIVE_SHA = '2ad0d42fa60f2ddde28a2cf4a161f1ac8cae1c2afef27dcf8083b53a466ace38'
ORIGINALS_SHA = '76af627e35085d1de5fc268e7c36ba121aa3cadc23f7a2aeaad8fb89e62d32b9'
PROVIDERS = {
    'uefa.champions': ('UEFA Champions League, League Phase',
                       'uefa.champions:NEW_FORMAT:league_phase', 'NEW_FORMAT:league_phase', 14534),
    'bra.1': ('Brazil Serie A', 'bra.1', 'regular', 13907),
}


def sha(body):
    return hashlib.sha256(body).hexdigest()


def source_module():
    file = PREVIOUS / 'originals.py'
    if sha(file.read_bytes()) != ORIGINALS_SHA:
        raise ValueError('published R7 source reader differs')
    spec = importlib.util.spec_from_file_location('original_r7_sources', file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def earlier_results(source, access, records, plan, work):
    package = PREVIOUS / 'evidence.tar.gz'
    if sha(package.read_bytes()) != OLD_ARCHIVE_SHA:
        raise ValueError('published November 25 evidence differs')
    with tarfile.open(package) as archive:
        snapshot = json.load(archive.extractfile('snapshot/ft-review.json'))
        original = snapshot['research']['R7']
        at = aware(snapshot['at'])
        earlier = source.r7_prior(access, work, records, at)
        if (original['registration'] != plan['record_sha256'] or len(earlier) != 33
                or earlier.keys() & original['tonight_firsts'].keys()):
            raise ValueError('the prior R7 result set differs from the original registration')
        old_actual = {mid: ref['score'] for mid, ref in earlier.items()}
        evidence = work / 'old-night-results'
        evidence.mkdir()
        for mid, settlement in original['tonight_firsts'].items():
            frozen = records[mid]
            f = frozen['fixture']
            if settlement['first_sha256'] != frozen['record_sha256']:
                raise ValueError('previous label is attached to another first issue')
            label = snapshot['certified_labels'][mid]
            same_fixture(f, label)
            meta = label['evidence']
            body = archive.extractfile('intake/' + meta['file']).read()
            if sha(body) != meta['sha256']:
                raise ValueError('prior result source checksum differs')
            file = mid.replace(':', '-') + '.json'
            (evidence / file).write_bytes(body)
            aligned = dict(label, cohort=f['cohort'], stage=f['stage'], kickoff_at=f['kickoff_at'],
                           evidence=dict(meta, file=file))
            actual = list(_actual(aligned, f, evidence, at))
            if actual != settlement['actual']:
                raise ValueError('prior R7 regulation result differs')
            old_actual[mid] = actual
    if len(old_actual) != original['cumulative_settled'] or len(old_actual) != 42:
        raise ValueError('expected the original forty-two settled firsts')
    return old_actual, original['original_first_vs_market']


def newly_settled(records, already):
    state = (ROOT / 'state').resolve()
    labels = [json.loads(line) for line in (state / 'normalized-results.jsonl').read_text().splitlines()]
    match_ids = {row['match_id'] for row in labels}
    now = aware(AT)
    eligible = {mid for mid, r in records.items()
                if aware(r['fixture']['kickoff_at']) + timedelta(minutes=90) <= now}
    if (len(labels) != 10 or len(match_ids) != 10 or set(already) & match_ids or
            match_ids != eligible - set(already)):
        raise ValueError('new evidence differs from the full due original population')
    certified = {}
    for label in labels:
        mid = label['match_id']
        record = records[mid]
        f = record['fixture']
        stage, cohort, normalized_stage, season_type = PROVIDERS[f['cohort']]
        meta = label['raw_reference']
        path = (state / meta['path']).resolve()
        if not path.is_relative_to(state):
            raise ValueError('result evidence outside archive')
        raw = gzip.decompress(path.read_bytes())
        header = json.loads(raw)['header']
        kickoff = aware(f['kickoff_at']).astimezone(BEIJING)
        if (f['stage'] != stage or label['cohort'] != cohort or label['stage'] != normalized_stage
                or header['league']['slug'] != f['cohort']
                or header['season']['year'] != 2026 or header['season']['type'] != season_type
                or kickoff.date().isoformat() != DAY or aware(record['recorded_at']) >= kickoff
                or sha(raw) != meta['sha256']):
            raise ValueError('finished match is outside the original research scope: ' + mid)
        target = dict(f, cohort=cohort, stage=normalized_stage)
        actual = _certify(label, target, state, now)
        certified[mid] = dict(fixture=f, score=[actual['home'], actual['away']], result_source=meta,
                              first_issue={'id': record['freeze_id'], 'recorded_at': record['recorded_at'],
                                           'sha256': record['record_sha256']},
                              original_line=record['payload']['line'],
                              original_forecasts=record['payload']['forecasts'])
    return certified


def rows(records, scores):
    return [dict(id=mid, date=aware(r['fixture']['kickoff_at']).astimezone(timezone.utc).date().isoformat(),
                 cohort=r['fixture']['cohort'], actual=scores.get(mid), forecast=r['payload']['forecasts'],
                 line=r['payload']['line'])
            for mid, r in records.items()]


def scores_for(group):
    return compare(group, baseline='market', candidate='candidate')


def agreement(group):
    paired = [row['forecast'] for row in group if row['actual'] is not None
              and all(row['forecast'][arm].get('top3') for arm in ('market', 'candidate'))]
    choices = [(row['candidate']['top3'], row['market']['top3']) for row in paired]
    return dict(paired=len(choices), same_first=sum(a[0] == b[0] for a, b in choices),
                same_three_ordered=sum(a == b for a, b in choices),
                same_three_members=sum(set(a) == set(b) for a, b in choices))


def review():
    source = source_module()
    access = source.Sources(UPDATES)
    with TemporaryDirectory(prefix='r7-nov26-') as tmp:
        work = Path(tmp)
        plan, records, _ = source.research_firsts(access, 'R7', work)
        older, prior_report = earlier_results(source, access, records, plan, work)
    prior = scores_for(rows(records, older))
    if len(records) != 192 or prior['tracks'] != prior_report['tracks'] or prior['paired'] != prior_report['paired']:
        raise ValueError('previous model and market denominators do not reproduce')
    new = newly_settled(records, older)
    union = older | {mid: r['score'] for mid, r in new.items()}
    combined = rows(records, union)
    by_competition = defaultdict(list)
    new_by_competition = defaultdict(list)
    for row in combined:
        by_competition[row['cohort']].append(row)
        if row['id'] in new:
            new_by_competition[row['cohort']].append(row)
    return dict(
        as_of=AT, registration_sha256=plan['record_sha256'], registered=len(records),
        previously_settled=len(older), newly_settled=len(new), cumulative_settled=len(union),
        pending=len(records) - len(union), cumulative=scores_for(combined),
        by_competition={code: scores_for(group) for code, group in sorted(by_competition.items())},
        today={code: scores_for(group) for code, group in sorted(new_by_competition.items())},
        agreement={'cumulative': agreement(combined),
                   'new': {code: agreement(group) for code, group in sorted(new_by_competition.items())}},
        new_results=new,
    )


if __name__ == '__main__':
    report = review()
    output = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    record = verify(json.loads((ROOT / 'review-freeze.json').read_bytes()))
    payload = record['payload']
    if (record['stage'] != 'review' or aware(record['recorded_at']) < aware(report['as_of'])
            or payload['original_registration'] != report['registration_sha256']
            or payload['report_sha256'] != sha(output.encode('utf-8'))
            or payload['summary_markdown'] != (ROOT / 'README.md').read_text(encoding='utf-8')):
        raise ValueError('recalculated results do not match the appended R7 review')
    print(output, end='')
