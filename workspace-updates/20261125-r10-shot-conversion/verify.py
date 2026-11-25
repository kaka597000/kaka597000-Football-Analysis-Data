"""Independently verify R10 archived scores, paired changes, price settlement and first issues."""
from collections import Counter, defaultdict
from datetime import datetime
import gzip
import hashlib
import json
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parent
KPI = ('score_top1','score_top3','wdl','actual_ou')


def require(condition, detail):
    if not condition:
        raise ValueError(detail)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    return sha(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode())


def read(name):
    return json.loads((ROOT/name).read_bytes())


def tar_json(bundle, name):
    return json.load(bundle.extractfile(name))


def settlement(total, line, side):
    if side is None:
        return None
    require(side in ('over','under') and type(line) in (int,float) and line>=0 and float(4*line).is_integer(), 'invalid price line')
    q = round(line*4)
    margins = [4*total-v for v in ([q-1,q+1] if q%2 else [q])]
    signs = sum((m>0)-(m<0) for m in margins)*(1 if side=='over' else -1)
    if signs==0:
        return 'PUSH'
    full = abs(signs)==len(margins)
    return ('FULL_' if full else 'HALF_') + ('WIN' if signs>0 else 'LOSS')


def score(row):
    h,a = row['actual']
    result, exact = ('home' if h>a else 'away' if a>h else 'draw'), f'{h}-{a}'
    arms = {}
    for key, pick in row['forecast'].items():
        picks = pick.get('top3') or []
        if picks:
            require(len(picks)==len(set(picks))==3 and picks[0]==pick['primary'], row['id'])
        category = settlement(h+a,row['line'],pick.get('total_side'))
        arms[key] = ([pick['primary']==exact if pick.get('primary') else None, exact in picks if picks else None,
                      result==pick['wdl'] if pick.get('wdl') else None,
                      category=='FULL_WIN' if category not in (None,'PUSH') else None], category)
    return arms


def verify_group(rows, archived):
    scored = [score(row) for row in rows]
    for arm, expectation in archived['scores'].items():
        require(expectation['games']==len(rows),arm)
        categories = Counter(c for s in scored if (c:=s[arm][1]) is not None)
        require(categories == expectation['settlements'],arm+' settlements')
        for i,k in enumerate(KPI):
            hits = [s[arm][0][i] for s in scored if s[arm][0][i] is not None]
            require([sum(hits),len(hits)]==expectation['counts'][k],arm+' '+k)
    controls={'market':('market','candidate'),'r7':('r7','candidate'),'r9':('r9','candidate'),
              'same_runtime':('local_r7','local_candidate'),'pace_vs_mean_only':('mean_only','fixed_full')}
    for c,metrics in archived['comparisons'].items():
        a,b=controls[c]
        for i,k in enumerate(KPI):
            pairs=[(s[a][0][i],s[b][0][i]) for s in scored if None not in (s[a][0][i],s[b][0][i])]
            if not metrics:
                require(not pairs,c); continue
            old,new=sum(x for x,y in pairs),sum(y for x,y in pairs)
            expect=metrics[k]
            require([old,new,new-old,len(pairs),sum(x!=y for x,y in pairs)]==
                    [expect[v] for v in ('control_hits','candidate_hits','net','paired','disagreements')],c+' '+k)


def verify_replay():
    merged=read('replay/metrics.json')
    n=0
    for mode in ('main','independent','elite'):
        with tarfile.open(ROOT/('replay/'+mode+'.tar.gz')) as t:
            windows=defaultdict(list); metrics=tar_json(t,'metrics.json')
            for member in t.getnames():
                if not member.endswith('/forecasts.jsonl.gz'):continue
                folder=member.rsplit('/',1)[0]
                fit=tar_json(t,folder+'/fit.json');seen=set()
                with gzip.GzipFile(fileobj=t.extractfile(member)) as f:
                    for row in map(json.loads,f):
                        require(row['id'] not in seen and row['cohort']==fit['competition'],row['id'])
                        seen.add(row['id']);windows[row['window']].append(row)
                        require(row['date']>=fit['bounds'][1],row['id'])
                n+=len(seen)
            for window,report in metrics.items():
                rows=windows[window]
                require(report==merged[window],window)
                require(report['fixture_set_sha256']==sha('\n'.join(sorted(r['cohort']+'|'+r['id'] for r in rows)).encode()),window)
                verify_group(rows,report['overall'])
                for cohort,r in report['competitions'].items():
                    verify_group([q for q in rows if q['cohort']==cohort],r)
    return n


def record(raw,ref):
    signed=dict(raw);signature=signed.pop('record_sha256')
    require(signature==digest(signed)==ref['sha256'] and ref.get('id',ref.get('freeze_id'))==signed['freeze_id'] and
            signed['evaluation_slot']=='FIRST_PREMATCH' and signed['revision']==1, signed['freeze_id'])
    at=lambda k:datetime.fromisoformat(k.replace('Z','+00:00'))
    require(at(signed['fixture']['cutoff_at'])<=at(signed['recorded_at'])<at(signed['fixture']['kickoff_at']),signed['freeze_id'])
    return signed


def verify_forward():
    with tarfile.open(ROOT/'forward/first-issues.tar.gz') as t:
        idx=tar_json(t,'receipts.json'); ref=idx['registration']; plan=record(tar_json(t,ref['file']),ref)
        require(set(plan['payload']['fixtures'])==set(idx['matches']),'population mismatch')
        for mid,receipt in idx['matches'].items():
            issue=record(tar_json(t,receipt['file']),receipt);f=issue['fixture'];p=issue['payload']
            require(all(f[k]==v for k,v in plan['payload']['fixtures'][mid].items()) and p['registration_sha256']==ref['sha256'],mid)
            pick=p['forecasts']['candidate'];require(len(set(pick['top3']))==len(pick['top3'])==3 and pick['primary']==pick['top3'][0],mid)
    with tarfile.open(ROOT/'forward/ranked.tar.gz') as t:
        r=tar_json(t,'plan.json');ranked=record(tar_json(t,r['file']),r);ident=ranked['payload']['identity']
        require(ident['source_registration']==ref['sha256'],'ranked source')
        pools=defaultdict(list)
        with tarfile.open(ROOT/'forward/first-issues.tar.gz') as orig:
            for mid,v in idx['matches'].items():
                issue=tar_json(orig,v['file']);p=issue['payload'];f=issue['fixture']
                pools[f['cohort']].append((-p['quality']['p_first'],datetime.fromisoformat(f['kickoff_at']),mid))
        for c,selected in ident['selected'].items():
            require([s['match_id'] for s in selected]==[u[2] for u in sorted(pools[c])[:3]],c)
    with tarfile.open(ROOT/'formal/nov25-issues-and-evidence.tar.gz') as t:
        rows=read('formal/nov25-display.json')
        for item in rows['actual_display']:
            for key in ('model_reference','comprehensive_reference'):
                v=item[key];rec=record(tar_json(t,'canonical/'+v['freeze_id']+'.json'),v)
                if key=='comprehensive_reference':
                    require(all(item[k]==rec['payload'][k] for k in ('primary','top3','wdl','total_line','total_direction')),item['match_id'])
        v=rows['ranked_batch'];rec=record(tar_json(t,'canonical/'+v['freeze_id']+'.json'),v)
        require(rec['payload']['top3']==rows['actual_display'],'AFC selected display')
    with tarfile.open(ROOT/'formal/nov26-ucl-three.tar.gz') as t:
        ucl=read('formal/nov26-ucl-firsts.json')
        v=ucl['batch'];batch=record(tar_json(t,'canonical/'+v['freeze_id']+'.json'),v)
        require(len(batch['payload']['top3'])==3 and batch['payload']['top3']==ucl['selections'],'complete UCL batch')
        text=t.extractfile('issuance/message.txt').read()
        require(sha(text)==batch['payload']['text_sha256'] and text.decode()==ucl['text'],'UCL body commitment')
        for item in ucl['selections']:
            v=item['comprehensive_reference'];rec=record(tar_json(t,'canonical/'+v['freeze_id']+'.json'),v)
            require(rec['payload']['displayed_scores']==item['top3'] and rec['payload']['authored_display']['text'] in ucl['text'],
                    item['match_id'])
            pair=rec['payload']['current_test_reference']
            snapshot=tar_json(t,'canonical/'+pair['freeze_id']+'.json'); signature=snapshot.pop('record_sha256')
            first=tar_json(t,'canonical/'+pair['freeze_id'].split('-v')[0]+'-v000001.json')
            require(signature==digest(snapshot)==pair['sha256'] and snapshot['previous_sha256']==first['record_sha256']
                    and snapshot['match_id']==item['match_id'], 'UCL model revision')
    return len(idx['matches'])


def verify_files():
    manifest=read('manifest.json')
    for name, expected in manifest['files'].items():
        with (ROOT/name).open('rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
        require(actual==expected,name)
    return len(manifest['files'])


if __name__=='__main__':
    print(json.dumps(dict(files=verify_files(),out_of_time_rows=verify_replay(),forward_first_issues=verify_forward(),
                          verified='archived counts, paired hits, Asian settlements, dated freezes and rankings')))
