"""Verify the original J1 research display against the retained schedule, odds and matrices."""
from hashlib import file_digest
from pathlib import Path
import csv
import json
import math
import tarfile
from tempfile import TemporaryDirectory

from research.analysis_freeze import aware
from research_program import all_scope_model as scores
from research_program import display_windows as windows
from research_program import goal_state_forward as ledger
from research_program.future_validation import quote_audit

ROOT = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    with path.open('rb') as stream:
        return file_digest(stream,'sha256').hexdigest()


def check(ok, message):
    if not ok:
        raise ValueError(message)


def extract(archive, dest):
    with tarfile.open(archive, 'r:gz') as files:
        for member in files.getmembers():
            path = Path(member.name)
            check(member.isfile() and not path.is_absolute() and '..' not in path.parts,
                  'invalid evidence member '+member.name)
            target = dest/path
            target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('xb') as output:
                output.write(files.extractfile(member).read())


def american(value):
    price = float(value)
    check(abs(price)>=100, 'invalid source price')
    return 1+(price/100 if price>0 else -100/price)


def verify():
    for name, expected in read(ROOT/'checksums.json').items():
        check(sha(ROOT/name)==expected, 'file checksum '+name)
    registered = ROOT/'registration'
    today = ROOT/'nov25'
    entries = read(today/'entries.json')
    message = (today/'message.txt').read_text(encoding='utf8')
    plan, fixtures, identity = windows.prepared_batch(registered,'nov25',entries,message,today)
    batch = ledger._read(today,read(today/'publication.json'))
    check(batch['payload']['identity']==identity, 'body, seats or authored rows differ')
    check(aware(plan['recorded_at'])<aware(batch['recorded_at'])<min(aware(f['kickoff_at']) for f in fixtures),
          'registration and earliest kickoff order')
    spec = read(ROOT/'protocol.json')
    info = plan['payload']['identity']
    check(info['protocol']==spec and info['protocol_sha256']==sha(ROOT/'protocol.json'),'J1 protocol differs')
    with TemporaryDirectory() as tmp:
        local = Path(tmp)
        observed = local/'observed'
        for path in sorted((ROOT/'evidence').glob('prematch-*.tar.gz')):
            extract(path,observed)
        archived = read(observed/'file-manifest.json')['files']
        for row in archived:
            check(sha(observed/row['path'])==row['sha256'],'raw evidence '+row['path'])
        extract(ROOT/'author-inputs.tar.gz',local/'used')
        parent_dir = ROOT.parent/'20261125-r10-shot-conversion'
        parent_file = 'forward/first-issues.tar.gz'
        check(sha(parent_dir/parent_file)==read(parent_dir/'manifest.json')['files'][parent_file],
              'R10 source archive checksum')
        historical = local/'r10'
        extract(parent_dir/parent_file,historical)
        earlier = ledger._read(historical,read(historical/'receipts.json')['registration'])
        check(earlier['record_sha256']==info['original_registration'] and
              aware(earlier['recorded_at'])<=aware(plan['recorded_at']),'R10 first schedule reference')
        # The second season-wide observation and the earlier R10 registrations independently cover both slates.
        calendar = read(observed/'raw/espn_calendar_2026.json')
        for window in spec['windows']:
            found = {}
            for e in calendar['events']:
                if not aware(window['from'])<=aware(e['date'])<aware(window['until']):
                    continue
                mid = 'espn:'+e['id']
                check(e['season']['slug']=='regular-season' and mid not in found,'ambiguous schedule identity')
                sides = {s['homeAway']:'espn:'+s['team']['id'] for s in e['competitions'][0]['competitors']}
                found[mid]=sides
                f = plan['payload']['fixtures'][mid]
                check(f==earlier['payload']['fixtures'][mid],'R10 original schedule '+mid)
                check(aware(f['kickoff_at'])==aware(e['date']) and (sides['home'],sides['away'])==(f['home'],f['away']),
                      'calendar sides and kickoff '+mid)
            check(sorted(found)==info['slates'][window['name']] and len(found)==window['expected'],'window coverage')
        captures = {r['match_id']:r['summary'] for r in read(observed/'raw/espn_status_manifest.json')['match_summaries']
                    if 'summary' in r}
        with (today/'predictions.csv').open(encoding='utf8',newline='') as stream:
            table = {r['match_id']:r for r in csv.DictReader(stream)}
        check(set(table)==set(entries),'prediction table coverage')
        n_strict = 0
        for mid, refs in entries.items():
            row = ledger._read(today,refs['authored'])
            f,p = row['fixture'],row['payload']
            for name, expected in p['evidence_files'].items():
                check(sha(local/'used'/name)==expected,'author input '+name)
            q = p['bookmaker']
            path = observed/'matches'/('espn_summary_'+mid.split(':')[1]+'.json')
            data = read(path)
            capture = captures[mid]
            check(capture['url']==q['source_url'] and q['query_time']==capture['retrieved_at_utc']
                  and q['source_sha256']==sha(path)==capture['sha256'] and aware(q['query_time'])<=aware(f['cutoff_at']),
                  'source and cutoff '+mid)
            event, = data['header']['competitions']
            check('espn:'+str(event['id'])==mid and event['status']['type']['state']=='pre' and
                  data['format']['regulation']['periods']*data['format']['regulation']['clock']==5400,
                  'regulation or fixture identity '+mid)
            odds, = [v for v in data['odds'] if v['provider']['name']==q['bookmaker']]
            check(q['line']==float(odds['overUnder'])==f['actual_total_line'] and q['quoted_at'] is None,'line or clock '+mid)
            prices = tuple(american(odds[k]['moneyLine']) for k in ('homeTeamOdds','drawOdds','awayTeamOdds'))
            totals = tuple(american(odds[k]) for k in ('overOdds','underOdds'))
            check(totals==(q['over_odds'],q['under_odds']) and
                  prices==tuple(p['market_snapshot']['h2h'][s] for s in scores.SIDES),'price mismatch '+mid)
            matrix = scores._full_market(prices,q['line'],totals)
            check(scores.pick(matrix,q['line'])==p['market_snapshot']['forecast'],'market comparison '+mid)
            strict = quote_audit(f)['eligible']
            check(strict==p['strict_quote_eligible'],'strict quote '+mid)
            n_strict += strict
            cells = table[mid]
            check(p['displayed_scores']==[cells[k] for k in ('first','second','third')] and
                  p['wdl']==cells['wdl'] and p['total_direction']==cells['total_side'] and
                  float(cells['line'])==q['line'] and cells['freeze_id']==row['freeze_id'] and
                  math.isclose(float(cells['model_consensus_probability']),identity['rows'][mid]['ranking_probability']),
                  'CSV selection '+mid)
            seat = identity['selected'].index(mid)+1 if mid in identity['selected'] else None
            check(cells['selected_seat']==(str(seat) if seat else ''),'CSV selected seat '+mid)
        return dict(windows={k:len(v) for k,v in info['slates'].items()}, issued=len(entries),strict_quotes=n_strict,
                    chosen=identity['selected'],publication_sha256=batch['record_sha256'],raw_evidence_files=len(archived))


if __name__=='__main__':
    print(json.dumps(verify(),ensure_ascii=False))
