# 数据来源与盘口证据审计

本次审计只使用本地源码和最小合成响应，未访问业务 API、网页或网络，未读取真实密钥，未重新测试 Cloudflare。工作范围为 runtime/data_sources/*、market_snapshot.py、infer_market_snapshot.py、market_bridge.py 及相关测试。遵循源码 AGENTS、项目目标、API 优先采集与 context-wcpp-odds-evidence 技能。所有验证使用 /workspace/football-venv/bin/python，线程数 1；测试进程以 env -i 清空真实环境，仅注入测试凭据。

## 已修复的三类问题

### 1. 盘口源接受有歧义的独立比赛身份（高）

修复前：在合成 ESPN 比赛中插入第二个 home 竞争者，字典覆盖后仍生成 1 条有效盘口；顶层状态为 pre、内层 competition 状态为 in 时，也仍生成 1 条有效盘口。重复比赛 ID、多个 competition 及内外 ID/时间冲突未统一拒绝。

修复：market_snapshot.build 要求唯一事件 ID、单一 competition、两个明确且不同的球队身份；存在内层 ID/日期/状态时必须与顶层一致。重复 provider event ID 不再用于匹配。破损独立赛事记录单列排除，不丢弃其他有效赛事。完整同机构同线两边价格、报价时间和原有快照规则保持。

验证：新增覆盖重复主队、重复赛事、多个 competition、内外 ID/开球/状态冲突、坏赛事不影响正常赛事、同 provider ID 指向不同比赛。原真实别名规则、同线配对、陈旧/未来报价与冲突机构测试仍通过。

### 2. 鉴权错误可能误报成功，单场请求拒绝后不停（高）

修复前：HTTP 200 JSON errors.token 被 scrub 删除为 {}，进而标记 api_success=true、authenticated=true。合成首个 403 在 match_context 中仍触发总计 6 次请求。

修复：clients.fetch 先从原始结构判断业务错误，再进行脱敏；HTTP 200 认证错误保留固定 PROVIDER_AUTHENTICATION_REJECTION 类别，不保存原始错误正文或密钥。统一 service_blocked 判定覆盖 401/403/429、缺绑定与 HTTP 200 认证及明确限流/日额度拒绝，match_context 和 api_first 均停止同服务后续请求；缺项保存 BATCH_PROVIDER_BLOCKED，先前成功证据保留。拒绝结果不写成功缓存。

验证：覆盖 errors.token/key/api_key/apikey/authentication、首请求及中途拒绝、完整成功六字段形状、默认批入口停止与无成功缓存。errors.rateLimit 与明确日请求上限统一标记 RATE_LIMITED 并停止；普通资源/赛季 plan 限制不全局阻断其他资源。

### 3. 独立 TheOdds 采集器可把响应回显凭据落盘（高）

修复前：合成含请求 apiKey 回显的 JSON 被 market_snapshot.fetch 直接写入 odds.json；该入口使用默认 urlopen 的重定向行为且不限制响应大小。

修复：采集限于既有 SCOPES 的固定 ESPN/TheOdds HTTPS 端点；请求和公开证据 URL 只允许规定的鉴权差异，禁止重定向。读取上限 20 MB，校验 JSON 结构、明确鉴权字段、原文及解码后真实凭据回显；原始 provider 的正常业务 key 字段保留；通过验证后才以独占新建模式保存。元数据只保留无凭据 URL，不覆盖已有响应文件。

验证：覆盖批准端点、禁用重定向处理器、跨站或公开 URL 不一致在请求前拒绝、普通及 Unicode 转义回显不落盘、敏感字段/错误响应/超长响应拒绝、已有证据不覆盖；非空 totals+h2h 响应从 fetch 保存到 build 生成两条合格盘口，原始机构/市场 key 和完整字节保持。

## 验证结果

- 数据来源模块：52 tests，全部通过。
- TheOdds/InferSports/盘口桥接模块：55 tests，全部通过。
- 合计 107 tests；新增 14 个测试方法，多组子案例。全部为软件合成验证，不是实际鉴权、来源权限或预测效果验证。
- 首次盘口组合测试因未设置 PYTHONPATH=runtime 导致 bridge 导入失败；补充项目导入路径后原组 54 项全部通过，未为该环境问题修改代码。
- 完整命令、文件哈希及机器可读状态见 audit_sources_markets-validation.json。

## 审查边界与遗留项

- 未修改 InferSports、market_bridge 或 quota.py；现有测试覆盖 stale 标志、明确机构、full_time、完整两侧、同线/拆分线、真实 as_of、源文件哈希、同场阶段/身份、追加时点、机构最新报价冲突及共享额度账本。
- 旧 match_context 与独立盘口 collect 入口仍未统一迁移到跨进程 QuotaLedger；默认 api_first 只有显式 quota_policies 时启用共享预算。此次修复拒绝停止，但不声称所有旧入口已受共享预算保护。
- API-first 的通用 requires_source_time 当前与运行时 now 比较；其 query_time 由客户端在请求开始记录，没有独立 captured_at。本轮未改其时点结构，不应将通用 API_EVIDENCE_PENDING_REVIEW 当作已通过盘口证据契约；独立盘口适配器仍使用真实捕获时间和报价时间双重核验。
- 未做新业务 API 测试，因此不刷新来源状态、权限、额度或注册表。

## 资产影响

只修改三处实现及三处测试文件；未编辑活动 Current/Test 工件、注册表、参数、数据库、历史冻结或数值推理模块，未使用 Git 命令。来源质量修复不等于模型晋级，不声称命中率或真实权限改善。

## 独立复核后的修正

独立复核发现初稿把原始 TheOdds bookmakers/markets 的业务 key 误交给通用敏感字段规则，造成非空合法赔率被拒。已用新增完整 totals+h2h fetch→build 回归先复现失败，再改为不修改 provider 数据的递归凭据检查；只拒绝明确鉴权字段和真实密钥值（含 JSON 转义后的字符串/字段名），保留业务 key。修正后盘口组 55 项全部通过。另按独立复核补充 HTTP 200 rateLimit/requests 日限额停止测试及普通 plan 范围限制不全局停止测试，数据来源组 52 项通过。
