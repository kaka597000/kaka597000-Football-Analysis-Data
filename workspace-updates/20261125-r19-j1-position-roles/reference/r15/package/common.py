"""File formats, source pins and numerical settings shared by the R15 builder and offline verifier."""
from datetime import datetime, timezone
import csv
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tarfile

SLUG = '20261125-r15-j1-lineups'
DEST = Path('workspace-updates') / SLUG
WORKFLOW = 'r15-j1-lineups.yml'
SIDES = ('home', 'away')
PROTOCOL = 'research/20261125-r15-j1/protocol.json'
REGISTRATION = 'd2ccb7b10163abba583374cdd3023b7441bceeb7'
SOURCE_COMMIT = '993686077a360705fb02c0667de96fc32b590e3b'
PROTOCOL_SHA = 'da900a991d6801de4547605b452d699dc71bcba28b6b6115b77ae583eb370e91'
PANEL_SHA = 'd0e9591d8221bd3e1f41b480a7f14c5eb743f1020ca2afaae23454bad49c8140'
IDS_SHA = 'd6b7fff542311b363f9ab6b7b827a998a909c92588112ebd825c8097e2aed06f'
ARCHIVES = {
    'r5': ('20261123-all-scope-kpi', 'models/jpn.1.tar.gz',
           'b9c883ee9055b0e562e8ad5b482a26dab219d1c0d6bd76ae0c16f74a42f23edb',
           'f3b6fa64903e97a6c74966362894c3378dfe5bca03a4a84709d4c694946ed3d8'),
    'r7': ('20261123-prematch-literature', 'models/jpn.1.tar.gz',
           'b6261ab328fe4ade9178dacb587fb819e765c80ef7fb2c6721abe0b16b98d183',
           'e2ed191e29150ba59bf9623ce2a44b265e8b71c9e777d9197ec869975a957df3'),
    'r10': ('20261125-r10-shot-conversion', 'replay/main.tar.gz',
            '7aa2c0d85ccc82779a7e922d3ed1b5184f576362ef958590ecce71bc80039f77',
            'f136707b0d5cbbac883f74cc9ce8dc85e9bc434ece591a2ba8c72c327faaf8cb'),
}
OUTPUTS = ('inputs.json', 'coverage.json', 'roster-coverage.jsonl.gz', 'fit.json', 'forward.json',
           'forecasts.jsonl.gz', 'selected-days.jsonl.gz', 'metrics.json')
FEATURES = ('own_attack_form', 'opponent_concession_form', 'own_attack_rating',
            'opponent_defensive_concession_rating', 'own_attack_retention', 'opponent_defence_retention')
FOLDS = {'train': 1912, 'validation': 380, 'evaluation': 380, 'recent': 150}
NUMERICAL_ENV = {
    'NPY_DISABLE_CPU_FEATURES': 'AVX512F',
    'OPENBLAS_CORETYPE': 'Haswell',
    'OPENBLAS_NUM_THREADS': '1',
    'OMP_NUM_THREADS': '1',
    'MKL_NUM_THREADS': '1',
    'NUMEXPR_NUM_THREADS': '1',
}


def replay_environment(pythonpath, tmp):
    """Set the NumPy and BLAS configuration before a fresh interpreter imports either library."""
    return dict(os.environ, **NUMERICAL_ENV, PYTHONPATH=pythonpath, PYTHONHASHSEED='0',
                PYTHONDONTWRITEBYTECODE='1', MPLCONFIGDIR=str(tmp/'mpl'))


def require(ok, detail):
    if not ok:
        raise ValueError(str(detail))


def digest(body):
    return hashlib.sha256(body).hexdigest()


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def encode(obj):
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(',', ':')) + '\n').encode()


def pretty(obj):
    return (json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()


def rows(path):
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rb') as stream:
        return [json.loads(line) for line in stream]


def unique(items, key):
    result = {}
    for row in items:
        value = row[key]
        require(value not in result, ('duplicate', key, value))
        result[value] = row
    return result


def utc(stamp):
    value = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
    require(value.utcoffset() is not None, ('unzoned timestamp', stamp))
    return value.astimezone(timezone.utc)


def fold(day):
    for name, before in zip(FOLDS, ('2024-01-01', '2025-01-01', '2026-01-01')):
        if day < before:
            return name
    return 'recent'


def gz(body):
    stream = io.BytesIO()
    with gzip.GzipFile(filename='', fileobj=stream, mode='wb', mtime=0, compresslevel=6) as out:
        out.write(body)
    return stream.getvalue()


def ledger(items):
    return gz(b''.join(encode(row) for row in items))


def csv_data(records):
    stream = io.StringIO(newline='')
    csv.writer(stream, lineterminator='\n').writerows(records)
    return stream.getvalue().encode()


def add_bytes(tar, name, body):
    member = tarfile.TarInfo(name)
    member.size = len(body)
    member.mode = 0o644
    tar.addfile(member, io.BytesIO(body))


def tar_gz(path, files):
    with path.open('xb') as stream, gzip.GzipFile(filename='', mode='wb', fileobj=stream, mtime=0) as z:
        with tarfile.open(fileobj=z, mode='w|', format=tarfile.USTAR_FORMAT) as tar:
            for name, body in sorted(files.items()):
                add_bytes(tar, name, body)


def safe_name(name):
    p = PurePosixPath(name)
    require(p.parts and not p.is_absolute() and '..' not in p.parts and p.as_posix() == name, ('archive path', name))
    return name


def unpack(path, dest):
    names = set()
    with tarfile.open(path, mode='r|*') as tar:
        for member in tar:
            name = safe_name(member.name)
            require(name not in names and member.isfile(), ('archive member', name))
            names.add(name)
            target = dest / name
            target.parent.mkdir(exist_ok=True, parents=True)
            with target.open('xb') as out:
                shutil.copyfileobj(tar.extractfile(member), out)
    return names


def inventory(root, exclude=()):
    return {p.relative_to(root).as_posix(): sha(p) for p in sorted(root.rglob('*'))
            if p.is_file() and p.relative_to(root).as_posix() not in exclude}


def valid_sha(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def member(tar, name):
    info = tar.getmember(name)
    require(info.isfile(), ('expected regular file', name))
    return tar.extractfile(info).read()
