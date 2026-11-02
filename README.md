# WCPP cloud handoff 2026-11-02

此分支只保存旧云端的交接包，不修改main或活动模型。

先下载 [control.zip](control.zip)、core-parts/ 内全部8片，再读取[新云端交接指令](HANDOFF.txt)。

核心包拆成每片<=24MiB以兼容上传大小限制。control.zip解压后的core-parts.json包含有序片名及SHA；把核心片放在它旁边，运行 `python join_core.py`，再运行 `python restore.py --packages . --stage /workspace/wcpp-incoming-20261102 --groups core`。

历史归档分别在models-history-parts/、audit-history-parts/、data-history-parts/；各目录的parts.json描述排序、单片及整体hash，可用`python fetch_parts.py --group models-history`取回并重组。未按需下载前，不把完整仓库clone当作必需。

保护新云端35项本地修改，不覆盖源码。核心1650文件、42工件、两个数据库已经旧云端暂存验收，新云端仍须独立检查；环境密钥不在包中。原工作区保留。本分支公开可下载。
