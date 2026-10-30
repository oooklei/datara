# datara 宿主 × dbx 前端桥修复与 18091 重新部署报告

- 日期：2026-10-29
- 范围：修复宿主 `datara-newweb` 集成 dbx 的 3 个缺陷 → 重新构建 → 部署 `192.168.1.9:18091` → 重跑 UI E2E
- 约束遵守：未修改 dbx 源码、未修改后端；验证 key/token 仅在 shell 内存使用，未落盘/入 URL/入报告/入截图；截图对变量值统一打码。

## 1. 修改摘要

| 缺陷 | 文件 | 改动 |
| --- | --- | --- |
| P0-1 DataCloneError | `datara-newweb/src/services/rebuild/dbxVariableBridge.ts` | `sendVariablesToDbx` 内先 `entries.map((e) => ({ ...e }))` 复制为普通对象数组，再 `postMessage`；展开运算符保留「可选字段缺失」语义（未定义字段不写入）。 |
| P1-2 bridge-ready 死代码 | `datara-newweb/src/views/ide/DbxIdeView.vue` | 监听改为 `window.addEventListener('message', onBridgeReady)`；`onBridgeReady(event: MessageEvent)` 先判 `data.type === 'datara:bridge-ready'`，再校验 `event.source === frameEl.value?.contentWindow`；`removeEventListener` 同步改为 `'message'`。 |
| P2-4 / 部署漂移 | `deploy/wsl-frontend/nginx.conf`（并同步 `datara-newweb/deploy/nginx.conf`，后者是 18091 现网 r3 镜像的配置来源） | 保留/补全 `location /ide/` 反代（`proxy_pass http://192.168.1.9:4224/ide/` + `proxy_http_version 1.1` + Host/X-Real-IP/X-Forwarded-For/Connection + SSE `proxy_buffering off` 等）；新增 `absolute_redirect off;`；`/api/` 反代改为 Docker DNS `http://datara-rebuild-api:8001`（`resolver 127.0.0.11` + 变量上游 + `$request_uri` 透传），去掉自指的 18091 回环。 |

> 说明：任务书定位的 `deploy/wsl-frontend/nginx.conf` 与现网 18091 镜像实际使用的 `datara-newweb/deploy/nginx.conf` 内容不一致（后者缺 `/ide/`）。为避免「改一个、部署另一个」的漂移，两处 nginx 配置均已修正为一致语义。

关键代码（P0-1）：

```ts
const plainEntries = entries.map((entry) => ({ ...entry }))
target.postMessage({ type: DATARA_VARIABLES_MESSAGE, entries: plainEntries }, DBX_IFRAME_ORIGIN)
```

关键代码（P1-2）：

```ts
function onBridgeReady(event: MessageEvent): void {
  const data = event.data as { type?: unknown } | null
  if (!data || typeof data !== 'object' || data.type !== 'datara:bridge-ready') return
  const source = frameEl.value?.contentWindow ?? null
  if (source !== null && event.source !== null && event.source !== source) return
  sendVariablesToDbx(entries.value)
}
window.addEventListener('message', onBridgeReady)
```

## 2. 构建结果（本机）

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 类型检查 | `npx vue-tsc --noEmit` | **exit 0** |
| 生产构建 | `npm run build`（`vue-tsc -b && vite build`） | **exit 0**，2438 modules，2.3s |
| 产物 | `dist/` | `index.html`、`assets/index-Ch1MXsWp.js`（3,376,699 B）、`assets/index-D4hf4Zqh.css`（504,652 B） |

## 3. 部署结果（192.168.1.9）

- 探查结论：18091 容器 `datara-newweb-web` **非 compose 管理**（无 compose 标签），网络 `datara_default`，端口 `18091:80`，restart `unless-stopped`，运行旧镜像 `datara-newweb:s1-20261029-r3`（其 nginx 无 `location /ide/`）。18090 为并行验证栈（`dpkg-web`），未触碰。
- 部署方式：在 1.9 隔离目录 `/lei/apps/datara-frontend-fix-20261029-r4/`（`dist/` + `deploy/nginx.conf` + `Dockerfile`，基于本地已有 `nginx:1.27-alpine`）构建新镜像并原地重建同名容器。
- 新镜像：`datara-newweb:s1-20261029-r4`，ID `sha256:c866583a0c87a2564f592682142f46241735d82c04b853d2fadd31c339bb1254`，创建于 2026-10-29 11:13 (+08:00)，大小 52,123,937 B；`nginx -t` 通过。
- 新容器：`datara-newweb-web`，镜像 `datara-newweb:s1-20261029-r4`，`--network datara_default --restart unless-stopped -p 18091:80`。

部署后入口验证（在 1.9 上执行）：

| 检查 | 结果 |
| --- | --- |
| `GET /ide/` | **200**，`text/html`，`<title>DBX</title>` ✅ |
| `GET /ide`（裸） | **301**，`Location: /ide/`（相对地址，保留端口）✅ |
| `GET /` | 200，`<title>Datara</title>`（宿主 SPA）✅ |
| `GET /p/33/ide` | 200（SPA fallback）✅ |
| `GET /api/v1/rebuild/health` | 200（`datara-rebuild-api:8001` 反代通）✅ |

## 4. UI E2E 实测（Playwright 1.64.1，chromium）

- 入口：`http://192.168.1.9:18091/p/33/ide`（项目 33 作用域路由，避开裸 `/ide`；裸 `/ide` 301 亦已修复可直用）
- 认证：ssh 取 `REBUILD_VALIDATION_KEY` → `POST /api/v1/rebuild/validation-token`（header `x-backend-validation-key` + `x-backend-validation-scope: high-priority-e2e`）→ `page.addInitScript` 注入 `globalThis.__DATARA_TEST_TOKEN__`（token 未落盘/未入 URL）
- 脚本：`datara-newweb/deploy/dbx-ide-ui-verify.mjs`（沿用既有脚本，未改动）
- 结果 JSON：`datara-newweb/.evidence/dbx-ide/last-run.json`

| 步骤 | 预期 | 实测 | 判定 |
| --- | --- | --- | --- |
| 1 打开页面 | 200 并路由到 IDE 视图 | `GET /p/33/ide` → **200**，finalPath `/p/33/ide` | ✅ |
| 2 iframe 加载 | `#dbx-ide-frame` src=`/ide/`，文档 title=`DBX` | src=`/ide/`，frame url `http://192.168.1.9:18091/ide/`，`contentDocument.title="DBX"` | ✅ |
| 3 变量现值面板 | 面板 + 变量行 | header「变量现值4 项」，**4 行**：`project.dw_name`、`project.retry_max`、`global.biz_date`、`builtin.version` | ✅ |
| 4 变量下发（P0-1/P1-2） | 宿主下发 `datara:variables`，dbx 回 `datara:variables-ack` count>0 | 收到 `datara:bridge-ready`；`datara:variables-ack` **count=4**（宿主自动下发，4 条变量）；另有一次 count=0（变量加载前的空下发）与 count=1（脚本 4b 手动普通载荷诊断） | ✅ **已修复** |
| 4b 桥接诊断 | 区分普通对象 vs Proxy | 普通对象载荷 `sent` 且 iframe 收到；Proxy 载荷仍抛 `DataCloneError`（证明缺陷成因真实，宿主已改为下发普通副本） | ✅ |
| 5 SQL 变量直执行（干净状态=真实路径） | 不弹参数弹窗，直接发起执行 | 输入 `SELECT * FROM t WHERE dt = '${global.biz_date}'` 并执行：`dialogCount=0`、`mentionsParameter=false`，发起 `/ide/api/query/execute-multi`（500 仅因测试表 `t` 不存在） | ✅ **已修复** |
| 5' SQL 直执行（对照） | 无弹窗、发起执行 | 同样 `dialogCount=0`，发起 `execute-multi` | ✅ |

补充说明：

- `variables-ack count=4` 出现在脚本 4b 手动载荷之前（时间戳更早），确系宿主 `refreshVariables()` 自动下发的结果，而非手动注入。
- 干净状态复测中，脚本在变量加载完成前就抓取了 `cleanStateMessages` 快照（仅含 count=0），但随后 SQL 执行无参数弹窗且 `execute-multi` 已发出，反证变量在执行业已送达 dbx。
- `/ide/api/query/execute-multi` 的 2 次 500 与 2 条 console 500 均为测试 SQL 引用不存在的表 `t` 所致，非缺陷；它同时证明执行请求确已发出。
- 项目 33 无敏感变量，`data-variable-masked` 行未出现，脱敏分支本次未覆盖（非缺陷）。

## 5. 证据清单

| 文件 | 说明 |
| --- | --- |
| `datara-newweb/.evidence/dbx-ide/01-host-ide-variable-panel.png` | 宿主 IDE 视图 + dbx iframe + 变量面板（值已打码 `******`） |
| `datara-newweb/.evidence/dbx-ide/02-dbx-editor.png` / `02-dbx-editor-after-run.png` | 编辑器输入与执行（对照状态） |
| `datara-newweb/.evidence/dbx-ide/03-dbx-editor-clean-state.png` | 干净状态输入 SQL |
| `datara-newweb/.evidence/dbx-ide/03-dbx-editor-clean-state-after-run.png` | **干净状态执行后：无「SQL 参数」弹窗，结果面板显示 SQL 错误（表 `t` 不存在）** |
| `datara-newweb/.evidence/dbx-ide/last-run.json` | 完整结构化实测结果 |
| `datara-newweb/deploy/dbx-ide-ui-verify.mjs` | 验证脚本（位于 `datara-newweb/deploy/`） |

## 6. 最终结论

**PASS（3 个缺陷全部修复并实测验证通过）。**

- P0-1：宿主变量下发不再抛 `DataCloneError`，dbx 收到 4 条变量（ack count=4）。
- P1-2：bridge-ready 握手改走 `message` 事件，补发逻辑生效。
- P2-4 / 部署漂移：18091 镜像已含 `location /ide/` 与 `absolute_redirect off`，`/ide/` 返回 DBX、裸 `/ide` 301 保留端口；`/api/` 反代指向 `datara-rebuild-api:8001`。
- SQL 变量直执行在干净状态下不再回落参数弹窗，实际发起 `/ide/api/query/execute-multi`。

遗留/说明：脱敏分支未覆盖（项目 33 无敏感变量）；执行 500 为测试表不存在，非缺陷。18091 系本项目固定验证入口，已原地重建，未影响 18090 并行验证栈。
