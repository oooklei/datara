# Ops 呈递 · 用户提速指令二项（02 部分解耦 + 立即派单）

- 记录席位: 运行监督 Ops
- 记录时间: 2026-10-22T15:08:04+08:00（当时水位 `v3-0020-evidence-ready-impl-v4-03`，epoch 3 / RUNNING）
- 指令来源: 用户在 Ops 会话明确下令"先执行'同意 02 部分解耦'和'立即派单'"（对应 Ops 提速分析 B-3、B-4 两项；B-1/B-2 未单独下令，但"立即派单"的派发对象蕴含释放线语义，见指令 2）
- 性质: 用户直接指令（authority=USER_EXPLICIT_INSTRUCTION），Flow 接纳登记后执行

## 指令 1 · IMPL-v4-02 部分解耦（用户同意）

- **用户裁定**: 同意 02 部分解耦——02 的非 LLM/非契约部分可与 IMPL-v4-01 并行，契约对齐项留尾在 01 之后。
- **事实依据（Ops 已核）**: 01 路径（backend rebuild/llm+runtime_node+run_stats+revisions+component_spec；FE 仅 services/rebuild/llmApi.ts+契约测试）与 02 路径（datasourceApi/rolePermissions/sshNodeApi + 三个视图 + NodeConfigPanel/ScheduleDialog + views/system）**文件级不相交**；仅共享目录 `datara-newweb/src/services/rebuild/`（不同文件，无路径锁冲突，集成窗 pathspec 需协调）。弱关联 = DEC-v4-D01（L3-04 后端闸门+FE 403 错误态）触及 02 的 service 层。
- **建议切分口径（供 Task 依赖整形、Decision 确认边界，Ops 不定案）**:
  - **02a 可并行段**: sshNodeApi+SshNodeManagementView、ResourceManagementView、NodeConfigPanel、ScheduleDialog、views/system 等——不触 D01 契约口径，可即刻随线并行。
  - **02b 契约尾段**: datasourceApi/rolePermissions 的 L3-04 口径 + 403 错误态对齐 + 契约测试联跑 + 1.9 端到端——保持排在 01 契约冻结之后。
- **执行席位**: Task 更新 02 票面与依赖（depends_on 调整/拆分 02a/02b 或同票分段标注）；如涉跨票裁定走 Decision D2/D3；Flow 登记新依赖结构。02a 首个可派窗口 = 下一释放线（05 收口后 trae 可接，或用户启用 codex）。

## 指令 2 · 立即派单（绕过心跳等待）

- **用户裁定**: 立即派发当前 READY 队首，不等 10 分钟心跳周期。
- **派发对象（Ops 依据快照+Task v3-0019 建议判定）**: **IMPL-v4-05（E 组清理归档，P2/MAINTENANCE，纯本机静态）→ trae 线**。
- **释放线语义确认**: 03 已 EVIDENCE_READY（本机工作完，远测 ENV_VERIFIED 归 Integration 席），用户此令蕴含确认 **EVIDENCE_READY 即释放实施线**；Flow 无需再以"trae WIP=1"为由等待。若 Flow 对该口径有异议，请在接纳事件中登记待确认项，勿静默搁置。
- **执行席位**: Flow 立即 DISPATCH_ASSIGNED（05→trae），不等心跳；03 的 1.9 e2e 排程交 Integration 按错峰序处理（Ops A-1 建议仍有效）。
- **后续注意**: 05 派出后 READY 清零——A-2（下一批立项预研）紧迫性升级，Task 应随即推进；02a 待线。

## 附带状态（未下单项，备忘）

- B-2（codex 上线）未下令：第三线仍离线，02a 的并行收益需等释放线；若用户随后下令启用，02a 可提前入实施。
- C-3（Token 预算）：当前两线+02 解耦后关键路径压缩，消耗仍随并行度上升，用户已通过下令提速视为知情。

## 边界声明

Ops 仅登记呈递用户指令与建议切分口径；派单执行权在 Flow、依赖整形权在 Task、边界裁定权在 Decision、租约权在 Integration。未写共享状态、未代派单、未代拆票。
