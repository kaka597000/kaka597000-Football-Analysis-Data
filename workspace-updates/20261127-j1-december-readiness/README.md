# 日职联 12 月赛前取证准备

已将本周末完整十场的 ESPN 与 InferSports 赛程逐场配对，核对赛事、主客顺序、别名、计划开球和提供方编号。20 支球队的两套 ID 覆盖 12 月每窗全部十场。12 月的场次及赛轮仍由原登记及 J.League 官方赛前明细核对，共 20/20 场。签发范围输入也以原登记的成年男子常规赛范围生成。[球队 ID](prepared/team-ids.json) · [范围输入](prepared/approved-scopes.json) · [原窗口](../20261126-j1-december-windows/README.md) · [官方赛前绑定](../20261127-j1-december-evidence/README.md)

| 原登记窗口 | 计划首场，北京时间 | 场次 | 具备两源球队 ID |
| --- | --- | ---: | ---: |
| 12 月 4–6 日，第 18 节 | 12 月 4 日 17:30 | 10 | 20/20 |
| 12 月 12–13 日，第 19 节 | 12 月 12 日 13:00 | 10 | 20/20 |

11 月 27 日 10:48 以 J1 联赛 ID 精确筛选两窗的首个比赛日，HTTP 200 且均无下一页。12 月 4 日接口返回 0 场，登记 1 场。12 月 12 日也返回 0 场，登记 3 场。两次查询只覆盖上述比赛日，官方登记仍为完整的两组十场。[12 月 4 日响应](captures/2026-12-04.json) · [12 月 12 日响应](captures/2026-12-12.json)

11 月 27 日 10:44 的横滨水手对 FC 东京对照有 21 条报价，6 家机构同时提供全场胜平负和大小球。响应标记为活跃，整份包的更新时间距采集约 38 分 29 秒，机构市场最新一行距采集约 83 分 26 秒。原一小时门槛复算严格报价 0/1。此样本仅用于核查后续取证链路。[原报价及时间](captures/odds.json) · [复算结果](prepared/readiness.json)

## 采集与首版回读

两窗各有十个待采集比赛输入。临近该窗的首次选分截止，在已有批次的 `evidence/` 下单独创建采集子目录。第二窗使用同一个原件根和自己的输出目录。复算程序使用保留的公开原件离线走完实际采集代码的两个子目录，检查原件从共用目录可重新读取。[第一窗输入](prepared/market-fixtures-dec04_06.json) · [第二窗输入](prepared/market-fixtures-dec12_13.json)

```bash
bundle=workspace-updates/20261127-j1-december-readiness
python /path/to/Football-Analysis/scripts/capture_public_club_markets.py \
  --fixtures "$bundle/prepared/market-fixtures-dec04_06.json" \
  --team-ids "$bundle/prepared/team-ids.json" \
  --archive-root "$j1_batch/evidence" \
  --out "$j1_batch/evidence/market-dec04_06"
```

周末原正文及 29 个文件的 GitHub 公开回读已独立复算。聊天首次送达仍待原渠道回执。12 月每个窗口在实际发布前承诺完整正文与有序冻结版本；正式复盘需要授权房间、作者、服务消息 ID、完整原文和各比赛槽的原始首次送达事件，并核对实际开球及 90 分钟结果。当前没有可调用的独立聊天原始事件读取器。[周末公开回读](../20261126-r26-j1-first-stage/public-archive/verified.json) · [原首次展示结算](https://github.com/kaka597000/Football-Analysis/blob/968fe42592a6b9ce4019c00e04c97b8dccb3323d/docs/standalone-display-settlement.md)

每窗仍按原协议验收完整十场首次比分与胜平负、至少八场严格实盘及至少七场非走盘，以及同场市场与精选三场首选全中。此处为赛前输入和证据状态。两次本地离线复算逐字节一致。[复算程序](verify.py) · [固定源码](https://github.com/kaka597000/Football-Analysis/commit/b47a99e72ade13bf03f75046c18f8f30175597da) · [校验清单](SHA256SUMS)
