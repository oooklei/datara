# IMPL-v4-07 领票凭证 · EXEC-2（claude 线 2）

- **席位**：Execution EXEC-2（claude 载体实施线 2）｜epoch 3 / RUNNING｜水位 `v3-0054-lease-until-narrative-realignment`
- **时间**：2026-10-22T18:48+08:00
- **动作**：领取 Flow 已接纳派单票 **IMPL-v4-07**，进入本地实施段

## 一、领票依据（四源一致）

| 源 | 内容 |
|---|---|
| 事件流 `v3-0052-dispatch-assigned-impl-v4-07`（18:47） | `IMPL-v4-07` `READY→ASSIGNED`，`assigned_to: claude`，`ticket_face: outbox/流程/fl-dispatch-impl-v4-07.json` |
| 票面 `fl-dispatch-impl-v4-07.json` | `wip_note`：「EXEC-2（claude 载体线 2）空闲候票，本票落 claude 线后由线内分配承接」 |
| 监督 `ops-triage-exec2-E1E2-P1-C1-v3-0048.md`（18:40）E-2 | 「07 可派至 **EXEC-2**（线 2 空），EXEC-1 续持 02a 至回执闭环，两线互不挤占」；WIP **按线计** |
| 实施 EXEC-1 `EXEC-EXEC1-heartbeat-round2-v3-0054.md`（18:44）§2 | **让渡声明**：「本席照此执行：不领 07、不预读 07 路径，07 归 EXEC-2 承接。EXEC-2 可凭本声明放心领票，无需与本席再行协调」 |

**结论**：流程已接纳（v3-0051 批次 9 → v3-0052 派单）+ 任务已排序（Task 增量 10 §六-1）+ 线内分配唯一（EXEC-1 让渡、EXEC-2 空闲）→ 本席领取，**无重复领票风险**。

## 二、开工前三复核

### 1. paths 实存复核（票面 8 路径）

| 路径 | 状态 |
|---|---|
| `datara-newweb/src/services/rebuild/governanceApi.ts` | **MISS → 新建** |
| `datara-newweb/src/services/rebuild/__tests__/governanceApi.contract.test.ts` | **MISS → 新建** |
| `datara-newweb/src/views/qc/QualityRuleView.vue` | **MISS → 新建**（`src/views/qc/` 目录不存在） |
| `datara-newweb/src/views/qc/QualityTaskView.vue` | **MISS → 新建** |
| `datara-newweb/src/views/__tests__/qualityRuleView.contract.test.ts` | **MISS → 新建** |
| `datara-newweb/src/views/__tests__/qualityTaskView.contract.test.ts` | **MISS → 新建** |
| `datara-newweb/src/router/routes.ts` | EXIST（51 行）→ 仅加 qc 两路由 |
| `datara-newweb/src/navigation/menu.ts` | EXIST（394 行）→ `qc-rule`/`qc-task` 两行 `future→formal` |

### 2. 验收标准复核（票面 7 项）

① `governanceApi` 覆盖 `POST/GET /projects/{id}/quality-rules`、`POST /quality-rules/{rule_id}/run`、`GET /projects/{id}/quality-runs`，包络三态与错误码对齐；② 契约测试 GREEN；③ Playwright 建规则→执行→quality-runs 查询闭环；④ **structural 语义如实**（行级四字段恒 0，不虚构行级结果）；⑤ 菜单 `future→formal` 且无空壳；⑥ 全量 vitest 基线不退化；⑦ 1.9 端到端 GREEN。

### 3. 后端契约实证（票面「后端端点已齐备」核验）

`datara-backend/rebuild/governance/api.py`（router `prefix="/api/v1/rebuild/governance"`）：
- `POST /projects/{project_id}/quality-rules` L1632（201，`EDIT_DEFINITION`）→ `{id, project_id, asset_id, name, expression, severity, enabled, created_at, updated_at}`
- `GET /projects/{project_id}/quality-rules` L1678（`VIEW_ALL`，`page/page_size`）→ `{total, list[]}`
- `GET /projects/{project_id}/quality-runs` L1728（`VIEW_ALL`）→ `{total, list[]}`
- `POST /projects/{project_id}/quality-rules/{rule_id}/run` L1768（201，`EDIT_DEFINITION`）→ `{asset_id, id, rule_id, status, checked_rows, success_rows, failed_rows, skipped_rows, summary, generated_at}`
- 错误码：`4041`（asset/rule not found）、`4091`（重名/disabled/persist failed）、`1003`（permission denied）、`4041`（project not found）
- **structural 口径确认**：L1755-1757 注释 + L1785-1793 实现——`checked_rows/success_rows/failed_rows/skipped_rows` **恒 0**，`summary.engine="structural"`；行级采样需绑定数据源，属后续增量。**前端不得虚构行级结果**（验收 ④）。

### 4. 停票规则复核

- **FE-SHELL 锁**：`routes.ts`/`menu.ts` 本票独占；12（API 页面）须待本票释放后取锁 → 本次仅动 qc 两路由 + 两菜单行，**不触其他路由/菜单项**。
- **REG-LEDGER 锁**：`CONTRACT_REGISTRY.md` **不进入本票可写路径**；台账行以证据包文本交付，由 Integration 集成窗单点追加。
- **本机边界**：只做业务代码稽核、静态校验、类型校验、逻辑稽核、契约测试；**1.9 执行须先取得 Integration 租约回执**（入口固定 18091，禁 8090/18090）；无 commit、无 push（USER_ONLY）；变更留工作区候集成窗 pathspec 圈定。
- **问题路由**：困难/歧义/冲突统一报 Ops，不弹窗找用户。

## 三、本票边界声明

本票 paths 与在飞票零交叠：EXEC-1 的 02a（sshNode 域）、trae 的 03（e2e 基建）、01（llm/runtime_node 域）均不涉 `governanceApi.ts` / `views/qc/` / qc 路由菜单行。**唯一共享面为 FE-SHELL 锁**，由本票独占期内串行修改。

—— Execution EXEC-2（claude）/ 领票完毕，进入本地实施段
