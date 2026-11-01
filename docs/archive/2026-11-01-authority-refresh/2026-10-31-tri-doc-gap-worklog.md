# 三文档合并收口 — Chief-of-Staff 查漏补缺工作日志

- **目标文档**：
  - `docs/designs/2026-10-29-phase-1-dbx-unified-backend-design.md`（dbx 统一后端迁移，phase-1 可行性设计）
  - `docs/designs/2026-10-31-frontend-style-drift-governance-plan.md`（前端样式漂移治理，review-only）
  - `docs/plans/2026-10-30-consolidation-and-simulation-todo.md`（合并收口与七项核查待办）
- **DRI**：QA（chief-of-staff 模式），2026-10-31 接管（embedded-gateway 迁移已转 codex）
- **策略**：先查漏补缺（三路并行 code-explorer），再按用户裁决修补；高风险/需用户裁决项单独标红。

## 查漏补缺结论（2026-10-31，三路并行 code-explorer）
- **Doc A**：dbx 统一后端迁移远未完成（仅 P1 基础设施就位；7/10 范围仍直连）。高风险 + 设计文档要求逐阶段用户批准。
- **Doc B**：已基本修完，仅 1 项残留（WorkflowRunMonitor 硬编码日志色）→ 本轮已修。
- **Doc C**：文档自述已过时，多数代码已落地；`/task-group` 经核查为**活跃功能（非死链）**，已排除误删。

## 用户裁决与执行记录（2026-10-31 续：裁决按建议推荐做，其他均批准）
- **Doc A P2（同步代理迁移）**：✅ 授权启动，但落地受设计文档「逐阶段用户批准」闸门约束。已确认两点事实：
  1. dbx `/query/execute` 响应结构 **已确认** = `{"columns":[...], "rows":[[...]], "truncated"?:bool}`（证据：`rebuild/governance/quality_dbx.py:parse_quality_counts`）。`DbxSyncGateway` 已正确解析该结构，并补齐 `conn.db`/`commit()`/`__enter__` 兼容 sync 执行器。
  2. **遗留同步链路无 dbx 映射**：`worker/executors/sync.py` 走 `common.models.DataSource`（`t_data_source`，仅 host/port/user/pwd，**无 `dbx_connection_id`**）+ `common/dsconn.open_connection()` 直连 pymysql；legacy 层**无迁移执行器**可加列。故 P2 不是「一开关切换」，而需先建**数据源→dbx 绑定层**（设计文档 gated phase），再把同步 I/O 在 dbx JSON API 上重表达（牺牲 SSCursor 流式、事务语义变化、分页待定）。
  → 已实施（方案 A，flag-guarded）后于 2026-10-31 **用户裁定回退**：新权威方案 `docs/plans/2026-10-31-embedded-direct-gateway-migration.md` 取代本方向（聚焦「浏览器直连网关」，与本同步执行器经 DbxClient 跑 SQL 属不同层面）。孤儿脚手架已删除——`rebuild/dbx/sync_gateway.py`、`tests/test_dbx_sync_gateway.py` 已删；`common/models.py:DatasourceDbxBinding` 已移除；`worker/executors/sync.py` 接线已复原为纯直连（`import os`/`_SYNC_VIA_DBX`/`_open_conn` 全移除）。仓库现与新权威方案一致。
- **Doc C A1（correction-plan 分支）**：✅ 采纳建议「维持不并入」。该分支为权威设计已退役的旧并行实现（orchestration/dbx/sshnode 替代），与现行架构冲突；保持不并入、不删除（留作考古）。
- **Doc C C7（治理 FK 级联）**：✅ 已实施。治理对象对 `rebuild_project` 外键改 `ON DELETE CASCADE`（`governance/models.py`）+ 新增迁移修订 `v0005`（MySQL 幂等 ALTER），使项目删除级联清理治理对象。
- **战略项（均批准）**：
  - lint 守卫：`tests/test_rebuild_dbx_identity_no_raw_drivers.py` ✅
  - 嵌入禁词契约测试：`datara-newweb/src/services/__tests__/embeddedBranding.contract.test.ts` ✅
  - `datara-web/` 归档：⏸ 受阻——Move-Item 报「文件被另一进程占用」，推迟（解锁后重试或评估是否必要）。前端仅注释引用，无功能依赖。

## 本轮已落地（可验证，lint 0）
- Doc B (a) 修复：`theme.css` + `WorkflowRunMonitor.vue`（新增 `--log-bg`/`--log-fg`，响应主题）。
- C7：`governance/models.py` FK CASCADE + `revisions/v0005_governance_project_fk_cascade.py` + `migrations.py` 注册。
- 前端契约测试：`embeddedBranding.contract.test.ts`。
- 后端守卫：`test_rebuild_dbx_identity_no_raw_drivers.py`（已删 `dbx/sync_gateway.py` + `tests/test_dbx_sync_gateway.py`，因用户 2026-10-31 回退 P2 孤儿脚手架）。
- 误报纠正：`/task-group` 为活跃功能，非死链，不动。

## 待办 / 进行中
- **Doc A P2 接线（已回退，2026-10-31）**：用户裁定回退，孤儿脚手架已删除（`sync_gateway.py` / `test_dbx_sync_gateway.py` / `DatasourceDbxBinding` / `sync.py` 接线全移除），`sync.py` 恢复纯直连。新权威方案为 `docs/plans/2026-10-31-embedded-direct-gateway-migration.md`（浏览器直连网关）；同步执行器经 dbx 的方向不再推进。
- `datara-web` 归档重试（解锁后）。
- 1.9 外部核验：8090 入口、禁词抽检、zhangsan E2E、DBX owner 1.9 实测、ECOM_SIM 入库、C7 迁移在 1.9 落库验证。

## 环境改进（已落地）
- 后端守卫固化「proxy/identity 层不得直连用户库原始驱动」方向。
- 前端契约固化「嵌入禁词收口」。
- P2 脚手架固化「仅按 connection_id 执行、绝不携带密码」契约。
