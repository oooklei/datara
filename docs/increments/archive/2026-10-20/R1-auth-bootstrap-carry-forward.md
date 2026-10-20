# R1 身份验证遗留项影响分析与补齐步骤

> 状态：PARTIAL（最终 Playwright 控件验证 PASS；环境契约/代码分批提交与完整 Backend 冻结门禁仍未关闭）  
> 关联增量：R1（旧 I1，原功能验收 PASS）；当前阻断条件：Backend 冻结前必须补齐  
> 日期：2026-10-14（Asia/Shanghai）

## 已批准变更事实

用户已裁定：新验证前端无人工登录页；验证运行环境使用统一 Backend 验证 key 获取 token，前后端完全分离。新测试页按对应参考产品真实前端逻辑制作。R1 原人工登录控件证据保留为历史证据，但不能作为新验证认证契约的证明。

## 影响面与边界

- 现有新 Backend 登录 API、`TokenService`、I1 验证页和测试使用硬编码演示用户；Compose 含 DB URL/token secret fallback，均不满足新 key-bootstrap 边界。
- 正常用户/密码认证 API 不移除，但不得被验证页作为登录 UX 使用。
- 新增仅在显式开启时有效的验证令牌交换 API；secret 缺失或功能未开启时 fail-closed；key 从 `REBUILD_VALIDATION_KEY` 运行时注入，不提供代码默认值。
- 用短时 token 及固定最小验证身份；验证身份不能授予系统管理员权限。现阶段最小权限角色为 `dev`，并保留 RBAC 拒绝测试；后续要修改 role 必须更新此契约。
- Key 只存在于批准的部署 secret/环境和测试运行器进程；页面静态资源、HTML/JS、URL、localStorage/sessionStorage、日志、截图及证据里不得出现 key。验证器使用服务端运行器换 token，再通过 Playwright/browser-use 初始化页面运行上下文。
- 移除启动时创建默认 `dev` 账号；普通登录测试必须通过显式 fixture 建立临时用户。所有 DB URL/token 签名密钥取消静态 fallback，测试通过 fixture 注入。

## 步骤与验收

1. 先写 auth-bootstrap 契约与测试：功能关闭、缺 key、错 key 均拒绝；正确 key 返回短 TTL token；token 能调用允许 API、不能执行系统管理权限操作；正常 password login 仍可独立验证。
2. Backend 移除默认 demo seed、硬编码凭据 fallback；Compose 只引用环境变量，不打印值；测试 fixture 显式提供 SQLite URL、token secret、验证 key 和测试用户。
3. 在 `rebuild-validation-i1.html` 及后续验证页移除登录表单；页面从测试上下文取得短时 bearer token，不自行携带 key。
4. 本机 pytest/ruff/compileall；远端只在 192.168.1.9 更新隔离 rebuild API 配置并检查健康、key 错误/正确 exchange、token 过期/RBAC/后台日志；页面用 browser-use，控件桥接失败按技能转 Playwright。
5. 检索构建产物、源码、URL、浏览器 storage 和日志，断言没有验证 key；保存不含 token/key 的测试报告。

R1 原有项目/数据源功能保持历史 PASS；本补充项以最新控制级证据判断 auth-bootstrap 是否闭环，不据此宣告整个 R1-R11 Backend 冻结。

### 2026-10-14 R1 验证页控件级闭环

- 本轮浏览器：browser-use 对现有 `http://192.168.1.9:18091/rebuild-validation-i1.html` 的标签页绑定连续两次在 30 秒超时；记录为 `browser-use=BLOCKED`，未将此桥接故障冒充为产品成功或失败。
- 按 `browser-use-playwright-fallback` 技能在同一部署页面运行 Playwright 控件流程，Chrome 149.0.7827.115；初轮 `r1-20261014142424` 8/8 通过，强化可见结果后发现异步列表刷新竞态并保留两次真实 FAIL 报告，修正等待条件后最终 `r1-20261014143228` 9/9 通过：HTTP 200、无人工登录控件、runner token 启用业务控件、页面创建并刷新项目、成员写入被 403 拒绝、mysql-src 探查 HTTP 200、页面注销提示可见、控件禁用、撤销 token 后请求 HTTP 401。
- 最终真实项目记录 ID=14、owner_id=0；MySQL 只读查询确认 `created_at=updated_at=2026-10-14 22:32:27`（Asia/Shanghai）。API 日志逐项对应 token 200、项目 POST/GET 200、成员 403、探查 200、注销 200、撤销后 401；容器 `running healthy`，health code=0。页面错误和失败网络请求均为 0。
- 证据：`docs/increments/evidence/R1/r1-20261014143228.json`、`r1-20261014143228.png`、`r1-20261014143228-remote.txt`；失败尝试 `r1-20261014143004`、`r1-20261014143128` 的 JSON/截图也保留。Playwright 报告不包含 key/token；key 仅由受控 runner 进程从远端环境读取并换取短期 token。
- 结论：本次 R1 auth-bootstrap 控件级补充验证 PASS；browser-use 通道仍 BLOCKED；R1 原有功能状态保持既有证据结论，整体 R0-R11 冻结门禁仍未达成。
