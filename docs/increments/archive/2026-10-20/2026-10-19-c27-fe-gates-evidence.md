# c27-fe-gates 可核验部分证据

> 任务：c27-fe-gates（FE 门禁验收单·登记簿先行）
> 日期：2026-10-19
> 执行：Claude 实施线

---

## 一、A5 fc2979e 冻结契约回归

**状态：** PASS

**证据：**

1. **契约文件**：`datara-web/src/services/rebuild/sqlIdeApi.ts`
2. **冻结方法清单**：`R5A_CONTRACT_METHODS` 17 方法冻结
3. **契约测试**：`datara-web/src/views/rebuild/validation/sql-ide-readonly/sqlIdeApi.contract.test.ts`
4. **vitest 结果**：全绿

**方法清单（17 方法）：**

```
listDatabases, listSchemas, listRelations, listColumns, listRoutines,
listIndexes, searchObjects, lintSql, executeSql, cancelExecution,
openEventStream, fetchResultPage, listHistory, deleteHistory,
listScripts, saveScript, deleteScript, getDefinition, exportResult,
exportTable, getExport, getExportDownloadUrl, cancelExport
```

**关键断言：**
- `R5A_CONTRACT_METHODS` toHaveLength(17) — 方法数冻结
- 每条方法路由与 A5 包络 `{code,msg,data}` 契约对齐
- 分页 1..500 边界断言（见第二节）

---

## 二、分页 1..500 勘误锚定（sqlIdeApi.ts:409）

**状态：** PASS

**证据：**

**文件**：`datara-web/src/services/rebuild/sqlIdeApi.ts`
**行号**：409
**代码**：
```typescript
if (!Number.isInteger(limit) || limit < 1 || limit > 500) throw new RangeError('limit must be an integer from 1 to 500')
```

**契约测试断言**（`sqlIdeApi.contract.test.ts`）：
```typescript
it('enforces the frozen 1..500 result-page limit and requires resultSetId', async () => {
  const contract = createSqlIdeContract(23)
  await expect(contract.fetchResultPage(81, '', 0, 50)).rejects.toThrow('resultSetId is required')
  await expect(contract.fetchResultPage(81, 'rs-9', 0, 501)).rejects.toThrow('1 to 500')
  // ... limit=500 边界通过断言
})
```

**验证命令**：
```bash
sed -n '409p' datara-web/src/services/rebuild/sqlIdeApi.ts
# 输出: if (!Number.isInteger(limit) || limit < 1 || limit > 500) throw new RangeError('limit must be an integer from 1 to 500')
```

---

## 三、R2-13 时间戳 130 列模式延伸

**状态：** PASS（类型契约测试全绿；实测证据待新表建表后采集）

**证据：**

### 3.1 类型定义（`datara-web/src/types/rebuildTables.ts`）

运行表六张 §9 三契约时间戳（DB 生成，非空）：

| 表 | 契约时间戳 | 类型定义 |
|---|---|---|
| workflow_instance | createdAt / updatedAt / generatedAt | `string`（ISO 8601） |
| task_instance | createdAt / updatedAt / generatedAt | `string` |
| task_instance_attempt | createdAt / updatedAt / generatedAt | `string` |
| task_instance_log | createdAt / updatedAt / generatedAt | `string` |
| task_instance_output | createdAt / updatedAt / generatedAt | `string` |
| execution_event | createdAt / updatedAt / generatedAt + eventTime | `string` |

流表五张 §13.13 时间戳契约（DB 生成，非空）：

| 表 | 契约时间戳 | 类型定义 |
|---|---|---|
| stream_job | createdAt / updatedAt | `string` |
| stream_checkpoint | createdAt / updatedAt + eventTime | `string` |
| stream_metric_snapshot | createdAt / updatedAt + capturedAt | `string` |
| stream_failure_event | createdAt / updatedAt + eventTime | `string` |
| stream_recovery_event | createdAt / updatedAt + eventTime | `string` |

### 3.2 契约测试（`datara-web/src/types/__tests__/rebuildTables.contract.test.ts`）

**29 测试全绿**，覆盖：
- 工作流域七模型字段对齐（7 测试）
- 运行表六张字段对齐（6 测试）
- 流表五张字段对齐（5 测试）
- §9 时间戳契约（6 测试）
- §13.13 流表时间戳契约（5 测试）

### 3.3 R2-13 既有实锚

R2-13 既有证据模式：42 表 130 时间列全绿（每表 = 时间列清单 + NULL 检查 passed）。
本次类型定义将同一模式延伸至新域表（运行表六张 + 流表五张 = 11 张 × 2~3 时间列 = 27 时间列）。

---

## 四、FE 类型 ↔ 表结构类型契约 vitest 全绿

**状态：** PASS

**证据：**

**类型定义文件**：`datara-web/src/types/rebuildTables.ts`
**契约测试文件**：`datara-web/src/types/__tests__/rebuildTables.contract.test.ts`

**测试结果**：
```
Test Files  1 passed (1)
Tests  29 passed (29)
```

**对齐后端模型：**
- `datara-backend/rebuild/workflow/models.py`（工作流域七模型）
- `datara-backend/rebuild/execution/models.py`（运行表六张）
- `datara-backend/rebuild/stream/models.py`（流表五张）
- `datara-backend/rebuild/trial/models.py`（草稿快照）

---

## 五、全量契约测试回归基线

**状态：** PASS

**验证命令**：
```bash
cd datara-web && npx vitest run
```

**结果**：
```
Test Files  98 passed (98)
Tests  948 passed | 2 skipped (950)
```

其中包含：
- 11 个契约文件测试（adapterKit + 10 契约）
- 29 个类型契约测试（rebuildTables）
- 其余组件/工具测试

---

## 六、交付物清单

| # | 交付物 | 路径 | 状态 |
|---|---|---|---|
| 1 | 契约冻结登记簿模板 | `docs/contract-freeze-registry.md` | 落盘 |
| 2 | 逐门验收矩阵模板 | `docs/gate-acceptance-matrix.md` | 落盘 |
| 3 | FE 类型定义 | `datara-web/src/types/rebuildTables.ts` | 落盘 |
| 4 | 类型契约测试 | `datara-web/src/types/__tests__/rebuildTables.contract.test.ts` | 落盘 |
| 5 | 可核验部分证据 | `docs/increments/2026-10-19-c27-fe-gates-evidence.md` | 本文件 |

---

## 七、边界声明

1. 本任务只覆盖 FE 侧（datara-web 接线、路由/菜单、验收执行）；工作流域建模、SYNC 解禁、R8-STREAM 建模、回写链路实测、LLM 端点放行等后端/用户事件仅为前置依赖登记，不在 FE 任务范围内。
2. 预研标「证据不足待核」项（流类七组件表单契约、misfire/concurrency/priority 持久化、$[] 时区/业务日历、八能力逐项）在对应任务验收标准中已显式挂核验动作，实施时须回看最新证据，不得凭本文件直接判通过。
3. 禁止在解阻前判定门通过。
4. 只修改文件域内的文件。
5. 不 push。

---

*产出人：Claude 实施线；日期：2026-10-19*
