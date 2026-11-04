完整研究执行归档；代码提交见manifest.json。解包前核验每卷及整包SHA256，restore.py只解到新目录，不覆盖运行资产。

运行：python restore.py --stage /absolute/new-directory

files.json逐文件哈希覆盖所有数值矩阵、逐场预测、xG依赖、原始采集证据和真实未来冻结。future/dependencies索引保留绝对原路径与副本映射；恢复不改写原冻结内容或哈希。先前全部活动资产仍由既有私有备份恢复，本包不变更Champion。未完成赛事及盘口证据缺口见执行结果。
