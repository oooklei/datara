# COPY_LEDGER 复制登记台账

> 建立日期：2026-10-20 ｜ 依据：权威设计 §2.3（复制准入条件）
> 用途：登记旧前端/旧代码复制准入全量记录；每个被复制文件必须登记。
> 最近登记：2026-10-23（**17.6 五步迁移⑤下线登记（dq2-T004）**：增量 17 已迁移三项（B3 `api/monitor.py`、B6 `api/runtime_node.py`、P4 `api/sshnode.py`）旧后端处理函数下线登记——旧文件保留在库未删（物理下线候用户授权），新承接证据与三处同步登记（§3 F 组状态列 + 本台账 + CONTRACT_REGISTRY 提交号回填）归档 `docs/increments/evidence/INC17/`；此前 **17.5 P5 D4-B 凭据前端遮罩**：`SshNodeManagementView.vue` 凭据列默认遮罩 `••••••••` + 显式「显示/隐藏」开关 + 编辑弹窗凭据输入默认 `password` + 安全债标注；后端 `rebuild/sshnode/api.py` `_payload` 与契约 `#20` 不动（R-34 冻结原样）；此前 17.3 P2 集群监控域收口：`rebuild/monitor/` + `/dep/monitor` 页面 + `monitorApi.ts` 契约层（承接 #13）+ 路由 `/dep/monitor`→`dep-monitor` 接驳；此前 17.5 P4 SSH 节点域收口：`rebuild/sshnode/` + `/dep/ssh` 页面 + `sshNodeApi.ts` 契约层；此前 17.4 P3 运行节点迁移：`rebuild/runtime_node/` + `/dep/runtime` 页面 + `runtimeNodeApi.ts` 契约层；此前 L18-05 终版核对：增量 1.3 迁移台账 + R-48 resource 版本下载扩展现态）

## 一、登记字段

| 字段 | 说明 |
|---|---|
| 源文件 | 旧前端/旧代码文件路径（如 `datara-web/src/views/TaskCenterView.vue`） |
| 目标文件 | datara-newweb 内目标路径 |
| 功能清单出处 | §3 功能清单行 + 对标出处（I 增量 / 用户裁定 + 日期，§3.4 口径） |
| 复制级别 | L0 / L1 / L2 / L3（见下表） |
| 联调验证证据 | pytest + vitest 契约测试 + 联调冒烟三重验证证据引用 |

## 二、复制分级（§2.3）

| 级别 | 含义 | 允许度 |
|---|---|---|
| L0 语义参考 | 仅参考业务语义，代码全部重写 | 允许 |
| L1 结构借鉴 | 借鉴文件组织与数据流结构，代码重写 | 允许 |
| L2 局部复制 | 复制函数/组件级代码块并适配载体 | 允许，须登记 |
| L3 整页移植 | 复制整页并适配契约层与单 BASE | 允许，须登记 + 联调验证 |

**本包级别判定口径**：增量 1.3 迁移对象为**契约层模块**（`services/rebuild/*`，非 Vue 页面）。
11 文件均为整文件复制 + 载体适配（相对导入路径、单 BASE、测试环境），按 §2.3 归 **L2（复制代码块并适配载体）**；
**L3（整页移植）保留给增量 2.x 的 Vue 页面整页移植**，且 L3 要求的「后端联调验证」在契约层迁移包内不可得（归增量 1.2 http 底座 / 1.5 部署联调）。

## 三、三判据（§2.3，缺一不可）

1. **对标功能清单**：被复制代码对应的功能必须在 §3 功能清单中已登记（有 I0~I11 对标出处与承载域）。
2. **API 一源**：复制后的 API 消费必须指向新后端 `datara-rebuild-api`；旧 `services/*.ts` 数据层一律禁复制。
3. **非全盘照抄**：不得整目录 `cp -r`；须逐文件判定。

## 四、登记记录

| # | 源文件 | 目标文件 | 功能清单出处 | 复制级别 | 联调验证证据 |
|---|---|---|---|---|---|
| 1 | `datara-web/src/services/rebuild/adapterKit.ts` | `datara-newweb/src/services/rebuild/adapterKit.ts` | §5.4 契约层架构共享原语（非用户功能项；承载域=rebuild 全域，10 域 API 复用） | L2 | 整文件复制零改写（`diff` 逐字节一致）；vitest `adapterKit.test.ts` 52 passed；`npm run build`（vue-tsc）通过 |
| 2 | `datara-web/src/services/rebuild/variableApi.ts` | `datara-newweb/src/services/rebuild/variableApi.ts` | §3.3 B 组「变量管理」／对标 I2／承载域 variables | L2 | 整文件复制零改写；vitest `variableApi.contract.test.ts` 17 passed |
| 3 | `datara-web/src/services/rebuild/dependencyApi.ts` | `datara-newweb/src/services/rebuild/dependencyApi.ts` | §3.3 B 组「依赖配置」／对标 I4／承载域 dependency | L2 | 整文件复制零改写；vitest `dependencyApi.contract.test.ts` 12 passed |
| 4 | `datara-web/src/services/rebuild/resourceApi.ts` | `datara-newweb/src/services/rebuild/resourceApi.ts` | §3.3 C 组「资源管理」／对标 I2+I4／承载域 resources | L2 | 初始迁移为整文件复制 + **1 处载体适配（3 行级改动）**：`base64ToBlob(base64):Blob` → `base64ToFile(base64,filename):File`、`new Blob([bytes])` → `new File([bytes], filename)`、`form.append('file', base64ToBlob(...), request.filename)` → `form.append('file', base64ToFile(request.contentBase64, request.filename))`；其后按 R-48 新增受保护的指定版本下载方法（属新后端契约扩展，不是旧代码复制）。vitest `resourceApi.contract.test.ts` 12 passed |
| 5 | `datara-web/src/services/rebuild/syncComponentApi.ts` | `datara-newweb/src/services/rebuild/syncComponentApi.ts` | §3.3 C 组「同步任务」／对标 I4(SYNC)／承载域 sync | L2 | 整文件复制零改写；vitest `syncComponentApi.contract.test.ts` 4 passed |
| 6 | `datara-web/src/services/rebuild/sqlIdeApi.ts` | `datara-newweb/src/services/rebuild/sqlIdeApi.ts` | §3.3 D 组「SQL IDE 只读」／对标 I5／承载域 sql_ide | L2 | 整文件复制零改写；vitest `sqlIdeApi.contract.test.ts` 9 passed |
| 7 | `datara-web/src/services/rebuild/sqlIdeDdlApi.ts` | `datara-newweb/src/services/rebuild/sqlIdeDdlApi.ts` | §3.3 D 组「SQL IDE DDL」／对标 I6／承载域 rb | L2 | 整文件复制零改写；vitest `sqlIdeDdlApi.contract.test.ts` 2 passed（RED 哨兵，待 R5-B 解禁） |
| 8 | `datara-web/src/services/rebuild/scheduleApi.ts` | `datara-newweb/src/services/rebuild/scheduleApi.ts` | §3.3 B 组「调度管理」／对标 I7／承载域 workflow.schedule | L2 | 整文件复制零改写；vitest `scheduleApi.contract.test.ts` 5 passed（RED 哨兵，待 T55 解禁） |
| 9 | `datara-web/src/services/rebuild/metricsApi.ts` | `datara-newweb/src/services/rebuild/metricsApi.ts` | §3.3 A 组「工作台」+E 组「指标看板」／对标 I9／承载域 metrics | L2 | 整文件复制零改写；vitest `metricsApi.contract.test.ts` 15 passed |
| 10 | `datara-web/src/services/rebuild/streamApi.ts` | `datara-newweb/src/services/rebuild/streamApi.ts` | §3.3 C 组「流数据处理」／对标 I8／承载域 stream | L2 | 整文件复制零改写；vitest `streamApi.contract.test.ts` 1 passed + `streamApiSurface.contract.test.ts` 2 passed |
| 11 | `datara-web/src/services/rebuild/aiToolsApi.ts` | `datara-newweb/src/services/rebuild/aiToolsApi.ts` | §3.3 H「AI 悬浮助手」／对标 I10／承载域 ai_bridge | L2 | 整文件复制零改写；vitest `aiToolsApi.contract.test.ts` 19 passed（含 `__tests__/mockAgent.ts` 假 Agent 适配落位） |
| 12 | `datara-backend/api/component_spec.py` + `datara-web/src/stores/componentStore.ts` | `datara-backend/rebuild/component_spec/{service.py,api.py}` + `datara-newweb/src/services/rebuild/componentSpecApi.ts` | §5A.3 组件规格一源／0.6 M1／WBS 4.1 | L1 | 后端业务映射语义迁移到独立只读域，载体改为 TokenService 与 rebuild 路由；前端仅借鉴 ETag/304 缓存流，重写为强 SHA-256 ETag、首次失败阻断、仅最后成功响应回退；pytest `test_component_spec_api.py` + vitest `componentSpecApi.contract.test.ts` |
| 13 | `datara-backend/api/monitor.py` + `datara-web/src/services/graphApi.ts`（`fetchMonitorNodes`） | `datara-backend/rebuild/monitor/{service.py,api.py}` + `datara-newweb/src/services/rebuild/monitorApi.ts` | §3 F 组「集群监控」／0.6 P2／WBS 17.3 | L1 | 业务聚合次序和降级语义照抄，载体适配为 rebuild SSH 表、TokenService 及 `/api/v1/rebuild/monitor/nodes`；pytest `test_monitor_api.py` + vitest `monitorApi.contract.test.ts`，红线扫描零命中 |
| 14 | `datara-backend/api/runtime_node.py`（P3 运行节点；B6）+ `datara-web/src/views/deploy/DeployRuntimeView.vue`（M16 语义参考，非契约来源） | `datara-backend/rebuild/runtime_node/{service.py,api.py,models.py,sftp.py,migrations.py,revisions/v0001_runtime_node_registry.py}` + `datara-newweb/src/services/rebuild/runtimeNodeApi.ts` + `datara-newweb/src/views/depops/RuntimeNodeView.vue` | §3 F 组「运行节点」／0.6 P3／WBS 17.4 | L1 | 后端 list 九字段语义 + `/{id}/ls` 目录优先/500 条截断 + 凭据（auth/password）零回吐 + 4101/4002/5002 码表照抄，载体适配为 rebuild_runtime_node 表、TokenService 及 `/api/v1/rebuild/runtime-nodes` 信封；前端为**新建组件**消费冻结契约（非旧页复制）；pytest `test_runtime_node_api.py` 9 passed + vitest `runtimeNodeApi.contract.test.ts` 7 + `runtimeNodeView.contract.test.ts` 7（路由 `/dep/runtime` 接驳经 `routes.contract.test.ts`） |
| 15 | `datara-backend/api/sshnode.py`（P4 SSH 节点；I4）+ `datara-web` SSH 节点管理视图语义（L0 语义参考，非契约来源） | `datara-backend/rebuild/sshnode/{service.py,api.py,models.py,probe.py,migrations.py,revisions/v0001_ssh_node_registry.py}` + `datara-newweb/src/services/rebuild/sshNodeApi.ts` + `datara-newweb/src/views/SshNodeManagementView.vue` | §3 F 组「SSH 节点」／0.6 P4／WBS 17.5 | L1 | 后端五端点语义（list 九字段载荷 / create / update / delete / `/{id}/probe` + 4101/4102/4103 码表 + `PERMISSION_MAP` list=VIEW_ALL、create/update/delete/probe=EDIT_DEFINITION）照抄，载体适配为 rebuild_ssh_node 表、TokenService 及 `/api/v1/rebuild/ssh-nodes` 信封；R-34 迁移期凭据全量回吐语义**显式冻结**（前端不遮罩）；前端为**新建组件**消费冻结契约（非旧页复制）；pytest `test_sshnode_api.py` + `test_sshnode_migrations.py` + vitest `sshNodeApi.contract.test.ts` 3 + `sshNodeManagementView.contract.test.ts` 3（路由 `/dep/ssh` 接驳经 `routes.contract.test.ts`） |

**契约测试落位（1.3-02，同包登记）**：

| # | 源测试文件 | 目标测试文件 | 复制级别 | 适配 |
|---|---|---|---|---|
| T1 | `datara-web/src/services/rebuild/__tests__/adapterKit.test.ts` | `datara-newweb/src/services/rebuild/__tests__/adapterKit.test.ts` | L2 | 零改写（`../adapterKit` 相对路径天然兼容） |
| T2 | `datara-web/src/views/rebuild/validation/variable/variableApi.contract.test.ts` | `datara-newweb/src/services/rebuild/__tests__/variableApi.contract.test.ts` | L2 | 导入路径 `'../../../../services/rebuild/variableApi'`→`'../variableApi'` |
| T3 | `datara-web/src/views/rebuild/validation/dependency-form/dependencyApi.contract.test.ts` | `datara-newweb/src/services/rebuild/__tests__/dependencyApi.contract.test.ts` | L2 | 同上（dependencyApi） |
| T4 | `datara-web/src/views/rebuild/validation/resource-upload/resourceApi.contract.test.ts` | `datara-newweb/src/services/rebuild/__tests__/resourceApi.contract.test.ts` | L2 | 同上（resourceApi） |
| T5 | `datara-web/src/views/rebuild/validation/sync-form/syncComponentApi.contract.test.ts` | `datara-newweb/src/services/rebuild/__tests__/syncComponentApi.contract.test.ts` | L2 | 同上（syncComponentApi） |
| T6 | `datara-web/src/views/rebuild/validation/metrics/metricsApi.contract.test.ts` | `datara-newweb/src/services/rebuild/__tests__/metricsApi.contract.test.ts` | L2 | 同上（metricsApi） |
| T7 | `datara-web/src/views/rebuild/validation/sql-ide-readonly/sqlIdeApi.contract.test.ts` | `datara-newweb/src/services/rebuild/__tests__/sqlIdeApi.contract.test.ts` | L2 | 同上（sqlIdeApi） |
| T8 | `datara-web/src/views/rebuild/validation/sql-ide-ddl/sqlIdeDdlApi.contract.test.ts` | `datara-newweb/src/services/rebuild/__tests__/sqlIdeDdlApi.contract.test.ts` | L2 | 同上（sqlIdeDdlApi） |
| T9 | `datara-web/src/views/rebuild/validation/schedule/scheduleApi.contract.test.ts` | `datara-newweb/src/services/rebuild/__tests__/scheduleApi.contract.test.ts` | L2 | 同上（scheduleApi） |
| T10 | `datara-web/src/services/rebuild/streamApi.contract.test.ts` | `datara-newweb/src/services/rebuild/__tests__/streamApi.contract.test.ts` | L2 | 导入路径 `'./streamApi'`→`'../streamApi'` |
| T11 | `datara-web/src/views/rebuild/validation/stream/streamApi.contract.test.ts` | `datara-newweb/src/services/rebuild/__tests__/streamApiSurface.contract.test.ts` | L2 | 导入路径适配（streamApi）；旧库同一契约存在 services 级与 views 级两份测试，均落位 |
| T12 | `datara-web/src/views/rebuild/validation/ai-assistant/aiToolsApi.contract.test.ts` | `datara-newweb/src/services/rebuild/__tests__/aiToolsApi.contract.test.ts` | L2 | 导入路径适配（aiToolsApi）；`'./mockAgent'` 随 T13 同落位 |
| T13 | `datara-web/src/views/rebuild/validation/ai-assistant/mockAgent.ts` | `datara-newweb/src/services/rebuild/__tests__/mockAgent.ts` | L2 | 导入路径适配（aiToolsApi / adapterKit）；R8-B 假 Agent 测试适配层（无 LLM） |

## 五、B3 数据层零复制核验（1.3-01 验收锚）

- 旧数据层 `datara-web/src/services/*.ts`（22 文件：alertApi/apiMode/baselineApi/baselineSpec/componentApi/componentSpec/datasourceApi/eventBus/featureFlags/graphApi/http/ideApi/indApi/index/lineageApi/metaApi/modelApi/runEventSource/streamApi/syncApi/templateApi/types）**零复制**。
- 新库 `datara-newweb/src/services/` 仅 `http.ts`（1.1 新建 8 行最小壳，非旧 85 行 http.ts 的复制，`diff` 实证 DIFFERENT）+ `rebuild/`（本包 1.3 迁移）。
- 符号级扫描：新库 `src/` 无旧数据层符号 import；无 `8000` / `LEGACY_BASE` 残留。
- 旧库同名 `services/streamApi.ts`（数据层）未进入新库；新库 `services/rebuild/streamApi.ts` 为契约层，路径不同、来源不同。

## 六、未落位（本包范围外，登记备查）

| 项 | 源 | 未落位原因 | 归属 |
|---|---|---|---|
| `bannerStatus.ts` + `bannerConsistency.contract.test.ts` | `datara-web/src/services/rebuild/` | FE-02 横幅一致性断言依赖 10 个验证页 `.vue`（B2 零验证页，本包不迁移）；`bannerStatus.ts` 为视图层词表非契约层 | 增量 2.x 视图迁移时随验证页退役一并处置 |

## 七、FE-MERGE-B3 视图资产纳入（2026-10-26）

源根（只读）：`D:\需求\数据治理工具\Datara`。下列 SHA-256 均按 D 盘源文件原始字节计算。

| # | 源相对路径 | 目标相对路径 | 源 SHA-256 | 功能清单出处 / 处置 | 复制级别 | 验证证据 |
|---|---|---|---|---|---|---|
| B3-1 | `datara-newweb/src/components/FilterPanel.vue` | `datara-newweb/src/components/FilterPanel.vue` | `c98efea23e70d661cf7bc2f7291383f5cf6d6a0c897b699bd858c8c9a8029a80` | §3 E 数据治理组共享筛选承载；消费接线后续批次 | L2 | `.codex-evidence/FE-MERGE-B3/` |
| B3-2 | `datara-newweb/src/components/VariableManagementDialog.vue` | `datara-newweb/src/components/VariableManagementDialog.vue` | `10602372f54ccba3ab0172b767dafa4a0fcc3875c464c2b1eb2e89e21569bfe5` | §5A.5 / §5B 变量管理；消费接线后续批次 | L2 | `.codex-evidence/FE-MERGE-B3/` |
| B3-3 | `datara-newweb/src/views/GovernanceHubView.vue` | `datara-newweb/src/views/GovernanceHubView.vue` | `df2091148cd9bc002936ad2fd9f758ccb3ce5fb06f646b2e8f4ebcdd5a9ffa24` | §3 E 数据治理组八页签；接入项目 `meta` 段 | L3 | `.codex-evidence/FE-MERGE-B3/` |
| B3-4 | `datara-newweb/src/views/qc/QualityAlarmView.vue` | `datara-newweb/src/views/qc/QualityAlarmView.vue` | `059c0076644285ee86bf95a323e99edd2b10123f0f1e51f01f8b510423f9afd5` | §4.3 质量扩展组 | L3 | `.codex-evidence/FE-MERGE-B3/` |
| B3-5 | `datara-newweb/src/views/qc/QualityExceptionView.vue` | `datara-newweb/src/views/qc/QualityExceptionView.vue` | `534c056aa0505b450c91ea2fb766f96e13e294e558f559b2fda19b0c0efec319` | §4.3 质量扩展组 | L3 | `.codex-evidence/FE-MERGE-B3/` |
| B3-6 | `datara-newweb/src/views/qc/QualityReportView.vue` | `datara-newweb/src/views/qc/QualityReportView.vue` | `5c1104d50c966b960bfad3db999bf342398ebdc7ae93bb2f669ea485716becb8` | §4.3 质量扩展组 | L3 | `.codex-evidence/FE-MERGE-B3/` |
| B3-7 | `datara-newweb/src/views/sec/AccessAuditView.vue` | `datara-newweb/src/views/sec/AccessAuditView.vue` | `89d1e53234b19bd91750092171c0f3c2ca1f68172c8dc0703a67898b59144dd9` | §3 G 系统管理安全审计承载；路由待 B5 | L3 | `.codex-evidence/FE-MERGE-B3/` |
| B3-8 | `datara-newweb/src/views/open/ApiManagementView.vue` | `datara-newweb/src/views/open/ApiManagementView.vue` | `16925350462374fb4ab3d8c04ecf724c5c3d3b117b8b4357f5174b9e4c826898` | §3.3 G API 管理；路由待 B5 | L3 | `.codex-evidence/FE-MERGE-B3/` |
| B3-9 | `datara-newweb/src/views/open/ApiKeyManagementView.vue` | `datara-newweb/src/views/open/ApiKeyManagementView.vue` | `9a057e9977f28193fe468cb7c01294907f5da0a3fac75474a0e8428ab4141919` | §3.3 G API-Key 管理；路由待 B5 | L3 | `.codex-evidence/FE-MERGE-B3/` |
| B3-10 | `datara-newweb/src/views/system/llm-models/LlmModelsView.vue` | `datara-newweb/src/views/system/llm-models/LlmModelsView.vue` | `2d25fe7b4f0940fa6522b03a40a4f05d2a898da5c3b09da3099aee703892b4a9` | §5E.3 LLM 模型配置目录；路由待 B5 | L3 | `.codex-evidence/FE-MERGE-B3/` |
| B3-11 | `datara-newweb/src/views/system/llm-models/LlmModelFormDialog.vue` | `datara-newweb/src/views/system/llm-models/LlmModelFormDialog.vue` | `8f9e017ffd50991a3a1a12d929db4bdbd8370b36447153be37712e0989465962` | §5E.3 LLM 模型表单；由 B5 页面消费 | L2 | `.codex-evidence/FE-MERGE-B3/` |
| B3-T1 | `datara-newweb/src/views/__tests__/projectSegmentView.contract.test.ts` | `datara-newweb/src/views/__tests__/projectSegmentView.contract.test.ts` | —（测试已按目标端资源默认值适配，不按源原件复制） | 治理中心项目段接线契约；保留目标资源页“全部类型”默认值 | L2 | RED/GREEN 见同目录日志 |

归一说明：WBS 增量 10 指定 `src/views/resources/**` 为资源管理承载，路由继续唯一消费 `views/resources/ResourceManagementView.vue`；未纳入 D 盘重复的根级 `views/ResourceManagementView.vue`。`NodeConfigPanel.vue` 三方核对后保留目标端 fail-closed 身份覆盖顺序，未以 D 盘原件覆盖。上述页面仅消费 `services/rebuild/**`，未纳入旧 `services/*.ts` 或 demo/mock 数据层。B3 只纳入资产；`open/**`、`sec/**`、`system/llm-models/**` 的路由归一与消费接线属于 FE-MERGE-B5 待办，`FilterPanel.vue` 与 `VariableManagementDialog.vue` 的实际消费也留给 B4/B5，不在本批冒称完成。

## FE-MERGE-B4 三方并集（2026-10-26）

源根（只读）：`D:\需求\数据治理工具\Datara`。以下 SHA-256 均为 D-WIP 原始字节；目标以当前 HEAD 的 rebuild API、权限和时序契约为基线，经逐文件核对后吸收令牌化、三段布局、表格/抽屉/页签和新增交互，不引入旧 `services/*.ts` 或 demo/mock 数据。

| 批次 | 相对路径（源=目标） | D-WIP SHA-256 | 并集说明 |
|---|---|---|---|
| B4-01 | `datara-newweb/src/views/meta/AssetMapView.vue` | `818cbbaf740c54834dde6b0e02a9caff8a129c9740a355c153324f14e3724916` | 保留资产 API；吸收统计、分组视图、跳转与请求序号守卫 |
| B4-02 | `datara-newweb/src/views/meta/LineageAnalysisView.vue` | `b8c8005bb1f67af8f3ee6e8fbf1ac6cf915f782542d7fdb314047474bade09b6` | 保留血缘 API；吸收方向/深度控制、详情布局与双请求守卫 |
| B4-03 | `datara-newweb/src/views/meta/MetadataCatalogView.vue` | `70c425d7b043725d1db4259c1508a82f142773fb7602096bb7f588551589840a` | 保留资产列表/详情 API；吸收筛选、详情抽屉和并发守卫 |
| B4-04 | `datara-newweb/src/views/meta/TagManagementView.vue` | `683b6b73de73be4cd4035165034bbb359ef1d3efde8b501b6653f6cf9ab9863b` | 保留标签创建/绑定 API；吸收筛选、解绑交互与请求守卫 |
| B4-05 | `datara-newweb/src/views/ind/ConsistencyCheckView.vue` | `6b90a749b2bc424088d811f4fae58965e06fb8d72871c17211efb4f18ae17fc7` | 保留一致性检查 API；新增结果抽屉、指标跳转与双请求守卫 |
| B4-06 | `datara-newweb/src/views/ind/IndicatorBoardView.vue` | `385a7fdcfa54dbcf1936169a18150f6e1483ff8c36894d68f0cea9cf0e14dc09` | 保留指标 API；新增列表/一致性入口与请求守卫 |
| B4-07 | `datara-newweb/src/views/ind/IndicatorListView.vue` | `1aa945811180bde7b689f51bf89dc50c3641a73de0e7744852bd4d5ce0c7cc44` | 保留指标创建 API；吸收筛选、抽屉式创建与请求守卫 |
| B4-08 | `datara-newweb/src/views/qc/QualityRuleView.vue` | `979eb43230dd4028214d611c0b8d0e04f6b50d0dab22302958dd8d3ebf9d5e3c` | 保留规则创建/运行 API 与运行记录跳转；吸收令牌化布局 |
| B4-09 | `datara-newweb/src/views/qc/QualityTaskView.vue` | `2ff6ad84a8ede4713380a47d66e178b784aaac68ca6eccd8f5613e093b8cf20d` | 保留质量运行列表 API；吸收筛选及状态展示 |
| B4-10 | `datara-newweb/src/views/std/StandardManagementView.vue` | `080014f8b574379c978d5a1fff134f28a027ef6b1bbe6013b84526a1972e6fcd` | 保留标准创建/检查 API；吸收筛选、抽屉、结果页签与双请求守卫 |
| B4-11 | `datara-newweb/src/views/depops/MonitorView.vue` | `0d38bc57a13c5367d3e823c0b41d9a8177e0b678f06ecadce292d3f36776e562` | 保留监控契约；吸收令牌化状态面板 |
| B4-12 | `datara-newweb/src/views/depops/RuntimeNodeView.vue` | `5df86bb229a1bb55d9325df1c36bec71494920e0c87bb549ce843c6f90ddf67b` | 保留运行节点与目录浏览契约；吸收三段布局和状态样式 |
| B4-13 | `datara-newweb/src/views/datasource/DataSourceListView.vue` | `d0cd4605f51b3a5b95f12bbc66b94d1c34c86c4c19ccba3468b79c2ce2c3ddbd` | 保留数据源 CRUD/探测/元数据 API；吸收令牌化主从布局 |
| B4-14 | `datara-newweb/src/views/PermissionMatrixView.vue` | `b064d2893cc3a6e0f6a5d72d1eb94c3fab9fcbcd50d7c55e2d8e6b7950e0df77` | 保留权限矩阵逻辑；仅吸收设计令牌 |
| B4-15 | `datara-newweb/src/views/ProjectMembersView.vue` | `3c8ccd5e7f12c0ac2fc0f16a3dde28c3eba4d24b6aa1fecb941633e27b4e8a7e` | 保留成员 API 与权限行为；仅吸收设计令牌 |
| B4-16 | `datara-newweb/src/views/ProjectWorkbenchView.vue` | `b95a447382c7ffceb91d3db96e64f87fa7c46b1575dd6840daa580519909dce0` | 保留指标契约和菜单导航；吸收设计令牌 |
| B4-17 | `datara-newweb/src/views/SshNodeManagementView.vue` | `c10dad023160537d80b0032e6df8d164f619dbe3ac1e4e00ff2adaf01c8e31de` | 保留 SSH CRUD/探测与后端回吐契约；前端默认掩码并显式揭示 |
| B4-T1 | `datara-newweb/src/views/__tests__/consistencyCheckView.contract.test.ts` | `4d6e8d78defccfae336dfac9fdcb474b77afcad65182627df3c92ad25f2f60bf` | 新增结果抽屉与指标跳转契约 |
| B4-T2 | `datara-newweb/src/views/__tests__/indicatorBoardView.contract.test.ts` | `08b845dad509a02ac88061ea24afa204587b70b66981e969ff0974282912f698` | 新增双入口导航契约 |
| B4-T3 | `datara-newweb/src/views/__tests__/sshNodeManagementView.contract.test.ts` | `712b8f6abfb0b3d7fc55d99482d38a971848fc31730a9b98d5a08fc0b386ad50` | 新增凭据默认掩码与编辑器显隐契约 |

## FE-MERGE-B5 冲突件并集（2026-10-26）

源根（只读）：`D:\需求\数据治理工具\Datara`。下列 SHA-256 均为 D-WIP 原始字节；目标端没有机械覆盖，而是在当前安全、鉴权和竞态契约上做语义并集。

| 批次 | 源相对路径 | D-WIP SHA-256 | 目标处置 / 并集说明 |
|---|---|---|---|
| B5-01 | `datara-newweb/src/services/rebuild/syncComponentApi.ts` | `58bb6b1b22974adee919cf549f3842f0882397280dde5d35331cf2fbfee66cda` | 吸收共享 `http.request`、`preserveEnvelopeCode` 与五操作权限矩阵；保留 `SyncApiError` 领域错误、诊断透传、15 秒超时和内存 token 底座。 |
| B5-T1 | `datara-newweb/src/services/rebuild/__tests__/syncComponentApi.contract.test.ts` | `83714a54150c9b256b439f4163ef345aa2dee947ee6c28d73a242bbaf8b6aeac` | 吸收权限面断言并强化为五个操作逐项精确映射；原请求路径、载荷、token 与诊断测试全部保留。 |
| B5-02 | `datara-newweb/src/views/ide/IdeView.vue` | `bc0f72f9a9828f140d06c64da576fc112e8b3c03f6903c40ce1227dd2ed0a437` | 保留变量校验、现时值预览、补全、SQL 编辑执行和 metadata 请求序号守卫；仅将页内硬编码色值归一为 r6 共享主题令牌。 |
| B5-03 | `datara-newweb/src/router/routes.ts` | `2d4ca5c799834ce2a77d665aacef0ab23755090bec7288289d5a3d0a5131a88c` | 保留现有路由集合与守卫边界；按用户裁定将 `/open/llm` 绑定 `views/system/llm-models/LlmModelsView.vue`、`/sec/audit` 绑定 `views/sec/AccessAuditView.vue`。两正本源文件 SHA 已登记于 B3-7/B3-10。 |

B5 新增/调整的 IDE、路由与 B3 消费合同测试为目标端验证代码，不冒充 D-WIP 原件；RED/GREEN、全量测试、类型检查和差异核验见 `.codex-evidence/FE-MERGE-B5/implementation/`。

## FE-MERGE-B6 测试资产筛选纳入（2026-10-26）

源根（只读）：`D:\需求\数据治理工具\Datara`。以下 SHA-256 为 D-WIP 原始字节；目标测试保留业务闭环，但按现行安全裁定移除 localStorage token 注入，统一改为应用已有 `__DATARA_TEST_TOKEN__` 一次性内存通道与请求期鉴权头。生成物、报告和证据目录仅加忽略规则，不纳入仓库。

| 批次 | 源相对路径 | D-WIP SHA-256 | 目标处置 / 筛选说明 |
|---|---|---|---|
| B6-01 | `datara-newweb/playwright.config.ts` | `03fc2b3da96cac415008fd3a1c82c0601f1cd2d8b7b165da2e2118096f28a801` | 保留 1.9/18091、单 worker、零重试；删除持久化 token 叙述，不启动本机 webServer |
| B6-02 | `datara-newweb/e2e/llm-models.spec.ts` | `e3a90e8a93d843d08d5f878d9332dd04f2d94794f68d9491c0c1c3348a5eda89` | 保留配置/掩码/连通性/删除闭环；路由归一为 `/open/llm`；凭据仅运行时存在 |
| B6-03 | `datara-newweb/e2e/qc.spec.ts` | `07ee38ff192135a7295d3df5ade5f7bd95296bc3e8b994111553c21dac3666ea` | 保留规则创建、structural 运行与项目上下文跳转；移除浏览器持久化读取 |
| B6-04 | `datara-newweb/e2e/sshNode.spec.ts` | `c80d71d6459ea4989dc8c3d3443fb9718972d2d5575b08dc760b788457666bf2` | 保留创建、凭据遮罩、探测与删除；移除浏览器持久化读取 |
| B6-05 | `datara-newweb/deploy/DEPLOY-1.9.md` | `f962a4746833db3fb09b755893acf84aa06f883bc52241f3bba543ec67809a4b` | 收敛为 1.9 隔离部署、SCP、短时内存鉴权与证据边界，清除旧本机运行口径 |
| B6-T1 | 目标新增 `datara-newweb/e2e/support/auth.ts` | —（目标安全适配） | 登录 token 不入 URL/静态产物/报告/浏览器存储；document-start 内存注入后由应用消费并删除 |

明确排除：`playwright-report/**`、`test-results/**`、`playwright.config.js`、`playwright.config.d.ts`、`e2e/**/*.js`、`e2e/**/*.d.ts`、`e2e/evidence/**`；对应精确规则见 `datara-newweb/.gitignore`。
