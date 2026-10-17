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

## #65 batch-2 复核补记（四个 checkout，2026-10-17）

本批基线为 canonical main `5249741b484e49906445e907b56e8c64e6ceec6f`。注册关系来自该仓 `git worktree list --porcelain`；逐工作区实测 `rev-parse --show-toplevel`、HEAD、分支、`status --short --untracked-files=all`、`refs/heads/main..HEAD`、branch/tag containment。四个指定路径均已注册、工作区非空；6789 父 checkout 与嵌套 `main` 分别核对。dirty/untracked 内容没有作为提交保存；本节只记录观察，不改动 checkout、引用或 tag。

### 摘要与保全状态

| 注册路径 → 实际 repo | HEAD / 分支 | 相对 main 独有提交与标签/引用保全 | 未提交内容状态 |
|---|---|---|---|
| `C:/Users/Administrator/.codex/worktrees/b245/Datara` | `5ca62e5` / `codex/i18-completion` | 11 个相对 main 独有提交；branch ref 存在，HEAD 无 tag，main 不包含该 HEAD。提交历史已有 branch 保底；删除 branch/worktree 前仍需 owner 评审 | 73 个 tracked 修改 + 32 个 untracked 文件，均未提交、未保存到 branch；内容范围广，不能清理 |
| `D:/需求/数据治理工具/Datara/.worktrees/r3-s9` | `49f9a6f` / `codex/r3-s9` | 无相对 main 独有提交；HEAD 是 main 祖先，且多个 `archive/*` tag 包含该历史。已提交基线有 main/tag 保底 | 8 个 tracked 修改 + 27 个 untracked 文件未提交 |
| `C:/Users/Administrator/.codex/worktrees/2d99/Datara` | `93d5861` / detached | 19 个相对 main 独有提交；HEAD 无分支、无包含它的 tag，main 不包含该 HEAD。提交对象当前由已注册 worktree HEAD 引用，但没有独立命名 ref 保底；若要清理，必须先由 owner 选择保全引用 | 6 个 tracked 修改 + 5 个 untracked 文件未提交 |
| `C:/Users/Administrator/.codex/worktrees/6789/Datara` | `60c5485` / detached | 无相对 main 独有提交；HEAD 是 main 祖先，并被若干既有 archive tag 包含，已提交基线有 main/tag 保底 | 无 tracked 修改；9 个未跟踪文件 + 已注册嵌套 checkout 的 `main/` 目录标记。文件均未提交 |
| `C:/Users/Administrator/.codex/worktrees/6789/Datara/main`（独立注册 checkout） | `305187e` / `codex/r6-schedule-endpoints` | 无相对 main 独有提交；HEAD 是 main 祖先，且 branch ref 存在。已提交基线有 main/branch 保底 | 3 个 tracked 修改 + 6 个 untracked 文件未提交 |

“已保底”仅指 commit 历史能由 main、现存 branch 或 tag 引用；不代表 dirty 工作树已保存。b245 的独有历史由现有 branch 引用，2d99 的 detached 独有历史目前没有 branch/tag，只由 worktree HEAD 暂时可达。四个父 checkout 以及嵌套 main 均存在未提交差异；不能因基线 commit 已有引用就判定整个工作区可清理。

### 逐 checkout dirty 清单

#### b245：`C:/Users/Administrator/.codex/worktrees/b245/Datara`

Tracked 修改（73）：

```text
datara-backend/api/auth.py
datara-backend/api/datasource.py
datara-backend/api/graph_rules.py
datara-backend/api/ide.py
datara-backend/api/lineage.py
datara-backend/api/main.py
datara-backend/api/wf_definition.py
datara-backend/common/models.py
datara-backend/tests/i13_smoke_no_pytest.py
datara-backend/tests/test_graph_rules.py
datara-backend/tests/test_lineage_graph.py
datara-backend/tests/test_wf_design_lineage.py
datara-backend/worker/executors/o_alert.py
datara-backend/worker/executors/o_doris.py
datara-backend/worker/executors/o_kafka.py
datara-backend/worker/executors/op_agg.py
datara-backend/worker/executors/op_cep.py
datara-backend/worker/executors/op_dedup.py
datara-backend/worker/executors/op_expr.py
datara-backend/worker/executors/op_filter.py
datara-backend/worker/executors/op_join.py
datara-backend/worker/executors/op_merge.py
datara-backend/worker/executors/op_replace.py
datara-backend/worker/executors/op_sample.py
datara-backend/worker/executors/op_script.py
datara-backend/worker/executors/op_select.py
datara-backend/worker/executors/op_sort.py
datara-backend/worker/executors/op_split.py
datara-backend/worker/executors/op_udf.py
datara-backend/worker/executors/out_db.py
datara-backend/worker/executors/out_file.py
datara-backend/worker/executors/p_filter.py
datara-backend/worker/executors/p_join.py
datara-backend/worker/executors/p_window.py
datara-backend/worker/executors/s_cdc.py
datara-backend/worker/executors/s_kafka.py
datara-backend/worker/executors/src_db.py
datara-backend/worker/executors/src_file.py
datara-web/src/App.vue
datara-web/src/graph/model/__tests__/resolveNodeSchema.test.ts
datara-web/src/graph/model/index.ts
datara-web/src/graph/model/specSchema.ts
datara-web/src/graph/workbench/DataNode.vue
datara-web/src/graph/workbench/GraphWorkbench.vue
datara-web/src/graph/workbench/Inspector.vue
datara-web/src/graph/workbench/__tests__/DataNode.test.ts
datara-web/src/graph/workbench/pages/BoardPage.vue
datara-web/src/graph/workbench/pages/StreamNodePage.vue
datara-web/src/router/routes.ts
datara-web/src/services/__tests__/lineageUtils.test.ts
datara-web/src/services/ideApi.ts
datara-web/src/services/lineageApi.ts
datara-web/src/services/mock/lineageUtils.ts
datara-web/src/views/ErCanvasView.vue
datara-web/src/views/LineageView.vue
datara-web/src/views/TaskCenterView.vue
datara-web/src/views/__tests__/LineageView.test.ts
datara-web/src/views/dag/InstanceRunsView.vue
datara-web/src/views/ide/components/ExplorerTree.vue
datara-web/src/views/model/ModelDesignView.vue
datara-web/src/views/model/ModelLineageView.vue
datara-web/src/views/qc/QcAlarmView.vue
datara-web/src/views/qc/QcExceptionView.vue
datara-web/src/views/qc/QcReportView.vue
datara-web/src/views/qc/QcRuleView.vue
datara-web/src/views/qc/QcScoreView.vue
datara-web/src/views/qc/QcTaskView.vue
datara-web/src/views/std/StdApprovalView.vue
datara-web/src/views/std/StdCodeView.vue
datara-web/src/views/std/StdElementView.vue
datara-web/src/views/std/StdMappingView.vue
datara-web/src/views/std/StdNamingView.vue
docs/increments/I18-增量实施稽核-20261012.md
```

Untracked（32）：

```text
_build_demo_doc.py
_make_test_workbook.mjs
_verify_workbook.mjs
datara-backend/api/qc.py
datara-backend/api/std.py
datara-backend/common/qc_engine.py
datara-backend/common/std_engine.py
datara-backend/tests/test_ide_split.py
datara-backend/tests/test_io_executors.py
datara-backend/tests/test_qc_api.py
datara-backend/tests/test_qc_engine.py
datara-backend/tests/test_std_api.py
datara-backend/tests/test_tabular_executors.py
datara-backend/worker/executors/_tabular.py
datara-web/src/services/qcApi.ts
datara-web/src/services/stdApi.ts
docs/increments/I19-数据开发IDE对象编辑.md
docs/increments/I21实现核验-20261013.md
docs/increments/I22实现核验-20261013.md
docs/increments/I26-执行器与全链路推进记录-20261013.md
docs/increments/I27-browser-use联调取证-20261013.md
docs/增量开发菜单晋级策略.md
outputs/qa_20261011/2026-10-10-一期功能实测包.xlsx
outputs/qa_20261011/2026-10-10-一期功能实测包.xlsx.inspect.ndjson
outputs/qa_20261011/2026-10-10-一期功能实测报告.md
outputs/qa_20261011/focus-results.json
outputs/qa_20261011/ide-export-1791770416368.csv
outputs/qa_20261011/ide-export-1791770448624.csv
outputs/qa_20261011/ide-retest-results.json
outputs/qa_20261011/lineage-retest-results.json
outputs/qa_20261011/stream-retest-results.json
outputs/qa_20261011/workbook-inspect.json
```

#### r3-s9：`D:/需求/数据治理工具/Datara/.worktrees/r3-s9`

Tracked 修改（8）：`.aoci/baseline.json`、`datara-web/deploy/r3-s9-i18-preview.cjs`、`datara-web/deploy/test_r3_s9_legacy_preview_page.py`、`datara-web/public/rebuild-validation-r3-s9.html`、`datara-web/tests/perf/last-bench.json`、`docs/increments/2026-10-14-datara-platform-rebuild-design.md`、`docs/increments/2026-10-14-datara-platform-rebuild.md`、`docs/increments/R3-S9-开始前影响分析.md`。

Untracked（27）：

```text
datara-backend/datara-backend/tests/rebuild/test_governance_legacy_migration_service.py
docs/increments/R4-SYNC-开始前影响分析.md
docs/increments/evidence/R3/r3s9-20261015104539-b5f5d8.json
docs/increments/evidence/R3/r3s9-20261015112406-c9fa7d.json
docs/increments/evidence/R3/r3s9-20261015121142-3cedfb.json
docs/increments/evidence/R3/r3s9-20261015122825-89f9f1.json
docs/increments/evidence/R3/r3s9-20261015123031-faa8d2.json
docs/increments/evidence/R3/r3s9-20261015123056-a9c391.json
docs/increments/evidence/R3/r3s9-20261015123133-855ea2.json
docs/increments/evidence/R3/r3s9-20261015124843-dc81df.json
docs/increments/evidence/R3/r3s9-20261015125654-0356f5.json
docs/increments/evidence/R3/r3s9-20261015132632-d31f45.json
docs/increments/evidence/R3/r3s9-20261015140013-680f56.json
docs/increments/evidence/R3/r3s9-20261015140025-a6878e.json
docs/increments/evidence/R3/r3s9-20261015140154-db7020.json
docs/increments/evidence/R3/r3s9-20261015140204-080915.json
docs/increments/evidence/R3/r3s9-admin-project-list-remote-20261015.txt
docs/increments/evidence/R3/r3s9-import-scope-guard-remote-final-20261015.md
docs/increments/evidence/R3/r3s9-remote-final-20261015.txt
docs/increments/evidence/R3/s9-i18-import-approval-and-auth-gate-20261015.md
docs/increments/evidence/R3/s9-local-review-fixes-20261016.txt
infra/r3_s9_remote_final.py
infra/r3_s9_restore_api_config.py
infra/r3_s9_rotate_isolated_credential.py
infra/r3_s9_ui_polyfill_runner.cjs
infra/run_r3_s9_ui_polyfill.ps1
{{.Destination}}
```

#### 2d99：`C:/Users/Administrator/.codex/worktrees/2d99/Datara`

Tracked 修改（6）：`datara-web/public/rebuild-validation-r4.html`、`docs/increments/2026-10-14-datara-platform-rebuild-design.md`、`docs/increments/2026-10-14-datara-platform-rebuild.md`、`docs/increments/R4-开始前影响分析.md`、`docs/increments/R4-设计文档.md`、`docs/increments/重建执行约法与台账.md`。

Untracked（5）：`.agents/skills/browser-use-playwright-fallback/SKILL.md`、`.agents/skills/browser-use-playwright-fallback/evals/evals.json`、`docs/increments/R4-SYNC-开始前影响分析.md`、`docs/increments/evidence/R4/r4-s3-login-prefilled.txt`、`docs/increments/evidence/R4/r4-s3-playwright.txt`。其 19 个 detached 独有提交按 `git log` 留在当前 HEAD 历史；无 branch/tag 可在 worktree 外保护，须优先保留。

#### 6789 当前会话工作区与嵌套 `main`

父 checkout `C:/Users/Administrator/.codex/worktrees/6789/Datara` 有 9 个未跟踪文件：

```text
datara-backend/rebuild/sql_ide/__init__.py
datara-backend/rebuild/sql_ide/ddl_diff.py
datara-backend/rebuild/sql_ide/ddl_plan.py
datara-backend/rebuild/sql_ide/ddl_policy.py
docs/increments/2026-10-17-R4-DEP-RES正式BE契约草案-v1.md
docs/increments/2026-10-17-R5-A-SSE传输与恢复语义草案-v1.md
docs/increments/evidence/R2/trae-r2-r7-independent-review-20261017.md
docs/increments/evidence/R5/dbx-object-driver-operation-matrix-20261017.md
docs/increments/evidence/R7/README.md
```

父 checkout 另报告 `?? main/`，这是下面独立注册的嵌套 checkout，不把它误算成普通文件资产。父 checkout HEAD `60c5485` 为 main 祖先，且被既有 archive tag 包含；无 tracked 修改。上述 9 个新增文件未提交，未保存到 commit/tag。

嵌套 checkout `C:/Users/Administrator/.codex/worktrees/6789/Datara/main`（branch `codex/r6-schedule-endpoints`）有 3 个 tracked 修改：`datara-backend/rebuild/api/app.py`、`datara-backend/rebuild/datasource/metadata.py`、`docs/handoff/2026-10-16-并行协作分工.md`；另有 6 个未跟踪文件：

```text
datara-backend/rebuild/variables/__init__.py
datara-backend/rebuild/variables/references.py
docs/increments/evidence/2026-10-17-standard-v2-feedback-disposition.md
docs/increments/evidence/DBX-DS-review-20261017.md
docs/increments/evidence/R2/r2-variable-reference-parser-20261017.md
docs/increments/evidence/R5/r5-routine-catalog-source-delta-20261017.md
```

嵌套 HEAD `305187e` 为 canonical main 祖先，且由现存 `codex/r6-schedule-endpoints` branch ref 引用；其 dirty/untracked 差异仍未保存。本路径就是当前 Codex 会话工作区：本轮只读盘点，不对其文件或 git 状态做任何变更。

### 本批结论与后续

四个候选及 6789 的嵌套 checkout 全部暂留。b245 的提交由 branch 保底；r3-s9 与 6789 两个已提交基线在 main 历史中可达（其中 r3-s9、6789 父 checkout 的历史另有 archive tag 包含）；2d99 的 19 个独有 detached commits 无 branch/tag 保底。所有列明的 tracked 修改和 untracked 文件均未提交，不能视为保全。后续可由 owner 评审后为 detached 独有历史建立归档 branch/tag；对 dirty tracked 变更导出 patch，对 untracked 文件显式快照/打包，或在确认可恢复性后使用包含 untracked 的 stash。任何保全方案及后续删除/tag/prune 均由主线程评估，本轮不执行。
