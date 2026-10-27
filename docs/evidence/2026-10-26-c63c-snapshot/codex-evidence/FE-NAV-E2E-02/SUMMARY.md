# FE-NAV-E2E-02

- 环境：`http://192.168.1.9:18091`，证据生成于 1.9 `/lei/datara/evidence/FE-NAV-E2E-02`。
- 覆盖：27 条全局菜单路由、7 个项目功能段、项目/数据源弹窗、工作流四视角、变量抽屉、画布、资源空态、IDE 编辑器与 lint。
- 认证：匿名访问跳 `/login`；high-priority-e2e token 仅内存注入；localStorage/sessionStorage 均为空。
- 注销：`POST /rebuild/logout` 200；撤销后受保护请求 401；干净上下文回 `/login`。
- 稳定项目综合跑：0 HTTP 错误、0 console error、0 page error、0 路由落点异常。
- 缺陷 1：375px 工作流页面横向溢出，`scrollWidth=657`、`clientWidth=375`。
- 缺陷 2：项目 27 的运行监控请求 `/api/v1/rebuild/metrics/workflow-result-stats` 返回 500。
- 缺陷 3：正式壳无可见退出/注销控件；仅底层 logout API 可用。
- 未执行保存、删除、SQL 执行、上传等数据变更操作。
