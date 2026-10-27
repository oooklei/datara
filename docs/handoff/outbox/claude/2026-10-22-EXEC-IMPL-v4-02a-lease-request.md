# 租约请求 · RT-IMPL-V4-02a-SSHNODE-DOMAIN（致 Integration）

- **请求席**：Execution（claude）｜**票据**：IMPL-v4-02a（B 组前端收口 02a 段，P1）
- **受理席**：Integration（租约管理）｜**执行席**：claude-lane-loop-executor
- **目标环境**：192.168.1.9｜**水位**：`v3-0045-lease-request-rt-impl-v4-03-c-group`
- **请求时间**：2026-10-22｜**响应对象**：本件（先于任何 1.9 执行）

---

## 1. 请求项

| 字段 | 值 |
|---|---|
| business_key | `IMPL-v4-02a:REMOTE_TEST:sshnode-domain` |
| deliverable | ① 1.9 vitest 契约测试 GREEN（sshNode 域 4 件 + llmApi）；② sshNode 域 1.9 端到端 GREEN（`/dep/ssh` 页面，经 18091） |
| target_host | 192.168.1.9 |
| lessee | I1_INTEGRATION |
| executor | claude-lane-loop-executor |
| lease_until | 随本窗（候 Integration 设定；1.9 单环境串行） |
| evidence_dir | 1.9 隔离工作目录（沿用 `/lei/` 隔离树，**禁写共享路径**） |

## 2. 执行内容

1. **契约测试（vitest，1.9 执行）**：`datara-newweb` 契约测试套中本票相关件——
   - `src/services/rebuild/__tests__/sshNodeApi.contract.test.ts`（3 用例：权限面冻结 / 五端点映射 + R-34 回显 / 1003 错误码透传）
   - `src/views/__tests__/sshNodeManagementView.contract.test.ts`（3 用例：列表 + R-34 / VIEW_ALL 降级 / 编辑全量替换载荷）
   - `src/views/__tests__/resourceManagementView.contract.test.ts`（2 用例：三类型枚举 / 不可变版本链 + 显式版本绑定）
   - `src/components/__tests__/scheduleDialog.contract.test.ts`（15 用例：9-03 验收锚 + 9-05 SKIP 语义）
   - `src/services/rebuild/__tests__/llmApi.contract.test.ts`（node A 收口复核）
2. **sshNode 域 1.9 端到端**：`/dep/ssh` 页面 CRUD + probe 闭环（**验证入口固定 `http://192.168.1.9:18091/`；禁 8090；18090 被并行验证栈占用**）。
   - ⚠️ **用例件缺口**：`datara-newweb/e2e/` 现无 sshNode 用例（详见 `2026-10-22-EXEC-IMPL-v4-02a-ops-report-boundary-and-findings.md` §E-1）——e2e 产出方式候 Ops/Flow 定路；若授权新增用例件，请回填授权凭据。
3. **后端契约面复核（可选，若窗口允许）**：`/api/v1/rebuild/ssh-nodes` 五端点 401 `code:1001` + 403 `code:1003` 实证。

## 3. 前置与边界

- **租约申请先于任何 1.9 执行**（TEST-ENVIRONMENT-POLICY §1/§4）；本请求即该前置。
- 本机（实施席）**零测试执行**：已完成的仅静态稽核（`vue-tsc -b` EXIT 0 / `tsc --noEmit -p tsconfig.node.json` EXIT 0 / NO_SECRET 0 命中）+ 契约对齐 + 证据包。
- 本席**不写** `control/remote-test-queue.json` / `governance-state.json`（控制面文件，他席职权）；登记归属请 Integration/Flow 定。
- **排队**：现网 ACTIVE 租约 `LEASE-IMPL-V4-01-A-GROUP`（lease_until 20:00:00）；本请求按回执规则自动排队其后。
- 证据十字段（business_key / target_host / deliverable_identity / environment_or_lease_id / commands / start_end_time / exit_codes / result_summary / raw_log_paths / executor）由执行席落 1.9 隔离目录。

## 4. 回执请求

请 Integration 回执：`LEASE_GRANTED`（含 lease_id / lease_until / 隔离工作目录绝对路径）或 `LEASE_DEFERRED`（含原因）。**回执前本席不进 1.9 执行段。**

—— Execution（claude），IMPL-v4-02a 租约请求。
