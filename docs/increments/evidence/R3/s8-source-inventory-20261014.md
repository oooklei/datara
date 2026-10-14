# R3-S8 旧治理资产只读盘点（初步证据）

- 查询时间：2026-10-14 22:44:05 Asia/Shanghai；目标主机 `192.168.1.9`；MySQL 容器 `datara-mysql-meta`。
- 查询来源：仓库脚本 `infra/r3_readonly_inventory.sh`。脚本 SQL 仅访问 `information_schema`，读取表引擎行数估算/列结构，并汇总 10 分钟 ERROR 标记；未执行任何 DML、DDL 或导出业务行。
- 远端 schema 表数：`datara_meta` 57 张 BASE TABLE；`datara_rebuild_i0` 16 张 BASE TABLE（I1/R1 + R3 迁移后的当前隔离库）。
- I18 建模：`t_biz_domain` 4、`t_dw_layer` 5、`t_dw_model` 3、`t_dw_model_field` 27、`t_dw_model_relation` 2、`t_dw_model_version` 1、`t_engine_type` 3（均为 `information_schema.tables.table_rows` 估算值，不是精确 COUNT）。
- I19 元数据/标签：`t_meta_table_ext`、`t_meta_tag`、`t_meta_tagging` 均估算 0 行。
- I20 指标：`t_indicator`、`t_indicator_version` 均估算 0 行。
- I21 质量：`t_qc_alarm_policy`、`t_qc_exception`、`t_qc_report`、`t_qc_rule`、`t_qc_run`、`t_qc_task` 均估算 0 行；`Qc*` ORM/表仍保留，旧 API/engine 已退役。
- I22 标准：7 表均存在；`t_std_approval`、`t_std_code`、`t_std_code_value` 各估算 1 行，其余表估算 0 行。
- 身份/权限相关 `t_user` 估算 4 行；本轮未读取用户行或凭据。旧盘点提到的 `t_mask_rule`、`t_access_log` 未出现在 live table list；按用户内部系统范围决定，本次不补密级/脱敏功能。
- 新隔离库 16 张表包含 I1 身份/项目基础表与 12 张 R3 governance 表；目前本证据未读取每个新治理实体精确行数，也未证明 I18–I23 对应映射或数据关系。
- 后台容器日志窗口 10 分钟：`datara-rebuild-api`、`datara-api`、`datara-worker` 的 ERROR/Traceback/Exception 标记均为 0。
- 运行限制：Windows 提交到远端 bash 时保留 CRLF，产生 `set -o pipefail` 和尾随 CR 诊断；核心信息架构查询和日志扫描已输出，但脚本末尾退出非零。因此本文件是初步采样，不是 S8 完成/验收证据。应先修复本地脚本行尾/传输方式，再重跑，并补精确 COUNT、用户/API/菜单/消费者映射、目标库精确实体计数及关系对账。
- 未做：读旧业务行；写任一 schema；迁移或删除资产；重启/部署容器。
