# 前端 B6 交接卡（2026-10-31）

## 已落地

- 当前源码已包含账号切换修复 `21e70ba5`/`1835fe4` 与登录撤销修复 `aec73ba8`。
- `datara-newweb/src/views/__tests__/authAccountSwitch.contract.test.ts`：2/2 通过。
- `datara-newweb`：`npm run build` 通过，生成 `dist/assets/index-BT3c04ua.js`。
- 1.9 已部署 `datara-newweb:ds-20261031`，容器 `datara-newweb-web`，`http://192.168.1.9:18091/` 返回 200。
- 修正并同步主站 Nginx 的 `/ide/api/*` owner 网关路由；此前该路由直通 DBX，匿名请求返回 200。

## 未完事项

- 已在 1.9 执行现有 dev → admin Playwright 回测：退出码 0；`idePageStatus=200`、`ideI18nStatus=200`、匿名 IDE API `401`、dev 监控入口 `0`、直达监控被拒、admin 项目数 `1`、监控入口 `1`、监控可进入、token 未持久化、页面异常 `0`。
- 前端定向契约回归：4 个文件、31/31 通过（账号切换、首页项目、项目守卫、鉴权 API）。
- 仍未取得 zhangsan 私有凭据场景：未授权空态 → 授权/共享 → 撤销即时失效 → 切回 admin 全量恢复。
- 按权威 §10.7 完成十五项前端/权限验收并回填证据。

## 下次第一步

在测试域复用现有 Playwright/WSL 验收入口，先核验 1.9 新容器实际加载 `index-BT3c04ua.js`，再执行账号切换 E2E；不得重新切换回 dbx 域。

## 关联节

- 收口计划 §三 B5-B6。
- 权威设计 §五身份与项目管理、§10.7验收矩阵。
