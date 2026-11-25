"""Replay Ptolemy's public J.LEAGUE cards and preserve exact cutoff-limited local capture ledgers."""
from collections import defaultdict
from datetime import timezone
from hashlib import sha256
from html.parser import HTMLParser
import json

from research.analysis_freeze import aware
from research_program import nov25_first_review as core

DIR = 'raw/jleague-official/'
LOGS = {'jleague-original-captures.jsonl': DIR+'match-card-captures.jsonl',
        'jleague-live-captures.jsonl': 'jleague-live-captures.jsonl',
        'jleague-commentary-captures.jsonl': DIR+'live-commentary-captures.jsonl'}
DOCUMENTS = {'jleague-homepage-metadata.json': DIR+'homepage-metadata.json',
             'jleague-kickoff-observations.json': 'jleague-kickoff-observations.json'}
ADDENDA = {'jleague-kickoff-observation-addendum-'+e[0]+'.json':code for code,e in core.J1_CARDS.items()}
DOCUMENTS.update({name:name for name in ADDENDA})
SLICES = LOGS | DOCUMENTS


def read_asof(root, ceiling):
    parts, rows, metadata, clocks = {}, [], {}, []
    for alias, name in LOGS.items():
        path = core.file_in(root,name)
        if path.is_file():
            captures, body = core.dated_log(path,ceiling)
            if captures:
                parts[alias] = body
                for _, rec in captures:
                    rows.append((alias,rec))
                    clocks.append(aware(rec['captured_at_utc']))
    for alias, name in DOCUMENTS.items():
        path = core.file_in(root,name)
        if path.is_file():
            body = path.read_bytes()
            doc = json.loads(body)
            clock = aware(doc['observed_at_utc'] if alias in ADDENDA else doc['captured_at_utc'])
            if clock <= ceiling:
                parts[alias], metadata[alias] = body, doc
                clocks.append(clock)
    return parts, rows, metadata, clocks


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = set()

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.links.add(dict(attrs).get('href','').split('#')[0])


def _raw(root, rec, expected_url, expected_path, at, inventory):
    if rec['url'] != expected_url or not aware(rec['requested_at_utc']) <= aware(rec['captured_at_utc']) <= at:
        raise ValueError('official acquisition URL or clocks differ')
    if rec.get('http_status') != 200 and not rec.get('path'):
        return None
    if rec.get('path') != expected_path:
        raise ValueError('official raw pathname differs from the card code or capture clock')
    path = core.file_in(root,expected_path)
    if not path.is_file():
        return None
    body = path.read_bytes()
    digest = sha256(body).hexdigest()
    if len(body) != rec['bytes'] or digest != rec['sha256']:
        raise ValueError('official acquisition bytes or SHA-256 differ: '+expected_path)
    inventory[expected_path] = digest
    if rec['http_status'] != 200:
        return None
    if rec['content_type'].split(';')[0].lower() != 'text/html':
        raise ValueError('expected official HTML')
    return body


def _reference(rec):
    return {k:rec.get(k) for k in ('url','path','http_status','requested_at_utc','captured_at_utc','sha256','bytes')}


def inspect(root, batch, reg, statuses, labels, at):
    _, rows, docs, _ = batch
    inventory, per_game, notes = {}, defaultdict(list), defaultdict(list)
    by_code = {k:'espn:'+v[0] for k,v in core.J1_CARDS.items()}
    registered = {e['mid']:e for e in reg['events']}
    board_ref, = [r for r in reg['preserved_pre_kickoff_sources'] if r['path']=='pre-kickoff/espn-j1-scoreboard-pre.json']
    board = json.loads(core.file_in(root,board_ref['path']).read_bytes())
    if [league['slug'] for league in board['leagues']] != ['jpn.1']:
        raise ValueError('original daily calendar is not the J1 scoreboard')
    calendar = {}
    for mid in by_code.values():
        f = statuses[mid]['fixture']
        game, = [e for e in board['events'] if 'espn:'+str(e['id'])==mid]
        core._game(game,f,False)
        pre = registered[mid]['pre_capture']
        core._game(json.loads(core.file_in(root,pre['path']).read_bytes())['header'],f,True)
        if not aware(pre['retrieved_at_utc']) <= aware(reg['created_at_utc']) < aware(f['kickoff_at']):
            raise ValueError('original event was not registered before its scheduled kickoff')
        calendar[mid] = dict(scoreboard_path=board_ref['path'],scoreboard_sha256=board_ref['copied_sha256'],
                             prematch_path=pre['path'],prematch_sha256=pre['copied_sha256'],prematch_read_utc=pre['retrieved_at_utc'],
                             registration_sha256=core.REGISTRY_SHA,season=game['season'],scheduled_utc=f['kickoff_at'])
    home_ref = docs.get('jleague-homepage-metadata.json')
    links = _Links()
    if home_ref:
        body = _raw(root,home_ref,'https://www.jleague.jp/',DIR+'homepage.html',at,inventory)
        if body:
            links.feed(body.decode('utf-8'))
    references = {}
    for alias, rec in rows:
        code = rec.get('jleague_match_code') or rec.get('match_code')
        if code not in by_code:
            raise ValueError('unknown official capture in this slate')
        mid = by_code[code]
        url = core.J1_URL.format(code)
        if alias == 'jleague-live-captures.jsonl':
            if str(rec.get('event_id',core.J1_CARDS[code][0])) != core.J1_CARDS[code][0]:
                raise ValueError('official refresh names a different registered ESPN event')
            clock = aware(rec['captured_at_utc']).astimezone(timezone.utc)
            suffix = {'match-card-FT': '-FT-refresh-', 'postgame-state-check': '-postgame-check-'}.get(rec.get('kind'), '-refresh-')
            path = DIR+'match-'+code+suffix+clock.strftime('%Y%m%dT%H%M%S%fZ')+'.html'
        elif alias == 'jleague-original-captures.jsonl':
            path = DIR+'match-'+code+'.html'
        else:
            url += 'live-commentary/'
            path = DIR+'live-commentary-'+code+'.html'
        ref = dict(_reference(rec),code=code,ledger=SLICES[alias])
        body = _raw(root,rec,url,path,at,inventory)
        if body is None:
            notes[mid].append(dict(source=ref, status='official_page_unavailable'))
            continue
        references[(alias,code)] = ref
        if alias == 'jleague-commentary-captures.jsonl':
            notes[mid].append(dict(source=ref,status='commentary_retained_as_reference'))
            continue
        f = statuses[mid]['fixture']
        try:
            page = core.official_card(body,ref,f)
        except (ValueError,KeyError,TypeError) as exc:
            notes[mid].append(dict(source=ref,status='unverified_card',reason=str(exc)))
            continue
        page['public_homepage_link_verified'] = (url in links.links or '/match/j1/2026/'+code+'/' in links.links)
        per_game[mid].append(page)

    obs = docs.get('jleague-kickoff-observations.json',{})
    seen = set()
    for record in obs.get('matches',[]):
        code = record['jleague_match_code']
        if code not in by_code or code in seen:
            raise ValueError('duplicate or unknown first-observation card code')
        seen.add(code)
        mid = by_code[code]
        event = registered[mid]
        original = references.get(('jleague-original-captures.jsonl',code))
        first = next((p for p in per_game[mid] if p['source'] == original),None)
        commentary = references.get(('jleague-commentary-captures.jsonl',code))
        bound = bool(first and record['espn_event_id'] == event['event_id'] and
                     record['provider_stage'] == 'jpn.1 regular-season' and
                     all(record[s] == event[s]['display_name'] for s in ('home','away')) and
                     (record['jleague_page_url'],record['jleague_page_sha256'],record['jleague_page_http_status']) ==
                     (original['url'],original['sha256'],original['http_status']) and
                     aware(record['jleague_page_retrieved_at_utc']) == aware(original['captured_at_utc']) <= aware(obs['captured_at_utc']) and
                     record['official_header_text_verbatim'] == first['header_verbatim'] and
                     record['official_page_date_field_utc_raw'] == first['structured_date_utc'] and
                     record['official_header_time_precision'] == ('minute' if first['ko_interval'] else 'not displayed'))
        notes[mid].append(dict(status='collector_index_matched' if bound else 'collector_index_unverified',
                               index_file='jleague-kickoff-observations.json', captured_at_utc=obs['captured_at_utc'],
                               commentary_sha_verified=bool(commentary and commentary['url']==record.get('official_live_commentary_url')
                                                           and commentary['sha256']==record.get('official_live_commentary_sha256'))))
    for name,code in ADDENDA.items():
        if name not in docs:
            continue
        add, mid = docs[name], by_code[code]
        event = registered[mid]
        page = next((p for p in per_game[mid] if p['source']['path']==add['official_page_path']),None)
        bound = bool(page and (add['espn_event_id'],add['jleague_match_code'])==(event['event_id'],code)
                     and add['provider_stage']=='J1 2026 Regular Season' and add['match_date']==page['calendar_jst']
                     and all((add[s]['espn_id'],add[s]['espn'],add[s]['jleague'])==
                             (event[s]['espn_id'],event[s]['display_name'],page['teams'][s]['name']) for s in ('home','away'))
                     and aware(add['scheduled_kickoff_at_utc'])==aware(page['scheduled_utc'])
                     and aware(add['observed_at_utc'])==aware(page['source']['captured_at_utc'])
                     and add['official_page_sha256']==page['source']['sha256'] and add['official_page_url']==page['source']['url']
                     and add['official_page_http_status']==200 and add['official_header_text_verbatim']==page['header_verbatim']
                     and add['precision']=='minute' and add['official_page_date_field_utc_raw']==page['structured_date_utc'])
        notes[mid].append(dict(status='collector_addendum_matched' if bound else 'collector_addendum_unverified',
                               index_file=name,captured_at_utc=add['observed_at_utc']))
    checks = {}
    for mid, status in statuses.items():
        pages = sorted(per_game[mid],key=lambda p: (aware(p['source']['captured_at_utc']),p['source']['path']))
        check = core.official_crosscheck(pages,status,labels.get(mid))
        checks[mid] = check
        if check['verdict'] == 'pending_conflict':
            labels.pop(mid,None)
        status['jleague'] = dict(applicable=mid in calendar, calendar_proof=calendar.get(mid), pages=pages, references=notes[mid],
                                 kickoff_interval=check['kickoff_interval'], kickoff_source=check['kickoff_source'],
                                 kickoff_conflict=check['kickoff_conflict'])
    return inventory, checks
