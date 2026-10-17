# T-2 worktree 脏区清理报告 — Trae 批次 2（batch2）

> 依据：心跳 #65 T-2 脏区裁定令（用户 2026-10-17 批「按建议执行」），甲类 Trae 名下 5 个，本线立即执行。
> 通用前提遵守：无 detached checkout（5 个均挂分支，无需补 tag）；分支一律保留；未用 `--force` 推送类操作（`git worktree remove --force` 仅删除本地工作目录，不动分支与远端）；完成后本报告 + 心跳回执。

## 一、执行明细（5/5 完成）

| worktree | 分支（保留✓） | HEAD | 脏项（删前核验） | 处置 |
|---|---|---|---|---|
| `.worktrees/deploy-contract-repairs` | trae/deploy-contract-repairs | 9c8adea | M datara-web/tests/perf/last-bench.json | 删 |
| `.worktrees/i7-i9-fe` | trae/i7-i9-red | 9167577 | M datara-web/pnpm-lock.yaml；M tests/perf/last-bench.json | 删 |
| `.worktrees/r3-s9-fe-fix` | trae/r3-s9-fe-fix | 41f9346 | M datara-web/tests/perf/last-bench.json | 删 |
| `.worktrees/r5-ide-fe` | trae/r5-a-red | e3493f3 | M datara-web/tests/perf/last-bench.json | 删 |
| `.worktrees/trae-r4-red` | trae/r4-red | 8ddacd5 | M docs/increments/evidence/R4/trae-red-pages-local-20261016.txt（#55 已证 diff 零行） | 删 |

与 #65 判定差异披露（诚实留痕）：#65 载明 Trae 脏项=last-bench.json×4 + touch 级证据 txt×1（5 项）；删前实测 6 项——`i7-i9-fe` 额外存在 `pnpm-lock.yaml` 修改，属 worktree 内依赖安装副作用（lockfile 以 main 为准，无业务价值），同属「零抢救价值」类，一并删除。

## 二、执行方式与验证

1. 删前逐 worktree `git status --porcelain` 核验脏项（见上表，无未披露的业务文件）。
2. `git worktree remove --force <path>`：git 元数据（worktree 注册）全部移除成功；磁盘目录因文件锁残留。
3. 残留目录 `Remove-Item -Recurse -Force` 补删：5/5 删除成功。
4. 删后验证：
   - `git worktree list`：Trae 名下 5 个 worktree 注册全部消失；主仓 main 正常。
   - `git branch --list 'trae/*'`：7 个分支全保留（deploy-contract-repairs / i7-i9-red / phase0-audit / r3-s9-fe-fix / r4-red / r5-a-red / s9-operator-token）。
   - `.worktrees/` 目录仅剩 Codex 名下 2 个（`q1-dag-catalog-integrate`、`r3-s9`——#65 甲类 Codex 执行项，本线未触碰）。

## 三、边界声明

- Codex 名下 7 甲 + 4 乙 worktree 本报告未触碰（按 #65 归属分工，由 Codex 线执行）。
- 无远端操作、无分支删除、无 tag 变更、无 `--force` 推送。
- 本报告对应 git 提交为 pathspec 单文件。

- worktree / 分支 / HEAD：main pathspec docs（本报告）；Trae worktree 清理不影响任何分支。
- Resolved: T-2 Trae 名下甲类 5 项清理完成（batch2）。
