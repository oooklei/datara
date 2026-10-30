# dbx 域 B4 交接卡（2026-10-30）

- 任务包：待办 `docs/plans/2026-10-30-consolidation-and-simulation-todo.md` §三 B.4；权威 `docs/designs/2026-10-29-dbx-unified-target-design.md` §四、§10.9。目标文件：`deploy/dbx/internal-token-patch/{auth.rs,internal_auth.rs,README.md}`、`datara-backend/rebuild/dbx/{api.py,client.py,ide_proxy.py}`；验收为 1.9 直接 DBX 匿名/无授权请求 401 且不泄露连接，datara owner 网关只返回可见连接。
- 已落地文件：本卡；本票未修改代码。现有 v0.6.60 `auth.rs` 已实现 `DBX_DATARA_GATEWAY_ONLY=1` 的数据 API 拦截与内部令牌通道；datara `client.py` 已在服务端发内部令牌，`api.py` 已按 owner 过滤连接列表。
- 当前运行边界：1.9 的 `dbx` 容器存在 `DBX_DISABLE_PASSWORD` 且其值使 `password_disabled=true`；容器环境中未见 `DBX_DATARA_GATEWAY_ONLY` 或 `DBX_INTERNAL_TOKEN`。该运行状态会跳过 DBX 自身认证，直连可绕过 datara owner 网关。1.9 `/lei/apps/dbx` 源码为 v0.6.29，当前运行镜像为 v0.6.60；不得用旧源码覆盖运行镜像。
- 验证命令与结果：只读查看远端容器环境变量**名称**和 `DBX_DISABLE_PASSWORD` 布尔状态，结果为 `password_disabled_true`；按用户最新顺序，未部署、未执行运行测试，故 B4 未验收。
- 未完事项：在全部代码修正完成后，以 v0.6.60 源码和仓库补丁构建新镜像；服务端配置足长内部令牌、`DBX_DATARA_GATEWAY_ONLY=1`，并让 datara 后端使用同一令牌；验证匿名/无授权直连 401、owner 代理可见性及 iframe 可用性。不得将令牌写入静态产物或仓库。
- 下次第一步：继续下一个单一代码域的待办修正；部署阶段先核对 v0.6.60 构建来源与补丁应用，再更新 1.9 隔离环境。涉及节号：权威 §四、§10.9；待办 §三 B.4。
