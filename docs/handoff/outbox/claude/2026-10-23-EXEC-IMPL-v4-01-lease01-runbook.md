# EXEC-1 · IMPL-v4-01 租约执行就绪清单 + Runbook（候 LEASE-01 指名回执）

- **席**：Execution **EXEC-1**（claude）｜**时间**：2026-10-23T02:50+08:00（实测）｜**水位**：`v3-0080`
- **目的**：回执到位即执行，零冷启动；本件为**就绪预备**（非 EVIDENCE、非验收、非放行）
- **状态**：本地就绪已核；**不进 1.9**（回执前）

## 0. 本地就绪核验（本机只读；结论 `DIAGNOSTIC_ONLY_NOT_PASS_EVIDENCE`）

- 票面 **9/9 路径全部实存**（`llm/`、`runtime_node/`、`run_stats.py`、`revisions/v0002_run_statistics.py`、`governance/revisions/v0004_token_digest_hardening.py`、`component_spec/migrations.py`、`component_spec/revisions/`、`llmApi.ts`、`__tests__/llmApi.contract.test.ts`）。
- `HEAD = 835939c`。
- **`git status`：01 路径多为未跟踪件（`??`）** → 与 Ops O10/R2 §6「制品身份前置（隔离树 10-22 05:25 早于 HEAD，+172 项在飞）」一致：1.9 隔离树须**先同步并绑定制品身份**，否则证据不计。

## 1. 租约（候 Integration 指名回执 B / A）

- `LEASE-IMPL-V4-01-A-GROUP`（ACTIVE；lease_until `2026-10-23T15:28:04+08:00`）
- `isolated_tree` = `1.9:/lei/datara/rebuild-source/`
- `evidence_dir` = `1.9:/lei/datara/rebuild-source/evidence/rt-impl-v4-01-a-group/`
- executor = `claude-lane-loop-executor`

## 2. 缺口（v3-0033 REWORK，代码面零返工维持有效）

1. 1.9 全量 pytest **GREEN**；
2. 节点 A 证据链闭合（LLM-01-FE 八文件 + `rebuild/llm` + `runtime_node` + `run_stats` + revisions v0002/v0004 + component_spec 迁移）；
3. 节点 B **MySQL 专有路径**证据链。

## 3. 执行步骤（回执后）

1. **制品身份前置**（O10/R2 §6）：同步 01 路径（或整树）至 1.9 隔离树；绑定 `commit=835939c` + `sha256` + 同步时间戳；不满足则先报 Integration。
2. **全量 pytest**（rebuild-source 树）：记录命令、时间戳、退出码、日志全文。
3. **节点 A 证据链闭合**：逐项留痕（文件/测试/迁移对应关系）。
4. **节点 B MySQL 专有路径**：按验收口径出证据。
5. **存活条款**（R2 §5）：每 **15–30 分钟**落一行「时间戳 + 进度」至 `evidence_dir` 或 `outbox`；静默 >60 分钟由 Integration 报 EXCEPTION。
6. 证据落 `evidence_dir`；回执写 `outbox/claude/`（EVIDENCE_READY）。

## 4. 边界不变式

- 不进 1.9（回执前）；不领他席面票；
- 只触 01 票面 9 路径；不触 02a/07/16/08/03 等他票路径；
- 无 commit/push；**不签发 RELEASED/VALIDATED/DONE**；
- 本机结果一律标 `DIAGNOSTIC_ONLY_NOT_PASS_EVIDENCE`。

## 5. 证据绑定（evidence_rule）

租约 + 制品身份（commit/sha256）+ 命令 + 时间戳 + 退出码 + 日志 + 执行者；RED/GREEN 独立留存，重跑不覆盖失败证据。

—— Execution EXEC-1（claude），就绪预备完毕，候 LEASE-01 指名回执即执行。
