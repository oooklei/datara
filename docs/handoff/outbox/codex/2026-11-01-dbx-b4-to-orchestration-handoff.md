# B4 DBX → 编排网关交接卡

## 已落地文件/证据

- DBX 代码当前已在 `621aab97`；本票新增证据卡提交 `51daa1d4`。
- 1.9 直连 DBX 无授权 401；Datara owner 网关 admin 200；dev 显式 share/撤销 share 可见性正确。
- `tests/rebuild/test_dbx_gateway_api.py test_dbx_ide_proxy.py test_dbx_ide_policy.py test_dbx_connection_access.py`：36 passed。
- 共享回验后 `datara-mysql-src` 的 owner 记录保留为 admin，dev 的 share 已删除；如需恢复“未 claim”初始状态，需由管理员在资源管理页执行明确的 owner 变更。

## 未完事项

- 编排任务 `tt` 保存失败的 Network 请求体/响应 code 尚未完成采集与修复。

## 下次第一步

在 1.9 `18091` 以 admin 打开任务编排，进入 `tt`，捕获 iframe 保存请求 URL、请求体字段摘要、HTTP 状态及 `code/msg`；随后仅切换编排域文件实现修复。

## 涉及节号

收口计划 §三 B4、B5；权威设计 §六、§10.4、§10.8。
