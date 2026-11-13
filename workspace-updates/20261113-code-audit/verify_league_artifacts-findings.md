# 欧国联/日联杯既有参数独立数值核查

只读加载欧国联 8 份、日联杯 edition 4 份、八强迁移 4 份既有研究工件。没有训练、调用 predict、冻结、网络访问、Git 操作或真实数据库写入；未改源码和工件。检查为现有参数重载与合成球队输入的软件验证，不是赛前回测或效果证明。

16 份工件合计 160 个矩阵：已见双方、仅主队未见、仅客队未见、双方未见；欧国联覆盖 neutral=False/True，日联杯覆盖 None/False/True。全部矩阵为 51×51、有限、非负且归一化；胜平负合计为 1；矩阵边际均值与返回预期进球一致，最大误差均为 4.44e-16。双方未见时，返回率与工件总体先验及已定义场地通道一致。

欧国联 64 次 distribution 返回的 missing 列表均符合实际未见球队；current 为无球队项的总体模型，按设计返回空列表。日联杯 distribution 仅返回矩阵和均值，无法直接审计返回 missing 列表。源码显示八强 predict 和历史诊断明确列出未见球队，但 edition predict 未输出该元数据；这属于可观察性缺口，本检查未调用 predict，不改锁定文件。

运行：OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=runtime /workspace/football-venv/bin/python（内联只读核查脚本）。逐工件哈希、输入分支及结果见 verify_league_artifacts-validation.json。16 份工件运行前后哈希一致。
