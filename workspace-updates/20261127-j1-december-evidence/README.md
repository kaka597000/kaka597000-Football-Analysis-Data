# 日职联 12 月两窗的开球与报价证据

北京时间 11 月 27 日 09:39:00，官方赛前身份绑定冻结为 `97517288244f1498-v000001`。20 场与原登记逐场核对了 ESPN 比赛、J.League 官方详情、主客俱乐部 ID、赛轮和计划开球。两窗各十场，12 月 4–6 日是第 18 节，12 月 12–13 日是第 19 节。原件由 19 次正常官网请求和一份保留原始接收时点的旧页面组成。[原窗口登记](../20261126-j1-december-windows/README.md) · [官方原件](official/captures.json) · [绑定冻结](kickoff-packet.json)

第一窗的十份官方赛前页显示单数字日期，例如 `2026/12/4 (金)`。解析器现可核对该格式，日期、星期和结构化开球时间仍逐项验证。正式复盘入口读回两窗的 20 份赛前原件，当前实际开球和完赛核实各为 0/20。[逐窗复算](verified.json) · [实际开球证据口径](https://github.com/kaka597000/Football-Analysis/blob/cbac9d911548ce2c2051647f805d1c52e8af42b6/docs/j1-official-kickoff-proof.md)

## 可用盘口证据

五次公开请求均返回 HTTP 200。InferSports 的 12 月 4 日和 12 日两次日历查询尚未返回原登记的日职联比赛。近场对照鹿岛鹿角对冈山绿雉的身份可核，原件有 21 条报价和 6 家机构的同场胜平负与全场大小球。接口标记 `stale=true`，最新行级 `as_of` 距采集为 26,814 秒，约 7 小时 27 分钟。ESPN Core 的同场 DraftKings 胜平负和 2.5 球双方价格可核，机构报价时间缺项。该场严格市场覆盖为 0/1。[五份响应](market-probe/captures.json) · [逐项报价](market-probe/strict-quote-rows.json)

日职联可通过现有公开俱乐部盘口入口准备新的首版输入。每次按原赛历、两源球队 ID、同机构市场、原盘线、两侧大小球价格及各自报价时钟核查，并在正式复盘重读原件。此次真实陈旧样本在该入口复跑，严格报价仍缺。两窗各至少八场严格盘口与至少七场非走盘的覆盖要求由原协议核算。[采集入口和字段](https://github.com/kaka597000/Football-Analysis/blob/cbac9d911548ce2c2051647f805d1c52e8af42b6/docs/j1-infersports-market-evidence.md) · [原协议](../20261126-j1-december-windows/protocol.json)

固定源码和本次归档支持离线复算。[固定源码](https://github.com/kaka597000/Football-Analysis/commit/cbac9d911548ce2c2051647f805d1c52e8af42b6) · [校验清单](SHA256SUMS)

```bash
folder=workspace-updates/20261127-j1-december-evidence
(cd "$folder" && sha256sum -c SHA256SUMS)
PYTHONPATH=/path/to/Football-Analysis/runtime python -B "$folder/verify.py" > /tmp/j1-december-evidence.json
cmp "$folder/verified.json" /tmp/j1-december-evidence.json
```
