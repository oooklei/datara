# FE-MERGE-B2

- D 盘未提交 WIP 已按文件级并集纳入：七段项目导航 icon 元数据、AppShell 图标/标签 DOM 契约。
- 权威设计 §4.2/§4.3 的 27 个正式菜单入口由既有 `menu.ts` 保持；定向契约逐组核对并通过。
- B 组继续 `direct: true`；future 组继续 `foldable/defaultFolded: true`，未改既有菜单机制。
- `routes.ts` 与 D 盘逐字节一致，未制造无必要路由差异。
- 全量测试通过；全量输出仍含既有 localhost:3000 ECONNREFUSED、Vue Router 空路径及 table/tr 警告，但退出码为 0。
- 复审补漏：全局菜单 27 个正式入口均补入 D 盘 icon 元数据，并以独立 `span.ico` / `span.lbl` 渲染；复审全量为 94 files / 788 tests passed。
