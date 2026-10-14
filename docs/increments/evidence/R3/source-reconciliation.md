# R3-S1 旧治理资产只读盘点与处置核对

- 采集时间：2026-10-14 17:54（Asia/Shanghai）；主机 `192.168.1.9`。
- 目标容器：`datara-mysql-meta`；查询全部来自 `information_schema`；未执行旧库 DML/DDL。
- 当前库：`datara_meta` 为 57 张 BASE TABLE；`datara_rebuild_i0` 为 3 张 BASE TABLE。R0 证据曾记 `datara_meta` 56 张；现证据暂无法解释 1 张计数差异，完整 live table list 已附于 `remote-schema-inventory.txt`，在迁移前应以表名清单/DDL 指纹而非单一计数作为基线。当前未观察到 VIEW，因此不是 BASE TABLE 与 VIEW 口径差异。
- I18 数仓建模 7 表当前存在；核心表估算行数：domain 4、layer 5、model 3、field 27、relation 2、version 1；`information_schema.TABLE_ROWS` 为 InnoDB 估算值，不作为最终导入核对计数。
- I19 元数据/标签 3 表存在，当前估算 0 行；I20 指标 2 表存在，当前估算 0 行。
- I21 质量 6 表存在；`t_qc_rule` 估算 0 行，其余表估算 0 行。旧 `t_qc_task`、`t_qc_run`、`t_qc_exception`、`t_qc_report` 等运行记录并无统一 `created_at/updated_at/generated_at`；R3 只迁移为新记录时，须由新 schema 的 DB defaults 生成系统时间戳，旧业务时间保存在来源字段中。
- I22 标准 7 表存在；`t_std_approval`、`t_std_code`、`t_std_code_value` 各估算 1 行，其他表估算 0 行。
- 迁移清单曾列 `t_mask_rule` 与 `t_access_log`，但当前 `datara_meta` live table list 未包含两表，且旧 ORM 未定义对应模型：它们是旧设计规划项，不是可迁移的现存表。按用户对内部系统的裁定，不建设敏感值扫描/列级脱敏/敏感内容加密；新 R3 只需建设基本操作审计，不假称迁移不存在的历史审计数据。
- `t_user` 4 行（估算）；实际结构含 `user_name/user_pwd/user_role/state/create_time/update_time`。R3 不迁移密码；账号迁移/验证身份的具体规则归 R1 identity carry-forward，不在治理资产 adapter 中读取或输出凭据。
- `datara_rebuild_i0` 当前 3 表仅用于身份/项目/datasource 基础，不含治理新表；确认 R3 schema 与业务基线一致。
- 后台日志：修订后的采集脚本只输出各容器最近 10 分钟 ERROR/Traceback/Exception 计数，不导出原始请求或敏感日志正文。

## 需要同步修订的旧处置表

R0 迁移清单将 `t_mask_rule/t_access_log` 写成已发现对象；其“已存在/待迁移”结论与 live schema 不一致。R3 设计已按用户裁定改为“遮罩表不存在且敏感值脱敏不纳入首期；操作审计新建”。此差异属于文档基线纠正，不修改任何数据库对象。
