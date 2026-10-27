# Ops 资源处置 · IMPL-v4-15（对账段）派给空闲席位

- **席位**：监督 Ops｜**时间**：2026-10-23T03:10+08:00｜**水位**：`v3-0080`｜**版本**：v1.0
- **来源**：用户直接指令（原话：「执行」）；承接 Ops 状态报告 §4 P2「15 派 codex 或空档线」
- **职权边界**：本件为 Ops 职权内的**资源/席位分配决定**；不写队列投影，`DISPATCH_ASSIGNED` 由 **Flow** 落。

---

## 一、决定

**批准** Task 派单提议（`outbox/任务/2026-10-23-task-dispatch-proposal-impl-v4-15.md`），**IMPL-v4-15 立即派给空闲席位**：

1. **首选 codex**（若已上线并 ACK——首包最适纯文档票，零代码冲突、零远测占用）；
2. **否则 claude / EXEC-3**，排在其 03 本地段之后；若 10:00 检查点前 03 未获重派，EXEC-3 **立即接 15**，不空等；
3. **不叠加**：EXEC-2 持 13a、EXEC-1 保留 01 租约执行，均不接 15。

## 二、依据（资源侧）

- **零远程窗口占用**：15 为 **P3 纯对账文档**，无 1.9 远测需求 → 与 D-PARALLEL-2 的双线窗口**不争用**。
- **路径隔离**：`paths` 仅 `docs/increments/evidence/2026-10-23-F2-F3-migration-reconciliation.md`（新）+ `datara-backend/**`（只读）；与在飞票面**零交集**，无覆盖冲突。
- **配额**：全局并发上限 8，当前实际线 3；派 15 后不触顶，配额不构成约束。

## 三、四字段（沿用 Task 提议，Ops 核验一致）

| 字段 | 值 |
|---|---|
| base_priority | P3 |
| effective_priority | P3 |
| priority_basis | MAINTENANCE，无运行时影响；纯对账文档，已解耦 01 |
| priority_override | null |

## 四、验收与证据（Ops 核验，不变）

- 验收：对账表全量、挂载状态矩阵、挂载窗口前置清单；`git diff` 于 `datara-backend/**` **为空**；不删/不改名/不触 `app.py`；NO_SECRET 0；Acceptance 独立复核 PASS。
- 证据：对账表原件 + `git status/diff` 空证明 + 逐件行号；执行者/时间戳/命令留痕。

## 五、路由

Task 提议（已具）→ **Flow 批 15 准入并落 `DISPATCH_ASSIGNED`** → 执行席本地交付 → EVIDENCE_READY → Acceptance 复核（纯文档）→ 集成窗。

---

## 修订记录

| 版本 | 时间 | 修订 | 依据 |
| --- | --- | --- | --- |
| v1.0 | 2026-10-23T03:10+08:00 | 初版：批准 15 派单（codex 优先 / EXEC-3 兜底） | 用户授权 + Task 提议 |

—— 监督 Ops / epoch 3 / 2026-10-23T03:10+08:00 / 水位 v3-0080 / 请 Flow 落 DISPATCH_ASSIGNED
