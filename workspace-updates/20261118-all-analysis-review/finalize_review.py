"""Build the complete review and append actual review freezes, retaining all losses."""
import csv,hashlib,json,os,sys,subprocess
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
R=Path(__file__).parent;S=Path('/workspace/Football-Analysis-xg-research-20261117')
sys.path.insert(0,str(S/'runtime'))
from research.analysis_freeze import save,verify,aware
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(n,x):
 with (R/n).open('x') as f:json.dump(x,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
now=lambda:datetime.now(timezone.utc).isoformat()
m=read(R/'metrics.json');lock=read(R/'review-scope-lock.json');process={x['match_id']:x for x in read(R/'verified-process.json')};results={x['match_id']:x for x in read(R/'verified-results.json')};cross=read(R/'cross-source-audit.json');models=read(R/'model-rows.json');summaries=read(R/'model-summaries.json');state=read(R/'forward-state-receipt.json')
s=m['comprehensive_first']['summary'];assert (s['primary_hits'],s['wdl_hits'],s['population'])==(2,5,11)
assert s['total_settlements']=={'win':4,'half_win':1,'push':1,'half_loss':0,'loss':5}
assert cross['all_results_corroborated']==11 and state['settled']==18 and not state['pending']
assert sum(len(x['red_cards']) for x in process.values())==3 and sum(len(x['goals']) for x in process.values())==37
assert len([g for x in process.values() for g in x['goals'] if g['normalized']['detail']['own_goal']])==1
asset_index=read('/workspace/WCPP/reports/tonight-20261117-2100/retained-assets/index.json')
for a in asset_index['path_mapping']:assert sha(a['original_path'])==a['sha256']
for ref in lock['frozen_records']:assert sha(ref['original_path'])==ref['file_sha256'];verify(read(ref['archived_path']))
assert not subprocess.check_output(['git','-C',str(S),'status','--porcelain']).strip()
diagnoses={
 'fifa.friendly:401930880':'中国2-2巴林。2分钟、20分钟已0-2落后，首球为传中头球、第二球来自角球后续；37分钟追回一球，80分钟点球扳平。中国15射只有2正，巴林6射3正，控场/射门量不能证明防守零封。原1-0与小2.25都低估了巴林得分和早失球后的开放路径。没有红牌；两队已在20分钟达到2球，不能把4球完全归于末段点球。',
 'fifa.friendly:401916336':'日本1-2巴拉圭。日本17射5正、66.3%控球，巴拉圭5射4正；巴拉圭两球均来自角球后续，日本85分钟才追回一球。此前连续友谊赛获胜没有延续，10人首发变化的定性修订也没有正确识别定位球防守风险。首版2-1错、主胜错，但大2.5全赢；临场1-1仍错、主胜仍错，小2.75半输。没有真实球员影响权重或xG，不能把这次变化称为数值模型自动优化。',
 'fifa.friendly:401916335':'新加坡0-7巴西。巴西22射11正，新加坡10射1正，巴西31分钟已4-0、65分钟已6-0，74分钟新加坡球员Raoul Suhaimi乌龙使巴西获益到7-0。零封与客胜判断成立，巴西进球数低估两球、小5.25失败；即使不计最后乌龙也已超过5.25，不能把失误归咎于乌龙。旧/刷新友谊赛模型分别1-1/1-2，对强弱差压缩过大；市场让球/总球映射已明显更接近，但人工选择5球上限路径仍不成立。',
 'espn:401861189':'威尔士2-3葡萄牙。半场已2-2，70分钟形成最终2-3，葡萄牙74分钟内托第二黄退场。威尔士22射8正，葡萄牙11射6正；客胜命中，原1-2把双方各少估一球，小3.25全输。全部5球均发生在红牌前，红牌不能解释这次小球失败。全场射门含红牌后的比赛状态，不全部视为赛前实力差。',
 'espn:401861190':'乌克兰1-0格鲁吉亚。乌克兰第1分钟进球后保持比分；双方射门11-12、射正3-4。格鲁吉亚90分钟才第二黄退场，无法解释开场失球。原0-0与平局失败，小2.25全赢；第三国场地情景把固定刷新/xG的1-0改成0-0，本次改分减少一次命中。场地事实正确，但自动去掉全部主场效应并未获得这一场的效果支持。',
 'espn:401861191':'匈牙利1-1北爱尔兰。匈牙利35分钟领先，北爱65分钟扳平；射门17-8，但射正仅2-2。原1-0过度押注北爱零球；北爱此前五场零封描述的是其防守，不能推出其本场不进球。比分、主胜均未中，小2.0走盘。原Current的1-1命中，综合改成1-0丢掉该次命中。',
 'espn:401861192':'爱尔兰3-0科索沃。科索沃26分钟红牌，爱尔兰28、50分钟两次罚进点球，75分钟再进头球；28射12正对5射3正含长时间人数优势。主胜与客队零球成立，1-0及小2.0失败。早红牌和两点球显著改变比赛路径，但保留全量复盘，不剔除此场，也不把赛后多打一人的射门数量直接当成赛前攻击强度。',
 'espn:401861193':'以色列1-1奥地利。以色列3射2正先得分，奥地利21射6正扳平；原0-1和客胜均未中，小3.0全赢。客队创造量占优却不足以兑现零封客胜；第三国情景把原/xG参考的1-1改成0-1，本次又少一次命中。缺真实xG，不能仅凭射门数断言所有偏差都是终结运气。',
 'espn:401861194':'丹麦2-3挪威。丹麦14分钟已2-0，挪威37分钟追回一球，83分钟扳平（NFF官方记84分钟），补时点球制胜；射门7-22、射正4-7。原2-1、主胜、小3.25全部失败，挪威持续创造和丹麦领先后的风险被低估。最终点球发生前已2-2，小3.25已经落入全输，不能只归咎于绝杀。ESPN2-3与InferSports2-2冲突已由挪威足协官方2-3报道解决。',
 'espn:401861195':'波兰1-1瑞典。波兰16分钟领先，瑞典24分钟扳平；射门10-17、射正3-6。原1-1、平局、小3.25全部命中。瑞典虽已锁定第一，仍有明显机会产出，锁定排名本身不能代替实际比赛强度判断。',
 'espn:401861196':'波黑2-1罗马尼亚。罗马尼亚6分钟领先，波黑44分钟扳平、82分钟反超；双方均13射6正。原2-1与主胜命中，大2.75半赢。本次人工改分相对1-0/1-1研究参考增加一次命中，但不能用这一场抵消其他改错场次。'}
rows=m['comprehensive_first']['rows'];ordered=sorted(rows,key=lambda x:aware(next(f['kickoff_at'] for f in lock['fixtures'] if f['match_id']==x['match_id'])))
point_total=sum(sum(map(int,x['primary'].split('-'))) for x in rows);actual_total=sum(sum(map(int,x['actual'].split('-'))) for x in rows)
zero=[{'match_id':x['match_id'],'side':('home','away')[i],'hit':int(x['actual'].split('-')[i])==0} for x in rows for i,v in enumerate(map(int,x['primary'].split('-'))) if v==0]
quality={}
for level,arm in [('A','shotmap-75'),('B','expected-75')]:
 quality[level]={}
 for role in ('goals',arm):
  rs=[x for x in models if x['track'].startswith('nations-xg-comparison:') and x['league_level']==level and x['role']==role]
  quality[level][role]={'n':len(rs),'primary_hits':sum(x['primary_hit'] for x in rs),'wdl_hits':sum(x['wdl_hit'] for x in rs),**{k:float(np.mean([x['probability_diagnostics'][k] for x in rs])) for k in ('score_log_loss','wdl_brier_sum3')}}
write('diagnostic-summary.json',{'point_score_total':point_total,'actual_total':actual_total,'note':'Point-score sums are not sums of model expected goals.','zero_choices':zero,'zero_hits':sum(x['hit'] for x in zero),'xg_selected_quality':quality,'diagnoses':diagnoses})
decision={'decision':['KEEP_ACTIVE_PARAMETERS','RETAIN_ALL_FIRST_AND_REVISION_OUTCOMES','COMPLETE_EXISTING_FORWARD_PLANS','PRIORITIZE_MANUAL_OVERRIDE_AND_TAIL_RESEARCH'],'model_promoted':False,'parameters_changed':False,'new_training_run':False,'data_queue_completed':18,'xg_forward_completed':8,'all_13_xg_arms_evaluated':True,'basis':{'comprehensive_first':s,'manual_net_vs_locked_xg':m['manual_score_net']['nations-xg-reference-update:selected'],'xg_selected_quality':quality,'japan_revision':m['comprehensive_revisions']},'research_decisions':['本轮实际完成13个原锁定xG权重/字段方案的未来同场结算，三个命中项目均没有相对进球基线增益；不提高xG权重或宣称已优化成功。','人工改分优先研究零球与一球路径、第三国主场效应，以及比分/大小球各自选择。当前8场已是已观察诊断样本，后续改规则不能再把这8场称为未见验证。','日本10人换阵仍允许继续研究；进攻产出与防守/定位球风险分别评估，不能把大幅轮换自动等同小球或仅下调进攻。','强弱悬殊友谊赛的历史强度收缩和高比分尾部需要单独实验。巴西场刷新模型仍给新加坡约1.79、巴西约2.30模型均值；不因本场直接手工加2球。','继续保存原候选、刷新候选、xG和综合各自独立结果，下一次实际赛事分析仍按真实数据执行研究，不用本批失败阻断分析。'],'next_check':'下一次实际赛前分析先记录候选/配方与比较节点，后续用新开赛比赛检验；已结束18场和本次8场xG完整保留为首轮前向证据。'}
write('review-decision.json',decision)
cn={None:'未给方向','win':'全赢','half_win':'半赢','push':'走盘','half_loss':'半输','loss':'全输'}
hit=lambda x:'✓' if x else '×'
lines=['# 11月17日全部预测复盘｜北京时间2026年11月18日','','HELLO BOSS','','**11场全部完成核验：第一比分2/11（18.2%），胜平负5/11（45.5%）；大小球4全赢、1半赢、1走盘、5全输。严格全赢率4/10＝40.0%，走盘剔出该分母，半赢没有当作全赢。**','',
'范围为11月17日分析的中国、日本、新加坡三场友谊赛，以及11月18日03:45八场欧国联。11场全部有明确首版三项选择，覆盖率均100%；未剔除红牌、点球、乌龙或失败场次。日本临场版本单独评价，不替换首版。','',
'|比赛|原第一比分|90分钟赛果|比分|原胜平负|方向|原实际大小球|结算|','|---|---|---|---|---|---|---|---|']
for x in ordered:lines.append(f"|{x['name']}|{x['primary']}|{x['actual']}|{hit(x['primary_hit'])}|{x['wdl']}|{hit(x['wdl_hit'])}|{'大' if x['total_direction']=='over' else '小'}{x['total_line']:g}|{cn[x['total_settlement']]}|")
lines+=['','## 首版、临场修订与TOP3','','日本首版11:44：2-1／主胜／大2.5，实际1-2，比分错、方向错、大球全赢。21:04临场修订：1-1／主胜／小2.75，比分和方向仍错，小球半输。**这次修订没有改善比分，并把正确的大小球方向改错。** 两次真实冻结、盘口和评价分别保留。','','欧国联原TOP3：乌克兰0-0、匈牙利1-0、爱尔兰1-0，比分0/3，胜平负1/3，大小球1全赢、1走盘、1全输。友谊赛原研究TOP3就是中国、日本、新加坡三场，比分0/3、胜平负1/3，大小球1全赢、2全输。没有赛后更换名单或排序。','','## 本轮错误主要在哪里','',
f'综合点比分合计{point_total}球，实际{actual_total}球；7次单队零球选择仅3次正确。这是选分偏差诊断，不把点比分合计称为模型期望进球。原11场中9场选小：3全赢、1走盘、5全输；偏小判断本轮没有兑现。','',
'人工改分相对原Current、固定刷新Test、锁定xG参考均净少中1场：增加波黑2-1命中，却分别丢掉两个原基准正确比分。相对原Test净增0，相对独立候选净增1；这些基准不能拼成一个赛后最优模型。两场第三国xG场景从1-0/1-1变成0-0/0-1均未中，场地判断与预测效果必须分开验证。','',
'红牌、点球和乌龙按实际发生时间解释。爱尔兰26分钟红牌和两点球确实改变比赛路径；威尔士—葡萄牙的5球全在74分钟红牌之前；丹麦在最后点球之前已2-2；巴西在乌龙之前已6-0。后三场大小球失败不能归因于最后的特殊事件。','',
'所有11场本次ESPN过程均没有真实xG；射门与射正只能确认可见创造量，不能据此断言“全是运气”或补造机会质量。统计点球字段有三场冲突（中国、爱尔兰、挪威），复盘采用逐球事件、分段比分及球队身份核验，原始字段原样保存。','','## 逐场过程与判断','']
for x in ordered:lines.extend([f"### {x['name']}",'',diagnoses[x['match_id']],''])
lines+=['## 模型对照','','下面是本批8场欧国联的同场描述，A/B具体版本在JSON中分别统计；均为保留研究候选，不冒称活动模型。原Current/Test没有事前冻结大小球方向的记录不回填方向；16日原五轨计划与17日新报价参考分别结算。','','|保留研究轨|比分命中|胜平负命中|','|---|---:|---:|']
for tr,role,label in [('nations-paired-candidates','current','原Current'),('nations-paired-candidates','test','原Test'),('nations-fixed-reference-update','fixed_current','固定刷新Current'),('nations-fixed-reference-update','fixed_test','固定刷新Test'),('nations-fixed-reference-update','challenger','独立候选')]:
 ss=next(x['batch_descriptive'] for x in summaries if x['track']==tr and x['role']==role and x['revision']==1)
 lines.append(f"|{label}|{ss['primary_hits']}/{ss['primary_n']}|{ss['wdl_hits']}/{ss['wdl_n']}|")
lines+=['|锁定xG方案：A shotmap-75／B expected-75|3/8|4/8|','|综合第一推荐|2/8|4/8|','',
'xG首次前向验证已完成8/8：13个原锁定方案和纯进球基线均为比分3/8、胜平负4/8，按上午原盘口均为4全赢、1走盘、3全输。**这一批没有观察到加入xG后的命中增益。** 不能用晚间新盘的结算替代上午原盘，也没有从13个方案里赛后重选赢家。','',
'概率质量按级别分别看（越低越好）：A组2场纯进球/shotmap-75的比分log-loss为3.6042/3.5890，B组6场纯进球/expected-75为2.3183/2.3316；A略改善、B略退步。样本有限，不能称已证明最优权重。缺失xG的球队仍使用原先声明的进球回退。','',
'友谊赛三场：保留历史版、固定配方刷新版、让球/总球映射、1X2/总球映射的统计第一比分均0/3；原冻结只有概率而未选胜平负/大小球方向的参考，不在赛后补方向算命中。活动Current/Test三场仍为不可用，统计为覆盖0/3，不与研究轨混算。','',
'## 完整前向队列及累计记录','','11月16日预先锁定的18场五轨比较现已18/18结算，待结算0；这18场包含前一批10场，不属于本次11场的额外分母。完整表见repair-complete-forward-review.json；队列已用现有运行入口更新，未重新推理或发起API请求。','','|级别／独立样本|原Current|原Test|固定Current|固定Test|独立候选|','|---|---:|---:|---:|---:|---:|','|A／4场|0/4|0/4|0/4|0/4|0/4|','|B／8场|3/8|2/8|3/8|3/8|1/8|','|C／4场|0/4|0/4|0/4|0/4|1/4|','|D／2场|1/2|0/2|0/2|0/2|0/2|','',
'另已复核52场欧国联原Current/Test首次冻结，逐级/版本统计见cumulative-first-candidates-52.json；未混入后续修订，不用不同级别的最佳结果拼接提升。','','## 处理决定与可核验证据','',
'本次完成了真实赛果核验、全部原版本结算、13种xG方案未来比较、18场原计划闭环以及52场原模型累计复核。保留活动参数和研究工件；本次没有新训练或晋级。后续研究重点为人工零球/一球改分、第三国主场效应、强弱悬殊场次的尾部分布，以及阵容变化对进攻和防守的分别影响。新的规则以新的未来冻结样本检验；本次已观察比赛不重复冒称未见测试。','',
'ESPN11场均有明确FT和两个半场比分，37个进球事件与球员所属队/进球受益队逐一核对。InferSports10场吻合；丹麦备用源2-2与ESPN2-3冲突，由挪威足协官方2-3赛后报道解决，备源错误值仍保存，原因未作无依据推断。NFF/ESPN的扳平分钟84/83及补时分钟展示差异分源保留。','',
'官方丹麦赛果：[挪威足协赛后报道](https://www.fotball.no/landslag/norge-a-herrer/2026/disse-starter-mot-danmark2/)。逐场原始API URL、HTTP状态、真实采集时间及哈希见verified-results.json与采集目录。77条原始赛前记录和所有旧工件哈希保持。复盘、模型对照和处理决定追加冻结；不发布环境。']
report='\n'.join(lines)+'\n'
(R/'复盘报告.md').write_text(report)
with (R/'复盘展示.csv').open('x',newline='') as f:
 w=csv.writer(f,lineterminator='\n');w.writerow(['比赛','原第一比分','90分钟赛果','比分命中','原胜平负','方向命中','原大小球','结算','首版冻结ID'])
 for x in ordered:w.writerow([x['name'],x['primary'],x['actual'],x['primary_hit'],x['wdl'],x['wdl_hit'],('大' if x['total_direction']=='over' else '小')+str(x['total_line']),cn[x['total_settlement']],x['freeze_id']])
receipts=[]
for x in ordered:
 f=next(f for f in lock['fixtures'] if f['match_id']==x['match_id']);payload={'first_prematch_review':x,'separate_revisions':[v for v in m['comprehensive_revisions'] if v['match_id']==x['match_id']],'process':process[x['match_id']],'result':results[x['match_id']],'diagnosis':diagnoses[x['match_id']],'decision_ref':{'path':str(R/'review-decision.json'),'sha256':sha(R/'review-decision.json')},'original_forecasts_unchanged':True}
 receipts.append(save(payload,dict(f,cutoff_at=now()),stage='review',track='comprehensive-postmatch-review'))
shell={'match_id':'all-analysis-review-20261117','kickoff_at':max(f['kickoff_at'] for f in lock['fixtures']),'cutoff_at':now()}
receipts.append(save({'report':report,'metrics':m,'decision':decision,'source_conflicts':cross,'report_sha256':sha(R/'复盘报告.md')},shell,stage='review',track='all-analysis-review'))
for top in m['top3_batches']:
 receipts.append(save(top,dict(shell,match_id=top['batch_id'],cutoff_at=now()),stage='review',track='top3-postmatch-review'))
receipts.append(save(decision,dict(shell,cutoff_at=now()),stage='review',track='model-review-decision'))
(R/'review-freezes').mkdir()
for receipt in receipts:
 p=Path(receipt['path']);verify(read(p));(R/'review-freezes'/(receipt['freeze_id']+'.json')).write_bytes(p.read_bytes())
write('review-freeze-receipts.json',receipts)
verification={'status':'PASS','source_commit':subprocess.check_output(['git','-C',str(S),'rev-parse','HEAD'],text=True).strip(),'prior_prematch_freezes_verified':77,'model_and_choice_rows_settled':298,'canonical_model_review_groups':44,'goals_verified':37,'red_cards':3,'independently_corroborated_results':11,'old_assets_verified':len(asset_index['path_mapping']),'review_freezes':len(receipts),'forward_population_settled':18,'cumulative_unique_first_matches':52,'production_code_changed':False,'parameters_changed':False,'model_promotion':False}
write('verification.json',verification)
print(json.dumps({'verification':verification,'batch_review':receipts[11]},ensure_ascii=False))
