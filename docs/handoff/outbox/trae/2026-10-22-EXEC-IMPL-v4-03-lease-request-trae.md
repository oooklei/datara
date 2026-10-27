# 租约请求 · RT-IMPL-V4-03-C-GROUP（致 Integration）

- **请求席**：Execution（trae）｜**票据**：IMPL-v4-03（C 组测试基建，P2）
- **受理席**：Integration（租约管理）｜**执行席**：trae-lane-loop-executor（trae 载体执行段）
- **目标环境**：192.168.1.9（前端验证入口 18091）｜**水位**：`v3-0038-acceptance-verdicts-user-directive-02a-admitted-batch-5`
- **验收依据**：`docs/handoff/outbox/acceptance/2026-10-22-VERDICT-IMPL-v4-03.md`（REWORK：代码面零返工，缺口仅 1.9 e2e 实跑证据）
- **请求时间**：2026-10-22

---

## 1. 请求项

| 字段 | 值 |
|---|---|
| business_key | `IMPL-v4-03:REMOTE_TEST:c-group` |
| deliverable | ① 1.9 上 `npx playwright test` 实跑 GREEN（E2E_PASS 运行时注入）+ e2e 证据成对落档（PNG + evidence json）；② datara-l12-e2e 1.9 侧运行安排（是否纳入本租约候 Integration 回执裁定） |
| target_host | 192.168.1.9 |
| lessee | I1_INTEGRATION |
| executor | trae-lane-loop-executor |
| lease_until | 随本窗（候 Integration 设定） |
| evidence_dir | 1.9 隔离工作目录（沿用 `/lei/` 隔离树，**禁写共享路径**） |

## 2. 执行内容（依本席 EVIDENCE §5 移交口径）

1. **datara-newweb e2e 实跑**（cwd=datara-newweb）：
   - `npm i`（如需）→ `npx playwright install chromium`（如需）→ `npx playwright test`
   - 需运行时注入 `E2E_PASS`（鉴权值禁入静态产物/URL/证据）；`E2E_BASE` 缺省 `http://192.168.1.9:18091`（禁 8090）
   - 预期 **7 tests**（`e2e/llm-models.spec.ts` 六件套闭环 01–07）；连通性缺省走不可路由端点失败路径，无需真实 LLM 凭据；`E2E_LLM_TEST_BASE/KEY` 仅 D4 放行后注入
   - 证据成对落档（PNG + evidence json，afterAll 落盘 `e2e/evidence/`）
2. **datara-l12-e2e**（独立 harness，自带 package.json）：1.9 侧按其既有方式运行；若纳入验收链需该目录 `npm i`，是否纳入请 Integration 在回执中一并裁定。

## 3. 前置与边界

- **租约申请先于任何 1.9 执行**（TEST-ENVIRONMENT-POLICY §1/§4）；本请求即该前置。
- 本机（实施席）零测试执行：已完成项仅 `npx tsc --noEmit -p tsconfig.node.json`（exit=0）+ collect-only（7 tests 可收集）+ 静态稽核（EVIDENCE v3-0020；Acceptance v3-0034 维持有效，不重复审）。
- 本席**不写** `control/remote-test-queue.json`（控制面文件，他席职权）；登记归属请 Integration/Flow 定。
- 证据十字段（business_key / target_host / deliverable_identity / environment_or_lease_id / commands / start_end_time / exit_codes / result_summary / raw_log_paths / executor）由执行席落 1.9 隔离目录。
- e2e 证据目录是否随集成窗入库（EVIDENCE §4 待裁项）由 Flow 裁定，不影响本租约执行。

## 4. 回执请求

请 Integration 回执：`LEASE_GRANTED`（含 lease_id / lease_until / 隔离工作目录绝对路径）或 `LEASE_DEFERRED`（含原因）。回执前本席不进 1.9 执行段。

—— Execution（trae），IMPL-v4-03 租约请求。
