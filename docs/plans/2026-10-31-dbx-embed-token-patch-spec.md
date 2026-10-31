# DBX 嵌入令牌补丁接口约定（容器侧实现规范）

- **目的**：让 DBX 容器支持 datara 统一嵌入网关（`embedded-direct-gateway-migration`）的同源直连：
  浏览器经 nginx 同源反代 `/ide/` 直达 DBX，nginx 注入 `X-Datara-Embed-Token`，
  DBX 容器**自验令牌 + 按 `project_id`/`user_id` 自过滤**，不再由 datara 逐路由代理其业务 API。
- **配套（已在仓库内完成）**：
  - `rebuild/orchestration/api.py:unified_embed_session` 签发 DBX 嵌入令牌并以 HttpOnly cookie `datara_dbx_embed`（path=/ide，TTL 900s）下发。
  - `datara-newweb/deploy/nginx.conf` + `deploy/wsl-frontend/nginx.conf` 的 `location /ide/` 注入
    `proxy_set_header X-Datara-Embed-Token $cookie_datara_dbx_embed;`（方案规则 2）。
- **DS 侧已有对照实现**：`deploy/dolphinscheduler/3.4.3/datara-integration.patch`（`LoginHandlerInterceptor` 解析 `X-Datara-Embed-Token` + `verifyDataraEmbedToken`）。

## 1. 令牌格式（与 DS 共用同一签名算法）

```
token = base64url(json_claims) + "." + base64url(hmac_sha256(secret, base64url(json_claims)))
```

- `json_claims`（无空格紧凑 JSON）：
  ```json
  {"u": "<datara_username>", "p": "<project_code>", "d": <project_id:int>, "exp": <unix_ts:int>, "jti": "<random16hex>"}
  ```
  - `u`：datara 用户名（DBX 侧按此做 `user_id` 过滤）。
  - `p`：datara 项目编码（辅助；DBX 以 `d` 为主键）。
  - `d`：datara 项目 id（**主归属键**，所有业务 API 必须按此过滤）。
  - `exp`：过期时间戳；DBX 必须拒绝 `exp < now`。
  - `jti`：一次性随机串，用于防重放缓存键（见 §4）。
- **签名密钥**：`DATARA_DS_EMBED_SECRET`（**datara-backend 与 DBX 容器必须配置为同一值，且 ≥ 32 字节**）。
  - datara 侧已用该环境变量签发；DBX 容器需以**只读挂载/环境变量**拿到同一密钥，禁止硬编码进镜像。
- **编码**：标准 `base64urlsafe`（去 padding）；claims 段与签名段均做 `rstrip("=")`。

## 2. 验证算法（DBX 入口拦截器伪代码）

```python
def verify_datara_embed_token(raw: str | None) -> dict:
    if not raw or "." not in raw:
        raise Unauthorized("missing embed token")
    claims_b64, sig_b64 = raw.split(".", 1)
    secret = os.environ["DATARA_DS_EMBED_SECRET"].encode()
    expected = hmac.new(secret, claims_b64.encode(), sha256).digest()
    provided = base64urlsafe_b64decode(sig_b64)            # 需补 padding
    if not hmac.compare_digest(expected, provided):
        raise Unauthorized("bad embed token signature")
    claims = json.loads(base64urlsafe_b64decode(claims_b64))
    if int(claims["exp"]) < int(time.time()):
        raise Unauthorized("embed token expired")
    return claims   # {u, p, d, exp, jti}
```

- 入口拦截器位置：DBX 所有 `/api/*` 业务路由之前（类比 DS 的 `LoginHandlerInterceptor`）。
- 验证失败 → `401`，且**不要**回退到旧 owner-gateway cookie 流程（避免令牌形同虚设）。
- 成功后将 `project_id=claims["d"]`、`user_id=claims["u"]` 绑定到当前请求上下文（DBX 会话/线程局部）。

## 3. 按 project_id/user_id 过滤（方案规则 ③ 的安全改造范围）

DBX 仅保留少数安全改造，其余原生 API 直通：

| 改造点 | 行为 |
|---|---|
| 连接列表 `GET /api/connection/list` | 仅返回归属 `project_id` 且对 `user_id` 可见的连接；拒绝跨项目。 |
| 连接保存 `POST /api/connection/save` | 写入时强制绑定 `project_id`（忽略/覆盖客户端传入的项目归属）；拒绝越权项目。 |
| 查询执行 `POST /api/query/execute` | 仅允许在过滤器确认归属的连接上执行；拒绝越权连接 id。 |
| 其余（schema / history / saved-sql / ai / tunnel / 资源文件等） | **原生 API 直通**，不再经 datara 代理；但所有请求已带 `project_id/user_id` 上下文，DBX 内部既有鉴权仍生效。 |

> 注意：DBX 自身的连接凭据**仍只存于 DBX**（datara 只持 `connection_id`），此约束不变。

## 4. 缓存（重构「用上缓存」要求）

- **令牌验证缓存**：以 `jti` 为键缓存 `(claims, 验证时间)`，`TTL = min(token.exp - now, 900s)`。相同 `jti` 在 TTL 内免重复 HMAC 验签；TTL 后可重放但已过期被拒，故安全。
- **连接元数据缓存**：按 `(project_id, user_id)` 缓存连接列表/可见性结果（建议 TTL 30–60s），降低每次列表/执行前的归属查询开销。
- **查询执行连接池**：为 DBX 后端到各用户库的连取建独立连接池（按 `connection_id` 隔离），避免全局单池被慢查询拖垮；池大小与读超时按项目/用户维度限流。
- **静态资源**：DBX 前端 `/ide/` 静态走 nginx（`proxy_buffering off` + 长 `Cache-Control`），DBX 容器侧对前端产物启用构建期 hash 缓存（build cache layer）。

## 5. 验收（供 1.9 实测）

1. 未带/带错 `X-Datara-Embed-Token` 调 DBX `/api/connection/list` → `401`。
2. 带有效令牌 → 仅返回该 `project_id` 下、该 `user_id` 可见的连接；尝试用别的项目 connection_id 执行 `query/execute` → 拒绝。
3. 令牌过期（exp 已过）→ `401`。
4. 直连路径经 nginx `/ide/` 实测：浏览器不持有令牌（HttpOnly cookie，JS 不可读），网关注入成功，DBX 自验通过。
5. `ide_proxy.py`（datara 旧代理）在 Phase A 仍保留作回退；Phase C 再下线（见迁移方案）。

## 6. 与 DolphinScheduler 的对称性

Dolphin 侧已通过 `datara-integration.patch` 落地同类拦截器；DBX 侧**只需补齐本文件 §2–§4**，密钥/头名/claims 结构完全一致，便于两端统一维护。
