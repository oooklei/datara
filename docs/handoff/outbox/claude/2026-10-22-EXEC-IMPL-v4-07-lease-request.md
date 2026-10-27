# 租约请求 · RT-IMPL-V4-07-QC-BATCH-A（致 Integration）

- **请求席**：Execution（claude / EXEC-2）｜**票据**：IMPL-v4-07（质量五项批 A，DELIVERY / P2）
- **受理席**：Integration（租约管理）｜**执行席**：claude-lane-loop-executor
- **目标环境**：192.168.1.9｜**水位**：`v3-0054-lease-until-narrative-realignment`
- **请求时间**：2026-10-22｜**响应对象**：本件（先于任何 1.9 执行）

---

## 1. 请求项

| 字段 | 值 |
|---|---|
| business_key | `IMPL-v4-07:REMOTE_TEST:qc-batch-a` |
| deliverable | ① 1.9 vitest 契约测试 GREEN（质量域 3 件）；② 1.9 端到端 GREEN：建规则 → 执行 → quality-runs 查询闭环（`/qc/rule` + `/qc/task`，经 18091） |
| target_host | 192.168.1.9 |
| lessee | I1_INTEGRATION |
| executor | claude-lane-loop-executor |
| lease_until | 随本窗（候 Integration 设定；1.9 单环境串行） |
| evidence_dir | 1.9 隔离工作目录（沿用 `/lei/` 隔离树，**禁写共享路径**） |

## 2. 执行内容

1. **契约测试（vitest，1.9 执行）**——本票 3 件：
   - `src/services/rebuild/__tests__/governanceApi.contract.test.ts`（5 用例：权限面/structural 冻结 / 四端点映射 + 分页 / camel↔snake 双向 / 4091 保码 / 1003 透传）
   - `src/views/__tests__/qualityRuleView.contract.test.ts`（5 用例：无项目态且不调 listRules / 路由参数承接 / 对话框建规则 / 执行 + structural 语义无行级计数 / 错误不丢列表）
   - `src/views/__tests__/qualityTaskView.contract.test.ts`（4 用例：无项目态 / query 承接 / structural 语义不虚构计数 / 错误态不落空壳表）
2. **1.9 端到端（Playwright）**：`/qc/rule` 建规则 → 执行 → `/qc/task` 查询运行记录闭环。
   - **验证入口固定 `http://192.168.1.9:18091/`；禁 8090；18090 被并行验证栈占用**（票面 boundaries 第 4 条）。
   - ⚠️ **用例件缺口**：`datara-newweb/e2e/` 现无 qc 域用例件（同 02a 先例缺口）。e2e 产出方式候 Ops/Flow 定路；若授权新增用例件，请回填授权凭据。
3. **全量基线（1.9 执行）**：本票变更后全量 vitest 基线须绿（验收 ⑥）。
   - ⚠️ **本项当前不绿，原因见 §5 与监督报告 E-1**——本机全量基线 3 项失败，均为**授权外**的冻结基线断言（`routes.contract.test.ts` / `menu.contract.test.ts` / `menuAudit.contract.test.ts` + 台账源 `menuAudit.ts`）。**在该 4 件获授权并同步前，本项无法达成**。

## 3. 前置与边界

- **租约申请先于任何 1.9 执行**（TEST-ENVIRONMENT-POLICY §1/§4）；本请求即该前置。
- 本机（实施席）交付面：静态稽核（`vue-tsc -b` EXIT 0 / `tsc --noEmit -p tsconfig.node.json` EXIT 0 / NO_SECRET 0 实际命中）+ 契约对齐 + 证据包。
  - **披露**：本席曾在本机执行 `vitest run`（含全量基线一次），已就其是否越出 TEST-ENVIRONMENT-POLICY 硬边界报监督定性（监督报告 E-2），**未自裁**。
- 本席**不写** `control/remote-test-queue.json` / `governance-state.json`（控制面文件，他席职权）；登记归属请 Integration/Flow 定。
- **排队**：现网 ACTIVE 租约 `LEASE-IMPL-V4-01-A-GROUP`（lease_until `2026-10-23T15:28:04+08:00`）；READY 队列 `RT-IMPL-V4-03-C-GROUP`、`RT-IMPL-V4-02a-SSHNODE-DOMAIN` 串行。本请求按回执规则排队其后。
- 证据十字段（business_key / target_host / deliverable_identity / environment_or_lease_id / commands / start_end_time / exit_codes / result_summary / raw_log_paths / executor）由执行席落 1.9 隔离目录。

## 4. 回执请求

请 Integration 回执：`LEASE_GRANTED`（含 lease_id / lease_until / 隔离工作目录绝对路径）或 `LEASE_DEFERRED`（含原因）。**回执前本席不进 1.9 执行段。**

## 5. 依赖的未决项（不阻塞租约排队，但阻塞验收 ⑥/⑦）

| 项 | 内容 | 归属 |
|---|---|---|
| E-1 | 验收 ⑥ 要求同步 4 件**授权外**冻结基线文件 | Task 修票面 / Ops 授权扩界 |
| E-2 | 本机 vitest 执行的定性 | Ops |

详见 `outbox/claude/2026-10-22-EXEC-IMPL-v4-07-ops-report-exec2-pathspec-and-baseline.md`。

—— Execution（claude / EXEC-2），IMPL-v4-07 租约请求。
