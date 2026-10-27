# 派单提议 · IMPL-v4-15（对账段）→ claude / EXEC-3（codex 优先）

- **发起**：Task / epoch 3 / 2026-10-23T02:51+08:00（实测）/ 水位 `v3-0080`
- **依据**：票面 v1.0（批 14 已登记 READY，`TICKETS_REGISTERED` v3-0078）；Ops 状态报告 §4 P2「15 派 codex 或空档线（30m 内）」
- **性质**：Task 派单建议（D3）；Flow 落 `DISPATCH_ASSIGNED`

## 四字段

| 字段 | 值 |
|---|---|
| base_priority | P3 |
| effective_priority | P3 |
| priority_basis | MAINTENANCE，无运行时影响；纯对账文档，裁定后已解耦 01 |
| priority_override | null |

## 依赖 / 路径 / 验收 / 证据

- **依赖**：`DEC-migration-direction`（已裁并入投影 v3-0071）；无其它。
- **paths**：`docs/increments/evidence/2026-10-23-F2-F3-migration-reconciliation.md`（新）；`datara-backend/**` 只读。
- **验收**：对账表全量（migrations/revisions ↔ `v0001_*`/`i17_*`/`r*` 映射）、挂载状态矩阵、挂载窗口前置清单；`git diff` 于 `datara-backend/**` 为空；不删/不改名/不触 `app.py`；NO_SECRET 0；Acceptance 独立复核 PASS。
- **证据**：对账表原件 + `git status/diff` 空证明 + 逐件行号；执行者/时间戳/命令留痕。纯文档，无远测需求。

## 执行席与顺序

1. **首选 codex**（若上线并 ACK——首包最适纯文档票，零代码冲突）；
2. 否则 **EXEC-3**，**排在其 03 本地段之后**（03 重派提议 v1.1 若获准）：先写 `e2e/sshNode.spec.ts`+`e2e/qc.spec.ts` 两件（关键路径），再对账表；若 10:00 检查点前 03 未获重派，EXEC-3 **立即接 15**，不空等；
3. EXEC-2 持 13a，不叠加；EXEC-1 保留 01 租约执行。

## 授权路径

Task 提议 → Flow 批 15 准入并派单 → 执行席本地交付 → EVIDENCE_READY → Acceptance 复核（纯文档）→ 集成窗。

---
Task / epoch 3 / 2026-10-23T02:51+08:00 / 水位 v3-0080 / 请 Flow 派单
