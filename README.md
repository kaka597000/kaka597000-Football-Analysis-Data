# WCPP 研究状态

2026-11-10 用户明确接受本数据仓库公开，并授权同步赛事数据、冻结复盘与审计材料；旧文档中的私有强制要求由此覆盖。密钥仍仅使用环境或仓库 Secrets，不写入数据或日志。最新增量备份见 `workspace-updates/20261110-review-and-audit/`。

源码：kaka597000/Football-Analysis，固定到workflow内完整commit。
每日北京时间02:17、08:17、14:17、20:17采集，10:37检查候选训练。
ESPN 采集仍是公开接口，每job最多5分钟，主采集90秒、100请求。
K联赛 kor.1 不走 ESPN：5Dollar `2270596712` 优先，失败再用 API-Football `219`，同一天四次。说明见 config/kor1-source-routing.md。该路最多再发6个带密钥请求，密钥是仓库 Secret `WCPP_5DOLLAR_API_KEY` 和 `WCPP_API_FOOTBALL_KEY`。
seed为追溯历史种子，不是完整数据库备份。候选不自动晋级。kor.1 新采集写入 `kor1/`，不进入训练表。
停止：禁用本仓库unattended.yml。无需本地电脑或长期运行聊天。


最新新环境恢复入口：[NEW-ENVIRONMENT.md](NEW-ENVIRONMENT.md)。请优先读取最终增量版；旧完整快照仍保持原样，勿遗漏后续增量。
