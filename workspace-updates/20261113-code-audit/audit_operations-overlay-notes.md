# 固定推理版本与本轮外围代码的离线兼容核验

本次仅做离线验收，没有编辑 workflow、更新 pin、hydrate、联网或写真实运行记录。

现有数据 workflow 保持推理/训练 base `6639867d502a2dfe53a9a235c8761f8ee6b91533`，采集另从 `collector-code` checkout 执行。捕获/复盘步骤先校验协议锁，再把5个外围文件复制到 base：prospective_cycle、market_bridge、result_queue、promotion_review、evaluation。

若 collector-code 更新到本轮源码，必须在该 overlay 列表中再加入：

```text
runtime/research_program/future_identity.py
```

本轮 prospective_cycle 的恢复包和终端复盘都直接导入该 helper。只改 collector-code pin、沿用5项列表，会让 base 缺少新模块；实际执行捕获/复盘时导入失败。helper 仅依赖已有 `research.analysis_freeze` 与标准库，无新增 pip 依赖。其他5项仍需保留。collector 的公平轮转直接在 collector-code 下执行，新增依赖 os/tempfile 均属标准库，独立 `scoreboard-attempts.json` 保存在数据根目录。

现有两份真实 bundle 共约束8个源码文件，均不在6项 overlay 列表内：continental/ucl_ml.py、prediction_engine.py、prediction_service.py、research/ucl_fixed_refresh.py、research_program/challengers.py、future_validation.py、ucl_refresh_forward.py、ucl_refresh_review.py。应继续在复制前后核对这些原始 SHA，保留现有 `locked.intersection(paths)` 拒绝机制，并把 helper 的实际 SHA 纳入 runtime-revisions receipt。

已获 root 授权执行 `git archive`，在唯一临时目录展开固定 base，复制原5项加 helper，核对8份锁定源码的复制前/后 SHA 都与真实协议一致；然后从临时 base 实际 import prospective_cycle 和 future_identity。子进程移除 PYTHONPATH，并检查两个模块路径均来自临时 base。结果 PASS（8个锁定源码、6个 overlay 文件、2个入口模块导入）。这只证明离线依赖齐全和锁定字节未变，不代表真实平台任务成功。

可复算脚本：`audit_operations-overlay-smoke.py`；实际结果：`audit_operations-overlay-validation.json`。

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /workspace/football-venv/bin/python \
  /workspace/WCPP/reports/code-audit-20261113/audit_operations-overlay-smoke.py \
  --repo /workspace/Football-Analysis \
  --data /workspace/kaka597000-Football-Analysis-Data \
  --out /tmp/wcpp-overlay-recheck.json
```

脚本输出文件使用独占创建，复跑请选择新的结果路径；Git 仅用于读取固定源码 archive，不切分支、不创建 worktree、不提交。

## 训练输入验证的部署边界

`automation/trainer.py` 不在上述8份源锁或当前活动注册表中。其 `code_fingerprint` 记录 trainer 加 optimization 三个文件的 SHA，用于新的候选输入指纹和重拟合判断，不是当前/test 工件加载锁。已有无人值守候选字节不会因新源码失效或被改写。

训练任务实际在固定 base 的 code 目录调用 `runtime.automation.run train`，再进入 `.trainer.train`。最近可读留存训练记录是北京时间2026-11-12 18:14、状态 COMPLETED、source_commit 为上述6639867版本。仅更新 collector-code 不会部署本轮 trainer 的场地/时间输入核验。因此本轮可交付该修复源码与回归，但训练输入验证仍待独立 rollout；本轮不修改 base pin、不启动训练，也不把这一修复放入捕获/复盘 overlay。
