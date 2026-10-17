# Codex T-2 worktree 清理回执（按 handoff #54 六步标准）

- 报告基线：handoff #54 实测基线 Codex 25 个（C 盘 `.codex/worktrees` 19 + 项目 `.worktrees` 6）；本次核对以当前主仓 `git worktree list --porcelain`、每个实际 checkout 的 `git status --short`、tag 与 branch refs 为依据。
- 结论：**部分完成，安全门禁通过；12 个未删除 worktree 保留待后续裁定/清理**。此前已删除 13 个干净 worktree，删除前 tag 已建立，分支保留；剩余 12 个均检测到脏区，按 #54 第4步不得删除。本回执不执行额外删除、移动或清理分支。

## 已删除：13 个干净 worktree

| 原 worktree | 分支/HEAD | 归档 tag → commit |
|---|---|---|
| `C:/Users/Administrator/.codex/worktrees/93be/Datara` | `codex/i19-i20-carry-forward` | `archive/codex/i19-i20-carry-forward` → `2e5cfd1` |
| `C:/Users/Administrator/.codex/worktrees/correction-plan/Datara` | `codex/correction-plan` | `archive/codex/correction-plan` → `0cb0438` |
| `C:/Users/Administrator/.codex/worktrees/i19-i20-main-port/Datara` | `codex/i19-i20-main-port` | `archive/codex/i19-i20-main-port` → `c6cf9f1` |
| `C:/Users/Administrator/.codex/worktrees/i19-i20-write-path/Datara` | `codex/i19-i20-import-executors` | `archive/codex/i19-i20-import-executors` → `b601499` |
| `C:/Users/Administrator/.codex/worktrees/phase0-matrix-v5-fix/Datara` | `codex/phase0-matrix-v5-fix` | `archive/codex/phase0-matrix-v5-fix` → `641fff6` |
| `C:/Users/Administrator/.codex/worktrees/phase0-q-detail-port/Datara` | `codex/phase0-q-detail-port` | `archive/codex/phase0-q-detail-port` → `22031b7` |
| `C:/Users/Administrator/.codex/worktrees/r3-i19-i20-closeout/Datara` | `codex/r3-s9-i19-i20-closeout` | `archive/codex/r3-s9-i19-i20-closeout` → `e375d87` |
| `C:/Users/Administrator/.codex/worktrees/r5b-ddl-policy/Datara` | `codex/r5b-ddl-policy` | `archive/codex/r5b-ddl-policy` → `3fdc851` |
| `C:/Users/Administrator/.codex/worktrees/sync-q-handoff-04/Datara` | `codex/sync-q-handoff-04` | `archive/codex/sync-q-handoff-04` → `bf89236` |
| `D:/需求/数据治理工具/Datara/.worktrees/codex-q1-dag-catalog-fix` | `codex/q1-dag-catalog-fix` | `archive/codex/q1-dag-catalog-fix` → `27b3499` |
| `D:/需求/数据治理工具/Datara/.worktrees/codex-r3s9-integration` | `codex/r3-s9-main-integration` | `archive/codex/r3-s9-main-integration` → `6342d5b` |
| `D:/需求/数据治理工具/Datara/.worktrees/codex-s9-runner-gate-fix` | `codex/s9-runner-gate-fix` | `archive/codex/s9-runner-gate-fix` → `0826174` |
| `D:/需求/数据治理工具/Datara/.worktrees/r4-sync-contract` | `codex/r4-sync-contract` | `archive/codex/r4-sync-contract` → `68e2c4f` |

逐项复核：13 个 tag 指向的 commit 与对应分支/原 HEAD 一致；13 个分支引用仍保留；当前 `git worktree list` 不再登记上述路径。未使用 `--force`。

## 保留：12 个脏区 worktree

以下路径在 `git status --short` 有修改或未跟踪内容；不满足删除条件。branch/HEAD 与本次 `git worktree list --porcelain` 对照：

| Worktree | 当前分支 / HEAD | 脏区概况 |
|---|---|---|
| `C:/Users/Administrator/.codex/worktrees/134a/Datara` | detached `bec06af` | 未跟踪纠偏重构方案/实施计划文档 |
| `C:/Users/Administrator/.codex/worktrees/2d99/Datara` | detached `93d5861` | R4 页面、设计、分析与证据改动 |
| `C:/Users/Administrator/.codex/worktrees/6789/Datara` | detached `60c5485` | SQL IDE/R4/R5 草案、证据及嵌套 `main/` 工作目录 |
| `C:/Users/Administrator/.codex/worktrees/6789/Datara/main` | `codex/r6-schedule-endpoints` @ `305187e` | R6 源码、变量模块、handoff 与证据改动 |
| `C:/Users/Administrator/.codex/worktrees/b245/Datara` | `codex/i18-completion` @ `5ca62e5` | 后端/前端多域实现、测试和文档改动（范围较广） |
| `C:/Users/Administrator/.codex/worktrees/contract-closure/Datara` | `codex/plan-closure` @ `38a6290` | 未跟踪 AI Copilot 模块 |
| `C:/Users/Administrator/.codex/worktrees/phase0-q-correction` | `codex/phase0-q-correction` @ `4c7200a` | handoff、FE 契约、差异矩阵和 Q 跟踪文档改动 |
| `C:/Users/Administrator/.codex/worktrees/phase0-status-sync/Datara` | detached `9f9bb61` | 纠偏方案/实施计划同步改动 |
| `C:/Users/Administrator/.codex/worktrees/q9-merge/Datara` | `codex/r4-sync-red-q9` @ `62ae20e` | handoff、计划、差异矩阵及 Q9 证据改动 |
| `C:/Users/Administrator/.codex/worktrees/r8a-contract-freeze`（仓库内容位于子目录 `Datara/`） | detached `84d8313` | `Datara/` 内 handoff 有修改；worktree 注册路径指向父目录，实际 Git checkout 位于子目录，路径注册差异待核实，保留 |
| `D:/需求/数据治理工具/Datara/.worktrees/q1-dag-catalog-integrate` | `codex/q1-dag-catalog-integrate` @ `6b0db9b` | 性能基准、运行脚本及 R3 证据未跟踪/修改 |
| `D:/需求/数据治理工具/Datara/.worktrees/r3-s9` | `codex/r3-s9` @ `49f9a6f` | AOCI baseline、R3 页面/部署、后端目录及大量证据变更 |

5 个 detached checkout (`134a`、`2d99`、`6789/Datara`、`phase0-status-sync`、`r8a-contract-freeze`) 暂无归档 tag。它们仍有工作内容且未删除，故当前不需补删除前 tag；若后续状态满足删除条件，必须先建立 `archive/wt-<目录名>-<短hash>` tag。

## 六步标准核验

1. **归属**：仅处理 Codex 名下 worktree；Trae worktree 未触碰。
2. **tag 先行**：13 个已删除项均有对应归档 tag；保留的 detached 项待未来删除时再 tag。
3. **保留 refs**：13 个已删除项对应的分支 refs 全部保留；没有删除任何分支。
4. **脏区门禁**：12 个 dirty checkout 全部保留；不对他人改动做清理。
5. **删除与复核**：13 个通过普通 worktree remove 移除（无 `--force`）；当前 worktree 列表确认其不再登记。清理期间运行 prune 后复核。
6. **报告**：本文件为 Codex 清理报告；单 pathspec 提交并在 handoff 心跳回执。

## 后续跟进

- 12 个脏区仍在，后续不得擅自删除或清空。用户/监督员需按 #54 安全规则另行裁定或等待 owner 自行收口。
- `r8a-contract-freeze` 注册父目录与实际 `Datara/` checkout 的路径差异应先核实注册关系；在此之前不 prune/removal 该条目。
- 本次清理报告与本次 worktree 列表仅是当前时点快照；新增或变更以复核时实测为准。

## #65 batch-1 复核补记（七个候选，2026-10-17）

本节按 canonical main `c0f8ee5` 时点实测 `git worktree list --porcelain`、各实际 checkout 的 `git status --short --untracked-files=all`、branch/HEAD 与 `git log refs/heads/main..HEAD` 补充。七个候选都仍注册且工作树非空；相对该 main 基线有独有提交的项目列于下表。下列状态均未做修改、暂存、提交、打 tag、删除或 prune。

| 候选及实际 checkout | 注册状态；HEAD / 分支 | 脏区和独有提交 | 复核结论 |
|---|---|---|---|
| `C:/Users/Administrator/.codex/worktrees/134a/Datara` | 已注册；`bec06af`，detached | 未跟踪 `docs/increments/2026-10-16-纠偏重构实施计划-执行附录.md`、`docs/increments/2026-10-16-纠偏重构方案设计.md`；无相对 main 独有提交 | 文档未跟踪，未读内容；不能按“无抢救价值”处理，暂留 |
| `C:/Users/Administrator/.codex/worktrees/phase0-q-correction` | 已注册；`4c7200a`，`codex/phase0-q-correction` | 修改 handoff、`FE契约适配层设计.md`、`客户九项要求追踪矩阵.md`、`阶段0-0.4差异复用矩阵.md`；未跟踪 `2026-10-16-Q答复跟踪台账.md`；无相对 main 独有提交 | 有协作答复和矩阵资产，暂留 |
| `C:/Users/Administrator/.codex/worktrees/phase0-status-sync/Datara` | 已注册；`9f9bb61`，detached | 修改 `2026-10-16-纠偏方案修订设计.md`、`2026-10-16-纠偏重构实施计划-执行附录.md`；无相对 main 独有提交 | 有方案/执行附录的未提交差异，暂留 |
| `C:/Users/Administrator/.codex/worktrees/q9-merge/Datara` | 已注册；`62ae20e`，`codex/r4-sync-red-q9` | 相对 main 有 5 个独有提交，含 R4-SYNC RED 实现及 R8-A 评审证据；修改 handoff、修订设计、实施附录、0.4 矩阵；未跟踪 `2026-10-17-R4-SYNC-q9分支实现证据.md` | branch 有独有提交，工作树还有未保存差异，暂留 |
| 注册路径 `C:/Users/Administrator/.codex/worktrees/r8a-contract-freeze`；实际 checkout `C:/Users/Administrator/.codex/worktrees/r8a-contract-freeze/Datara` | 已注册；`84d8313`，detached | 修改 `2026-10-16-纠偏重构实施计划-执行附录.md`；无相对 main 独有提交 | 工作树有未提交差异，且注册路径与实际 checkout 有父/子目录差异，暂留 |
| `D:/需求/数据治理工具/Datara/.worktrees/q1-dag-catalog-integrate` | 已注册；`6b0db9b`，`codex/q1-dag-catalog-integrate` | 相对 main 有 1 个独有提交（`fix(backend): preserve URLs while parsing DAG profiles`）；修改 `datara-web/tests/perf/last-bench.json`；未跟踪 `.s9-operator-runner.cjs`、`docs/increments/evidence/R3/r3s9-20261015235317-b7b6e9.json` | 有独有代码提交及未提交运行/证据资产，暂留 |
| `C:/Users/Administrator/.codex/worktrees/contract-closure/Datara` | 已注册；`38a6290`，`codex/plan-closure` | 相对 main 有 1 个独有提交（`docs: record correction plan contract answers`）；未跟踪 `datara-backend/rebuild/ai_copilot/__init__.py`、`datara-backend/rebuild/ai_copilot/contracts.py` | 草稿是 R8-A 八工具只读合同（`0.1.0-draft`，含 schema、错误/结果、权限上下文、审计字段和预算定义；无 runtime handlers/授权接线），不能替代 P1-1 的模块骨架、`==`+vendor wheel+锁文件、chromadb 目录及 TDD 实现；可作 P1-3/R8-A 契约参考，是否转存 evidence 待 owner 决定；暂留 |

### 对 #65 假设的修正与处置

#65 的“脏项零抢救价值”假设与本轮逐路径实况冲突：本批包含三个有相对 main 独有提交的分支（q9-merge 5 个、q1-dag-catalog-integrate 1 个、contract-closure 1 个；合计 7 个独有提交），以及多份未提交或未跟踪的方案、矩阵、答复、实现和证据文件。故本轮按保全工作产物原则七项全部暂留。没有为 HEAD 创建 tag，也没有删除 worktree、清理分支或执行 prune。当前 HEAD 无 tag；更重要的是 tag 仅保留 commit，无法保留 dirty/untracked 工作树内容。

### 后续可选保全方式（本轮未执行）

- 对有独有提交的 branch，由 owner 评审后选择 cherry-pick/合并至 canonical main，或通过 bundle/归档分支保存提交历史；先核对目标与 pathspec。
- 对已跟踪但未提交差异，可由 owner 在确认后导出 binary diff/patch；未跟踪文件需另行显式纳入副本或归档清单，不能只依赖普通 diff。
- 经 owner 确认后可用包含 untracked 的 stash 或完整目录快照保存工作树；先验证恢复路径和内容清单，再讨论删除。
- 当提交历史和工作树差异都已验证保存、owner 确认无残余价值后，才重新评估 tag、worktree remove 与 prune；单独打 tag 不构成 dirty 工作树的保全。
