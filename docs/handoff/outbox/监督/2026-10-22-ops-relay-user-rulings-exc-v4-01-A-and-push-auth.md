# Ops 呈递 · 用户两项裁定记录（呈 Flow 接纳执行）

- 记录席位: 运行监督 Ops
- 记录时间: 2026-10-22（当时水位 `v3-0018-integration-commit-impl-v4-04`，epoch 3 / RUNNING）
- 裁定来源: 用户在 Ops 会话中对待用户项"EXC-v4-01 正位裁定（Ops 建议 A）、IMPL-v4-06 的 push 授权"明确批复 **"同意"**
- 性质: D4 级用户直接裁定记录（D4 归用户；Decision 无需再出 Envelope，本记录即用户授权凭据，由 Flow 接纳登记）

## 裁定 1 · EXC-v4-01 = 选项 A（注册表正位至 super-develop events）

- 内容: authority-carrier-registry.json 中 `mailbox` / `state_view` 两项 ACTIVE 锚点由 Datara 仓库 handoff 路径迁移至 super-develop events 投影（`D:\super-develop\runtime\datara-live\events\2026-10-22-restart.jsonl`）。
- 语义与边界:
  - super-develop events 投影自 v3-0007 起已是事实唯一事件写入点，选项 A 将其正式确立为唯一权威；过渡行为转正，无额外迁移动作。
  - Datara 仓库 `STATE.md` / `mailbox.jsonl` 维持 v3-0006 冻结截点（已随 ef18c2d 入库），降为非权威快照，不再由 Flow 双写。
  - 执行席: Flow（唯一共享控制载体写入者）更新注册表并核销/关闭 EXC-v4-01，authority=USER_EXPLICIT_INSTRUCTION（本记录）。
  - Ops 不执行注册表变更，仅呈递裁定。

## 裁定 2 · IMPL-v4-06 push 授权（同意）

- 内容: 用户授权 IMPL-v4-06 终局一次性 push。
- 执行边界（Ops 记录口径）:
  - 授权对象 = 06 票定义的聚合 push：既有 5 提交 + ef18c2d + IMPL-v4-01..05 新批次发布清单，一次性执行。
  - 06 当前仍 BLOCKED（待 01..05 完成）；本授权为终局闸门预授权，**不构成对当前中间态（仅 ef18c2d + 既有 5 提交在本地）立即 push 的指令**。push 时机仍按完成链：01..05 DONE → 06 聚合发布清单 → 依本授权执行 push 并登记结果。
  - 若用户另有"立即 push 现有本地提交"意图，请用户另行明确指令，Flow/Integration 方可提前执行。
  - push 执行与结果登记: Flow/Integration（USER_ONLY 授权已由本记录落档）。

## 边界声明

Ops 仅登记呈递用户裁定，未写 mailbox/STATE/队列投影/注册表，未执行 push，未替任何席位实施。
