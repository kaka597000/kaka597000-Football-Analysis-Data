# 验收记录更正与最终代码补验

本次仅更正文档并补验，未改模型、权重、候选、冻结或实验结论。原日志原样保留；更正前 README 和 validation 另存于本目录。

## 历史批次（不回填运行身份）

| 原日志 | 数量 | 失败 / 跳过 | 本地日志mtime（北京时间，仅观察值） |
|---|---:|---|---|
| ../integration.log.gz | 1,080 / 25套件 | 0 / 0 | 2026-11-18 16:38:43 |
| ../data-tests-final.log.gz | 28 | 0 / 0 | 2026-11-18 16:39:42 |
| ../data-tests-roundoff.log.gz | 30 | 0 / 0 | 2026-11-18 16:44:47 |

原日志没有绝对开始/结束时间，mtime不是可靠执行时间。测试时存在开发工作树改动，未保存完整树身份，因此精确执行提交未知。旧validation的源码78427c8…是后续交付锚点，不能证明该提交或最终783e02…已完整跑过1,080项。历史命令、后续锚点及限制见 historical-audit.json。

4个融合测试和5个生命周期测试已在1,080项内；后来生命周期单独运行6项，只有单名额测试新增。不能将4+6重复累计，也不能把分次总数称为最终完整运行。针对性运行没有单独保留日志及绝对时间，沿用原工具输出记录，不伪造补齐。

## 本次完整补验

源码：`783e02ddebd427383dbdd6a9e4b359dc68c13d8b`。
数据：`0884b5e166a0a21c404e5350a5bb209e71ed2e88`。
执行前两仓git状态均干净；结束仅新增本验收证据目录。

| 命令 | 北京时间开始 → 结束（2026-11-18） | 总数 | 失败 / 跳过 | 完整性 |
|---|---|---:|---|---|
| scripts/run_tests.py --layer integration | 16:50:30.864529 → 16:51:41.644449 | 1,081 / 25套件 | 0 / 0 | 完整严格资产集成 |
| unittest discover -s runtime -v | 16:51:41.666345 → 16:51:42.004957 | 30 | 0 / 0 | 完整数据runtime发现 |

Python 3.12.14。上述严格运行使用真实活动工件及注册表，不以普通CI替代。运行前后71份资产及受保护文件（包括原32份保护文件）哈希一致，见 protected-before.json、protected-after.json。原证据清单的所有SHA256亦已核对不变。

可复现命令（需相同真实资产与依赖；不要为复现覆盖现有工作树）：

```sh
cd /workspace/Football-Analysis
/workspace/football-venv/bin/python scripts/run_tests.py --layer integration
cd /workspace/kaka597000-Football-Analysis-Data
PYTHONPATH=/workspace/Football-Analysis/runtime /workspace/football-venv/bin/python -m unittest discover -s runtime -v
```

receipt.json保存精确提交、runtime/scripts树、时间、命令、退出码和日志哈希；对应两个log.gz保留原始输出。driver.py.txt记录执行驱动。后续提交仅增加本目录并更正第三批README/validation，因此测试对应上面的代码提交，后续文档提交不被冒称为精确HEAD全测。旧证据缺失的绝对时间与执行树无法恢复；本次补验独立解决最终代码完整验证缺口。
