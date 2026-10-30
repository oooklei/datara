# Track A runtime wiring verdict — 2026-10-18

## 判定

**代码接线缺口（FAIL，移交 Claude 修复）；不是已具备生产接线但缺少截图的证据缺口。** 本次仅只读定位和证据整理，没有改动业务代码、运行部署或触碰远端。

## 证据定位

- `datara-backend/rebuild/api/app.py:81-94`：`create_app` 接收可选 `ai_bridge_ports`。
- `datara-backend/rebuild/api/app.py:169-177`：生产 `execution_port` 与 `audit_writer` 已构造并写入 `app.state`。
- `datara-backend/rebuild/api/app.py:751-753`：AI router 仅在 `ai_bridge_ports is not None` 时挂载；这里没有从 `app.state` 组装 bridge ports。
- `datara-backend/rebuild/ai_bridge.py:208-234`：`AiBridgePorts` 要求由外部提供 handler 映射和 audit writer；`build_ai_router` 在 audit writer 缺失时拒绝构造。
- `datara-backend/tests/sql_ide/test_repair_integration.py:240-275`：挂载测试显式注入空 handler 映射和 `MagicMock` audit writer，预期 `/api/v1/rebuild/ai/tools` 为 401；默认 app 的反向测试预期 404。它没有证明生产 handler 消费 `app.state`。

已有本地输出：

- `docs/increments/evidence/2026-10-18-TrackA-Codex-revalidate-pytest.txt`：88 项测试通过（4.80s）。其中 `TestRunSqlRuntime::test_bridge_mounted_with_explicit_ports` 和 `test_bridge_not_mounted_without_explicit_ports` 只覆盖上述装配分支。
- `docs/increments/evidence/2026-10-18-TrackA-Codex-revalidate-lifespan-di.txt`：lifespan 进入；审计表存在；`execution_port=ProductionSqlExecutionPort`、`audit_writer=DbBackedAuditWriter`；`default_app_ai_bridge_routes=[]`；文件自身明确注明未断言 route handler 消费。

因此，88 项测试通过和 lifespan DI 探针不能作为 AI bridge/handler → `app.state` 生产消费证据。当前默认 app 缺少该路由，显式注入测试则使用假 writer。工作区确有 `docs/increments/evidence/R8/tracka-repair-evidence.json` 与同名 PNG：JSON 记录的是 88 项测试及 Gap3/Gap4 修复范围，PNG 是测试数量条形图；它们不是 app.state handler 消费或远端最终运行的 A3 证据，也没有本轮对应的配对摘要/远端归档。`docs/increments/evidence/R2/` 下虽有 remote-final 文件，但属于 2026-10-15 的 R2 记录，不能证明本次 Track A runtime 接线。故 A3/runtime 证据仍未闭环，不能据此宣告 GREEN。

## 移交 Claude 的修复点

1. **文件 / 函数：** `datara-backend/rebuild/api/app.py`，`create_app` 生产装配段（当前 `app.state.execution_port`、`app.state.audit_writer` 创建处及其后的 bridge 挂载分支）。
   **期望：** 生产 app 装配时，明确把已创建的生产依赖传给 AI bridge handler；不要要求部署入口额外注入一套与 `app.state` 分离的端口。保留当前缺少必要依赖时 fail-closed 的行为。
2. **文件 / 函数：** `datara-backend/rebuild/ai_bridge.py` 的 run_sql handler/ports 适配点（如需新增，遵循既有 handler 与工具契约）。
   **期望：** 实际 run_sql 请求使用 `app.state.execution_port` 执行，并通过 `app.state.audit_writer` 写审计；审计失败继续拒绝成功响应，不绕过审计。不得只在 `app.state` 上存放对象而不由 handler 消费。
3. **文件：** `datara-backend/tests/sql_ide/test_repair_integration.py`。
   **期望：** 增加不传 `ai_bridge_ports` 的生产装配集成断言：默认 app 的 bridge 路由按已批准的生产契约挂载；请求 handler 实际调用 app.state 中的生产端口和审计 writer。另保留缺依赖时拒绝构造/调用的 fail-closed 断言。显式 `MagicMock` ports 测试只能作为单元装配覆盖，不能替代该生产路径证据。
4. **验收证据：** 修复后重新执行针对性测试并记录命令与输出定位；Track A 要求的 A3 JSON/PNG 必须成对，另附 remote-final 归档。全部证据通过独立复验后再更新 Track A 判定。

## 本次执行边界

只读取应用装配、bridge 和已有测试/输出；没有运行部署或远端命令，没有修改业务代码，没有调用 AOCI，没有 push。交付为本文件单文件。
