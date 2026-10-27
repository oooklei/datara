# 监督巡检报告：队列指标 / 心跳 / 采集器 / 审计 / 政策合规（水位 v3-0054）

- **席位**：监督 Ops｜**时间**：2026-10-23T02:00+08:00｜**基线水位**：`v3-0054-lease-until-narrative-realignment`
- **版本**：v1.0（修订记录见文末）
- 仅读数、分类与建议；不写共享状态、不替裁定、不替验收、不处置计划任务。

## 1. 队列指标

| 指标 | 读数 | 判定 |
| --- | --- | --- |
| WIP | 3（01 REWORK / 02a EVIDENCE_READY / 03 REWORK） | 名义在飞；**有效执行 WIP=0**（见 A2） |
| IMPLEMENTATION | ready 0 / assigned 2 / in_progress 3 / blocked 9 | ready 0 为结构性见底；assigned 中 07 候本席分诊、08 持票席无 ACK |
| BLOCKED 9 | 02b←01；06←01..05；09←08；10←09；11←10；12←11+07；13←DEC-D05；14←USER-D4；15←方向裁定+01 | 依赖真实、无伪阻塞；依赖图线性，**无循环依赖** |
| REMOTE_TEST | ready 2（03、02a）/ in_progress 1（LEASE-01，至 2026-10-23T15:28:04，余约 13.5h） | 单环境串行；LEASE-01 空转即全队列空转 |
| 共享路径 | FE-SHELL 锁在 07；16 明令禁碰 routes/menu；12 候 07 释放 | 无碰撞 |
| flow_metrics | arrival/service/P90 全 null；wip=3 | 量测缺失（并入 A6/R-6，不单独立项） |
| EXCEPTION | 未决 **0**（EXC-v4-01..04 已核销） | 无开口项 |

## 2. 心跳看门狗（现状 02:00）

- 仅 `outbox/裁定/heartbeat.json` 存在，内容时间戳 **00:05**（已超控制线 60 分钟阈值约 1h55m）；文件 mtime 与内容时间戳不一致（mtime 01:58 / 内容 00:05），采信内容时间戳判超时。
- 其余席位 **heartbeat.json 全部缺失**：监督 / 流程 / 任务 / 验收 / 集成 / claude / trae / codex。
- 末次实质产出：claude 19:15、流程派单面 18:46、集成回执 18:41 → 全体静默约 **6h45m**；远超控制线 60 分钟、实施线 30 分钟。
- 01:58 裁定席（ACK/自暂停）与 EXEC-3（ACK/自暂停）恢复上线，属**部分恢复**；流程、任务、验收、集成、trae 仍无在线证据。
- 判定：按契约升级 **A→用户**（A1）。说明：循环条款为软保证，若外部无守护进程拉起，隔夜静默属可预期；但各席上线后未落 heartbeat.json 本身构成执行面缺陷，须由 Flow 投影登记口径。

## 3. 采集器与审计告警

- **采集器已停**：`heartbeat.json` captured_at 17:03:11（pid 22424），`stopped.json` stopped_at 17:03:15；停摆约 **8h55m**。
- `latest.json` 冻结于 17:03，mailbox 读数仍为 `v3-0006`（已冻结快照），相对权威事件流 v3-0054 严重滞后。
- `logs/governance-audit-latest.json`（17:02:51）：watermark v3-0006；告警 `READY_STARVATION` + `BLOCKED_WORK×2`。BLOCKED 现为 9，告警计数为陈旧快照值，非新增。
- `logs/hard-constraint-audit-latest.json`：PASS，0 failures（12:51 捕获，未刷新）。
- 根因即既有 **F-2 / R-6 advisory**：采集源仍读冻结 mailbox；采集源正位与计划任务处置属 **USER_ONLY（HC-07）**，监督不擅动（A6）。

## 4. 政策合规（以投影为准）

- `control/policy-receipts.json`：POLICY-v3 **APPLIED**，effective_epoch 3，superseded_by null；AOCI 开发期停用。**未按政策源文件 status 判库存**。
- 合规发现 1 项：EXEC-2 本机执行 `npx vitest run`（全量基线 615 例）超出 `TEST-ENVIRONMENT-POLICY.md` 字面硬边界（单元执行归 1.9）→ 见 A5/E-2 定性。

## 5. 异常分类与处置建议

| # | 级别 | 分类 | 事实 | 建议/路由 |
| --- | --- | --- | --- | --- |
| **A1** | **升级用户（A）** | 心跳面全线超时 | 除裁定席外 heartbeat.json 全缺；末次产出 19:15，静默 6h45m；采集器同时停摆 | **升级 A→用户**：是否拉起/保留外部守护进程由用户定；各席上线后须按契约落 heartbeat.json。监督不处置计划任务 |
| **A2** | **阻断·关键路径** | LEASE-01 执行者缺位、空转烧租约 | 1.9 侧自 18:40 起无可确证执行（集成巡逻：evidence_dir 未建、隔离树零写入、who 空）；租约余约 13.5h；01 不定则 02b/06/15 全链不动，RT-03/02a 串行受阻 | **路由 Integration（首要）**：30 分钟内复核执行者存活并按 Ops 18:48 建议 B 补在案回执（或判 A）；EXEC-1 进执行段并每 15–30 分钟落进度心跳。**检查点 2026-10-23T10:00**：仍无证据则评估提前释放/重排租约，保留 15:28 到期缓冲 |
| **A3** | **控制面一致性（高）** | IMPL-v4-16 派单面锚点悬空 | `fl-dispatch-impl-v4-16.json` 引用 `v3-0057/v3-0058`，但权威事件流仅 54 行止于 v3-0054，v3-0055..0058 均不存在；snapshot 无 IMPL-v4-16；面件 generated_at 19:05 晚于其 mtime 18:46（未来时间戳） | **路由 Flow**：核验是否漏追加事件；补写前 **IMPL-v4-16 视为未合法派单**，任何席位不得开工。建议按 EXCEPTION 登记（Flow 定号）。timestamp 倒挂一并校正 |
| **A4** | 投影滞后 | 07 租约请求未入权威队列 | `RT-IMPL-V4-07-QC-BATCH-A`（19:09）不在 `control/remote-test-queue.json`；snapshot 自 v3-0054 未更新 | **路由 Flow**：扫箱准入并更新队列投影；**路由 Integration**：租约回执排于 LEASE-01 之后 |
| **A5-E1** | 票面缺陷 | 07 验收⑥与 paths 不足 | 需同步 3 件授权外文件（`routes.contract.test.ts` / `menu.contract.test.ts` / `menuAudit.ts`），否则全量基线恒 3 红 | **定性：Task 票面漏列，非实施越界**。建议 **Task 修票面 paths 追加 3 件并注明「冻结基线同步」**；Flow 准入后 EXEC-2 落盘、复跑基线（1.9 面）至绿 → EVIDENCE_READY。集成窗 PATHSPEC_MANIFEST 按票面归因圈定（C-1） |
| **A5-E2** | 政策口径 | 本机 vitest 越界 | 字面违反 TEST-ENVIRONMENT-POLICY 硬边界 | **定性：越界执行（无恶意、诊断用途）**。产出标 **DIAGNOSTIC_ONLY_NOT_PASS_EVIDENCE**，不得作验收证据；后续本机仅 `vue-tsc -b` / `tsc --noEmit` / NO_SECRET / FE-BE 对拍；全量基线及 14 用例移交 1.9。建议 Flow 投影注记一笔执行口径缺陷（非阻断） |
| **A6** | 顾问（既有 R-6） | 采集器停摆 / 审计水位失真 | 见 §3 | 候**用户明确指令**：采集源正位与计划任务处置；监督不擅动 |
| **A7** | 观察 | 08 持票席无 ACK、trae 长时静默 | trae 末件 15:33（约 10.5h）；08 派单后无 ACK | **路由 Task/Flow**：唤醒后若无 ACK，按规程评估重派；派单权不在监督 |

## 6. 结论

- **升级 A→用户：A1（心跳/守护进程）与 A6（采集器与计划任务）需用户决定**；其余均已路由至职权席：A2→Integration（首要）、A3/A4→Flow、A5-E1→Task、A5-E2→已定性并交 EXEC-2/Flow 注记、A7→Task。
- 本轮**不建议新派单**：READY=0 结构性见底，且 16 未合法入流（A3）；07 候票面修订（E-1）；08 候 ACK。
- 下一触发点：Integration 执行者存活回执（A2）/ Flow 事件流补写与 07 租约准入（A3/A4）/ Task 票面修订（E-1）/ 各席上线心跳。

---

## 修订记录

| 版本 | 时间 | 修订 | 依据 |
| --- | --- | --- | --- |
| v1.0 | 2026-10-23T02:00+08:00 | 初版 | 四件控制文件 + outbox 近期件 + control 投影 + 采集器/审计日志 |

—— 监督 Ops / epoch 3 / 2026-10-23T02:00+08:00
