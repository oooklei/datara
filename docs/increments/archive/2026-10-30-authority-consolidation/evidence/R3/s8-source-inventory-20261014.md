# R3-S8 旧治理资产只读盘点（初步证据）

- schema/列结构采样：2026-10-14 22:44:05 Asia/Shanghai；精确行数查询：2026-10-14 22:46:32 Asia/Shanghai；目标主机 `192.168.1.9`；MySQL 容器 `datara-mysql-meta`。
- 查询来源：仓库脚本 `infra/r3_readonly_inventory.sh`。脚本 SQL 仅访问 `information_schema`，读取表引擎行数估算/列结构，并汇总 10 分钟 ERROR 标记；未执行任何 DML、DDL 或导出业务行。
- 远端 schema 表数：`datara_meta` 57 张 BASE TABLE；`datara_rebuild_i0` 16 张 BASE TABLE（I1/R1 + R3 迁移后的当前隔离库）。
- I18 建模：精确 `COUNT(*)` 为 `t_biz_domain` 4、`t_dw_layer` 5、`t_dw_model` 3、`t_dw_model_field` 27、`t_dw_model_relation` 2、`t_dw_model_version` 1、`t_engine_type` 3。
- I19 元数据/标签：`t_meta_table_ext`、`t_meta_tag`、`t_meta_tagging` 精确行数均为 0。
- I20 指标：`t_indicator`、`t_indicator_version` 精确行数均为 0。
- I21 质量：`t_qc_alarm_policy`、`t_qc_exception`、`t_qc_report`、`t_qc_rule`、`t_qc_run`、`t_qc_task` 精确行数均为 0；`Qc*` ORM/表仍保留，旧 API/engine 已退役。
- I22 标准：7 表均存在；`t_std_approval`、`t_std_code`、`t_std_code_value` 各 1 行，其余表为 0 行。
- 身份/权限相关 `t_user` 精确行数为 4；本轮未读取用户行或凭据。旧盘点提到的 `t_mask_rule`、`t_access_log` 未出现在 live table list；按用户内部系统范围决定，本次不补密级/脱敏功能。
- 新隔离库 12 张治理表精确计数：asset 15、asset_field 30、asset_tag 7、lineage_edge 6、quality_rule 7、quality_run 0、semantic_metric 5、standard 5、tag 7、migration_batch 0、migration_item 0；其余 4 张为 I1 身份/项目 schema。新治理计数包含 R3-S7 控件验证产生的 fixture，不能当作旧资产已迁移。
- 后台容器日志窗口 10 分钟：`datara-rebuild-api`、`datara-api`、`datara-worker` 的 ERROR/Traceback/Exception 标记均为 0。
- 源码调用面初步映射（源文件已定位，仍需逐实体字段/关系核对）：I18 位于 `datara-backend/common/models.py` 的 `BizDomain/DwLayer/EngineType/DwModel/DwModelField/DwModelRelation/DwModelVersion`，由旧 `api/model.py` 的 models/fields/versions/reverse/DDL/lineage API 服务，正式页面在 `/model/*`；I19 位于 `MetaTableExt/MetaTag/MetaTagging`，由 `api/meta.py` 的 catalog/tags/taggings/map 路由服务，页面在 `/meta/catalog`、`/meta/tag`；I20 位于 `Indicator/IndicatorVersion`，由 `api/ind.py` 的 `/indicators*` 服务；I22 位于 Std* ORM 和旧 `api/std.py` 的 elements/codes/code-values/naming-rules/mappings/approvals/check API，页面在 `/std/*`。I21 的 Qc* ORM 留存，但旧 qc router/engine 已按既定裁定退役；新的 `rebuild/governance/api.py` 提供 project-scoped assets/tags/lineage/quality-rules/quality-runs/standards/metrics/audit API。当前只是入口映射，不代表 API 语义等价或授权规则已闭合。
- 模型覆盖差异：新 R3 schema 只有通用 asset/field/tag/lineage/quality rule+run/standard/semantic metric 等表。旧 I18 分层/模型版本、I20 指标维度/单位/来源及历史版本、I21 调度任务/异常/报告/告警策略、I22 码值集合/审批/命名规则/映射/校验报告，均没有独立、结构等价的新实体；仅 `properties_json`/文本字段是否足以保真尚未证明。不能把这些非空数据按当前 R3 schema 直接导入并声称完整承接。
- 迁移裁定门：在用户选定“扩展规范化新模型”或“旧库只读保留、延后替换”之前，不执行任何导入；当前 `t_dw_*` 45 条精确行和 I22 三条记录必须保持原样。内部系统不要求密级/脱敏功能，故不为缺失的 `t_mask_rule` 另建实现。
- 运行限制：直接传输 inventory 脚本时出现 CRLF 诊断；重跑通过 `tr -d '\015' | bash -s` 清除传输层 CR 后正常结束。精确数查询 `infra/r3_s8_exact_counts.sh` 成功，但尚无主键/外键关系等价性证明。因此这仍是 S8 的中间证据，不是 S8 完成/验收证据；尚须完成用户/API/菜单/消费者映射、实体字段语义映射及关系对账。
- 未做：读旧业务行；写任一 schema；迁移或删除资产；重启/部署容器。
