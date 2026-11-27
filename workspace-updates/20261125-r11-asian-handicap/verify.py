"""Check raw same-book quote columns, dated fixture identities and every paired R11 score."""
from collections import Counter, defaultdict
import csv
from datetime import datetime
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile

ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('r10_evidence',ROOT.parent/'20261125-r10-shot-conversion/verify.py')
v=importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
FIELDS=('B365H','B365D','B365A','B365>2.5','B365<2.5','AHh','B365AHH','B365AHA','AHCh','B365CAHH','B365CAHA')
ARCHIVE=('regular_1x2_B365H','regular_1x2_B365D','regular_1x2_B365A','regular_total25_over_B365',
         'regular_total25_under_B365','regular_AH_home_handicap_AHh','regular_AH_home_price_B365AHH','regular_AH_away_price_B365AHA',
         'closing_AH_home_handicap_AHCh','closing_AH_home_price_B365CAHH','closing_AH_away_price_B365CAHA')


def same_odds(a,b):
    a=a.strip();b=b.strip()
    return (not a and not b) or (bool(a and b) and float(a)==float(b))


def raw_inputs(name):
    matched={}; fixture_totals={}
    with tarfile.open(ROOT/(name+'.tar.gz')) as t:
        raw={}
        for f in t.getnames():
            if f.startswith('raw/') and f.lower().endswith('.csv'):
                data=t.extractfile(f).read()
                try:text=data.decode('utf-8-sig')
                except UnicodeDecodeError:text=data.decode('latin1')
                raw[v.sha(data)]=list(csv.DictReader(io.StringIO(text)))
            if f.endswith('.panel.jsonl') or f=='fixture-panels.jsonl':
                for g in map(json.loads,t.extractfile(f)):
                    key=(g['competition'],g['id'])
                    v.require(key not in fixture_totals,'duplicate match')
                    fixture_totals[key]=g
        old=name=='intake'
        sheet='r11_nonclosing_primary.csv' if old else 'market-rows.csv'
        for record in csv.DictReader(io.TextIOWrapper(t.extractfile(sheet),encoding='utf-8-sig')):
            key=(record['competition'],record['id'])
            pos=int(record['source_row_physical' if old else 'csv_row_physical'])
            src=raw[record['source_sha256']][pos-2]
            g=fixture_totals[key]
            day=src['Date'].strip()
            fmt='%d/%m/%Y' if len(day.split('/')[-1])==4 else '%d/%m/%y'
            v.require(datetime.strptime(day,fmt).date().isoformat()==g['date'] and
                      int(src['FTHG'])==g['home_goals'] and int(src['FTAG'])==g['away_goals']
                      and src['HomeTeam'].strip()==g['home'] and src['AwayTeam'].strip()==g['away'],key)
            for table_key,raw_key in zip(ARCHIVE if old else FIELDS,FIELDS,strict=True):
                v.require(same_odds(record.get(table_key) or '',src.get(raw_key) or ''),(key,raw_key))
            q=[src.get(k,'') for k in FIELDS[:8]]
            legal=all(str(x or '').strip() for x in q) and (4*float(q[5])).is_integer()
            matched[key]=bool(legal)
    return fixture_totals,matched


def check_group(rows,group):
    scored=[v.score(row) for row in rows]
    for arm,expected in group['scores'].items():
        v.require(len(rows)==expected['games'],arm)
        for i,metric in enumerate(v.KPI):
            hits=[s[arm][0][i] for s in scored if s[arm][0][i] is not None]
            v.require([sum(hits),len(hits)]==expected['counts'][metric],(arm,metric))
        v.require(Counter(s[arm][1] for s in scored if s[arm][1])==expected['settlements'],arm)
    for arm,comp in group['paired'].items():
        for i,k in enumerate(v.KPI):
            pairs=[(s[arm][0][i],s['candidate'][0][i]) for s in scored if None not in (s[arm][0][i],s['candidate'][0][i])]
            if not pairs and not comp:continue
            old=sum(x for x,y in pairs);new=sum(y for x,y in pairs)
            v.require((old,new,new-old,len(pairs),sum(x!=y for x,y in pairs))==
                tuple(comp[k][f] for f in ('control_hits','candidate_hits','net','paired','disagreements')),(arm,k))


def main():
    manifest=json.loads((ROOT/'manifest.json').read_bytes())
    for file,sha in manifest['files'].items():
        with (ROOT/file).open('rb') as fp:v.require(hashlib.file_digest(fp,'sha256').hexdigest()==sha,file)
    original,old=raw_inputs('intake');extra,new=raw_inputs('extension')
    v.require(not (original.keys() & extra.keys()),'duplicate extension')
    games=original|extra; markets=old|new
    loaded=defaultdict(list);seen=set()
    with tarfile.open(ROOT/'replay.tar.gz') as rt:
        for name in rt.getnames():
            if not name.endswith('/forecasts.jsonl.gz'):continue
            folder=name.split('/')[0];fit=v.tar_json(rt,folder+'/fit.json')
            future=v.tar_json(rt,folder+'/forward.json')
            v.require(future['fit_sha256']==v.sha(rt.extractfile(folder+'/fit.json').read()) and future['dose']==fit['dose'],folder)
            for row in map(json.loads,gzip.GzipFile(fileobj=rt.extractfile(name))):
                key=(row['cohort'],row['id']);g=games[key]
                v.require(key not in seen and g['date']==row['date'] and g['source_sha256']==row['source_sha256']
                          and [g['home_goals'],g['away_goals']]==row['actual'],key)
                v.require(row['quote_complete']==markets.get(key,False),key)
                seen.add(key);loaded[row['window']].append(row)
        for table in ('metrics','matched-metrics'):
            results=v.tar_json(rt,table+'.json')
            v.require(results==json.loads((ROOT/(table+'.json')).read_bytes()),table)
            for w,summary in results.items():
                rows=[r for r in loaded[w] if table=='metrics' or r['quote_complete']]
                v.require(summary['fixture_set_sha256']==v.sha('\n'.join(sorted(r['cohort']+'|'+r['id'] for r in rows)).encode()),w)
                check_group(rows,summary['overall'])
                for c,g in summary['competitions'].items():check_group([r for r in rows if r['cohort']==c],g)
    print(json.dumps(dict(raw_archive_rows=len(old),valid_three_market_rows=sum(old.values()),extension_rows=len(new),
                          out_of_time_matches=len(seen),status='verified'),indent=2))


if __name__=='__main__':
    main()
