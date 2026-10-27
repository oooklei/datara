# IMPL-v4-07 · EVIDENCE_READY 证据包（EXEC-2 / claude）

- **票**：IMPL-v4-07（质量五项批 A：/qc/rule + /qc/task + governanceApi 契约 + 菜单转正）
- **席**：Execution（claude / EXEC-2，实施线 2）
- **时间**：2026-10-23T02:35+08:00｜**水位**：v3-0060
- **票面依据**：**Task 增量 13 §二（票面 v1.1，8→11 路径 + 验收⑥改 1.9 权威基线）**；Task 明示「实施席可依本件立即执行，证据面注明依据」。Flow 准入 `TICKET_FACE_REVISED` 事件前，控制面以本件为凭。

## 1. 路径实存清单（11/11 实存，票面 v1.1）

| # | 路径 | 状态 |
|---|---|---|
| 1 | src/services/rebuild/governanceApi.ts | 实存（本票新增质量域契约层，171 行） |
| 2 | src/services/rebuild/__tests__/governanceApi.contract.test.ts | 实存 |
| 3 | src/views/qc/QualityRuleView.vue | 实存（新） |
| 4 | src/views/qc/QualityTaskView.vue | 实存（新） |
| 5 | src/views/__tests__/qualityRuleView.contract.test.ts | 实存（新） |
| 6 | src/views/__tests__/qualityTaskView.contract.test.ts | 实存（新） |
| 7 | src/router/routes.ts（仅 qc 两路由） | 实存（本票归因 10 行） |
| 8 | src/navigation/menu.ts（仅 qc-rule/qc-task 两行） | 实存（本票归因 2 行） |
| 9 | src/router/__tests__/routes.contract.test.ts | 实存（本轮新增同步，见 §2） |
| 10 | src/navigation/__tests__/menu.contract.test.ts | 实存（本轮新增同步） |
| 11 | src/navigation/menuAudit.ts | 实存（本轮新增同步） |

## 2. 本轮（授权解锁后）3 件落盘明细——依据 Task 增量 13 §二

| 文件 | diff（numstat） | 本票归因 | 内容 |
|---|---|---|---|
| routes.contract.test.ts | 25+/1- | 本票 14+ / 他票 11+/1-（闭合） | 冻结路径表 +2（/qc/rule、/qc/task）+ 具名绑定断言 1 条 + import 2 |
| menu.contract.test.ts | 6+/2- | 本票 4+/2- / 他票 2+（闭合） | E 组断言 10 formal / 3 future |
| menuAudit.ts | 4+/4- | 本票全部 | no:3/no:4 disposition future→formal + note 注记 |

- 增量追加式遵守：未回退/改写他票既存行（/dep/ssh、/sec/perm、dep-ssh 行原样保留）。
- `menuAudit.contract.test.ts` 未改（对拍器，台账源同步后自动转绿——Task §二.3 边界遵守）。
- `AUDIT_COUNTS` 未改（grouped=formal∪future，计数不变 10，EXEC-2 v1.1 复核结论）。

## 3. 本机静态校验（2026-10-23T02:30±5，EXIT 实测）

| 项 | 结果 |
|---|---|
| `npx vue-tsc -b` | **EXIT 0** |
| `npx tsc --noEmit -p tsconfig.node.json` | **EXIT 0** |
| NO_SECRET 预检（11 路径） | **0 实际命中**（3 命中均为「API-Key 管理」产品名标签字面量：menu.ts:350 / menu.contract.test.ts:142 / menuAudit.ts:137，皆为非本票改动行既存内容） |

**验收⑥（修订后口径）**：本机静态三项通过 ✅；全量 vitest 基线 GREEN 权威证据由 **1.9 租约段**出具（本机 vitest 结果按 `evidence_rule.local_result` 仅作 DIAGNOSTIC_ONLY_NOT_PASS_EVIDENCE，不作验收依据——A5-E2 定性承接，见 2026-10-23 裁定承接回执）。

## 4. 承前证据（前序会话产出，本轮核验仍有效）

- FE↔BE 契约对拍（验收①）：4/4 端点 + 3/3 错误码 + 字段逐项吻合 —— `2026-10-22-EXEC-IMPL-v4-07-fe-be-alignment.md`
- CONTRACT_REGISTRY 待登记行（证据 5）：`2026-10-22-EXEC-IMPL-v4-07-contract-registry-row.md`（不改 CONTRACT_REGISTRY.md，随证据交付）
- structural 语义（验收④）：行级四字段恒 0 口径已固化于 governanceApi.ts 文件头红线 + `QUALITY_STRUCTURAL_ONLY` 常量；前端不虚构行级结果
- 菜单转正（验收⑤）：menu.ts qc-rule/qc-task `future→formal` 两行，diff 归因 2 行

## 5. 1.9 段（候执行，不阻断 EVIDENCE_READY）

- 租约请求 **RT-IMPL-V4-07-QC-BATCH-A** 已注册 READY（v3-0057；Ops A4 已由 Flow 处理），候 Integration 回执。
- 1.9 段交付面：全量 vitest 基线 GREEN（权威）+ 本票契约测试/视图测试 14 用例 + Playwright 建规则→执行→quality-runs 查询闭环（验收③⑦）+ 验证入口 18091（禁 8090/18090）。

## 6. C-1 集成窗归因（重申，v1.2 逐行切分）

- `routes.ts`：本票 **10 行**（注释 4 + import 2 + 路由注释 2 + 路由 2）；他票 7 行。
- `menu.ts`：本票 **2 行**；他票 12+/3-。
- 本轮 3 件基线同步文件的归因见 §2 表。请 PATHSPEC_MANIFEST 按票面归因列圈定。

## 7. 状态申明

- 本席仅申明 **EVIDENCE_READY**；不签发 RELEASED/VALIDATED/DONE。
- 完成链：EVIDENCE_READY → ENV_VERIFIED（Integration 租约 RT-IMPL-V4-07-QC-BATCH-A）→ PASS（Acceptance）→ Flow 集成窗提交。
- 工作区变更留置候集成窗，无 commit、无 push（USER_ONLY）。

## 自报

本轮轮次 1（唤醒→落盘→校验→EVIDENCE_READY）/ 空转比低。

—— Execution（claude / EXEC-2），EVIDENCE_READY。
