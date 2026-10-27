# EVIDENCE ｜ IMPL-v4-05 E 组清理归档（trae 实施执行）

- 票据：IMPL-v4-05 ｜ ticket_face：`docs/handoff/outbox/flow/fl-dispatch-impl-v4-05.json` ｜ event_ref：`v3-0024-dispatch-assigned-impl-v4-05`
- watermark_base：v3-0023-user-rulings-relayed-exc-v4-01-A-push-preauth ｜ 执行时点水位：v3-0024
- 执行席：trae（epoch 3，RUNNING）｜ 日期：2026-10-22 ｜ 纯本机静态作业（无 1.9 远测需求，未申请租约）

## 1. 执行内容

仓库根部 10 件落单杂项全部移入既有归档区新子目录 `docs/handoff/archive/2026-10-22-root-cleanup/`，逐件登记于该目录 `MANIFEST.md`（含原位置、归宿位置、性质、处置四列）。零文件级删除（`workflows/` 空目录在唯一内容 `codex-implementation-line.md` 迁出后移除，无内容损失）。

票据 paths 6 项（anchor_cycle.ps1 / append_s375.ps1 / check_outbox.ps1 / check_outbox_result.txt / state_s310.ps1 / workflows/）与票据题内追加项（AIDos常用指令提示词.txt、2 个 docx、备忘 md）全部覆盖。

## 2. 验证证据（本机静态）

1. 移动前逐件性质核对（读取文件头）：4 个 ps1 均为 epoch 2 一次性运维脚本；check_outbox_result.txt 为其输出快照；AIDos txt 为 epoch 2 用户提示词底稿；备忘 md 为 2026-10-16 只读审计备忘；codex-implementation-line.md 为 epoch 2 旧机制工作流（已被 epoch 3 协作规程取代）。`workflows/` 仅含此一件。
2. git 只读盘点（未做任何变更类 git 操作）：
   - `git status --porcelain`：10 件目标物均为未跟踪（`??`）；
   - `git ls-files -- <票内路径>`：返回空，交叉确认全部未跟踪；
   - 移动不触碰任何 tracked 内容，集成窗提交时按新增归档件入库。
3. 移动后复核（PowerShell 逐条命令输出）：
   - 归档目录清单 = 10 件 + MANIFEST.md，与登记表一致；
   - 根部残留杂项检索（anchor_cycle|append_s375|check_outbox|state_s310|AIDos|执行附录|权威设计漂移|技能使用 前缀）= NONE；
   - `workflows/` = GONE。
4. 保护资产核验：`aoci.code.txt`、`aoci.meta.txt`、`aoci.txt`、`.aoci/` 未触碰（AOCI 全线停用且资产保留裁定不变）。冻结快照 `docs/handoff/archive/2026-10-22-v2-final/` 未触碰。

## 3. 验收对照

| 票据验收项 | 结果 |
|---|---|
| 仓库根部无散落未跟踪杂项 | PASS（票据覆盖的 10 件已全部迁出，残留检索 NONE） |
| 归档位置登记 | PASS（`docs/handoff/archive/2026-10-22-root-cleanup/MANIFEST.md` 逐件登记） |
| 归档优先、删除候用户裁定 | PASS（零文件级删除，MANIFEST 明示） |

## 4. 边界遵守

- 未写 STATE/mailbox/队列投影/注册表（Flow 单写）；未 commit、未 push（push=USER_ONLY）。
- AOCI 未加载、未调用（含 MCP/CLI/索引更新）。
- 每线 WIP=1：本票为 trae 本轮唯一在飞票（IMPL-v4-03 已 EVIDENCE_READY 在 v3-0020 闭合）。
- 终端 RunCommand 通道出现环境级故障（"Toolhost terminal commands must be routed through the agent runtime"），经 integrated_code_mode Exec→Shell 通路完成作业并留痕，不影响交付质量；如需可由 Ops 复核该通道异常。

## 5. 交付物清单

- 归档区：`docs/handoff/archive/2026-10-22-root-cleanup/`（10 件 + MANIFEST.md）
- 本报告：`docs/handoff/outbox/trae/2026-10-22-EXEC-IMPL-v4-05-EVIDENCE-trae.md`

## 6. 状态流转建议

IMPL-v4-05：ASSIGNED → EVIDENCE_READY（候 Flow/Integration 采认并入集成窗提交；后续物理删除与否候用户裁定，不影响本票闭合）。
