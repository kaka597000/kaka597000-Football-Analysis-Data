import json,hashlib,csv,sys,math
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
B=Path(__file__).parent;W=Path('/workspace/WCPP');R=Path('/workspace/Football-Analysis')
read=lambda p:json.loads(Path(p).read_text())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
registry=read(W/'runtime/active-model.json');rows=[];details=[];evidence={}
names={'eng.1':'英超','eng.2':'英冠','esp.1':'西甲','ger.1':'德甲','ger.2':'德乙','ita.1':'意甲','fra.1':'法甲','ned.1':'荷甲','ned.2':'荷乙','por.1':'葡超','bra.1':'巴甲','swe.1':'瑞典超','nor.1':'挪超','ksa.1':'沙特联','usa.1':'美职联','mex.1:apertura:regular':'墨超Apertura常规赛','jpn.1':'日职联','jpn.2':'日职乙','kor.1':'韩K1','kor.2':'韩K2','aus.1':'澳超','uefa.champions:NEW_FORMAT:league_phase':'欧冠新制联赛阶段','afc.champions:ELITE:league_phase':'亚冠精英联赛阶段','afc.cup:CHAMPIONS_TWO:group_stage':'亚冠二级小组赛','eng.league_cup:single_leg':'英联杯单回合'}
def source(p):
 p=Path(p);evidence[str(p)]=sha(p);return str(p)
def clean(v):
 if isinstance(v,dict):return {k:clean(x) for k,x in v.items() if k not in ['history','records','predictions','test_prediction_records','matrix']}
 if isinstance(v,list):return [clean(x) for x in v]
 return v
def metric(m):return {k:m[k] for k in ['n','primary_hits','top1_hits','top1','exact_top1','wdl_hits','wdl_accuracy','score_log_loss','score_logloss','score_brier','wdl_brier','wdl_rps'] if k in m}
def add(p,cohort,role,scope,metrics=None,metric_source=None,note=''):
 p=Path(p);d=read(p);core=d.get('core',{});id=hashlib.sha256(str(p).encode()).hexdigest()[:12]
 row={'id':id,'赛事':names.get(cohort,cohort),'cohort':cohort,'角色':role,'状态':scope,'版本':d.get('version',d.get('schema')),'训练截止':d.get('train_end',core.get('fit_end',core.get('train_end'))),'训练行数':d.get('training_n',core.get('fit_n',core.get('training_n',len(d.get('history',[])) or None))),'评估口径':note,'参数':{},'效果':metrics or {},'工件':source(p),'SHA256':sha(p),'评估来源':source(metric_source) if metric_source else None}
 if 'anchor' in d:
  base=d['core']['baseline'];row['参数']={'实际执行':'anchor.baseline','baseline_weight':1.,'half_life_days':180,'smoothing_prior':8,'home_mean':base['home_mean'],'away_mean':base['away_mean'],'stored_inactive_weights':dict(zip(d['experts'],d['weights']))}
 elif 'alpha' in d:row['参数']={'alpha':d['alpha'],'DC_weight':1-d['alpha'],'ML_weight':d['alpha'],'config':d.get('config'),'long':{k:v for k,v in core.get('long',{}).items() if k in ['half_life_days','ridge','intercept','home_advantage','nuisance']}}
 elif 'configuration' in d:row['参数']={'configuration':d['configuration'],**{k:v for k,v in core.items() if k in ['half_life','ridge']},'rho':d.get('rho')}
 elif 'baseline' in core:row['参数']={k:v for k,v in core['baseline'].items() if k not in ['teams']};row['参数'].update(half_life_days=180,smoothing_prior=8)
 else:row['参数']={k:v for k,v in core.items() if k not in ['teams','attack','defence','coefficients']}
 details.append({'id':id,'source_path':str(p),'sha256':sha(p),'artifact_without_training_rows':clean(d),'note':'完整参数；booster_model是树结构，feature_importance不是固定预测权重。训练数据行不重复导出。'})
 rows.append(row);return row
for c,v in registry['models'].items():
 for role,key,hkey in [('current','artifact_path','artifact_sha256'),('test','test_artifact_path','test_artifact_sha256')]:
  p=Path(v[key]);assert sha(p)==v[hkey];d=read(p);m=None;rp=None;note='未找到该工件独立评分；不借其他版本成绩'
  if d.get('version') in ['WCPP-WEIGHTED-0.1','WCPP-ML-0.1','WCPP-ML-UCL-0.1']:
   rp=Path(v.get('test_report_path',str(Path(v['test_artifact_path']).with_name('report.json'))));report=read(rp);m=metric(report['test']['current_baseline' if role=='current' else 'ml']);note='历史开发时间留出/滚动拟合诊断；不是未来实绩，也不是最终全历史工件的未见测试'
  row=add(p,c,role,'当前默认研究路由；非正式晋级',m,rp,note)
  row['验收']=d.get('acceptance',{'formal_promotion':False})
  if v.get(role+'_engine')=='systematic_candidate' or (role=='test' and v.get('test_engine')=='systematic_candidate'):row['运行备注']='源码依赖须匹配；J1昨日实测失败，不能仅凭登记称可用'
# Latest systematic candidates, including additional leagues not in active registry.
for dirname in ['systematic-20261015-final-003','systematic-20261015-final-extended-003','systematic-20261015-final-repair-001','systematic-20261015-final-secondary-004']:
 for p in sorted((W/'models'/dirname).glob('*/artifact.json')):
  d=read(p)
  if dirname=='systematic-20261015-final-003' and d['cohort'] in ['ksa.1','usa.1']:continue
  selection=Path(d['selection_source']);scores=selection.parent/('audit-'+d['configuration']['name']+'-scores.json');m=None
  if scores.exists():
   z=read(scores);assert isinstance(z,list);valid=[x for x in z if x.get('N_scored')==1];m={'n':len(z),'scored':len(valid),'primary_hits':sum(x['top1'] for x in valid),'wdl_hits':sum(x['wdl_hit'] for x in valid),'score_log_loss':sum(x['score_log_loss'] for x in valid)/len(valid) if valid else None};m['top1']=m['primary_hits']/len(valid) if valid else None;m['wdl_accuracy']=m['wdl_hits']/len(valid) if valid else None
  add(p,d['cohort'],'systematic候选','独立候选；是否被当前入口引用以默认表为准',m,scores if scores.exists() else None,'评分属于此前audit拟合；最终全历史工件已含audit标签，不能移植为其未见成绩')
# ML0.2 retained candidate
reg=read(W/'runtime/training-candidates.json');source(W/'runtime/training-candidates.json')
for c,v in reg['models'].items():
 p=Path(v['artifact_path']);rp=p.with_name('report.json');report=read(rp);m=metric(report['test']['new']);add(p,c,'ML0.2候选','未启用候选',m,rp,'历史开发诊断；未通过替换')
# Nations
idxpath=Path('/workspace/nations-model-20261110/models/candidates.json');idx=read(idxpath);source(idxpath)
for level,roles in idx['routes'].items():
 for role,a in roles.items():
  p=Path(a['path']);report=p.with_name('diagnostic.json');r=read(report);m=metric(r['metrics'][role].get('metrics',{}));m['n']=r['metrics'][role].get('n');add(p,'欧国联'+level+'级联赛阶段',role,'独立候选；未通过验收',m,report,'2026历史留出；不是未来冻结实绩')
# Jcup transfer and old edition candidates
ip=Path('/workspace/jcup-qf-expansion-20261111/final-models/candidates.json');index=read(ip);source(ip)
for leg,v in index['routes'].items():
 for role,a in v['artifacts'].items():
  met=v['metrics'][role];m=metric(met.get('metrics',{}));m['n']=met.get('n');add(a['path'],'日联杯四分之一决赛第'+leg+'回合',role,'独立迁移研究候选；未验收',m,ip,'历史跨届留出；首回合另有2026-11-11未来冻结各0/4，不合并')
ip=Path('/workspace/jleague-cup-20261111/final-models/candidates.json');index=read(ip);source(ip)
for c,v in index['routes'].items():
 for role,a in v['artifacts'].items():
  p=Path(a['path']);rp=Path(v['report_path']);r=read(rp);m=metric(r['metrics'][role]['metrics']);m['n']=r['metrics'][role]['n'];add(p,c,role,'旧届阶段专用候选；不能套当前四分之一决赛',m,rp,'旧届留出诊断，不能转用于当前赛制')
# Existing cup artifacts absent from current recovered registry
for dirname,c in [('afc2-group-20261029-r2','afc.cup:CHAMPIONS_TWO:group_stage'),('efl-cup-20261029-r3','eng.league_cup:single_leg')]:
 for role in ['current','test']:
  add(W/'models'/dirname/(role+'-artifact.json'),c,role,'工件存在，当前默认注册表未登记',None,None,'旧文档有历史评分，但当前工件不可冒称默认已接入；见覆盖文档')
# Additional retained J2/K2 baselines
for c in ['jpn.2','kor.2']:
 add(W/'reports/japan-korea-20261010'/(c+'-artifact.json'),c,'current基线','工件存在，默认未登记',None,None,'未取得该工件独立评分')
# Four-league refresh, final candidates only; evidence separate
for c in ['eng.1','ita.1','swe.1']:
 for role in ['current','test']:
  p=Path('/workspace/refresh-20261110/europe-final')/c/'final'/(role+'-artifact.json');add(p,c,'11月10日刷新'+role,'全量刷新候选未启用',None,None,'已含留出标签；评价候选成绩另列，不能移植')
for role in ['current','test']:add(Path('/workspace/refresh-20261110/aus/result')/('final-'+role+'-artifact.json'),'aus.1','11月10日刷新'+role,'全量刷新候选未启用',None,None,'已含留出标签；评价候选成绩另列，不能移植')
source(W/'runtime/active-model.json');source(R/'runtime/prediction_engine.py');source(R/'runtime/v6/ml_model.py');source(R/'runtime/v2/model.py')
(B/'inventory.json').write_text(json.dumps({'observed_at':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),'registry_routes':len(registry['models']),'models':rows,'source_hashes':evidence},ensure_ascii=False,indent=2))
(B/'exact-parameters.json').write_text(json.dumps(details,ensure_ascii=False,indent=2))
print('models',len(rows),'registered',len(registry['models']))
for r in rows[:38]:
 m=r['效果'];p=r['参数'];print(r['赛事'],r['角色'],r['训练行数'],r['训练截止'],'Top1',m.get('primary_hits'),m.get('n'),'WDL',m.get('wdl_hits'),'alpha',p.get('alpha'),'mean',p.get('home_mean'),p.get('away_mean'))
