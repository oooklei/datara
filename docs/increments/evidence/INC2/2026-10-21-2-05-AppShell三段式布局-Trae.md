# 票 2-05 AppShell 三段式布局组件 交付证据（Trae 线）

> **单号锚**：s230-inc2-ratify → 完成报备 tr-done-205 | **日期**：2026-10-21 | **交付线**：Trae

## ① 交付物

| 文件 | 内容 |
|---|---|
| `datara-newweb/src/layouts/AppShell.vue` | 三段式布局组件（grid header/aside/main 语义保持增量 1 最小壳）+ 菜单消费（filterMenuGroups 唯一入口）+ future 组折叠渲染接驳（groupFold）+ AI 全局挂载点（`#ai-assistant-global-mount`，与 RouterView 同级）；`filterOverrides` props 供测试/后续增量注入 |
| `datara-newweb/src/App.vue` | 认证壳切换改造：`shellActive = path!=='/login' && getToken()`——登录页不挂载 AppShell（0.8 §6 规则 1），AI 挂载点随 AppShell 保证单实例 |
| `datara-newweb/src/layouts/__tests__/appShell.contract.test.ts` | 组件测试 8 用例（独立 memory router + stub 视图，不改产品 routes.ts） |

## ② 验收锚核对（0.8 §7 测试集 6/7）

| 锚 | 结果 |
|---|---|
| AI 入口跨业务路由单实例 | PASS（/a→/b 切换挂载点恒 1 个，AppShell 不重建） |
| 登录页不渲染 | PASS（App 级：/login 无 AppShell 无挂载点；认证后业务路由挂载） |
| 切换路由后上下文更新 | PASS（aiContext=route.fullPath 随 /b→/a 更新，0.8 §6 规则 3） |
| 菜单显隐不替代鉴权 | PASS（产品真实守卫：无 token 访问 / → /login；R-15 初始态侧栏零渲染+守卫仍拒——联合断言） |
| 菜单消费正向 | PASS（批次开+路由注册→B 组一级直达可见、direct 组标题不渲染、link href=/dag） |
| future 折叠渲染 | PASS（默认折叠 aria-expanded=false→点击展开→localStorage 稳定键持久化→路由零变化；空时整组不渲染） |

## ③ 实跑记录

- `npx vitest run src/layouts`：**8/8 passed**（首轮 2 失败已修：RouterLink 渲染后断言 href 而非 to prop；previewAllowed 传 Set 非 Array）
- 全量回归 `npx vitest run`：**20 files / 251 passed / 0 failed**——既有 243 零破坏
- `npx vue-tsc -b`：**EXIT=0**（App.vue/AppShell.vue 类型检查通过）

## ④ 边界声明

- 产品 routes.ts 零改动（组件测试用独立 memory router）；路由守卫逻辑（router/index.ts）零改动
- AI 助手本体（Launcher 组件/API 接线）归增量 15，本票仅挂载点结构（0.8 §6 规则 5 未接线不伪装）
- RBAC 权限面归增量 15（ctx.permissions 空集注入，未配置 permission 的项视为通过）

## 修订记录

| 版本 | 修订 |
|---|---|
| v1 | 首版交付：AppShell.vue + App.vue 改造 + 8 测试全绿（251 全量+vue-tsc 零错） |
