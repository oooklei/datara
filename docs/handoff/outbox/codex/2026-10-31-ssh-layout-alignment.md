# SSH 试运行节点页面布局交接（2026-10-31）

- 任务包：当前前端票；权威 §八、§10.10 R1–R4；用户实测“SSH 节点页面与 Worker 分组等页面布局不一样”。
- 已提交 `fbf88d7`：`datara-newweb/src/views/SshNodeManagementView.vue` 及 SSH/资源页契约测试。
- 改动：页面统一 `.pg/.pg-head/.toolbar/.panel/.tbl/.err-box` 骨架、刷新/重试、加载骨架和空态；保留探测、凭据脱敏、Python/Shell 试运行开关；导航名称统一为“SSH 试运行节点”。
- 验证：SSH 与编排资源页定向测试 16 passed；`npx vue-tsc -b --noEmit` 通过；`git diff --check` 通过。
- 遗留：1.9 浏览器视觉复测；环境组海豚 patch 尚未纳入本票提交，需单独完成官方源码 patch 应用与构建验证。
- 下次第一步：在 1.9 隔离目录打开 `/dep/ssh`，核对与 Worker 分组页的标题、工具栏、表格宽度、加载失败重试和弹窗定位。
