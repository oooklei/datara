# 契约冻结登记簿（FE-02 交付物）

> 建立日期：2026-10-19 ｜ 依据：WBS FE-02 契约测试基线收口与 CI 门禁接线
> 用途：G 组门 1 验收（FE-13）直接消费；新增/变更契约文件有测试对应方可合入。

## 1. 契约文件 ↔ 测试映射表（11 文件一一对应，无缺口）

| # | 契约文件 | 测试文件 | 状态 | 说明 |
|---|---|---|---|---|
| 1 | `adapterKit.ts` | `services/rebuild/__tests__/adapterKit.test.ts` | GREEN | 共享机械原语（命名映射/id 归一/包络解包/错误类型） |
| 2 | `variableApi.ts` | `views/rebuild/validation/variable/variableApi.contract.test.ts` | GREEN | R2 统一变量，6 方法接线 |
| 3 | `dependencyApi.ts` | `views/rebuild/validation/dependency-form/dependencyApi.contract.test.ts` | GREEN | R4 依赖组件，5 方法接线 |
| 4 | `resourceApi.ts` | `views/rebuild/validation/resource-upload/resourceApi.contract.test.ts` | GREEN | R4 资源上传 |
| 5 | `syncComponentApi.ts` | `views/rebuild/validation/sync-form/syncComponentApi.contract.test.ts` | GREEN | R4 同步组件表单，5 方法接线（FE-09 前置改写：工作流版本域数据可用性） |
| 6 | `sqlIdeApi.ts` | `views/rebuild/validation/sql-ide-readonly/sqlIdeApi.contract.test.ts` | GREEN | R5-A SQL IDE 只读，16 方法（FE-07a 拆分登记） |
| 7 | `sqlIdeDdlApi.ts` | `views/rebuild/validation/sql-ide-ddl/sqlIdeDdlApi.contract.test.ts` | RED | R5-B DDL 写路径（FE-07b 拆分登记，待 R5-B D 阶段解禁） |
| 8 | `scheduleApi.ts` | `views/rebuild/validation/schedule/scheduleApi.contract.test.ts` | RED | R6 调度运行时，待工作流域建模（FE-08 补登 alarm 页签 Alert 落位） |
| 9 | `metricsApi.ts` | `views/rebuild/validation/metrics/metricsApi.contract.test.ts` | GREEN | R7 统计质量血缘 |
| 10 | `streamApi.ts` | `views/rebuild/validation/stream/streamApi.contract.test.ts` | GREEN | R8 流处理观摩，6 方法接线（FE-10 调用方换绑目标，头注释已修正） |
| 11 | `aiToolsApi.ts` | `views/rebuild/validation/ai-assistant/aiToolsApi.contract.test.ts` | RED | R8-A AI 八工具，待 LLM 端点解阻 |

## 2. 包络与底座一致性核对（FE-01 收口确认）

- **包络 {code,msg,data} 三态**：GREEN 接线期 9 契约层实证固化，`adapterKit.unwrapEnvelope` 纯函数为冻结结论共享原语（成功 code=0/200/undefined → data；业务错误 code≠0/200 → ContractApiError；系统错误非 2xx → 调用方解包前抛错）。
- **http 底座共享**：variableApi / dependencyApi / resourceApi / metricsApi / sqlIdeApi 均 `import { getToken } from '../http'`；rebuild 域无 mock 分支（apiMode='mock' 时正式 demo 页走 `services/mock/seed.ts`，rebuild 域隔离）。
- **adapterKit 原语使用**：variableApi（camelToSnake/snakeToCamel/ContractApiError）、dependencyApi（+ID_NORMALIZATION_FAILED）、resourceApi、metricsApi（+wireIdToString）；RED 骨架 3 文件（sqlIdeDdlApi / scheduleApi / aiToolsApi）未接线，不使用底座（正常）；FE-01 修订后 syncComponentApi / streamApi 已转 GREEN 并接入底座。

## 3. CI 门禁说明

- **基线**：`npm test`（= `vitest run`）全量绿，当前 905 passed（896 基线 + 9 包络三态新增）。
- **门禁规则**：新增/变更契约文件（`src/services/rebuild/*.ts`）须有对应测试文件（`*.contract.test.ts` 或 `__tests__/*.test.ts`）并全绿方可合入。
- **契约冻结登记**：每契约文件冻结时登记提交号 + 测试文件 + 状态（见上表）。
- **包络语义冻结**：`unwrapEnvelope` 三态语义（成功/业务错误/系统错误）已冻结，全域统一；RED 契约文件接线时沿用同一原语。

## 4. 冻结记录

| 契约名 | 冻结提交号 | 测试文件 | 状态 | 冻结日期 |
|---|---|---|---|---|
| adapterKit | 0b1a4be | adapterKit.test.ts | GREEN | 2026-10-19 |
| variableApi | — | variableApi.contract.test.ts | GREEN | — |
| dependencyApi | — | dependencyApi.contract.test.ts | GREEN | — |
| resourceApi | — | resourceApi.contract.test.ts | GREEN | — |
| metricsApi | — | metricsApi.contract.test.ts | GREEN | — |
| sqlIdeApi | — | sqlIdeApi.contract.test.ts | GREEN | — |
| syncComponentApi | — | syncComponentApi.contract.test.ts | GREEN | 2026-10-19 |
| sqlIdeDdlApi | — | sqlIdeDdlApi.contract.test.ts | RED | — |
| scheduleApi | — | scheduleApi.contract.test.ts | RED | — |
| streamApi | — | streamApi.contract.test.ts | GREEN | 2026-10-19 |
| aiToolsApi | — | aiToolsApi.contract.test.ts | RED | — |
