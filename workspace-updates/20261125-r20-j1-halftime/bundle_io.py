"""Immutable file and archive operations for the R20 data release."""

from hashlib import file_digest, sha256
from io import BytesIO
import ctypes
import errno
import gzip
import json
import os
from pathlib import Path, PurePosixPath
import re
import tarfile


def require(condition, message):
    if not condition:
        raise ValueError(message)


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def digest(body):
    return sha256(body).hexdigest()


def file_sha(path):
    with path.open('rb') as stream:
        return file_digest(stream, 'sha256').hexdigest()


def safe(name):
    require(isinstance(name, str) and name and '\\' not in name and '\0' not in name,
            f'invalid archive path {name!r}')
    path = PurePosixPath(name)
    require(not path.is_absolute() and path.parts and '..' not in path.parts and path.as_posix() == name,
            f'unsafe or noncanonical archive path {name!r}')
    return name


def checked_file(root, name):
    path = root / safe(name)
    require(path.resolve().is_relative_to(root.resolve()) and not path.is_symlink() and path.is_file(),
            f'missing or unsafe input {name}')
    return path


def write(root, name, body):
    path = root / safe(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(body)
    return path


def checked_bytes(body, ref):
    require(len(body) == ref['bytes'] and digest(body) == ref['sha256'], f'acquisition bytes differ: {ref}')
    return body


def archive(path, files):
    """GNU-compatible deterministic gzip/tar containing only named regular files."""
    with path.open('xb') as stream, gzip.GzipFile(fileobj=stream, mode='wb', filename='', mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode='w') as tar:
            for name, body in sorted(files.items()):
                item = tarfile.TarInfo(safe(name))
                item.size = len(body)
                tar.addfile(item, BytesIO(body))


def members(path, choose=lambda name: True):
    """Read only chosen members, while checking type, uniqueness and paths of the whole archive."""
    seen, selected = set(), {}
    with tarfile.open(path, 'r|*') as tar:
        for item in tar:
            name = safe(item.name)
            require(item.isfile() and name not in seen, f'duplicate or non-file archive member {name}')
            seen.add(name)
            if choose(name):
                selected[name] = tar.extractfile(item).read()
    return selected


def first_files(folder, registration_sha, receipts_sha):
    for value in (registration_sha, receipts_sha):
        require(isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value), 'two independent full SHA-256 pins required')
    body = checked_file(folder, 'receipts.json').read_bytes()
    require(digest(body) == receipts_sha, 'original receipts.json bytes differ from independent pin')
    index = json.loads(body)
    require(set(index) == {'registration', 'matches'} and len(index['matches']) == 10
            and index['registration']['sha256'] == registration_sha, 'original registration or ten-first index differs')
    files = {'receipts.json': body}
    for ref in [index['registration'], *index['matches'].values()]:
        name = ref['file']
        require(re.fullmatch('[0-9a-f]{16}-v000001[.]json', name) and name == ref['id'] + '.json'
                and name not in files, f'different or duplicate first receipt {name}')
        files[name] = checked_file(folder, name).read_bytes()
    require({p.name for p in folder.iterdir()} == files.keys(), 'missing, revised or unindexed firsts')
    return files, json.loads(files[index['registration']['file']])


def install(staged, target):
    """Publish one fully verified directory; a repeated identical build is a read-only success."""
    # Linux RENAME_NOREPLACE also protects an empty destination created concurrently.
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.renameat2(-100, os.fsencode(staged), -100, os.fsencode(target), 1) == 0:
        return
    error = ctypes.get_errno()
    if error not in (errno.EEXIST, errno.ENOTEMPTY):
        raise OSError(error, os.strerror(error), target)
    require(target.is_dir() and not target.is_symlink(), 'output already exists with different type')
    names = {p.name for p in staged.iterdir()}
    require({p.name for p in target.iterdir()} == names
            and all(file_sha(checked_file(target, n)) == file_sha(staged / n) for n in names),
            'existing output differs; original directory was preserved')
