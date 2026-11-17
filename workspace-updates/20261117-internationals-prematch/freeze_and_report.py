"""Freeze the full three-match research batch before publication, append-only."""
from datetime import datetime, timezone
import csv
import hashlib
import json
from pathlib import Path
import shutil
import sys
from zoneinfo import ZoneInfo

ROOT=Path(__file__).parent
SOURCE=Path('/workspace/Football-Analysis-xg-research-20261117')
sys.path.insert(0,str(SOURCE/'runtime'))
from research.analysis_freeze import save, verify
from research.score_distribution_audit import audit_prediction
from research.team_goal_analysis import summarize_prediction
from v2.model import aware


def read(p):return json.loads(Path(p).read_text())
def write(p,v):
    with Path(p).open('x') as f:json.dump(v,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
def bjt(t):return aware(t).astimezone(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')


DECISIONS={
'401930880':{
 'name':'中国—巴林','primary':'1-0','wdl':'主胜','total_direction':'小','total_line':2.25,
 'ranking':1,'priority_reason':'本土场地已获官方确认，近期主场比赛过程及实盘均可核；小比分路径较清楚，但巴林近期样本仅两场，胜平负优势不大。',
 'reason':'中国在肇庆连续比赛，上一场10分钟和19分钟已进两球；同地环境与边路传中、前插配合提供先取得一球的路径。面对巴林，仍以窄胜而非重复2-0为主：上场两队射门10比10，中国只有3次射正，不能把高转化率直接外推。',
 'counterevidence':'旧/刷新友谊赛研究模型最高格均为1-1。巴林刚3-1胜也门，存在定位球或反击扳平路径；中国近八场可见友谊赛有五场未进球，主胜并不稳。',
 'compared_scores':['1-0','1-1','0-0','2-0','2-1'],
 'zero_vs_one':{'away':{'reason':'巴林本次可见友谊赛仅两场；3球来自也门，不能视为对中国同等创造力。中国上场仅让对手2次射正；主场窄胜和市场小球路径支持将0球放在前。',
                         'counterevidence':'巴林最近已进3球，刷新历史模型给客队零球的概率不足三成；1-1是实质反例。没有取得真实xG，零封判断仅为研究选择。'}},
 'three_plus_path':'若巴林先失球后提高投入，2-1或2-2可发生；历史模型三球以上概率超过一半，需与实盘偏小信号并列保存。',
 'wdl_reason':'主场条件与本期同地备战、上场已验证的进球配合、两条实盘均指向中国略占优；不用1-0本身证明主胜。',
 'wdl_counter':'历史研究主胜约44%，并无过半优势；巴林样本稀疏，中国此前连续三场未进球且失9球。',
 'total_reason':'选择M8Bet小2.25：上场中国10射3正未形成持续大压制；巴林3球对手是也门，跨对手不能等量外推。实盘2.25小球1.80及同机构让球/总球映射总球均值约2.32支持低总球。2球为半赢，3球起全输。',
 'total_counter':'刷新历史分布三球以上53.3%，与实盘冲突；若早球迫使巴林追分，小球容易失败。此方向为人工研究，未改模型概率。',
 'risk':'1-1是主要反证；巴林近期友谊赛覆盖很薄。',
 'confidence':'中等偏低',
},
'401916336':{
 'name':'日本—巴拉圭','primary':'2-1','wdl':'主胜','total_direction':'大','total_line':2.5,
 'ranking':2,'priority_reason':'双方近期可见友谊赛覆盖较完整，比赛地和日本离队信息已核；日本优势来自近期对手表现与盘口，但中立场、镰田缺席和高转化回落使比分及大球仅为较弱倾向。',
 'reason':'日本最近三场可见友谊赛分别3-1乌拉圭、2-1委内瑞拉、3-2巴西，连续对较强对手取得至少两球。巴拉圭近六场友谊赛均进球，并刚4-1胜新加坡；日本最近三场也都有失球。因此综合选择日本窄胜且双方进球的2-1路径。',
 'counterevidence':'日本上场8射4正进3球，对方17射6正，终结效率不应照搬；镰田大地确认因俱乐部事务退出。比赛在新加坡，不给日本本土主场优势。旧/新历史模型众数都是1-1，同机构盘口映射众数是1-0，2-1是明确的人工覆盖，尚无已验证增益。',
 'compared_scores':['2-1','1-1','1-0','2-0','2-2'], 'zero_vs_one':{},
 'three_plus_path':'日本的边路/二线进攻连续三场产出两球以上，巴拉圭连续六场有进球；若互有一球后日本继续形成优势，2-1成立。若日本终结率回落或镰田离队影响连接，1-1、1-0更合理。',
 'wdl_reason':'日本近期对乌拉圭、委内瑞拉、巴西均赢球；移除主场优势后，真实1X2和日本-0.75盘口仍支持日本略到中度占优。',
 'wdl_counter':'巴拉圭近六场5胜1负，四场零封；历史强度研究两队接近，不能将市场偏好当必胜。',
 'total_reason':'选择M8Bet大2.5的弱倾向：日本最近三场均至少3球，巴拉圭连续六场进球，日本最近三场均失球；同机构盘口映射三球以上约52%。依据是双方进球路径和总球分布，而非2-1点比分。',
 'total_counter':'新旧历史研究小2.5概率分别53.4%和59.0%；巴拉圭近六场四次零封，日本高转化回落与镰田缺席均利于小球。大小球信号接近均衡，不包装成强推荐。',
 'risk':'1-1或1-0；镰田缺席与日本上场终结效率回落。',
 'confidence':'胜平负中等，比分及大球偏低',
},
'401916335':{
 'name':'新加坡—巴西','primary':'0-5','wdl':'客胜','total_direction':'小','total_line':5.25,
 'ranking':3,'priority_reason':'巴西胜负方向最清楚，但精确进球数、极高总球线及巴西人员状态不确定性最大；以比分为最高指标排序，故全场综合优先级列第三，不能把客胜把握转移给0-5。',
 'reason':'新加坡上场主场1-4负巴拉圭；巴西上场对日本17射6正，虽2-3输球仍有明确进攻产出。同机构新加坡+4.75与总球5.25映射到约0.27/5.28进球率，0-5为该市场参考最高单格。结合实力差和新加坡可能大部分时间防守，选择0-5，比较保留0-4、0-6和1-4。',
 'counterevidence':'新加坡上场能攻破巴拉圭球门；巴西近八场可见友谊赛七场失球，零封并非稳妥。巴西拉菲尼亚上场90+2分钟红牌，本场停赛/出场资格未获官方确认。旧/新历史模型1-1、1-2暴露了强弱差压缩问题，不能作为本场可信比分锚点。',
 'compared_scores':['0-5','0-4','0-6','1-4','1-5','1-2'],
 'zero_vs_one':{'home':{'reason':'同机构真实让球+4.75与总球5.25共同对应新加坡低进球机会；面对巴西持续控球压迫，前场回合可能较少。此市场参考新加坡零球约76%，支持先选0球。',
                         'counterevidence':'新加坡上场对巴拉圭进1球，巴西近八场可见友谊赛七场失球；1-4或1-5可由定位球、反击或大比分后注意力下降形成。上述76%仅是盘口映射假设，非综合校准概率。'}},
 'three_plus_path':'巴西对日本已17射6正，本期对弱队有持续创造机会基础；早球可打开空间到6球以上。反路径是大比分领先后比赛强度降低或换人，停在4至5球；这只是情景，不能宣称已知教练会收手。',
 'wdl_reason':'新加坡刚1-4负巴拉圭，巴西对更强日本仍创造17次射门；盘口有巨大实力分层，巴西客胜是本批最明确的胜负方向。',
 'wdl_counter':'友谊赛首发和换人未知；盘口客胜1.01不等于可靠的99%真实胜率，也不代表有价格价值。',
 'total_reason':'小5.25仅弱倾向：该盘口要求6球才使大球全赢；同机构让球/总球映射下，0至4球约35.0%、5球约17.1%、6球以上约47.9%。小球有约52.1%的正结算概率，但5球只半赢；高盘下稍倾向小，不因巴西强就自动追6球以上。',
 'total_counter':'若新加坡先丢球后持续失位，巴西可独力到6球；新加坡进球也会推高总球。市场大球1.81更热，这个小球选择不代表已有正期望收益；它与胜负方向的把握差距很大。',
 'risk':'0-4、0-6或新加坡进1球；拉菲尼亚资格及巴西轮换未知。',
 'confidence':'客胜方向高，比分与大小球低',
}}


def main():
    out=ROOT/'publication';out.mkdir(exist_ok=False)
    archive=out/'freezes';archive.mkdir()
    receipts=[]; published=[]
    market={p['fixture']['match_id'].split(':')[-1]:p for p in read(ROOT/'derived/market-handicap-reference.json')['fixtures']}
    availability={p['match_id']:p for p in read(ROOT/'derived/active-load-status.json')}
    for eid,d in DECISIONS.items():
        evidence=read(ROOT/f'derived/{eid}-research.json'); fixture=dict(evidence['fixture'])
        fixture['cutoff_at']=datetime.now(timezone.utc).isoformat()
        missing=availability[fixture['match_id']]
        pair={k:{'status':'ABSTAIN_UNSUPPORTED_FRIENDLY_ROUTE','reason':missing['actual_load_error'],'matrix':None,'primary':None} for k in ('current_model','test_model')}
        pair.update(active_route=False,formal_kpi_eligible=False)
        active_receipt=save(pair,fixture,stage='prematch',track='current-test-pair')
        research_receipt=save({'status':'INDEPENDENT_FRIENDLY_RESEARCH','active_route':False,'formal_kpi_eligible':False,
                              'history_references':evidence['research_models'],
                              'market_wdl_total_reference':evidence['market_implied_reference'],
                              'market_handicap_total_reference':market[eid]},fixture,stage='prematch',track='friendly-independent-research')
        fixture['cutoff_at']=datetime.now(timezone.utc).isoformat()
        models=dict(evidence['research_models'],market_wdl_total=evidence['market_implied_reference'],market_handicap_total=market[eid])
        audits={name:audit_prediction(p,d['primary']) for name,p in models.items()}
        team_goals={name:summarize_prediction(p) for name,p in models.items()}
        payload=dict(d,status='UNVALIDATED_MANUAL_RESEARCH',formal_kpi_eligible=False,
          decision_policy_version='WCPP-COMPREHENSIVE-REPAIR-1',override_validation_status='UNVALIDATED_MANUAL_RESEARCH',
          current_test_reference=active_receipt, independent_research_reference=research_receipt,
          current_test_status=missing,research_score_comparisons=audits,team_goal_analysis=team_goals,
          selection_evidence={'compared_scores':d['compared_scores'],'zero_vs_one':d['zero_vs_one'],
               'three_plus_path':d['three_plus_path'],'total_reason':d['total_reason'],
               'wdl_evidence':{'reason':d['wdl_reason'],'counterevidence':d['wdl_counter']},
               'total_evidence':{'reason':d['total_reason'],'counterevidence':d['total_counter']}},
          source_notes={'xg':'Checked current ESPN summaries; no verified xG/xGA. No shot count or modeled goal mean relabeled as xG.',
               'personnel':'JFA confirms Kamada withdrawal for club reasons; no confirmed starting XIs; Raphinha eligibility unresolved.',
               'markets':'InferSports real source timestamps. One snapshot per quote; no price movement or money-flow inference.'},
          evaluation='Evaluate all three first comprehensive records on 90-minute exact score, WDL and actual quarter-line settlement separately. Alternatives are not recommendations and do not earn hits.')
        receipt=save(payload,fixture,stage='prematch',track='comprehensive')
        for r in (active_receipt,research_receipt,receipt):
            record=verify(read(r['path']));assert record['record_sha256']==r['sha256']
            shutil.copy2(r['path'],archive/(r['freeze_id']+'.json'));receipts.append(r)
        published.append({'fixture':fixture,'payload':payload,'freeze':receipt})
    batch={'match_id':'international-friendlies-20261117-three-match-batch',
           'kickoff_at':min(p['fixture']['kickoff_at'] for p in published),'cutoff_at':datetime.now(timezone.utc).isoformat()}
    rank_payload={'top3':[], 'formal_kpi_eligible':False,
           'reason':'No active friendly Current/Test route; these are explicitly frozen independent research priorities, not qualified active-model TOP3.',
           'research_priorities':[{'rank':p['payload']['ranking'],'match_id':p['fixture']['match_id'],'primary':p['payload']['primary'],
                'wdl':p['payload']['wdl'],'total_line':p['payload']['total_line'],'total_direction':p['payload']['total_direction'],
                'reason':p['payload']['priority_reason'],'comprehensive_reference':p['freeze']} for p in published],
           'separate_wdl_priority':['Singapore-Brazil:Brazil','Japan-Paraguay:Japan','China-Bahrain:China'],
           'all_comprehensive_predictions_preserved':True}
    ranked=save(rank_payload,batch,stage='prematch',track='top3-selection')
    verify(read(ranked['path']));shutil.copy2(ranked['path'],archive/(ranked['freeze_id']+'.json'));receipts.append(ranked)
    write(out/'freeze-receipts.json',receipts)
    write(out/'published-analysis.json',published)
    with (out/'predictions.csv').open('x',newline='') as f:
        w=csv.writer(f);w.writerow(['研究排序','对阵','北京时间','唯一综合第一比分','胜平负','实际总球线','大小球','盘口机构','源报价北京时间','冻结ID'])
        for p in published:
            d=p['payload'];fxt=p['fixture'];w.writerow([d['ranking'],d['name'],bjt(fxt['kickoff_at']),d['primary'],d['wdl'],d['total_line'],d['total_direction'],'M8Bet / InferSports',bjt(fxt['total_quote']['as_of']),p['freeze']['freeze_id']])
    lines=['# 2026年11月17日三场国际友谊赛赛前研究', '',
      '三场均为成年男子国际友谊赛、90分钟口径。所有展示时间为北京时间；这是首发公布前的独立研究首版，已实际冻结。比分、胜平负、实际盘口大小球分别判断。', '',
      '| 研究排序 | 对阵 | 开球 | 综合第一比分 | 胜平负 | 实盘大小球 |', '|---|---|---|---|---|---|']
    for p in published:
        d=p['payload'];fxt=p['fixture'];lines.append(f"| {d['ranking']} | {d['name']} | {bjt(fxt['kickoff_at'])[11:16]} | **{d['primary']}** | {d['wdl']} | {d['total_direction']}{d['total_line']} |")
    lines += ['', '胜平负单项把握顺序：巴西胜 ＞ 日本胜 ＞ 中国胜。全场研究排序以精确比分路径和证据覆盖为先，不将巴西客胜把握转移给0-5或大小球。三场均不冒充活动模型正式TOP3。', '',
      '## 模型与真实数据', '',
      '活动注册表没有国际友谊赛路由，三场实际加载均返回范围不支持，Current/Test不可用记录也已冻结。保留原友谊赛研究工件，再按原配方用1,566场历史重拟合：新增4场截至11月14日的完赛记录、重新核查32场、修正8场中立场标志。半衰期365天、ridge=8、Dixon–Coles ρ=-0.0226963411、温度1.2355514728保持；不改活动参数，不宣称准确率提高。', '',
      '| 对阵 | 保留研究版（截至10/7）统计Top1 | 刷新研究版（截至11/14）统计Top1 | 同机构让球/总球映射Top1 | 综合第一比分 |', '|---|---|---|---|---|']
    for p in published:
        eid=p['fixture']['match_id'].split(':')[-1];refs=read(ROOT/f'derived/{eid}-research.json')['research_models']
        lines.append(f"| {p['payload']['name']} | {refs['retained']['primary']} | {refs['refreshed']['primary']} | {market[eid]['primary']} | **{p['payload']['primary']}** |")
    lines += ['', '盘口映射使用同机构真实让球和总球两项价格，按独立泊松反推；另保存1X2/总球映射以检查冲突。它们只是可复算市场参考，不是新训练模型，也未与历史概率硬设权重融合。巴西场1X2/总球映射给0-4，而让球/总球映射给0-5，说明极短1X2赔率与深让球分布存在差异。', '',
      '**真实xG/xGA此次仍未取得。** 已检查最新历史summary字段，射门和射正仅用于定性过程分析，不改称xG。没有确认首发；日本镰田大地退出已获JFA官方确认，理由是俱乐部事务，不是伤病。拉菲尼亚上场红牌已查到，本场停赛/资格未确认，不冒称确定缺阵。', '',
      '## 逐场判断与反证']
    for p in published:
        d=p['payload'];fxt=p['fixture'];eid=fxt['match_id'].split(':')[-1]
        lines += ['',f"### {d['name']}｜{bjt(fxt['kickoff_at'])[11:16]}", '',
          f"**第一比分 {d['primary']}；{d['wdl']}；{d['total_direction']}{d['total_line']}。** {d['reason']}", '',
          f"反证：{d['counterevidence']}", '',f"胜平负：{d['wdl_reason']} 反证：{d['wdl_counter']}", '',
          f"大小球：{d['total_reason']} 反证：{d['total_counter']}", '',
          f"候选比较（不算额外推荐）：{'、'.join(d['compared_scores'])}。{d['three_plus_path']}", '',
          f"主要风险：{d['risk']} 判断强度：{d['confidence']}。", '',
          f"M8Bet / InferSports真实总球报价：{d['total_line']}，大{fxt['total_quote']['prices']['over']} / 小{fxt['total_quote']['prices']['under']}；源报价 {bjt(fxt['total_quote']['as_of'])}，采集 {bjt(fxt['total_quote']['query_time'])}。仅有本次快照，不能推断升降水或资金流。", '',
          f"冻结：`{p['freeze']['freeze_id']}`，{bjt(p['freeze']['recorded_at'])}。"]
        if d['zero_vs_one']:
            for side,z in d['zero_vs_one'].items():lines += ['', f"零球/一球比较（{'主队' if side=='home' else '客队'}）：{z['reason']} 反证：{z['counterevidence']}"]
    lines += ['', '## 单队进球分布参考', '',
      '下表来自同机构让球/总球的市场映射，均值不是实测xG；中央80%区间只描述该分布，并非已验证的真实覆盖率。完整旧/新模型分布与比分格概率保存在JSON和冻结中。', '',
      '| 对阵/球队 | 均值 | 中央80%区间 | 0球 | 至少2球 | 至少3球 |', '|---|---:|---|---:|---:|---:|']
    for p in published:
        eid=p['fixture']['match_id'].split(':')[-1]
        for side in ('home','away'):
            t=market[eid]['team_goal_analysis'][side];iv=t['central_interval']
            lines.append(f"| {p['fixture'][side]} | {t['mean']:.2f} | {iv['lower']}–{iv['upper']} | {t['p0']:.1%} | {t['p_ge_2']:.1%} | {t['p_ge_3']:.1%} |")
    lines += ['', '## 来源与复盘约定', '',
      '- [中国足协：肇庆赛果及中国—巴林今日20:00赛程](https://www.thecfa.cn/zhongguozhidui/20261115/38436.html)',
      '- [日本足协2026赛程与新加坡场地](https://www.jfa.jp/samuraiblue/schedule_result/2026.html)',
      '- [日本足协：镰田大地退出公告](https://www.jfa.jp/samuraiblue/20261117/news/00037030/)',
      '- ESPN三场summary、六队2026友谊赛赛程与历史summary，以及InferSports三个真实赛事ID的报价原文、查询时间和SHA-256均随本包归档。日本21:10、新加坡18:00开球由ESPN与InferSports独立对齐；中国20:00另有CFA确认。',
      '- 中国上场进球10/19分钟、马来西亚红牌90分钟；日本上场制胜球90+1、巴西红牌90+2。红牌不能解释先前进球，未删除该两场。',
      '- 全部三场首次综合比分、WDL、实际盘口结算独立计分；研究模型及市场参考另轨计分，不赛后选最好的版本。小2.25遇2球半赢、小5.25遇5球半赢，半赢与全赢分开。未开赛/未完赛保持待结算。',
      '- 旧工件与活动模型不变；没有发布环境、没有自动晋级。比赛前如有新首发或盘口，仅能追加修订，不覆盖本版。', '']
    (out/'赛前分析.md').write_text('\n'.join(lines))
    print(json.dumps({'frozen_records':len(receipts),'comprehensive':[{'match':p['payload']['name'],'score':p['payload']['primary'],'freeze':p['freeze']['freeze_id'],'time':bjt(p['freeze']['recorded_at'])} for p in published],'report':str(out/'赛前分析.md')},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
