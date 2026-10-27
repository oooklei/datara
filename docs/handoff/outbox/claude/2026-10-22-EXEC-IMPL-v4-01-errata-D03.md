# 勘误登记 · DEC-v4-D03（LLM 前端 API 封装落位）

- **登记席**：Execution（claude）｜**票据**：IMPL-v4-01
- **裁定依据**：DEC-v4-D03（D2，v3-0006 裁定书 `artifacts/datara-decision-rulings-D01-D04-2026-10-22.md`）
- **登记时间**：2026-10-22｜**水位**：`v3-0020-evidence-ready-impl-v4-03`
- **性质**：设计文档勘误登记（不回写历史文档；候 E 组清理或后续文档窗处理）

---

## 1. 勘误项

| # | 文档 | 位置 | 原文（早期表述） | 正位（代码现实） |
|---|---|---|---|---|
| E-1 | `docs/increments/2026-10-19-纠偏重构前端权威设计.md` | **§5E.3**（L786） | `API 封装：\`src/api/llm.ts\`（getLlmModels / createLlmModel / updateLlmModel / deleteLlmModel / testLlmModel / setDefaultLlmModel）` | `datara-newweb/src/services/rebuild/llmApi.ts`（`list` / `create` / `update` / `remove` / `testModel` / `setDefault`） |
| E-2 | `docs/increments/2026-10-20-单线多增量WBS开发计划.md` | **15.6**（L458） | `… API 封装 \`src/api/llm.ts\`）` | 同上 |

## 2. 裁定理由（DEC-v4-D03 原文要点）

1. 代码现实：`llmApi.ts` 已存在于 `src/services/rebuild/`，与全部既有 service 同构（`datasourceApi` / `rolePermissions` / `sshNodeApi` / `projectApi` 同目录）。
2. 17.1 前端目录落位对照预研（2026-10-20，G-05 行）已登记「新增 llmApi.ts」于 services 层，是后于 §5E.3 的收敛口径。
3. `datara-newweb` 无 `src/api/` 目录惯例。
4. 先例：PROJ-FE-01 票「governance/latest.md 矩阵滞后于代码现实，按代码现实收敛」。

## 3. 执行口径

- IMPL-v4-01 **按现状收口**（不迁移、不改设计文档）。
- 设计文档（§5E.3 / WBS 15.6）勘误**登记**于本件，随证据包提交；`docs/increments/**` **不在 IMPL-v4-01 paths 内**，实施线**未改动**。
- 处理归属：**E 组清理（IMPL-v4-05）或后续文档窗**。

## 4. 边界声明

- 本件为勘误**登记**，非文档改写；未触碰 `docs/increments/**` 任何文件。
- 未写 STATE/mailbox/队列投影；未 commit/push；AOCI 停用未调用。

—— Execution（claude），DEC-v4-D03 勘误登记。
