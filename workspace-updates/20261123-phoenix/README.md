# 凤凰足球数据入库 · 2026-11-23

五大联赛正式接口返回 31,781 条比赛记录。按赛事、赛季和主客队核准身份后，统一赛事数据库的回测视图包含 31,706 场已完赛比赛。英超与西甲共有 4,110 场能以相同球队、相同主客方向和开球时间直接对应到凤凰的两个数据流，4,110 场的终场比分全部一致。

| 来源 | 实际入库 | 可复用字段 |
| --- | ---: | --- |
| 正式赛程与赛果 | 英超 2,750、西甲 7,737、德甲 6,237、意甲 7,700、法甲 7,357 条 | 比赛与供应商事件 ID、赛季、主客队、带偏移开球时间、状态、可核准的完赛比分 |
| 授权逐场盘口 | 408 场综合响应，另有其中 4 场的定点快照 | 各机构胜平负、亚洲让球开收盘、部分交易所、部分报价轨迹和定点报价。各场字段和时间覆盖不同 |
| 公开历史赔率 | 英超、西甲共 4,180 场，3,322 场有价，10 个机构代码，325,864 个胜平负变价节点 | 主、平、客报价和供应商显示时间。英超覆盖至 2026-05-24，西甲至 2025-05-26 |
| 近七日公开复盘 | 13 项赛事，105 场，684 条供应商预测记录及 105 份逐场明细 | 供应商预测、开收盘胜平负、让球与大小球盘线、赛后归因。按供应商复盘比赛 ID 单独保存 |

全部 20 项纳入覆盖核对。凤凰目录可精确映射 19 项。正式比赛接口仅授权五大联赛，其余 14 个具名代码均实测返回 HTTP 403 `no_subscription`。世界杯正赛没有对应目录代码。未具名的 `other` 分类未并入赛事回测。另有日职联、韩 K、澳超、美职联、荷甲、巴甲、挪超和瑞典超能在近七日公开复盘中核准。欧冠、欧联、欧协联、亚冠、欧国联、日联杯和世界杯在该窗口没有可核准的逐场记录。[逐赛事覆盖表](coverage.csv)

## 回测口径

- `phoenix_verified_backtest_games` 每场一行。证据集中保留了不同数据流的赛果、队名和盘口原文。38 场奥维耶多、34 场荷尔斯泰因基尔的名称差异有多个日期和对手佐证。公开历史库有 62 场缺少正式接口同场佐证，其中含需核对的队伍层级。
- `phoenix_trial_prematch_prices` 仅接受早于开球的供应商时间。使用固定提前量时，报价还须早于该决策时点。正式轨迹中有 616 个胜平负变价时间晚于开球，另 3 个等于开球，供应商却标为赛前。原始记录可查。公开库变价时间只显示月、日、时、分，重放按最接近开球的年份换算。该历史时钟无法证明当时已经收到报价。
- `phoenix_review_evidence` 保存供应商复盘。比赛键为 `review_match_id`，一场可以对应多条 `prediction_id`。其开收盘字段和赛后归因不能进入自有模型的前向成绩。该来源给出了大小球盘线，样本中大小球双边价格为 0。
- 胜平负历史市场基准按机构去除水位后等权平均，在同场比分证据可核准时取概率最高的方向。开球前 24 小时为 1,761/3,227（54.57%），前 1 小时为 1,798/3,270（54.98%）。两个时点的可用场次不同。[数据库核验明细](database-audit.json)

## 读取和恢复

统一库中的凤凰原表以 `phoenix_` 为前缀。此归档保留 4,214 份可复算的来源响应及续采清单。每份响应记录了来源 URL、采集时间和原始字节的 SHA-256。两个加密分片覆盖整套来源文件。恢复需要本次保存的原试用凭据，可通过环境变量提供。[归档索引](bundle.json) · [恢复核验](restore-verification.json)

使用 Python 3.11 或更高版本，并取源码提交 `54dc8796472efe20d2cb3dde4df35a63f3dc1628`。在本目录执行下列命令。将 `FOOTBALL_SOURCE` 指向 Football-Analysis 检出目录，`fenghuangtest` 由本地密钥配置注入。

```bash
python restore.py --verify-only
python -m pip install cryptography
python restore.py --root ./phoenix-captures --source "$FOOTBALL_SOURCE" --db ./phoenix-football.sqlite
python verify_report.py
```

恢复程序逐份检查响应哈希，重建 SQLite，并与本次统一库的 SQL 核验结果比较。回测可以直接从以下查询开始。

```sql
SELECT competition, COUNT(*) AS finished_games
FROM phoenix_verified_backtest_games
GROUP BY competition;

SELECT competition, fixture_id, bookmaker, market, phase, source_time, line, home, draw, away
FROM phoenix_trial_prematch_prices
WHERE seconds_to_kickoff >= 3600 AND market = 'odds_1x2';
```

## 续采

最后一次成功响应显示已用 500/500 次，当日余额 0。以 11 月 22 日末为截止，2,600 天试用历史窗口内已完赛且标记有价的 12,590 场取得了 408 场详情。截止次日实际采集时，又有 8 场结束。续采队列合计 12,193 场，包括 12,190 场已结束和 3 场待赛。供应商给出的本次试用截止时间为北京时间 2026-11-26 14:40。原始清单中的更早赛程也按来源保存，详情访问以实际授权历史窗为准。

核对待采数量可在恢复目录运行第一条。额度更新后第二条会按照原队列优先顺序读取授权比赛，单场写入 SQLite 并保存原始响应。成功过的比赛会自动跳过，达到响应头所示额度时结束。该操作需有效供应商凭据。

```bash
python "$FOOTBALL_SOURCE/runtime/database/phoenix_resume.py" --root ./phoenix-captures --db ./phoenix-football.sqlite --max-matches 0
python "$FOOTBALL_SOURCE/runtime/database/phoenix_resume.py" --root ./phoenix-captures --db ./phoenix-football.sqlite --max-matches 500
```

[凤凰官方文档](https://data.soccerdreamai.com/#/docs) · [公开赔率与复盘页](https://data.soccerdreamai.com/odds-archive) · [采集范围及计数](coverage-summary.json)
