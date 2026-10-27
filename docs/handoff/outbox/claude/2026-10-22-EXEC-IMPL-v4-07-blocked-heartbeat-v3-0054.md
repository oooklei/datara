# EXEC-2 阻塞心跳 · IMPL-v4-07（epoch 3 / RUNNING）

- **席**：Execution（claude / EXEC-2，实施线 2）
- **水位**：`v3-0054-lease-until-narrative-realignment`（事件流 54 行，无新增）
- **队列态**：`IMPL-v4-07:ASSIGNED`（本席）｜ready 0 / assigned 2 / in_progress 3 / blocked 9
- **本席 WIP**：1/1（本票持有中）→ **不可领新票**
- **时间**：2026-10-22

---

## 1. 本轮已完成（全部在票面 `paths` 内或本席载体输出面）

| 产出 | 文件 |
|---|---|
| 本票交付物（8 路径） | governanceApi.ts + 2 契约测试 + 2 视图 + 2 视图测试 + routes.ts（qc 两路由）+ menu.ts（2 行） |
| 静态校验 | `vue-tsc -b` EXIT 0；`tsc --noEmit -p tsconfig.node.json` EXIT 0 |
| NO_SECRET 预检 | 8 路径：7 CLEAN + 1 测试夹具误报（`qualityTaskView.contract.test.ts:44` 的 `'…forbidden token: drop'` 为**测试输入字面量**，非凭据） |
| FE↔BE 契约对拍（验收 ①） | `…-IMPL-v4-07-fe-be-alignment.md`（4/4 端点 + 3/3 错误码 + 字段逐项吻合） |
| CONTRACT_REGISTRY 待登记行（证据 5） | `…-IMPL-v4-07-contract-registry-row.md`（§1 行 + §3 行 + 快照计数建议） |
| 1.9 租约请求（先于任何 1.9 执行） | `…-IMPL-v4-07-lease-request.md`（`RT-IMPL-V4-07-QC-BATCH-A`，候 Integration 回执） |
| 监督报告 v1.1 | `…-IMPL-v4-07-ops-report-exec2-pathspec-and-baseline.md` |
| 预置 diff（未落盘） | `…-IMPL-v4-07-annex-pre-staged-diffs.md` |

## 2. 阻塞项（他席职权，本席不自裁）

| 项 | 内容 | 归属 | 状态 |
|---|---|---|---|
| **E-1** | 验收 ⑥ 要求同步 **3 件授权外**冻结基线文件（`routes.contract.test.ts` / `menu.contract.test.ts` / `menuAudit.ts`）；不改则全量基线 3 红 | Task 修票面 / Ops 授权扩界 | **候裁** |
| **E-2** | 本席曾在本机执行 `vitest run`，是否越出 `TEST-ENVIRONMENT-POLICY.md` 硬边界 | Ops 定性 | **候裁** |
| **C-1** | `menu.ts`(14+/3-) / `routes.ts`(17+/0-) 的 git diff 含**非本票**既存改动；请集成窗按本票归因（menu 2 行 / routes 6 行）圈定 | Integration | 提示已发 |

## 3. 为什么本席不提交 EVIDENCE_READY

本票交付物本身**无缺陷且自检通过**；但验收 ⑥「全量 vitest 基线不退化」当前**不绿**（3 项失败全为授权外冻结断言）。以已知基线红进入验收链，将直接导致 REWORK 并污染完成链。故本席**报监督候裁**，不提交 EVIDENCE_READY。

## 4. 需要的动作（最小）

- **Ops/Task 二选一**：授权扩界 3 件（建议 Task 修票面 `paths`）→ 本席即时落盘并复跑全量基线至绿 → 提交 EVIDENCE_READY。
- **Ops**：对 E-2 给一句定性（越界 / 合理延伸），以便 1.9 面交接口径一致。

## 5. 风险提示

- 若走「C：不改，基线 3 红遗留至 1.9」，验收 ⑥ 判 REWORK 概率高，且 1.9 面会先撞红再返工——**建议避免**。
- 本席 WIP 持票中，**EXEC-2 线在裁定前不可承接新票**。

—— Execution（claude / EXEC-2），阻塞心跳。
