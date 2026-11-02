# 旧云端交接包 → 新云端

北京时间2026年11月2日整理。本分支保存交接包，未改 main。源码仍从原项目仓库下载；这里补充未在源码仓库中的数据库、模型、冻结和报告。仓库公开，包中不含环境密钥；原工作区保留。

## 给新云端直接执行

先读 [HANDOFF.txt](HANDOFF.txt) 与 [HANDOFF.md](HANDOFF.md)。保护新云端已有35项本地修改，不覆盖源码，不 reset。

```bash
mkdir -p /workspace/wcpp-transfer-20261102
cd /workspace/wcpp-transfer-20261102
curl -fL 'https://raw.githubusercontent.com/kaka597000/kaka597000-Football-Analysis-Data/handoff/wcpp-20261102/control.zip' -o control.zip
curl -fL 'https://raw.githubusercontent.com/kaka597000/kaka597000-Football-Analysis-Data/handoff/wcpp-20261102/fetch_parts.py' -o fetch_parts.py
python fetch_parts.py --group core
python -m zipfile -e control.zip .
python restore.py --packages . --stage /workspace/wcpp-incoming-20261102 --groups core
```

暂存目录必须尚不存在。此步骤仅解压与验证，不自动替换 `/workspace/WCPP`；该目录已存在时先对照保全，按HANDOFF.md继续接入和测试。核心1650文件、42活动工件、21队列、两个数据库已在旧云端暂存自测，新云端仍须独立验收。

## 历史归档按需下载

```bash
python fetch_parts.py --group models-history
python fetch_parts.py --group audit-history
python fetch_parts.py --group data-history
```

核心约200MB，历史约2.23GB，总计约2.43GB；每片≤24MiB。脚本检查每片与整体SHA256。无需clone整个交接分支；普通clone会下载所有归档。

密钥在新云端安全设置中确认，不在聊天中传输。下载完成不等于项目恢复完成；需核对目标代码兼容、依赖与真实输入测试结果。
