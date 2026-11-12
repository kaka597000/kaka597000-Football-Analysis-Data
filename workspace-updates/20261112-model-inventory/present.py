import json,hashlib,math,csv
from pathlib import Path
from openpyxl import Workbook,load_workbook
from openpyxl.styles import Font,PatternFill,Alignment
B=Path(__file__).parent;D=json.loads((B/'inventory.json').read_text());rows=D['models'];details=json.loads((B/'exact-parameters.json').read_text());rd={r['id']:r for r in rows}
# Keep same artifact scores available by reference, explicitly as earlier audit fits.
for r in rows[:38]:
 if r['角色']=='test' and r['cohort'] in ['jpn.1','kor.1']:
  x=next(x for x in rows if x['cohort']==r['cohort'] and x['角色']=='systematic候选');r['效果']=x['效果'];r['评估来源']=x['评估来源'];r['评估口径']=x['评估口径']
# No percentage weight is implied by tree gain.
gains=[];flat=[]
def walk(v,path,ident):
 if isinstance(v,dict):
  for k,x in v.items():walk(x,path+'.'+str(k),ident)
 elif isinstance(v,list):
  for i,x in enumerate(v):walk(x,f'{path}[{i}]',ident)
 elif isinstance(v,(int,float)) and not isinstance(v,bool):flat.append([ident,rd[ident]['赛事'],rd[ident]['角色'],path,v])
for d in details:
 a=d['artifact_without_training_rows'];ident=d['id']
 for k in ['core','config','configuration','weights','alpha','rho','context_coefficients','model']:
  if k in a:walk(a[k],k,ident)
 fg=a.get('feature_importance_gain',{})
 if isinstance(fg,dict):
  s=sum(fg.values())
  for k,v in fg.items():gains.append([ident,rd[ident]['赛事'],rd[ident]['角色'],k,v,v/s if s else None,'训练增益占比；不是固定概率/因果权重'])
# Auxiliary upset tracks, separate from score predictors, no unpickle.
shadow=[]
for regname in ['upset-classifier.json','upset-candidates.json']:
 p=Path('/workspace/WCPP/runtime')/regname;reg=json.loads(p.read_text());D['source_hashes'][str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
 for c,v in reg['models'].items():
  rp=Path(v['report_path']);r=json.loads(rp.read_text());t=r.get('test',r.get('diagnostic_test',{}));market=r['market_baseline'];ap=Path(v['artifact_path']);assert hashlib.sha256(ap.read_bytes()).hexdigest()==v['artifact_sha256']
  row={'cohort':c,'version':reg['version'],'status':reg['status'],'n':t.get('n'),'loss_brier':t.get('loss_brier'),'market_loss_brier':market.get('loss_brier'),'loss_auc':t.get('loss_auc'),'selected':r.get('selected',{'C':r.get('selected_C')}),'acceptance':r['acceptance_gate_passed'],'artifact':str(ap),'sha256':v['artifact_sha256'],'report':str(rp),'parameters':None}
  if ap.suffix=='.json':
   a=json.loads(ap.read_text());row['parameters']={k:a[k] for k in ['features','config','model','alert_threshold'] if k in a}
  else:row['parameters_note']='二进制工件未反序列化；仅报告登记选择参数，不能称已导出全部树权重'
  shadow.append(row);D['source_hashes'][str(rp)]=hashlib.sha256(rp.read_bytes()).hexdigest()
(B/'auxiliary-upset.json').write_text(json.dumps(shadow,ensure_ascii=False,indent=2));D['auxiliary_models']=len(shadow);D['unique_primary_artifacts']=len({r['工件'] for r in rows});(B/'inventory.json').write_text(json.dumps(D,ensure_ascii=False,indent=2))
# Tables
fmt=lambda v:'—' if v is None else str(v)
def score(r):
 m=r['效果'];n=m.get('n');hits=m.get('primary_hits',m.get('top1_hits'));p=m.get('top1',m.get('exact_top1'))
 if n is not None and hits is None and p is not None:hits=round(n*p)
 return f'{hits}/{n}（{100*p:.2f}%）' if n and hits is not None and p is not None else (f'{hits}/{n}' if n and hits is not None else '未取得对应独立评分')
def wdl(r):
 m=r['效果'];n=m.get('n');p=m.get('wdl_accuracy');h=m.get('wdl_hits');return f'{h if h is not None else round(n*p)}/{n}（{p:.1%}）' if p is not None and n else '—'
def table(headers,rr):return '| '+' | '.join(headers)+' |\n|'+ '|'.join(['---']*len(headers))+'|\n'+'\n'.join('| '+' | '.join(str(c).replace('|','/') for c in r)+' |' for r in rr)+'\n'
intro='''# 全赛事模型效果与权重核对表

核查日期：2026年11月12日，北京时间。以当前环境实际默认注册表、工件和可定位的评估报告为准。本轮只盘点、提取和复算已有指标，没有训练、改参数、晋级或发布新预测。

当前默认注册表为WCPP-DUAL-4，共19个赛事队列、38个模型引用，工件SHA256均与登记一致。本表共101项主要模型/角色引用（含同工件不同用途引用），另外单列18项冷门辅助分类器。全部是研究体系，不代表70%比分或80%方向目标已验证。没有把拟合内准确率当预测效果；下表大多是历史开发留出、滚动诊断，必须按各自分母阅读，不跨版本求平均。

**配置差异：** 2026-10-29文档记载WCPP-DUAL-5的21条路由，但本次实际默认文件只有19条；亚冠二级和英联杯工件在，当前默认登记缺失。没有自动覆盖注册表。本轮检查工件完整性不等于逐队列完成实时预测；J1最近实测test因源码依赖不匹配拒绝，欧国联8工件今日重载通过。工件自身active字段与外部路由可能不同，以默认表与实际调用分别判定。

## 默认当前/test模型

下列15项可取得同一报告中的current_baseline与ml对照；训练行数是全历史工件行数，评估分母是此前时间分割的评价样本，二者不可混称。

'''
active=rows[:38];pairs=[active[i:i+2] for i in range(0,38,2)]
text=intro+table(['赛事','全历史行数','训练截止','当前Top1','test Top1','当前胜平负','test胜平负','test α'],[[a['赛事'],a['训练行数'],a['训练截止'],score(a),score(b),wdl(a),wdl(b),b['参数'].get('alpha','见专用配置')] for a,b in pairs])
text+='''
多数默认当前模型执行anchor.baseline，基准100%，五专家融合0%；训练样本按180天半衰期衰减，球队攻防采用8倍联赛均值平滑。不是五模块都在影响当前预测。test的α是**比分概率矩阵混合权重**：P=(1−α)P_DC+αP_ML。不是主客进球率相加，也不是“伤停占比”。ML分支仍以DC进球率为基准，并由树模型做限幅的对数进球率修正。

LightGBM标准默认配方：70轮、学习率0.03、7叶、每叶最少25行、L2=5、对数进球率残差限幅±0.4。某联赛alpha=1只表示使用全部ML修正矩阵，不能说原始攻防基础被移除。完整树、各队攻防系数和参数见exact-parameters.json；逐数值参数可在Excel筛选。

## 默认基线及存储的融合候选权重

下面融合权重属于已训练但当前默认入口未采用的旧融合候选。顺序是基线、365天实力、180天实力、DC365、双变量365；总和为100%。联赛主/客均值属于已拟合基线参数，乘上双方球队攻防系数后才是具体比赛进球率。

'''
text+=table(['赛事','主/客基准均值','基线%','实力365%','实力180%','DC365%','双变量365%','当前实际'],[[a['赛事'],f"{a['参数']['home_mean']:.4f}/{a['参数']['away_mean']:.4f}",*[f'{v*100:.2f}' for v in a['参数']['stored_inactive_weights'].values()],'仅基线100%'] for a,b in pairs if 'stored_inactive_weights' in a['参数']])
text+='''
## 系统化候选：各联赛固定配置及历史audit效果

这些行属于单独实验，不取代上表。同一J1/K1工件虽被当前研究路由引用，仍不能等同正式验收。最终工件用全历史重拟合；下表成绩来自此前audit拟合，不宣称最终工件自身有未见测试成绩。alpha=0表示没有树修正；process表示历史射门/射正等过程组，不代表伤停、战意已经训练。

'''
sysrows=[r for r in rows if r['角色']=='systematic候选'];text+=table(['赛事','拟合行数','截止','半衰期/天','ridge','特征组','α','audit Top1','audit胜平负'],[[r['赛事'],r['训练行数'],r['训练截止'],r['参数']['configuration']['half_life'],r['参数']['configuration']['ridge'],r['参数']['configuration']['group'],r['参数']['configuration']['alpha'],score(r),wdl(r)] for r in sysrows])
text+='''
## 欧国联、日联杯及专用杯赛

欧国联current是独立Poisson截距+主场参数；test是球队攻防Poisson，半衰期730天、ridge=8。两模型独立输出，没有current/test融合百分比。下列截距和主场系数均处于log进球率尺度，不是概率百分比。

'''
nr=[r for r in rows if r['赛事'].startswith('欧国联')];text+=table(['等级/角色','拟合行数/截止','历史Top1','历史胜平负','截距','主场系数'],[[r['赛事']+'/'+r['角色'],str(r['训练行数'])+'/'+r['训练截止'],score(r),wdl(r),f"{r['参数']['intercept']:.6f}",f"{r['参数']['home_advantage']:.6f}"] for r in nr])
jr=[r for r in rows if r['赛事'].startswith('日联杯')];text+='\n'+table(['阶段/角色','训练截止','训练行数','历史Top1','历史胜平负'],[[r['赛事']+'/'+r['角色'],r['训练截止'],r['训练行数'],score(r),wdl(r)] for r in jr])
text+='''
日联杯四分之一决赛每回合仅12场拟合，历史留出每侧4场；11月11日首回合真实冻结current/test各0/4，和历史留出分开。current有截距/主场/场地未知指示项，test另加球队攻防；球队ridge=20，前三项惩罚系数为0.001/1/1，不使用日期衰减；进球率裁剪0.08–8。首回合所有训练场地未知，主场项未获得有效信息；第二回合总比分虽存入数据，尚未训练其数值系数。2023小组赛、2025首轮候选只能用于其原阶段，完整记录另在Excel。

其他专用模型：澳超current常数均值1.602779/1.315283；test采用Poisson365/ridge20/rho0，不启用booster。旧V1固定起点压力测试487场为current48/487、test43/487，跨多年状态滞后；这不是当前DATAFIX工件的未见成绩。亚冠精英current为常数、test为球队Poisson，具体常数与系数在参数页；未找到与当前工件一一匹配的独立效果报告，不编准确率。亚冠二级旧文档记载留出7/50与8/50，英联杯11/80与11/80，两者当前默认缺路由，文档成绩不填为本次已独立复算结果。

## 最近刷新与前瞻效果

11月10日四联赛时间留出：英超29场current旧→刷新5→5、test4→4；意甲35场3?（准确为current2→3、test2→2）；瑞典超26场current3→4、test3→3；澳超12场两侧均2→2。欧洲三联赛方向表现没有同步改善，没有稳定增益证明；最终全量工件已包含留出标签，不能把评价工件成绩直接移植给最终工件。此批不是未来冻结实绩，也不替换活动参数。

ML0.2和其他候选逐项参数见Excel及JSON，未因更大训练量自动晋级。当前表不是全项目未来冻结累计命中率报表；除日联杯本批明确引用外，不将零散复盘拼成当前工件的实盘表现。

## 权重解释与缺项

- 泊松球队攻防系数不是加起来100%的模块占比；截距、主场和攻防系数共同决定log进球率。数组型coefficients保留原始顺序及teams映射，须结合对应design函数读取；详细JSON提供全部值。
- 树模型没有每个特征固定一个“百分比权重”。Excel特征增益页是训练分裂增益及归一化占比，不能解释为因果影响、当前一场贡献或人工信心。
- 实际盘口、伤停、首发、战意、完整体能多数仍为证据审查层，不能编成20%/15%等固定权重。某些历史过程/xG独立候选的状态和特征值必须按其工件读取；不能据模型框架列了xG就说默认模型已经训练xG。
- 冷门0.1/0.2辅助分类器共18项独立列出Brier、AUC及市场基线，不混入比分Top1。0.2二进制工件本轮没有反序列化，仅列登记参数并给工件哈希，未声称导出全部树参数。
- 没有合格真实盘口的历史报告，固定2.5诊断不作为大小球实盘准确率。未取得评分写缺失，不写0%。

## 来源及复现

inventory.json含每行工件、评估来源、SHA256与状态；exact-parameters.json含主要工件全部参数（不重复训练行）；auxiliary-upset.json含辅助分类器指标。audit.py从原始登记和报告生成清单，present.py制作表格。101项是用途引用，含重复路径，不能当101套不同模型；唯一工件数量见inventory.json。旧备份、失败试训和早期被替代工件不作为“目前采用”重复列入。未更改旧冻结、模型和注册表。
'''
text=text.replace('意甲35场3?（准确为current2→3、test2→2）','意甲35场current2→3、test2→2')
(B/'模型效果与权重.md').write_text(text)
wb=Workbook();wb.remove(wb.active)
def sheet(name,heads,data):
 s=wb.create_sheet(name);s.append(heads)
 for row in data:s.append([json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for v in row])
 s.freeze_panes='A2';s.auto_filter.ref=s.dimensions
 for c in s[1]:c.font=Font(bold=True,color='FFFFFF');c.fill=PatternFill('solid',fgColor='16324F')
 for col in s.columns:
  letter=col[0].column_letter;s.column_dimensions[letter].width=min(65,max(12,max(len(str(c.value or '')) for c in list(col)[:80])+2))
 return s
sheet('说明',['事项','说明'],[['时间',D['observed_at']],['口径','历史开发/留出和未来实绩分开；效果不属于最终全历史工件未见测试'],['路由','实际19条，旧文档21条，亚冠二级/英联杯未在当前默认登记'],['原始参数','exact-parameters.json；树结构不能伪装成固定特征百分比'],['条目',f"101项主要引用，{D['unique_primary_artifacts']}个唯一主要工件，18项辅助分类器"]])
sheet('默认模型',['赛事','角色','版本','状态','训练行数','截止','Top1','胜平负','参数','评估口径','工件','评估来源'],[[r[k] for k in ['赛事','角色','版本','状态','训练行数','训练截止']]+[score(r),wdl(r),r['参数'],r['评估口径'],r['工件'],r['评估来源']] for r in active])
sheet('全部主要模型',['ID','赛事','角色','版本','状态','训练行数','截止','Top1','胜平负','效果原字段','参数摘要','口径','工件','SHA256','评分来源'],[[r['id']]+[r[k] for k in ['赛事','角色','版本','状态','训练行数','训练截止']]+[score(r),wdl(r),r['效果'],r['参数'],r['评估口径'],r['工件'],r['SHA256'],r['评估来源']] for r in rows])
sheet('具体数值参数',['ID','赛事','角色','原始字段路径','数值'],flat)
sheet('树特征增益',['ID','赛事','角色','特征','gain','gain占比','解释'],gains)
sheet('冷门辅助',['赛事','版本','状态','评估n','loss Brier','市场Brier','AUC','登记选择参数','通过','工件'],[[r[k] for k in ['cohort','version','status','n','loss_brier','market_loss_brier','loss_auc','selected','acceptance','artifact']] for r in shadow])
sheet('来源哈希',['文件','SHA256'],list(D['source_hashes'].items()))
file=B/'全赛事模型效果与权重.xlsx';wb.save(file);check=load_workbook(file,read_only=True);assert check['全部主要模型'].max_row==102;assert check['默认模型'].max_row==39
print(json.dumps({'main_references':len(rows),'unique_artifacts':D['unique_primary_artifacts'],'auxiliary':len(shadow),'numeric_parameters':len(flat),'gain_rows':len(gains),'xlsx_validated':True},ensure_ascii=False))
