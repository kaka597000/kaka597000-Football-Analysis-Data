HELLO BOSS

# 日职联 2026-11-28/29 赛前采集证据

采集时间为北京时间 2026-11-26 13:12–13:13。此为只读独立 staging；没有写入数据仓库、修改冻结或访问中国体彩/镜像。API优先流程与赔率证据技能已遵循。原登记：`/workspace/football-r24-data/workspace-updates/20261125-j1-stage-windows/registration/99791e2c015d1473-v000001.json`。

## 登记赛程复核

两份 ESPN 日历响应（11月28日、29日各一份）合计返回10场；与登记的10个 ESPN event ID、主客队 ID及开球时间完全一致。事件类型为 `Japanese J1 League, Regular Season`，赛前状态 `STATUS_SCHEDULED`。北京时间：

| 日期 | 比赛 | ESPN ID | 北京时间 |
|---|---|---|---|
| 11月28日 | 京都不死鸟 vs 大阪樱花 | 401877537 | 13:00 |
| 11月28日 | 清水心跳 vs 浦和红钻 | 401877539 | 13:00 |
| 11月28日 | 鹿岛鹿角 vs 冈山绿雉 | 401877542 | 14:00 |
| 11月28日 | 神户胜利船 vs 千叶市原 | 401877516 | 14:00 |
| 11月28日 | 柏太阳神 vs 广岛三箭 | 401877525 | 15:00 |
| 11月29日 | 水户蜀葵 vs 长崎航海 | 401877541 | 13:00 |
| 11月29日 | 横滨水手 vs FC东京 | 401877523 | 13:00 |
| 11月29日 | 川崎前锋 vs 大阪钢巴 | 401877540 | 14:00 |
| 11月29日 | 名古屋鲸八 vs 福冈黄蜂 | 401877538 | 14:00 |
| 11月29日 | 町田泽维亚 vs 东京绿茵 | 401877524 | 15:00 |

全队名与 ID、开球 UTC/BJT、状态和阶段字段另存于 `per-match-findings.json` / `calendar-fixtures.json`。北京时间由原始 UTC 加8小时换算。

## 当前公开盘口（仅观察值）

10份赛事 summary 都包含 DraftKings 机构对象与三项 1X2、实际总球线和大/小两侧水位；同时字段 `hasOdds=false`，对象自身无 `lastUpdated`。可以展示 API 返回的观察值，但报价真实时钟缺失，无法验证报价距离登记截点是否在1小时内，因此没有任何一场满足严格时点线。表内 1X2 顺序为主/平/客，大小球价格顺序为大/小；数字为美式赔率。`开盘`和`close`是ESPN对象内的两个字段名，没有独立采样时间，不能称为已核验的开盘/收盘变化。ESPN `spread` 字段未当作亚洲让球。

| 北京时间 | 比赛 ID | 主队 vs 客队（球队 ID） | 机构 | 1X2 主/平/客 | 总球线 | 大/小 | 报价时钟 |
|---|---|---|---|---|---:|---|---|
| 11-28T14:00 | 401877516 | Vissel Kobe (7477) vs JEF United Ichihara-Chiba (7111) | DraftKings | -165 / +310 / +390 | 2.5 | -130 / -110 | 无 |
| 11-29T13:00 | 401877523 | Yokohama F. Marinos (7116) vs FC Tokyo (3384) | DraftKings | +370 / +290 / -150 | 2.5 | -135 / -105 | 无 |
| 11-29T15:00 | 401877524 | Machida Zelvia (22167) vs Tokyo Verdy 1969 (3393) | DraftKings | -190 / +280 / +500 | 2.5 | +110 / -160 | 无 |
| 11-28T15:00 | 401877525 | Kashiwa Reysol (7476) vs Sanfrecce Hiroshima (7114) | DraftKings | +195 / +265 / +120 | 2.5 | -160 / +115 | 无 |
| 11-28T13:00 | 401877537 | Kyoto Sanga (21361) vs Cerezo Osaka (7109) | DraftKings | +145 / +240 / +170 | 2.5 | -140 / +100 | 无 |
| 11-29T14:00 | 401877538 | Nagoya Grampus (7108) vs Avispa Fukuoka (7107) | DraftKings | -120 / +245 / +300 | 2.5 | -105 / -140 | 无 |
| 11-28T13:00 | 401877539 | Shimizu S-Pulse (7104) vs Urawa Red Diamonds (3385) | DraftKings | +295 / +255 / -115 | 2.5 | -115 / -125 | 无 |
| 11-29T14:00 | 401877540 | Kawasaki Frontale (7112) vs Gamba Osaka (7102) | DraftKings | -105 / +285 / +220 | 3.5 | +115 / -170 | 无 |
| 11-29T13:00 | 401877541 | Mito Hollyhock (131701) vs V-Varen Nagasaki (19001) | DraftKings | +180 / +225 / +150 | 2.5 | +100 / -140 | 无 |
| 11-28T14:00 | 401877542 | Kashima Antlers (7115) vs Fagiano Okayama (22522) | DraftKings | -125 / +265 / +330 | 2.5 | -115 / -120 | 无 |

## 首发与伤停

每场 `rosters` 只有主客队元数据，没有球员条目；本次响应不能确认已公布首发。summary未提供本场伤停/停赛列表或空列表，因此伤停状态未知。不得把缺列表解释成无人伤停。保留的 league news 不是逐队伤停证据。summary含球队近五场区块，但本任务使用的11月25日新增近况补充见下节。

## 本地已核验的 11月25日近况

复用了 `/workspace/r24-acceptance/review/results.json` 及对应原始赛果证据，无新网络请求。7场均在该review登记为 J1 regular、FT，按90分钟；记录中的 ESPN summary 与 FotMob 日期接口双源结果一致。可用于14支参赛队最近一场补充；其余6队没有11月25日这批记录：神户胜利船、京都不死鸟、柏太阳神、町田泽维亚、鹿岛鹿角、大阪钢巴。

| 主队（ESPN ID） | 客队（ESPN ID） | 90分钟赛果 | ESPN ID |
|---|---|---:|---|
| 福冈黄蜂 (espn:7107) | 横滨水手 (espn:7116) | 1-2 | espn:401877527 |
| 冈山绿雉 (espn:22522) | 清水心跳 (espn:7104) | 2-0 | espn:401877528 |
| 千叶市原 (espn:7111) | 名古屋鲸八 (espn:7108) | 1-2 | espn:401877529 |
| 水户蜀葵 (espn:131701) | 东京绿茵 (espn:3393) | 1-0 | espn:401877530 |
| 长崎航海 (espn:19001) | 川崎前锋 (espn:7112) | 1-2 | espn:401877545 |
| FC东京 (espn:3384) | 广岛三箭 (espn:7114) | 2-2 | espn:401877546 |
| 浦和红钻 (espn:3385) | 大阪樱花 (espn:7109) | 2-2 | espn:401877547 |

逐场证据时间、结果、双方ID、响应SHA-256及双源URL在 `prior-review-crosscheck.json`。

## 随后的第一组未来赛程

两份后续日历请求（12月5日、6日）返回8场 Regular Season，比20队联赛完整一轮预期少2场；结果未列出千叶市原和川崎前锋。故这批公开日历可报告所见的8场，但不能据此认证“随后第一轮完整赛程”。

| 北京时间 | ESPN ID | 主队 vs 客队（ESPN ID） |
|---|---|---|
| 12-05T13:00 | 401877513 | Tokyo Verdy 1969 (3393) vs Kyoto Sanga (21361) |
| 12-05T13:00 | 401877515 | Urawa Red Diamonds (3385) vs Nagoya Grampus (7108) |
| 12-05T14:00 | 401877520 | Cerezo Osaka (7109) vs Mito Hollyhock (131701) |
| 12-05T14:00 | 401877509 | V-Varen Nagasaki (19001) vs Shimizu S-Pulse (7104) |
| 12-06T13:00 | 401877510 | Sanfrecce Hiroshima (7114) vs Vissel Kobe (7477) |
| 12-06T14:00 | 401877511 | Gamba Osaka (7102) vs Yokohama F. Marinos (7116) |
| 12-06T15:00 | 401877521 | Kashiwa Reysol (7476) vs Avispa Fukuoka (7107) |
| 12-06T15:00 | 401877512 | Machida Zelvia (22167) vs Fagiano Okayama (22522) |

此前试用两天日期范围参数均HTTP400；未重试该错误形态，改为按日期的4次成功请求。有效日历请求间隔超过1秒。尝试总数因此为6（其中2个400），需在来源账中披露；The Odds API本次未请求，已拒绝/失败服务未重试。

## 归档与哈希

- `raw/summary/`：10份 ESPN 原始summary响应，单场请求，间隔超过1秒。
- `raw/calendar/`：4份成功日历原始响应；400参数错误只记录在 `calendar-manifest.json`，未取得响应正文。
- `summary-manifest.json`、`calendar-manifest.json`：URL、北京时间换算所据UTC抓取时刻、HTTP状态、响应字节数与响应SHA-256。
- `per-match-findings.json`：10场身份、价格/盘线、时钟/阵容缺项与来源指针。
- `prior-review-crosscheck.json`：本地已核验近况及原证据哈希。
- `calendar-fixtures.json`：18条（目标10场+后续8场）日历比赛摘要。
- `sha256-manifest.json`：本轮独立目录中所有归档文件的SHA-256（不自哈希）。

此目录不修改任何仓库、冻结、模型或数据源注册表。