# DBX IDE 403 / 白屏收口

## 改动

- `datara-backend/rebuild/dbx/ide_proxy.py`：IDE 会话启动改按项目读取权限校验；连接列表仍按用户可见连接过滤，未授权连接不返回。
- `datara-backend/rebuild/api/app.py`：管理员角色判定兼容大小写，避免 admin 因历史 token 角色大小写导致 403。

## 验证

- `python -m pytest datara-backend/tests/rebuild/test_dbx_ide_proxy.py -q`
- 结果：21 passed（仅既有 FastAPI duplicate operation id 警告）。
- 1.9 DBX 内部令牌回验：`connection/list` 返回 200；`liveness-events` 返回 200 SSE。

## 遗留

- 需将本次后端镜像部署到 1.9，并用 admin 及普通项目成员各回测一次 `/ide/`、连接列表和新建连接。
