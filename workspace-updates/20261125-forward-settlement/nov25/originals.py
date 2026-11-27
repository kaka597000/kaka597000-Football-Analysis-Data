"""Recover the distinct authored, research and same-quote firsts from the published local archives."""
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import tarfile
from urllib.parse import urlsplit

from research.analysis_freeze import aware
from research_program import all_scope_model as scores, display_windows, goal_state_forward as ledger
from research_program.display_market import TOTAL, WDL
from research_program.display_window_review import _quote_source, _raw_market_clock
from research_program.future_identity import fixture_identity
from research_program.goal_state_study import sha
from research_program.kpi_validation import _actual, _first
from research_program.nov25_first_review import _game, same_fixture
from research_program.ranked_score_study import rank
from research_program.result_schedule_revision import revised_actual

J1 = '20261125-j1-stage-windows'
AFC = '20261125-r10-shot-conversion'
FORMAL = AFC + '/formal/'
FIRSTS = {
    'R7': ('20261123-prematch-literature/first-issues.tar.gz', '52f1dd07d146a93ba9cec41ce9e1c9cdf75b3db43f8a65da7ffea222467f385d'),
    'R8': ('20261125-r8-prematch/score/first-issues.tar.gz', '969bc947a037f994f23d3c5a8a1d2e3553abeefa17ac6f641fd9adb814760ce1'),
    'R9': ('20261125-r9-team-score/forward/first-issues.tar.gz', '105a1082d6b3e8d5ecb8f277078c3fe88f8597a289e5be2c2a7d57ba69bb7af1'),
    'R10': (AFC+'/forward/first-issues.tar.gz', 'f2f44fa476bfd0645bbdfa5f218782716683857b7d4ba407e64442e1a54fc602'),
    'R13': ('20261125-r13-domestic-form/forward/first-issues.tar.gz', '86808d14475d3584439af1571f9ece8a23b82ffc2801bb3e9a00078073f3fc08'),
}
RANKED = {'R10': 'b20064dab9bd826f590babce135ba10462c35f95f3071265990e3b66be682d0e',
          'R13': '9060b3c66d1dfb854f1f2043527258d20ca7055ddfb9b5d797a251f8ea4ecb76'}


def read(path):
    return json.loads(path.read_bytes())


class Sources:
    def __init__(self, root):
        self.root = root
        self.files = {}

    def file(self, name, checksum):
        path = self.root/name
        if sha(path) != checksum:
            raise ValueError('archived source bytes differ: ' + name)
        self.files[name] = checksum
        return path


def authored_pick(p):
    return dict(primary=p['primary'], top3=p['top3'], wdl=WDL[p['wdl']], total_line=p['total_line'],
                total_side=TOTAL[p['total_direction']])


def j1(source):
    folder = source.root / J1
    checks = read(source.file(J1+'/checksums.json', 'b005a6ed38653fa003d32d0a2403d14fbb88a9d7cc7f37581a25776c5bdf5804'))
    for name, checksum in checks.items():
        if name.startswith(('registration/', 'evidence/', 'nov25/')) or name == 'protocol.json':
            source.file(J1+'/'+name, checksum)
    out, reg = folder/'nov25', folder/'registration'
    plan, fixtures, issued = display_windows.prepared_batch(reg, 'nov25', read(out/'entries.json'),
                                                          (out/'message.txt').read_text(encoding='utf8'), out)
    published = ledger._read(out, read(out/'publication.json'))
    _first(published, display_windows.TRACK+'-nov25-registration')
    if (published['payload']['identity'] != issued or issued['parent'] != plan['record_sha256']
            or published['payload']['fixtures'] != {f['match_id']:f for f in fixtures}
            or len(fixtures) != 7 or len(issued['selected']) != 3):
        raise ValueError('J1 #51 authored body or frozen three seats differ')
    records, rows, cache = {}, {}, {}
    for fixture in fixtures:
        mid = fixture['match_id']
        link = issued['rows'][mid]
        rec = ledger._read(out, link['authored'])
        _first(rec, 'comprehensive')
        p, f = rec['payload'], rec['fixture']
        same_fixture(f, fixture)
        if not aware(plan['recorded_at']) <= aware(rec['recorded_at']) <= aware(published['recorded_at']) < aware(f['kickoff_at']):
            raise ValueError('J1 authored first or three-seat lock outside the original window')
        snap = p['market_snapshot']
        quote = f['total_quote']
        ok, reason, clock = _quote_source(quote, f, folder/'evidence', cache, expected_h2h=snap['h2h'])
        if not ok or quote != snap['quote'] or quote['line'] != p['total_line']:
            raise ValueError('J1 same-quote check failed: ' + str(reason))
        _game(json.loads(cache[quote['source_sha256']][0])['header'], f, True)
        matrix = scores._full_market(tuple(snap['h2h'][s] for s in scores.SIDES), quote['line'],
                                     (quote['over_odds'], quote['under_odds']))
        market = scores.pick(matrix, quote['line'])
        if market != snap['forecast'] or p['top3'] != link['displayed_scores']:
            raise ValueError('J1 original market forecast or displayed order differs')
        records[mid] = rec
        rows[mid] = dict(fixture=f, first=rec['record_sha256'], issued_at=rec['recorded_at'], pair=link['pair']['sha256'],
                         candidate=authored_pick(p), market=market, frozen_market=market, quote=quote,
                         h2h=snap['h2h'], provider_clock=clock, market_basis='signed_same_quote_market')
    return dict(registration=plan['record_sha256'], publication=published['record_sha256'], published_at=published['recorded_at'], body_sha256=issued['body_sha256'],
                archived_source='#51', selected=issued['selected'], rows=rows), records


def afc(source):
    doc = read(source.file(FORMAL+'nov25-display.json','db877cf340d4257d804e40c5bfa0b040dda166340596dfa7eb89f05fd2ca5cb7'))
    pack = source.file(FORMAL+'nov25-issues-and-evidence.tar.gz','2a8dc8b51250f22ca44e1b42f296e0f90bf885f350c200cc686a5b040e70c78e')
    records, rows = {}, {}
    with tarfile.open(pack) as t:
        def get(name):
            return json.load(t.extractfile(name))

        def first(ref, track):
            r = _first(get('canonical/'+ref['freeze_id']+'.json'), track)
            if (r['record_sha256'],r['freeze_id'],r['recorded_at']) != (ref['sha256'],ref['freeze_id'],ref['recorded_at']):
                raise ValueError('AFC signed record differs from first receipt')
            return r

        planref = doc['batch_plan']
        plan = _first(get('issuance/batch-plan/'+planref['file']), 'afc-comprehensive-20261125-east-registration')
        ranked = first(doc['ranked_batch'], 'top3-selection')
        originals = doc['actual_display']
        mids = [d['match_id'] for d in originals]
        if (get('issuance/display.json') != doc or planref['sha256'] != plan['record_sha256']
                or ranked['payload']['top3'] != originals or ranked['payload']['batch_plan'] != planref
                or len(mids) != 2 or mids != plan['payload']['identity']['ordered_ids']
                or set(mids) != set(plan['payload']['fixtures']) or [d['rank'] for d in originals] != [1,2]
                or (ranked['payload']['planned_slots'],ranked['payload']['empty_slots']) != (3,1)):
            raise ValueError('AFC two archived firsts or short ranking differ')
        refs = {v['name']:v for v in get('issuance/sources.json')}
        board_bytes = t.extractfile('issuance/raw/board.json').read()
        board = json.loads(board_bytes)
        if sha256(board_bytes).hexdigest() != refs['board']['sha256'] or [g['slug'] for g in board['leagues']] != ['afc.champions']:
            raise ValueError('AFC original source scoreboard differs')
        for shown in originals:
            mid, eid = shown['match_id'], shown['match_id'].split(':')[1]
            rec = first(shown['comprehensive_reference'], 'comprehensive')
            pair = first(shown['model_reference'], 'current-test-pair')
            p, f = rec['payload'], rec['fixture']
            if (p['current_test_reference'] != shown['model_reference'] or p['batch_plan'] != planref
                    or fixture_identity(f) != fixture_identity(plan['payload']['fixtures'][mid])
                    or fixture_identity(f) != fixture_identity(pair['fixture']) or f['fixture_source_sha256'] != refs['board']['sha256']
                    or not aware(pair['recorded_at']) <= aware(rec['recorded_at']) <= aware(ranked['recorded_at']) < aware(f['kickoff_at'])
                    or not aware(plan['recorded_at']) <= aware(rec['recorded_at'])
                    or any(p[k] != shown[k] for k in ('primary','top3','wdl','total_line','total_direction'))):
                raise ValueError('AFC original first, pair or placement differs')
            event, = [e for e in board['events'] if str(e['id']) == eid]
            _game(event, f, False)
            body = t.extractfile('issuance/raw/'+eid+'.json').read()
            raw, quote, ref = json.loads(body), f['total_quote'], refs[eid]
            url = urlsplit(quote['source_url'])
            if (p['source_market'] != quote or ref['url'] != quote['source_url'] or sha256(body).hexdigest() != ref['sha256']
                    or quote['raw_sha256'] != ref['sha256'] or quote['match_id'] != mid or ref['observed_at'] != quote['query_time']
                    or url.scheme != 'https' or url.hostname != 'sports.core.api.espn.com'
                    or url.path != f'/v2/sports/soccer/leagues/afc.champions/events/{eid}/competitions/{eid}/odds/100'
                    or urlsplit(raw['$ref']).path != url.path or raw['provider']['name'] != quote['bookmaker']
                    or not aware(ref['observed_at']) <= aware(f['cutoff_at']) or raw['overUnder'] != p['total_line']
                    or (raw['overUnder'],raw['current']['over']['decimal'],raw['current']['under']['decimal']) !=
                       (quote['line'],quote['over_odds'],quote['under_odds'])):
                raise ValueError('AFC actual same-book quote or acquisition clock differs')
            hda = dict(home=raw['homeTeamOdds']['current']['moneyLine']['decimal'], draw=raw['current']['draw']['decimal'],
                       away=raw['awayTeamOdds']['current']['moneyLine']['decimal'])
            matrix = scores._full_market(tuple(hda[k] for k in scores.SIDES),quote['line'],(quote['over_odds'],quote['under_odds']))
            native = pair['payload']['market_baseline']
            if native['status'] != 'ABSTAIN':
                raise ValueError('AFC original strict market status differs')
            records[mid] = rec
            rows[mid] = dict(fixture=f, first=rec['record_sha256'], issued_at=rec['recorded_at'], pair=pair['record_sha256'],
                             candidate=authored_pick(p), market=scores.pick(matrix,quote['line']), frozen_market={},
                             frozen_market_status=native['status'], quote=quote,h2h=hda,provider_clock=_raw_market_clock(raw),
                             market_basis='reconstructed_from_original_DraftKings_response')
    return dict(registration=plan['record_sha256'], publication=ranked['record_sha256'], published_at=ranked['recorded_at'], archived_source=FORMAL,
                selected=mids, rows=rows), records


def research_firsts(source, name, temp):
    relative, checksum = FIRSTS[name]
    if name != 'R7' and not (source.root/relative).is_file():
        return None
    folder = temp/name
    with tarfile.open(source.file(relative,checksum)) as t:
        t.extractall(folder, filter='data')
    idx = read(folder/'receipts.json')
    plan = ledger._read(folder, idx['registration'])
    pop, track = plan['payload']['fixtures'], plan['payload']['track']
    _first(plan, track+'-registration')
    if set(pop) != set(idx['matches']):
        raise ValueError(name+' lost original firsts')
    records = {}
    for mid, ref in idx['matches'].items():
        rec = ledger._read(folder,ref)
        _first(rec, track)
        if (fixture_identity(rec['fixture']) != fixture_identity(pop[mid]) or rec['match_id'] != mid
                or rec['payload']['registration_sha256'] != plan['record_sha256']
                or aware(rec['fixture']['cutoff_at']) < aware(plan['recorded_at'])):
            raise ValueError(name+' spliced first issue: '+mid)
        records[mid] = rec
    ranking = None
    if name in RANKED:
        path = str(Path(relative).with_name('ranked.tar.gz'))
        if (source.root/path).is_file():
            with tarfile.open(source.file(path,RANKED[name])) as t:
                receipt = json.load(t.extractfile('plan.json'))
                reg = _first(json.load(t.extractfile(receipt['file'])), 'research-ranked-first-scores-r10-registration')
            ident = reg['payload']['identity']
            if (reg['record_sha256'] != receipt['sha256'] or reg['payload']['fixtures'] != pop
                    or ident['source_registration'] != plan['record_sha256'] or ident['source_track'] != track):
                raise ValueError('unbound research ranking')
            ranking = {}
            for code in ('jpn.1', 'afc.champions'):
                group = [dict(match_id=k,kickoff_at=v['fixture']['kickoff_at'],first_probability=v['payload']['quality']['p_first'])
                         for k,v in records.items() if v['fixture']['cohort']==code]
                selected = ident['selected'].get(code, [])
                if [v['match_id'] for v in selected] != [v['match_id'] for v in rank(group)]:
                    raise ValueError('original research rank differs')
                for v in selected:
                    mid = v['match_id']
                    pick = records[mid]['payload']['forecasts']['candidate']
                    if (v['first_issue'] != idx['matches'][mid] or v['primary'] != pick['primary'] or v['top3'] != pick['top3']
                            or aware(records[mid]['recorded_at']) > aware(reg['recorded_at'])):
                        raise ValueError('ranked research seat differs from first')
                ranking[code] = [v['match_id'] for v in selected]
            ranking = dict(registration=reg['record_sha256'], recorded_at=reg['recorded_at'], selected=ranking)
    return plan, records, ranking


def r7_prior(source, temp, records, at):
    path = source.file('20261125-forward-settlement/verify_mls.py','4501ad2a7c905ee661ca5f16c085be02fd48309c26d6a72a3a0fc8dbb8420e33')
    spec = importlib.util.spec_from_file_location('archived_nov25_verify_mls', path)
    mls = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mls)
    for relative, checksum in mls.ORIGINALS.values():
        source.file(relative,checksum)
    _, evidence, old, case = mls.prepare(temp/'prior')
    if len(old) != 32 or mls.CASE in {r['match_id'] for r in old} or len({r['match_id'] for r in old}) != 32:
        raise ValueError('wrong R7 older 32')
    actuals = {}
    for row in [*old,case]:
        mid = row['match_id']
        if aware(row['observed_at']) > at:
            continue
        try:
            goals = _actual(row, records[mid]['fixture'], evidence, at)
        except ValueError as exc:
            if mid != mls.CASE or str(exc) != 'retained kickoff conflict':
                raise
            goals = revised_actual(row, records[mid], evidence, at)
        if goals is None:
            raise ValueError('pending score included in older R7 certified rows')
        actuals[mid] = dict(score=list(goals), observed_at=row['observed_at'], source_sha256=row['evidence']['sha256'],
                            method='verified_schedule_revision' if mid==mls.CASE else 'original_schedule')
    return actuals
