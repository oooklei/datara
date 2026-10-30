# DBX owner 隔离：当前请求路径核对（2026-10-30）

范围：当前源码与 192.168.1.9 只读运行状态；未切换共享 DBX 服务或前端入口。此文是缺口证据，不是验收通过。

## 事实

1. 1.9 的 `dbx` 容器对所有网卡发布 `4224:4224`。从本机无凭据请求 `http://192.168.1.9:4224/ide/api/auth/check` 得到 HTTP 200，正文 `{"authenticated":true,"required":false,"setup_required":false}`。
2. 当前 `datara-newweb/deploy/nginx.conf` 的 `/ide/` 直接转发到 `192.168.1.9:4224/ide/`；`deploy/wsl-frontend/nginx.conf` 和 `ide-verify.nginx.conf` 同样直连 DBX。DBX iframe 的 API 请求因此不会经过 Datara owner 网关。
3. 源码已有 `/api/v1/rebuild/dbx/projects/{project_id}/connections` 的 owner/共享接口，也已有 `/api/v1/rebuild/dbx/ide-proxy/{path}` 草案；但未接入上述 iframe 请求路径。历史搜索、SQL 资产和 AI 对话已有 owner 范围及单元测试；AI 配置/流式请求、`tunnel-profiles/`、`prompt-templates` 等仍被拒绝，直接接线会损坏原版 IDE 的既有能力。
4. `deploy/dbx/internal-token-patch/README.md` 明记 DBX 内部令牌补丁尚未集成或部署。只把前端改走网关、仍开放无密码的 4224，仍可绕过 owner 过滤。
5. `D:\dbx-main\crates\dbx-web\Cargo.toml` 和 1.9 `/lei/apps/dbx/crates/dbx-web/Cargo.toml` 均标为 0.6.29，但 1.9 运行镜像 `/ide/api/version` 返回 0.6.60。不能把主机源码当作运行镜像的同版本依据。当前部署契约按官方 v0.6.60 标签源码与运行行为核对；该版本新增 `/saved-sql/{id}/default-content`，本地网关已补 owner 校验。

## 本地补缺（尚未部署）

- 历史搜索强制按可见连接 ID 查询；伪造其他连接、名称回退及混合数据库筛选已覆盖。
- SQL 文件/文件夹记录独立 owner 与显式共享；共享连接不会自动共享 SQL 文件，撤销后不可读取。删除文件夹前检查整个递归子树，防止误删其他用户对象。
- 网关的 IDE `auth/check` 由 Datara 会话响应，避免 DBX 直接入口收紧后出现第二个登录页。
- `test_dbx_gateway_api.py` 与 `test_dbx_ide_proxy.py` 定向测试共 14 项通过。这仅证明本地策略，不证明现网隔离。
- 之后补了旧 SQL 管理员编辑兼容、管理员认领、删除后重用 ID 的隔离验证，以及 0.6.60 的 SQL 默认内容保存和旧历史列表分页。当前 DBX 网关/策略三组定向测试 23 项通过。相关结果仍只适用于本地源码。
- 连接编辑核对了现网 12 条 DBX 连接实际返回字段：新增非敏感高级字段回显，隐藏字段与密码由服务端原配置合并；Datara 独立连接编辑接口空密码也保留原密钥。三组定向测试现为 24 项通过。现网仍未接线。
- 继续按 0.6.60 路由核对连接写操作：共享连接用户不能通过 DBX 的数据库信息保存、写解锁、会话凭据、断开连接或 Salesforce 授权接口修改 owner 的连接状态；MCP 增删连接入口直接拒绝，要求走 Datara owner API。三组定向测试现为 25 项通过，仍不是现网隔离证据。

## 使目标成立所需的完整闭环

先逐项核对 DBX 原版 API 的请求/响应与现有 IDE 操作，补全连接、配置、SQL 资产、历史和 AI 的 owner/共享策略；代理需支持 DBX 实际使用的 JSON、流和上传协议。随后在隔离环境接入 `/ide/api/`，验证 IDE 原有对象树、SQL、结果、历史、导出、AI 功能不回退；最后给 DBX 直接入口设置服务端认证/内网限制，并复测无授权用户、显式共享、撤销共享、管理员及切换登录。`4224` 直接访问未封闭前不能宣称 owner 隔离完成。

数据库密码和 DBX 内部令牌不得进入前端静态产物、URL 或浏览器持久存储。

## 0.6.60 IDE 接口覆盖复核（后续只读核对）

从 0.6.60 的 `apps/desktop/src/lib/backend/http.ts` 提取静态 `/api/` 路径，去重后按前缀计数：`connection` 29、`schema` 72、`query` 90、`history` 7、`saved-sql` 4、`ai` 21、`tunnel-profiles` 3、`prompt-templates` 3、`layout` 3。此计数含查询参数变体和 SQL 生成辅助端点，也不覆盖动态构造的路径，不能解释为全部路由数。

当前 `ide_proxy.py` 对 AI、隧道配置和提示词模板整域拒绝，且 `DbxClient._request` 只按 JSON 解析响应；原版 IDE 使用的 SSE、上传等协议没有透传。`/ide/` 仍直连 4224。**在代理补齐并以原版 IDE 回归前，不能切换 Nginx 到现有代理。** 本轮没有修改 1.9 的 DBX 容器、端口或前端代理。

后续对代理默认转发规则加了支持路径白名单：伪造一个可见连接 ID 访问 `auth/change-password`、`app-settings/config/decrypt`、`backup/restore` 或未知 `connection/*` 路径均返回 403，未触发 DBX 调用；schema 非 GET 请求要求 SQL 执行权限。身份切换也会吊销同一浏览器的旧 Datara token，并清除 `/ide/api` 的旧 IDE cookie。身份与 DBX 相关回归共 51 项通过；这些仍是本地代码结果。

在 1.9 用**独立无挂载、仅监听本机 14224**的临时 DBX 容器核对了原版 0.6.60 认证：`DBX_DISABLE_PASSWORD=0` 且未设置密码时，`auth/check` 返回 `setup_required=true`，`connection/list` 和 `query/execute` 返回 401；向未打补丁的容器提交 `X-Datara-Internal-Token` 仍为 401。临时容器已停止并自动删除，未触碰现网 DBX 数据。此实测证明原版认证可封住直连，但 Datara 内部通道还必须打补丁并构建验证；当前现网无密码直连仍开放。
## 2026-10-30 补充：原版 AI 对话 owner 隔离（本机代码验证）

- 核对 DBX v0.6.60：`ai/conversations` 返回全局对话，`ai/conversation` 保存也是全局写入；原版 AI 配置列表包含 `apiKey`，不能直接转发给项目用户。
- Datara IDE 网关已对 AI 对话实施项目、连接及对象 owner/共享过滤；新对话登记 owner，修改和删除只准 owner 或 admin；旧对话需 admin 认领后才可共享。未认领旧对话对普通用户不可见。
- 本机 `test_dbx_ide_proxy.py` + `test_dbx_gateway_api.py`：23 passed；加身份和 DBX 策略回归共 54 passed。AI 配置和流式对话仍未接通，不能据此判定原版 AI 能力已完成；1.9 未部署此改动。

## 2026-10-30 补充：IDE 数据 API 路由白名单

- 对照 DBX v0.6.60 `crates/dbx-web/src/main.rs`，将 `schema/`、`query/`、`mq/`、`history/`、`saved-sql/` 的前缀放行收紧为 232 条已声明路由及必要的对象 ID 路由，防止伪造一个可见 `connectionId` 后调用新增或未知的管理端点。
- 本机 IDE 网关及 owner API 回归 24 passed，`git diff --check` 通过。此为本地网关改动，未部署到 1.9。

## 2026-10-30 补充：同版本补丁编译与本机入口故障

- 原内部令牌补丁基于主机旧版 0.6.29；已归档旧基线和旧补丁，并将新增逻辑重新移植到官方 v0.6.60 `auth.rs`。相对官方文件仅 62 行新增、1 行测试导入修改，保留 v0.6.60 原有会话撤销逻辑。本机 WSL Ubuntu 24.04 中 `cargo check -q -p dbx-web --no-default-features` 退出码 0；尚未构建发布镜像。
- 用户报错入口为本机 `http://localhost:18121/`。初检 Windows 端拒绝连接，WSL 内 nginx 容器正常；短暂启动 WSL 后可访问，WSL 退出又失联。以隐藏后台 `wsl.exe ... sleep infinity` 保持实例运行后，Windows `localhost:18121/p/33/ide` 返回 200；Playwright 使用短时 token 验证 IDE 工作台就绪，DBX 初始化接口均 200，页面脚本错误 0。
- 用户给出的具体前端异常为动态导入 `/ide/assets/i18n-DvdMpN9C.js` 失败。恢复 WSL 常驻后，该资源从 `localhost:18121` 与 1.9 DBX 直连均返回 HTTP 200、3286 字节；本机 `/ide/` 和带项目上下文的 `/p/33/ide` 浏览器复测通过。原标签页需刷新以重新执行失败的动态导入。
- 另有独立的 Datara 后端缺口：1.9 `datara-rebuild-api` 未设置 `DBX_INTERNAL_TOKEN`，`/api/v1/rebuild/dbx/projects/33/connections` 返回 503；DBX 容器自身 `/ide/` 和 `/ide/api/connection/list` 均返回 200。该 503 随内部令牌镜像和后端配置接入处理，不能把它记为 DBX 容器宕机。
