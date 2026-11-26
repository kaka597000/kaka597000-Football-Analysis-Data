# 日职联 11 月 28–29 日原比分公开留档

北京时间 11 月 26 日 13:34:16，GitHub 的原核验步骤已通过，服务端记录绑定数据提交 `aba9784cd0c0d47c13ba20fa7ffdd8f40de97618`。首场计划于北京时间 11 月 28 日 13:00 开球。北京时间 19:01 从同一不可变提交公开读取 29 份文件，均返回 HTTP 200，与原提交逐字节一致。文件涵盖原赛程、整批比分正文、十份双模型首冻、十份综合首冻及逐场比分表。[原 PR](https://github.com/kaka597000/kaka597000-Football-Analysis-Data/pull/68) · [原核验作业](https://github.com/kaka597000/kaka597000-Football-Analysis-Data/actions/runs/45762416257/job/139715257933) · [公开读取明细](captures.json)

十场的唯一首选、两个不同备选、胜平负和三席顺序逐场核对。三席按原顺序为名古屋对福冈、町田对东京绿茵、水户对长崎。J.League 官方成年 J1 第 17 节赛历在北京时间 19:03 取回，11 月 28 日、29 日各五场与原登记的主客及北京时间开球一致。横滨水手对 FC 东京的两个球队和开球也经独立官方详情核对。[原比分](../nov28_29/frozen-scorecard.csv) · [官方赛历](https://www.jleague.jp/j1/match/search-list/?startdate=2026-11-28&enddate=2026-11-29&period=custom&sort_desc=true) · [核验及逐场配对](verified.json)

原聊天首次送达凭据、实际开球和真实 90 分钟赛果仍按原协议核实，十场保持待赛。原盘线均属已观察报价，机构报价时点合格覆盖为 0/10。[原证据口径](https://github.com/kaka597000/Football-Analysis/blob/12de69b106ab8496ef10bc2211ebe03cabcbc9cb/docs/standalone-display-settlement.md) · [原盘口记录](../evidence/per-match-findings.json)

数据仓根目录运行 `python -B workspace-updates/20261126-r26-j1-first-stage/public-archive/verify.py`，令 `PYTHONPATH` 指向源码的 `runtime`，可比对已归档的原内容、赛历和 GitHub 服务时间。[文件校验](SHA256SUMS)
