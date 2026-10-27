# IMPL-v4-07 · CONTRACT_REGISTRY 待登记行文本（证据包第 5 项）

- **票据**：IMPL-v4-07（质量五项批 A）｜**席**：Execution（claude / EXEC-2）
- **水位**：`v3-0054-lease-until-narrative-realignment`
- **交付方式**：**不改** `CONTRACT_REGISTRY.md`（票面 boundaries 第 2 条）；以下文本由 Integration 集成窗单点追加。

---

## A. §1 契约文件 ↔ 测试映射表 · 新增行

追加于表尾（现行末行 #18 `rolePermissions.ts` 之后）：

```markdown
| 19 | `governanceApi.ts` | `services/rebuild/__tests__/governanceApi.contract.test.ts` | GREEN | 4 | 5 | 质量五项批 A（WBS 增量 14 包 14.4）：质量规则/运行记录契约层。四端点接 `rebuild/governance`（POST/GET `/projects/{id}/quality-rules`、POST `/quality-rules/{rule_id}/run`、GET `/projects/{id}/quality-runs`）；`{code,msg,data}` 三态 + `preserveEnvelopeCode` 保 4xxx 业务码（4041 不存在 / 4091 重名·停用·落库失败 / 1003 项目成员鉴权）；权限矩阵 VIEW_ALL/EDIT_DEFINITION 冻结；**structural 语义红线**（验收 ④）落码——行级四字段恒 0、`summary.engine` 恒 `structural`，前端不虚构行级结果 |
```

## B. §3 冻结提交表 · 新增行

```markdown
| `governanceApi.ts`（14.4 批 A 质量域契约层；四端点 + 权限矩阵 + structural 口径常量 `QUALITY_STRUCTURAL_ONLY` 单一事实源） | 待监督线代提交（工作区未提交） | `services/rebuild/__tests__/governanceApi.contract.test.ts`（5 用例）+ `views/__tests__/qualityRuleView.contract.test.ts`（5 用例）+ `views/__tests__/qualityTaskView.contract.test.ts`（4 用例） | GREEN | 2026-10-22 |
```

## C. §1 状态快照行 · 建议同步刷新

现行：`GREEN 17 / RED 1；冻结方法合计 133`
建议：`GREEN 18 / RED 1；冻结方法合计 137`（+`governanceApi` 4 方法 / +5 测试）

## D. §4 测试计数表 · 建议同步刷新

现行合计 `154` → 建议 `159`（+`governanceApi.contract.test.ts` 5）

---

## E. 登记前提（须先闭合）

- **E-1 未决**：验收 ⑥ 要求同步 4 件授权外冻结基线文件（`routes.contract.test.ts` / `menu.contract.test.ts` / `menuAudit.contract.test.ts` / `menuAudit.ts`）。**在该 4 件获授权并同步前，本行状态不得记为 GREEN 并完成登记**——否则登记簿将记录一个已知不绿的本票。
- 建议 Integration 集成窗**待 E-1 裁定落地后**再追加本行。
