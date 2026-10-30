# CONTRACT_REGISTRY 契约冻结登记簿

> 建立日期：2026-10-20 ｜ 依据：权威设计 §5.6（契约冻结登记）
> 用途：门 1 API 契约验收直接消费；新增/变更契约文件有测试对应方可合入。
> 最近更新：2026-10-27（三轮收编并集：#22 governanceApi 20→24（质量批 B 写侧 disposeException/createReport/createAlarmPolicy/setAlarmPolicyEnabled）+ 新增 #36 aiAgentApi（R8-B 对话链）；GREEN 36 / 冻结方法合计 220）；2026-10-27（AI Agent 对话链收口：新增 aiAgentApi；aiToolsApi 显式接入递归 camel↔snake 映射）；2026-10-26（M3 统一核验 + 契约登记表收口：#28 modelApi 方法数 8→22（A6-1~A6-22 全量）/测试 1+视图→3+9 视图；§1 新增 #33/#34/#35（M2a 数仓建模四视图 9、M2b API 管理双视图 3、M2c 质量批 B 三视图 10、网关端点 G 后端 8），GREEN 32→35、冻结方法合计 201→215；§3 增本次回归基线 vitest 854 passed/102 文件 + vue-tsc EXIT=0 + build EXIT=0；§4 增 M2b 网关端点 / M2c 质量 run 端点 / M2d D-08+D-09 三行）；2026-10-26（T5 变量三要求收口：#31 variableReferenceField 获**首个 UI 消费方**——`views/ide/IdeView.vue` 以 surfaceId=ide.sql-editor 登记 SQL 编辑器输入位，显式校验按钮 + completeVariables 补全面板接入，落位提交 0d76ba93）；2026-10-25（契约实态校正：scheduleApi、openapiAdminApi 与 workflow categories/tags 均已由统一 HTTP 底座接线现有后端；旧 NOT_WIRED 常量仅作兼容标记，不再是活哨兵）

## 1. 契约文件 ↔ 测试映射表

| # | 契约文件 | 测试文件 | 状态 | 冻结方法数 | 测试数 | 说明 |
|---|---|---|---|---|---|---|
| 1 | `adapterKit.ts` | `services/rebuild/__tests__/adapterKit.test.ts` | GREEN | 12 导出（4 类型 + 8 运行期原语） | 52 | 共享机械原语（命名映射 / id 归一 / 包络解包 / 错误类型） |
| 2 | `variableApi.ts` | `services/rebuild/__tests__/variableApi.contract.test.ts` | GREEN | 6 | 17 | R2 变量管理（I2） |
| 3 | `dependencyApi.ts` | `services/rebuild/__tests__/dependencyApi.contract.test.ts` | GREEN | 5 | 12 | R4 依赖组件（I4） |
| 4 | `resourceApi.ts` | `services/rebuild/__tests__/resourceApi.contract.test.ts` | GREEN | 6 | 12 | R4 资源上传/版本下载（I2/I4；R-48） |
| 5 | `syncComponentApi.ts` | `services/rebuild/__tests__/syncComponentApi.contract.test.ts` | GREEN | 5（+ `suggestInitialMapping` 纯函数） | 5 | R4 同步组件；统一 `http.request` 信封与 5 操作权限矩阵 |
| 6 | `sqlIdeApi.ts` | `services/rebuild/__tests__/sqlIdeApi.contract.test.ts` | ARCHIVED（2026-10-29） | 23 | 9 | dbx 统一后已无运行时消费者；源码与契约测试见 `docs/archive/2026-10-29-dbx-unified-retirement/`。原 R5-A SQL IDE 记录仅作追溯。 |
| 7 | `sqlIdeDdlApi.ts` | `services/rebuild/__tests__/sqlIdeDdlApi.contract.test.ts` | GREEN | 5 | 11 | R5-B DDL 写路径 GREEN（16.1 波2）：5 方法接 rb 四端点（validate-policy/preview-impact/confirm/execution-records 全 POST）+ R5-A definitions 复用；A6 权限矩阵冻结；A7 红线（空短语拒发/无样本值/sourceVersion fail-closed）落码 |
| 8 | `scheduleApi.ts` | `services/rebuild/__tests__/scheduleApi.contract.test.ts` | GREEN | 5 | 6 | R6 调度观测面 GREEN（2026-10-25 更正）：5 方法经 `request()` 真实接线后端 rebuild/schedule；`R6_SCHEDULER_NOT_WIRED` 仅作 View 横幅兼容常量保留（`@deprecated`），非活哨兵；旧 RED 注释与实现体不一致已修正；`scheduleCrudApi.ts`（#14）同域 CRUD 面已 GREEN，两处契约互补 |
| 9 | `metricsApi.ts` | `services/rebuild/__tests__/metricsApi.contract.test.ts` | GREEN | 6 | 15 | R7 统计/质量/血缘（I9） |
| 10 | `streamApi.ts` | `services/rebuild/__tests__/streamApi.contract.test.ts` + `streamApiSurface.contract.test.ts` | GREEN | 6 | 1 + 2 | I8 流处理观摩（旧库同一契约存在 services 级与 views 级两份测试，均落位） |
| 11 | `aiToolsApi.ts` | `services/rebuild/__tests__/aiToolsApi.contract.test.ts`（+ `__tests__/mockAgent.ts` 假 Agent 适配层） | GREEN | 9 | 20 | R8-A AI 八工具（I10；注册表驱动八工具 UI + 七个非 SQL 生产 handler + 递归 camel↔snake 信封映射） |
| 12 | `componentSpecApi.ts` | `services/rebuild/__tests__/componentSpecApi.contract.test.ts` | GREEN | 1 | 5 | M1 组件规格例外契约：200 裸 `{items}`、强 ETag、304 空体；刷新失败仅回退最后成功响应，首次失败阻断并可重试 |
| 13 | `monitorApi.ts` | `services/rebuild/__tests__/monitorApi.contract.test.ts` | GREEN | 1 | 4 | B3 集群监控：单一 rebuild 路由；ZK 可用性、心跳三态与指标三态原样透传 |
| 14 | `scheduleCrudApi.ts` | `services/rebuild/__tests__/scheduleCrudApi.contract.test.ts` | GREEN | 7 | 9 | R6 调度 CRUD 拆分（R-22：CRUD 面 GREEN 化；观测面 `scheduleApi.ts` 保持 RED 候增量 8；9-02 GREEN 段收编 695b07a1+9f012e55 两骨架件，含 nextFireTimes 响应面 ScheduleMutationResult） |
| 15 | `workflowApi.ts` | `services/rebuild/__tests__/workflowApi.contract.test.ts` | GREEN | 12 | 20 | FE-6 ① 工作流六模型 12 端点 FE 面（候选池/定义 CRUD/draft 节点边增量写/publish/版本读取 + workflowCategories 目录面 + WF_NODE_TYPES 托盘类型；R-25 差量保存协调器 `workflowSaveQueue.ts` 同批落位） |
| 16 | `datasourceApi.ts` | `services/rebuild/__tests__/datasourceApi.contract.test.ts` | GREEN | 11 | 4 | 10A 正式 rebuild datasource 契约：11 端点逐项映射，项目路径隔离，权限/错误/凭据矩阵冻结（R-47） |
| 17 | `trialApi.ts` | `services/rebuild/__tests__/trialApi.contract.test.ts` | GREEN | 7 | 13 | FE-7 trial 试运行域八能力 FE 面（WBS 4.5）：trialApi 7 方法（snapshot/run/promote×2/runs/output，run 与 run promote 携 snapshot_id）+ `stores/trialRun.ts` + `components/TrialRunPanel.vue` 同批落位 |
| 18 | `rolePermissions.ts` | `services/rebuild/__tests__/rolePermissions.contract.test.ts` | GREEN | 6 导出（2 类型 + 3 常量 + 1 判定函数） | 10 | 15.1-C 权限矩阵冻结快照：四角色 × 32 权限点逐词形逐序固化（权威源 `rebuild/identity/contracts.py` L56-98 ROLE_PERMISSIONS；票面「33 权限点」以后端枚举实际 32 项为准）；后端矩阵漂移即红，强制 15-P0 门 1 同步链 |
| 19 | `runtimeNodeApi.ts` | `services/rebuild/__tests__/runtimeNodeApi.contract.test.ts` | GREEN | 2 | 7 | 17.4 P3 运行节点（B6）：单一 rebuild 路由 `/api/v1/rebuild/runtime-nodes`（list 九字段载荷 + `/{id}/ls` 目录浏览，目录优先 + 500 条截断）；权限矩阵 `VIEW_ALL` 冻结；凭据（auth/password）零回吐（契约层 + 后端 `_payload` 双重断言）；领域错误 4101/4002/5002 经 `ContractApiError` 转译 |
| 20 | `sshNodeApi.ts` | `services/rebuild/__tests__/sshNodeApi.contract.test.ts` | GREEN | 5 | 3 | 17.5 P4 SSH 节点（I4）：单一 rebuild 路由 `/api/v1/rebuild/ssh-nodes` 五端点（list/create/update/delete + `/{id}/probe`）；`SSH_NODE_PERMISSION_MATRIX` 冻结（list=VIEW_ALL，create/update/delete/probe=EDIT_DEFINITION）；`SSH_NODE_ERROR_CODES` 冻结（1001/1003/4101/4102/4103）；权限错误 1003 经 `ContractApiError` 保码转译；R-34 凭据回显语义**显式冻结**（迁移期全量回吐，前端不遮罩） |
| 21 | `views/ide/IdeView.vue` | `views/__tests__/ideView.contract.test.ts` | ARCHIVED（原 GREEN） | 23（消费 `sqlIdeApi.ts` #6） | 7 | 增量 11/R5-A 数据开发 IDE 只读态页面：对象树/查询执行(SSE)/结果网格分页/历史/变量引用/脚本/导出；消费已冻结契约 `sqlIdeApi.ts`（#6，23 方法）+ `datasourceApi.ts`（#16）+ `variableApi.ts`（#2）；路由 `/ide` 接驳经 `routes.contract.test.ts`；菜单可见性候批（`BATCH_SWITCHES.inc11` 保持 false，直链可达）。**ARCHIVED（2026-10-29）**：项目改为集成 dbx 服务，自研 IDE 视图废弃；已归档至 `docs/archive/2026-10-29-dbx-ide/views/ide/IdeView.vue`、`docs/archive/2026-10-29-dbx-ide/views/__tests__/ideView.contract.test.ts`；历史冻结记录保留，不删除 |
| 22 | `governanceApi.ts` | `services/rebuild/__tests__/governanceApi.contract.test.ts`（12）+ `views/__tests__/lineageAnalysisView.contract.test.ts`、`assetMapView.contract.test.ts`、`metadataCatalogView.contract.test.ts`、`tagManagementView.contract.test.ts`、`standardManagementView.contract.test.ts`、`indicatorListView.contract.test.ts`、`indicatorBoardView.contract.test.ts`、`consistencyCheckView.contract.test.ts`（36）+ `services/rebuild/__tests__/qualityReadViewsApi.contract.test.ts`（2） | GREEN | 24 | 50 | 增量 14 治理域（inc14）：既有 20 方法 + 质量批 B 四个写方法 disposeException/createReport/createAlarmPolicy/setAlarmPolicyEnabled；异常处置、报告快照生成、告警策略创建/启停均走项目权限与统一包络；单一 rebuild 路由 `/api/v1/rebuild/governance`；包络 `{code,msg,data}` 三态 + `preserveEnvelopeCode` 保码透出（1003/4041/4091/4103）；structural 红线保持：规则 run 端点四字段恒 0、`engine` 恒 `structural`，前端不得虚构行级结果；质量报告仅聚合已持久化 quality-runs。 |
| 23 | `authApi.ts` | `services/rebuild/__tests__/authApi.contract.test.ts` | GREEN | 2 | 5 | I1 登录域：login/logout 两方法直连 `/api/v1/rebuild/login`（UserRecord + verify_password + token 签发，`rebuild/api/app.py` L456-471）；登录态由 LoginView/AppShell 视图层消费；补测 5P（2026-10-24 DEV TDD：anonymous 请求形态/token 落 `datara_token`/401·403 冻结口径 `code=httpStatus` 不解析包络 1.2/logout 本地收敛语义——后端吊销失败不阻断清 token）。补测前缺口「独立契约测试缺位」由 6 契约补登盘点（DEV 2026-10-24）发现，当日闭环 |
| 24 | `llmApi.ts` | `services/rebuild/__tests__/llmApi.contract.test.ts` | GREEN（条件挂载） | 6 | 5 | 15.6 §5E LLM 桥配置面（I10 邻接）：6 方法（list/create/update/remove/testModel/setDefault，`LLM_CONTRACT_METHODS` 单一事实源）+ `LLM_PROVIDERS`（siliconflow/volcengine/longcat——T1 单源对齐 `ai_copilot/config.py`）+ `LLM_ERROR_CODES` 冻结；后端 `rebuild/llm/api.py` 条件挂载（`LLM_ENCRYPTION_KEY` 注入时生效）；端到端 LLM 联调受 FV-02（已解除）后可实测 |
| 25 | `memberApi.ts` | `services/rebuild/__tests__/memberApi.contract.test.ts` | GREEN | 4 | 6 | L3-04 项目成员 RBAC 面：`MEMBER_ROLES` 四角色（admin/developer/operator/viewer）+ 4 方法（listMembers/addMember/removeMember/updateMemberRole）；端点 `rebuild/api/app.py` L1009-1128；包络三态标准信封 |
| 26 | `openapiAdminApi.ts` | `services/rebuild/__tests__/openapiAdminApi.contract.test.ts` | GREEN | 12 | 9 | API 定义、API-Key 与调用日志 12 方法经统一底座接线 `/api/v1/open`；后端 `rebuild/openapi_admin.py` 与 `rebuild/apikey` 已挂载；安全红线保持 hash-only key、one-shot plaintext 与脱敏日志。 |
| 27 | `projectApi.ts` | `services/rebuild/__tests__/projectApi.contract.test.ts` | GREEN | 1 | 5 | L3-02 §5A.11 方案 A 项目域：listProjects 分页面（`ProjectListPage`，active 项目切换入口）；单一 rebuild 路由；包络三态标准信封 |
| 28 | `modelApi.ts` | `services/rebuild/__tests__/modelApi.contract.test.ts`（3）+ `views/__tests__/{modelListView,dwModelDesign,dwModelVersion,dwModelLineage,dwModelEr}.contract.test.ts`（9） | GREEN | 22 | 3 + 9 视图测试 | M2a 扩登：数仓建模模型域 FE 面（增量 16 前置）A6-1~A6-22 共 22 方法（list/dicts/create/update/remove/publish/redraft/ddl/detail/updateFields/listVersions/createVersion/diffVersion/rollbackVersion/getEr/putEr/lineage/impact/physicalize/reverseScan/reverseImport/reverseImportDdl）接 `/rebuild/models` 与 `/rebuild/model-dicts`；5 视图（`/model/list|design|version|lineage|er`→`routes.ts` L70-74）；`ModelRow` 状态机 draft/published/built；T0 补登（落位提交 28a0e5fc） |
| 29 | `executionStatsApi.ts` | `services/rebuild/__tests__/executionStatsApi.contract.test.ts` + `components/__tests__/workflowRunMonitor.contract.test.ts` | GREEN | 2 | 2 + 组件测试 | §5A.10 会议纪要⑨ 运行统计后台表 FE 面：listWorkflowRunStats/getWorkflowRunStat 两函数接 `/rebuild/execution/run-stats`（分页 + 对账明细 detail）；消费方 `components/WorkflowRunMonitor.vue`（TaskCenterView L385 挂载）；T0 补登（落位提交 1fe2a9e3/e5560589/8dc66abc） |
| 30 | `secAuditApi.ts` | `services/rebuild/__tests__/secAuditApi.contract.test.ts` + `views/__tests__/secAuditView.contract.test.ts` | GREEN | 1（`SEC_AUDIT_CONTRACT_METHODS` 冻结） | 1 + 视图测试 | G11 访问审计查询（admin-only）：listAccessLogs 接 `/rebuild/sec/access-logs`；snake→camel 逐字段归一（userName/rowsSeen/requestId/accessedAt）；facets allow/deny 计数透传；消费方 `views/SecAuditView.vue`（路由 `/sec/audit`）；T0 补登（落位提交 28a0e5fc） |
| 31 | `variableReferenceField.ts` | `services/rebuild/__tests__/variableReferenceField.contract.test.ts` | GREEN | 3 导出函数 + 2 冻结常量（纯逻辑契约，零网络） | 11 | L5-04 变量引用输入位消费契约：`VARIABLE_REFERENCE_DIAGNOSTIC_CODES`/`LABELS`（SYNTAX/UNDEFINED/TYPE_MISMATCH/SCOPE_INVISIBLE/CYCLE 五诊断码）+ defineVariableReferenceField（descriptor 冻结校验）/variableReferenceFieldKey（surfaceId:fieldPath 稳定键）/checkVariableReferenceField（显式按钮唯一动作入口，诊断逐项保留）；**UI 消费方（2026-10-26 T5 起）**：`views/ide/IdeView.vue`（surfaceId=ide.sql-editor，fieldPath=sql，校验按钮/补全面板/现时值 previewResolution 三要求齐，0d76ba93）；T0 补登（落位提交 26f2926c） |
| 32 | `workflowSaveQueue.ts` | `services/rebuild/__tests__/workflowSaveQueue.test.ts` | GREEN | R-25 差量保存协调器（store，非 HTTP 契约） | 8 | FE-6 工作流差量保存协调器：draft 节点/边增量写排队与协调；#15 附注件转独立行（T0 补登，落位提交 26f2926c） |
| 33 | `views/open/` API 管理双视图 | `views/__tests__/{apiManagementView,apiKeyManagementView}.contract.test.ts` | GREEN | 视图契约（消费 `openapiAdminApi.ts` #26，零新增方法） | 3 | M2b：`/open/api` 与 `/open/key` 两页（`routes.ts` L65-66）；只读记录面零明文 key（仅 keyPrefix），一次性明文仅 `KeyIssuance.plainKey` |
| 34 | `views/qc/` 质量批 B 三视图 | `views/__tests__/{qualityRuleView,qualityTaskView,qualityReadOnlyView}.contract.test.ts` | GREEN | 视图契约（消费 `governanceApi.ts` #22，零新增方法） | 10 | M2c：`/qc/rule`、`/qc/task`、`/qc/exception|report|alarm` 五路由（`routes.ts` L85-89）；structural 红线（run 四字段恒 0、`engine` 恒 `structural`），前端不虚构行级结果 |
| 35 | `rebuild/openapi_admin.py` 网关端点 G（后端域件，非前端契约文件） | `datara-backend/tests/rebuild/test_openapi_gateway_api.py` | GREEN | 1（`gateway/{api_path:path}`） | 8 | M2b：受控 facade only（禁任意 URL 代理）；fail-closed 5041；路径白名单 + token 校验 |
| 36 | `aiAgentApi.ts` | `services/rebuild/__tests__/aiAgentApi.contract.test.ts` | GREEN | 1 | 2 | R8-B 自研 Agent 对话：项目隔离、默认 LLM fail-closed、工具调用消息原样承接；API key 仅由后端 resolver 消费 |

> **门1 契约实态复核（2026-10-25）**：openapiAdminApi 已接线 `rebuild/openapi_admin.py`/`rebuild/apikey`；workflow categories/tags 已接线 `rebuild/workflow/api.py`；scheduleApi 已接线 rebuild/schedule。当前登记契约无活跃 RED 哨兵。
>
> **状态快照：2026-10-27（三轮收编并集后）**：前端契约层 **GREEN 36 / RED 0**；冻结方法合计 **220**（D 侧 M3 口径 215 + c63c 质量批 B 写侧 governanceApi 4 + aiAgentApi 1）。#33/#34/#35 为 D 侧 M2b/M2c 视图与后端网关行；#36 aiAgentApi 为 c63c R8-B 对话链；#22 governanceApi 20→24（质量批 B 写侧四方法）。八工具执行仍唯一经过 #11 aiToolsApi 统一端点。
>
> **状态图例：ARCHIVED（2026-10-29 新增）**：`ARCHIVED` = 该行契约文件/视图已物理归档至 `docs/archive/`，退出构建与门禁，**不计入 GREEN/RED 计数与冻结方法合计**；登记行保留为历史冻结记录，不删除。当前仅 §1 #21（`views/ide/IdeView.vue` ↔ `ideView.contract.test.ts`，2026-10-29 dbx IDE 集成后自研 IDE 视图废弃）。
>
> **状态快照：2026-10-26（M3 统一核验 + 契约登记表收口，临时实施计划差距 D-01/D-08/D-09 收口）**：前端契约层 **GREEN 35 / RED 0**；冻结方法合计 **215**（187 + modelApi 22 + executionStatsApi 2 + secAuditApi 1 + governanceApi 质量只读 3；variableReferenceField 为纯逻辑契约、workflowSaveQueue 为 store 协调器，不计入 HTTP 方法合计）。§1 更新 #28（modelApi 8→22，测试 1+视图→3+9 视图）；新增 #33（M2b API 管理双视图 3）、#34（M2c 质量批 B 三视图 10）、#35（M2b 网关端点 G 后端 8，后端域件不计入前端方法合计）三行。#33/#34 为视图契约，消费既有契约（#26 openapiAdminApi / #22 governanceApi），零新增 HTTP 方法。
>
> **状态快照：2026-10-25（契约实态校正）**：前端契约层 **GREEN 27 / RED 0**；冻结方法合计 187。
>
> **状态快照：2026-10-24（DEV 18R2-i 补登记：§1 新增 #23~#27 五契约行——authApi GREEN 代码/测试缺位 2 方法、llmApi GREEN 条件挂载 6/5、memberApi GREEN 4/6、openapiAdminApi RED 底座策略 12/9（NOT_WIRED 活哨兵候 15.2-A~D）、projectApi GREEN 1/5；方法合计 +25）**：同日 DEV TDD 补测 #23 authApi 独立契约测试 5P（缺位缺口闭环，测试合计 +5）；2026-10-24（增量 14 治理域：§1 新增 #22 `governanceApi.ts` ↔ 契约测试 12 + 8 视图契约测试 36 = 48 测试，GREEN，冻结方法 17；不新增 rebuild 端点，契约层计数递增 17）；2026-10-24（增量 11/R5-A：§1 新增 #21 视图↔测试映射 `views/ide/IdeView.vue` ↔ `ideView.contract.test.ts`，GREEN 7 测试；不新增契约文件与方法，契约层计数不变）；2026-10-23（17.5 P4：#20 sshNodeApi 新行 GREEN，方法数 5）；GREEN 25 / RED 2；冻结方法合计 182。
>
> **与设计 §5.6 快照（GREEN 8 / RED 3）的差异**：`aiToolsApi.ts` 实测为 **GREEN**——源码无 `NOT_WIRED` 活哨兵，`createAiToolsContract()` 发起真实 API 调用（`requestJson` → `fetch`），旧库 `bannerConsistency.contract.test.ts` 断言亦为 GREEN。设计 §5.6 快照系提交 `6c0de0c`（验证域契约 GREEN 化）之前的状态。**建议监督线刷新权威设计 §5.6 快照为 GREEN 9 / RED 2。**

## 2. 包络与底座一致性核对

- **包络 {code,msg,data} 三态**（§5.4 冻结）：
  - `code === 0 / 200 / undefined` → `resolve(data)`；
  - `code ≠ 0 / 200`（业务错误）→ `throw ContractApiError{httpStatus, code, msg, raw?}`；
  - 非 2xx（系统错误）→ 调用方解包前抛错。
- `adapterKit.unwrapEnvelope` 为冻结结论共享原语，全域统一（含 RED 契约接线时沿用）。
- **http 底座共享**：所有 GREEN 契约文件通过 `../http` 的 `request`（JSON）或 `requestResponse`（SSE）共享单 BASE、token、超时和信封策略；单 BASE `'/api/v1'`。
  - S320 FE-8 实测：`syncComponentApi/sqlIdeApi/streamApi` 已移除本地 JSON fetch/解包通道；SQL IDE SSE 经 `requestResponse`，不存在认证旁路。
  - 16.1 波2 实测：`sqlIdeDdlApi` 已移除 RED 哨兵，经同一 `http.request` 底座真实接线（rb 四端点 validate-policy/preview-impact/confirm/execution-records + R5-A definitions 复用）。
  - 2026-10-25 更正：`scheduleApi.ts` 已 GREEN 化——`createScheduleContract()` 五方法经 `request()` 真实接线后端 rebuild/schedule；`R6_SCHEDULER_NOT_WIRED` 仅作兼容常量保留（`@deprecated`），非活哨兵；旧 RED 注释已修正。
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
- **17.4 P3 回归**（本机诊断，`DIAGNOSTIC_ONLY_NOT_PASS_EVIDENCE`；远程权威基线刷新候 D-INTEG 1.9）：`npx vue-tsc -b` 零错（EXIT=0）；`npx vitest run` 全量 **646 passed / 0 failed（63 测试文件）**（较 16.1 波2 基线 583/54 递增 +63/+9，零退化；本票贡献 +2 新测试文件 `runtimeNodeApi.contract.test.ts` 7 + `runtimeNodeView.contract.test.ts` 7，并改 `routes.contract.test.ts` 增 `/dep/runtime` 绑定断言；其余 +49/+7 为同窗并行线新增件贡献，不在本票报验面）。本票交付：`runtimeNodeApi.ts` 两方法 GREEN（§1 #19 新行）+ `RuntimeNodeView.vue`（九字段节点表 + SFTP 目录浏览，手动刷新）+ 路由 `/dep/runtime`→`dep-runtime` 接驳；后端 `rebuild/runtime_node/`（models/service/sftp/api/migrations/revisions）经 `tests/rebuild/test_runtime_node_api.py` 9 passed 覆盖。
- **17.5 P4 回归**（远程 192.168.1.9 权威证据，lease-dq2-t002-192.168.1.9；日志 `fe-green.log` / `fe-baseline.log` / `fe-tsc.log`）：`npx vue-tsc -b` 零错（EXIT=0）；`npx vitest run` 全量 **642 passed / 0 failed（61 测试文件）**（较 17.4 P3 远程基线 641/61 递增 +1/+0，零退化；本票贡献 +2 新测试文件 `sshNodeApi.contract.test.ts` 3 + `sshNodeManagementView.contract.test.ts` 3，并改 `routes.contract.test.ts` 增 `/dep/ssh` 绑定断言 1）；单域 GREEN **3 文件 24 tests passed**（`sshNodeApi.contract.test.ts` 3 + `sshNodeManagementView.contract.test.ts` 3 + `routes.contract.test.ts` 18）。本票交付：`sshNodeApi.ts` 五方法 GREEN（§1 #20 新行）+ `SshNodeManagementView.vue`（节点表 + 探测 + 全量替换草稿，R-34 凭据回显不遮罩）+ 路由 `/dep/ssh`→`dep-ssh` 接驳；后端 `rebuild/sshnode/`（models/service/probe/api/migrations/revisions）经 `tests/rebuild/test_sshnode_api.py` + `test_sshnode_migrations.py` 覆盖（远程 RED EXIT=2 → GREEN 7 passed，配对证据）。
- **17.3 P2 回归**（远程 192.168.1.9 权威证据，lease-dq2-t003-192.168.1.9；日志 `fe-red.log` / `fe-green.log` / `fe-baseline.log` / `fe-tsc.log` / `be-green.log` / `be-baseline.log`）：`npx vue-tsc -b` 零错（EXIT=0，日志 0 字节）；`npx vitest run` 全量 **643 passed / 0 failed（61 测试文件）**（较 17.5 P4 远程基线 642/61 递增 +1/+0，零退化；本票贡献 +1 新用例 `routes.contract.test.ts` `/dep/monitor` 绑定断言，并新增在飞件 `monitorView.contract.test.ts` 6 + `MonitorView.vue`；单域 GREEN **3 文件 29 tests passed**（`monitorApi.contract.test.ts` + `monitorView.contract.test.ts` 6 + `routes.contract.test.ts`）；**TDD 红证据** `fe-red.log` **2 failed / 27 passed（EXIT=1）**——删 `/dep/monitor` 路由注册后路径断言与绑定用例双双失败，红成立）；后端 `rebuild/monitor/`（api/service）经 `tests/rebuild/test_monitor_api.py` **4 passed**（1.55s）；**BE 全量基线** `be-baseline.log` **7 failed / 1284 passed / 1 skipped（391.33s，EXIT=1）**，失败集与 dq2-T002 基线**逐条一致（`diff` = IDENTICAL_FAILURE_SET）**——7 条全在 `test_execution_models` / `test_identity_api` / `test_identity_token_digest_migration` / `test_sql_ide_route_coverage_matrix`（他线未提交件 + 远端缺 runtime key/挂载），**零 monitor 域回归、零新增失败**。本票交付：`MonitorView.vue`（集群节点表 + 心跳/指标态标签 + 手动刷新 + ZK 源 + 生成时间 + 空态/告警锚点）+ 路由 `/dep/monitor`→`dep-monitor` 接驳（`routes.ts` + `routes.contract.test.ts`）；后端 `rebuild/monitor/`（`__init__`/`api`/`service`）经 `app.py` L1056-1063 `prefix="/api/v1/rebuild/monitor"` 接驳；现状核实结论（已入库/在飞/未开工）入交付包 `delivery-dq2-T003.json`。
- **14 治理域回归**（远程 192.168.1.9 权威证据，lease-inc14-r1-192.168.1.9；日志 `fe-tsc.log` / `fe-green.log` / `fe-governance.log` / `governance-http.log`，证据目录 `/lei/datara-newweb-iso/evidence/inc14-r1/`，node v22.14.0）：`npx vue-tsc -b` 零错（EXIT=0，日志 0 字节）；`npx vitest run` 全量 **713 passed / 0 failed（73 测试文件）**（较前序基线 670/66 递增 +43/+7，零退化；本票贡献 +8 新测试文件 8 视图契约 36 + `governanceApi.contract.test.ts` 5→12 即 +7）；单域 GREEN **9 文件 48 tests passed**（`governanceApi.contract.test.ts` 12：17 方法全覆——质量规则 4 + 资产/标签/血缘/标准/指标/审计 13，包络三态 + `preserveEnvelopeCode` 保码 1003/4041/4091/4103 + camel↔snake 深度转换 + structural 红线四字段恒 0；8 视图契约 36：`lineageAnalysisView`/`assetMapView`/`metadataCatalogView`/`tagManagementView`/`standardManagementView`/`indicatorListView`/`indicatorBoardView`/`consistencyCheckView`，断言 `data-*` 锚点与 mock 调用参数）；**治理域 8 端点 HTTP 实测**（经 18091 → 8001 单源代理，证据 `governance-http.log`）：`projects/8/{assets,standards,metrics,quality-rules,quality-runs,audit}` 六端点 200（载荷 total=11/3/3/5/0/31）+ `assets/1` 200 + `assets/1/lineage?direction=both&depth=3` 200；无 token 对照 **401** `{"code":1001,"msg":"invalid token"}`）。本票交付：`governanceApi.ts` 17 方法契约层（§1 #22 新行，接 rebuild 路由 `/api/v1/rebuild/governance`）+ inc14 meta/std/ind 8 页视图接线；后端域件 `rebuild/governance/`（api/service）归 rebuild-api 侧，前端零双源（§6 一源原则）。
- **M3 统一核验回归**（本机工作树证据，`npx vue-tsc --noEmit -p tsconfig.app.json` EXIT=0）：`npx vitest run` 全量 **854 passed / 0 failed（102 测试文件）**（较 14 治理域远程基线 713/73 递增 +141/+29，零退化；本批 M2a/M2b/M2c/M2d 贡献：modelApi 契约 3 + M2a 四视图 9 + M2b 双视图 3 + M2c 三视图 10 + 其他并行线增量）；`npx vue-tsc --noEmit -p tsconfig.app.json` **EXIT=0**（修复 `modelApi.contract.test.ts` 的 `vi.fn` 参数显式声明，消除 TS2493/TS2740/TS2339）；`npm run build`（`vue-tsc -b && vite build`）**BUILD_EXIT=0**（1807 modules transformed / dist `index-BcBJ7E4G.css` 468.75 kB + `index-BzSf0LoH.js` 1,612.23 kB）；后端 `python -m pytest tests/rebuild -q` **EXIT 0**（日志尾部仅 ZK 重连 warning 噪声，本地无 ZK 属已知基线）。本批交付：M2a modelApi 8→22 + 数仓建模四视图、M2b 网关端点 G + API 管理双视图、M2c 质量批 B 三视图 + run 端点转绿、M2d D-08 ADR 映射表 + D-09 upload 版本化迁移销账。

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
| `scheduleApi.ts` | 待登记 | `__tests__/scheduleApi.contract.test.ts` | GREEN（2026-10-25 更正；createScheduleContract() 五方法经 request() 真实接线；NOT_WIRED 仅兼容常量） | 2026-10-21 |
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
| 17.4 P3 运行节点迁移（`runtimeNodeApi.ts` 两方法 list + ls，接后端 `rebuild/runtime_node/`；配套 `views/depops/RuntimeNodeView.vue` 页面 + 路由 `/dep/runtime` 接驳） | `891c9403`（dq2-T001 后端 15 件，commit-registration-dq2-T001.json；QA dq2-0055 登记） | `services/rebuild/__tests__/runtimeNodeApi.contract.test.ts`（7）+ `views/__tests__/runtimeNodeView.contract.test.ts`（7）+ `router/__tests__/routes.contract.test.ts`（/dep/runtime 绑定） | GREEN | 2026-10-23 |
| 17.5 P4 SSH 节点域收口（`sshNodeApi.ts` 五方法 list/create/update/delete/probe，接后端 `rebuild/sshnode/`；配套 `views/SshNodeManagementView.vue` 页面 + 路由 `/dep/ssh` 接驳） | `7e7e5ff7`（dq2-T002 前端 6 件，commit-registration-dq2-T002.json；后端 `rebuild/sshnode/` 域件入库 `c65096a`） | `services/rebuild/__tests__/sshNodeApi.contract.test.ts`（3）+ `views/__tests__/sshNodeManagementView.contract.test.ts`（3）+ `router/__tests__/routes.contract.test.ts`（/dep/ssh 绑定） | GREEN | 2026-10-23 |
| 17.3 P2 集群监控域收口（承接 #13：前端 `views/depops/MonitorView.vue` 页面 + 路由 `/dep/monitor`→`dep-monitor` 接驳；消费已冻结契约 `monitorApi.ts`（#13，`createMonitorContract().fetchMonitorNodes()`）；后端 `rebuild/monitor/`（api/service）经 `app.py` L1056-1063 `prefix="/api/v1/rebuild/monitor"` 接驳） | `8e8c11d`（dq2-T009 前端 4 件，QA dq2-0067 判 PASS）；后端域件入库 `c65096a`，D-18 wiring 修复 `19ba1ce`（持久分支 `dq2-T003-R1-persist`，QA dq2-0073 判 PASS；均未 push USER_ONLY） | `views/__tests__/monitorView.contract.test.ts`（6）+ `router/__tests__/routes.contract.test.ts`（/dep/monitor 绑定）+ `datara-backend/tests/rebuild/test_monitor_api.py`（4） | GREEN | 2026-10-23 |
| 14 治理域契约层（`governanceApi.ts` 17 方法：资产 list/get/create、标签 create/assign、血缘 create/get、标准 list/create/check、指标 list/create、审计 list、质量规则 listRules/createRule/listRuns/runRule；接 rebuild 路由 `/api/v1/rebuild/governance`；包络 `{code,msg,data}` 三态 + `preserveEnvelopeCode` 保码；`QUALITY_PERMISSION_MATRIX` / `QUALITY_ERROR_CODES` / `QUALITY_STRUCTURAL_ONLY` 冻结；structural 红线 run 四字段恒 0） | `c56189b`（门1 六契约冻结锚点入库：契约+契约测试+8 视图测试+meta/std/ind 8 页面共 23 件整体入库，DEV 2026-10-24，ruling-contract-registry-home 门1 可行动作） | `services/rebuild/__tests__/governanceApi.contract.test.ts`（12）+ 8 视图契约测试（36：`views/__tests__/{lineageAnalysisView,assetMapView,metadataCatalogView,tagManagementView,standardManagementView,indicatorListView,indicatorBoardView,consistencyCheckView}.contract.test.ts`） | GREEN | 2026-10-24 |
| #23 authApi 登录域（login/logout 两方法直连 `/api/v1/rebuild/login`；UserRecord + verify_password + token 签发） | `5051368`（契约测试 5P，18R2-i）+ `c56189b`（authApi.ts 源文件 HEAD 自洽补齐——5051368 已提交测试依赖本源文件，HEAD 上 import 必崩，同日修复） | `services/rebuild/__tests__/authApi.contract.test.ts`（5） | GREEN | 2026-10-24 |
| #24 llmApi LLM 桥配置面（6 方法 + `LLM_CONTRACT_METHODS` 单一事实源 + `LLM_PROVIDERS` + `LLM_ERROR_CODES` 冻结；后端条件挂载） | `c56189b`（llmApi.ts + 契约测试 5P 入库） | `services/rebuild/__tests__/llmApi.contract.test.ts`（5） | GREEN（条件挂载） | 2026-10-24 |
| #26 openapiAdminApi API 管理面（12 方法 + 权限矩阵 + `/api/v1/open`） | `c56189b` + 2026-10-25 实态校正 | `services/rebuild/__tests__/openapiAdminApi.contract.test.ts`（9） | GREEN | 2026-10-25 |
| #25 memberApi 项目成员 RBAC 面（`MEMBER_ROLES` 四角色 + 4 方法 listMembers/addMember/removeMember/updateMemberRole；端点 `rebuild/api/app.py` L1009-1128） | `111f464`（前端三票入库 2026-10-21） | `services/rebuild/__tests__/memberApi.contract.test.ts`（6） | GREEN | 2026-10-24（锚点补登） |
| #27 projectApi 项目域（listProjects 分页面 `ProjectListPage`；单一 rebuild 路由；包络三态标准信封） | `111f464`（前端三票入库 2026-10-21） | `services/rebuild/__tests__/projectApi.contract.test.ts`（5） | GREEN | 2026-10-24（锚点补登） |
| #28 modelApi 数仓建模域（A6-1~A6-22 共 22 方法 + 5 视图 `/model/list|design|version|lineage|er`；M2a 扩登 8→22） | 待监督线代提交（工作区未提交） | `services/rebuild/__tests__/modelApi.contract.test.ts`（3）+ `views/__tests__/{modelListView,dwModelDesign,dwModelVersion,dwModelLineage,dwModelEr}.contract.test.ts`（9） | GREEN | 2026-10-26 |
| #33/#34 M2b/M2c 视图契约批（`/open/api`+`/open/key` 双视图 3；`/qc/rule|task|exception|report|alarm` 五路由三视图 10；消费 #26/#22 零新增方法） | 待监督线代提交（工作区未提交） | `views/__tests__/{apiManagementView,apiKeyManagementView,qualityRuleView,qualityTaskView,qualityReadOnlyView}.contract.test.ts`（13） | GREEN | 2026-10-26 |
| #35 M2b 网关端点 G（后端域件 `rebuild/openapi_admin.py` `gateway/{api_path:path}`；受控 facade only，禁任意 URL 代理；fail-closed 5041） | 待监督线代提交（工作区未提交） | `datara-backend/tests/rebuild/test_openapi_gateway_api.py`（8） | GREEN | 2026-10-26 |
| M2c 质量 run 端点（`rebuild/governance/api.py` quality-runs 转绿；structural 红线四字段恒 0、engine 恒 structural） | 待监督线代提交（工作区未提交） | `services/rebuild/__tests__/governanceApi.contract.test.ts`（含 structural 断言） | GREEN | 2026-10-26 |
| M2d D-08 ADR 映射表 + D-09 upload 版本化迁移销账（`rebuild/component_spec/migrations.py` + `v0002_component_catalog_upload.py` + `scripts/seed_rebuild_component_catalog.py`） | 待监督线代提交（工作区未提交） | `datara-backend/tests/rebuild/test_component_spec_upload_migration.py` | GREEN | 2026-10-26 |

> **六契约 1.9 passed 记录（R-03 口径）**：2026-10-24 HEAD `c56189b` 快照（git archive→scp→/lei/datara-newweb-iso/datara-newweb 解包，node v22.14.0）全量 vitest `Test Files 5 failed | 70 passed (75) / Tests 26 failed | 680 passed (706)`；六契约 72 用例（governance 12+8 视图 36、auth 5、llm 5、openapiAdmin 9（RED 态断言通过）、member 6、project 5）全数含于 680P；26F 与 notice-head-selfconsistency-gaps.json 定性同构（4 个 1.9 工作区残留 untracked 在途测试 + sqlIdeDdlApi 8F=HEAD 测试依赖 http.ts 在途换芯），六契约面零回归。

> 17.6 下线登记（dq2-T004，2026-10-23）提交号回填：17.4=`891c9403`（dq2-T001）、17.5=`7e7e5ff7`（dq2-T002 前端 6 件）、17.3=`8e8c11d`（dq2-T009 前端 4 件）、后端 monitor/sshnode 域件=`c65096a`、D-18 wiring 修复=`19ba1ce`——均经 QA verdict 判 PASS（dq2-0055/0067/0071/0073），未 push（USER_ONLY）。后续新冻结行提交号仍按「监督线代提交后回填」口径执行。15.1-C 前端权限矩阵只读页**已落地**（2026-10-21）：消费上表 15.1 行后端契约与 `rebuild/identity/contracts.py` L56-98 权威矩阵，`rolePermissions.ts`（§1 #18）+ `PermissionMatrixView.vue` + 路由 `/sec/perm` 接驳；菜单可见性候批（inc15 开关保持 false）。
