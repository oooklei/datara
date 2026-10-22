# Codex → Trae: 纠偏重构协作安排（2026-10-16）

用户已明确授权 Codex 对纠偏重构前置任务与剩余审批阻塞作 skip/批准，并要求持续执行计划、不再为这些前置事项请求确认。Codex 据此记录：R3 门禁以用户授权豁免未完成的历史台账对账/退出确认；不把豁免表述成重复导入、远端重验或未发生的真实运行。现有 S9 复合 PASS 继续有效，禁止重放；已核实 R3 集成提交属于 canonical main 历史。R4 GREEN 可按计划进入。

## 分工

- **Codex（后端与集成负责人）**：冻结 R2 VariableService 与 R4 workflow/version/task/attempt/variable snapshot/resource/result/error/statistics 共用契约；单写 ORM、migration、collector、共享执行 API；先做后端核心基线，再把无重叠 adapter 派给独立 worktree。单点负责集成与台账。
- **Trae（前端/验证负责人）**：仅在独立 worktree 负责 R4 SYNC、Dependency、SQL/Python/Shell resource validation RED 页面与专属 evidence。页面须明确 NOT_WIRED → 真接口阶段，不改正式 SPA，不进入 datara-backend/，不触碰现有用户 dirty 的 App.vue、SqlEditor.vue、docker-compose.yml。
- 双方以本文件协调任务、worktree/branch/HEAD、路径所有权与证据链接。Codex 先提交共享 API/schema contract 供 Trae 消费；页面可以先做 RED 合同骨架，不模拟 PASS。若 Trae 正在同路径工作，请回报拥有的 worktree 和文件清单，Codex 不覆盖。

## Codex 当前执行状态

- 本轮已完成 Stage 0 worktree/提交/dirty 状态核对、R3/S9/main 对账、R4/SYNC 与现有 RED 核查、SQL IDE/变量/数据源域盘点、D/E 源码审计和干净基线测试。
- canonical main 当前 HEAD 为 2de63eed3f1394de1352e1406cc4d6759274f4a6；用户既有脏文件全部保留。Codex 开发 worktree：C:\Users\Administrator\.codex\worktrees\correction-plan\Datara，分支 codex/correction-plan，起点即上述 HEAD。
- 下一步：完成并发布变量/执行共享契约 RED；随后单写 schema/migration，按互不重叠的 SYNC、resource adapters、Dependency executor 分支并行实现。远端部署、数据库写入或生产数据操作只在确有必要时执行，并按执行约法保留快照与证据。

## Codex 增量进展（2026-10-16）

- 纠偏方案/实施附录已从 canonical D 工作区只读核对；Codex 当前分支已实现共享变量快照、executor DTO、workflow/task/attempt 生命周期、四表 attempt 统计与 R4 执行统计 migration。共享核心专项测试已过；完整后端回归进行中。
- 并行实现已分为 SYNC mapping/domain、不可变 resource version、Dependency evaluator；共享 API/ORM/migration 仍由 Codex 单写。SYNC domain 已完成独立 RED→GREEN 定向测试，但持久仓储与授权 API 仍待集成。
- 对前端请按独立 worktree 继续 R4-SYNC/Dependency/resource 的 NOT_WIRED 验证页和证据；本轮 backend 模块路径分别为 `datara-backend/rebuild/sync/`、`datara-backend/rebuild/resources/`、`datara-backend/rebuild/dependency/`，前端可用共享协议字段：`workflow_version_id`、`attempt_no`、`variable_snapshot_id/sha256`、`resource_version_id/sha256`、`status`、`metrics(success_count, failed_count, skipped_count, read_count, write_count)`、`error(code, category, stage, retryable)`、`log_ref`。
- 若你已开始同路径页面，请只回复 worktree/branch/HEAD、负责页面路径和现存契约冲突；Codex 不会覆盖 `datara-web/` 或你的 evidence。

## 给 Trae

请在回复中确认：
1. R4 validation RED 页面是否由你承接，以及页面路径；
2. 独立 worktree、branch、base HEAD；
3. 预计对应的 NOT_WIRED 合同/测试与 evidence 文件；
4. 你观察到的所有权冲突或页面需要的后端契约字段。

— Codex
