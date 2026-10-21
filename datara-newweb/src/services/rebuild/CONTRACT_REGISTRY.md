# CONTRACT_REGISTRY 契约冻结登记簿

> 建立日期：2026-10-20 ｜ 依据：权威设计 §5.6（契约冻结登记）
> 用途：门 1 API 契约验收直接消费；新增/变更契约文件有测试对应方可合入。
> 最近更新：2026-10-21（16.1 波2：sqlIdeDdlApi 契约转绿——R5-B 五方法接 BE rb 四端点 + R5-A definitions 复用，A7 红线落码；此前 S320 FE-8：SYNC / SQL IDE / STREAM 收编统一 http 信封底座，SCHEDULE 保持业务 RED）

## 1. 契约文件 ↔ 测试映射表

| # | 契约文件 | 测试文件 | 状态 | 冻结方法数 | 测试数 | 说明 |
|---|---|---|---|---|---|---|
| 1 | `adapterKit.ts` | `services/rebuild/__tests__/adapterKit.test.ts` | GREEN | 12 导出（4 类型 + 8 运行期原语） | 52 | 共享机械原语（命名映射 / id 归一 / 包络解包 / 错误类型） |
| 2 | `variableApi.ts` | `services/rebuild/__tests__/variableApi.contract.test.ts` | GREEN | 6 | 17 | R2 变量管理（I2） |
| 3 | `dependencyApi.ts` | `services/rebuild/__tests__/dependencyApi.contract.test.ts` | GREEN | 5 | 12 | R4 依赖组件（I4） |
| 4 | `resourceApi.ts` | `services/rebuild/__tests__/resourceApi.contract.test.ts` | GREEN | 6 | 12 | R4 资源上传/版本下载（I2/I4；R-48） |
| 5 | `syncComponentApi.ts` | `services/rebuild/__tests__/syncComponentApi.contract.test.ts` | GREEN | 5（+ `suggestInitialMapping` 纯函数） | 5 | R4 同步组件；统一 `http.request` 信封与 5 操作权限矩阵 |
| 6 | `sqlIdeApi.ts` | `services/rebuild/__tests__/sqlIdeApi.contract.test.ts` | GREEN | 23 | 9 | R5-A SQL IDE 只读（I5；23 方法对应 24 后端路由，执行状态轮询为独立入口） |
| 7 | `sqlIdeDdlApi.ts` | `services/rebuild/__tests__/sqlIdeDdlApi.contract.test.ts` | GREEN | 5 | 11 | R5-B DDL 写路径 GREEN（16.1 波2）：5 方法接 rb 四端点（validate-policy/preview-impact/confirm/execution-records 全 POST）+ R5-A definitions 复用；A6 权限矩阵冻结；A7 红线（空短语拒发/无样本值/sourceVersion fail-closed）落码 |
| 8 | `scheduleApi.ts` | `services/rebuild/__tests__/scheduleApi.contract.test.ts` | RED（底座策略已登记） | 5 | 6 | R6 调度观测面；5 操作权限矩阵已冻结，业务端点未接线、零 I/O |
| 9 | `metricsApi.ts` | `services/rebuild/__tests__/metricsApi.contract.test.ts` | GREEN | 6 | 15 | R7 统计/质量/血缘（I9） |
| 10 | `streamApi.ts` | `services/rebuild/__tests__/streamApi.contract.test.ts` + `streamApiSurface.contract.test.ts` | GREEN | 6 | 1 + 2 | I8 流处理观摩（旧库同一契约存在 services 级与 views 级两份测试，均落位） |
| 11 | `aiToolsApi.ts` | `services/rebuild/__tests__/aiToolsApi.contract.test.ts`（+ `__tests__/mockAgent.ts` 假 Agent 适配层） | GREEN | 9 | 19 | R8-A AI 八工具（I10；契约层已接线，端到端 LLM 联调受 FV-02 阻塞，归增量 15.4） |
| 12 | `componentSpecApi.ts` | `services/rebuild/__tests__/componentSpecApi.contract.test.ts` | GREEN | 1 | 5 | M1 组件规格例外契约：200 裸 `{items}`、强 ETag、304 空体；刷新失败仅回退最后成功响应，首次失败阻断并可重试 |
| 13 | `monitorApi.ts` | `services/rebuild/__tests__/monitorApi.contract.test.ts` | GREEN | 1 | 4 | B3 集群监控：单一 rebuild 路由；ZK 可用性、心跳三态与指标三态原样透传 |
| 14 | `scheduleCrudApi.ts` | `services/rebuild/__tests__/scheduleCrudApi.contract.test.ts` | GREEN | 7 | 9 | R6 调度 CRUD 拆分（R-22：CRUD 面 GREEN 化；观测面 `scheduleApi.ts` 保持 RED 候增量 8；9-02 GREEN 段收编 695b07a1+9f012e55 两骨架件，含 nextFireTimes 响应面 ScheduleMutationResult） |
| 15 | `workflowApi.ts` | `services/rebuild/__tests__/workflowApi.contract.test.ts` | GREEN | 12 | 20 | FE-6 ① 工作流六模型 12 端点 FE 面（候选池/定义 CRUD/draft 节点边增量写/publish/版本读取 + workflowCategories 目录面 + WF_NODE_TYPES 托盘类型；R-25 差量保存协调器 `workflowSaveQueue.ts` 同批落位） |
| 16 | `datasourceApi.ts` | `services/rebuild/__tests__/datasourceApi.contract.test.ts` | GREEN | 11 | 4 | 10A 正式 rebuild datasource 契约：11 端点逐项映射，项目路径隔离，权限/错误/凭据矩阵冻结（R-47） |
| 17 | `trialApi.ts` | `services/rebuild/__tests__/trialApi.contract.test.ts` | GREEN | 7 | 13 | FE-7 trial 试运行域八能力 FE 面（WBS 4.5）：trialApi 7 方法（snapshot/run/promote×2/runs/output，run 与 run promote 携 snapshot_id）+ `stores/trialRun.ts` + `components/TrialRunPanel.vue` 同批落位 |
| 18 | `rolePermissions.ts` | `services/rebuild/__tests__/rolePermissions.contract.test.ts` | GREEN | 6 导出（2 类型 + 3 常量 + 1 判定函数） | 10 | 15.1-C 权限矩阵冻结快照：四角色 × 32 权限点逐词形逐序固化（权威源 `rebuild/identity/contracts.py` L56-98 ROLE_PERMISSIONS；票面「33 权限点」以后端枚举实际 32 项为准）；后端矩阵漂移即红，强制 15-P0 门 1 同步链 |

> **状态快照：2026-10-21（16.1 波2：#7 sqlIdeDdlApi RED→GREEN，方法数 5 不变；#18 行延续）；GREEN 17 / RED 1；冻结方法合计 133。**
>
> **与设计 §5.6 快照（GREEN 8 / RED 3）的差异**：`aiToolsApi.ts` 实测为 **GREEN**——源码无 `NOT_WIRED` 活哨兵，`createAiToolsContract()` 发起真实 API 调用（`requestJson` → `fetch`），旧库 `bannerConsistency.contract.test.ts` 断言亦为 GREEN。设计 §5.6 快照系提交 `6c0de0c`（验证域契约 GREEN 化）之前的状态。**建议监督线刷新权威设计 §5.6 快照为 GREEN 9 / RED 2。**

## 2. 包络与底座一致性核对

- **包络 {code,msg,data} 三态**（§5.4 冻结）：
  - `code === 0 / 200 / undefined` → `resolve(data)`；
  - `code ≠ 0 / 200`（业务错误）→ `throw ContractApiError{httpStatus, code, msg, raw?}`；
  - 非 2xx（系统错误）→ 调用方解包前抛错。
- `adapterKit.unwrapEnvelope` 为冻结结论共享原语，全域统一（含 RED 契约接线时沿用）。
- **http 底座共享**：所有 GREEN 契约文件通过 `../http` 的 `request`（JSON）或 `requestResponse`（SSE）共享单 BASE、token、超时和信封策略；单 BASE `'/api/v1'`。
  - S320 FE-8 实测：`syncComponentApi/sqlIdeApi/streamApi` 已移除本地 JSON fetch/解包通道；SQL IDE SSE 经 `requestResponse`，不存在认证旁路；`sqlIdeDdlApi/scheduleApi` 为 RED 哨兵、零 I/O，但未来接线权限矩阵已登记且必须使用同一底座。
  - 16.1 波2 实测：`sqlIdeDdlApi` 已移除 RED 哨兵，经同一 `http.request` 底座真实接线（rb 四端点 validate-policy/preview-impact/confirm/execution-records + R5-A definitions 复用）；`scheduleApi` 仍为 RED 哨兵（R6 冻结面零触碰）。
  - 全库扫描：新库 `src/` 无 `LEGACY_BASE`、无 `8000` 端口残留（红线 1 / §7.1）。

## 3. CI 门禁说明

- **门禁规则**：新增/变更契约文件（`src/services/rebuild/*.ts`）须有对应测试文件并全绿方可合入。
- **契约冻结登记**：每契约文件冻结时登记提交号 + 测试文件 + 状态（见 §4）。
- **基线**：`npm test`（= `vitest run`）全量绿。
- **INC4-BE-1 回归**：`npm test -- --run` 全量 **349 passed / 0 failed（34 测试文件）**；`npm run build` 通过（1625 modules transformed）。
- **17.3-01 回归**：`npm test -- --run` 全量 **405 passed / 0 failed（39 测试文件）**；`npm run build` 通过（1629 modules transformed）。
- **9-02 GREEN 段回归**：`vue-tsc -b` 零错；`npx vitest run` 全量 **438 passed / 0 failed（41 测试文件）**；`npm run build` 通过（1634 modules transformed / 770ms）。
- **FE-6 ①②③ 回归**：`vue-tsc -b` 零错；`npx vitest run` 全量 **470 passed / 0 failed（42 测试文件）**（438 基线递增 +32，无退化；FE-6 三件：workflowApi 契约扩容、workflowGraph store 契约新文件、taskCenterView 宿主接驳归真）；`npm run build` 通过（1646 modules transformed / 1.04s）。
- **FE-7 回归**：`vue-tsc -b` 零错；`npx vitest run` 全量 **515 passed / 0 failed（47 测试文件）**（470 基线递增 +45，零退化；其中 FE-7 三件贡献 +38：trialApi 契约 13 / trialRun store 12 / TrialRunPanel 13；其余 +7 为同窗并行线新增件贡献，不在本票报验面）；`npm run build` 通过（863ms）。
- **9-03 回归**：`vue-tsc -b` 零错；`npx vitest run` 全量 **527 passed / 0 failed（48 测试文件）**（515 基线递增 +12，零退化；+12 全为本票 `components/__tests__/scheduleDialog.contract.test.ts`）；`npm run build` 通过（947ms）。本票为组件票（ScheduleDialog.vue 手工模态壳+双视图/cron 即时预览/门链校验/上线/下线），消费已冻结契约 `scheduleCrudApi.ts`（#14），契约面零变更，不新增 §1 行。
- **9-04 回归**：`vue-tsc -b` 零错；`npx vitest run` 全量 **531 passed / 0 failed（48 测试文件）**（527 基线递增 +4，零退化；+4 = `palette.contract.test.ts` +1 行内「定时」入口用例 + `taskCenterView.contract.test.ts` +3 单实例接线用例）；`npm run build` 通过（835ms）。本票为接线票（Palette 行内 `.pt-cron` ⏱ + Workbench 顶栏 `wf-schedule` 双入口 emit schedule → TaskCenterView 单实例 ScheduleDialog 复用打开），消费已冻结契约 `scheduleCrudApi.ts`（#14）与既有组件 `ScheduleDialog.vue`（9-03 件，本票零改动），契约面零变更，不新增 §1 行。
- **9-05 回归**：`vue-tsc -b` 零错；`npx vitest run` 全量 **534 passed / 0 failed（48 测试文件）**（531 基线递增 +3，零退化；+3 全为本票 `scheduleDialog.contract.test.ts` 追加 9-05 describe：闭环链（行内定时→配置→保存→回读）+ SKIP 分支断言（R-05 B 语义）+ 三策略载荷对照）；`npm run build` 通过（867ms）。本票为契约测试票（T9-E 验收锚：调度闭环链「行内定时 → 配置 → 保存 → 回读 → 按策略触发」；SKIP 断言按 R-05 裁定 2026-10-21（B `SCAN_SECONDS` 宽限）落 B 语义实际断言，拆票登记 9-建3 A/B 参数化占位因裁定到达而消解；运行时触发核验归后端 `test_schedule_policies.py`（10 passed）与 1.9 侧 Playwright E2E 票候派），消费已冻结契约 `scheduleCrudApi.ts`（#14）与既有组件 `ScheduleDialog.vue`（9-03 件，本票仅注释收口），契约面零变更，不新增 §1 行。
- **15.1-C 回归**：`npm run build`（`vue-tsc -b && vite build`）通过（零类型错，992ms）；`npx vitest run` 全量 **569 passed / 0 failed（53 测试文件）**（9-05 基线 534/48 递增 +35/+5，零退化；本票贡献 +18：`rolePermissions.contract.test.ts` 10 + `permissionMatrixView.contract.test.ts` 7 + `routes.contract.test.ts` 追加 /sec/perm 绑定断言 1；其余 +17/+3 为同窗并行线新增件贡献，不在本票报验面）。本票交付：`rolePermissions.ts` 冻结矩阵常量（§1 #18 新行）+ `PermissionMatrixView.vue` 只读矩阵页（手写 HTML/CSS，零 element-plus）+ 路由接驳三连锁（`routes.ts` 加 `/sec/perm` + `routes.contract.test.ts` 基线同步 + `menu.ts` sec-perm 补 `routeName:'sec-perm'`）；菜单可见性候批（`BATCH_SWITCHES.inc15` 保持 false，直链 `/sec/perm` 可达，开关置 true 牵扯同批 open-api/open-key/llm-config 渲染行为，候监督线裁定）。
- **16.1 波2 回归**：`npm run build`（`vue-tsc -b && vite build`）通过（零类型错，947ms）；`npx vitest run` 全量 **583 passed / 0 failed（54 测试文件）**（15.1-C 基线 569/53 递增 +14/+1，零退化；本票贡献 +9：`sqlIdeDdlApi.contract.test.ts` 2→11；其余 +5/+1 为同窗并行线新增件贡献，不在本票报验面）。本票交付：`sqlIdeDdlApi.ts` RED→GREEN 重塑（§1 #7）——五方法真实接线（A6 权限矩阵逐字冻结；A7 红线三落点：submitConfirm 空白短语 400 CONFIRM_PHRASE_INVALID 拒发请求、previewImpact 不含样本值、getDefinition 缺 sourceVersion fail-closed 502 SOURCE_VERSION_UNAVAILABLE）+ 11 契约用例（snake 归一/默认分页/RangeError 守卫/409 POLICY_BLOCKED+422 LINEAGE_UNKNOWN typed 转译）。

### 3.1 基线登记（1.3 起步）

| 项 | 值 |
|---|---|
| 设计基线锚 | **≥905 passed**（权威设计 §5.6 / §7.4，旧库 `datara-web` 全量基线；WBS 增量 1 退出标准 #1） |
| 1.3 实际起步基线 | **154 passed / 0 failed / 0 skipped（14 测试文件）** |
| 其中契约测试 | **149 passed（12 测试文件）** |
| 其中骨架/冒烟 | 5 passed（`tests/skeleton.test.ts` 1 + `tests/smoke.test.ts` 4） |
| 构建链 | `npm run build`（`vue-tsc -b && vite build`）✅ 通过（1607 modules transformed） |

**逐文件测试数**（`vitest run --reporter=json` 实测）：

| 测试文件 | 测试数 |
|---|---|
| `src/services/rebuild/__tests__/adapterKit.test.ts` | 52 |
| `src/services/rebuild/__tests__/aiToolsApi.contract.test.ts` | 19 |
| `src/services/rebuild/__tests__/variableApi.contract.test.ts` | 17 |
| `src/services/rebuild/__tests__/metricsApi.contract.test.ts` | 15 |
| `src/services/rebuild/__tests__/dependencyApi.contract.test.ts` | 12 |
| `src/services/rebuild/__tests__/resourceApi.contract.test.ts` | 11 |
| `src/services/rebuild/__tests__/sqlIdeApi.contract.test.ts` | 9 |
| `src/services/rebuild/__tests__/scheduleApi.contract.test.ts` | 5 |
| `src/services/rebuild/__tests__/syncComponentApi.contract.test.ts` | 4 |
| `src/services/rebuild/__tests__/sqlIdeDdlApi.contract.test.ts` | 2 |
| `src/services/rebuild/__tests__/streamApiSurface.contract.test.ts` | 2 |
| `src/services/rebuild/__tests__/streamApi.contract.test.ts` | 1 |
| `tests/smoke.test.ts` | 4 |
| `tests/skeleton.test.ts` | 1 |
| **合计** | **154** |

### 3.2 基线差距说明（提请监督线裁定）

设计基线锚 **905 passed** 为**旧库全量基线**（含视图 / 组件 / 图引擎 / 数据层测试）。增量 1.3 范围**仅为契约层 11 文件迁移适配**（WBS:114 任务包 1.3 明示），且：

- **B3 红线**：旧 `services/*.ts` 数据层禁复制 → 旧库 `src/services/__tests__/*`（约 20 文件）不可迁移；
- **B2 红线**：正式路由零 demo、零验证页 → 旧库 `src/views/**` 验证页/正式页测试不在 1.3 范围（视图迁移归增量 2.x-17.x）；
- 旧库其余测试（`src/graph/**`、`src/stores/**`、`src/components/**`、`src/types/**`）属图引擎/状态层，归后续增量。

**结论**：1.3 起步基线 = **154 passed**；905 基线锚需随增量 2.x-17.x 视图/组件/图引擎迁移递增至达（WBS 增量 1 退出标准 #1 的完全满足归 1.6 CI 门禁接线时点）。**该差距为设计锚与增量范围的结构性差异，非 1.3 实施缺陷，提请监督线确认口径。**

## 4. 冻结记录

| 契约名 | 冻结提交号 | 测试文件 | 状态 | 冻结日期 |
|---|---|---|---|---|
| 1.3 契约层 11 文件（整体迁移落位） | 待监督线代提交（工作区未提交） | 见 §1（12 测试文件） | GREEN 9 / RED 2 | 2026-10-21 |
| `adapterKit.ts` | 待登记 | `__tests__/adapterKit.test.ts` | GREEN | 2026-10-21 |
| `variableApi.ts` | 待登记 | `__tests__/variableApi.contract.test.ts` | GREEN | 2026-10-21 |
| `dependencyApi.ts` | 待登记 | `__tests__/dependencyApi.contract.test.ts` | GREEN | 2026-10-21 |
| `resourceApi.ts` | 待登记 | `__tests__/resourceApi.contract.test.ts` | GREEN | 2026-10-21 |
| `syncComponentApi.ts` | 待登记 | `__tests__/syncComponentApi.contract.test.ts` | GREEN | 2026-10-21 |
| `sqlIdeApi.ts` | 待登记 | `__tests__/sqlIdeApi.contract.test.ts` | GREEN | 2026-10-21 |
| `sqlIdeDdlApi.ts` | 待登记 | `__tests__/sqlIdeDdlApi.contract.test.ts` | GREEN（16.1 波2 转绿） | 2026-10-21 |
| `scheduleApi.ts` | 待登记 | `__tests__/scheduleApi.contract.test.ts` | RED | 2026-10-21 |
| `metricsApi.ts` | 待登记 | `__tests__/metricsApi.contract.test.ts` | GREEN | 2026-10-21 |
| `streamApi.ts` | 待登记 | `__tests__/streamApi.contract.test.ts` + `__tests__/streamApiSurface.contract.test.ts` | GREEN | 2026-10-21 |
| `aiToolsApi.ts` | 待登记 | `__tests__/aiToolsApi.contract.test.ts` | GREEN | 2026-10-21 |
| `componentSpecApi.ts` | 待监督线代提交（工作区未提交） | `__tests__/componentSpecApi.contract.test.ts` | GREEN | 2026-10-21 |
| `monitorApi.ts` | 待监督线代提交（工作区未提交） | `__tests__/monitorApi.contract.test.ts` | GREEN | 2026-10-21 |
| `scheduleCrudApi.ts` | 待监督线代提交（工作区未提交） | `__tests__/scheduleCrudApi.contract.test.ts` | GREEN | 2026-10-21 |
| `workflowApi.ts` | 待监督线代提交（工作区未提交） | `__tests__/workflowApi.contract.test.ts` | GREEN | 2026-10-21 |
| `datasourceApi.ts` | 待监督线代提交（工作区未提交） | `__tests__/datasourceApi.contract.test.ts` | GREEN | 2026-10-21 |
| `trialApi.ts` | 待监督线代提交（工作区未提交） | `__tests__/trialApi.contract.test.ts` | GREEN | 2026-10-21 |
| 15.1-A/B identity 管理面后端契约（/api/v1/rebuild/users 四端点 + /projects/{id}/permissions 查询；信封 {code,msg,data}，码表 1005 last-admin / 1006 disabled / 4092 username 冲突；权威源 `rebuild/identity/contracts.py` ROLE_PERMISSIONS） | 待监督线代提交（工作区未提交） | `datara-backend/tests/rebuild/test_identity_api.py`（15.1 段 9 用例） | GREEN | 2026-10-21 |
| `rolePermissions.ts`（15.1-C 权限矩阵冻结快照：四角色 × 32 权限点，权威源 `rebuild/identity/contracts.py` L56-98） | 待监督线代提交（工作区未提交） | `services/rebuild/__tests__/rolePermissions.contract.test.ts` + `views/__tests__/permissionMatrixView.contract.test.ts` + `router/__tests__/routes.contract.test.ts`（/sec/perm 绑定） | GREEN | 2026-10-21 |
| 16.1 波3 DDL 双轨编辑器 UI（`views/ide/ddl/`：DdlEditorView.vue 容器八步管控面 + SourceDdlEditor/StructuredDdlEditor 双轨互斥 + DdlSnapshotMeta 元信息 + objectSourceKinds 轨则枚举；消费 `sqlIdeDdlApi.ts` 五方法契约，三重闸 fail-closed：edit_definition 角色闸（getDefinition 属 VIEW_ALL 读不拦）/ kind 闸仅 5 API 值 / capability 闸 supported+conditional 放行） | 待监督线代提交（工作区未提交） | `views/ide/ddl/__tests__/ddlEditorView.contract.test.ts`（13 用例执行：双轨互斥 14 类别走查 + table 结构化轨派生 ALTER + 八步 happy path + A7 影响预览无样本值 + capability 拒写/conditional 放行 + viewer 拒写 + 非 API kind 禁链 + SOURCE_VERSION_UNAVAILABLE 呈现） | GREEN | 2026-10-21 |

> 提交号由监督线代提交后回填（本包 `.git` 只读，改动全部在工作区）。15.1-C 前端权限矩阵只读页**已落地**（2026-10-21）：消费上表 15.1 行后端契约与 `rebuild/identity/contracts.py` L56-98 权威矩阵，`rolePermissions.ts`（§1 #18）+ `PermissionMatrixView.vue` + 路由 `/sec/perm` 接驳；菜单可见性候批（inc15 开关保持 false）。
