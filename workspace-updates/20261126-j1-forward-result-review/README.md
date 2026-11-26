# 日职联赛果结算和实盘来源核查

窗口原登记中的赛段写为 `Japanese J1 League`，结果库用 `regular`。复盘逐场核验原始 ESPN 日职联常规赛类型和 90 分钟终场。用 11 月 25 日原始响应复算，七场均获有效赛果。当时可证的独立首次展示回执为 0/7。[已核赛果](verification.json) · [原窗口](../20261125-j1-stage-windows/README.md)

R28 复盘从项目正常的结果状态目录读取，经同一源赛果核验结算锁定首选、三选和精选席。签发后的本次检查保留十场待赛，三条统计轨各三席待赛。[R28 原登记](../20261126-r28-j1-process-forward/README.md)

BSD 官方文档公布 `bookmaker_slug`，机构目录确认 `pinnacle`。用现有 BSD 权限查询鹿岛–冈山已核验赛事 212344，于北京时间 11 月 26 日 14:39 返回 HTTP 403，代码为 `bookmakers_not_entitled`，响应注明具名机构报价需要 Football Unlimited。免费聚合参考另有原始证据。12 月正式验收仍需要带来源报价时钟的同机构盘口。[官方文档摘录](bsd/schema-excerpt.json) · [请求与原始 403](bsd/request-audit.json) · [聚合证据](../20261126-j1-market-clock-review/README.md)

从数据仓库根目录运行 `python -B workspace-updates/20261126-j1-forward-result-review/verify.py`，将 `PYTHONPATH` 指向固定源码的 `runtime`。脚本重放原日期、注册回执和原始响应，核查同一赛果及精选待赛人数，再核查具名机构探针。[固定源码](https://github.com/kaka597000/Football-Analysis/commit/71ba85c405c825d3fff10894de6b7dcf2eb3e5e3) · [校验清单](SHA256SUMS)
