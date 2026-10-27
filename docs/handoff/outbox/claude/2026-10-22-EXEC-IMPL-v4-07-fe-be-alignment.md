# IMPL-v4-07 · FE↔BE 契约对拍证据（验收 ①）

- **票据**：IMPL-v4-07｜**席**：Execution（claude / EXEC-2）
- **水位**：`v3-0054-lease-until-narrative-realignment`
- **方法**：静态对拍（本机业务代码稽核，非测试执行）。后端权威源 `datara-backend/rebuild/governance/api.py`。

---

## 1. 端点映射（4/4 吻合）

| # | 后端（api.py） | 方法 | 状态码 | 权限 | FE（`governanceApi.ts`） |
|---|---|---|---|---|---|
| 1 | `POST /projects/{project_id}/quality-rules` L1632 | 创建规则 | **201** | `EDIT_DEFINITION` | `createRule` |
| 2 | `GET /projects/{project_id}/quality-rules` L1678 | 规则列表 | 200 | `VIEW_ALL` | `listRules` |
| 3 | `GET /projects/{project_id}/quality-runs` L1728 | 运行记录列表 | 200 | `VIEW_ALL` | `listRuns` |
| 4 | `POST /projects/{project_id}/quality-rules/{rule_id}/run` L1768 | 执行规则 | **201** | `EDIT_DEFINITION` | `runRule` |

- router prefix `/api/v1/rebuild/governance`（L184）+ FE `BASE='/rebuild/governance'` → 全路径 `/api/v1/rebuild/governance/...` ✅
- 分页：后端 `page`/`page_size`（`ge=1`，`page_size le=200`，默认 50）↔ FE `{page, pageSize}` 默认 `1/50` ✅
- 包络：`{code,msg,data}` 三态；FE 经 `preserveEnvelopeCode` 保后端码 ✅

## 2. 响应体字段对拍

**规则（创建响应 L1657-1668）** → FE `QualityRuleRecord`：
`id, project_id, asset_id, name, expression, severity, enabled, created_at, updated_at`
→ FE `id, projectId?, assetId, name, expression, severity, enabled, createdAt, updatedAt` ✅ 逐字段吻合（`projectId` 设为可选：列表项不含该字段）。

**运行记录（`quality_run_payload` L1321-1332 + 调用点前置 `asset_id`）** → FE `QualityRunRecord`：
`id, rule_id, status, checked_rows, success_rows, failed_rows, skipped_rows, summary, generated_at` + `asset_id`
→ FE `id, assetId, ruleId, status, checkedRows, successRows, failedRows, skippedRows, summary, generatedAt` ✅ 逐字段吻合。

**`summary`（`summary_json` L1786-1792）** → FE `QualityRunSummary`：
`{engine:"structural", message:"structural predicate validation only; row-level sampling requires a bound datasource", issues:[...]}` ✅ 逐字段吻合；`QUALITY_STRUCTURAL_ONLY.message` 与后端字面量**逐字一致**。

## 3. 错误码对拍（3/3 吻合）

| 后端触发点 | HTTP | code | FE `QUALITY_ERROR_CODES` |
|---|---|---|---|
| L1644 `asset not found in project` | 404 | **4041** | `notFound: 4041` ✅ |
| L1653 `quality rule name already exists` | 409 | **4091** | `duplicateName: 4091` ✅ |
| L1783 `quality rule not found in project` | 404 | **4041** | `notFound: 4041` ✅ |
| L1785 `quality rule is disabled` | 409 | **4091** | `disabled: 4091` ✅ |
| L1812 `quality rule run failed to persist` | 409 | **4091** | `runPersistFailed: 4091` ✅ |
| `project_permission_error`（`rebuild/api/app.py` L539-558） | — | **1003** | `permissionDenied: 1003` ✅ |

- 401 未授权由 `authenticate` 先行返回（1001 段），不在本域码表内。

## 4. structural 语义红线（验收 ④）对拍

后端 L1785-1793：`checked_rows=success_rows=failed_rows=skipped_rows=0`、`summary.engine="structural"`、`status = "failed" if issues else "succeeded"`。
禁用词表 `_FORBIDDEN_EXPRESSION_TOKENS`（L1757-1766）：`;` `drop ` `delete ` `update ` `insert ` `truncate ` `alter ` `create `。

FE 侧：
- `QualityRunRecord` 保留四字段类型（如实反映后端恒 0），但**两个视图均不渲染为行级结论**；
- `QualityRuleView.run()` 文案明示「行级四字段恒 0」；
- `QualityTaskView.summaryText()` 只输出 `engine + message + issues`；
- 两页均带 `data-structural-note` 常注。

✅ 未虚构行级结果。

## 5. 结论

**验收 ①「governanceApi 覆盖四端点，包络三态与错误码对齐」：静态对拍 4/4 端点 + 3/3 错误码 + 字段逐项吻合，通过。**

⚠️ 本项为**静态对拍**结论；运行期 GREEN 须由 1.9 面执行（租约 `RT-IMPL-V4-07-QC-BATCH-A` 已请求，候回执）。
