# R1：身份、项目、数据源和最小权限——开始前影响分析

> 状态：PASS
>
> 上一增量：R0（PASS）
>
> 权威项目根目录：`D:\需求\数据治理工具\Datara`

## 1. R0 → R1 影响分析

### 已确认的 R0 基线

- 远程运行环境固定为 `192.168.1.9`；Web 重建验证入口固定为 `http://192.168.1.9:18091/`。
- `mysql-meta` 已提供隔离 schema `datara_rebuild_i0` 及专用用户；`mysql-src/ec_retail` 和 `mysql-dw/datara_dw` 可访问。
- Redis、Kafka、Zookeeper、API、Master、Worker、Alert、Logger 和 Web 均已具备运行基线。
- I18-I23 资产只做迁移/承接，不删除；R1 不写入旧业务表。
- 正式前端和旧 Backend 保持冻结；R1 只创建新 Backend `rebuild/` 与独立验证页。

### 对 R1 的直接影响

| R0 改变 | R1 影响 | 处理方式 |
|---|---|---|
| 新增隔离 schema/用户 | R1 迁移和运行表必须使用隔离连接 | 新 Backend 配置默认指向 `datara_rebuild_i0`；远程注入凭据，不写普通日志 |
| Web 改为 18091 | browser-use 验证页必须走 18091 | 独立路由组，不注册正式菜单；证据统一记录 18091 |
| I18-I23 保留 | R1 不可复用旧业务写接口 | 仅复用已验证的读模型/迁移资料，不导入旧 API 模块 |
| 运行资源已验证 | R1 可以进入登录、项目和数据源闭环 | 仍需由页面牵引 API→MySQL/Redis→日志完成验证 |

## 2. R1 细化步骤

- [x] Step 1：先写身份会话、项目成员、数据源能力矩阵的契约测试，已确认 RED。
- [x] Step 2：创建 `datara-backend/rebuild/` 的公共配置、响应、数据库和迁移边界；新代码未 import 旧 `api`/`common`。
- [x] Step 3：实现 token 会话、开发者角色最小 RBAC、项目创建/列表和权限拒绝基础语义。
- [x] Step 4：实现数据源草稿校验、能力矩阵端点和隔离数据库配置注入；真实连通性探查仍需补齐。
- [x] Step 5：建立独立验证页，仅挂载 `/rebuild-validation/i1` 路由，不注册正式菜单、不改旧业务页面。
- [x] Step 6：本机执行 py_compile、ruff、契约测试和旧 API 隐式依赖扫描；12 项 Backend 测试、前端路由测试和前端构建通过。
- [x] Step 7：将新 Backend/Web 构建部署到 `192.168.1.9`，使用 18091 通过 browser-use 完成登录、项目权限、数据源连接和拒绝场景的逐项交互证据。
- [x] Step 8：采集 MySQL/Redis/Worker/API 日志、页面结果和时间戳，回写 R1 证据；R1 通过后才进入 R2 影响分析。

## 3. R1 不改变的边界

- 不改正式前端菜单、正式路由和旧 mock 分支。
- 不删除或迁移 I18-I23 数据。
- 不把旧 `datara-backend/api`、`common` 作为新 Backend 运行时依赖。
- 不使用 8090；验证入口只允许 18091。
- 若发现数据库模型、鉴权契约或数据源边界与总体设计冲突，暂停并按第 1 条法条刷新设计、计划和台账。

## 4. R1 验收证据

- `docs/increments/evidence/R1/`：部署、浏览器、API、数据库、Redis、日志和失败权限场景。
- 本机证据：契约测试 RED/GREEN、py_compile、ruff、旧 API import 扫描。
- 远程证据：18091 页面操作、请求链路、MySQL 记录、Redis token、API/Worker 日志和页面最终结果。

## 5. 当前状态

- R1：PARTIAL。
- 已完成：新 Backend 独立包、身份/项目/数据源基础契约、独立验证页、远端 `datara-rebuild-api` 健康、18091 反代和登录接口。
- 未完成：browser-use 控件级交互证据、真实数据源连通性测试、Redis 会话撤销、成员管理和权限拒绝闭环。

## 6. 追加运行验证（2026-10-14）

- 后端新增显式 R1 增量迁移：对已存在的 `rebuild_user` 表补齐 `created_at/updated_at`，不触碰旧业务表。
- 远端 `datara-rebuild-api` 已重新构建并健康运行；`http://192.168.1.9:18091/api/v1/rebuild/health` 返回 HTTP 200。
- 远端登录返回 token；使用 `datara-mysql-src/ec_retail` 完成真实 MySQL 探查，返回连接成功、数据库名、MySQL 版本和能力矩阵。
- 登出后原 token 调用项目接口返回 HTTP 401；成员权限接口对无 `manage_user` 权限角色返回 HTTP 403。
- Redis 容器健康，API 日志记录 health/login/datasource/logout/401 全链路；证据见 `docs/increments/evidence/R1/remote-deploy.txt`。
- R1 仍保持 `PARTIAL`：18091 浏览器控制树交互尚未形成可复核证据，必须补齐后才能 PASS。

## 7. 追加验证页闭环（2026-10-14）

- 验证页补齐登出撤销、开发者成员权限拒绝和请求生成时间戳展示；页面仍保持独立路由，不进入正式菜单。
- 本地前端路由测试和生产构建通过；远端 Web 已按实际 bind mount `/lei/datara/datara-web/dist` 更新并重启，18091 返回 HTTP 200。
- browser-use 控件树绑定已恢复并完成控件级闭环；本条此前的超时记录保留为历史过程，不再作为当前门禁结论。
- 已新增并部署纯 HTML 入口 `/rebuild-validation-i1.html` 排除 SPA/hash 路由因素；该页面已完成浏览器交互验收。

## 8. browser-use 控件级闭环（2026-10-14）
- `http://192.168.1.9:18091/rebuild-validation-i1.html` 已由 browser-use 读取并完成真实交互。
- 登录成功：页面显示“Token：已获得（dev）”，时间戳 `2026-10-13T21:20:53.733Z`。
- 项目创建并刷新成功：页面显示项目数 `2`，时间戳 `2026-10-13T21:22:01.416Z`。
- 真实数据源探查成功：页面显示 `cross_schema、metadata、query`，时间戳 `2026-10-13T21:23:08.290Z`。
- 权限拒绝成功：页面显示“权限拒绝验证成功（HTTP 403）”，时间戳 `2026-10-13T21:24:15.373Z`。
- 登出撤销成功：页面显示“登出成功，旧 Token 已撤销”，时间戳 `2026-10-13T21:25:22.771Z`。
- R1 结论：后端、MySQL、Redis、Web、页面控件和后台日志证据已闭合，R1 PASS；R2 可按前置影响分析启动。

