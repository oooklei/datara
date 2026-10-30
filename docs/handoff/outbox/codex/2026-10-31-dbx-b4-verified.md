# DBX B4 验证卡（2026-10-31）

## 依赖与范围

- 计划节：§三 B4（DBX 1.9 直连鉴权）、B6（1.9 部署版本核验）；本卡不切换前端、编排或测试域。
- 权威边界：DBX 仅接受 Datara 内部令牌访问数据 API；公开访问不得绕过 Datara 网关。
- 目标文件：`deploy/dbx/internal-token-patch/auth.patch.0.6.29.rs`、`deploy/dbx/internal-token-patch/internal_connection.rs`。

## 已落地

- 0.6.29 鉴权补丁在 `DBX_DATARA_GATEWAY_ONLY=1` 且禁用密码时，对匿名 API 返回 401；合法 `X-Datara-Internal-Token` 仍先行放行。
- 0.6.29 内部参数路由直接返回 `Storage::load_connections` 已水合的配置，兼容该版本不存在 `WebState::resolve_connection_credentials` 的差异。
- 1.9 远端镜像 `dbx:datara-gateway-20261031` 构建成功并已重建 `dbx` 容器。

## 验证证据

- Docker release 构建：通过；`dbx-web` 仅有既有弃用/未使用 warning。
- `GET http://192.168.1.9:4224/ide/api/connection/list` 匿名：`401`。
- Datara API 容器携内部令牌请求同一路径：`HTTP/1.1 200 OK`，令牌长度仅核验为 64，未输出令牌。
- Datara API 容器携内部令牌请求 `/ide/internal/connection/datara-mysql-src/params`：`200`，响应体 715 字节；未输出凭据内容。

## 遗留

- B5：zhangsan 凭据链浏览器 E2E 尚未在 1.9 验收。
- B6：未完成。1.9 `datara-newweb:ds-20261030` 镜像创建时间为 `2026-10-30T14:37:46+08:00`，晚于账号切换修复 `21e70ba5`（13:03）但早于登录撤销修复 `aec73ba8`（15:41）；不能证明 `18091` 含登录撤销修复。下一会话第一步：切换前端域，重建并部署包含 `aec73ba8` 的镜像，再做账号切换 E2E。
- 提交 `9b4cc2e9` 时索引中已有一个与本票无关的 `sync_runtime.py` 重命名，随提交一并落入；未修改其余未暂存工作树变更，后续整理需单独核查。
