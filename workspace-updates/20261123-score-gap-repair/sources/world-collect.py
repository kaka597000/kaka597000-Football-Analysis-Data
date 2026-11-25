#!/usr/bin/env python3
"""Retrieve public ESPN and OpenFootball source snapshots with Python urllib's default User-Agent."""
import base64,datetime,hashlib,json,pathlib,urllib.error,urllib.request
ROOT=pathlib.Path('/workspace/WCPP/reports/kpi-optimization-20261123-r6/world-early'); RAW=ROOT/'raw'; ESPN=RAW/'espn'; OF=RAW/'openfootball'
YEARS=[1994,1998,2002,2006,2010,2014]
for d in (ESPN,OF):d.mkdir(parents=True,exist_ok=True)
def get(url,path):
    req=urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req,timeout=45) as r: body=r.read(); status=r.status; headers=dict(r.headers)
    except urllib.error.HTTPError as e: body=e.read();status=e.code;headers=dict(e.headers)
    except Exception as e: body=str(e).encode();status=None;headers={}
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(body)
    meta={'url':url,'http_status':status,'retrieved_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest(),'content_type':headers.get('Content-Type'),'path':str(path.relative_to(ROOT))}
    path.with_suffix(path.suffix+'.meta.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
    try:data=json.loads(body) if status==200 else None
    except Exception:data=None
    return data,meta
# Download ESPN scoreboards by tournament year.
for year in YEARS:
    url=f'https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates={year}&limit=1000'
    get(url,ESPN/f'fifa.world-{year}-scoreboard.json')
# Download exact OpenFootball GitHub blob response bodies through the GitHub API.
tree_url='https://api.github.com/repos/openfootball/worldcup.json/git/trees/master?recursive=1'
tree,tree_meta=get(tree_url,OF/'github-tree.json')
for year in YEARS:
    target=f'{year}/worldcup-full.json'; entry=next((x for x in (tree or {}).get('tree',[]) if x.get('path')==target),None)
    if not entry:continue
    envelope,meta=get(entry['url'],OF/str(year)/'blob-response.json')
    if not envelope or envelope.get('encoding')!='base64':continue
    body=base64.b64decode(envelope['content']); decoded=OF/str(year)/'worldcup-full.json';decoded.write_bytes(body)
    decoded_meta=dict(meta);decoded_meta.update({'github_blob_sha':entry.get('sha'),'decoded_path':str(decoded.relative_to(ROOT)),'decoded_sha256':hashlib.sha256(body).hexdigest()})
    decoded.with_suffix('.json.meta.json').write_text(json.dumps(decoded_meta,ensure_ascii=False,indent=2)+'\n')
print('Raw requests captured. Run build_panel.py to assemble the 90-minute dataset.')
