"""Verify the additive research delta into a NEW stage; never overwrite assets."""
import argparse,hashlib,json,tarfile
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('--stage',required=True);a=p.parse_args()
    here=Path(__file__).resolve().parent;stage=Path(a.stage).resolve()
    if stage.exists():raise SystemExit('Stage exists; no overwrite allowed')
    m=json.loads((here/'manifest.json').read_text());archive=here/m['archive']
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=m['archive_sha256']:raise ValueError('archive checksum')
    expected={x['path']:x for x in m['files']}
    if len(expected)!=len(m['files']):raise ValueError('duplicate manifest paths')
    stage.mkdir(parents=True);seen=set()
    with tarfile.open(archive,'r:gz') as tar:
        for member in tar:
            dest=(stage/member.name).resolve()
            if (not member.isfile() or not dest.is_relative_to(stage) or member.name in seen
                    or member.name not in expected):raise ValueError('unsafe or unexpected member')
            data=tar.extractfile(member).read();e=expected[member.name]
            if len(data)!=e['bytes'] or hashlib.sha256(data).hexdigest()!=e['sha256']:raise ValueError('file checksum')
            dest.parent.mkdir(parents=True,exist_ok=True)
            with dest.open('xb') as f:f.write(data)
            seen.add(member.name)
    if seen!=set(expected):raise ValueError('missing files')
    print(json.dumps({'verified_files':len(seen),'production_overwritten':False,'stage':str(stage)}))
if __name__=='__main__':main()
