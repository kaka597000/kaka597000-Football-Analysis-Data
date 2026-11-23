"""Export per-competition gate denominators, independent market comparisons and future first issues."""
import argparse
import csv
import json
from pathlib import Path

METRICS=('score_top1','score_top3','wdl','actual_ou')
ZH=('首选比分','三选比分','胜平负','真实大小球')
TARGETS=(.20,.40,.65,.70)


def read(p):
    return json.loads(p.read_bytes())


def lines(p):
    return [json.loads(s) for s in p.open() if s.strip()]


def save_csv(path,rows):
    with path.open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)


def collect(root,scope):
    base=[];paired=[];phases=[]
    coverage=read(root/'asof-coverage.json')
    for c in scope['competitions']:
        code=c['code'];folder=root/'study'/code
        r=read(folder/'report.json');local=read(folder/'neighbor-report.json')
        locks=read(folder/'neighbor-lock.json');source=read(root/'panels'/(code+'-source.json'))
        for window in ('evaluation','recent'):
            v=r[window];n=v['population'];z=local[window]
            row={'赛事':c['name'],'代码':code,'窗口':window,'90分钟场次':n,'原训练场':r['fit'],'选型场':r['selection'],
                 '真实盘线场':v.get('priced_line',0),'整盘走水':v.get('pushes',0)}
            expected=coverage[code]['known_fixture_target'] if window=='evaluation' else None
            row['已知应纳入场次']=expected
            row['全赛事场次数已核齐']=(expected==n) if expected is not None else None
            for j,k in enumerate(METRICS):
                hits,count=z['metrics']['candidate'][k]
                gate=n-(row['整盘走水'] if k=='actual_ou' else 0)
                yes=bool(count and count==gate and hits/count>=TARGETS[j])
                row.update({ZH[j]+'命中':hits,ZH[j]+'分母':count,ZH[j]+'命中率':hits/count if count else None,
                            ZH[j]+'完整分母达标':yes,ZH[j]+'距门槛场':max(0,(__import__('decimal').Decimal(str(TARGETS[j]))*gate).__ceil__()-hits) if gate else None})
                for control,label in [('market','同场市场'),('original','上一层模型'),('team','球队强弱基线')]:
                    cp=z['vs_'+control].get(k,{});m,cnt=z['metrics'][control][k]
                    # All three model decisions exist wherever their benchmark is eligible.
                    if cnt!=cp.get('eligible',0):raise ValueError('paired denominator '+code+k+control)
                    net=cp.get('net_hits',0);ci=cp.get('date_cluster_ci')
                    paired.append({'赛事':c['name'],'代码':code,'窗口':window,'指标':ZH[j],'对照':label,'同场场数':cnt,
                                   '模型命中':m+net,'对照命中':m,'净增':net,'改对':cp.get('gained',0),'改错':cp.get('lost',0),
                                   '95%日期抽样区间':str(ci) if ci is not None else ''})
            row['四项全过']=bool(expected==n and all(row[zh+'完整分母达标'] for zh in ZH))
            row['首选初选方法']=r['policy']['first'];row['首选相似场方法']=locks['policy']['first']
            row['输入行数']=source['n']
            base.append(row)
            file=folder/('neighbor-'+window+'.jsonl')
            phase={}
            for g in lines(file):
                x=phase.setdefault(g['stage'],[0,0,0]);x[0]+=1
                score='-'.join(map(str,g['actual']));pred=g['forecast']['candidate']
                x[1]+=int(score==pred['primary']);x[2]+=int(score in pred['top3'])
            phases.extend({'赛事':c['name'],'代码':code,'窗口':window,'阶段':s,'90分钟场次':a,'首选命中':b,'三选命中':d} for s,(a,b,d) in phase.items())
    return base,paired,phases


def future(root,name):
    out=root/'issued';index=read(out/'receipts.json');rows=[]
    other=root/'market-priority';alt=read(other/'receipts.json')['matches'] if other.exists() else {}
    for mid,receipt in index['matches'].items():
        rec=read(out/receipt['file']);f=rec['fixture'];p=rec['payload'];pred=p['forecasts']['neighbor']
        from datetime import datetime
        from zoneinfo import ZoneInfo
        ko=datetime.fromisoformat(f['kickoff_at']).astimezone(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M')
        extra=read(other/alt[mid]['file'])['payload'] if mid in alt else None
        option=extra['forecasts']['market_priority'] if extra else None
        rows.append({'北京时间':ko,'赛事':name[f['cohort']],'代码':f['cohort'],'阶段':f['stage'],'主场':p['home_name'],'客场':p['away_name'],
              '首选':pred['primary'],'备选一':pred['top3'][1],'备选二':pred['top3'][2],'胜平负':{'home':'主胜','away':'客胜','draw':'平'}[pred['wdl']],
              '真实盘线':p['line'],'大小方向':{'over':'大','under':'小',None:''}[pred['total_side']],
              '赔率依据':p['market_mode'],'盘口对照首选':option['primary'] if option else None,'盘口对照三选':'、'.join(option['top3']) if option else None,'盘口对照来源':extra['score_source'] if extra else None,'结算':'待赛','比赛ID':mid,'冻结SHA256':rec['record_sha256']})
    return sorted(rows,key=lambda x:(x['北京时间'],x['代码'],x['比赛ID']))


def excel(path,tables):
    import xlsxwriter
    book=xlsxwriter.Workbook(path)
    header=book.add_format({'bg_color':'#1B435D','font_color':'white','bold':True,'text_wrap':True,'valign':'vcenter'})
    pct=book.add_format({'num_format':'0.0%'})
    for name,rows in tables:
        sheet=book.add_worksheet(name);keys=list(rows[0]);sheet.freeze_panes(1,2);sheet.set_row(0,32)
        for j,key in enumerate(keys):
            sheet.write(0,j,key,header)
            width=min(43,max(11,len(key)*2+1,max(len(str(r[key])) for r in rows[:300])+1 if j<6 else 12))
            sheet.set_column(j,j,width)
        for i,r in enumerate(rows,1):
            for j,k in enumerate(keys):
                val=r[k]
                if val is None:continue
                if k.endswith('命中率'):sheet.write_number(i,j,val,pct)
                else:sheet.write(i,j,val)
        sheet.autofilter(0,0,len(rows),len(keys)-1)
    book.close()


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--scope',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--xlsx',action='store_true');a=p.parse_args()
    a.out.mkdir(exist_ok=True,parents=True);scope=read(a.scope)
    rows,paired,phases=collect(a.root,scope)
    slate=future(a.root,{c['code']:c['name'] for c in scope['competitions']})
    for filename,values in [('scorecard',rows),('paired',paired),('stages',phases),('forward',slate)]:save_csv(a.out/(filename+'.csv'),values)
    if a.xlsx:excel(a.out/'20项赛事模型验证.xlsx',[('独立留出',[r for r in rows if r['窗口']=='evaluation']),('近期复验',[r for r in rows if r['窗口']=='recent']),('同场对照',paired),('阶段比分',phases),('赛前冻结',slate)])
    (a.out/'scorecard.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':main()
