# I69 / T69 — DEP-07~12 宿主实测覆盖矩阵（t69host, s129-c7c92b）

- 执行线：Trae（实施线），2026-10-20
- 硬约束遵守：.git 只读、未 push、未调用 aoci_*
- 交付物：`datara-backend/tests/rebuild/test_e2e_six_node_types.py`（7 测试）
- 本地证据：`t69-dep07-e2e-six-node-types.txt`（7 passed）、`t69-dep10-full-rebuild-pytest.txt`（854 passed / 11 failed / 1 skipped）

## DEP-07 端到端六类节点闭环

验收锚：六类执行器各 ≥1 条真实 FORMAL 执行闭环。

| 节点类型 | 测试 | 实测内容 | 状态 |
|---|---|---|---|
| SQL | test_sql_node_formal_lifecycle_with_real_execution_port | SQL 真执行端口（BEGIN READ ONLY + FakeEngineRegistry 连接审计）+ FORMAL 状态机 PENDING→RUNNING→SUCCEEDED | 🟢 本地绿 |
| PYTHON | test_python_shell_pipeline_formal_state_machine | 5 节点（START/SQL/PYTHON/SHELL/END）FORMAL task 集 + 状态机 | 🟢 本地绿 |
| SHELL | 同上 | 同上（SHELL 节点入 task 集） | 🟢 本地绿 |
| SYNC | test_sync_node_bridge_persists_metrics_stats_and_lineage | sync_executor 桥：8 类 metrics 键、result_stat (1,0,0)、rows_in json、8 segments、SYNC_FIELD_LINEAGE (sync, 4:src.users→5:dw.users) | 🟢 本地绿（FakeDriver） |
| DEPENDENCY | test_dependency_node_evaluate_reports_pending_without_history | /dependency/evaluate 无历史指标 → 诚实 pending verdict + per-condition resolved | 🟢 本地绿 |
| STREAM | test_stream_instance_job_lifecycle_and_checkpoint_roundtrip | STREAM 实例 + job 生命周期 + checkpoint roundtrip | 🟢 本地绿（内存库） |

阻塞：SYNC 真实 MySQL / STREAM 真实 Kafka+Redis 驱动闭环需 1.9 宿主（S128 已知环境阻塞，本机无 docker、目标库不可达）。本地层以 FakeDriver/内存库最大化覆盖了桥接逻辑与持久化协议。

## DEP-08 P95 性能三指标

未实测。SQL IDE 补全 2s / 调度延迟 10s / 流刷新 5s 均需 1.9 宿主远程环境。**阻塞 = 1.9 宿主授权（用户操作项）**。

## DEP-09 部署基线 1.9 实测

未执行。T44 备料 5 文件在库（PLAN_ONLY 门控）。**阻塞 = 1.9 宿主授权（用户操作项）**。

## DEP-10 Backend 测试全量

`python -m pytest tests/rebuild -q --tb=no` → **854 passed / 11 failed / 1 skipped**（约 4.5 min）。

11 个失败全部为**预先存在**的治理域失败（T67/T69 之前即存在，本轮上报监督线）：

| 文件 | 失败数 | 现象 |
|---|---|---|
| test_governance_legacy_i19_preview_api.py | 2 | assert 403 == 200（预览 API 返回 403） |
| test_governance_legacy_i20_preview_api.py | 4 | assert 403 == 200（同上） |
| test_governance_legacy_i23_mapping.py | 4 | mapper 错误码集合不含预期（unsupported_target_role 覆盖了 invalid_source_identity / incomplete_source_row 等） |
| test_governance_legacy_i23_preview_api.py | 1 | assert 200 == 401（capability 端点未鉴权） |

佐证：`test_governance_legacy_dry_run_api.py`（T67 修复对象）在全量中 0 失败，T67 修复经全量回归验证。

## DEP-11 变量引用校验五诊断码

`test_dep11_variable_reference_five_diagnostic_codes` 逐码实测（check-reference API）：

| 诊断码 | 触发式 | 实测结果 |
|---|---|---|
| SYNTAX | `${bad syntax}`（有大括号但不匹配 `${scope.name}` 形态；无闭合 `}` 的片段不触发） | 🟢 |
| SCOPE_INVISIBLE | `${tmp.ghost}`（scope 不在可见集） | 🟢 |
| UNDEFINED | `${project.missing_var}` | 🟢 |
| TYPE_MISMATCH | `${project.bad_int}`（value_type=integer 存 abc，API upsert 校验绕过、直插行构造） | 🟢 |
| CYCLE | `${project.loop_a}` → loop_b → loop_a | 🟢 |
| （健康路径） | `${project.alpha}` → valid=true, diagnostics=[] | 🟢 |

覆盖度清单说明：本层覆盖**后端 check-reference 语义**全覆盖（5 码 + 健康路径）。"所有核心节点表单和编辑器入口"的前端接线属前端域，未在本任务范围内实测。

## DEP-12 异常注入六场景

`test_dep12_cancel_failure_guard_redispatch_and_attempt_isolation` 实测 3 场景（本地可测部分）：

| 场景 | 实测内容 | 状态 |
|---|---|---|
| 取消 | RUNNING 实例 /runs/{id}/cancel → 200 {status: CANCELLED} | 🟢 本地绿 |
| 失败注入 | FakeDriver fail_write → attempt=FAILED + task=FAILED + 无 result_stat；guard：FAILED task 原地重跑 → ExecutionDomainError 4103 | 🟢 本地绿 |
| 重派 + attempt 隔离 | 新 task_id（(workflow_instance_id, task_id) UNIQUE 约束强制）重派 → 新 task attempt_no=1 SUCCEEDED，失败 task 的 attempt_no=1 FAILED 互不污染；append_attempt 单调到 2 | 🟢 本地绿 |
| 断点恢复 | 需真实流环境（checkpoint 恢复消费） | 🔴 阻塞 = 1.9 宿主 |
| 重复数据 | 需真实流环境（幂等去重实测） | 🔴 阻塞 = 1.9 宿主 |
| 乱序数据 | 需真实流环境（event_time/offset 乱序实测） | 🔴 阻塞 = 1.9 宿主 |

## 环境阻塞汇总（需 1.9 宿主）

- DEP-07 收口：SYNC 真实 MySQL 驱动 + STREAM 真实 Kafka/Redis 驱动
- DEP-08：P95 三指标全部
- DEP-09：部署基线实测（12 容器 + 18091）
- DEP-12 收口：断点恢复 / 重复数据 / 乱序数据
