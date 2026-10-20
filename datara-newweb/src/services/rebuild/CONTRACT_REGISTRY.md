# CONTRACT_REGISTRY 契约冻结登记簿

> 建立日期：2026-10-20 ｜ 依据：权威设计 §5.6（契约冻结登记）
> 用途：门 1 API 契约验收直接消费；新增/变更契约文件有测试对应方可合入。
> 最近更新：2026-10-21（增量 1.3-01/02 契约层 11 文件迁移适配落位 + 契约测试落位，Claude 实施线）

## 1. 契约文件 ↔ 测试映射表（11 文件一一对应，无缺口）

| # | 契约文件 | 测试文件 | 状态 | 冻结方法数 | 测试数 | 说明 |
|---|---|---|---|---|---|---|
| 1 | `adapterKit.ts` | `services/rebuild/__tests__/adapterKit.test.ts` | GREEN | 12 导出（4 类型 + 8 运行期原语） | 52 | 共享机械原语（命名映射 / id 归一 / 包络解包 / 错误类型） |
| 2 | `variableApi.ts` | `services/rebuild/__tests__/variableApi.contract.test.ts` | GREEN | 6 | 17 | R2 变量管理（I2） |
| 3 | `dependencyApi.ts` | `services/rebuild/__tests__/dependencyApi.contract.test.ts` | GREEN | 5 | 12 | R4 依赖组件（I4） |
| 4 | `resourceApi.ts` | `services/rebuild/__tests__/resourceApi.contract.test.ts` | GREEN | 5 | 11 | R4 资源上传（I2/I4） |
| 5 | `syncComponentApi.ts` | `services/rebuild/__tests__/syncComponentApi.contract.test.ts` | GREEN | 5（+ `suggestInitialMapping` 纯函数） | 4 | R4 同步组件（I4 SYNC；R3 收口后转 GREEN，已经监督线确认） |
| 6 | `sqlIdeApi.ts` | `services/rebuild/__tests__/sqlIdeApi.contract.test.ts` | GREEN | 12 | 9 | R5-A SQL IDE 只读（I5） |
| 7 | `sqlIdeDdlApi.ts` | `services/rebuild/__tests__/sqlIdeDdlApi.contract.test.ts` | RED | 5 | 2 | R5-B DDL 写路径（I6，待 R5-B 解禁） |
| 8 | `scheduleApi.ts` | `services/rebuild/__tests__/scheduleApi.contract.test.ts` | RED | 5 | 5 | R6 调度（I7，待 T55 解禁） |
| 9 | `metricsApi.ts` | `services/rebuild/__tests__/metricsApi.contract.test.ts` | GREEN | 6 | 15 | R7 统计/质量/血缘（I9） |
| 10 | `streamApi.ts` | `services/rebuild/__tests__/streamApi.contract.test.ts` + `streamApiSurface.contract.test.ts` | GREEN | 6 | 1 + 2 | I8 流处理观摩（旧库同一契约存在 services 级与 views 级两份测试，均落位） |
| 11 | `aiToolsApi.ts` | `services/rebuild/__tests__/aiToolsApi.contract.test.ts`（+ `__tests__/mockAgent.ts` 假 Agent 适配层） | GREEN | 9 | 19 | R8-A AI 八工具（I10；契约层已接线，端到端 LLM 联调受 FV-02 阻塞，归增量 15.4） |

> **状态快照：2026-10-21（1.3 落位实测）；GREEN 9 / RED 2；契约方法合计 64。**
>
> **与设计 §5.6 快照（GREEN 8 / RED 3）的差异**：`aiToolsApi.ts` 实测为 **GREEN**——源码无 `NOT_WIRED` 活哨兵，`createAiToolsContract()` 发起真实 API 调用（`requestJson` → `fetch`），旧库 `bannerConsistency.contract.test.ts` 断言亦为 GREEN。设计 §5.6 快照系提交 `6c0de0c`（验证域契约 GREEN 化）之前的状态。**建议监督线刷新权威设计 §5.6 快照为 GREEN 9 / RED 2。**

## 2. 包络与底座一致性核对

- **包络 {code,msg,data} 三态**（§5.4 冻结）：
  - `code === 0 / 200 / undefined` → `resolve(data)`；
  - `code ≠ 0 / 200`（业务错误）→ `throw ContractApiError{httpStatus, code, msg, raw?}`；
  - 非 2xx（系统错误）→ 调用方解包前抛错。
- `adapterKit.unwrapEnvelope` 为冻结结论共享原语，全域统一（含 RED 契约接线时沿用）。
- **http 底座共享**：所有 GREEN 契约文件 `import { getToken } from '../http'`；单 BASE `'/api/v1'`。
  - 实测：`variableApi/dependencyApi/resourceApi/syncComponentApi/sqlIdeApi/metricsApi/streamApi` 共用 `getToken`；`aiToolsApi` 共用 `getToken` + `BASE`；`sqlIdeDdlApi/scheduleApi` 为 RED 哨兵（零 import）；`adapterKit` 自洽零 import。
  - 全库扫描：新库 `src/` 无 `LEGACY_BASE`、无 `8000` 端口残留（红线 1 / §7.1）。

## 3. CI 门禁说明

- **门禁规则**：新增/变更契约文件（`src/services/rebuild/*.ts`）须有对应测试文件并全绿方可合入。
- **契约冻结登记**：每契约文件冻结时登记提交号 + 测试文件 + 状态（见 §4）。
- **基线**：`npm test`（= `vitest run`）全量绿。

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
| `sqlIdeDdlApi.ts` | 待登记 | `__tests__/sqlIdeDdlApi.contract.test.ts` | RED | 2026-10-21 |
| `scheduleApi.ts` | 待登记 | `__tests__/scheduleApi.contract.test.ts` | RED | 2026-10-21 |
| `metricsApi.ts` | 待登记 | `__tests__/metricsApi.contract.test.ts` | GREEN | 2026-10-21 |
| `streamApi.ts` | 待登记 | `__tests__/streamApi.contract.test.ts` + `__tests__/streamApiSurface.contract.test.ts` | GREEN | 2026-10-21 |
| `aiToolsApi.ts` | 待登记 | `__tests__/aiToolsApi.contract.test.ts` | GREEN | 2026-10-21 |

> 提交号由监督线代提交后回填（本包 `.git` 只读，改动全部在工作区）。
