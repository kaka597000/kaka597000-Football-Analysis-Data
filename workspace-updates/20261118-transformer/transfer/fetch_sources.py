"""Fetch the five complete source CSVs for the prespecified later season."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent
LEAGUES = ('D1','E0','F1','I1','SP1')


def fetch(league):
    url = f'https://www.football-data.co.uk/mmz4281/2627/{league}.csv'
    with urlopen(url, timeout=20) as response:
        if response.status != 200:
            raise ValueError(f'{league} HTTP {response.status}')
        raw = response.read()
        modified = response.headers.get('last-modified')
    first = datetime.now(timezone.utc).isoformat()
    path = HERE/'raw'/f'2627_{league}.csv'
    if path.exists() and path.read_bytes() != raw:
        raise ValueError(f'Original snapshot would change: {league}')
    path.write_bytes(raw)
    return {'url':url,'captured_at':first,'last_modified':modified,'file':path.name,
            'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}


if __name__ == '__main__':
    snapshot = HERE/'raw/source-metadata.json'
    if snapshot.exists():
        raise SystemExit('Retained sources already exist; use evaluate.py to replay offline.')
    with ThreadPoolExecutor(max_workers=5) as pool:
        sources = list(pool.map(fetch, LEAGUES))
    snapshot.write_text(json.dumps(sources,sort_keys=True,indent=2)+'\n')
