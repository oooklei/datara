# 顶栏预警消息中心

- 改动文件：`datara-newweb/src/layouts/AppShell.vue`、`datara-newweb/src/services/rebuild/alertApi.ts`
- 实现：右上角预警入口、未读数徽标、消息列表、刷新/重试、点击标记已读并按后端 target 跳转。
- 验证：`npm run build` 通过；提交 `0eeb3664`。
- 遗留：尚未部署到 1.9，需联调确认 `/api/v1/alerts` 在当前后端实例可访问及权限裁剪。
