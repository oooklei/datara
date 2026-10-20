# 契约冻结登记簿

> 用途：G 组门禁验收（FE-13 ~ FE-19）逐门消费的契约冻结登记表。
> 条目格式：契约名 = 冻结提交号 + 测试文件 + 状态。
> 规则：每门验收时，FE 侧动作 = 验收执行 + 冻结令登记（提交号）；「前置依赖」列登记的后端/用户解阻事件不属 FE 实施范围，仅作派发门禁。
> 禁止在解阻前判定门通过。

---

## 一、登记簿条目格式

| 字段 | 说明 |
|---|---|
| 契约名 | 契约标识（如 R2-Variable / R5-A-SqlIde / I8-Stream） |
| 冻结提交号 | 后端契约冻结的 git commit short hash |
| 测试文件 | vitest 契约测试文件路径 |
| 方法数 | 契约方法清单长度 |
| 状态 | FROZEN / GREEN-WIRED / RED-PENDING / BLOCKED |
| 冻结日期 | 契约冻结日期 |
| 验收任务 | 对应 FE-13 ~ FE-19 任务号 |
| 备注 | 关键锚点（如 A5 fc2979e、分页 1..500 等） |

---

## 二、契约条目登记

### 2.1 底座契约

| 契约名 | 冻结提交号 | 测试文件 | 方法数 | 状态 | 冻结日期 | 验收任务 | 备注 |
|---|---|---|---|---|---|---|---|
| adapterKit | — | `datara-web/src/services/rebuild/__tests__/adapterKit.test.ts` | N/A（共享原语） | GREEN | 2026-10-17 | FE-01/FE-02 | §2.1 命名映射 / §2.2 id 归一 / §2.3 包络三态 / §2.4 ContractApiError |

### 2.2 R2 变量契约

| 契约名 | 冻结提交号 | 测试文件 | 方法数 | 状态 | 冻结日期 | 验收任务 | 备注 |
|---|---|---|---|---|---|---|---|
| R2-Variable | — | `datara-web/src/views/rebuild/validation/variable/variableApi.contract.test.ts` | 6 | GREEN-WIRED | 2026-10-17 | FE-16 | 七级优先级链 run>task>workflow>project>global>env>builtin；`VARIABLE_SCOPE_PRIORITY` 冻结 |

### 2.3 R4 依赖契约

| 契约名 | 冻结提交号 | 测试文件 | 方法数 | 状态 | 冻结日期 | 验收任务 | 备注 |
|---|---|---|---|---|---|---|---|
| R4-Dependency | — | `datara-web/src/views/rebuild/validation/dependency-form/dependencyApi.contract.test.ts` | 5 | GREEN-WIRED | 2026-10-17 | FE-15 | upstreamTaskCode string→int 哨兵转换；DEP_* 错误码透出 |

### 2.4 R4 资源契约

| 契约名 | 冻结提交号 | 测试文件 | 方法数 | 状态 | 冻结日期 | 验收任务 | 备注 |
|---|---|---|---|---|---|---|---|
| R4-Resource | — | `datara-web/src/views/rebuild/validation/resource-upload/resourceApi.contract.test.ts` | 5 | GREEN-WIRED | 2026-10-17 | FE-15 | multipart 不手工设 Content-Type；RES_* 错误码透出 |

### 2.5 R4 同步契约

| 契约名 | 冻结提交号 | 测试文件 | 方法数 | 状态 | 冻结日期 | 验收任务 | 备注 |
|---|---|---|---|---|---|---|---|
| R4-Sync | — | `datara-web/src/views/rebuild/validation/sync-form/syncComponentApi.contract.test.ts` | 5 | GREEN-WIRED | 2026-10-17 | FE-13 | SYNC 契约解禁后验收；xfail 门禁处置核对 |

### 2.6 R5-A SQL IDE 只读契约

| 契约名 | 冻结提交号 | 测试文件 | 方法数 | 状态 | 冻结日期 | 验收任务 | 备注 |
|---|---|---|---|---|---|---|---|
| R5-A-SqlIde | fc2979e | `datara-web/src/views/rebuild/validation/sql-ide-readonly/sqlIdeApi.contract.test.ts` | 17 | FROZEN | 2026-10-14 | FE-13 | A5 fc2979e 冻结；分页 1..500 勘误锚定 `sqlIdeApi.ts:409`；`R5A_CONTRACT_METHODS` 17 方法冻结 |

### 2.7 R5-B DDL 契约

| 契约名 | 冻结提交号 | 测试文件 | 方法数 | 状态 | 冻结日期 | 验收任务 | 备注 |
|---|---|---|---|---|---|---|---|
| R5-B-SqlIdeDdl | — | `datara-web/src/views/rebuild/validation/sql-ide-ddl/sqlIdeDdlApi.contract.test.ts` | 5 | RED-PENDING | — | FE-13 | RED 哨兵 `R5B_BACKEND_NOT_WIRED`；待 A5 ddl 后端接线 |

### 2.8 I7 调度契约

| 契约名 | 冻结提交号 | 测试文件 | 方法数 | 状态 | 冻结日期 | 验收任务 | 备注 |
|---|---|---|---|---|---|---|---|
| I7-Schedule | — | `datara-web/src/views/rebuild/validation/schedule/scheduleApi.contract.test.ts` | 5 | RED-PENDING | — | FE-15 | RED 哨兵 `R6_SCHEDULER_NOT_WIRED`；待调度后端接线 |

### 2.9 R7 统计契约

| 契约名 | 冻结提交号 | 测试文件 | 方法数 | 状态 | 冻结日期 | 验收任务 | 备注 |
|---|---|---|---|---|---|---|---|
| R7-Metrics | — | `datara-web/src/views/rebuild/validation/metrics/metricsApi.contract.test.ts` | 6 | GREEN-WIRED | 2026-10-17 | FE-18 | MetricValue 透传不加工；runId wireIdToString 归一 |

### 2.10 I8 流契约

| 契约名 | 冻结提交号 | 测试文件 | 方法数 | 状态 | 冻结日期 | 验收任务 | 备注 |
|---|---|---|---|---|---|---|---|
| I8-Stream | — | `datara-web/src/views/rebuild/validation/stream/streamApi.contract.test.ts` | 6 | GREEN-WIRED | 2026-10-19 | FE-13 | R8-STREAM 新域建模交付后验收；流表五张模型 |

### 2.11 R8-A AI 工具契约

| 契约名 | 冻结提交号 | 测试文件 | 方法数 | 状态 | 冻结日期 | 验收任务 | 备注 |
|---|---|---|---|---|---|---|---|
| R8-A-AiTools | — | `datara-web/src/views/rebuild/validation/ai-assistant/aiToolsApi.contract.test.ts` | 9 | RED-PENDING | — | FE-13 | RED 哨兵 `R8A_BACKEND_NOT_WIRED`；mock Agent 验证面 GREEN；待 LLM 端点解阻 |

---

## 三、冻结令登记规则

1. **FROZEN**：契约已冻结（后端提交号已登记），FE 侧验收通过，全条目 = 提交号 + 测试 passed。
2. **GREEN-WIRED**：FE 侧已接线，vitest 全绿，等待后端冻结令登记。
3. **RED-PENDING**：FE 侧契约为 RED 态（哨兵拒绝），等待后端接线后转 GREEN-WIRED。
4. **BLOCKED**：前置依赖未满足（后端建模/用户操作），禁止判定门通过。

---

## 四、逐门验收指引

| 门 | 验收任务 | 消费的契约条目 | 前置解阻事件 | FE 侧关键动作 |
|---|---|---|---|---|
| 门 1 API 契约冻结 | FE-13 | 全部 11 契约 | SYNC 解禁 / 工作流域建模 / R8-STREAM 建模 | 契约冻结登记簿全条目 = 提交号 + 测试 passed；三新域契约逐域复核 |
| 门 2 数据模型冻结 | FE-14 | — | 工作流域六模型建表 | 建表清单与 app.py 建表核对表登记；FE types 与表结构类型契约 vitest 全绿 |
| 门 3 节点协议冻结 | FE-15 | R4-Dependency / I7-Schedule | 节点配置协议建模冻结 | 30 子项逐项验收矩阵登记（每子项 = 测试用例 + passed） |
| 门 4 变量协议冻结 | FE-16 | R2-Variable | 变量域逐级验收收口 + FE-05 完成 | 七级优先级链逐级验收；入口全覆盖核对表登记 |
| 门 5 执行状态冻结 | FE-17 | I7-Schedule | 工作流域建模交付 + 1.9 授权 | 八能力逐项验收登记；CANCELLED/CANCEL_FAILED 终态实测 |
| 门 6 统计协议冻结 | FE-18 | R7-Metrics | 回写链路 1.9 实测环境 | 回写链路 Playwright 全链路；10 字段核对表登记 |
| 门 7 时间戳规范冻结 | FE-19 | — | 新表建表（随门 2） | 新表时间戳契约实测证据登记（每表 = 时间列清单 + NULL 检查 passed） |

---

## 五、变更日志

| 日期 | 变更 | 操作人 |
|---|---|---|
| 2026-10-19 | 初始登记簿模板建立（c27-fe-gates 任务） | Claude 实施线 |
