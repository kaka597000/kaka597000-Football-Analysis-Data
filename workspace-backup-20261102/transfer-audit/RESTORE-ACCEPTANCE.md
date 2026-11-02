# 新云端核心恢复验收

交接固定版本：a0635b6551ba7a31c524ba3b25aee7e0ccbb8430。
源码固定版本：627838f1823087e7f3672ef2a121812b9ea6d05f。

- 核心包199,436,428字节，8片及整体SHA256通过。
- 新暂存目录 /workspace/wcpp-incoming-20261102：1650文件hash、21队列42工件hash、两个数据库quick_check均通过。
- 原源码完整备份 local-source-before-restore.tar.gz；逐文件复核304个非Git元数据文件未变，完整本地status一致，35项改动保留。Git fetch仅增加对象及FETCH_HEAD。
- 独立源码 source-627838f，真实Git HEAD已登记，工作区干净。
- 静态检查271源码文件，0发现。
- 首轮20组共349项测试；automation三项错误、upset一项失败均因独立源码缺Git元数据。补齐真实提交后受影响模块全部复测通过。详见tests.log、retest-automation.log、retest-upset.log。
- 原配方刷新私有集成组缺历史资产而跳过，不称全部无跳过通过。
- ESPN新查询11月7日Leeds–Tottenham未来赛程，summary验证非中立且未开赛；默认入口双模型51×51非负归一矩阵通过；隔离冻结写入和读回hash校验1份通过。仅迁移功能验收，不发布推荐、不计业务KPI，首发与盘口完整性未验收。
- 原WCPP对照1213文件相同、435缺失、2冲突。仅新增435文件，见additive-integration.json；原registry与统一库均未覆盖。新库仍在暂存目录。
- 新registry通过incoming-active-model.json显式传入；其42工件已接入原WCPP路径。默认主流程未切换。
- 数据仓库映射：/workspace/Football-Analysis-Data → /workspace/kaka597000-Football-Analysis-Data；未用旧缓存覆盖新clone，未改保存的仓库选择。

## 验收入口

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python /workspace/wcpp-transfer-20261102/source-627838f/runtime/predict_active.py /workspace/wcpp-transfer-20261102/future-fixture.json --registry /workspace/wcpp-transfer-20261102/incoming-active-model.json --out NEW_OUTPUT.json --freeze-root /workspace/wcpp-transfer-20261102/test-freezes
```

仅适用于该赛程仍未开赛且重新核查时间与输入时；不要把旧输入当作持续更新的数据。

## 未完成及边界

历史三包未下载；原配方刷新私有集成测试缺audit-history历史输入。原源码尚未合并至新基线，默认registry和数据库未切换，不能声称全部迁移完成。API凭据未做本轮鉴权验证，未部署或验证邮件/自动任务，未删除旧环境及资产。
