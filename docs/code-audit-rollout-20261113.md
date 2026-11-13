# 2026-11-13 代码审计运行版本

源码PR #37已合并，main为 `1257fdde7b6746b7ba6d2aa919382214a2cfb589`。本次仅更新已有collect任务的collector-code固定版本，并给前向外围增加 `research_program/future_identity.py` 依赖；两条定时表达式、请求/时间预算和5分钟job上限不变。

训练及锁定推理继续使用 `6639867d502a2dfe53a9a235c8761f8ee6b91533`。复制外围代码前后仍逐个核对原协议锁定的8份源码。活动注册表、模型权重、旧候选、旧冻结均不切换。trainer输入校验的新修复仅在最新源码中，尚未升级到这个固定训练版本。

配套韩K采集器保存赛程/身份更正并恢复跨年历史分页，原始观察和游标保持。源码严格资产集成24组938次通过、零跳过；数据采集器14项测试通过；固定base加6文件外围的离线SHA/导入验收通过。实际部署结果以 `workspace-updates/20261113-code-audit/delivery-receipt.json` 为准，不由代码合并推断。

回滚：对本次数据部署提交追加revert，恢复collector-code `8488660427610e0fbf6df9a6d356e84f6ec66b7b` 及原5文件外围清单；训练base无需回滚。保留 `scoreboard-attempts.json` 及所有追加数据/冻结，旧代码忽略新增队列文件。源码回滚点为PR前 `a342384242140c613033bd7f830569f3ae92babd`，共享main只用revert，不重写历史。
