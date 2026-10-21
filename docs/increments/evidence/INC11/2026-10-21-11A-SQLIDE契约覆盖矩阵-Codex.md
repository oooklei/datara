# 11A SQL IDE 契约覆盖矩阵（Codex）

- 日期：2026-10-21 Asia/Shanghai
- 裁定：R-49（24↔17↔23 逐路由矩阵作为 11B–11I 开工门）
- 结论：**计数歧义已消除；24 条后端路由均有前端入口，23 个 contract 对象方法已统一到冻结常量，status 作为独立恢复入口；R5-B DDL 客户端继续 RED 隔离。**

## 计数解释

- **17**：旧 `R5A_CONTRACT_METHODS` 常量，只覆盖最早的元数据、执行、历史和脚本子集，已过时。
- **23**：`SqlIdeContract` 对象的完整只读方法数；本票已把冻结常量扩为同一 23 项。
- **24**：后端 `_ROUTE_SPECS` 路由数。额外的恢复入口 `getExecutionStatus` 由独立函数 `getSqlIdeExecutionStatus` 承接；下载路由由 `getExportDownloadUrl` 生成授权 URL，因此 24 路由与 24 个前端入口逐一对应。

## 逐路由覆盖矩阵

| # | 后端 | operation | 前端入口 | 页面承接票 | 测试锚 |
|---:|---|---|---|---|---|
| 1 | GET `/databases` | listDatabases | listDatabases | 11B/11C | sqlIdeApi contract + 11A gate |
| 2 | GET `/schemas` | listSchemas | listSchemas | 11C | 11A gate |
| 3 | GET `/relations` | listRelations | listRelations | 11C | 11A gate |
| 4 | GET `/columns` | listColumns | listColumns | 11C | 11A gate |
| 5 | GET `/routines` | listRoutines | listRoutines | 11C | 11A gate |
| 6 | GET `/indexes` | listIndexes | listIndexes | 11C | 11A gate |
| 7 | GET `/objects/search` | searchObjects | searchObjects | 11C | sqlIdeApi contract + 11A gate |
| 8 | POST `/definitions` | getDefinition | getDefinition | 11C/11H | sqlIdeApi contract + 11A gate |
| 9 | POST `/lint` | lintSql | lintSql | 11D/11F | sqlIdeApi contract + 11A gate |
| 10 | POST `/executions` | executeSql | executeSql | 11D | sqlIdeApi contract + 11A gate |
| 11 | POST `/executions/{task_id}/cancel` | cancelExecution | cancelExecution | 11D | sqlIdeApi contract + 11A gate |
| 12 | GET `/executions/{task_id}/events` | openEventStream | openEventStream | 11D | SSE reconnect contract + 11A gate |
| 13 | GET `/executions/{task_id}` | getExecutionStatus | getSqlIdeExecutionStatus | 11D | 11A gate |
| 14 | GET `/results/{history_id}` | fetchResultPage | fetchResultPage | 11E | pagination contract + 11A gate |
| 15 | GET `/history` | listHistory | listHistory | 11G | 11A gate |
| 16 | DELETE `/history/{history_id}` | deleteHistory | deleteHistory | 11G | 11A gate |
| 17 | GET `/scripts` | listScripts | listScripts | 11G | 11A gate |
| 18 | POST `/scripts` | saveScript | saveScript | 11G | CAS contract + 11A gate |
| 19 | DELETE `/scripts/{script_id}` | deleteScript | deleteScript | 11G | CAS contract + 11A gate |
| 20 | POST `/exports` | exportResult | exportResult | 11G | sqlIdeApi contract + 11A gate |
| 21 | POST `/table-exports` | exportTable | exportTable | 11G | 11A gate |
| 22 | GET `/exports/{export_id}` | getExport | getExport | 11G | 11A gate |
| 23 | GET `/exports/{export_id}/download` | downloadExport | getExportDownloadUrl | 11G | sqlIdeApi contract + 11A gate |
| 24 | DELETE `/exports/{export_id}` | cancelExport | cancelExport | 11G | 11A gate |

“页面承接票”是后续实现责任映射，不把尚未实现的页面声称为已完成。11A 只冻结契约覆盖并防止路由漏接。

## DDL RED 隔离

`sqlIdeDdlApi.ts` 的 `validatePolicy / previewImpact / submitConfirm / executeDdl` 不进入 R5-A 常量或矩阵。自动门同时断言 R5-A client 不导入该模块，写路径继续归增量 16。

## 验证

```text
cd datara-backend
python -m pytest -q tests/rebuild/test_sql_ide_route_coverage_matrix.py
3 passed in 0.36s

cd datara-newweb
npx vitest run src/services/rebuild/__tests__/sqlIdeApi.contract.test.ts
Test Files  1 passed (1)
Tests       9 passed (9)
```

## SHA256

```text
fd6aa3d55b40bc22b385ef110d490052b6630815bf4c601c8e60d2350ba7c168  datara-newweb/src/services/rebuild/sqlIdeApi.ts
0a92047fd38292f78c4d8315b65bcd3a5c9a16da373e0145e1c8bc2f2fda20fd  datara-newweb/src/services/rebuild/__tests__/sqlIdeApi.contract.test.ts
9e750b9ec16de2047bb57fdebe92409602fbc9bc390f2cdcb7abdece5b465abb  datara-backend/tests/rebuild/test_sql_ide_route_coverage_matrix.py
```

提交号：无，工作区改动，待监督线代提交。
