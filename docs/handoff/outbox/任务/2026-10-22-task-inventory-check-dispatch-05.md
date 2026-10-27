# IMPLEMENTATION 库存核对与派单建议（增量 05）

- **席位**: Task / epoch 3 / RUNNING
- **基线水位**: `v3-0018-integration-commit-impl-v4-04`（前次：2026-10-22-task-inventory-check-dispatch-04.md）
- **当前水位**: `v3-0029-integration-patrol-v3-0024`
- **动作性质**: 增量库存核对 + 派单建议；提交流程控制 Flow 接纳，Task 不写队列投影

## 一、变化检测（相对基线）

| 变化项 | 基线（增量 04） | 当前 | 判定 |
|---|---|---|---|
| 水位 | v3-0018 | **v3-0029-integration-patrol-v3-0024** | 推进 |
| IMPL-v4-01 | ASSIGNED 在飞（claude） | **EVIDENCE_READY**（event `v3-0026`；本机静态稽核全过 + D04 注释修正 + D03 勘误登记；新发现 F-2 死代码已路由 Ops） | 状态变更 |
| IMPL-v4-03 | ASSIGNED 在飞（trae） | **EVIDENCE_READY**（event `v3-0020`） | 状态变更 |
| IMPL-v4-05 | READY（连续两周期未被派单） | **EVIDENCE_READY**（event `v3-0028`，trae，14:40） | 状态变更：已派单并交证据，增量 04 派单建议被采纳 |
| EXC-v4-01 | D4 候用户裁定（A/B/C 三方案） | **已裁定选项 A 并核销关闭**（`v3-0023-user-rulings-relayed-exc-v4-01-A-push-auth`，Ops 转达用户裁定：注册表锚点正位 super-develop events 投影；Datara 仓 STATE.md/mailbox.jsonl 降为非权威快照，mailbox 冻结 v3-0006 不变，STATE.md 终局行后 Flow 停写；R-1 lifecycle 陈旧字段一并对齐） | EXCEPTION 变动 |
| IMPL-v4-06 | BLOCKED（push 待授权） | BLOCKED，**blocked_reason 补录 push 预授权**（v3-0023 Ops 转达：01..05 全 DONE + 06 发布清单后一次性聚合 push，非即时 push 指令） | 状态附注更新 |
| REMOTE_TEST | 空 | **新增 RT-IMPL-V4-01-A-GROUP READY**（租约请求，event `v3-0027`，候 Integration 回执 LEASE_GRANTED/LEASE_DEFERRED） | 新增条目 |
| DECISION | D01-D04 已裁定（v3-0006） | 无新增 | 未变 |
| IMPL-v4-04 | DONE（ef18c2d） | DONE | 未变 |
| 队列计数 | ready 1 / assigned 2 / blocked 2 | ready 0 / in_progress 3 / blocked 2 | 计数变化 |

**触发判定**：水位推进 + 三票状态变更 + EXCEPTION 核销 + REMOTE_TEST 新增 → 产出本增量。

## 二、逐票复核（六票）

| 票 | 四字段（base/effective/basis/override） | 依赖 | 判定 |
|---|---|---|---|
| IMPL-v4-01 | P1/P1/权威设计关键路径 LLM 域；停机在飞残留首位（决策卡 A 组）/null ✓ | D03、D04 已裁定（v3-0006）✓ | **EVIDENCE_READY**；下一步 1.9 全量 pytest（租约 RT-IMPL-V4-01-A-GROUP 候 Integration 回执，回执前不进 1.9 执行） |
| IMPL-v4-02 | P1/P1/前端关键路径；basis 文本仍载"PROJ-FE-01 候裁解锁"（D01 已裁定选项①，解锁已落地，属历史快照表述，优先级无偏，无需动作）/null ✓ | D01 ✓ + IMPL-v4-01 未 DONE ✗ | BLOCKED 保位，不占队首；01 DONE 后立即补位 |
| IMPL-v4-03 | P2/P2/验收链补全（决策卡 C 组）/null ✓ | D02 已裁定 ✓ | **EVIDENCE_READY**；候 ENV_VERIFIED → PASS → 集成窗提交 |
| IMPL-v4-04 | P1/P1/epoch 3 运行期载体须入库（决策卡 D 组）/null ✓ | ∅ ✓ | DONE（ef18c2d）闭环；EXC-v4-01 裁定 A 与已提交载体无冲突（STATE/mailbox 降为非权威快照、mailbox 冻结），无 REWORK 触发 |
| IMPL-v4-05 | P2/P2/仓库根部卫生（决策卡 E 组）/null ✓ | ∅ ✓ | **EVIDENCE_READY**；候静态审查 + 归档位置登记验收 → 集成窗提交 |
| IMPL-v4-06 | P1/P1/发布终局闸门（USER_ONLY，HC-09）/null ✓ | 01..05：04 DONE；01/03/05 EVIDENCE_READY；02 BLOCKED ✗ | BLOCKED 保位，owner User；push 预授权已在案（v3-0023），残余 = 发布清单制备 + 01..05 全 DONE |

**依赖 DAG 无环**：D03/D04→01→02；D01→02；D02→03；∅→05；∅→04（DONE）；{01..05}→06。无循环 ✓。
**BLOCKED 不占 READY 队首**：IMPLEMENTATION READY=0；02/06 BLOCKED 排后 ✓。
**可派库存**：**READY=0（结构性触底）**。六票计划封闭，Task 无法再造合法新库存；02 被 01 门控、06 被全链门控。回填唯一来源 = 01 完成（1.9 pytest GREEN → PASS → DONE）解锁 02。当前吞吐瓶颈在完成链下游（Integration 租约回执 + Acceptance 审查），非派单环节。

## 三、下一调度周期建议（提交 Flow 路由）

IMPLEMENTATION **无新派单**（READY=0；01/03/05 已交证据，不重复派单；02/06 依赖未满足）。

| 序 | 事项 | 授权路径 | 证据/回执要求 |
|---|---|---|---|
| 1 | **RT-IMPL-V4-01-A-GROUP 租约处置**（关键路径首位） | Integration 依 v3-0027 租约请求出具 LEASE_GRANTED/LEASE_DEFERRED 回执；回执前 claude 不进 1.9 执行 | 租约回执事件 + 1.9 全量 pytest GREEN + 节点 A/B 证据链闭合复核 + MySQL 专有路径结果 |
| 2 | **IMPL-v4-05 验收推进**（纯静态，最快闭环） | Integration ENV_VERIFIED（静态审查 + 归档位置登记）→ Acceptance PASS → Flow 集成窗提交 | 静态审查记录 + 归档位置登记；归档优先，删除须用户裁定 |
| 3 | **IMPL-v4-03 验收推进** | Integration ENV_VERIFIED → Acceptance PASS → Flow 集成窗提交 | 1.9 e2e 可运行并纳入验收链；npx tsc --noEmit -p tsconfig.node.json 通过 |
| 4 | **序位预约**：01 DONE 后 02 立即补位派单 | Flow 派单票（依赖 IMPL-v4-01 DONE + D01 选项①：后端闸门 + FE 403 错误态）；01 完成后 claude WIP 归零，建议派 claude | 契约测试 + 1.9 端到端 GREEN |

路径无碰撞：02（datasource/rolePermissions/sshNode services + PermissionMatrix/ResourceManagement/SshNodeManagement views + NodeConfigPanel/ScheduleDialog + views/system）与在飞完成链路径互不交叠。

## 四、风险与提示

1. **瓶颈在完成链而非派单**：READY=0，01/03/05 三票同候下游（租约回执、ENV_VERIFIED、PASS、集成窗提交）。Integration 与 Acceptance 的吞吐决定 02 解锁时点与 06 终局时点；建议 Flow 优先处置序 1 租约回执。
2. **EXC-v4-01 已核销**：注册表 mailbox/state_view 锚点正位 super-develop events 投影（事件流唯一权威转正）；Datara 仓 STATE.md/mailbox.jsonl 降为非权威快照。Task 角色输出面不变（本 outbox 目录仍为票面引用路径所在，继续按契约写本目录）。
3. **F-2（死代码）**：claude 于 IMPL-v4-01 证据期新发现并已路由 Ops，候 Ops 分类；若升级为票，经 Flow 接纳后由 Task 纳入库存并补齐四字段——当前不计入六票封闭计划。
4. **IMPL-v4-06 残余**：push 预授权已在案（v3-0023）；执行 push 时仍以用户授权记录为凭（HC-09），时点 = 01..05 全 DONE + 发布清单就绪。发布清单候 01..05 终态后聚合，勿提前制备。
5. 无新增 DECISION；D01-D04 维持 v3-0006 裁定不变。

---
Task / epoch 3 / 2026-10-22 / 基线 v3-0018 → 当前 v3-0029-integration-patrol-v3-0024 / 提交 Flow 接纳
