"""Verify the Phoenix capture bundle, or recover its original response bytes and SQLite database."""
import argparse
from hashlib import sha256, scrypt
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile

HERE = Path(__file__).resolve().parent
AAD = b'WCPP-PHOENIX-ARCHIVE-v1'


def payload(metadata):
    pieces = []
    for part in metadata['parts']:
        path = HERE / part['file']
        block = path.read_bytes()
        if len(block) != part['bytes'] or sha256(block).hexdigest() != part['sha256']:
            raise ValueError('corrupt archive part ' + path.name)
        pieces.append(block)
    data = b''.join(pieces)
    if sha256(data).hexdigest() != metadata['ciphertext_sha256']:
        raise ValueError('archive ciphertext hash mismatch')
    return data


def derive(credential, salt):
    return scrypt(b'wcpp/phoenix/backup/v1\0'+credential.strip().encode(),
                  salt=salt, n=32768, r=8, p=1, maxmem=128 << 20, dklen=32)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-only', action='store_true')
    parser.add_argument('--root', type=Path, help='new directory for the raw captures')
    parser.add_argument('--source', type=Path, help='Football-Analysis source checkout')
    parser.add_argument('--db', type=Path, help='new standalone SQLite database')
    parser.add_argument('--key-env', default='fenghuangtest', help='name of environment variable holding the original credential')
    args = parser.parse_args()
    meta = json.loads((HERE/'bundle.json').read_text())
    encrypted = payload(meta)
    if args.verify_only:
        print(f"Verified {len(meta['parts'])} ciphertext parts, {len(encrypted):,} bytes.")
        return
    if not all((args.root, args.source, args.db)):
        parser.error('restore requires --root, --source and --db')
    if args.root.exists() and any(args.root.iterdir()):
        parser.error('the restore directory must be empty')
    if args.db.exists():
        parser.error('select a new SQLite path')
    secret = os.environ.get(args.key_env)
    if not secret:
        parser.error('the original archive credential is missing from the named environment variable')
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    plain = AESGCM(derive(secret, bytes.fromhex(meta['salt']))).decrypt(
        bytes.fromhex(meta['nonce']), encrypted, AAD)
    if sha256(plain).hexdigest() != meta['compressed_sha256']:
        raise ValueError('decrypted tar hash mismatch')
    args.root.mkdir(parents=True,exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(plain),mode='r:gz') as archive:
        for member in archive:
            target = (args.root/member.name).resolve()
            if not member.isfile() or not target.is_relative_to(args.root.resolve()):
                raise ValueError('unexpected archive member')
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(archive.extractfile(member).read())
    args.db.parent.mkdir(parents=True,exist_ok=True)
    code=args.source/'runtime/database'
    subprocess.run([sys.executable,str(code/'phoenix.py'),'--manifest',str(args.root/'database-manifest.jsonl'),
                    '--root',str(args.root),'--db',str(args.db),'--scope',str(args.root/'scope.json')],check=True)
    check=args.root/'restored-audit.json'
    subprocess.run([sys.executable,str(code/'phoenix_validation.py'),'--db',str(args.db),'--out',str(check)],check=True)
    actual=json.loads(check.read_text())
    official=json.loads((HERE/'database-audit.json').read_text())
    for report in (actual,official):
        report.pop('database',None)
    if actual!=official:
        raise ValueError('restored SQL audit differs from the original unified database')
    print(f"Restored {args.db} and reproduced the original statistical audit.")


if __name__ == '__main__':
    main()
