"""Grade the three original HKJC correct-score firsts against independently retained FT90s."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import math
import tarfile
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from research.analysis_freeze import aware, verify
from research_program import displayed_exact_scores
from research_program.kpi_validation import _actual
from verify_mls import THIS, UPDATES, source


OLDER = UPDATES / '20261123-team-strength'
RESEARCH = '7165ba80bbd0801a4de0fc13d452b0a283fa4e2988642f728335b63b77ae3efc'
PAGES = 'eca5f611b3a4ef0232c894f035b94b4ceb837a83a3be5fb294679ac1fcb5b761'
SEASONS = {'eng.1':'2026-27-english-premier-league','esp.1':'2026-27-laliga','ita.1':'2026-27-italian-serie-a'}


def sha(body):
    return hashlib.sha256(body).hexdigest()


def checked(name, fingerprint):
    path = OLDER / name
    if sha(path.read_bytes()) != fingerprint:
        raise ValueError('original correct-score archive differs: ' + name)
    return path


def read(path):
    return json.loads(path.read_bytes())


def same_implied_values(a, b):
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(same_implied_values(v,b[k]) for k,v in a.items())
    if isinstance(a, list):
        return len(a) == len(b) and all(same_implied_values(v,w) for v,w in zip(a,b))
    if type(a) is float:
        return math.isclose(a,b,abs_tol=1e-12,rel_tol=1e-12)
    return a == b


def calculate(root):
    with tarfile.open(checked('research-and-freezes.tar.gz', RESEARCH)) as tar:
        for member in tar:
            if member.name.startswith('direct/') or member.name in ('direct-score-protocol.json','freeze_displayed.py','review_displayed.py'):
                tar.extract(member,root,filter='data')
    parse_market = runpy.run_path(str(root/'freeze_displayed.py'))['markets']
    refs = read(root/'direct/summary.json')['rows']
    evidence = root/'evidence'
    evidence.mkdir()
    labels, cases = [], []
    with tarfile.open(checked('sources.tar.gz',PAGES)) as pages, tarfile.open(source('review')) as prior, tarfile.open(source('schedule')) as boards:
        providers = {r['espn_match_id']:r for r in json.load(pages.extractfile('live-acquisition/hkjc-official-three-matches.json'))['events']}
        finals = {r['match_id']:r for r in json.load(prior.extractfile('R7/results.json'))}
        for item in refs:
            mid = item['match_id']
            freeze = verify(read(root/'direct'/(item['receipt']['freeze_id']+'.json')))
            frozen, fixture = freeze['payload'], freeze['fixture']
            rec = providers[mid]
            src = rec['source_evidence']
            text, html = (pages.extractfile('live-acquisition/raw/hkjc/'+src[k]).read() for k in ('hkjc_row_file','hkjc_dom_file'))
            if (sha(text) != frozen['source_text_sha256'] or sha(html) != frozen['source_dom_sha256']
                    or frozen['hkjc_event_id'] != rec['hkjc_match_id'] or frozen['source_url'] != src['match_odds_page_url']
                    or aware(src['capture_time_utc']) != aware(frozen['observed_at'])):
                raise ValueError('original quote page or its independently retained capture differs: '+mid)
            offers, groups, hda, totals = parse_market(text.decode('utf8'))
            ranks = displayed_exact_scores.compare(offers, groups, h2h=hda, totals=totals)
            reference = frozen['prediction'].copy()
            implied = ranks.pop('inferred_same_page')
            saved = reference.pop('inferred_same_page')
            if (ranks != reference or not same_implied_values(implied,saved)
                    or frozen['offered_totals'] != totals or frozen['offered_1x2'] != hda
                    or len(offers) != frozen['declared_explicit_prices'] or len(groups) != frozen['other_groups']):
                raise ValueError('reconstructed quote ranking differs from first issue: '+mid)

            cutoff = aware(fixture['kickoff_at'])
            code = fixture['cohort']
            old = finals[mid]
            main = old['evidence']
            body = prior.extractfile('R7/evidence/'+main['file']).read()
            if sha(body) != main['sha256'] or old['cohort'] != code or aware(old['kickoff_at']) != cutoff:
                raise ValueError('later raw full-time source differs from fixture: '+mid)
            (evidence/main['file']).write_bytes(body)
            header = json.loads(body)['header']
            board = json.load(boards.extractfile('forward/raw/'+code.replace('.','_')+'_20261123.json'))
            event, = [v for v in board['events'] if 'espn:'+str(v['id'])==mid]
            game, = event['competitions']
            sides = {p['homeAway']:'espn:'+str(p['team']['id']) for p in game['competitors']}
            if (fixture['stage'] != 'regular' or event['season']['slug'] != SEASONS[code]
                    or [lg['slug'] for lg in board['leagues']] != [code] or header['league']['slug'] != code
                    or sides != {s:fixture[s] for s in ('home','away')} or aware(game['date']) != cutoff
                    or any(event['season'][k] != header['season'][k] for k in ('type','year'))):
                raise ValueError('different source season, home/away or competition phase: '+mid)
            label = dict(fixture, score_basis='regulation_90', event_status='FT', observed_at=main['query_time'],
                         home_goals=old['home_goals'], away_goals=old['away_goals'], evidence=main)
            actual = _actual(label, fixture, evidence, aware(main['query_time']))
            labels.append(label)
            cases.append(dict(match_id=mid, home=item['home'],away=item['away'], actual=list(actual),
                prices=len(offers),other_groups=len(groups),individual_quote_time=frozen['individual_quote_time'],
                observed_at=frozen['observed_at'],signed_at=freeze['recorded_at'],direct=item['direct'],
                same_page_inferred=item['inferred'],original_first=frozen['original_first'],raw_result_sha256=main['sha256']))
    if set(providers) != {r['match_id'] for r in cases}:
        raise ValueError('full three-fixture population required')
    label_path = root/'labels.json'
    label_path.write_text(json.dumps(labels))
    out = root/'review.json'
    source_repo = Path(displayed_exact_scores.__file__).resolve().parents[2]
    runpy.run_path(str(root/'review_displayed.py'))['main'](SimpleNamespace(source=source_repo,bundle=root,
        results=label_path,evidence_root=evidence,out=out))
    graded = read(out)
    counts = {}
    for comparison in graded['comparisons'].values():
        for name, track in comparison['tracks'].items():
            counts[name] = {k:[track['metrics'][k]['hits'],track['metrics'][k]['eligible']] for k in ('score_top1','score_top3')}
    return dict(first_plan_sha256=graded['direct_plan'],original_model_plan=graded['original_plan'],cases=cases,counts=counts,
                evidence='Observed full-time correct-score prices on archived pages; individual quote clocks missing.')


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--write',action='store_true')
    args=ap.parse_args()
    with TemporaryDirectory() as tmp:
        verified=calculate(Path(tmp))
    target=THIS/'hkjc-three-results.json'
    if args.write:
        with target.open('x',encoding='utf8') as stream:
            json.dump(verified,stream,ensure_ascii=False,indent=2)
            stream.write('\n')
    elif read(target)!=verified:
        raise ValueError('archived correct score or FT90 differs')
    print(json.dumps(verified['counts']))
