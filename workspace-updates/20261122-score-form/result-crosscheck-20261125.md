# 11 月 22 日英超两场研究首冻的赛后核对

2026 年 11 月 25 日，以赛前已登记的两场英超研究样本逐场核对 90 分钟终场。登记覆盖 2/2，两场都有原 Test、全比分候选、仅在 Test 前三内重排的候选。原登记、原生双模型冻结和候选冻结均通过原源码的完整性检查，各自首次记录时间早于开球。下面三列采用各自原先保存的顺序，第一项为首选。

| 赛事（ESPN ID） | 终场 | 原 Test | 全比分候选 | 仅重排 Test 前三 |
|---|---|---|---|---|
| 赫尔城–布莱顿（401879234） | 2–0 | 1–1、1–2、0–1 | 1–1、0–1、1–2 | 1–1、1–2、0–1 |
| 利物浦–曼联（401878755） | 4–0 | 1–1、2–1、1–2 | 1–1、2–1、1–2 | 1–1、2–1、1–2 |

三种方案各自第一比分 0/2，三比分任一命中 0/2。相对 Test，两种候选各改对 0、改错 0，首选与三比分集合改变场数都为 0。全比分候选在赫尔城一场互换了两个备选的次序。两场数据只能交代这批已锁定研究的结果。实际展示三比分与正式结算各自需要独立证据。

两场终场来自俱乐部正式赛报和比赛中心。这里附录的是赛后人工来源核对。赛前记录中的 `PENDING` 描述原登记时点；原始字节和当时状态保留。[布莱顿比赛中心](https://www.brightonandhovealbion.com/match-centre-stats?gameId=2645300) · [英超赛报](https://www.premierleague.com/en/news/4764879/mcburnies-late-double-stuns-brighton-as-hull-end-winless-run) · [利物浦赛报](https://www.liverpoolfc.com/news/match-report-liverpool-4-0-manchester-united-premier-league)

原始依据为数据提交 `f7143128733067d568167d726f850a182de165c0` 下的 `forward-receipts.json`（SHA-256 `e03936b41780865b7c2af1986488d11619dd472721211bed09774968a4441f98`）和同目录归档中的 `forward/plan.json`、`forward/pairs/`、`forward/registered/`。可用固定源码 `1196b57c1369193e38b9b0c5c05addaf7d270094` 和同目录 `verify_evidence.py --source SOURCE_CHECKOUT` 离线重放；再按原回执的 `reference_three`、`candidate_three`、`within_reference_three` 与上表的终场分别比较首项和三项集合。
