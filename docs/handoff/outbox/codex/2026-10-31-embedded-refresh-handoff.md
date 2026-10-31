# 嵌入页面刷新控件交接卡（2026-10-31）

## 已落地

- `datara-newweb/src/views/ide/DbxIdeView.vue` 顶部保留会话安全重载，并标注 `data-ide-refresh`，按钮文案统一为“刷新数据开发页面”。
- `datara-newweb/src/views/TaskCenterView.vue` 在编排画布顶部新增 `data-tc-embed-refresh`“刷新画布”；刷新仅重载 iframe，会保留项目、工作流与当前路由。
- `datara-newweb/src/views/__tests__/taskCenterView.contract.test.ts` 增加刷新控件与上下文保持契约。
- 前端构建产物已部署到 1.9 `datara-newweb-web`，入口仍为 `http://192.168.1.9:8090/`。

## 验证

- `npx vitest run src/views/ide/__tests__/dbxIdeSession.contract.test.ts src/views/__tests__/taskCenterView.contract.test.ts`：2 files / 37 tests passed。
- `npm run build`：`vue-tsc -b` 与 Vite 构建通过。
- 1.9 nginx reload 成功。

## 待用户联调

- 请在 8090 的数据开发 IDE、任务编排画布顶部分别点击刷新，确认嵌入页面延迟加载时可手动重载且仍停留在当前项目/工作流。
