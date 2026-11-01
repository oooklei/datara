# B4 DBX 数据访问网关交接卡

> 2026-11-01 权威刷新注记：编排网关（后端代理海豚）已取消，画布改为 iframe 同源直连；本卡仅保留 DBX owner 网关阶段的成果与未完事项。现时权威见 `docs/designs/2026-11-01-datara-current-authority.md`。

## 已落地文件/证据

- DBX 代码当前已在 `621aab97`；本票新增证据卡提交 `51daa1d4`。
- 1.9 直连 DBX 无授权 401；Datara owner 网关 admin 200；dev 显式 share/撤销 share 可见性正确。
- `tests/rebuild/test_dbx_gateway_api.py test_dbx_ide_proxy.py test_dbx_ide_policy.py test_dbx_connection_access.py`：36 passed。
- 共享回验后 `datara-mysql-src` 的 owner 记录保留为 admin，dev 的 share 已删除；如需恢复“未 claim”初始状态，需由管理员在资源管理页执行明确的 owner 变更。

## 未完事项

- 编排任务 `tt` 保存失败的 Network 请求体/响应 code 尚未完成采集与修复。

## 下次第一步

在 1.9 `http://192.168.1.9:8090/`（唯一前端入口）以 admin 打开任务中心 `/dag`，进入 `tt`，捕获 iframe（`/dolphinscheduler/` 同源直连）保存请求 URL、请求体字段摘要、HTTP 状态及 `code/msg`；随后仅切换编排域文件实现修复。

## 涉及节号

现时权威 §三（三条唯一正确路径）、§四（集成机制）、§六（后端 API 域）；原「收口计划」与 2026-10-29 权威设计已归档至 `docs/archive/2026-11-01-authority-refresh/`。
