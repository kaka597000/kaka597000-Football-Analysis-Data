"""Select the exact provider bodies used by a signed R18 information cutoff."""

import json

from bundle_io import checked_bytes, checked_file, digest, members, require, safe, write

ESPN = 'refreshes.jsonl'
ORIGINAL = 'raw/jleague-official/match-card-captures.jsonl'
LIVE = 'jleague-live-captures.jsonl'
LOGS = (ESPN, ORIGINAL, LIVE)
AUDIT = 'audit/nov22-25-annual-calendar-audit.json'
DAILY = 'audit/espn-j1-scoreboard-observations.jsonl'
ANNUAL = 'raw/espn_calendar_2026.json'
ANNUAL_ARCHIVE = 'evidence/prematch-07.tar.gz'
FIELDS = ('path', 'sha256', 'bytes', 'url', 'requested_at_utc', 'captured_at_utc')
ALIASES = {ESPN: 'snapshot/refreshes.jsonl', ORIGINAL: 'snapshot/jleague-original-captures.jsonl',
           LIVE: 'snapshot/jleague-live-captures.jsonl'}


def original_logs(f, intake, evidence, at):
    cal = evidence['calendar']
    require(cal['scoreboard_log'] == DAILY and cal['audit_file'] == AUDIT, 'different calendar evidence locations')
    logs = {name: f.review.dated_log(checked_file(intake, name), at)[1] for name in LOGS}
    check_full_logs(logs, evidence)
    logs[DAILY] = f.review.dated_log(checked_file(intake, DAILY), f.aware(cal['audit_created_at_utc']))[1]
    require(digest(logs[DAILY]) == cal['scoreboard_log_sha256'], 'calendar log changed during read')
    return logs


def check_full_logs(logs, evidence):
    require({name: digest(logs[name]) for name in LOGS} == evidence['acquisition_log_sha256'],
            'complete acquisition log slices differ from registered digests')


def receipts(logs):
    out = {}
    for name, body in logs.items():
        for line in body.splitlines():
            row = json.loads(line)
            path = row.get('path')
            if path and row.get('http_status') == 200:
                safe(path)
                require(path not in out, f'non-unique acquisition path {path}')
                out[path] = (name, row)
    return out


def source_index(f, early, intake, evidence, at, logs):
    """Resolve citations to original log rows. Include the actual source of the official KO interval."""
    lookup = receipts(logs)
    pages, _ = f._official(intake, early, at)
    refs = {}

    def add(ref, role, subject, available_logs):
        path = ref['path']
        name, row = lookup[path]
        require(name in available_logs and all(ref[k] == row[k] for k in FIELDS if k in ref),
                f'cited source does not match acquisition row: {path}')
        identifying = ('event_id', 'league_slug', 'match_code', 'jleague_match_code', 'date_query', 'http_status')
        item = refs.setdefault(path, dict(source={k: row[k] for k in FIELDS}, log=name, kind=row.get('kind'),
                                         provider_fields={k: row[k] for k in identifying if k in row}, uses=[]))
        item['uses'].append(dict(role=role, subject=subject))

    for mid, event in sorted(evidence['events'].items()):
        if event['verdict'] != f.AGREED:
            continue
        add(event['official'], 'official_final', mid, (ORIGINAL, LIVE))
        cross = f.review.official_crosscheck(pages[mid], {'kickoff': event['espn_actual_kickoff']}, None)
        require(event['official_ko_interval'] == cross['kickoff_interval'], f'official kickoff interval differs: {mid}')
        if cross['kickoff_source']:
            add(cross['kickoff_source'], 'official_kickoff_minute', mid, (ORIGINAL, LIVE))
        if event['espn_actual_kickoff']:
            add(event['espn_actual_kickoff']['source'], 'espn_actual_kickoff', mid, (ESPN,))
        label = event['espn']
        add(dict(path=label['file'], sha256=label['sha256'], url=label['url'], captured_at_utc=label['query_time']),
            'espn_certified_ft90', mid, (ESPN,))
        for ref in event['ft_summary_sources']:
            add(ref, 'espn_ft_starters', mid, (ESPN,))
    cal = evidence['calendar']
    for day, row in sorted(cal['daily'].items()):
        add(row, 'dated_calendar', day, (DAILY,))
    annual = cal['annual']
    return dict(acquisitions=[refs[k] for k in sorted(refs)],
                annual=dict(source=dict(path=cal['annual_file'], url=annual['url'], sha256=annual['sha256'],
                                        bytes=annual['bytes'], requested_at_utc=None,
                                        captured_at_utc=annual['retrieved_at_utc']),
                            archive=ANNUAL_ARCHIVE, member=ANNUAL),
                audit=dict(path=AUDIT, sha256=cal['audit_sha256'], created_at_utc=cal['audit_created_at_utc']),
                full_log_sha256={n: digest(v) for n, v in sorted(logs.items())})


def package_inputs(intake, index, logs):
    files = {'logs/' + name: body for name, body in logs.items()}
    audit = checked_file(intake, AUDIT).read_bytes()
    require(digest(audit) == index['audit']['sha256'], 'calendar audit changed')
    files['calendar-audit.json'] = audit
    for entry in index['acquisitions']:
        ref = entry['source']
        body = checked_bytes(checked_file(intake, ref['path']).read_bytes(), ref)
        files.setdefault('objects/' + ref['sha256'], body)
    return files


def materialize(f, files, index, evidence, root, at):
    """Restore acquired bytes under their original names and derive the model's narrower input logs."""
    logs = {name: files['logs/' + name] for name in (*LOGS, DAILY)}
    check_full_logs(logs, evidence)
    cal = evidence['calendar']
    require(digest(logs[DAILY]) == cal['scoreboard_log_sha256'], 'signed daily log digest differs')
    audit = files['calendar-audit.json']
    require(digest(audit) == cal['audit_sha256'], 'signed calendar audit digest differs')
    write(root, AUDIT, audit)
    lookup = receipts(logs)
    used, objects = set(), set()
    for item in index['acquisitions']:
        ref = item['source']
        path = ref['path']
        name, row = lookup[path]
        require(path not in used and name == item['log'] and ref == {k: row[k] for k in FIELDS}
                and ((name == ESPN and row['league_slug'] == 'jpn.1' and row['kind'] == 'summary')
                     or name in (DAILY, ORIGINAL, LIVE)), f'different source or out-of-scope body {path}')
        key = 'objects/' + ref['sha256']
        write(root, path, checked_bytes(files[key], ref))
        used.add(path)
        objects.add(key)
    require(set(files) == {'logs/' + n for n in logs} | objects | {'calendar-audit.json'},
            'missing or unused files in evidence slice')
    projected = {}
    for name, body in logs.items():
        lines = body.splitlines(keepends=True)
        limit = f.aware(cal['audit_created_at_utc']) if name == DAILY else at
        require(all(f.aware(json.loads(line)['captured_at_utc']) <= limit for line in lines), f'future row in {name}')
        selected = b''.join(line for line in lines if json.loads(line).get('path') in used)
        if name == DAILY:
            require(selected == body, 'coverage of four dated calendars differs')
        elif selected or name == ESPN:
            projected[name] = digest(selected)
        write(root, name, selected)
    return logs, projected


def read_annual(display, row):
    with_archive = members(checked_file(display, ANNUAL_ARCHIVE), lambda n: n == ANNUAL)
    return checked_bytes(with_archive[ANNUAL], row)


def final_review(files):
    manifest = json.loads(files['package-manifest.json'])
    require(manifest['schema'] == 'NOV25-OFFLINE-PACKAGE-1', 'different nine-match review format')
    ft = json.loads(checked_bytes(files['snapshot/ft-review.json'], manifest['files']['snapshot/ft-review.json']))
    require((ft['registered'], ft['certified_ft90'], ft['pending']) == (9, 9, 0)
            and ft['at'] == manifest['as_of'], 'review does not contain nine certified FT90s at its declared cutoff')
    return manifest


def shared_bodies(review_path, index):
    """Look up only cited bodies already present in an immutable companion review."""
    wanted = {'intake/' + e['source']['path']: e['source'] for e in index['acquisitions']}
    names_to_read = wanted.keys() | {'package-manifest.json', 'snapshot/ft-review.json'}
    files = members(review_path, names_to_read.__contains__)
    manifest = final_review(files)
    names, bodies = {}, {}
    for name in sorted(wanted.keys() & files.keys()):
        body = checked_bytes(checked_bytes(files[name], manifest['files'][name]), wanted[name])
        key = 'objects/' + wanted[name]['sha256']
        names.setdefault(key, name)
        bodies[key] = body
    return manifest['as_of'], names, bodies


def nine_intake(f, review_archive, calendar_root, at, dest):
    """Materialize just the J1 portion of a complete nine-match offline review for full-source checking."""
    small = {'package-manifest.json', 'snapshot/ft-review.json', *ALIASES.values()}
    source = members(review_archive, small.__contains__)
    manifest = final_review(source)
    for name in small - {'package-manifest.json'}:
        checked_bytes(source[name], manifest['files'][name])
    names = set()
    for name, alias in ALIASES.items():
        path = write(dest, name, source[alias])
        for _, row in f.review.dated_log(path, at)[0]:
            if (name != ESPN or row['league_slug'] == f.CODE) and row.get('path'):
                names.add('intake/' + safe(row['path']))
    bodies = members(review_archive, names.__contains__)
    require(names == bodies.keys(), 'missing cutoff-eligible J1 body in nine-match review')
    for name, body in bodies.items():
        write(dest, name.removeprefix('intake/'), checked_bytes(body, manifest['files'][name]))
    for name in (AUDIT, DAILY):
        write(dest, name, checked_file(calendar_root, name).read_bytes())
    for _, row in f.review.dated_log(dest / DAILY, f.aware(json.loads((dest / AUDIT).read_bytes())['audit_created_at_utc']))[0]:
        write(dest, row['path'], checked_bytes(checked_file(calendar_root, row['path']).read_bytes(), row))
    return dest
