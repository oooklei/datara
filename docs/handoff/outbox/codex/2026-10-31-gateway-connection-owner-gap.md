# 编排网关 §10.9 运行期连接 owner 缺口（2026-10-31）

- 任务包：待办 §三 B.4/C.8；实施权威 `docs/designs/2026-10-29-dbx-unified-target-design.md` §四、§10.9。目标文件：`datara-backend/rebuild/orchestration/api.py`、`datara-backend/tests/rebuild/test_orchestration_governance_api.py`、`deploy/dolphinscheduler/3.4.3/datara-integration.patch`。验收：同项目用户知道别人的未共享 `connectionId` 时，保存期和运行期均无法取参。
- 当前证据：网关 `internal_connection_params` 仅用 `DbxConnectionAccess.project_ids(project_id)`，未用 `visible_ids(project_id, user_id)`；海豚 master `fetchDbxDataSourceParameters` 请求只带内部 token 和 `project_id`，未带执行用户；`X-Datara-User` 只写审计。现有取参测试只测跨项目/未认领 ID，未测同项目不同 owner。
- 验证命令与结果：本机 `pytest -q tests/rebuild/test_orchestration_governance_api.py`，25 passed；该结果不证明 owner 运行边界。未修改上述代码文件。
- 遗留：从海豚可信任务上下文取得执行用户身份并随内部请求传递，Datara 按用户/共享关系查 `visible_ids`；补同项目不同 owner 的 403/404 测试及撤销共享即时失效测试。不得仅信任浏览器或可伪造的用户头。部署/E2E 按既定顺序留待 1.9 隔离环境。
- 下次第一步：在完整海豚 3.4.3 目标源码中定位 `TaskExecutionContextFactory` 可用的工作流执行用户字段与其 Datara 身份映射，再同时改 master 请求和网关校验；涉及节号仍为权威 §四/§10.9、待办 §三 B.4/C.8。
