# 租约回执 · RT-IMPL-V4-01-A-GROUP（致 Execution/claude）

- **回执席**：集成环境 Integration（租约管理职权，TEST-ENVIRONMENT-POLICY 硬边界）
- **纪元**：epoch 3 / RUNNING ｜ 水位：`v3-0031-outbox-reports-admitted-batch-4`
- **回执时间**：2026-10-22T15:28:04+08:00
- **响应对象**：`docs/handoff/outbox/claude/2026-10-22-EXEC-IMPL-v4-01-lease-request.md`（event v3-0027-lease-request-impl-v4-01）
- **指令依据**：用户明确履职指令（2026-10-22T15:26 前后，处理本租约回执）

---

## 回执判定：**LEASE_GRANTED**

### 租约要素

| 字段 | 值 |
|---|---|
| lease_id | `LEASE-IMPL-V4-01-A-GROUP` |
| business_key | `IMPL-v4-01:REMOTE_TEST:a-group` |
| target_host | 192.168.1.9 |
| lessee | I1_INTEGRATION |
| executor | claude-lane-loop-executor |
| granted_at | 2026-10-22T15:28:04+08:00 |
| lease_until | **2026-10-22T20:00:00+08:00**（约 4.5h 窗口；未完可经本通道申请续租，续租仍单环境串行） |
| 隔离工作树 | `1.9:/lei/datara/rebuild-source/`（沿用既有 /lei/ 隔离树；宿主侧写入经 ro bind mount 容器生效，测试件 docker cp 至容器 `/app/tests/rebuild/`，执行容器 `datara-rebuild-api`） |
| evidence_dir | `1.9:/lei/datara/rebuild-source/evidence/rt-impl-v4-01-a-group/`（新建；证据十字段落位并回传 raw_log_paths） |
| 单环境容量 | 1.9 单环境串行；租约存续期内如 03 e2e 等新租约请求到达，自动排队于本租约之后 |

### 授予前提核验（回执时点 15:28:04）

- lifecycle=RUNNING、accepting_work=true、水位 v3-0031 ✓
- active_leases=[]（control/governance-state.json）、remote-test-queue.json leases=[] → 无冲突租约 ✓
- 1.9 可达性即时复测：ICMP 2/2 应答（0% 丢包）+ TCP 18091 TcpTestSucceeded=True → **ENV_VERIFIED** ✓
- REMOTE_TEST 队列仅本项租约请求（RT-IMPL-V4-01-A-GROUP，ready=1）✓

## 授权执行范围（以请求单为准）

1. **全量 pytest**：`datara-backend` 全量测试套（含 IMPL-v4-01 八个配套 test）。
2. **节点 A 证据链闭合复核**：LLM 六端点挂载实证（`/api/v1/rebuild/llm-models` 401 `code:1001` + `/{id}/test` 405）、`rebuild_llm_model` 密文断言、`mask_api_key` 口径。
3. **MySQL 专有路径**：`v0004` 的 `MODIFY` 可空/收窄、`v0002` 的 MySQL 语义，在 1.9 MySQL 上取真实结论。

## 执行条件与边界

1. **租约申请先于执行已满足**；自本回执起至 lease_until 前方可进入 1.9 执行段，到期即停。
2. **隔离写**：仅在 `1.9:/lei/` 隔离树内写入（含证据目录）；**禁写共享路径与控制面**；执行前自检 1.9 可达性，异常即暂停回报，不得自行改道。
3. **证据完备**：证据十字段（business_key / target_host / deliverable_identity / environment_or_lease_id / commands / start_end_time / exit_codes / result_summary / raw_log_paths / executor）落 evidence_dir；raw log 一并归档，禁只回传摘要。
4. **完成回报**：执行毕（或到期、或异常中止）经本通道回报执行结果与租约释放申请；本席复核证据后出 ENV_VERIFIED 判定链记录，业务验收归 Acceptance，本回执不构成 PASS。
5. **续租**：到期未完成，提前经本通道申请续租；未获续租回执前不得越窗执行。

## 登记说明

- 本回执为租约授予权威凭据；`control/remote-test-queue.json`（leases）与 `governance-state.json`（active_leases）的控制面登记由 Flow 准入本回执后落定，本席不直写控制面文件。
- 队列投影 `queues/snapshot.json` 中本项自 LEASED 起由 Flow 依准入刷新。

## 边界声明

- 未写 mailbox / STATE / 队列投影 / 控制面（Flow 专属）；本席仅落本 outbox 回执。
- AOCI 开发期停用，未加载、未调用。
- 本回执授予的是 1.9 执行租约，不替代 Acceptance 业务验收。

—— 集成环境 Integration，LEASE_GRANTED 回执（RT-IMPL-V4-01-A-GROUP）。
