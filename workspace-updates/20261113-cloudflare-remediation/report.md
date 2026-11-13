# Cloudflare 官方例外机制核查（2026-11-13）

已找到官方支持的 Skip 机制，但它由 API 服务方的 Cloudflare 站点管理员配置。当前会话只有 API 消费者凭据，没有这两家服务方的 Cloudflare 管理绑定或工具，因此本轮没有创建规则，也没有执行“跳过后调用成功”的测试。两家的访问恢复尚未验证。

## 官方资料实际说明

| 场景 | 官方支持的处理 | 本项目当前能否执行 |
|---|---|---|
| 某些 WAF 规则、规则处理阶段或可选安全产品误拦合法请求 | 服务方定位命中项后，在其站点设置范围明确的 Skip 规则或适用例外 | 需要服务方的站点管理权限；当前会话无法执行 |
| Bot Fight Mode | 官方说明 WAF custom rules / Page Rules 的 Skip、Bypass、Allow 均不能为该产品建立例外 | 不应假定一个 Skip 规则能解除所有机器人防护 |
| 不知道命中了哪条规则 | 服务方查看 Security Events；结合已有请求时间、主机、路径、Ray ID 调查 | 当前没有服务方日志；事件可能采样，未查到事件不等于没有拦截 |

资料来自 [Cloudflare 官方 GitHub 文档仓库](https://github.com/cloudflare/cloudflare-docs/tree/dc696ce1fefd0b0b5eddcc28064f4434e9bdc202/src/content/docs)：

- [Skip 规则](https://github.com/cloudflare/cloudflare-docs/blob/dc696ce1fefd0b0b5eddcc28064f4434e9bdc202/src/content/docs/waf/custom-rules/skip/index.mdx)
- [Skip 选项](https://github.com/cloudflare/cloudflare-docs/blob/dc696ce1fefd0b0b5eddcc28064f4434e9bdc202/src/content/docs/waf/custom-rules/skip/options.mdx)
- [Bot Fight Mode](https://github.com/cloudflare/cloudflare-docs/blob/dc696ce1fefd0b0b5eddcc28064f4434e9bdc202/src/content/docs/bots/get-started/bot-fight-mode.mdx)
- [Security Events](https://github.com/cloudflare/cloudflare-docs/blob/dc696ce1fefd0b0b5eddcc28064f4434e9bdc202/src/content/docs/waf/analytics/security-events.mdx)

本次直接读取 Cloudflare 文档站返回 403 text/plain，已停止该主机访问；随后从其公开 GitHub 源码取得资料。这是公开文档核查，不是取得受阻 API 数据。精确摘录、抓取时间和失败请求均保留在 sources.json、search-log.json。Security Events 本文没有提供 Ray ID 专用查询步骤，不能把通用调查建议称为已验证的后台操作。

## 可执行的恢复与验收路径

1. 将[上一轮支持材料](https://github.com/kaka597000/kaka597000-Football-Analysis-Data/blob/3301a33f751b0cf935c7a83f2a1c10d3bc3d086f/workspace-updates/20261113-api-403-diagnosis/support-request-unsent.md)交给各自服务商，先确认实际命中规则和受影响范围。材料已备好，本会话未发送。
2. 由服务方对其确认的误拦设置最小范围的例外或支持的服务器调用配置。当前没有已确认的稳定出口 IP，不填写猜测的 IP/网段，不要求全面关闭防护。
3. 服务方确认修正后，以既有官方地址、鉴权头和正常 TLS 各做一次受保护端点调用：API-Football `/status`、TheRundown `/api/v2/markets`。成功标准为结构化 JSON、无应用错误、受保护端点确认凭据；若仍出现 401/403/429 或挑战，记录并停止。
4. 只有访问验收成功后，再核查目标赛事/赛季与真实盘口权限。目录接口成功不等于已有足球赛程、首发、xG 或有效盘口。

## 本轮实际状态

- 已完成：官方源码检索、Skip 适用范围核验、环境 revision 4 与目标域名绑定复核、恢复验收方案和证据保存。
- 未完成：服务方防火墙规则定位/修改、Skip 后真实 API 调用验收。缺口是服务方管理权限及拦截日志。
- 本轮业务 API 请求 **0 次**，Cloudflare 规则修改 **0 项**；没有把旧 403 当成本轮新测结果，没有宣称成功跳过。
- 最近真实 API 结果仍引用上一轮：API-Football 北京时间 10:08:05 为 Cloudflare HTML 403；TheRundown 10:02:43、10:02:48、10:02:53 三种控制均为同类 403。具体触发规则未知，密钥及套餐状态未判定。
- 源码、活动模型、比赛数据库及环境发布状态未改变；本报告是追加技术审计，不纳入赛事预测成绩。冻结回执见 delivery.json。
