# DBX IDE 403 修复部署回执

## 部署

- 1.9 `datara-rebuild-api` 已更新 `rebuild/dbx/ide_proxy.py`、`rebuild/api/app.py` 并重启。
- 容器状态：`Up`，Uvicorn 正常监听 8001。

## 回验

- 未携带 IDE 会话访问 `connection/list`：HTTP 401，`IDE session required`。
- 未携带 IDE 会话访问 `connection/liveness-events`：HTTP 401，`IDE session required`。
- 日志无启动异常。

## 待用户联调

- admin 登录进入数据开发 IDE：既有连接可见、创建连接成功、liveness 不再 403。
- 普通项目成员：页面可进入，仅显示有权限连接；无管理权限时保存操作给出权限提示。
