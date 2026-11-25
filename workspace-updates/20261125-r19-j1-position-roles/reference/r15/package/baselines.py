"""Resolve archived baselines, including the original ESPN schedule for every R5 slot."""
from collections import Counter, defaultdict
import gzip
import json
import tarfile

from common import ARCHIVES, FOLDS, IDS_SHA, PANEL_SHA, SIDES, digest, fold, member, read, require, sha, unique, utc


def board_events(body):
    data = json.loads(body)
    require([x['slug'] for x in data['leagues']] == ['jpn.1'], 'scoreboard league')
    return unique(data['events'], 'id')


def fixture(event):
    match, = event['competitions']
    require(str(match['id']) == str(event['id']), ('competition ID', event['id']))
    sides = unique(match['competitors'], 'homeAway')
    require(set(sides) == set(SIDES), ('scoreboard sides', event['id']))
    result = dict(date=match['date'], status=match['status']['type']['name'],
                  completed=match['status']['type']['completed'])
    if result['status'] == 'STATUS_FULL_TIME':
        require(match['status']['type'].get('state') == 'post' and match['status'].get('period', 2) <= 2,
                ('regulation final status', event['id']))
    for side, row in sides.items():
        result[side] = row['team']['displayName']
        result[side + '_id'] = str(row['team']['id'])
        result[side + '_goals'] = str(row.get('score', ''))
    require(result['home_id'] != result['away_id'], ('ordered teams', event['id']))
    return result


def read_baselines(data_root, inputs):
    history = {}
    originals = {}
    archive_sha = {}
    for label, (folder, name, pinned, manifest_hash) in ARCHIVES.items():
        root = data_root / 'workspace-updates' / folder
        require(sha(root / 'manifest.json') == manifest_hash, ('baseline manifest', label))
        manifest = read(root / 'manifest.json')
        require(sha(root / name) == manifest['files'][name] == pinned, ('baseline archive', label))
        archive_sha[label] = pinned
        with tarfile.open(root / name) as tar:
            if label == 'r5':
                body = member(tar, 'panel.jsonl')
                require(digest(body) == inputs['panel_sha256'] == PANEL_SHA, 'R5 panel member')
                history = unique(map(json.loads, body.splitlines()), 'id')
                fifth = []
                for window in ('evaluation', 'recent'):
                    fifth.extend(dict(json.loads(s), window=window) for s in
                                 member(tar, 'study/' + window + '.jsonl').splitlines())
                originals[label] = unique(fifth, 'id')
            else:
                sub = 'main/' if label == 'r7' else 'main/jpn.1/'
                require(digest(member(tar, sub + 'fit.json')) == inputs[label + '_fit_sha256'], (label, 'fit'))
                if label == 'r7':
                    require(digest(member(tar, sub + 'forward.json')) == inputs['baseline_sha256'], 'R7 forward')
                body = gzip.decompress(member(tar, sub + 'forecasts.jsonl.gz'))
                originals[label] = unique(map(json.loads, body.splitlines()), 'id')
    require(archive_sha == inputs['archive_sha256'], 'baseline archive bindings')
    id_data = ''.join(mid + '\n' for mid in sorted(history)).encode()
    require(len(history) == 2822 and digest(id_data) == IDS_SHA, 'original R5 fixture ID set')
    holdout = {mid for mid, g in history.items() if fold(g['date']) in ('evaluation', 'recent')}
    require(all(set(v) == holdout for v in originals.values()), 'published comparator populations')
    require(Counter(fold(g['date']) for g in history.values()) == FOLDS, 'original R5 folds')
    root = data_root / 'workspace-updates' / ARCHIVES['r5'][0]
    files = read(root / 'manifest.json')['files']
    index_name = 'evidence/source-index.json'
    require(inputs['schedule_index_sha256'] == files[index_name] == sha(root / index_name), 'R5 scoreboard index')
    index = read(root / index_name)
    grouped = defaultdict(lambda: defaultdict(list))
    for game in history.values():
        key = game['source_sha256']
        grouped['evidence/' + index[key]['archive']][key].append(game)
    for name, keys in grouped.items():
        require(sha(root / name) == files[name], ('original R5 scoreboard archive', name))
        with tarfile.open(root / name) as tar:
            for key, games in keys.items():
                body = gzip.decompress(member(tar, index[key]['member']))
                require(digest(body) == key, ('original R5 response', key))
                events = board_events(body)
                for g in games:
                    f = fixture(events[g['id'].removeprefix('espn:')])
                    require(g['competition'] == 'jpn.1' and g['score_basis'] == 'regulation_90'
                            and f['status'] == 'STATUS_FULL_TIME' and f['completed'] is True
                            and utc(f['date']).date().isoformat() == g['date']
                            and all(g[s] == f[s] and str(g[s+'_goals']) == f[s+'_goals'] for s in SIDES),
                            ('original R5 regulation fixture', g['id']))
                    g.update(home_id=f['home_id'], away_id=f['away_id'], kickoff_at=f['date'])
    return history, originals
