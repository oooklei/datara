# 库存核对与下一批 READY（增量 12 · v3-0054 派单后补位）

- **席位**：Task / epoch 3 / **RUNNING**
- **水位读取**：事件流 54 行，尾 `v3-0054-lease-until-narrative-realignment`；`queues/snapshot.json` watermark **v3-0054**；`control/governance-state.json` mailbox_watermark 仍为 v3-0048（见 §一-3 投影不一致）
- **基线**：`2026-10-22-task-inventory-check-dispatch-10.md` **v1.3**（07~15 票面四字段以此为准，本件不重复展开）
- **动作**：确认 Flow 已消费 07/08 → **补 1 票 READY**（16）+ **1 票 BLOCKED**（17，不占 READY 队首）；报告关键路径风险与投影缺陷

---

## 一、本轮读数

### 1. 控制面/队列

| 载体 | 读数 |
|---|---|
| `governance-state.json` | lifecycle **RUNNING**；mailbox_watermark **v3-0048**；active_tasks = 01/02a/03；LEASE-01 **ACTIVE**（至 2026-10-23T15:28:04+08:00） |
| `queues/snapshot.json` | watermark **v3-0054**；IMPLEMENTATION **ready 0 / assigned 2 / in_progress 3 / blocked 9** |
| 事件流 | 54 行；v3-0049 02a EVIDENCE_READY、v3-0050 02a 租约请求、v3-0051 批 9 准入、**v3-0052 07→claude**、**v3-0053 08→trae**、v3-0054 租约叙述校正 |
| REMOTE_TEST | RT-01 LEASED；RT-03 READY（串行候回执）；02a 租约请求已准入但未在 items[] 呈现 |

### 2. Flow 已消费 READY（07/08）

- `fl-dispatch-impl-v4-07.json`：`assigned_to=claude`，`READY->ASSIGNED`，P2/P2，路径/验收与本席增量 10 票面一致；FE-SHELL 锁由 07 独占。
- `fl-dispatch-impl-v4-08.json`：`assigned_to=trae`，`READY->ASSIGNED`，P2/P2，15-P0 契约冻结，不建表不写实现。
- 结论：**本席上批 2 票 READY 已全部被消费**；07/08 进入执行，不再计入可派库存。

### 3. 投影一致性缺陷（需 Flow 处置，本席不写控制面）

1. **state 滞后**：`governance-state.json` 水位仍 v3-0048、active_tasks 不含 07/08；事件流与 snapshot 已到 v3-0054。
2. **snapshot 计数与 items 不一致**：计数为 assigned 2 / in_progress 3 / blocked 9，但 `IMPLEMENTATION.items[]` 仅出现 04/01/02a/02b/03/05/06 七项，**缺 07/08 与 09~15**。
3. 影响：下游若只读 items[] 会误判“07/08 未派单、09~15 不存在”。本席以**事件流 + snapshot 计数 + 增量 10 v1.3 票面**为准，并建议 Flow 修复投影后重发一致性事件；在修复前，各席读库存须交叉校验事件流尾部。

---

## 二、新增 READY 库存（1 票）

### IMPL-v4-16 · 17.3 集群监控页组件段（不含路由/菜单壳）

| 字段 | 值 |
|---|---|
| **状态** | **READY** |
| **domain** | DELIVERY |
| **base_priority** | P2 |
| **effective_priority** | P2 |
| **priority_basis** | WBS 17.3「P2 集群监控迁移」（用户 2026-10-20/22 裁定纳入，权威设计 §3.3 F 组「含新前端页面 + 1.9 远程验收；候 P2 立票」）；后端 `rebuild/monitor` 已挂载 `GET /api/v1/rebuild/monitor/nodes`，`monitorApi.ts` 契约 GREEN（REGISTRY #13），`dep-monitor` 菜单条目已在册（future）；非当前发布关键路径，但为 07/08 后唯一可立即开工的合法补位 |
| **priority_override** | null |
| **depends_on** | [] |
| **depends_satisfied** | 17.1 B3 契约冻结已验收（`monitorApi` 类型/端点已冻结）；后端挂载与认证链已存在；无未满足票面依赖 |
| **authority** | 用户裁定纳入（WBS §5.2 P2/B3）+ 权威设计 §3.3「候 P2 立票」→ Task 立票；Flow 准入后派单。无需新 Decision |
| **acceptance** | ① `MonitorView.vue` 仅经 `createMonitorContract().fetchMonitorNodes()` 取数，禁止直连 fetch/axios；② 展示 `zkAvailable`/`generatedAt` 与 master/worker/ssh 三类节点行；字段覆盖 module/node/cpu/mem/memUsedMb/memTotalMb/disk/heartbeat/metricState/lastSeen/tags；③ 空指标如实显示 `—`，不得用 0 冒充；`heartbeat=unknown`（ZK 不可用）、`metricState=stale/unsupported`（Redis 过期 / SSH 无指标）须有可辨识文案，不得虚构实时性；④ 加载/空/错误三态齐备，非 0 包络码展示错误信息；提供手动刷新，不做高频轮询；⑤ 组件测试覆盖成功（混合模块）、空、错误、空指标、stale、unsupported、刷新；⑥ 本机 `vue-tsc -b`/`tsc --noEmit`/NO_SECRET 通过，1.9 组件测试 GREEN（经 Integration 租约）；⑦ **不得改 `router/routes.ts`、`navigation/menu.ts`**（FE-SHELL 锁在 07），不得改后端/`monitorApi.ts`（发现契约缺陷即停票上报） |
| **evidence_requirements** | 路径实存清单；静态检查输出（EXIT=0）；1.9 vitest 输出（经租约，请求先于执行）；NO_SECRET 0 命中；组件测试清单与用例数；无越界路径声明 |
| **paths** | `datara-newweb/src/views/depops/MonitorView.vue`（新）<br>`datara-newweb/src/views/__tests__/monitorView.contract.test.ts`（新） |
| **boundaries** | 本票是 17.3 的**组件段**，不含 `/dep/monitor` 路由注册与菜单转正；完整闭环由 17（BLOCKED）在 07 释放 FE-SHELL 后收口。1.9 e2e 不在本票（无路由不可达），仅组件测试。 |
| **completion_chain** | EVIDENCE_READY → ENV_VERIFIED（1.9 组件测试租约）→ PASS → Flow 集成窗提交 → RELEASED/DONE |
| **dispatch_advice** | claude 线：07 落线后建议由 **EXEC-2** 承接（WIP 0/1），EXEC-1 保持 01/02a 远程候执；本票与 07 路径不交叠，可并行本地开工。若 Ops 选项 A 令 EXEC-1 立即接管 01 执行段，本票改排 trae-08 之后或候 codex，不预占执行者。 |

---

## 三、新增 BLOCKED 票（1 票，不占 READY 队首）

### IMPL-v4-17 · 17.3 集群监控页壳激活（路由 + 菜单 + 1.9 e2e 闭环）

| 字段 | 值 |
|---|---|
| **状态** | **BLOCKED**（不占 READY 队首） |
| **domain** | DELIVERY |
| **base_priority** | P2 |
| **effective_priority** | P2 |
| **priority_basis** | WBS 17.3 闭环退出标准第 2 条「/dep/monitor 页面联通」；壳激活是 16 的唯一收口段，体量小但不可省略 |
| **priority_override** | null |
| **depends_on** | `IMPL-v4-07`（FE-SHELL 路径锁）、`IMPL-v4-16`（页面组件）、`IMPL-v4-03`（e2e 目录路径锁） |
| **blocked_reason** | routes.ts/menu.ts 由 07 独占；e2e/ 由 03 持有至 DONE；16 未交付前无组件可挂 |
| **acceptance** | ① `routes.ts` 仅新增 `/dep/monitor`（name `depMonitor`，component `MonitorView`）；② `menu.ts` 仅 `dep-monitor` 一行 `future→formal`，无空壳；③ 直链与菜单入口均可达，页面加载 1.9 真实后端；④ 1.9 Playwright 联通证据（查询→展示→刷新）成对（截图 + JSON）；⑤ 全量 vitest 基线不退化；⑥ 路由/菜单 diff 仅圈定两处 |
| **evidence_requirements** | 路由/菜单 diff（仅两处）；1.9 Playwright 截图+JSON 成对；vitest 基线；NO_SECRET；CONTRACT_REGISTRY 无新增（`monitorApi` 行已 GREEN） |
| **paths** | `datara-newweb/src/router/routes.ts`（仅 `/dep/monitor` 一条）<br>`datara-newweb/src/navigation/menu.ts`（仅 `dep-monitor` 一行）<br>`datara-newweb/e2e/`（仅新增 monitor 场景，候 03 释放） |
| **completion_chain** | 07/03 释放 + 16 PASS → READY → 派单 → EVIDENCE_READY → ENV_VERIFIED（1.9 e2e 租约）→ PASS → 集成窗提交 → DONE |

说明：若 Flow 认为 16+17 拆分过细，可在 07 释放后将两票合并为单票派发；本席保留拆分是为了让 16 在 FE-SHELL 锁存续期间仍可作为合法 READY 库存，不制造路径冲突。

---

## 四、依赖图增量（无环）

```
07 ──┐
     ├──> 17（BLOCKED：壳激活）
16 ──┤
03 ──┘
08 ──> 09 ──> 10 ──> 11 ──> 12
01 ──> 02b ──> 06
01 / Decision F-2/F-3 ──> 15
DEC-D05 ──> 13
用户 D4 ──> 14
```

- 16 独立，不依赖 07；17 串在 07/16/03 之后，天然让出 READY 队首。
- 09~15 票面与四字段见增量 10 v1.3 §四；DAG 较增量 11 仅增 16/17 两条边，无环。

---

## 五、关键风险与路由（Task 标注，不越权处置）

1. **LEASE-01 执行段无执行者（最高影响）**：EXEC-1 核实前会话已终止、1.9 无 lane-loop/后台进程、`evidence_dir` 未创建、120min 零写入；01 实际停滞约 3h。01 是 `02b → 06` 与 RT-03/RT-02a 排队的前置。**请 Ops/Integration/Decision 在选项 A（同源会话承接现行租约）/ B（补回执）/ C（释放重授）中裁定**；Task 不建议释放有效租约，倾向 A（最快且不破坏单实例纪律），但执行者身份必须由 Ops/Integration 书面确认。07/08 的派单不能解除该风险。
2. **投影缺陷**：state 水位/active_tasks 滞后、snapshot items[] 缺 07/08 与 09~15；建议 Flow 优先修复并出投影校正事件（参照 v3-0054 的显式修订披露口径），否则各席库存读数将持续分叉。
3. **trae 静默**：08 派单后若一个调度周期内无 ACK，按 Ops A1 升级；回退候选为 EXEC-1/EXEC-2（须避开其 WIP 与 01 接管），不在线别未定时预占路径。
4. **准入吞吐**：07/08 已入控制面，16/17 仍需 Flow 扫箱准入。16 是本轮唯一 READY；若 Flow 不再准入，READY 将在本轮后再次见底。建议 Flow 在修复投影的同批准入 16，保持至少一个调度周期库存。

---

## 六、下一轮触发

- 07/08 ACK 或 EVIDENCE_READY｜08 PASS → 09 转 READY｜07 RELEASED → 17 去一依赖｜01 租约裁定 → 02b/06 排程｜DEC-D05 → 13｜用户 D4 → 14｜Decision F-2/F-3 + 01 DONE → 15。
- 若下一轮无上述变化：仅写待命心跳，不重复票面、不增库存。

---

Task / epoch 3 / 2026-10-22T18:52+08:00 / 水位 v3-0054（state 文件 v3-0048，已披露）/ 提交 Flow 接纳
