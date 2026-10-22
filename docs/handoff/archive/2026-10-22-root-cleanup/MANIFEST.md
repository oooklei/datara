# 根部落单物清理归档 MANIFEST（IMPL-v4-05）

- 日期：2026-10-22 ｜ 执行：trae（实施执行 Execution，epoch 3）
- 票据：IMPL-v4-05（E 组清理归档，P2，event_ref v3-0024-dispatch-assigned-impl-v4-05）
- 归档区：`docs/handoff/archive/2026-10-22-root-cleanup/`（既有归档区 `docs/handoff/archive/` 下的新日期子目录，未触碰冻结快照 `2026-10-22-v2-final/`）
- 处置原则：归档优先，零物理删除（仅 `workflows/` 空目录在内容迁出后移除，无内容损失）；任何文件级删除均候用户裁定

## 逐件归宿登记

| # | 原位置（仓库根部） | 归宿位置（本目录） | 性质 | 处置 |
|---|---|---|---|---|
| 1 | `anchor_cycle.ps1` | `anchor_cycle.ps1` | epoch 2 一次性运维脚本（duty cycle 三源+候收编面锚定） | 归档，保留原名 |
| 2 | `append_s375.ps1` | `append_s375.ps1` | epoch 2 一次性脚本（mailbox 追加 s375 前 TAIL/DUP 守卫） | 归档，保留原名 |
| 3 | `check_outbox.ps1` | `check_outbox.ps1` | epoch 2 一次性脚本（outbox 队列盘点，产出 check_outbox_result.txt） | 归档，保留原名 |
| 4 | `check_outbox_result.txt` | `check_outbox_result.txt` | 上脚本的输出快照（旧队列面 b/c/gov-wait/i1/sent 等） | 归档，保留原名 |
| 5 | `state_s310.ps1` | `state_s310.ps1` | epoch 2 一次性脚本（STATE.md S303 行归档前置守卫） | 归档，保留原名 |
| 6 | `AIDos常用指令提示词.txt` | `AIDos常用指令提示词.txt` | epoch 2 时代用户提示词底稿（B裁定席 duty cycle 循环令等） | 归档，保留原名 |
| 7 | `执行附录与权威稿对比备忘-2026-10-16.md` | `执行附录与权威稿对比备忘-2026-10-16.md` | 2026-10-16 只读对比审计备忘（trae 质量监督，基线 main 61be8d5） | 归档，保留原名 |
| 8 | `权威设计漂移事故复盘与教训-2026-10-16.docx` | `权威设计漂移事故复盘与教训-2026-10-16.docx` | 2026-10-16 漂移事故复盘文档（docx，二进制） | 归档，保留原名 |
| 9 | `技能使用说明书.docx` | `技能使用说明书.docx` | 技能使用说明文档（docx，二进制） | 归档，保留原名 |
| 10 | `workflows/codex-implementation-line.md` | `codex-implementation-line.md` | epoch 2 codex 实施线持续交付工作流（R-43/mailbox 旧机制，已被 epoch 3 协作规程取代）；`workflows/` 仅此一件 | 归档后移除空目录 `workflows/` |

## 登记备注

1. git 状态（移动前只读盘点）：上述 10 件均为未跟踪（`??`），无 tracked 内容受影响；`git ls-files` 对票内路径返回空，交叉确认。
2. 票据 paths 6 项（1-5 + workflows/）与票据题内追加项（6-9）全部覆盖；`aoci.code.txt`、`aoci.meta.txt`、`aoci.txt`、`.aoci/` 为 AOCI 保护资产，不在票内、未动。
3. 归档位置已在本 MANIFEST 逐件登记；物理删除未执行，如需删除候用户裁定。
