# 库存核对 · 派单升级与票面预塑（增量 14 · v3-0069）

- **席位**：Task / epoch 3 / **RUNNING**
- **水位**：`v3-0069-projection-realignment-batch-12`（state / snapshot / 事件流 69 行一致）
- **基线**：增量 10 v1.3（07~15）、增量 12（16/17）、增量 13 v1.1（07 票面已准入 v3-0063）
- **本轮动作**：① 08 重派升级呈请；② 唤醒裁定席；③ 1.9 串行窗排程建议；④ 02b/03 票面预塑（不铸空壳票）；⑤ 缺陷登记

---

## 一、读数（v3-0069）

| 队列 | 读数 | 要点 |
|---|---|---|
| DECISION | ready 2 | D05→13；migration-direction→15（另需 01） |
| IMPLEMENTATION | ready **0** / assigned 1 / in_progress 5 / blocked 10 | assigned=08（trae）；in_progress=01 REWORK、03 REWORK、02a/07/16 EVIDENCE_READY；DONE=04、05 |
| REMOTE_TEST | LEASED 1 / READY 4 | LEASE-01 至 **15:28:04**（余 ~12h55m）；RT-03/02a/07/16 全 LEASE_DEFERRED |
| EXCEPTION | 未决 0 | 04 项已核销 |

**判定**：投影 READY=0 已持续一个多调度周期；实施线唯一可立即消费的工作是 **08 重派**（详见 §三）。BLOCKED 10 票均不占 READY 队首，维持原位。

## 二、上轮产出接纳确认（闭环增量 13）

| 增量 13 事项 | 接纳结果 | 状态 |
|---|---|---|
| DEC-v4-D05 / DEC-migration-direction 正式提交 | v3-0062 DEC 入队 | ✅ 队列 ready 2，候裁定 |
| 07 票面 v1.0→v1.1（解 E-1） | v3-0063 TICKET_FACE_REVISED | ✅ 执行席依 v1.1 交付 EVIDENCE_READY（v3-0066） |
| 16 派单面锚点事件缺失（§五-1） | v3-0067/v3-0068 补齐 | ✅ 缺陷核销，16 已 EVIDENCE_READY |
| 08 重派建议 / 唤醒看门狗 | **未落** | ⏳ 见 §三、§六 |

## 三、派单面：两条可执行杠杆

### 3.1 IMPL-v4-08 重派（升级呈请：请 Flow 立即出 `DISPATCH_REASSIGNED`）

- **新事实（实测 outbox/trae/ mtime）**：trae 末件 2026-10-22T15:33，至今 **约 11h 零产出、零心跳**；08 派单（18:47，v3-0053）后 **7h45m 无 ACK**。EXEC-3 于 02:08 交付 16 后**本地 WIP 归零**；EXEC-2 交付 07 后同为空档（仅剩 RT 排队）。重派不发新路径冲突。
- **建议**：08 执行席 trae → **claude / EXEC-3**；票面内容、优先级、路径、验收、证据**零变更**；单实例守则不变（Flow 重派前 trae 若正式 ACK 则按首 ACK 定席；重派生效后 trae 不得触碰 08 路径）。
- **票面四字段**（沿用）：`base_priority=P2` / `effective_priority=P2` / `priority_basis="15-P0 是 15.2-A 建模唯一未满足前置（门 1/门 7）；G 组六票链头"` / `priority_override=null`
- **依赖**：无票面依赖（15.2 立项已批）；**下游**：09→10→11→12 全链。
- **验收/证据**：不变（三表冻结 + 端点清单与状态机 + 权限/错误码 + 安全红线 + Acceptance 独立评审 PASS + 1.9 契约测试 GREEN + 不建表不写实现；证据依 `evidence_rule` 绑定租约）。
- **授权路径**：Task 提议 → Ops 裁定可行（D3，可逆）→ Flow 执行重派；trae 静默按 A1 另行升级，不因重派豁免。

### 3.2 唤醒裁定席（其自暂停唤醒条件 1/2 已满足）

- 裁定席 00:05 自暂停，唤醒条件明列「DEC-v4-D05 正式提交」「DEC-migration-direction 入队」——**双双于 v3-0062 满足**，但至今无裁定席心跳/产出。
- Task 无权唤醒他席；请 **Ops/采集器按点名唤醒**。若裁定席持续静默，13（P2 DELIVERY）与 15（P3）继续挂起，且 14 的 D4 envelope 亦无承接（§五-3）。

## 四、1.9 串行窗排程建议（关键路径，租约归属 Integration）

- **串行序（Task 建议）**：`RT-03 → RT-02a → RT-07 → RT-16`（到达序 + 依赖：03 释放 e2e 目录锁，02a/07 用例依赖 03 基础设施口径）。
- **建议窗位**：LEASE-01 释放/到期后立即起窗；以 Ops A2 **10:00 检查点**为 go/no-go：若 LEASE-01 执行段届时仍无产物（evidence_dir 未建、隔离树零写入），建议 Integration **提前释放**，使 4 项在 15:28 前完成，而非全部滑租约。
- **理由**：4 项 RT 全属 EVIDENCE_READY 票的 ENV_VERIFIED 前置；滑窗一日即 02a/07/16 三票验收全延，17 壳收口随之延。
- **边界**：窗口时序、执行者指名、1.9 复测均为 Integration 职权，Task 仅排程建议，不代签。

## 五、依赖预塑（本轮不新铸空壳票）

### 5.1 IMPL-v4-02b 预塑：残留缺口审计（01 契约冻结后即可派）

- **实证（Task 只读）**：02b 三路径**均已存在且为未跟踪件**——`datasourceApi.ts`（10-21 13:02）、`rolePermissions.ts`（10-21 20:41）、`PermissionMatrixView.vue`（10-21 20:42），与 15.1-C/inc17 在途面重合（增量 13 §二已见 routes.contract.test.ts 含 `/sec/perm` 与 PermissionMatrixView）。
- **风险**：解冻后执行席若按票面全量重写，将覆盖他票在途实现。
- **建议（01 冻结时随 TICKET_FACE_REVISED 落地）**：票面加**步骤 0 只读残留审计**（`git status/diff` 对照契约，出具 delta 清单），仅改增量；验收追加「零重复实现证明 + 与他票在途改动逐行归因」。
- **四字段**：`P1 / P1 / "前端关键路径 02b 段；D01 选项① 落地段" / null`；**依赖**：DEC-D01（已裁）、IMPL-v4-01 契约冻结；**证据**：1.9 端到端 GREEN（datasource/rolePermissions/PermissionMatrix 域）+ 契约测试。

### 5.2 e2e 用例件缺口（02a/07 的 RT 前置，无票承接）

- **实证**：`datara-newweb/e2e/` 仅 `llm-models.spec.ts`（未跟踪，03 在途）；RT-02a 所需 sshNode 用例、RT-07 所需 qc 用例**均不存在且无票主**——两票 RT 若照跑必红。
- **方案 A（Task 推荐）**：03 票面 v1.0→v1.1 增补 `e2e/sshNode.spec.ts`、`e2e/qc.spec.ts`（目录已在 03 锁内；纯测试件、零产品码；与 03 REWORK 缺口不冲突）。**四字段**：`P2 / P2 / "验收链补全（决策卡 C 组）" / null`；依赖：DEC-D02（已裁）；验收追加：两用例件实存且 1.9 实跑纳入 03 证据。须 Flow 准入 `TICKET_FACE_REVISED`。
- **方案 B**：由 RT 窗口执行者受限扩界产出（须 Ops 明示路径豁免 + Integration 认可）。
- **配套**：03 执行席 trae 静默；若 A 被采纳，建议与 03 重派一并对齐（否则增补件无人承接）。

### 5.3 IMPL-v4-14 的 D4 envelope 缺位

- 14 挂 `USER-D4-flow-domain`，但 DECISION 队列无对应升级项、裁定席已自暂停 → 该 D4 无载体、无时限。
- **建议**：裁定席复启后先出短 envelope（流表新域建模/不建模二选一 + 影响面）；Task 不直接触达用户（routing 禁令）。

## 六、控制面缺陷登记（Task 只登记，处置权归 Ops/Flow）

1. **未来时间戳**：Flow `fl-self-pause-20261023-batch12.md` 内容时间 02:42、扫窗起点 mtime「02:37:26」，均晚于本席实测 02:32——与 EXEC-1 已自纠的同类缺陷（02:40→02:27）。建议各席时间字段一律取实测 `date`。
2. **唤醒断路**：裁定席唤醒条件已由 v3-0062 满足，但无采集器/监督实际点名 → 队列 ready 2 空转。看门狗/唤醒机制需覆盖「裁定席自暂停」场景。
3. **心跳单槽碰撞**：EXEC-2/EXEC-3 同报已载；Task 附议。建议采用方案 A（state 内嵌席前缀），规格定稿权归 Ops/Flow。
4. **trae 静默 11h**：无心跳、无 ACK，A1 升级未落地；影响 08（链头）与 03（验证链）双票。
5. **增量 13 §五-2 看门狗项部分缓解**：Integration 02:13 已上线（1.9 可达），余 LEASE-01 执行者与 RT 回执未决。

## 七、库存维持与 DAG

- **不铸空壳票**：本轮仅做 02b/03 **预塑**（01 冻结或 Ops 定路后即转可派），不新增票面。
- **可派库存**：08 重派后 EXEC-3 单票（P2，链头）；RT 队列 4 项（执行型，候窗）；02b 预塑（候 01）。
- **DAG 现状**：`08→09→10→11→12`；`01→{02b,06,15}`；`07/16/03→17`；`DEC-D05→13`；`DEC-migration→15`；`USER-D4→14`（无载体，§5.3）。无新增边；本轮未发现死锁环（5.2 缺口经 A 方案转为 03 内部增补）。

## 八、下一轮触发

08 重派事件｜裁定席复启并出 D05/migration 裁定｜Integration 出 LEASE-01 或串行窗回执｜01 契约冻结｜Flow 准入 02b/03 票面修订｜trae 复活或 03 重派。无变化则仅写哨兵心跳，不重载权威集。

---

## 本件修订记录

- **v1.0（2026-10-23T02:33，实测时间）**：初版。

---
Task / epoch 3 / 2026-10-23T02:33+08:00 / 水位 v3-0069 / 交 Flow 准入
