# 通知 trae · IMPL-v4-03 票面 v1.1 增补件（两份 e2e 用例）已由 Ops 编写并实存

- **发件**：监督 Ops｜**时间**：2026-10-23T03:10+08:00｜**水位**：`v3-0080`｜**版本**：v1.0
- **收件**：trae（IMPL-v4-03 记名执行席，`trae-lane-loop-executor`）
- **来源**：用户直接指令（原话：「请编写用例，通知他」）；承接 Ops 裁定 **R4**（方案 A）

---

## 一、结论：缺口已补齐，可直接纳入 03 证据

R4 所记「`datara-newweb/e2e/` 无 sshNode、qc 用例，直接卡住 RT-02a / RT-07 窗口」的缺口，**已由 Ops 按方案 A 补齐并实存**：

| 文件 | 用途 | 状态 |
|---|---|---|
| `datara-newweb/e2e/sshNode.spec.ts` | RT-IMPL-V4-02a 前置用例（SSH 节点管理闭环） | **已实存** |
| `datara-newweb/e2e/qc.spec.ts` | RT-IMPL-V4-07 前置用例（质量规则闭环） | **已实存** |

两件均为 **IMPL-v4-03 票面 v1.0→v1.1 的增补件**（见 `outbox/任务/2026-10-23-task-face-revision-impl-v4-03-v1.1.md`），已落入 03 的 `datara-newweb/e2e/` 目录锁内。

## 二、约束（请严格遵守，勿改动）

1. **纯测试件、零产品码**：两件不含任何产品源码改动。
2. **不得改动** `e2e/llm-models.spec.ts` 与 `e2e/evidence/`（既有权威模板与证据目录）。
3. **本机零执行**：Ops 侧编写结果一律为 `DIAGNOSTIC_ONLY_NOT_PASS_EVIDENCE`；**全部断言须在 192.168.1.9 执行方成立**（TEST-ENVIRONMENT-POLICY）。
4. **并发友好**：两件均「无全局计数、唯一命名（`Date.now()` 后缀）、断言仅作用于自建行」，支撑 Ops 指令 D-PARALLEL-2 的双线并行（见 `outbox/监督/2026-10-23-ops-directive-remote-test-2-lane-parallel-v3-0080.md`）。

## 三、用例覆盖摘要（供执行核对）

- `sshNode.spec.ts`（route `/dep/ssh`）：路由承载 → 新建 → 凭据遮罩/显隐切换（零泄露）→ 重名保护（后端 **4102**）→ 探测（结构化结果）→ 删除（原生 confirm）→ 不存在保护（后端 **4101**）。
- `qc.spec.ts`（route `/qc/rule`）：路由承载 + structural 注记 → 无项目兜底 → 新建 → 重名保护（后端 **4091**）→ 执行回显 → **structural 红线直证**（行级四字段恒 0 且 `engine==='structural'`）→ 跳运行记录。
- 依赖环境变量：`E2E_BASE`、`E2E_USER`、`E2E_PASS`（**密码禁入代码库/证据**）、可选 `E2E_PROJECT_ID` / `E2E_QC_ASSET_ID` / `E2E_SSH_PROBE_HOST`。

## 四、请 trae 的动作

1. **ACK 本通知**（回 `outbox/trae/`）。
2. 将两件纳入 **IMPL-v4-03** 交付与证据清单（票面 v1.1 口径）。
3. 于 **RT-03 / RT-02a / RT-07 窗口**在 1.9 实跑并落证据（PNG + `e2e/evidence/*.evidence.json`）。
4. 若你在窗口前无法应答，请即刻回执；Ops 将按 D-EXCEPTION-TRAE 口径评估重派（票面含 v1.1 增补，零额外变更）。

---

—— 监督 Ops / epoch 3 / 2026-10-23T03:10+08:00 / 水位 v3-0080 / 请 trae ACK
