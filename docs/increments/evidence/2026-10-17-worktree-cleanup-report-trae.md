# Trae 名下 worktree 清理报告（T-2 / 心跳 #54 执行令产出）

> 执行线：Trae 实施线；执行时点：2026-10-17；执行依据：心跳 #54 用户裁定（清理执行+六步安全标准）。
> 范围：项目 `.worktrees/` 内 trae 系 7 个 worktree；主工作区 main 零触碰；零远端 push。

## 0. 基线核对（六步标准第 1 步前置）

- 本线实测 7 个 trae 系 worktree 与 #54 基线**完全一致**（deploy-contract-repairs / i7-i9-fe / r3-s9-fe-fix / r5-ide-fe / s9-operator-token / trae-phase0-audit / trae-r4-red），7/7 全部带分支检出（无 detached HEAD）。
- 实测与基线的差异均在**非本线域**（如实登记，不代清不代裁）：
  - `.codex/worktrees/` 目录 23 个、registry 注册 19 项（含 6789 嵌套 main 一项）；5 个目录未注册（4f86/645a/8015/f289/fa14，疑为已 remove 后残留空壳）——归 Codex 核处。
  - `.worktrees/supervision-repro-848` 目录存在但**不在** `git worktree list` 注册表——归监督线核处。
- 以上差异按 #54「先报心跳再动手」精神在心跳 #55 同步通报；本线范围无差异，正常执行。

## 1. 删除清单（2 个，干净区，六步全过）

| worktree | HEAD | 分支（保留） | 归档 tag（保底） | 脏区检查 |
|---|---|---|---|---|
| `.worktrees/s9-operator-token` | `e39a19f` | `trae/s9-operator-token` | `archive/trae/s9-operator-token` | CLEAN |
| `.worktrees/trae-phase0-audit` | `76d540c` | `trae/phase0-audit` | `archive/trae/phase0-audit` | CLEAN |

删除动作：`git worktree remove <path>`（无 `--force`）×2 → `git worktree prune` → `git worktree list` 复核通过（两路径均消失、目录已不存在）。

## 2. 保留-脏区清单（5 个，标准第 4 步：porcelain 非空不得删除，等用户裁定）

| worktree | HEAD | 分支（保留） | 脏项 | 定性（O7 实证） |
|---|---|---|---|---|
| `.worktrees/deploy-contract-repairs` | `9c8adea` | `trae/deploy-contract-repairs` | `M datara-web/tests/perf/last-bench.json` | 自动生成性能基准工件（generatedAt 时间戳+指标值更新） |
| `.worktrees/i7-i9-fe` | `9167577` | `trae/i7-i9-red` | `M datara-web/pnpm-lock.yaml` + `M tests/perf/last-bench.json` | lockfile 漂移 + 同上基准工件 |
| `.worktrees/r3-s9-fe-fix` | `41f9346` | `trae/r3-s9-fe-fix` | `M datara-web/tests/perf/last-bench.json` | 同上基准工件 |
| `.worktrees/r5-ide-fe` | `e3493f3` | `trae/r5-a-red` | `M datara-web/tests/perf/last-bench.json` | 同上基准工件 |
| `.worktrees/trae-r4-red` | `8ddacd5` | `trae/r4-red` | `M docs/increments/evidence/R4/trae-red-pages-local-20261016.txt` | **内容等同 touch**（diff 零行，CRLF/mtime 级；文件内容与 HEAD 完全一致） |

裁定提示（供用户参考，不代裁）：除 i7-i9-fe 的 pnpm-lock.yaml 外，全部脏项为自动生成工件或内容等同 touch；若用户裁定「可弃」，下批可用同标准补删（tag 先行不变）。

## 3. tag 清单（第 2 步，tag 一律不删）

- `archive/trae/s9-operator-token` → `e39a19f`
- `archive/trae/phase0-audit` → `76d540c`
- 保留-脏区 5 个未打 tag：其 HEAD 均由分支引用钉住（第 3 步分支全保留），删除前再按标准补 tag。

## 4. 分支保留核对（第 3 步）

7 个 trae 系分支全部原样保留（含 15 个未并入分支口径内）：`trae/deploy-contract-repairs`、`trae/i7-i9-red`、`trae/r3-s9-fe-fix`、`trae/r5-a-red`、`trae/s9-operator-token`、`trae/phase0-audit`、`trae/r4-red`。**零分支删除**。

## 5. P0-2/P0-3 关联注记

- `trae/r4-red` 分支在已并入 main 的 `0824069` 之后尚有 2 提交：`8ddacd5`（R2 残留：VariableValidationView 横幅诚实化修正，属 P0-2 收尾范围）与 `e0a21ff`（R7 metricsApi 接线 6/6 方法+I9→R7 词形，即任务池 P0-3 指定并入对象）。
- worktree 目录移除不影响上述分支引用；后续合并走分支引用操作。

## 6. 监督抽核锚点

- 复核命令：`git worktree list`（应无 s9-operator-token / trae-phase0-audit）；`git tag -l "archive/trae/*"`（2 个）；`git branch -a | grep trae/`（7 分支在）；`git -C .worktrees/<dir> status --porcelain`（5 保留项脏项与上表一致）。
