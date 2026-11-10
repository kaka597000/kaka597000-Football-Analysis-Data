# TheRundown 接口可用性与数据范围探查

探查时间：2026-11-10，北京时间（UTC+8）。仅做小规模只读检查；1 次 authenticated 请求（预算上限 10），未改仓库代码、配置或绑定。密钥仅从环境变量 `therundown` 读取，并只按官方文档要求放在 `X-TheRundown-Key` 请求头中；没有写入产物或日志，也没有放进 URL。目录里保留官方公开文档快照及安全调用记录；未保留认证头。

## 官方地址、认证与低成本端点

公开官方文档现可从 [docs.therundown.io/llms.txt](https://docs.therundown.io/llms.txt) 访问（HTTP 200）。官方 Quickstart 和 Authentication 明确生产 API host 为 `https://therundown.io`，推荐路径前缀 `/api/v2`，使用 `X-TheRundown-Key` header。Query-key 仅为旧集成兼容方式，文档明确不建议新集成使用。没有将密钥发往 RapidAPI 或其他未确认 host。

文档确认 `GET /api/v2/sports` 和 `/api/v2/affiliates` 是公开目录接口；因此它们即使成功也不能证明账户认证。用于验证受保护访问的低成本候选是 `GET /api/v1/sports/{sportID}/schedule`：文档说成功后每次消耗 0 data points，且响应可带使用窗口 headers。我们按 EPL `sportID=11`、`limit=5`、`from=2026-11-10`、`include=teams` 做了 1 次认证调用，另对完全相同 endpoint/参数做 1 次无 key 对照。

## 实际调用结果

认证调用的安全记录见 [authenticated-schedule.json](authenticated-schedule.json)，无 key 对照见 [unauthenticated-schedule-comparison.json](unauthenticated-schedule-comparison.json)。

- 认证调用：HTTP **403**，`text/html; charset=UTF-8`，4,834 bytes，响应 SHA-256 `464dd31ae43daa8dba7813467841eaa20a2741823c1f2fbe6aab3c0cde377444`；响应标题/正文摘要为 Cloudflare “Attention Required / Sorry, you have been blocked”，header 有 `x-at-upstream-error: true`。没有收到 JSON API 错误、业务响应或额度 headers。
- 无 key 对照：HTTP **403**，同样是 Cloudflare HTML、4,834 bytes，SHA-256 `fa04a11104c582e503990b4b4c4b7004c66318d9ae360b297ee1b1e4066930db`。

这组结果表明当前网络路径上的 Cloudflare 阻断了对 `therundown.io` API 路径的访问；它没有到达可识别的 API 鉴权层。因此**本次不能判定 key 有效或无效，也没有验证账户套餐、球队赛事或赔率权限**。按采集规则收到 403 后停止该服务后续认证调用，没有换认证方法或重试。早先对官网 `/api` 与 `/api/documentation` 的 403 已由公开 docs 子域发现所解决；网页首页受阻不代表官方文档不存在。

## 文档所列数据能力（不是本 key 实测权限）

官方 `reference/sports.md` 列出这些足球 sport IDs：MLS `10`、EPL `11`、Ligue 1 `12`、Bundesliga `13`、La Liga `14`、Serie A `15`、UEFA Champions League `16`、UEFA Euro `17`、FIFA `18`、J-League `19`、Liga MX `34`。文档特别说明欧联比赛当前归入 `17`；目录中的 `33` 标注为没有赛事，建议查 `17`。这些是文档目录和说明，不是本 key 的实测覆盖结果。

官方 schema 支持赛程/事件记录、球队、开球时间、赛事状态和比分；赔率结构含 market、participant、line、book/affiliate 与 price。文档列出的足球相关核心市场：Moneyline `1`、Spread/handicap `2`、Total (Over/Under) `3`。足球三项胜平负由 Moneyline `1` 内三个 participants（主/和/客）表达；不要把 `563` 当足球胜平负，它是文档标注的 NHL regulation three-way market。`2` 在文档里称 spread/handicap，本次没有验证具体亚洲盘线值、四分之一盘或结算规则。Total `3` 是大小球类别。具体比赛和机构是否有报价需查该日期的市场与赛事响应。

赔率价格对象文档含价格、line value、affiliate ID 和 `updated_at`；`updated_at` 是报价更新时间，查询时间不能代替它。文档还列出按事件/日期查询 opening、closing snapshots 与历史价格；Free 文档限制为 7 天事件窗口且历史赔率需 Starter 或更高。Free 延迟赛前数据标为 5 分钟，WebSocket 和 live game state 标为 Ultra 或更高。以上均为官方计划说明，具体账户套餐/额度未从本 key 响应确认。

EPL coverage matrix 文档对多数列出的 sportsbook 标为覆盖，包括 Bet105、BetCRIS、BetMGM、BetOnline、BookMaker、Bovada、Circa、DraftKings、FanDuel、HardRock、Heritage、Intertops、LowVig、Matchbook、Pinnacle、SportsBetting、theScore Bet、Unibet、YouWager、Kalshi、Novig、Polymarket、Polymarket US、ProphetX；Caesars 显示 `Review`。矩阵也提示赛事、市场、来源及套餐会影响实际可用性。`/api/v2/affiliates` 是文档指定的动态 source health/ID 查询，但该目录对本 key 未调用。

赔率事件响应的数据点文档计算为每个赛事 2 点（event + score），另加返回的每个 sportsbook 价格 1 点；V1 schedule 成功时为 0 点。Free 文档限额是 20,000 点/UTC日及 200,000 点/UTC月。小样本赔率请求可明确筛选市场、单一 `affiliate_ids`、`main_line=true`，但本次403后没有进行该请求，也没有可报告的实际报价。

已查看的官方文档没有在此次范围确认 xG、伤停、真实首发或投注资金流字段；本次不将其描述为不存在，只标为未确认。

## 文件与来源

[官方文档快照和 SHA 记录](docs-download-log.json)；完整 Markdown 快照位于 [docs](docs/)。其中包括 llms 索引、Quickstart、Authentication、Rate Limits、足球目录、市场/机构、EPL coverage matrix、V2 赛事市场接口和 V1 schedule 接口。实际 API 响应正文未保存为原始 HTML，只保留安全错误摘要、响应长度与 SHA。`environment-readiness.json` 为主代理已放入的文件，保留原样。
