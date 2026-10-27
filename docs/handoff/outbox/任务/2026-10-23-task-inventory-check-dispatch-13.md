# 库存核对 · 派单调整与票面修订（增量 13 · v3-0054）

- **席位**：Task / epoch 3 / **RUNNING**
- **水位**：`v3-0054`（governance-state / snapshot / 事件流 54 行，三者一致）
- **基线**：增量 10 **v1.3**（07~15 票面四字段）、增量 12（16/17 票面）
- **本轮动作**：① 修 07 票面（解 E-1 死锁）；② 建议 08 重派；③ 16 落线；④ 正式提交 DEC-v4-D05 与 DEC-migration-direction；⑤ 登记投影/看门狗缺陷

---

## 一、读数（v3-0054）

| 项 | 读数 |
|---|---|
| IMPLEMENTATION | ready 0 / assigned 2（07→claude、08→trae）/ in_progress 3（01、03 REWORK；02a EVIDENCE_READY）/ blocked 9；items[] 已含 07/08 与 09~15 |
| REMOTE_TEST | RT-01 LEASED（至 **2026-10-23T15:28:04**，余 13h18m）/ RT-03 READY / RT-02a READY；串行候 Integration 回执 |
| 在飞阻塞 | 07 停于 E-1（票面 paths 缺 3 件冻结基线）→ 本轮解；08 trae 静默未 ACK → 本轮建议重派；01 租约执行者缺位（Ops v3-0051 建议 B）→ 仍候 Integration |
| 16/17 | snapshot 未纳入；Flow 派单面 `fl-dispatch-impl-v4-16.json` 已出但锚点事件不存在（§五-1） |

---

## 二、IMPL-v4-07 票面修订 v1.0 → **v1.1**（显式修订披露）

**触发**：EXEC-2 阻塞心跳 19:14（E-1）。验收⑥要求全量基线 GREEN，但票面 paths 不含使其转绿的 3 件，执行席按纪律不扩界、停票候裁。

**修订内容**：

1. `paths` 追加（仅限 qc 相关冻结基线同步，性质注明「冻结基线同步」）：
   - `datara-newweb/src/router/__tests__/routes.contract.test.ts`（冻结路径表 +2：`/qc/rule`、`/qc/task`）
   - `datara-newweb/src/navigation/__tests__/menu.contract.test.ts`（E 组断言：10 formal / 3 future）
   - `datara-newweb/src/navigation/menuAudit.ts`（仅 `no:3`/`no:4` `disposition: future→formal`；`AUDIT_COUNTS` 不变，采 EXEC-2 v1.1 复核）
   - **Task 只读复核（git diff）**：前两件在工作区**已有他票在途改动**——`routes.contract.test.ts` +11/-1（`/dep/ssh`、`/sec/perm` 与 `PermissionMatrixView`，15.1-C/inc17 面）、`menu.contract.test.ts` +2（`dep-ssh` 行）；`menuAudit.ts` 无在途改动。故本授权为**增量追加式**：07 只加 qc 相关断言，**不得回退/改写他票既存行**；集成窗按行归因（他票行不计入 07）。
2. **验收⑥修订为**：本机 `vue-tsc -b` / `tsc --noEmit -p tsconfig.node.json` / NO_SECRET 通过；**全量 vitest 基线 GREEN 的权威证据由 1.9 租约段出具**。本机 vitest 结果按 `evidence_rule.local_result` 仅作 `DIAGNOSTIC_ONLY_NOT_PASS_EVIDENCE`，不作验收依据；E-2 定性不阻断 EVIDENCE_READY。
3. **边界**：上述 3 件只允许同步本次 qc 路由/菜单变更所需的断言，禁止放宽为通配放行、禁止改动其它冻结项；`menuAudit.contract.test.ts` 不改（对拍逻辑，台账源同步后自动转绿）。
4. **C-1 归因确认**：集成窗按 EXEC-2 v1.2 逐行切分圈定——`routes.ts` 本票 **10 行**、`menu.ts` 本票 **2 行**，其余为在途他票既存改动，不计入本票越界。

**披露**：本修订为 v1.0 覆盖式升版，非静默改写；理由=票面 paths 漏列本次变更的必然同步项（执行席零缺陷）。**须 Flow 准入为 `TICKET_FACE_REVISED` 事件方固控制面**；实施席可依本件立即执行，证据面注明「依据 Task 增量 13 §二」。

**修订记录（票面）**：v1.0（增量 10 v1.3，8 路径）→ **v1.1**（11 路径 + 验收⑥口径改为 1.9 权威基线 + 基线文件增量追加式授权）。

---

## 三、IMPL-v4-08 重派建议（trae → claude / EXEC-3）

- **事实**：08 于 18:47 派 trae（v3-0053）；trae 末件 15:33，**约 10.5h 无产出、派单后 7h+ 无 ACK**。EXEC-3 于 01:58 上线 ACK，WIP 0、无票可领。
- **建议**：Flow 出 `DISPATCH_REASSIGNED`——08 执行席改为 **claude / EXEC-3**（实施线 3），票面内容/优先级/路径/验收/证据**零变更**。
- **单实例守则**：同一时刻仅一个 08 执行者。若 trae 在 Flow 重派前已正式 ACK，则由 Flow 按首 ACK 定席；重派生效后 trae 不得触碰 08 路径（trae 仅保留 03 候租约）。
- **理由**：08 是 G 组链头（08→09→10→11→12），链路挂起成本最高；EXEC-3 空转中，重派不引发路径冲突（08 路径为 contract 骨架/测试/证据 md）。
- **附**：请 Ops 对 trae 静默按 A1 升级（看门狗），不因重派而豁免。

---

## 四、IMPL-v4-16 落线建议（依 Flow 派单面 wip_note）

- 16 派单面记 **claude**，倾向 **EXEC-1**：01 的租约段计 REMOTE_TEST 面、EXEC-1 本地 WIP 0（Ops E-2 按线计 WIP 口径）。
- **建议**：16 → EXEC-1 本地开工（组件 + 组件测试，不触 routes/menu）；若 Integration 按 Ops 建议 B 指名 EXEC-1 执行 LEASE-01，则 16 改排 trae（若已复活）或 codex（须先上线 ACK），不预占执行者。
- **前置**：见 §五-1，16 的派单面须先有真实准入事件，否则 EXEC-1 无合法队列卡可引。

---

## 五、控制面缺陷登记（Task 只登记，请 Flow/Ops/Integration 处置）

1. **派单面锚点事件缺失**：`流程/fl-dispatch-impl-v4-16.json` 声明锚点 `v3-0057-outbox-reports-admitted-batch-10`、`v3-0058-dispatch-assigned-impl-v4-16`，但权威事件流（`events/2026-10-22-restart.jsonl`）尾为 **v3-0054**，无 v3-0055~0058；snapshot 亦无 16。→ 请 Flow 二选一：补写两事件并更新投影，或作废该派单面重出。**在此之前不得以该面作为执行凭据。**
2. **看门狗超期**：Ops 18:43、Integration 18:39、Task 18:52 后静默 >7h（控制线阈值 60m）；Flow 心跳 01:59 正常。当前最高影响：LEASE-01 执行者缺位未回执、RT-03/RT-02a 排队未回执、07 E-2 未定性。→ 请监督/采集器按看门狗升级。
3. **租约余量**：LEASE-01 至 2026-10-23T15:28:04，**余 13h18m**。若执行段不在本轮续上，01 证据链将再次跨日；Ops 建议 B（Integration 补在案回执并指名现任执行者）仍为最快解。

---

## 六、DEC 正式提交（解依赖环）

| 裁定项 | 请求件 | 解阻票 | 级别 |
|---|---|---|---|
| `DEC-v4-D05` | `2026-10-23-task-dec-v4-d05-request.md` | IMPL-v4-13 | D2–D3（Decision 自主） |
| `DEC-migration-direction` | `2026-10-23-task-dec-migration-direction-request.md` | IMPL-v4-15 | D2–D3（Decision 自主） |

- 两项此前仅以票面 `depends_on` 挂名、无正式候裁件（Decision 席 2026-10-23 ACK 已指出）；本轮补齐，**请 Flow 准入 DECISION 队列**。
- `IMPL-v4-14` 挂 `USER-D4-flow-domain`：属 Decision→User 升级路径，本席不直接触达用户；待裁前保持 BLOCKED，不予替代承载。

---

## 七、READY 库存与依赖图

- **投影 READY=0**；操作面可派库存 = 16（待 Flow 事件）+ 08 重派（待 Flow 重派）。按「不提前铸造空壳票」的既往口径，本轮不新增票面。
- 若 Flow 作废 16 派单面，则 16 退回 READY（增量 12 §二 票面原样），维持至少一个调度周期库存。
- DAG 无新增边：07 的 3 件同步并入 07 自身；08 重派不改变 `08→09→10→11→12`；`DEC-D05→13`、`DEC-migration-direction + 01→15`、`USER-D4→14` 保持。

---

## 八、下一轮触发

07 E-1 修订被采纳并出 EVIDENCE_READY｜08 重派 ACK｜16 事件补齐或作废｜DEC-D05 / DEC-migration-direction 出裁定｜01 租约执行段回执｜trae 复活。无变化则仅写哨兵心跳，不重载权威集、不重复票面。

---

## 本件修订记录

- **v1.1（2026-10-23 02:03，同轮）**：§二 补入基线文件工作区在途改动实证（Task 只读 `git diff`），授权口径由「3 件同步」明确为「增量追加式、不得回退他票行」；票面修订版本仍为 v1.1。触发：发布后即时只读复核，避免与他票在途改动冲突。
- **v1.0（02:02）**：初版（07 修订 / 08 重派 / 16 落线 / DEC 提交 / 缺陷登记）。

---
Task / epoch 3 / 2026-10-23T02:03+08:00 / 水位 v3-0054 / 交 Flow 准入
