# 顶栏预警消息中心部署

- 版本：`datara-newweb:alert-center-20261031`，来源提交 `0eeb3664`。
- 目标：192.168.1.9 `datara-newweb-web`，端口 `18091`。
- 操作：同步 `datara-newweb/dist`，重建镜像并重建容器。
- 验证：`curl http://127.0.0.1:18091/` 返回 HTTP 200；容器 healthy，镜像已切换。
- 注意：当前 1.9 rebuild API 对 `/api/v1/alerts` 返回 404，消息列表会显示“预警消息暂时无法加载”；需后端接入告警查询路由后恢复真实数据。
