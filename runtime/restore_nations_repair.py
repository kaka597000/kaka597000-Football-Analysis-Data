"""Verify retained archives and restore exact bytes without replacing conflicts."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import tarfile


def sha(body):return hashlib.sha256(body).hexdigest()


def restore(repo,index_path,dest=None):
    repo=Path(repo).resolve();index=json.loads(Path(index_path).read_text())
    if index['schema']!='WCPP-NATIONS-REPAIR-ARCHIVE-1':raise ValueError('unsupported archive index')
    destination=Path(dest).resolve() if dest is not None else None
    groups=defaultdict(list);seen=set()
    for entry in index['files']:
        original=Path(entry['original_path'])
        if (not original.is_absolute() or '..' in original.parts or
                not str(original).startswith('/workspace/') or str(original) in seen):
            raise ValueError('invalid or duplicate restore path')
        seen.add(str(original));groups[entry['archive']].append(entry)
    restored=0
    for relative,entries in groups.items():
        archive=(repo/relative).resolve()
        if not archive.is_relative_to(repo):raise ValueError('archive outside data repository')
        metadata=index['archives'][relative]
        if archive.stat().st_size!=metadata['bytes'] or sha(archive.read_bytes())!=metadata['sha256']:
            raise ValueError('archive checksum mismatch')
        wanted=defaultdict(list)
        for entry in entries:wanted[entry['member']].append(entry)
        with tarfile.open(archive,'r|gz') as stream:
            members=set()
            for member in stream:
                path=Path(member.name)
                if (member.name in members or not member.isfile() or path.is_absolute() or '..' in path.parts):
                    raise ValueError('unsafe or duplicate archive member')
                members.add(member.name)
                if member.name not in wanted:continue
                body=stream.extractfile(member).read();checksum=sha(body)
                for entry in wanted[member.name]:
                    if len(body)!=entry['bytes'] or checksum!=entry['sha256']:
                        raise ValueError('retained member checksum mismatch')
                    if destination is not None:
                        target=destination/entry['original_path'].lstrip('/')
                        if not target.resolve().is_relative_to(destination):raise ValueError('restore path escaped destination')
                        if target.exists():
                            if not target.is_file() or sha(target.read_bytes())!=entry['sha256']:
                                raise ValueError('existing restore destination differs; refusing replacement')
                        else:
                            target.parent.mkdir(parents=True,exist_ok=True)
                            with target.open('xb') as handle:handle.write(body)
                    restored+=1
            if not set(wanted)<=members:raise ValueError('missing retained member')
    return {'verified_paths':restored,'archives':len(groups),'source_commit':index['source_commit'],
            'destination':str(destination) if destination else None,'active_model_promotion':False}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repo',default='.')
    p.add_argument('--index',default='workspace-updates/20261116-nations-repair/archive-index.json')
    p.add_argument('--dest');a=p.parse_args();print(json.dumps(restore(a.repo,a.index,a.dest)))
