# DBX 4224 访问检查

- 检查时间：2026-10-31。
- `http://192.168.1.9:4224/` 返回 HTTP 404；原因是 DBX 服务配置了 context path `/ide`，根路径没有页面路由。
- `http://192.168.1.9:4224/ide/` 返回 HTTP 200，页面 HTML 正常。
- 监听确认：容器 `dbx` 映射 `0.0.0.0:4224->4224/tcp`，容器状态 running。
- 后台日志不是文件日志，使用 `docker logs --tail 80 dbx`；已看到 `DBX Web server starting on http://0.0.0.0:4224` 与 `Serving DBX Web under context path /ide`。
- 结论：服务未宕机；用户访问根 URL 会误判不可用，应使用 `/ide/`（平台 8090 入口已代理该路径）。
