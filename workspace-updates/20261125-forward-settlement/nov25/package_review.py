"""Create or independently replay a portable November 25 data package without contacting any service."""
import argparse
import gzip
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import tarfile
from tempfile import TemporaryDirectory

import review


def snapshot_files(folder):
    manifest = review.originals.read(folder/'snapshot-manifest.json')
    files = manifest['files']
    if (not {'inputs.json','ft-review.json','live-status.json','refreshes.jsonl'} <= set(files)
            or set(files) - {'inputs.json','ft-review.json','live-status.json','refreshes.jsonl','channel-input.json'} - review.jleague.SLICES.keys()):
        raise ValueError('incomplete or unknown snapshot files')
    for name, expected in files.items():
        if review.originals.sha(folder/name) != expected:
            raise ValueError('snapshot digest differs: '+name)
    inputs = review.originals.read(folder/'inputs.json')
    expected = {k:dict(intake_path=v,sha256=files[k]) for k,v in review.jleague.SLICES.items() if k in files}
    if inputs.get('official_ledgers',{}) != expected:
        raise ValueError('official capture slice paths or hashes differ')
    if (inputs['at'] != manifest['as_of'] or files['refreshes.jsonl'] != inputs['acquisition_log_sha256']
            or files.get('channel-input.json') != inputs['channel_input_sha256']):
        raise ValueError('snapshot cutoff or source binding differs')
    return manifest, inputs


def contents(folder, intake, updates):
    manifest, inputs = snapshot_files(folder)
    files = {'snapshot/'+n:(folder/n,h) for n,h in manifest['files'].items()}
    files['snapshot/snapshot-manifest.json'] = folder/'snapshot-manifest.json',review.originals.sha(folder/'snapshot-manifest.json')
    for prefix,root,entries in [('intake',intake,inputs['intake_files']),('updates',updates,inputs['archived_sources'])]:
        for name,expected in entries.items():
            files[prefix+'/'+name] = review.core.file_in(root,name), expected
    return manifest['as_of'], files


def add(tar, name, data):
    item = tarfile.TarInfo(name)
    item.size = len(data)
    item.mode = 0o644
    tar.addfile(item,BytesIO(data))


def pack(folder, intake, updates, out):
    stamp, files = contents(folder,intake,updates)
    out.mkdir(parents=True,exist_ok=True)
    key = review.aware(stamp).strftime('%Y%m%dT%H%M%S%fZ')
    suffix = '-jleague' if any('snapshot/'+name in files for name in review.jleague.SLICES) else ''
    target = out/(key+'-nov25-first-review'+suffix+'.tar.gz')
    with TemporaryDirectory(dir=out) as temporary:
        path = Path(temporary)/'complete.tar.gz'
        inventory = {}
        with path.open('wb') as stream, gzip.GzipFile(filename='',fileobj=stream,mode='wb',mtime=0) as zipped, tarfile.open(fileobj=zipped,mode='w') as tar:
            for name,(src,expected) in sorted(files.items()):
                data = src.read_bytes()
                if sha256(data).hexdigest() != expected:
                    raise ValueError('raw acquisition or original source changed: '+name)
                add(tar,name,data)
                inventory[name] = dict(bytes=len(data),sha256=expected)
            add(tar,'package-manifest.json',review.encoded(dict(schema='NOV25-OFFLINE-PACKAGE-1',as_of=stamp,files=inventory)))
        verify(path)
        try:
            os.link(path,target)
        except FileExistsError:
            if review.originals.sha(path) != review.originals.sha(target):
                raise ValueError('another package already exists for this cutoff')
    return target


def verify(path):
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        with tarfile.open(path,'r:gz') as tar:
            actual = {}
            for member in tar:
                dest = review.core.file_in(root,member.name)
                if not member.isfile() or dest.exists():
                    raise ValueError('invalid or duplicate package member')
                body = tar.extractfile(member).read()
                dest.parent.mkdir(parents=True,exist_ok=True)
                dest.write_bytes(body)
                actual[member.name] = dict(bytes=len(body),sha256=sha256(body).hexdigest())
        package = review.originals.read(root/'package-manifest.json')
        actual.pop('package-manifest.json')
        if package['schema'] != 'NOV25-OFFLINE-PACKAGE-1' or actual != package['files']:
            raise ValueError('package inventory differs from contents')
        folder = root/'snapshot'
        stamp, required = contents(folder,root/'intake',root/'updates')
        if stamp != package['as_of'] or set(required) != set(actual):
            raise ValueError('package membership or cutoff differs from snapshot')
        # This file is the exact captured prefix/slice. Use it as the original collection log during replay.
        os.link(folder/'refreshes.jsonl',root/'intake/refreshes.jsonl')
        for alias,name in review.jleague.SLICES.items():
            if (folder/alias).is_file():
                dest = root/'intake'/name
                dest.parent.mkdir(parents=True,exist_ok=True)
                os.link(folder/alias,dest)
        channel = folder/'channel-input.json'
        _, rebuilt = review.build(root/'intake',root/'updates',stamp,channel if channel.exists() else None)
        if any((folder/name).read_bytes() != data for name,data in rebuilt.items()) or set(rebuilt) != set(snapshot_files(folder)[0]['files']):
            raise ValueError('offline replay differs from the packaged status or FT review')
        ft = review.originals.read(folder/'ft-review.json')
        result = dict(as_of=stamp,verified_files=len(actual),ft90=ft['certified_ft90'],pending=ft['pending'],
                      r7_settled=ft['research']['R7']['cumulative_settled'],package_sha256=review.originals.sha(path))
        if 'result_crosscheck' in ft:
            result['official_secondary'] = ft['independent_official_secondary']
        return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command',required=True)
    make = commands.add_parser('pack')
    batch = make.add_mutually_exclusive_group()
    batch.add_argument('--snapshot',type=Path,help='existing immutable snapshot')
    batch.add_argument('--at',help='build and package the review at a zoned cutoff')
    make.add_argument('--snapshots',type=Path,default=review.HERE/'snapshots')
    make.add_argument('--intake',type=Path,default=review.INTAKE)
    make.add_argument('--updates',type=Path,default=review.UPDATES)
    make.add_argument('--out',type=Path,default=review.HERE/'packages')
    check = commands.add_parser('verify')
    check.add_argument('package',type=Path)
    a = parser.parse_args()
    if a.command == 'pack':
        folder = a.snapshot or review.write_snapshot(a.intake,a.updates,a.snapshots,a.at)
        print(pack(folder,a.intake,a.updates,a.out))
    else:
        print(json.dumps(verify(a.package)))
