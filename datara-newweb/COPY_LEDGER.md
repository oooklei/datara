# COPY_LEDGER 复制登记台账

> 建立日期：2026-10-20 ｜ 依据：权威设计 §2.3（复制准入条件）
> 用途：登记旧前端/旧代码复制准入全量记录；每个被复制文件必须登记。
> 最近登记：2026-10-21（增量 1.3-01 契约层 11 文件迁移适配，Claude 实施线）

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
| 4 | `datara-web/src/services/rebuild/resourceApi.ts` | `datara-newweb/src/services/rebuild/resourceApi.ts` | §3.3 C 组「资源管理」／对标 I2+I4／承载域 resources | L2 | 整文件复制 + **1 处载体适配（3 行级改动）**：`base64ToBlob(base64):Blob` → `base64ToFile(base64,filename):File`、`new Blob([bytes])` → `new File([bytes], filename)`、`form.append('file', base64ToBlob(...), request.filename)` → `form.append('file', base64ToFile(request.contentBase64, request.filename))`。成因为 happy-dom 下 `FormData.append(blob, filename)` 不采纳 filename 实参（`diff --strip-trailing-cr` 实证仅此 3 hunk）；vitest `resourceApi.contract.test.ts` 11 passed |
| 5 | `datara-web/src/services/rebuild/syncComponentApi.ts` | `datara-newweb/src/services/rebuild/syncComponentApi.ts` | §3.3 C 组「同步任务」／对标 I4(SYNC)／承载域 sync | L2 | 整文件复制零改写；vitest `syncComponentApi.contract.test.ts` 4 passed |
| 6 | `datara-web/src/services/rebuild/sqlIdeApi.ts` | `datara-newweb/src/services/rebuild/sqlIdeApi.ts` | §3.3 D 组「SQL IDE 只读」／对标 I5／承载域 sql_ide | L2 | 整文件复制零改写；vitest `sqlIdeApi.contract.test.ts` 9 passed |
| 7 | `datara-web/src/services/rebuild/sqlIdeDdlApi.ts` | `datara-newweb/src/services/rebuild/sqlIdeDdlApi.ts` | §3.3 D 组「SQL IDE DDL」／对标 I6／承载域 rb | L2 | 整文件复制零改写；vitest `sqlIdeDdlApi.contract.test.ts` 2 passed（RED 哨兵，待 R5-B 解禁） |
| 8 | `datara-web/src/services/rebuild/scheduleApi.ts` | `datara-newweb/src/services/rebuild/scheduleApi.ts` | §3.3 B 组「调度管理」／对标 I7／承载域 workflow.schedule | L2 | 整文件复制零改写；vitest `scheduleApi.contract.test.ts` 5 passed（RED 哨兵，待 T55 解禁） |
| 9 | `datara-web/src/services/rebuild/metricsApi.ts` | `datara-newweb/src/services/rebuild/metricsApi.ts` | §3.3 A 组「工作台」+E 组「指标看板」／对标 I9／承载域 metrics | L2 | 整文件复制零改写；vitest `metricsApi.contract.test.ts` 15 passed |
| 10 | `datara-web/src/services/rebuild/streamApi.ts` | `datara-newweb/src/services/rebuild/streamApi.ts` | §3.3 C 组「流数据处理」／对标 I8／承载域 stream | L2 | 整文件复制零改写；vitest `streamApi.contract.test.ts` 1 passed + `streamApiSurface.contract.test.ts` 2 passed |
| 11 | `datara-web/src/services/rebuild/aiToolsApi.ts` | `datara-newweb/src/services/rebuild/aiToolsApi.ts` | §3.3 H「AI 悬浮助手」／对标 I10／承载域 ai_bridge | L2 | 整文件复制零改写；vitest `aiToolsApi.contract.test.ts` 19 passed（含 `__tests__/mockAgent.ts` 假 Agent 适配落位） |

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
