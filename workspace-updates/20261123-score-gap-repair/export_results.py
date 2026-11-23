"""Create league-level CSVs and the review workbook from reproduced decisions."""
import argparse,csv,json,math
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

KEYS=('score_top1','score_top3','wdl','actual_ou')
LABELS=('首选比分','三选比分','胜平负','大小球全赢')
GOALS=(.20,.40,.65,.70)
WINDOWS={'evaluation':'历史主回放','recent':'近期复验','early':'独立早期赛事'}
ARMS={'r5':'上一版','conditional':'完整新模型','agreement':'有共识才改首选','retained_first':'固定旧首选','market':'同场市场','price_pair_proxy':'完整价格推算','no_process':'仅用进球校准','structural':'跨阶段基线','local_anchor':'原固定基线'}


def read(path):
    return json.loads(path.read_bytes())


def export(result,scope,forward,out,excel=False):
    out.mkdir(parents=True,exist_ok=True)
    names={x['code']:x['name'] for x in read(scope)['competitions']}
    tables={}
    pairs=[];quality=[];weights=[]
    for window,title in WINDOWS.items():
        table=[]
        for c,g in [('all',result[window]['aggregate']),*result[window]['competitions'].items()]:
            for arm,n in ARMS.items():
                row=dict(赛事=names.get(c,'全部纳入赛事'),赛事代码=c,模型=n,场次=g['n'],已知完整赛程场次=g['known_schedule_n'],实际盘线=g['actual_lines'],走水=g['pushes'],四分之一盘两边均无法全赢=g['quarter_boundary'])
                for k,label,target in zip(KEYS,LABELS,GOALS):
                    hits,d=g['scores'][arm][k]
                    row.update({label+'命中':hits,label+'分母':d,label+'命中率':hits/d if d else None,
                        label+'门槛':target,label+'有效样本尚差命中':max(0,math.ceil(round(target*d,8))-hits) if d else None})
                row['四项按完整赛程达标']=g['agreement_all_four_pass'] if arm=='agreement' and window=='evaluation' else g['all_four_pass'] if arm=='conditional' and window=='evaluation' else None
                table.append(row)
            for candidate,k in [('conditional','paired'),('agreement','agreement_paired')]:
                for control,metrics in g[k].items():
                    for metric,stats in metrics.items():
                        ci=stats['date_cluster_ci'] or [None,None]
                        pairs.append(dict(窗口=title,赛事=names.get(c,'全部纳入赛事'),候选=ARMS[candidate],对照=ARMS[control],指标=LABELS[KEYS.index(metric)],共同场数=stats['eligible'],改对=stats['gained'],改错=stats['lost'],净增命中=stats['net_hits'],置信下限=ci[0],置信上限=ci[1]))
            for arm,q in g['probability_quality'].items():
                quality.append(dict(窗口=title,赛事=names.get(c,'全部纳入赛事'),模型=ARMS[arm],场数=q['n'],
                    首选概率=q['p1'],三选概率=q['p3'],最大胜平负概率=q['wdl_max'],条件全赢概率=q['expected_full_win'],
                    精确比分对数损失=q['score_nll'],胜平负Brier=q['wdl_brier']))
        tables[title]=table
    tables['同场改对改错']=pairs;tables['概率质量']=quality
    for scenario in ('replay','final-early'):
        for path in sorted((forward.parent/scenario).glob('*/fit.json')):
            m=read(path)
            for arm,betas in m['coefficients'].items():
                weights.append(dict(数据窗口='主历史' if scenario=='replay' else '独立早期',赛事=names[m['competition']],模型=arm,训练截止=m['training_through'],训练场数=m['training_matches'],**dict(zip(m['feature_names'],betas))))
    tables['实际拟合权重']=weights
    frows=[]
    for ref in read(forward/'receipts.json')['matches'].values():
        r=read(forward/ref['file']); f,d=r['fixture'],r['payload'];p=d['forecasts']['agreement']
        frows.append(dict(北京时间=datetime.fromisoformat(f['kickoff_at']).astimezone(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M'),赛事=names[f['cohort']],主队=d['home_name'],客队=d['away_name'],首选=p['primary'],备选一=p['top3'][1],备选二=p['top3'][2],
            胜平负={'home':'主胜','draw':'平','away':'客胜'}[p['wdl']],真实盘线=d['line'],大小球={'over':'大','under':'小',None:None}[p['total_side']],旧首选=d['forecasts']['r5']['primary'],完整模型首选=d['forecasts']['conditional']['primary'],结算='待赛',比赛ID=f['match_id'],冻结哈希=r['record_sha256']))
    tables['未来首次冻结']=sorted(frows,key=lambda x:(x['北京时间'],x['比赛ID']))
    files=['primary','recent','early','paired','probabilities','weights','forward']
    for filename,(sheet,rows) in zip(files,tables.items()):
        with (out/(filename+'.csv')).open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    if excel:
        import xlsxwriter
        with xlsxwriter.Workbook(out/'score-gap-review.xlsx') as book:
            hdr=book.add_format({'bold':True,'font_color':'white','bg_color':'#164553','text_wrap':True,'valign':'vcenter'})
            pct=book.add_format({'num_format':'0.0%'});num=book.add_format({'num_format':'0.000'})
            for sheet,rows in tables.items():
                ws=book.add_worksheet(sheet);keys=list(rows[0]);ws.freeze_panes(1,2);ws.set_row(0,34)
                for j,key in enumerate(keys):
                    ws.write(0,j,key,hdr);ws.set_column(j,j,max(14,min(33,len(key)*2+2)))
                for i,r in enumerate(rows,1):
                    for j,k in enumerate(keys):
                        v=r[k]
                        if v is None:continue
                        fmt=pct if isinstance(v,float) and any(s in k for s in ('命中率','门槛','概率','置信')) else num if isinstance(v,float) else None
                        ws.write(i,j,v,fmt)
                ws.autofilter(0,0,len(rows),len(keys)-1)


if __name__=='__main__':
    ap=argparse.ArgumentParser()
    for key in ('report','scope','forward','out'):ap.add_argument('--'+key,required=True,type=Path)
    ap.add_argument('--xlsx',action='store_true')
    a=ap.parse_args();export(read(a.report),a.scope,a.forward,a.out,a.xlsx)
