# Ops 呈递 · 用户指令：02a 派 claude + Task 同步立下一批

- 记录席位: 运行监督 Ops
- 记录时间: 2026-10-22（当时水位 `v3-0029-integration-patrol-v3-0024`，epoch 3 / RUNNING；15:08 的 02 解耦呈递件尚候心跳接纳，本指令为用户点名直接执行版，效力衔接前件）
- 指令来源: 用户在 Ops 会话明确下令"02a 派 claude，Task 同步立下一批"
- 性质: 用户直接指令（authority=USER_EXPLICIT_INSTRUCTION）

## 指令 1 · 02a 即时派 claude（点名派发，不等心跳）

- **用户裁定**: IMPL-v4-02a（并行段）即刻派发至 claude 线，绕过心跳等待（沿用"立即派单"口径的点名版）。
- **前置（衔接 15:08 呈递件已获批的解耦裁定）**: Task 先完成 02 票面重构——
  - **02a 并行段**: sshNodeApi + SshNodeManagementView、ResourceManagementView、NodeConfigPanel、ScheduleDialog、views/system（不触 D01 契约口径，路径与 01 文件级不相交）
  - **02b 契约尾段**: datasourceApi/rolePermissions 的 L3-04 口径 + 403 错误态对齐 + 契约测试联跑 + 1.9 端到端（保持排在 01 契约冻结之后）
- **执行席位**: Task 发布 02a 票面（拆分或同票分段标注）→ Flow DISPATCH_ASSIGNED（02a→claude）→ claude 接票。
- **claude 线实况**: 自 01 EVIDENCE_READY（v3-0026）已释放、当前空闲，本指令落地即恢复满载。

## 指令 2 · Task 同步立下一批

- **用户裁定**: Task 席即刻按 WBS/§3.4 纪律发布下一批 READY 库存。
- **建议范围（Ops advisory，Task 按 WBS 定案/排序）**:
  - 质量五项承接批次（质量规则/检查任务/异常数据核查/质量报告/质量告警，🔶 承接批次待细化）
  - 项目管理前端 §5A.11（⭕ 待建，顶层导航关键）
  - API 管理 / API-Key 管理（⭕ 新建模立项）
  - 流表新域（🔶 候排产）
  - F-2 独立票（P3/MAINTENANCE，Ops 已分类 D1-D2；方向"挂载 vs 删死码"候 Decision，建议随批路由 DECISION 队列）
  - T55 SKIP 语义裁定（调度管理 ⛔ 解锁前置——为裁定项非实施票，建议随批路由 DECISION 队列）
- **优先级**: 按权威设计关键路径 + WBS 依赖序定 base/effective priority；用户未下 override。
- **派发节奏说明**: 用户本指令点名即时派发的仅 02a→claude；下批票按 Flow 心跳正常派发节奏执行（用户未逐张点名）。trae 线已释放（05 EVIDENCE_READY），为下批首票的自然消费线；若用户要求下批首张也绕过心跳，另行一句话即可。

## 边界声明

Ops 仅登记呈递；票面拆分归 Task、派单/接纳归 Flow、契约边界与 F-2/T55 方向归 Decision。未写共享状态、未代派单、未代立票。
