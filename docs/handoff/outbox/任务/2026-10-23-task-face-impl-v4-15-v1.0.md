# IMPL-v4-15 票面 **v1.0**（迁移挂载死码对账段）+ IMPL-v4-18 立项建议（挂载窗口）

- **发起**：Task / epoch 3 / 2026-10-23T02:39+08:00（实测）/ 基于 v3-0069
- **依据**：Decision 裁定 `DECISION-DEC-migration-direction-ruling`（方向 A 分阶段；15 可先做对账，不触 `app.py`；挂载窗口另立票）
- **关键变化**：原 15 的 `depends_on` 含 `IMPL-v4-01`（开 app.py 安全窗）。裁定明确**对账段不需要 01**，故本票解耦为纯文档段立即 READY；`app.py` 挂载移入 18。

---

## IMPL-v4-15｜迁移挂载死码对账（对账表 + 命名/映射定稿）

| 字段 | 值 |
|---|---|
| base_priority | P3 |
| effective_priority | P3 |
| priority_basis | MAINTENANCE，无运行时影响、既有状态非回归；裁定后由"候裁定"转为可开工的纯对账段 |
| priority_override | null |

- **依赖**：`DEC-migration-direction`（已裁 2026-10-23，候 Flow 采信）。**不再依赖 IMPL-v4-01**。
- **paths**：
  - `docs/increments/evidence/2026-10-23-F2-F3-migration-reconciliation.md`（新）
  - 只读引用：`datara-backend/rebuild/*/migrations.py`、`*/revisions/`、`datara-backend/rebuild/app.py`（**只读，禁改**）
- **验收标准**：
  1. 对账表覆盖全部 `migrations.py` 与 `revisions/` 件：外层版本锚（`v0001_*` 排序/登记面）↔ 内部 revision 号（`i17_*`、`r*`）逐件映射，含被测试断言者（如 `i17_0001` sshnode）与全仓零引用者（如 `i17_0002` runtime_node，登记为"挂载窗口一并接挂"）；
  2. 挂载状态矩阵：每模块「已挂载 / 未挂载 / create_all 兼容段 / 零引用」四态，含证据行号；
  3. 挂载窗口实施顺序与前置清单（供 18）；每模块幂等守卫要点、回滚落点（选项 C 口径）；
  4. **零代码改动**：`git diff` 于 `datara-backend/**` 为空；不删、不改名任何 revisions/migrations 件；不触 `app.py`；
  5. NO_SECRET 0 命中；Acceptance 独立复核 PASS。
- **授权路径**：Task 票面 → Flow 准入派单 → 执行席（建议 codex 上线后或 claude 空档线；路径仅新增 1 个证据 md，无代码冲突）→ EVIDENCE_READY → Acceptance 复核（纯文档，无远测需求）。
- **证据要求**：对账表原件 + `git status/diff` 空证明 + 逐件引用行号；本机即权威（文档段不需要 1.9），但仍须执行者/时间戳/命令留痕。

## IMPL-v4-18（Task 建议编号，候 Flow 登记）｜迁移挂载窗口

| 字段 | 值 |
|---|---|
| base_priority | P3 |
| effective_priority | P3 |
| priority_basis | 裁定落地序②：01 DONE 开 app.py 安全窗后的唯一挂载入口 |
| priority_override | null |

- **依赖**：`IMPL-v4-01` DONE + `IMPL-v4-15` PASS。
- **paths（预计）**：`datara-backend/rebuild/app.py`（单一有序 runner/lifespan 挂载 + 存在性幂等守卫）、挂载窗口证据件。
- **验收标准（预计）**：切换建表真源前全量 1.9 pytest GREEN；重复执行幂等零 DDL 变更/零 seed 漂移；回归即回退 create_all 并报 Ops。
- **状态**：BLOCKED（不占 READY 队首）；仅用于 DAG 登记，不派单。

---

## 版本记录

- **v1.0（2026-10-23T02:39）**：15 解耦为纯对账段（去 01 依赖）；18 立项建议登记。
- 替代关系：原 15 票面（增量 10 v1.3：`DEC-migration-direction` + `IMPL-v4-01` 双依赖）由本件升版，非静默改写。

---
Task / epoch 3 / 2026-10-23T02:39+08:00 / 水位 v3-0069 / 请 Flow 准入 15 并登记 18
