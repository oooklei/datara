# I18-I23 迁移盘点基线

> R0 只盘点和初步定级，不执行迁移、删除或旧表写入；`MIGRATE` 仅表示后续迁移候选，不代表数据已迁移完成。

| 资产 | 已发现表/对象 | R0 处置 | R1-R3 计划 |
|---|---|---|---|
| I18 数仓建模 | `t_dw_layer`, `t_biz_domain`, `t_engine_type`, `t_dw_model`, `t_dw_model_field`, `t_dw_model_relation`, `t_dw_model_version` | `MIGRATE` | 导入新治理/模型域，旧表迁移期只读 |
| I19 元数据/标签 | `t_meta_table_ext`, `t_meta_tag`, `t_meta_tagging` | `MIGRATE` | 导入资产、标签、业务域，保留实时内省 |
| I20 指标 | `t_indicator`, `t_indicator_version` | `MIGRATE` | 导入指标定义和版本快照 |
| I21 数据质量 | `t_qc_rule`, `t_qc_task`, `t_qc_run`, `t_qc_exception`, `t_qc_report`, `t_qc_alarm_policy` | `MIGRATE` | 导入规则、运行、异常、报告和告警关联 |
| I22 数据标准 | `t_std_element`, `t_std_code`, `t_std_code_value`, `t_std_naming_rule`, `t_std_mapping`, `t_std_approval`, `t_std_check_report` | `MIGRATE` | 导入数据元、码表、命名、映射和审批快照 |
| I23 权限 | `t_user` 扩展、`t_mask_rule`, `t_access_log` | `READ_ONLY_COMPAT` + `MIGRATE` | 先保留旧权限读取，导入新 RBAC/数据权限/审计模型后切换新写入真源 |
| 现有运行/工作流资产 | `t_wf_category`, `t_wf_definition`, `t_wf_definition_log`, `t_wf_schedule`, `t_wf_template`, `t_wf_template_version`, `t_wf_variable`, `t_workflow_instance`, `t_task_instance`, `t_task_log`, `t_run_event`, `t_runtime_node` | `READ_ONLY_COMPAT` | R1-R2 建立新模型和版本/运行快照映射 |
| 现有流资产 | `t_stream_job`, `t_stream_offset` | `READ_ONLY_COMPAT` | R8 建立独立 stream_job/checkpoint/metric/failure 模型后映射 |

处置原则：禁止直接删除；迁移期间旧资产只读；新 Backend 迁移完成后成为新写入真源；未完成迁移前不得标记旧资产 `RETIRE_AFTER_MIGRATION`。
