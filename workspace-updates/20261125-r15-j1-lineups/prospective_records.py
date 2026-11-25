"""Read-only checks for R15 prospective first issues and their previously published controls."""
import json
import math
import re
import tarfile

from common import ARCHIVES, digest, member, read, require, safe_name, sha, unique, utc

CODE = 'jpn.1'
TRACK = 'research-r15-j1-prior-starters-20261125'
DISPLAY = 'j1-comprehensive-windows-20261125'
DISPLAY_DIR = '20261125-j1-stage-windows'
MORNING = 'nov25'
WEEKEND = 'nov28_29'
DISPLAY_PLAN = '72c7037d45286dfc846f930a027b3b0b728cbc019180e1217b80d989e94e92f2'
MORNING_PUBLICATION = 'c7d073161148ea5acb2c388d754bf5032fe0200b2a4809b8153dc94e3adfea7b'
# These are the original registration record hashes, distinct from tarball/file hashes.
FIRSTS = {
    'r5': ('forward-first-issues.tar.gz', 'issued/', '1645cae773d498cf312a6ab545335293240afdcd80c6e4de3ad1ac321f2fef41'),
    'r7': ('first-issues.tar.gz', '', '4e200312d9e4956617c45153824b6ee9a450f4c28b9dc82e1e66c5f7b4d09d1a'),
    'r10': ('forward/first-issues.tar.gz', '', 'a3826b216c74eaafe33baaaffc3550099dd7d10091e3512dcc3b9b64b8d665b2'),
}
ORIGINAL_FIELDS = {'r5': 'odds_source_first_issue', 'r7': 'r7_first_issue', 'r10': 'r10_first_issue'}


def freeze_hash(value):
    body = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(',', ':')).encode()
    return digest(body)


def file_reader(folder, name):
    path = folder / safe_name(name)
    require(not path.is_symlink() and path.resolve().is_relative_to(folder.resolve()), ('evidence path', name))
    return path.read_bytes()


def scope(record):
    return {k: record[k] for k in ('match_id', 'stage', 'track')}


def fixture_key(f):
    return f['match_id'], f['cohort'], f['stage'], utc(f['kickoff_at']), f['home'], f['away']


def first(get, ref):
    fid = ref['id']
    require(isinstance(fid, str) and re.fullmatch(r'[0-9a-f]{16}-v000001', fid)
            and ref['file'] == fid + '.json', 'expected an original first receipt filename')
    body = get(ref['file'])
    r = json.loads(body)
    checksum = freeze_hash({k: v for k, v in r.items() if k != 'record_sha256'})
    require(r['schema'] == 'WCPP-ISSUED-FREEZE-1' and r['record_sha256'] == ref['sha256'] == checksum
            and r['recorded_at'] == ref['recorded_at'] and r['freeze_id'] == fid == freeze_hash(scope(r))[:16] + '-v000001'
            and r['stage'] == 'prematch' and type(r['revision']) is int and r['revision'] == 1
            and r['evaluation_slot'] == 'FIRST_PREMATCH' and r['previous_sha256'] is None
            and r['model_promotion'] is False and r['match_id'] == r['fixture']['match_id'],
            ('first receipt identity, revision or checksum', fid))
    f = r['fixture']
    require(utc(f['cutoff_at']) <= utc(r['recorded_at']) < utc(f['kickoff_at']), ('first receipt clock', fid))
    return r


def plan_record(get, ref, track=None, expected_hash=None):
    r = first(get, ref)
    p = r['payload']
    require(r['track'] == p['track'] + '-registration' and (track is None or p['track'] == track)
            and (expected_hash is None or r['record_sha256'] == expected_hash)
            and r['match_id'] == p['track'] + '-plan:' + freeze_hash(p)
            and r['idempotency_key'] == freeze_hash(p), 'registration scope or fingerprint')
    require(p['fixtures'] and all(mid == f['match_id'] for mid, f in p['fixtures'].items())
            and min(utc(f['kickoff_at']) for f in p['fixtures'].values()) == utc(r['fixture']['kickoff_at']),
            'registered fixture IDs or earliest kickoff')
    return r


def check_match(r, plan, mid):
    f = r['fixture']
    require(r['track'] == plan['payload']['track'] and r['match_id'] == mid
            and fixture_key(f) == fixture_key(plan['payload']['fixtures'][mid])
            and r['idempotency_key'] == r['payload']['registration_sha256'] == plan['record_sha256']
            and utc(plan['recorded_at']) <= utc(f['cutoff_at']), ('fixture first does not belong to registration', mid))


def batch(get, track=None, expected_hash=None):
    idx = json.loads(get('receipts.json'))
    require(set(idx) == {'registration', 'matches'}, 'unexpected first-issue index')
    plan = plan_record(get, idx['registration'], track, expected_hash)
    fixtures = plan['payload']['fixtures']
    require(set(idx['matches']) == set(fixtures), 'first-issue inventory differs from its registration')
    records = {}
    for mid, f in fixtures.items():
        if f['cohort'] != CODE:
            continue
        r = first(get, idx['matches'][mid])
        check_match(r, plan, mid)
        records[mid] = r
    return plan, records


def checked_archive(root, label, name):
    folder, _, _, manifest_hash = ARCHIVES[label]
    base = root / 'workspace-updates' / folder
    require(sha(base / 'manifest.json') == manifest_hash, ('original data manifest', label))
    require(sha(base / name) == read(base / 'manifest.json')['files'][name], ('original prematch archive', label, name))
    return base / name


def verify_observation_bodies(tar, observations, firsts):
    bodies = {}

    def original(name, checksum):
        if name not in bodies:
            raw = member(tar, 'forward/' + safe_name(name))
            bodies[name] = digest(raw), raw
        require(bodies[name][0] == checksum, ('prematch source bytes', name))
        return bodies[name][1]

    for mid, record in firsts.items():
        s = observations['schedule_sha256'][mid]
        for ref in s['sources']:
            board = json.loads(original(ref['raw_path'], ref['sha256']))
            require([v['slug'] for v in board['leagues']] == [CODE], ('scheduled league', mid))
            event, = [e for e in board['events'] if 'espn:' + str(e['id']) == mid]
            game, = event['competitions']
            sides = {p['homeAway']: str(p['team']['id']) for p in game['competitors']}
            require(str(game['id']) == str(event['id']) and utc(game['date']) == utc(s['kickoff_at'])
                    and game['status']['type']['name'] == 'STATUS_SCHEDULED' and len(game['competitors']) == 2
                    and sides == {side:str(s[side+'_id']) for side in ('home','away')}, ('scheduled raw identity', mid))
        market = observations['market_status_sha256'][mid]
        for kind, price in record['payload']['prices'].items():
            if price is not None:
                quote = quote_source(market, kind, record['payload']['displayed_label'])
                ref = quote['source']
                if ref.get('file'):
                    original(ref['file'], ref['sha256'])


def originals(root):
    sources = {}
    for label, (name, prefix, pin) in FIRSTS.items():
        with tarfile.open(checked_archive(root, label, name)) as tar:
            sources[label] = batch(lambda n: member(tar, prefix+n), expected_hash=pin)
    r5plan = sources['r5'][0]['payload']['identity']
    observations = {}
    with tarfile.open(checked_archive(root, 'r5', 'forward-observations.tar.gz')) as tar:
        for file, key in [('fixtures.jsonl', 'schedule_sha256'), ('market-latest-status.jsonl', 'market_status_sha256')]:
            body = member(tar, 'forward/'+file)
            require(digest(body) == r5plan[key], ('prematch source ledger', file))
            observations[key] = unique((r for line in body.splitlines() if (r := json.loads(line))['competition'] == CODE),
                                       'match_id')
        verify_observation_bodies(tar, observations, sources['r5'][1])
    return sources, observations


def collect_display(get, parent, cutoff):
    """Read only registered windows and prematch publications available at the signed cutoff."""
    kept = {}

    def keep(name):
        body = get(name)
        kept[name] = body
        return body

    reg = plan_record(lambda n: keep('registration/'+n), json.loads(keep('registration/plan.json')),
                      DISPLAY, DISPLAY_PLAN)
    spec = reg['payload']['identity']
    fixtures = reg['payload']['fixtures']
    parent_fixtures = {mid: f for mid, f in parent['payload']['fixtures'].items() if f['cohort'] == CODE}
    require(utc(reg['recorded_at']) <= cutoff and spec['original_registration'] == parent['record_sha256']
            and fixtures.keys() == parent_fixtures.keys()
            and all(fixture_key(f) == fixture_key(parent_fixtures[k]) for k, f in fixtures.items()), 'official window registration')
    slates = spec['slates']
    require(set(slates) == {MORNING, WEEKEND} and (len(slates[MORNING]), len(slates[WEEKEND])) == (7, 10)
            and sorted(slates[MORNING] + slates[WEEKEND]) == sorted(fixtures), 'official 17-slot window partition')
    slots, recommendations = {}, []
    for window in (MORNING, WEEKEND):
        mids = slates[window]
        for mid in mids:
            slots[mid] = dict(window=window, status='no_verified_publication_by_cutoff')
        name = window + '/publication.json'
        try:
            ref_bytes = get(name)
        except (FileNotFoundError, KeyError):
            require(window != MORNING, 'missing original public recommendations')
            continue
        ref = json.loads(ref_bytes)
        # A later publication must never enter a reconstruction at an earlier cutoff.
        publication_get = lambda n: get(window+'/'+n)
        pub = plan_record(publication_get, ref, DISPLAY+'-'+window, MORNING_PUBLICATION if window == MORNING else None)
        if utc(pub['recorded_at']) > cutoff:
            require(window != MORNING, 'original public recommendations postdate R15')
            continue
        kept[name] = ref_bytes
        get_window = lambda n: keep(window+'/'+n)
        keep(window+'/'+ref['file'])
        entries = json.loads(get_window('entries.json'))
        message = get_window('message.txt')
        identity = pub['payload']['identity']
        rows, selected = identity['rows'], identity['selected']
        require(set(mids) == set(entries) == set(rows) == set(pub['payload']['fixtures'])
                and all(fixture_key(pub['payload']['fixtures'][m]) == fixture_key(fixtures[m]) for m in mids)
                and identity['parent'] == reg['record_sha256'] and identity['window'] == window and identity['slots'] == 3
                and identity['body_sha256'] == digest(message) and len(set(selected)) == len(selected) <= 3
                and set(selected) <= set(mids), ('official publication or message', window))
        if window == MORNING:
            require(len(selected) == 3, 'three original public recommendations required')
        for mid in mids:
            row, entry = rows[mid], entries[mid]
            authored, pair = row['authored'], row['pair']
            require(row['match_id'] == mid and utc(row['kickoff_at']) == utc(fixtures[mid]['kickoff_at'])
                    and authored == entry.get('authored') and pair == entry.get('pair'), ('official row', mid))
            if authored is not None:
                a, b = first(get_window, authored), first(get_window, pair)
                f = dict(fixtures[mid], stage=spec['protocol']['competition_stage'])
                require(a['track'] == 'comprehensive' and b['track'] == 'current-test-pair'
                        and fixture_key(a['fixture']) == fixture_key(b['fixture']) == fixture_key(f)
                        and utc(reg['recorded_at']) <= utc(b['recorded_at']) <= utc(a['recorded_at']) <= utc(pub['recorded_at'])
                        and a['payload']['current_test_reference']['sha256'] == pair['sha256']
                        and a['payload']['registered_window']['sha256'] == reg['record_sha256']
                        and all(row[k] == a['payload'].get(k) for k in ('displayed_scores','wdl','total_line','total_direction')),
                        ('official authored or Current/Test first', mid))
            else:
                require(pair is None and mid not in selected and entry.get('unissued_reason') == row['unissued_reason'],
                        ('unissued official slot', mid))
            slots[mid].update(status='authored_first' if authored else 'unissued', publication_sha256=pub['record_sha256'],
                              published_seat=selected.index(mid)+1 if mid in selected else None,
                              authored_sha256=(authored or {}).get('sha256'), current_test_pair_sha256=(pair or {}).get('sha256'))
        if window == MORNING:
            recommendations = [dict(seat=i, **rows[mid]) for i, mid in enumerate(selected, 1)]
    display = dict(registration_sha256=reg['record_sha256'], current_sha256=spec['current_sha256'],
                   test_sha256=spec['test_sha256'], slots=slots)
    return kept, display, recommendations


def decimal(v):
    return type(v) in (int, float) and math.isfinite(v) and v > 1


def valid_line(v):
    return type(v) in (int, float) and math.isfinite(v) and v > 0 and float(v*4).is_integer()


def quote_source(market, kind, label):
    book = market.get(kind) or {}
    return book.get(label) or book.get('close') or book.get('open') or market.get('observed_line_only') or {}


def observed_prices(market):
    hda = total = label = None
    for when in ('close', 'open'):
        book = (market.get('h2h') or {}).get(when) or {}
        quotes = book.get('prices', book)
        sides = {s: (quotes.get(s) or {}).get('decimal') for s in ('home', 'draw', 'away')}
        has_sides = all(decimal(v) for v in sides.values())
        ou = (market.get('total') or {}).get(when) or {}
        over, under = (ou.get(k) or {} for k in ('over', 'under'))
        offer = None
        if (valid_line(over.get('line')) and over['line'] == under.get('line')
                and decimal(over.get('decimal')) and decimal(under.get('decimal'))):
            offer = dict(line=over['line'], over=over['decimal'], under=under['decimal'])
        if has_sides and offer and market.get('paired_market', True):
            return dict(h2h=sides, total=offer), True, when
        if hda is None and has_sides:
            hda, label = sides, when
        if total is None:
            total = offer
    observed = market.get('observed_line_only') or {}
    if total is None and valid_line(observed.get('line')):
        total = dict(line=observed['line'])
    return dict(h2h=hda, total=total), False, label


def checked_market(p, raw, scheduled, market, fixture, raw_cutoff):
    mid = fixture['match_id']
    for row in (scheduled, market):
        key = (row['match_id'], row['competition'], row['stage'], utc(row['kickoff_at']),
               'espn:'+str(row['home_id']), 'espn:'+str(row['away_id']))
        require(key == fixture_key(fixture) and 'espn:'+str(row['event_id']) == mid and row['identity_verified'] is True
                and utc(row['observed_at']) <= raw_cutoff, ('market/schedule source identity or clock', mid))
    require(scheduled['status'] == 'STATUS_SCHEDULED' and scheduled['score_basis'] == 'regulation_90'
            and p['fixture_sources'] == raw['fixture_sources'] == scheduled['sources'] and scheduled['sources']
            and p['source_market_status'] == market['market_status']
            and all(p[k] == raw[k] for k in ('line','market_mode','market_evidence','prices')), ('original market evidence', mid))
    prices = raw['prices']
    expected, is_paired, label = observed_prices(market)
    require(expected == prices and label == raw['displayed_label'] and is_paired == (raw['market_mode'] == 'paired'),
            ('price, line or pairing differs from the actual market observation', mid))
    hda, total = prices['h2h'], prices['total']
    if hda is not None:
        require(set(hda) == {'home','draw','away'} and all(decimal(v) for v in hda.values()), ('incomplete WDL', mid))
    line = total['line'] if total is not None else None
    two_sided = total is not None and ('over' in total or 'under' in total)
    if total is not None:
        require(valid_line(line)
                and (not two_sided or all(decimal(total.get(k)) for k in ('over','under'))), ('actual O/U quote', mid))
    paired = raw['market_mode'] == 'paired'
    require(line == p['line'] and (not paired or (hda is not None and two_sided and market.get('paired_market', True))),
            ('observed total line or paired market', mid))
    if not hda and total is None:
        require(not raw['market_evidence'] and not raw['forecasts']['market'], ('missing prices acquired a market pick', mid))
    for kind, quote in prices.items():
        if quote is None:
            continue
        evidence = raw['market_evidence']
        evidence = evidence if 'source_sha256' in evidence else evidence[kind]
        obs = quote_source(market, kind, raw['displayed_label'])
        require(obs['source']['sha256'] == evidence['source_sha256'] and obs['observed_at'] == evidence['observed_at']
                and obs.get('quoted_at') == evidence.get('quoted_at') and obs.get('bookmaker') == evidence.get('bookmaker')
                and utc(obs['observed_at']) <= raw_cutoff
                and (not obs.get('quoted_at') or utc(obs['quoted_at']) <= utc(obs['observed_at'])),
                ('quote source or time', mid, kind))
    for tip in p['forecasts'].values():
        require(tip.get('total_line') in (None, line) and (line is not None or tip.get('total_side') is None),
                ('forecast uses an unobserved line', mid))
    return dict(wdl=hda is not None, actual_line=line is not None, two_sided_total=two_sided,
                paired=paired, line=line, market_status=market['market_status'])


def rank_seats(payloads):
    for mid, p in payloads.items():
        probability, tip = p['quality']['p_first'], p['forecasts']['candidate']
        require(type(probability) in (int, float) and math.isfinite(probability) and 0 <= probability <= 1
                and len(tip['top3']) == len(set(tip['top3'])) == 3 and tip['primary'] == tip['top3'][0],
                ('issued first score or probability', mid))
    order = sorted(payloads, key=lambda mid: (-payloads[mid]['quality']['p_first'], mid))
    return [dict(seat=i, match_id=mid, primary=payloads[mid]['forecasts']['candidate']['primary'],
                 top3=payloads[mid]['forecasts']['candidate']['top3'], p_first=payloads[mid]['quality']['p_first'])
            for i, mid in enumerate(order[:3], 1)]


def partition(parent, plan, records, display, cutoff):
    population = {m: f for m, f in parent['payload']['fixtures'].items() if f['cohort'] == CODE}
    started = sorted(m for m, f in population.items() if utc(f['kickoff_at']) <= cutoff)
    remaining = set(population).difference(started)
    identity = plan['payload']['identity']
    require(len(population) == 17 and len(started) == 7 and len(remaining) == 10 and identity['already_started'] == started
            and remaining == set(records) == set(plan['payload']['fixtures'])
            and set(started) == {m for m, v in display['slots'].items() if v['window'] == MORNING}
            and remaining == {m for m, v in display['slots'].items() if v['window'] == WEEKEND}
            and all(plan['payload']['fixtures'][m] == population[m] for m in remaining), 'original 17 / started 7 / remaining 10')
    return population, started


def audit_batch(plan, records, sources, observations, display, official, study):
    identity = plan['payload']['identity']
    cutoff = utc(identity['inputs_cutoff_at'])
    day = cutoff.date().isoformat()
    parent = sources['r10'][0]
    population, started = partition(parent, plan, records, display, cutoff)
    require(plan['payload']['track'] == TRACK and identity['prior_display'] == display
            and identity['formal_kpi_eligible'] is False and identity['competitions'] == [CODE]
            and identity['slots_per_competition'] == 3 and identity['selection_scope'] == 'whole unstarted R10 J1 slate'
            and identity['history_cutoff'] == day and utc(identity['roster_snapshot_at']) <= cutoff <= utc(plan['fixture']['cutoff_at'])
            and all(identity[k] == v for k, v in study.items()), 'signed R15 study, clock or display identity')
    require(identity['source_registrations'] == {k: v[0]['record_sha256'] for k, v in sources.items()}
            and all(set(v[1]) == set(population) for v in sources.values()), 'original R5/R7/R10 registrations and IDs')
    payloads, audit_rows = {}, []
    for mid, f in sorted(population.items()):
        originals = {k: v[1][mid] for k, v in sources.items()}
        for k, r in originals.items():
            require(fixture_key(r['fixture']) == fixture_key(f) and utc(r['recorded_at']) <= cutoff, ('source first fixture', k, mid))
        fifth, seventh, tenth = (originals[k] for k in FIRSTS)
        a, b, c = (r['payload'] for r in (fifth, seventh, tenth))
        require(utc(fifth['recorded_at']) <= utc(seventh['fixture']['cutoff_at'])
                and utc(seventh['recorded_at']) <= utc(tenth['fixture']['cutoff_at'])
                and utc(c['archived_cutoff_at']) == utc(fifth['fixture']['cutoff_at'])
                and fifth['record_sha256'] == b['input_sha256'] == c['odds_source_first_issue']
                and b['model_sha256'] == c['r7_forward_sha256'] == study['r7_forward_sha256']
                and c['recipe_sha256'] == study['r10_recipe_sha256']
                and a['line'] == b['line'] == c['line'] and b['forecasts']['candidate'] == c['forecasts']['r7']
                and a['forecasts']['market'] == b['forecasts']['market'] == c['forecasts']['market'],
                ('published controls or source ordering', mid))
        old = {k: dict(id=r['freeze_id'], sha256=r['record_sha256'], forecast=r['payload']['forecasts']['candidate'])
               for k, r in originals.items()}
        row = dict(match_id=mid, kickoff_at=f['kickoff_at'], home=f['home'], away=f['away'], originals=old,
                   prior_display=display['slots'][mid], status='started' if mid in started else 'issued')
        if mid not in started:
            record = records[mid]
            p = dict(record['payload'])
            require(p.pop('registration_sha256') == plan['record_sha256'] and utc(record['fixture']['cutoff_at']) == utc(plan['recorded_at'])
                    and p['formal_kpi_eligible'] is False and p['history_cutoff'] == day and utc(p['inputs_cutoff_at']) == cutoff
                    and p['prior_display'] == display['slots'][mid] and p['forecasts']['market'] == a['forecasts']['market']
                    and 'espn:'+p['home_id'] == f['home'] and 'espn:'+p['away_id'] == f['away']
                    and all(p[field] == originals[k]['record_sha256'] and p['forecasts'][k] == old[k]['forecast']
                            for k, field in ORIGINAL_FIELDS.items()), ('independent R15 first or published references', mid))
            slots = {k: dict(slot=r['evaluation_slot'], cutoff_at=r['fixture']['cutoff_at'], recorded_at=r['recorded_at'])
                     for k,r in originals.items()}
            require(p['source_slots'] == slots and freeze_hash(p) == identity['payload_sha256'][mid], ('signed payload', mid))
            bindings = ('version','protocol_sha256','study_inputs_sha256','fit_sha256','rosters_sha256',
                        'roster_manifest_sha256','roster_snapshot_at','roster_coverage','panel_sha256','r7_forward_sha256','r10_recipe_sha256')
            require(all(p[k] == study[k] for k in bindings) and p['recipe_sha256'] == study['recipe_sha256'][CODE]
                    and p['training_through'] == b['training_through'] == c['training_through'] < day
                    and p['reference'] == 'original_prospective_R7_first' and p['r7_track'] == seventh['track'],
                    ('issued model or historical cutoff', mid))
            market = checked_market(p, a, observations['schedule_sha256'][mid], observations['market_status_sha256'][mid],
                                    f, utc(fifth['fixture']['cutoff_at']))
            row.update(first_id=record['freeze_id'], first_sha256=record['record_sha256'], market=market)
            payloads[mid] = p
        audit_rows.append(row)
    seats = rank_seats(payloads)
    require(set(identity['payload_sha256']) == set(payloads) and freeze_hash(identity['selected']) == freeze_hash({CODE: seats}),
            'issued research seats differ from whole-slate ranking')
    markets = [r['market'] for r in audit_rows if r['status'] == 'issued']
    coverage = {k: sum(r[k] for r in markets) for k in ('wdl','actual_line','two_sided_total','paired')}
    return dict(registration_sha256=plan['record_sha256'], inputs_cutoff_at=identity['inputs_cutoff_at'],
                registered=len(population), started=len(started), issued=len(records), market_coverage=dict(denominator=len(markets), **coverage),
                research_seats=seats, original_public_recommendations=official, slots=audit_rows)
