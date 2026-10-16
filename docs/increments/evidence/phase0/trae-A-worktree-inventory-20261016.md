# 阶段0 槽位 A：worktree / dirty / owner 只读快照清单（2026-10-16）

- 采集时间：2026-10-16 22:4x（Asia/Shanghai）
- 执行者：Trae 质量监督线（只读职权内；用户裁定甲授权补 A 槽）
- 采集锚：canonical main `4a23d37`
- 裁定锚：0.4 A/B/C 裁定**甲**（用户 2026-10-16 批复）——B/C 判定已被后续证据实质吸收，A 以本清单补齐；0.4 关闭、阶段0 六项全关
- owner 口径：按分支前缀推断（`codex/*`→Codex、`trae/*`→Trae 实施线、`(detached)`→待认领）；**owner 归属待 Codex 会签确认**，本清单不构成清理/合并/删除授权
- 边界：只记录事实；执行附录 §5.1 A 槽禁令不变（不清理、不 checkout 覆盖、不合并）

## 1. 总量与结论

- worktree 总数：**28**（主工作区 + 27 worktree）；此前心跳所记 23/24 均过期，P3 计数项就此关闭
- 含脏文件工作区 13 个，脏文件合计 **265**；干净 15 个
- 风险热点：main 46（§3 分解）、b245 96、correction-plan 62、r3-s9 35

## 2. 逐 worktree 快照表

路径缩写：`.codex/X` = `C:\Users\Administrator\.codex\worktrees\X\Datara`；`.worktrees/Y` = `D:\需求\数据治理工具\Datara\.worktrees\Y`；`main` = `D:\需求\数据治理工具\Datara`。

| # | 路径 | 分支 | HEAD | dirty | owner 推断 |
|---|---|---|---|---|---|
| 1 | main | main | 4a23d37 | 46 | 共享（监督/实施/Codex 均写入，见 §3） |
| 2 | .codex/134a | (detached) | bec06af | 2 | 待认领 |
| 3 | .codex/2d99 | (detached) | 93d5861 | 10 | 待认领 |
| 4 | .codex/6789 | (detached) | 60c5485 | 1 | 待认领 |
| 5 | .codex/93be | codex/i19-i20-carry-forward | 2e5cfd1 | 0 | Codex |
| 6 | .codex/b245 | codex/i18-completion | 5ca62e5 | 96 | Codex（脏文件最多，性质待 Codex 会签） |
| 7 | .codex/correction-plan | codex/correction-plan | 9afb864 | 62 | Codex（活跃 WIP，R2/R4/R5/收尾 29 问来源） |
| 8 | .codex/i19-i20-main-port | codex/i19-i20-main-port | c6cf9f1 | 0 | Codex |
| 9 | .codex/i19-i20-write-path | codex/i19-i20-import-executors | b601499 | 0 | Codex |
| 10 | .codex/phase0-matrix-v5-fix | codex/phase0-matrix-v5-fix | 641fff6 | 0 | Codex |
| 11 | .codex/phase0-q-correction | codex/phase0-q-correction | 4c7200a | 5 | Codex（在飞） |
| 12 | .codex/phase0-q-detail-port | codex/phase0-q-detail-port | 22031b7 | 0 | Codex |
| 13 | .codex/r3-i19-i20-closeout | codex/r3-s9-i19-i20-closeout | e375d87 | 0 | Codex |
| 14 | .codex/r5b-ddl-policy | codex/r5b-ddl-policy | 3fdc851 | 0 | Codex（DDL helpers 已并入 main） |
| 15 | .codex/sync-q-handoff-04 | codex/sync-q-handoff-04 | bf89236 | 0 | Codex（已并入 main） |
| 16 | .worktrees/codex-q1-dag-catalog-fix | codex/q1-dag-catalog-fix | 27b3499 | 0 | Codex |
| 17 | .worktrees/codex-r3s9-integration | codex/r3-s9-main-integration | 6342d5b | 0 | Codex |
| 18 | .worktrees/codex-s9-runner-gate-fix | codex/s9-runner-gate-fix | 0826174 | 0 | Codex |
| 19 | .worktrees/deploy-contract-repairs | trae/deploy-contract-repairs | 9c8adea | 1 | Trae |
| 20 | .worktrees/i7-i9-fe | trae/i7-i9-red | 9167577 | 2 | Trae（schedule/stream/metrics 页来源） |
| 21 | .worktrees/q1-dag-catalog-integrate | codex/q1-dag-catalog-integrate | 6b0db9b | 3 | Codex |
| 22 | .worktrees/r3-s9 | codex/r3-s9 | 49f9a6f | 35 | Codex（S9 执行现场，按 R3 裁定留痕不重放） |
| 23 | .worktrees/r3-s9-fe-fix | trae/r3-s9-fe-fix | 41f9346 | 1 | Trae |
| 24 | .worktrees/r4-sync-contract | codex/r4-sync-contract | 68e2c4f | 0 | Codex（R4 RED 契约锚 `e6a3174` 所在分支） |
| 25 | .worktrees/r5-ide-fe | trae/r5-a-red | e3493f3 | 1 | Trae（R5-A/B 页来源） |
| 26 | .worktrees/s9-operator-token | trae/s9-operator-token | e39a19f | 0 | Trae |
| 27 | .worktrees/trae-phase0-audit | trae/phase0-audit | 76d540c | 0 | Trae（D/E 原始报告载体，保留不合入） |
| 28 | .worktrees/trae-r4-red | trae/r4-red | b4035fa | 0 | Trae（活跃：9 页 RED + FE 适配层） |

## 3. main 46 脏文件分解（canonical 工作区）

| 构成 | 数量 | 性质与归属 |
|---|---|---|
| infra/（untracked） | 23 | 来源未登记，待 Codex 会签（疑与 AOCI baseline 相关） |
| docs/（untracked） | 11 | 未提交文档，逐文件归属待会签 |
| 根目录用户自留文件（docx/xls/md，中文名） | 6 | 用户文件，任何 agent 禁触碰 |
| package-lock.json（untracked） | 1 | 来源待核（pnpm 工程出现 npm lock） |
| docker-compose.yml（M） | 1 | 已登记 P3（暂存归属处置中） |
| .aoci/baseline.json、aoci.code.txt（MM） | 2 | AOCI 收口窗（Codex 域；heartbeat #20 已披露，Trae 未触碰） |
| .claude/plans runbook（untracked） | 1 | Trae 线执行台账（本地维护，不提交） |

全部 46 项均为 untracked 或修改，**无删除项**；无 staged 凭据类文件。

## 4. 与其他登记项的联动

- **R1-R3 验证页归属（歧义处置 #9）**：8 个含 `rebuild/validation` 路由的 worktree（#20/21/16/24/18/27/25/28）中均无 identity/datasource/governance 页——归属仍需 `git log -S "rebuild/validation"` 历史反查 + 18091 部署栈溯源（Trae 实施线专项），本清单提供排查底册。
- 29 问答复闸、P1 契约冻结不受本清单影响（裁定甲不动 Codex 队列）。
- `git branch --contains` 显示 R4 RED 锚 `e6a3174` 仅存在于 `trae/r4-red`（与矩阵 §3 一致）。

## 5. 可复现命令

```powershell
git worktree list --porcelain | Where-Object { $_ -like 'worktree *' } |
  ForEach-Object { $_.Substring(9) } | ForEach-Object {
    $p=$_; $h=(git -C $p rev-parse --short HEAD 2>$null);
    $b=(git -C $p branch --show-current 2>$null); if(-not $b){$b='(detached)'};
    $d=@(git -C $p status --porcelain 2>$null).Count;
    "{0} | {1} | {2} | dirty={3}" -f $p,$b,$h,$d }
```
