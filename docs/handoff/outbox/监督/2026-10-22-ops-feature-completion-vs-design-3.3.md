# Ops 对标汇报 · 权威设计 §3.3 功能完成情况 与 实施线现状

- 截至: 水位 `v3-0020-evidence-ready-impl-v4-03`（epoch 3 / RUNNING）
- 对标口径: `docs/increments/2026-10-19-纠偏重构前端权威设计.md` §3.3 功能清单总表（状态列为 2026-10-20 快照，HEAD bd3250d/S152；本报告叠加 epoch 3 在飞批次实况）
- 数据源（只读）: 设计 §3.3、queues/snapshot.json、events v3-0001..v3-0020

## 1. §3.3 总量口径（37 行功能条目）

| 状态 | 数量 | 条目 |
|---|---|---|
| ✅ 已收口交付 | **15** | 工作台｜运行实例与日志、变量管理、依赖配置｜数据源管理、资源管理｜血缘分析、资产地图、元数据目录、标签管理、标准管理、指标目录、指标看板、一致性检查｜权限管理 |
| ✅ 已裁定纳入（待排产交付） | 4 | 运行时节点、集群监控（候 P2 立票）｜访问审计（迁移待立项）｜数仓建模（裁定排后） |
| 🔶 部分实现 | 9 | 工作流定义与编排（协议冻结待验收）｜流数据处理（流表候排产）｜SQL IDE 只读（路由已挂载）｜质量规则/检查任务/异常数据核查/质量报告/质量告警（承接批次待 WBS 细化）｜AI 悬浮助手（仅 run_sql 接线，阻塞于 LLM 端点 FV-02） |
| ⛔ 门禁/阻塞/移除 | 4 | 调度管理（T55 SKIP 语义裁定阻塞）｜同步任务（R3 刻意 RED 门禁）｜SQL IDE DDL（用户裁定排后，R5-B 承接）｜脱敏规则（用户裁定移除本版） |
| ⭕ 待立项/待建 | 5 | 工作流运行监控（§5A.10）｜项目管理前端（§5A.11）｜API 管理、API-Key 管理（新建模立项）｜LLM 模型配置（随增量 15） |

**交付率口径**: 已收口 15/37 ≈ 41%；含"裁定纳入待交付"则范围锁定 19/37 ≈ 51%；范围外仅脱敏 1 项。

## 2. epoch 3 在飞批次 → §3.3 功能映射（增量推进）

| 票 | 状态 | 推进的 §3.3 功能 |
|---|---|---|
| IMPL-v4-01（claude 在飞，P1 关键路径） | ASSIGNED | **LLM 模型配置**（rebuild/llm + llmApi.ts + 契约测试，⭕→收口中，同步解阻 AI 助手 FV-02）｜**工作流运行监控**（run_stats + v0002 修订）｜**运行时节点后端迁移**（runtime_node）｜治理 v0004 token 加固 |
| IMPL-v4-02（待 01，D01 已裁定） | BLOCKED | **权限管理 FE**（PermissionMatrix）｜**数据源管理 FE 收口**｜**运行时节点 FE**（SshNodeManagement）｜NodeConfigPanel/ScheduleDialog/views/system 53 处 |
| IMPL-v4-03（trae，14:30 EVIDENCE_READY） | 待 1.9 远测 | 验收链基建（e2e/playwright/7 测试可收集、tsc GREEN）——非用户功能，支撑 §7.2 八门准绳验收通道 |
| IMPL-v4-04（claude） | **DONE**（ef18c2d） | 治理载体入库（CONTROL，非用户功能） |
| IMPL-v4-05 | READY 可派 | 仓库卫生（MAINTENANCE） |
| IMPL-v4-06 | BLOCKED 待 01..05 | 发布终局 push（用户已同意预授权，Ops relay 已落档待 Flow 接纳） |

**本批次落地后 §3.3 预期变化**: LLM 模型配置 ⭕→✅、工作流运行监控 ⭕→✅（后端侧）、运行时节点 4 要素齐（后端+前端+立票+远测）、权限/数据源 FE 收口补强；已收口行数 15→约 18-19。

## 3. 实施线现状（WIP=2）

| 线 | WIP | 当前 | 备注 |
|---|---|---|---|
| claude | 1 | IMPL-v4-01 | P1 关键路径，04 已 DONE（13:44→14:22 全链 38 分钟样本）后无缝转投 |
| trae | 0（释放） | IMPL-v4-03 EVIDENCE_READY | 待 Integration 1.9 租约跑 e2e → ENV_VERIFIED；线已空出可接 05 |
| codex | 0 | 无 | **空闲且无上线 ACK**（v3-0019 Flow 记录 UNCLAIMED） |

- Task 建议（v3-0019 采纳为 advisory）：释放线接 **IMPL-v4-05**；02 在 01 DONE 后立即回填。
- **库存见底预警**（v3-0019 已登记）：05 派出后 READY 即清零，仅剩 06 终局——§3.3 中 🔶/⛔/⭕ 剩余项（质量五项、调度管理 T55、同步任务 R3、项目管理前端、API/API-Key、SQL IDE DDL）**均未立票**，需 Task/WBS 下一批次立项，避免实施线空转。
- EXC-v4-01：用户已裁选项 A（Ops relay 落档）；快照仍 ready=1，待 Flow 接纳登记并核销。
- R-1（role-contracts/remote-test-queue lifecycle 陈旧 STOPPED 字段）仍 pending Flow 下次投影对齐。
- 03 的两项 Flow 观察项：gitignore e2e 产物缺口（归卫生窗）、evidence 目录入库口径（commit 时裁定）——不阻塞。

## 4. Ops 处置建议

1. **立即可做**: 释放的 trae 线接 IMPL-v4-05（P2/纯本机静态）；codex 线如启用先补上线 ACK 再接票。
2. **瓶颈关注**: 01 为当前唯一 P1 关键路径（后端收口+8 测试+1.9 全量 pytest），其时长直接决定 02/06 解锁；1.9 租约排程将是下一个共享资源竞争点（01 pytest 与 03 e2e 都需 Integration 租约）。
3. **建议下一批立项清单**（供 Task/WBS，未立票项按 §3.4 纪律先登记再实施）: 质量五项承接批次、调度管理 T55 SKIP 语义裁定、同步任务 R3 门禁推进、项目管理前端 §5A.11、API/API-Key 新建模、SQL IDE DDL R5-B、流表新域。
4. **§3.3 状态列刷新**: 本批次 PASS/DONE 后按 §3.4 由 WBS/心跳刷新状态列（Ops 不代写设计文档）。

## 5. 边界声明

Ops 仅只读对标汇报；状态判定以 §3.3 注册快照 + 事件流为准，未替 Decision 裁定、未替 Acceptance 验收、未写共享状态。
