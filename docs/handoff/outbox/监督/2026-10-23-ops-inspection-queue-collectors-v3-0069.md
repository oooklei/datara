# 监督巡检报告（水位 v3-0069）：队列指标 / 心跳 / 采集器 / 审计 / 政策合规

- **席位**：监督 Ops｜**时间**：2026-10-23T02:33+08:00｜**基线水位**：`v3-0069-projection-realignment-batch-12`（事件流 69 行）
- **版本**：v1.3（巡检系列第 2 期；v1.0 = 2026-10-23T02:00 / v3-0054，原件保留不改；v1.1 → v1.2 → v1.3 增量见 §7）
- 仅读数、分类与建议；不写共享状态、不替裁定、不替验收、不处置计划任务。

## 0. 相对 v3-0054 报告的增量更正（显式披露）

| 上期项 | 本期结论 | 依据 |
| --- | --- | --- |
| A3 IMPL-v4-16 派单面锚点悬空 | **关闭** | 事件流已补至 v3-0069；v3-0067/0068 使 16 合法入流，snapshot 已含 16（EVIDENCE_READY） |
| A4 RT-07 未入权威队列 | **部分关闭** | snapshot 已含 RT-07/02a/16；但 `control/remote-test-queue.json` 仍只列 RT-03（见 O5） |
| A1 心跳面全线超时 | **大部分恢复** | 除 trae/codex 外各席 heartbeat.json 均已出现且多席新鲜（见 §2） |
| A2 LEASE-01 执行者缺位 | **未关闭** | 1.9 侧仍无可确证执行；租约余 12h55m；有效远测吞吐 = 0（见 O1） |
| A7 trae 静默 | **未关闭并扩大** | 无 heartbeat，末件 15:33，静默约 11h；08 仍 ASSIGNED 未 ACK（见 O3） |
| A5-E1 07 票面漏列 | **关闭** | Task 增量 13 v1.1 修票面，Flow v3-0066 准入，07 已 EVIDENCE_READY |

## 1. 队列指标

| 指标 | 读数（v3-0069） | 判定 |
| --- | --- | --- |
| WIP | snapshot `wip=5`；active_tasks 6（01/02a/03/07/08/16） | 名义在飞；**有效执行 WIP ≈ 0**（本地三线均暂停；远测 0 执行） |
| DECISION | ready 2 / in_progress 0 / blocked 0 | 2 项 D2–D3 候裁（D05、migration-direction），裁定席自暂停中 → 见 O2 |
| IMPLEMENTATION | ready 0 / assigned 1 / in_progress 5 / blocked 10 | ready=0 结构性见底；08 持票席无 ACK |
| REMOTE_TEST | ready 4 / in_progress 1（LEASE-01） | 单环境串行；LEASE-01 空转即全队列空转 |
| VALIDATION / DISPATCH / INTEGRATION / EXCEPTION / POLICY_RECEIPT | 均 0 | EXCEPTION 未决 **0**（EXC-v4-01..04 已核销） |
| 等待时长（READY→租约） | RT-03 10h42m（15:51 起）/ RT-02a 10h32m（16:01）/ RT-07 7h24m（19:09）/ RT-16 4m（02:29） | 远端闸门前排队已构成事实性 P90 失控（量测缺失，见 O6） |
| 吞吐 | 本地 EVIDENCE_READY 本轮 +2（07、16）；epoch 3 起 **ENV_VERIFIED = 0** | 唯一测试环境 11h 零产出，**吞吐瓶颈在远测闸门，不在本地交付** |
| 共享路径 | FE-SHELL 锁在 07；16 禁触 routes/menu；12 候 07；08 路径（services/rebuild + docs）与 16 无交集 | 无碰撞 |
| 依赖图 | 02b←01；06←01..05；09←08；10←09；11←10；12←11+07；13←D05；14←USER-D4；15←方向裁+01 | 线性，**无循环依赖** |
| 配额 | 全局上限 8；实际并发线 3（claude）/ 0（trae、codex） | 配额非约束；瓶颈是租约与席位缺位，非并发额度 |
| Token | 未见超限证据；claude heartbeat 104B 略超 100B 上限（见 O7） | 轻缺陷 |

## 2. 心跳看门狗（采样 02:33）

| 席位 | heartbeat 内容时间 | 文件 mtime | 年龄 | 阈值 | 判定 |
| --- | --- | --- | --- | --- | --- |
| 监督 | 02:00 | 02:00 | 33m | 60m | 正常（本件刷新） |
| 流程 | 02:31:23 | 02:31 | 2m | 60m | 正常 |
| 裁定 | **00:05** | 01:58 | **2h28m** | 60m | **超时 A**；但属登记自暂停，唤醒条件已满足 → 见 O2 |
| 任务 | 02:05 | 02:04 | 28m | 60m | 正常 |
| 验收 | 02:32 | 02:32 | 1m | 60m | 正常 |
| 集成 | 02:14 | 02:12 | 19m | 60m | 正常 |
| claude | 02:27:42 | 02:28 | 5m | 30m | 正常（多线共槽，见 O4） |
| trae | **缺失** | — | **约 11h**（末件 15:33） | 30m | **超时 A** → 见 O3 |
| codex | **缺失** | — | 从未 ACK | 30m | 判定**未上岗**，非在线席超时（观察） |

## 3. 采集器与审计告警

- **采集器停摆**：运行根 `heartbeat.json` 17:03:11、`stopped.json` 17:03:15；至采样时停摆 **9h30m**。
- `logs/governance-audit-latest.json` 冻结于 17:02:51，watermark 仍为 **v3-0006**（落后 63 个事件）；告警 `READY_STARVATION` + `BLOCKED_WORK×2` 为陈旧快照，非新增。
- `logs/hard-constraint-audit-latest.json`：PASS / 0 failures，但未带时间戳且未刷新（末次约 12:51），**不能作为现行合规证据**。
- `flow_metrics`：arrival_rate / service_rate / p90 全 null，`seat_self_reports` 为空——各席已按契约自报，汇聚未发生。结构性冲突：`role-contracts.self_report.aggregator=Ops`，但 `sink` 在 Flow 单写者持有的 snapshot → 见 O6。
- 根因仍为既有 **F-2 / R-6**：采集源读冻结 mailbox。计划任务生命周期 **USER_ONLY（HC-07）**，监督不擅动。

## 4. 政策合规（以投影为准）

- `control/policy-receipts.json`：**POLICY-v3 = APPLIED**，effective_epoch 3，superseded_by null；未据政策源文件 status 判库存。
- AOCI：开发期 **DISABLED**，无越界引用。HC-01/02/05/07/09 未见违反。
- 既有 A5-E2（本机 vitest 越界）已由 EXEC-2 承接并标 `DIAGNOSTIC_ONLY_NOT_PASS_EVIDENCE`，**关闭**；本轮未发现新的本机测试执行。
- 证据绑定：07/16 本地结果均正确标注 DIAGNOSTIC；LEASE-01 侧仍无 evidence_dir 回执（O1）。

## 5. 异常分类与处置建议

| # | 级别 | 分类 | 事实 | 路由/处置 |
| --- | --- | --- | --- | --- |
| **O1** | **阻断·关键路径** | 远测闸门零吞吐 | LEASE-01 自 15:28 起空转 11h，余 12h55m；4 张 READY 远测全排队；01 不定则 02b/06/15 链不动 | **Integration 首要**：03:00 前按建议 B 出在案回执并指名现任 EXEC-1；A 为降级；C 仍否决。**10:00 硬检查点**：仍无证据则评估提前释放/分段重排（R2） |
| **O2** | **高·控制面** | 裁定席自暂停 + 心跳超时，阻塞 2 项候裁 | 自暂停 00:05；DECISION ready=2（D05→13、migration-direction→15），唤醒条件 1/2 均已满足 | **Flow/采集器点名唤醒裁定席**（不得依赖其自轮询）。属运维唤醒，不需用户介入 |
| **O3** | **高·看门狗** | trae 静默约 11h，持 08 ASSIGNED + 03 REWORK | 08 派单 7h46m 无 ACK；08 为 G 组链头 | **裁定 R3：批准 08 重派 claude/EXEC-3**；trae 按 A1 升级并保留 03；RT-03 窗口开启时若仍静默，Task 预备 03 重派 |
| **O4** | 中·控制面 | claude 三线共槽 heartbeat 碰撞 | 单槽 last-writer-wins，看门狗误判；EXEC-3 已按前缀口径执行 | **裁定 R1：过渡采用方案 A（state 前缀 + ≤100B）**；方案 B（按线分文件）交 Flow 修订心跳规格 |
| **O5** | 中·投影一致性 | `control/remote-test-queue.json` 滞后 | 仅列 RT-03；缺 02a/07/16 与延期/排序回执，与 snapshot 4 ready 不一致 | **路由 Flow**：按快照重建远测队列投影（含 LEASE_DEFERRED 排序与前置） |
| **O6** | 中·顾问/用户 | 采集器停摆 + 指标失真 + 汇聚职责冲突 | 见 §3 | **USER_ONLY（HC-07）**：采集器重启与采集源正位须用户明确指令；汇聚写入应由 Flow 执行、Ops 供聚合值（契约口径建议修订） |
| **O7** | 低·观察 | 时间戳与件规范 | claude 07/16 心跳碰撞报告声明 02:37/02:31，mtime 实为 02:24/02:23（未来时间戳）；heartbeat 104B >100B；裁定 heartbeat 内容/mtime 不一致 | **路由 Flow 注记**：写件前校时；执行面按 ≤100B 收紧。不阻断 |
| **O8** | 低·观察 | 投影字段漂移 | `roles_active=[]` 但多席在线；codex 从未 ACK | Flow 下一批投影顺带校准；codex 视作未上岗，不计超时 |

## 6. 结论

- **头号瓶颈仍是 O1（LEASE-01 空转）**：本地交付已把 4 张票推到远测门口，唯一测试环境 11h 零产出；本轮所有提速动作的边际收益都取决于 03:00 回执与 10:00 检查点。
- **O2/O3 是可控的解阻动作**：唤醒裁定席 + 重派 08，分别解 13/15 与 G 组链头，不触碰共享状态。
- **唯一需用户决定的仍是 O6**：采集器/计划任务生命周期（HC-07）与外部守护进程；其余均在职权席闭环。
- 下一触发点：Integration 03:00 回执 / 10:00 检查点｜裁定席唤醒后 2 裁定｜Flow 执行 DISPATCH_REASSIGNED｜Flow 远测队列投影追平。

## 7. v1.2 增量更新（哨兵复读，02:33:45 实测）

本轮收尾哨兵发现两席在 02:33 新落件，增量深读后更正如下（不覆盖 §1–§6 原读数）：

1. **O2 关闭（Ops 侧）**：裁定席已于 **02:33:42** 复启并落两票 D2–D3 裁定——`2026-10-23-DECISION-DEC-v4-D05-ruling.md`、`2026-10-23-DECISION-DEC-migration-direction-ruling.md`，ACK 声明“2 票裁毕待 Flow 采信”。**无需再点名唤醒**；DECISION 队列在 Flow 采信前仍显示 ready 2，属投影时差，不是空转。解阻 13/15（15 另需 01）。
2. **O3/R3 得到 Task 增量 14 独立佐证**：Task 02:33 件明确“Task 提议 → Ops 裁定可行 → Flow 执行重派”，与 R3 一致；请 Flow 直接落 `DISPATCH_REASSIGNED`。
3. **新增 O9（中·控制面）**：IMPL-v4-14 挂 `USER-D4-flow-domain`，但裁定席复启后仅处理 D2–D3 并再次自暂停，**D4 无 envelope 载体、无时限**（Task 增量 14 §5.3）。Route：裁定席下次唤醒须先出短 envelope；按 routing，Ops 不见 envelope 不上呈用户（不越权）。
4. **O7 升级为中·跨席时间卫生**：裁定席两块新件声明 **03:22**（实测 02:33，偏移约 49m）；Task 增量 14 §6.1 另记录 Flow batch12 声明 02:42、扫窗 mtime 02:37，均属未来时间戳。建议 Flow 统一“写件前取实测 `date`”并在下一投影批注记，不阻断业务。
5. **新增 R4（e2e 用例缺口）**：Task 增量 14 §5.2 的 02a/07 e2e 用例件缺口转 Ops 定路 → 见裁定件 R4（推荐方案 A，03 票面增补 e2e 纯测试件；B 仅作窗口先到时的条件豁免）。
6. **Integration 第 2 会话 ACK（02:34）证实 O1 全部事实**：1.9 可达（ICMP 2/2、SSH 成功、远端时钟同步）；LEASE-01 未过期（余 12h54m）；`who`=0、evidence_dir 不存在、隔离树自 15:28 起 `-newermt` 命中 0——**零产出、执行段未启动，已耗窗 11h06m**。Integration **不自行释放/重排**，明确待 Ops 落定（指名/授权/早释）→ 与 R2 一致；另将 RT-16 回 `LEASE_DEFERRED`，串行序 03→02a→07→16 不变。
7. **新增 O10（阻断·证据面）**：隔离树 `/lei/datara/rebuild-source/` 最新件为 2026-10-22T05:25，早于本地 HEAD `835939c` 且不含 172 项在飞改动。**任何 1.9 执行前必须先同步制品并绑定 commit/路径清单（+sha256）**，否则证据不能满足 `evidence_rule` 的制品身份要件——该前置对 4 张 RT 一体适用，非仅 RT-16。已并入 R2 前置。

---

## 修订记录

| 版本 | 时间 | 修订 | 依据 |
| --- | --- | --- | --- |
| v1.3 | 2026-10-23T02:36+08:00 | 接入 Integration 第 2 会话 ACK（02:34）：证实 O1 零产出、LEASE-01 待 Ops、RT-16 DEFERRED；新增 O10 制品身份前置 | 集成 outbox `INT-ACK-v3-0069`、`INT-LEASE-DEFERRED-RT-16` |
| v1.2 | 2026-10-23T02:35+08:00 | 哨兵复读增量：O2 关闭（裁定席自行复启、两裁定落盘）；O7 升级；新增 O9；R4 转裁定件 | 裁定 outbox 02:33 新件 + Task 增量 14（02:33）+ 心跳 mtime |
| v1.1 | 2026-10-23T02:33+08:00 | 第 2 期巡检；关闭 A3/A5-E1，部分关闭 A4，A1 大部恢复；新增 O1–O8 | governance-state / snapshot v3-0069 + outbox 近期件 + 采集器日志 + policy 投影 |
| v1.0 | 2026-10-23T02:00+08:00 | 初版（v3-0054），原件保留 | 同 |

—— 监督 Ops / epoch 3 / 2026-10-23T02:33+08:00｜自报：本轮轮次 1 / 空转比低（无重复读全量）
