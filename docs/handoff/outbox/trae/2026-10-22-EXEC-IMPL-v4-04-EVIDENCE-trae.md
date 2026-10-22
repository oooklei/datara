# EVIDENCE_READY — IMPL-v4-04（trae 载体）

- **票据**：IMPL-v4-04 · D 组治理载体入库：STATE/mailbox/协作规程/AGENTS.md/.mcp.json/outbox 结构/archive v2-final 一次性集成窗提交
- **域/优先级**：CONTROL / P1 / 依赖无
- **水位锚**：`v3-0006-decision-rulings-d01-d04`
- **载体**：trae（Execution）；**实施性质**：零突变稽核 + 集成窗提交物料准备
- **日期**：2026-10-22

## 1. 票据路径逐项核验（10/10 在位）

| # | 路径 | git 态 | 静态核验结果 |
|---|---|---|---|
| 1 | `docs/handoff/STATE.md` | M（已跟踪，内容=epoch3 重启态） | epoch 3 / RUNNING / 水位 v3-0006 / previous s375 / active 0-0-0 / D01-D04 已裁定 / IMPL ready 6 —— 与 governance-state.json 全字段一致 |
| 2 | `docs/handoff/mailbox.jsonl` | M（已跟踪） | 恰 6 行 = v3-0001..v3-0006，与 `D:\super-develop\runtime\datara-live\events\2026-10-22-restart.jsonl` 前 6 行逐事件一致（event_id/ts/actor/type/payload 全同）；无 v3-0007/0008 混入，符合 Flow「Datara 载体不推进」冻结口径（v3-0007 field_check） |
| 3 | `docs/agents/协作规程.md` | M（已跟踪） | v3 版，当前状态节 = RUNNING / epoch 3 / v3-0006 / D01-D04 已裁定；该路径即注册表 `collaboration_rules` ACTIVE 载体本尊（仓库副本=权威） |
| 4 | `AGENTS.md` | M（已跟踪） | 含 AOCI 停用裁定、域规范、Active handoff 指引；§Active handoff「当前为 STOPPED / epoch 3」一句相对 v3-0002 起 RUNNING 陈旧 → 已报 Ops 取 D0 口径（见 §5-4），不改内容 |
| 5 | `.mcp.json` | M（已跟踪） | 合法 JSON，`{"mcpServers": {}}`，无密钥 |
| 6 | `LICENSE-COMMERCIAL.md` | M（已跟踪） | 双许可（AGPLv3 + 商业）说明完整，非签署文本 |
| 7 | `docs/handoff/README.md` | ??（新增） | epoch 3 交接区说明：STATE/mailbox/outbox 三通道定位与归档指针，口径正确 |
| 8 | `docs/handoff/outbox/` | 混合：新十角色目录（acceptance/claude/codex/decision/flow/integration/ops/reject/task/trae，各含 .gitkeep）为 ??；旧 v2 出箱文件在原路径呈 D（已整体移入 archive v2-final） | 十角色结构齐备；flow/ 当前仅 .gitkeep（v3-0007/0008 引用的两个 fl-* 面缺失）→ 已报 Ops；trae/ 已含本席 ACK 与本证据件 |
| 9 | `docs/handoff/archive/2026-10-22-v2-final/` | ??（新增整卷） | 含 ARCHIVE-POINTER.md、旧 STATE/mailbox、v2 各席出箱快照（b/c/claude/codex/i1/sent/trae）等，与 v3-0001 事件登记的 handoff_archive 位置一致 |
| 10 | `docs/agents/archive/` | ??（新增） | 含 `2026-10-22-v1.4-协作规程.md`，规程旧版归档到位 |

## 2. 一致性预核对（验收项「与 super-develop 权威载体一致」的 Execution 侧预检）

- STATE.md ↔ `control/governance-state.json`：epoch / lifecycle / watermark / previous_epoch_watermark / accepting_work / 恢复闸门叙事 全部一致。PASS
- mailbox.jsonl ↔ `events/2026-10-22-restart.jsonl`：6/6 事件逐行一致，水位截点一致（v3-0006）。PASS
- 协作规程.md ↔ 注册表 ACTIVE 载体路径：同一文件，自证权威。PASS
- 终验归属 Flow（验收标准原文），本席仅预检。

## 3. git 盘点与集成窗提交物料（本席不执行 commit）

工作树同时承载 A/B/C/E 组变更（datara-backend/llm、runtime_node、run_stats、revisions、component_spec、newweb 各 service/view、e2e、根目录 E 组散件等），**不属于本票**。集成窗提交必须按 pathspec 圈定，建议命令：

```powershell
git add -A -- docs/handoff/STATE.md docs/handoff/mailbox.jsonl docs/handoff/README.md docs/handoff/outbox docs/handoff/archive/2026-10-22-v2-final "docs/agents/协作规程.md" docs/agents/archive AGENTS.md .mcp.json LICENSE-COMMERCIAL.md
```

**pathspec 边界两个待裁定项（报 Flow/Ops，提交前定）**：
1. 旧出箱文件删除（`D docs/handoff/outbox/**` 约 190 件）由 `git add -A docs/handoff/outbox` 一并捕获——与 archive v2-final 新增是同一次搬迁的两面，建议纳入；另有 5 件根级搬迁删除（`docs/handoff/2026-10-16-*.md`×4、`监管员启动提示词.md`）不在票据 paths 字面内，但其内容已整体位于 archive/2026-10-22-v2-final/，建议 Flow 一并纳入或明确排除。
2. `docs/handoff/archive/2026-10-22-STATE-S301..S303.md`、`cl-report-epoch3-stop-status.json`（??，在 v2-final 卷外）不在本票 paths，未纳入；归属请 Task/Ops 裁定。

**提交信息草案**（沿用仓库 commit_gate 体例，集成窗执行）：

```
D组治理载体入库（epoch 3 v4-04 集成窗提交）：
STATE/mailbox（v3-0001..v3-0006）+协作规程 v3+AGENTS.md/.mcp.json/LICENSE-COMMERCIAL
+handoff README+outbox 十角色结构（含 epoch3 各席 ACK/证据面）+archive v2-final 整卷
+docs/agents/archive v1.4 规程
commit_gate：FLOW_CONSISTENCY_PASS（与 super-develop 权威载体逐项一致）
+ACCEPTANCE_PASS+PATHSPEC_MANIFEST+NO_SECRET 全过
```

- NO_SECRET 预检：十路径内容无凭据/验证 key（.mcp.json 空配置；mailbox/STATE 仅状态叙事）。PASS

## 4. 状态链与边界遵守

- 本席动作：只读稽核 + 本 outbox 两件输出；**未改**任何票据路径内容，未写 STATE/mailbox/队列投影，未做远测、未领 1.9，**未 commit、未 push**（push=USER_ONLY）。
- 状态：**EVIDENCE_READY**（纯载体，无远测需求）→ 待 Acceptance 审查 PASS → 集成窗按 §3 pathspec 提交 → Flow DONE。

## 5. 报 Ops 事项汇总

1. **指派归属核对（优先）**：events v3-0008 将 IMPL-v4-04 指派 claude（13:44），用户随后指示 trae 领队首票；claude 线无 v4-04 证据件。请 Ops/Flow 确认归属（本证据可作为独立核验采信或与 claude 证据取一，Flow 幂等拒重）。
2. 队列快照水位（v3-0006）落后 events 投影（v3-0008）两拍，in_progress=0 与 v3-0008 ASSIGNED 不一致，请 Flow 对齐投影。
3. v3-0007/0008 引用的 `outbox/flow/fl-ack-online-epoch3-v3-0007.json`、`fl-dispatch-impl-v4-04-dgroup-v3-0008.json` 仓库内缺失。
4. `role-contracts.json` `lifecycle:"STOPPED"` 陈旧字段。
5. `AGENTS.md` §Active handoff「STOPPED / epoch 3」表述陈旧，集成窗提交前是否刷新请给 D0 口径。

—— Execution（trae），IMPL-v4-04 EVIDENCE_READY 提交。
