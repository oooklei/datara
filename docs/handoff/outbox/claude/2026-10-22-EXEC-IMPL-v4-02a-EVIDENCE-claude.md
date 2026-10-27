# EVIDENCE_READY · IMPL-v4-02a（B 组前端收口 02a 段）

- **提交席**：Execution（claude）｜**载体**：claude-lane-loop-executor
- **票据**：IMPL-v4-02a（P1/P1，DELIVERY）｜**派单票**：`outbox/flow/fl-dispatch-impl-v4-02a.json`（event v3-0041-dispatch-assigned-impl-v4-02a）
- **授权**：USER_EXPLICIT_INSTRUCTION（v3-0035 Ops 转达：02a 指名派 claude）
- **纪元/水位**：epoch 3 / RUNNING / `v3-0045-lease-request-rt-impl-v4-03-c-group`
- **提交时间**：2026-10-22｜**完成链定位**：EVIDENCE_READY（本地段）→ ENV_VERIFIED（Integration 租约）→ PASS（Acceptance）→ Flow 集成窗提交

---

## 0. 结论摘要

| 维度 | 结论 |
|---|---|
| 路径核验 | **6/6 全部实存**（均工作区未跟踪新件） |
| 本机静态校验 | **vue-tsc -b EXIT 0**；**tsc --noEmit -p tsconfig.node.json EXIT 0**；**NO_SECRET 预检 0 实际命中** |
| sshNode 域契约对齐（FE↔BE） | **10/10 PASS** |
| 组件接线 | **5/5 落位**（含菜单/路由/宿主单实例） |
| 边界张力 | **1 项（B-1）**：NodeConfigPanel.vue 对 02b 路径 `datasourceApi.ts` 的编译期依赖 → 已报 Ops 候裁 |
| 附带发现 | **F-3**（后端 ssh_node 迁移死码，02a 路径外）、**F-4**（CONTRACT_REGISTRY 缺 sshNodeApi 行，02a 路径外） |
| 1.9 段 | 租约请求已提交（见 §7），**回执前不进 1.9 执行** |

---

## 1. 票据面复核（paths / acceptance / 停票规则）

- **paths（6）**：`datara-newweb/src/services/rebuild/sshNodeApi.ts`、`datara-newweb/src/views/SshNodeManagementView.vue`、`datara-newweb/src/views/ResourceManagementView.vue`、`datara-newweb/src/components/NodeConfigPanel.vue`、`datara-newweb/src/components/ScheduleDialog.vue`、`datara-newweb/src/views/system/`
- **acceptance**：sshNode 域契约测试 + 本机静态校验 + 1.9 端到端 GREEN（sshNode 域）
- **evidence_requirements**：契约测试记录 + 本机静态校验输出（vue-tsc/tsc + NO_SECRET 预检 0 实际命中）+ 1.9 e2e 证据（经 Integration 租约）
- **停票/边界规则**：02a/02b 路径互斥无交叠；对 datasourceApi/rolePermissions 的编译期依赖经 Ops 路由 Decision（D0-D2）处置，不静默扩边；02a paths 不含 `datara-newweb/e2e/`；本机=静态/类型/逻辑稽核，1.9 须先取得租约回执；无 commit、无 push

---

## 2. 路径核验（6/6 PASS）

| # | 路径 | 实存 | 规模 | git 态 | 判定 |
|---|---|---|---|---|---|
| 1 | `datara-newweb/src/services/rebuild/sshNodeApi.ts` | ✓ | 16 行 | `??` 未跟踪 | PASS |
| 2 | `datara-newweb/src/views/SshNodeManagementView.vue` | ✓ | 19 行 | `??` 未跟踪 | PASS |
| 3 | `datara-newweb/src/views/ResourceManagementView.vue` | ✓ | 136 行 | `??` 未跟踪 | PASS |
| 4 | `datara-newweb/src/components/NodeConfigPanel.vue` | ✓ | 399 行 | `??` 未跟踪 | PASS |
| 5 | `datara-newweb/src/components/ScheduleDialog.vue` | ✓ | 589 行 | `??` 未跟踪 | PASS |
| 6 | `datara-newweb/src/views/system/` | ✓ | `llm-models/LlmModelsView.vue`（437 行）+ `LlmModelFormDialog.vue` | `??` 未跟踪 | PASS |

- **零越界**：本席未新增/修改 02a paths 之外任何文件；未触 02b（datasourceApi.ts / rolePermissions.ts / PermissionMatrixView.vue）代码体。
- **配套测试件（工作区未跟踪，非 02a paths 显式列举，随 02a 交付面收口）**：
  - `src/services/rebuild/__tests__/sshNodeApi.contract.test.ts`（3 用例）
  - `src/views/__tests__/sshNodeManagementView.contract.test.ts`（3 用例）
  - `src/views/__tests__/resourceManagementView.contract.test.ts`（2 用例）
  - `src/components/__tests__/scheduleDialog.contract.test.ts`（15 用例，含 9-05 SKIP 语义）

---

## 3. 本机静态校验输出（本机允许面：类型/静态/逻辑稽核）

| 项 | 命令 | 结果 |
|---|---|---|
| 前端全量类型 | `npx vue-tsc -b` | **EXIT 0**（0 错误） |
| node 工程类型 | `npx tsc --noEmit -p tsconfig.node.json` | **EXIT 0**（0 错误） |
| 密钥预检 | NO_SECRET 正则（sk-/AKIA/PRIVATE KEY/password/api_key/token 字面量）遍历 6 路径 | **0 实际命中**（grep exit 1 = 无匹配） |
| 迁移注册链自洽 | `sshnode/migrations.py` → `GovernanceMigration(revision=v0001_ssh_node_registry, checksum, upgrade, tables=SSH_NODE_TABLES)` | 结构自洽（**挂载缺口见 F-3**） |

- **本机零测试执行**：vitest 单元执行为 1.9 面（TEST-ENVIRONMENT-POLICY 硬边界），本席未在本机跑 `vitest run`。
- 凭据面复核：`sshNodeApi.ts` 无硬编码凭据；`SshNodeManagementView.vue` 凭据仅经 API 回显（R-34 冻结债务，非本席新增）；`ScheduleDialog.vue` / `NodeConfigPanel.vue` 无凭据字段。

---

## 4. sshNode 域契约对齐（FE ↔ BE，10/10 PASS）

后端事实源：`datara-backend/rebuild/sshnode/api.py`（挂载 `/api/v1/rebuild/ssh-nodes`，`app.py` L1107-1108）；服务层 `service.py`；探针 `probe.py`。

| # | 契约项 | FE（sshNodeApi.ts / SshNodeManagementView.vue） | BE（api.py / service.py） | 判定 |
|---|---|---|---|---|
| 1 | list 端点 | `GET /api/v1/rebuild/ssh-nodes` | `@router.get("")` | PASS |
| 2 | create 端点 | `POST /api/v1/rebuild/ssh-nodes` | `@router.post("")` | PASS |
| 3 | update 端点 | `PUT /api/v1/rebuild/ssh-nodes/{id}` | `@router.put("/{node_id}")` | PASS |
| 4 | delete 端点 | `DELETE /api/v1/rebuild/ssh-nodes/{id}` | `@router.delete("/{node_id}")` | PASS |
| 5 | probe 端点 | `POST /api/v1/rebuild/ssh-nodes/{id}/probe` | `@router.post("/{node_id}/probe")` | PASS |
| 6 | 权限矩阵 | `SSH_NODE_PERMISSION_MATRIX = {list:VIEW_ALL, create/update/delete/probe:EDIT_DEFINITION}` | `PERMISSION_MAP` 同构逐字 | PASS |
| 7 | R-34 凭据回显 | `SshNodeRecord.cred` + `[data-cred]` 断言 | `_payload` 原样回 `cred`（冻结安全债务） | PASS（债务冻结） |
| 8 | 错误码 | `SSH_NODE_ERROR_CODES = {invalidToken:1001, permissionDenied:1003, notFound:4101, duplicateName:4102, invalidInput:4103}` | `_error(401,1001)` / `_error(403,1003)` / `SshNodeDomainError(4101/4102/4103)` | PASS |
| 9 | 响应信封 | `{code,msg,data}`（`preserveEnvelopeCode:true`） | `_success` / `_error` 同构 | PASS |
| 10 | probe 载荷 | `SshNodeProbeResult = {ok:boolean; message:string}` | `service.probe` 返回 `{"ok":bool,"message":str}`（**无 mutation/commit**，心跳单写者） | PASS |

- **R2 字面量纪律**：BE 4101/4102/4103 为域内字面量（未 import resp.py），与 FE 常量一致 ✓。
- **权限降级语义**：list=VIEW_ALL 可读、EDIT_DEFINITION 拒绝时列表仍可渲染（FE 用例 2 断言 `data-node-list` 存在 + `role=alert` 提示）✓。

---

## 5. 组件接线核验（5/5 PASS）

| 组件 | 接线 | 锚点 | 判定 |
|---|---|---|---|
| `SshNodeManagementView` | 顶层路由 `/dep/ssh` + 菜单 `dep-ssh` | `src/router/routes.ts`；`src/navigation/menu.ts`（formal, batch inc17, VIEW_ALL） | PASS |
| `ResourceManagementView` | `ProjectSegmentView.vue`（`seg === 'resources'` 分支） | `src/views/ProjectSegmentView.vue` L2/L25 | PASS |
| `NodeConfigPanel` | `WorkflowGraphWorkbench.vue` | L51 import / L455 挂载 | PASS |
| `ScheduleDialog` | `TaskCenterView.vue` 单实例 | L44 import / L398 挂载（9-04 双入口同对话框） | PASS |
| `views/system/llm-models` | 顶层 `/system/llm-models` + 菜单 `llm-config`（future） | `LlmModelsView.vue`（六件套 #1-#6 齐备）+ `LlmModelFormDialog.vue` | PASS |

- **ResourceManagementView 菜单面**：`resource-mgmt` 为 formal 但 `decisionGate: route-frozen-inc10`、**无 path**（「路径待路由契约，增量 10 冻结，此前不显示空壳」）——与组件嵌入 `ProjectSegmentView` 的现态自洽，非缺陷。
- **LLM 面（views/system/，node A 收口）**：`llmApi.ts` 6 端点（list/create/update/remove/testModel/setDefault）逐项对齐 `rebuild/llm/api.py`（GET "" / POST "" / PUT/{id} / DELETE/{id} / PUT/{id}/default / POST/{id}/test）；错误码 1001/1003/4001/4041/4091/4092/5021 与后端 `_error` 一致；**F-1 注释串（DELETE 409/4091→409/4092）已在位**（L110）。

---

## 6. 边界张力（B-1）与附带发现

### B-1（D0-D2 候裁）：02a 路径对 02b 路径的编译期依赖

- **事实**：`datara-newweb/src/components/NodeConfigPanel.vue`（**02a 路径**）L24：
  ```ts
  import { createDatasourceContract } from '../services/rebuild/datasourceApi'
  ```
  `datasourceApi.ts` 属 **02b 路径**（Task 增量 06 §3 / 增量 07 §3）。
- **依赖性质**：**只读消费**——`createDatasourceContract(projectId).listDatasources()` 用于 `srcDs`/`tgtDs` 下拉；加载失败**静默降级**（面板提示、不阻断保存其余字段）。无写路径、无权限面扩张。
- **现状**：`datasourceApi.ts` 已实存（工作区未跟踪），且 `CONTRACT_REGISTRY.md` #16 记为 GREEN（11 端点 / 4 测试）——即依赖**可满足**，02b 实施工作非本依赖的前置。
- **处置**：按票面边界规则，**不静默扩边**，已报 Ops 候 Decision（D0-D2）处置（见 `2026-10-22-EXEC-IMPL-v4-02a-ops-report-boundary-and-findings.md` §B-1）。**本席未修改 `datasourceApi.ts`**。

### F-3（后端，02a 路径外）：`apply_ssh_node_migrations` 死码

- `datara-backend/rebuild/sshnode/migrations.py` L16 定义 `apply_ssh_node_migrations(engine)`；**全仓无调用点**（仅 `tests/rebuild/test_sshnode_migrations.py` 引用）。
- `rebuild_ssh_node` 表经 `Base.metadata.create_all`（`app.py` L318 起 tables 列表含 `SshNodeRecord.__table__`，L41）创建。
- **影响**：`rebuild_schema_migration` 台账**不会**登记 revision `v0001_ssh_node_registry`——与既有 F-2（`apply_runtime_node_migrations` / `apply_execution_migrations` 同类死码）**同型**。
- **处置**：后端文件、**02a 路径外**，报 Ops 归并（见同件 §F-3）。

### F-4（登记簿，02a 路径外）：CONTRACT_REGISTRY 缺 sshNodeApi 行

- `datara-newweb/src/services/rebuild/CONTRACT_REGISTRY.md` 现 18 行，**无 sshNodeApi 条目**；其头部自订「新增/变更契约文件有测试对应方可合入」。
- `sshNodeApi.ts` 为新契约件且**有对应测试**（`sshNodeApi.contract.test.ts`），但未登记 → 门 1 API 契约验收面**不可见**该契约。
- **处置**：`CONTRACT_REGISTRY.md` **02a 路径外**，报 Ops（见同件 §F-4）。

---

## 7. 1.9 段（租约请求已提交，回执前不执行）

- **请求件**：`docs/handoff/outbox/claude/2026-10-22-EXEC-IMPL-v4-02a-lease-request.md`
- **business_key**：`IMPL-v4-02a:REMOTE_TEST:sshnode-domain`
- **请求内容**：① 1.9 vitest 契约测试（sshNodeApi / SshNodeManagementView / ResourceManagementView / ScheduleDialog / llmApi）；② sshNode 域 1.9 端到端（经 `http://192.168.1.9:18091/`，**禁 8090/18090**）
- **排队说明**：1.9 单环境串行；现网有 ACTIVE 租约 `LEASE-IMPL-V4-01-A-GROUP`（lease_until 20:00:00），本请求按其回执规则**自动排队其后**
- **本席在回执前不进 1.9 执行**（TEST-ENVIRONMENT-POLICY §1/§4）

---

## 8. 边界合规声明

- 本轮仅：**只读稽核**（6 路径 + 接线 + 契约对齐）+ **本机静态校验**（vue-tsc / tsc / NO_SECRET 预检）+ **证据件落盘**。
- **未**修改 02a paths 之外任何文件；**未**修改 `datasourceApi.ts` / `rolePermissions.ts` / `PermissionMatrixView.vue`（02b 面）；**未**新增 `datara-newweb/e2e/` 用例件。
- **未**写 STATE / mailbox / 队列投影（Flow 单写）；**未** commit、**未** push（USER_ONLY）。
- **未**加载 / 调用 AOCI（开发期全线停用）。
- **未**在本机执行 vitest 单元测试（1.9 面）。
- 变更留工作区候集成窗 pathspec 圈定。

—— Execution（claude），IMPL-v4-02a EVIDENCE_READY（本地段），1.9 段候租约回执。
