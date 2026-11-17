# WCPP 研究状态

2026-11-17 北京时间08:32：[昨晚10场欧国联复盘](workspace-updates/20261117-nations-review-0833/复盘报告.md)已冻结。综合第一比分0/7（3待定），胜平负8/10，实际大小球5全输、1半输、1走盘（3观望）；原TOP3比分0/3、方向3/3。现有18场五轨计划已结10场、余8场待赛，研究候选保持inactive；[结果、完整冻结链及恢复清单](workspace-updates/20261117-nations-review-0833/README.md)。

2026-11-16 北京时间20:43：[今晚至明晨10场欧国联赛前报告](workspace-updates/20261116-nations-prematch-2044/欧国联赛前分析.md)已冻结，含独立新旧候选、综合判断、研究TOP3及真实盘口。唯一比分7场、3场资格缺口待定；证据与冻结链见[本轮归档](workspace-updates/20261116-nations-prematch-2044/README.md)。

2026-11-10 用户明确接受本数据仓库公开，并授权同步赛事数据、冻结复盘与审计材料；旧文档中的私有强制要求由此覆盖。密钥仍仅使用环境或仓库 Secrets，不写入数据或日志。最新增量备份见 `workspace-updates/20261110-review-and-audit/`。

源码：kaka597000/Football-Analysis，固定到workflow内完整commit。
每日北京时间02:17、08:17、14:17、20:17采集，10:37检查候选训练。
ESPN 采集仍是公开接口，每job最多5分钟，主采集90秒、100请求。
K联赛 kor.1 不走 ESPN：5Dollar `2270596712` 优先，失败再用 API-Football `219`，同一天四次。说明见 config/kor1-source-routing.md。该路最多再发6个带密钥请求，密钥是仓库 Secret `WCPP_5DOLLAR_API_KEY` 和 `WCPP_API_FOOTBALL_KEY`。
seed为追溯历史种子，不是完整数据库备份。候选不自动晋级。kor.1 新采集写入 `kor1/`，不进入训练表。
停止：禁用本仓库unattended.yml。无需本地电脑或长期运行聊天。


最新新环境恢复入口：[NEW-ENVIRONMENT.md](NEW-ENVIRONMENT.md)。请优先读取最终增量版；旧完整快照仍保持原样，勿遗漏后续增量。

2026-11-16 密钥核验：手动工作流 `api-secret-validation.yml` 使用仓库已有的 `BSD`、`FOOTBALLDATA`、`INFER`、`OPENFOOT`、`THEODDSAPI`、`WCPP_5DOLLAR_API_KEY` 和 `WCPP_API_FOOTBALL_KEY`，分别映射到对应提供方的程序环境变量。无需连接器拥有 Secrets 读取权限。定时盘口任务优先读取 `THEODDSAPI`，兼容旧名称 `WCPP_ODDS_API_KEY` / `THE_ODDS`。

核验结果追加到 `api-probes/<run-id>-<attempt>/`，保留每次鉴权、请求状态、记录数量及可验证盘口证据。接口调用成功、有效赛事返回、盘口通过身份及时间校验分开报告；不代表所有赛事均覆盖或历史前向样本已补齐。每提供方有限请求，无自动重试，401/403/429 后停止该提供方；INFER 最多抽测一场独立核实身份的未来比赛。此任务不触发训练、活动模型切换或预测冻结。

本轮实际结果：[7 个密钥云端实测及盘口加载验收](api-probes/43863271589-1/README.zh-CN.md)。6 个成功取得数据，API-Football 返回业务鉴权拒绝；The Odds API 10 场 / 287 组、INFER 抽测 1 场 / 2 组合法报价。
