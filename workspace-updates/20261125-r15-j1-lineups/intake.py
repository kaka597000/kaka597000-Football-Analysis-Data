"""Freeze Maxwell's snapshot, receipts and deduplicated original response bodies."""
from collections import defaultdict
import gzip
from itertools import islice
import json
from pathlib import Path
import tarfile
from urllib.parse import parse_qs, urlsplit

from common import (add_bytes, digest, encode, gz, pretty, read, require, rows,
                    sha, tar_gz, utc, valid_sha)

PILOTS = [f'sources/espn-jpn1-{name}.meta.json' for name in
          ('scoreboard-20180223', 'scoreboard-20220218', 'summary-506293', 'summary-625842')]
METADATA = ('r5-target-ids.txt', 'r5-targets.jsonl', 'r5-reconciliation.json', 'targets.jsonl',
            'annual-source-only-extras.jsonl', 'sources/scoreboard-index.jsonl', 'SCHEMA.md')
CHUNK = 8 * 1024 * 1024
EXTRACT_SHA = '5784ee713b7fc79cde2e73ddc07c0545dcb784122be233cb5a0c101b2cf84351'
FINAL_EXTRACT_SHA = '945982d5fd4adbc02bcb9941aaf7c7125d132575c690e33a59e24a2d45ecd933'


def receipt_hash(r):
    key = r.get('response_sha256') or r.get('sha256')
    require(valid_sha(key), ('response checksum', r.get('url')))
    return key


def clock(r):
    return r.get('query_time_utc') or r.get('captured_at_utc') or r.get('attempted_at_utc')


def receipt_info(r):
    u = urlsplit(r['url'])
    base = '/apis/site/v2/sports/soccer/jpn.1/'
    require(u.scheme == 'https' and u.netloc == 'site.api.espn.com' and not u.fragment
            and u.path in (base + 'summary', base + 'scoreboard'), ('ESPN endpoint', r['url']))
    query = parse_qs(u.query, strict_parsing=True)
    kind = u.path.split('/')[-1]
    key = 'event' if kind == 'summary' else 'dates'
    token, = query[key]
    require(token.isdigit() and (kind != 'summary' or str(r.get('source_match_id', r.get('event_id'))) == token),
            ('ESPN request identity', r['url']))
    utc(clock(r))
    return kind, token


def receipts(meta):
    cp = rows(meta / 'checkpoint.jsonl')
    boards = rows(meta / 'sources/scoreboard-index.jsonl')
    return cp + boards + [read(meta / p) for p in PILOTS]


def snapshot_files(intake, snapshot, inputs):
    key = inputs['rosters_sha256']
    roots = [snapshot, intake] if snapshot else [intake]
    manifests, audits, candidates = [], [], []
    for root in roots:
        for name, values in [('snapshot-manifest.json', manifests), ('coverage-audit.json', audits)]:
            if (root / name).is_file():
                values.append((root / name).read_bytes())
        candidates.extend(root / name for name in ('events.jsonl', 'rosters.jsonl'))
        checkpoint = root / 'checkpoints/sha256'
        wrapper_path = checkpoint / (key + '.manifest.json')
        if wrapper_path.is_file():
            wrapper = read(wrapper_path)
            manifests.append(pretty(wrapper['snapshot_manifest']))
            audits.append(pretty(wrapper['coverage_audit']))
            candidates.append(checkpoint / (key + '.events.jsonl'))
    manifest = next((m for m in manifests if digest(m) == inputs['roster_manifest_sha256']), None)
    require(manifest is not None, ('exact snapshot manifest unavailable', inputs['roster_manifest_sha256']))
    audit_key = json.loads(manifest)['coverage_audit_sha256']
    audit = next((a for a in audits if digest(a) == audit_key), None)
    require(audit is not None, ('exact snapshot coverage audit unavailable', audit_key))
    events = next((p for p in candidates if p.is_file() and sha(p) == key), None)
    require(events is not None, ('exact training JSONL unavailable', key))
    return manifest, audit, events


def freeze(intake, snapshot, inputs, dest, tmp):
    manifest, audit, events = snapshot_files(intake, snapshot, inputs)
    m, a = json.loads(manifest), json.loads(audit)
    require(digest(manifest) == inputs['roster_manifest_sha256'] and digest(audit) == m['coverage_audit_sha256']
            and sha(events) == m['events_jsonl_sha256'] == inputs['rosters_sha256'], 'canonical replay snapshot hashes')
    meta = {name: (intake / name).read_bytes() for name in (*METADATA, *PILOTS)}
    meta['snapshot-manifest.json'] = manifest
    meta['coverage-audit.json'] = audit
    extractor = (snapshot or intake) / 'extract.py'
    recorded = (extractor if extractor.is_file() else intake / 'extract.py').read_bytes()
    replay_extractor = EXTRACT_SHA
    if m.get('all_target_ids_attempted') is True:
        require(digest(recorded) == FINAL_EXTRACT_SHA, 'final checkpoint extractor checksum')
        replay_extractor = FINAL_EXTRACT_SHA
    meta['extractor.json'] = encode(dict(observed_sha256=digest(recorded), replay_extractor_sha256=replay_extractor))
    if digest(recorded) != EXTRACT_SHA:
        meta['observed-extract.py'] = recorded
    with (intake / 'checkpoint.jsonl').open('rb') as stream:
        prefix = list(islice(stream, a['summary_checkpoint_lines']))
    require(len(prefix) == a['summary_checkpoint_lines'], 'acquisition checkpoint prefix')
    meta['checkpoint.jsonl'] = b''.join(prefix)
    index = []
    with events.open('rb') as stream:
        for line in stream:
            r = json.loads(line)
            index.append(dict(source_sha256=r['source_sha256'], source_match_id=r['source_match_id'], row_sha256=digest(line)))
    meta['event-index.jsonl'] = b''.join(encode(r) for r in index)
    local = tmp / 'metadata'
    for name, body in meta.items():
        p = local / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body)
    capture = receipts(local)
    hashes = {receipt_hash(r) for r in capture}
    require({r['source_sha256'] for r in index} <= hashes, 'training body without capture receipt')
    plain = {receipt_hash(read(local / name)): intake / 'raw' / (Path(name).name.removesuffix('.meta.json') + '.json')
             for name in PILOTS}
    raw = dest / 'raw'
    raw.mkdir()
    catalog = []
    chunk, size, part = [], 0, 0

    def flush():
        nonlocal part
        if not chunk:
            return
        part += 1
        name = f'part-{part:04d}.tar'
        with tarfile.open(raw / name, 'w', format=tarfile.USTAR_FORMAT) as tar:
            for key, length, compressed in chunk:
                add_bytes(tar, key + '.json.gz', compressed)
                catalog.append(dict(sha256=key, bytes=length, gzip_sha256=digest(compressed),
                                    gzip_bytes=len(compressed), archive=name))
        chunk.clear()

    for key in sorted(hashes):
        path = intake / 'raw/sha256' / (key + '.json.gz')
        if path.is_file():
            body = gzip.decompress(path.read_bytes())
        else:
            require(key in plain and plain[key].is_file(), ('missing original ESPN body', key))
            body = plain[key].read_bytes()
        require(digest(body) == key, ('original ESPN body', key))
        compressed = gz(body)
        member_size = 512 + ((len(compressed) + 511) // 512) * 512
        if size + member_size > CHUNK:
            flush()
            size = 0
        chunk.append((key, len(body), compressed))
        size += member_size
    flush()
    meta['raw-index.jsonl'] = b''.join(encode(r) for r in catalog)
    tar_gz(dest / 'intake.tar.gz', meta)


def open_raw(pkg, meta, tmp):
    """Validate every physical member and receipt, including non-training or failed captures."""
    records = rows(meta / 'raw-index.jsonl')
    indexed = {r['sha256']: r for r in records}
    require(len(indexed) == len(records) and all(valid_sha(k) for k in indexed), 'raw catalog keys')
    capture = receipts(meta)
    require({receipt_hash(r) for r in capture} == set(indexed), 'receipt/body inventory')
    by_sha = defaultdict(list)
    for r in capture:
        key = receipt_hash(r)
        receipt_info(r)
        require(r.get('bytes', r.get('response_bytes')) == indexed[key]['bytes']
                and 100 <= r['http_status'] <= 599, ('response length or HTTP status', r['url']))
        if r.get('raw_gzip'):
            require(r['raw_gzip'] == 'raw/sha256/' + key + '.json.gz', 'receipt content address')
        by_sha[key].append(r)
    base = tmp / 'bodies'
    base.mkdir()
    chunks = sorted((pkg / 'raw').iterdir())
    require([p.name for p in chunks] == [f'part-{i:04d}.tar' for i in range(1, len(chunks)+1)],
            'raw chunk sequence')
    for p in chunks:
        with tarfile.open(p, 'r|') as tar:
            for item in tar:
                key = item.name.removesuffix('.json.gz')
                require(key in indexed and item.name == key + '.json.gz' and item.isfile()
                        and indexed[key]['archive'] == p.name, ('raw chunk member', p.name, item.name))
                z = tar.extractfile(item).read()
                r = indexed[key]
                require(digest(z) == r['gzip_sha256'] and len(z) == r['gzip_bytes'], ('gzip bytes', key))
                body = gzip.decompress(z)
                require(digest(body) == key and len(body) == r['bytes'], ('uncompressed response', key))
                with (base / item.name).open('xb') as out:
                    out.write(z)
    require(len(list(base.iterdir())) == len(indexed), 'missing original response')
    return base, by_sha
