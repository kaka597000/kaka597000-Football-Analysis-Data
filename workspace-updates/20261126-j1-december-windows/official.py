"""Verify the original December windows from the retained J.League result list."""

from datetime import datetime
import gzip
from hashlib import sha256
from html import unescape
import json
import re
from zoneinfo import ZoneInfo

from research.analysis_freeze import aware


SOURCE_URL = 'https://www.jleague.jp/j1/match/search-list/?startdate=2026-12-04&enddate=2026-12-13&period=custom&sort_desc=true'
TITLE = '【公式】明治安田Ｊ１リーグ 2026年12月4日〜2026年12月13日の日程・結果 | Ｊリーグ公式サイト'
JST = ZoneInfo('Asia/Tokyo')
BJT = ZoneInfo('Asia/Shanghai')
LINK = re.compile(r'<a[^>]*href="(/match/j1/2026/([0-9]{6})/)"[^>]*>(.*?)</a>', re.DOTALL)
TEAM = re.compile(r'\bm-schedule__team-name" data-media="pc">([^<]+)</span>')
CLOCK = re.compile(r'\bm-schedule__time-text">([0-9]{1,2}:[0-9]{2})</p>')
SLOT = re.compile(r'<template id="(P:[a-z0-9]+)"></template>')
RENDER = re.compile(r'\$RS\("(S:[a-z0-9]+)","(P:[a-z0-9]+)"\)')
CLUBS = {
    'ＦＣ東京': 3384, '川崎フロンターレ': 7112, 'ガンバ大阪': 7102, '鹿島アントラーズ': 7115,
    'アビスパ福岡': 7107, '京都サンガF.C.': 21361, 'ジェフユナイテッド千葉': 7111, '浦和レッズ': 3385,
    '名古屋グランパス': 7108, 'サンフレッチェ広島': 7114, 'ヴィッセル神戸': 7477, '柏レイソル': 7476,
    'Ｖ・ファーレン長崎': 19001, '水戸ホーリーホック': 131701, 'ＦＣ町田ゼルビア': 22167,
    'ファジアーノ岡山': 22522, '清水エスパルス': 7104, 'セレッソ大阪': 7109,
    '横浜Ｆ・マリノス': 7116, '東京ヴェルディ': 3393,
}


def official_rows(evidence, fixtures, slates):
    metadata = json.loads((evidence/'jleague-december-capture.json').read_bytes())
    body = gzip.decompress((evidence/'jleague-december-calendar.html.gz').read_bytes())
    return check_schedule(metadata, body, fixtures, slates, expected_url=SOURCE_URL, expected_title=TITLE)


def check_schedule(metadata, body, fixtures, slates, *, expected_url, expected_title):
    if (metadata['url'] != expected_url or metadata['status'] != 200 or len(body) != metadata['bytes']
            or sha256(body).hexdigest() != metadata['sha256']):
        raise ValueError('official J.League calendar differs from its public capture')
    page = body.decode('utf-8')
    if f'<title>{expected_title}</title>' not in page:
        raise ValueError('J.League search returned a different competition or date range')
    captured = aware(metadata['received_utc'])
    if aware(metadata['started_utc']) > captured or captured >= min(aware(f['kickoff_at']) for f in fixtures):
        raise ValueError('the independent J.League calendar requires a pregame capture')
    mounts = {slot: source for source, slot in RENDER.findall(page)}
    by_fixture = {(f['home'], f['away'], aware(f['kickoff_at'])): f['match_id'] for f in fixtures}
    paired = {}
    official_ids = set()
    for path, key, card in LINK.findall(page):
        clocks = CLOCK.findall(card)
        if not clocks:
            continue
        clock, = clocks
        teams = TEAM.findall(card)
        for slot in SLOT.findall(card):
            if slot in mounts:
                part = page.split(f'<div hidden id="{mounts[slot]}">', 1)[1].split('</script>', 1)[0]
                teams.extend(TEAM.findall(part))
        home, away = map(unescape, teams)
        when = datetime.strptime(f'2026{key[:4]} {clock}', '%Y%m%d %H:%M').replace(tzinfo=JST)
        match = (f'espn:{CLUBS[home]}', f'espn:{CLUBS[away]}', when)
        mid = by_fixture.get(match)
        if mid is None or mid in paired or key in official_ids:
            raise ValueError('official J.League fixture, ordered teams or kickoff differs: ' + path)
        paired[mid] = dict(url='https://www.jleague.jp'+path, home=home, away=away,
                           kickoff_beijing=when.astimezone(BJT).isoformat())
        official_ids.add(key)
    if len(official_ids) != len(fixtures) or paired.keys() != {f['match_id'] for f in fixtures}:
        raise ValueError('the official J.League capture must cover every registered match')
    return dict(source_url=expected_url, captured_at=captured.astimezone(BJT).isoformat(), source_sha256=metadata['sha256'],
                confirmed_per_window={name: sum(mid in paired for mid in ids) for name, ids in slates.items()},
                fixtures=paired)
