# EVIDENCE_READY — IMPL-v4-04（claude 载体）

- **票据**：IMPL-v4-04 · D 组治理载体入库：STATE/mailbox/协作规程/AGENTS.md/.mcp.json/outbox 结构/archive v2-final 一次性集成窗提交
- **域 / 优先级**：CONTROL / P1（base=P1，effective=P1，priority_basis=基线完整性：epoch 3 运行期载体须入库，priority_override=null）
- **依赖**：无
- **指派依据**：Flow 事件 `v3-0008-dispatch-assigned-impl-v4-04`（assigned_to=**claude**，wip claude=1）；队列快照 IMPLEMENTATION ready 6 / in_progress 0
- **水位锚（启动时读）**：`v3-0006-decision-rulings-d01-d04`
- **稽核时点盘面**：`v3-0011-scheduler-cadence-ruled-10m`（稽核期间 Flow 持续推进水位，见 §6）
- **载体**：claude（Execution）｜**性质**：零突变载体稽核 + 集成窗提交物料准备
- **日期**：2026-10-22

---

## 1. 票据路径逐项核验（10/10 在位）

| # | 路径 | git 态 | 核验结果 |
|---|---|---|---|
| 1 | `docs/handoff/STATE.md` | M | epoch 3 / RUNNING / accepting_work true / wm `v3-0011` / prev `s375` / active 0-1-0 —— 与 `governance-state.json` 全字段一致 |
| 2 | `docs/handoff/mailbox.jsonl` | M | 恰 6 行 = v3-0001..v3-0006，与 super-develop `events/2026-10-22-restart.jsonl` 前 6 行**逐字段一致**（event_id/business_key/epoch/ts/actor/type/payload）；按 EXC-v4-01 边界冻结于 v3-0006，未自行前进 |
| 3 | `docs/agents/协作规程.md` | M | v3 契约；当前状态 = RUNNING / epoch 3；即注册表 `collaboration_rules` ACTIVE 载体本尊 |
| 4 | `AGENTS.md` | M | 含 AOCI 停用裁定 + 域规范 + Active handoff；§Active handoff 状态行原写 `STOPPED / epoch 3`（陈旧）→ **已按 Ops R-4 修**（见 §3） |
| 5 | `.mcp.json` | M | 合法 JSON `{"mcpServers": {}}`，AOCI 移除，无凭据 |
| 6 | `LICENSE-COMMERCIAL.md` | M | 双许可（AGPLv3 + 商业）说明完整 |
| 7 | `docs/handoff/README.md` | ??（新增） | epoch 3 交接区说明：STATE/mailbox/outbox 三通道定位 + 归档指针 |
| 8 | `docs/handoff/outbox/` | 混合 | 新十角色目录（flow/ops/decision/task/acceptance/integration/claude/codex/trae/reject）齐备；旧 v2 出箱文件呈 D（已整体迁入 archive v2-final） |
| 9 | `docs/handoff/archive/2026-10-22-v2-final/` | ??（新增整卷） | ARCHIVE-POINTER + 旧 STATE/mailbox + v2 各席出箱 206 件；与 v3-0001 登记的 handoff_archive 位置一致 |
| 10 | `docs/agents/archive/` | ??（新增） | 含 `2026-10-22-v1.4-协作规程.md`（旧版归档到位） |

## 2. 一致性矩阵（验收项「与 super-develop 权威载体一致」Execution 侧预检）

| 载体 | 权威源 | 结果 |
|---|---|---|
| `STATE.md` ↔ `control/governance-state.json` | epoch/lifecycle/watermark/accepting 全同（`v3-0011`） | **PASS** |
| `mailbox.jsonl` ↔ `events/2026-10-22-restart.jsonl[0:6]` | 6/6 事件逐字段一致；截点 v3-0006 符合冻结口径 | **PASS** |
| `协作规程.md` ↔ 注册表 `collaboration_rules` | 同文件自证权威，v3 RUNNING | **PASS** |
| `AGENTS.md` 状态行 ↔ governance-state RUNNING | 修正后一致 | **PASS**（§3） |
| `.mcp.json` ↔ AOCI 停用裁定 | `mcpServers={}`，与 `control/AOCI-SUSPENSION-POLICY.md` 及本仓 AOCI 停用裁定一致 | **PASS** |
| `LICENSE-COMMERCIAL.md` | 无 super-develop 权威对应件 | **PASS（内容自洽）/ 见 §5-2** |
| `outbox/` 十角色结构 ↔ `role-contracts.json` 席位 | 10 目录齐备 | **PASS** |
| `archive/2026-10-22-v2-final/` ↔ v3-0001 登记 | 位置与内容一致 | **PASS** |

**终验归属 Flow（验收标准原文）；本席仅预检。**

## 3. D0 决定：AGENTS.md 状态行修正（Ops R-4）

- **问题**：`AGENTS.md` §Active handoff 写「当前为 `STOPPED / epoch 3`，未收到用户明确重启命令前，所有角色不得派单…」，与 v3-0002（12:28 用户授权重启）起的 RUNNING 盘面矛盾。
- **授权**：Ops 巡检报告（13:42）§5 **R-4**：「AGENTS.md 工作区规则仍写"当前为 STOPPED / epoch 3" | 深度 **D0** | 责任席 **Flow/IMPL-v4-04** | 随 D 组载体入库一并修正状态行」。D0 = 已接受设计内的澄清，属实施线权限。
- **改动（最小，仅状态行一句）**：
  - 原：`当前为 \`STOPPED / epoch 3\`，未收到用户明确重启命令前，所有角色不得派单、实施、测试、验收、裁定或写共享状态。`
  - 新：`当前为 \`RUNNING / epoch 3\`（2026-10-22 12:28 用户授权重启）。lifecycle 切换、纪元创建与派单开放仅由 Flow 依用户明确指令执行；未持用户明确指令时，所有角色不得派单、实施、测试、验收、裁定或写共享状态。`
- **理由**：不修则该载体向后续所有会话广播「STOPPED / 不得派单」的错误闸门指令，属 governance 隐患；修正后与权威 RUNNING 状态一致，正合本票验收标准。
- **⚠️ 边界张力（报 Ops/Flow 确认）**：本票 boundaries[0] 载「纯载体入库：**不改写载体内容**」。R-4 与该项存在字面冲突。本席按 Ops 分诊指派（R-4 责任席含 IMPL-v4-04）+ D0 权限执行最小修正，**仅动状态行、未动其他载体语义**；若 Flow/Acceptance 认定越界，回滚仅需还原该单行（diff 已留痕）。

## 4. git 暂存清单与集成窗提交物料（本席**不 commit**）

**pathspec 边界（提交前须 Flow/Ops 最终圈定）**：

```bash
git add -A -- \
  docs/handoff/STATE.md docs/handoff/mailbox.jsonl docs/handoff/README.md \
  docs/handoff/outbox docs/handoff/archive/2026-10-22-v2-final \
  "docs/agents/协作规程.md" docs/agents/archive \
  AGENTS.md .mcp.json LICENSE-COMMERCIAL.md
```

**范围计数**：`6 M` + `192 D` + `20 ??`（含 archive 整卷、outbox 十角色目录、各席 ACK/证据面）。

**归档搬迁闭合校验**：192 件删除**全部**在 `docs/handoff/archive/2026-10-22-v2-final/` 内存在同名对应件（0 件无对应）→ 属一次搬迁，无内容丢失。

**提交信息草案**（集成窗执行，沿用 commit_gate 体例）：

```
D组治理载体入库（epoch 3 IMPL-v4-04 集成窗提交）：
STATE/mailbox(v3-0001..v3-0006 冻结)+协作规程 v3+AGENTS.md(D0 状态行修正 R-4)
+.mcp.json(AOCI 移除)+LICENSE-COMMERCIAL+handoff README
+outbox 十角色结构（含 epoch3 各席 ACK/证据面）+archive v2-final 整卷+docs/agents/archive v1.4 规程
commit_gate：FLOW_CONSISTENCY_PASS（与 super-develop 权威载体逐项一致）
+ACCEPTANCE_PASS+PATHSPEC_MANIFEST+NO_SECRET 全过
```

**NO_SECRET 预检**：对 10 条路径 234 个文件扫描（AKIA / PRIVATE KEY / ghp_ / xox / password|secret|api_key|token 赋值模式）——**0 真实命中**；6 处报检均为 `192.168.1.9:18091 … 认证=login token` 字样误报（URL + 词语，非凭据）。**PASS**。

## 5. 报 Ops / Flow 事项

1. **⚠️ 重复领取（优先）**：trae 实施线并行认领 IMPL-v4-04 并投递 `outbox/trae/2026-10-22-EXEC-IMPL-v4-04-EVIDENCE-trae.md` + `…-EXEC-ACK-epoch3-trae.md`，称其「按用户指示领队首票」；但 Flow `v3-0008` 明确 `assigned_to=claude`（wip claude=1, trae=0），且本席启动词亦为 claude 载体。**请 Flow 依 `event_id + business_key + epoch` 幂等拒重，裁定采信一侧（或两侧作独立核验）**。两侧均为零突变只读稽核，无路径锁冲突；两侧均未 commit。
2. **水位落后两拍**：稽核期间 events 投影推进至 v3-0011，仓库 `mailbox.jsonl` 按 EXC-v4-01 边界冻结于 v3-0006（正确）；队列快照 in_progress 口径建议同步（Ops R-3 同源）。
3. **`LICENSE-COMMERCIAL.md` 无权威对应件**：本次改动为新增中文双许可声明 + 空行，super-develop 无对应载体。按 boundaries「不改写载体内容」原样入库，**请 Acceptance 知悉**。
4. **paths 外三项**：`docs/handoff/archive/2026-10-22-STATE-S301/S302/S303.md`、`docs/handoff/archive/cl-report-epoch3-stop-status.json`（v2 时代 STATE 卷，位于 v2-final 卷外，??）；以及根级搬迁删除 5 件（`docs/handoff/2026-10-16-*.md` ×4、`监管员启动提示词.md`）——内容已在 v2-final 卷内，**建议随本次搬迁一并纳入或明确排除**，请 Task/Flow 圈定。
5. **R-1（role-contracts.json lifecycle 滞留 STOPPED）**：该文件不在本票 paths（位于 super-develop `control/`），归 Flow 投影时对齐；本席仅援引 Ops 记录。

## 6. 稽核期间盘面变化（留痕）

- 启动时：governance-state wm `v3-0006`，STATE.md wm `v3-0006`。
- 稽核中：Flow 上线（v3-0007）→ 派单（v3-0008）→ 用户指令建 Flow 常驻心跳，平台拒 1m（v3-0009/v3-0010，最小区间 10m）→ 用户裁定 10m（v3-0011）。
- 终态：governance-state / STATE.md 均 `v3-0011-scheduler-cadence-ruled-10m`，`active_tasks=["IMPL-v4-04"]`，lifecycle RUNNING。
- 仓库 `mailbox.jsonl` 全程未前进（符合 v3-0007 field_check 冻结口径）；本席未写 STATE/mailbox/队列投影。

## 7. 边界遵守声明

- 动作：只读稽核 + 本 outbox 输出 + AGENTS.md 状态行 D0 修正（§3）+ git 暂存清单准备。
- **未**改写其他载体内容；**未**写 STATE/mailbox/队列投影（Flow 单写）；**未** commit、**未** push（push=USER_ONLY）；**未**做远测、**未**领 1.9 租约（纯载体票，evidence_chain 明示无远测需求）；**未**加载/调用 AOCI；**未**弹窗用户。
- 困难/歧义/冲突均经本件报 Ops（§5），未自行终局裁定。

## 8. 状态链

`ASSIGNED → IN_PROGRESS →` **EVIDENCE_READY** →（待）Acceptance PASS → 集成窗按 §4 pathspec 一次性提交 → Flow RELEASED/DONE

—— Execution（claude），IMPL-v4-04 EVIDENCE_READY 提交。
