# datara 宿主 × dbx IDE 集成 UI E2E 验收报告

- 验收日期：2026-10-29
- 验收对象：宿主 `datara-newweb`（`DbxIdeView.vue` + `dbxVariableBridge.ts`）集成 dbx 的 IDE 视图（iframe `#dbx-ide-frame` + `datara:variables` 变量桥 + SQL 变量直执行）
- 关联计划：`docs/plans/2026-10-29-dbx-ide-integration-workflow.md`
- 验证方式：Playwright 1.64.1（chromium）无头浏览器，脚本 `datara-newweb/deploy/dbx-ide-ui-verify.mjs`
- **最终结论：部分通过（存在 P0 阻塞缺陷）**
  - iframe 集成、iframe 文档加载、变量现值面板展示：**通过**
  - 变量自动下发（宿主 → dbx）：**失败（P0：DataCloneError）**
  - SQL 变量直执行（不弹参数弹窗）：**失败（真实路径必然回落参数弹窗）**

> 上述为**首轮**结论。P0-1/P1-2/P2-4 修复后已重跑验收，结论见 **§8：通过**（三项缺陷确认修复，另发现 2 项非阻塞问题）。

> 敏感信息一律掩码：验证 key 与 token 仅经环境变量注入，未落盘、未入 URL、未进截图；截图已对变量面板值统一打码。本报告不含任何 key/token/密码明文。

---

## 0. 阻塞根因（先讲结论）

**宿主侧把 Vue 3 响应式 Proxy 数组直接交给 `postMessage`，structured clone 不支持 Proxy，抛 `DataCloneError`，导致 dbx 永远收不到变量。**

证据链（一次运行内同时取得）：

| 检查项 | 方法 | 结果 |
| --- | --- | --- |
| 宿主自动下发 ack | 宿主 `message` 监听器收集 `datara:*` | 仅收到 `datara:bridge-ready`；`datara:variables-ack` **count=0** |
| 普通对象载荷 | 向 iframe `postMessage({type:'datara:variables', entries: 普通数组})` | `sent`，iframe 侧收到 `datara:variables` |
| Proxy 载荷 | 同上但 `entries: new Proxy(plain.slice(), {})` | **抛 `DataCloneError: Failed to execute 'postMessage' on 'Window': [object Object] could not be cloned.`** |
| dbx 侧逻辑 | 手动发普通对象载荷后 | dbx 回 `datara:variables-ack count=1`（**桥机制与 dbx 侧均正常**） |
| 控制台 | `consoleErrors` | `DataCloneError ... at index-DfW55u49.js:151`（宿主 bundle） |

即：**唯一故障点是宿主传入 Proxy**。dbx 侧 `datara:variables` 监听与 `datara:variables-ack` 回执逻辑完全正常。

---

## 1. 验收环境

| 项 | 值 |
| --- | --- |
| 宿主验证栈 | `http://192.168.1.9:18093`（临时容器 `datara-newweb-s16-verify`，镜像 `datara-newweb:s16`，dist `index-DfW55u49.js`） |
| 宿主入口 | `/p/33/ide`（项目 33「电商全域数据治理项目」作用域路由） |
| dbx | `http://192.168.1.9:18093/ide/`（s16 nginx `location /ide/` → `http://192.168.1.9:4224/ide/`） |
| 认证 | `page.addInitScript` 注入 `globalThis.__DATARA_TEST_TOKEN__`（短时 token，role=admin，900s） |
| token 来源 | `POST /api/v1/rebuild/validation-token`（header `x-backend-validation-key` / `x-backend-validation-scope`，仅 shell 内使用） |

> **为何用 18093 而非任务书写的 18091**：18091 实际运行的镜像不含本特性（见 §3 问题 P1-3）。为不停止 18091 现有验证栈，另起临时容器 `datara-newweb-s16-verify`（`--network datara_default -p 18093:80`）承载 s16 做集成验证；**验收结束已 `docker rm -f` 清理**，18091 栈未受影响。

---

## 2. 分步实测结果

| 步骤 | 预期（设计） | 实测 | 判定 |
| --- | --- | --- | --- |
| 1. 打开页面 | 宿主 SPA 加载，路由到 IDE 视图 | `GET /p/33/ide` → **200**，finalPath `/p/33/ide` | ✅ 通过 |
| 2. iframe 加载 | 出现 `#dbx-ide-frame`，src 含 `/ide/`，文档 title `DBX` | `#dbx-ide-frame` src=`/ide/`；frame url `http://192.168.1.9:18093/ide/`；`contentDocument.title="DBX"`，readyState=`complete` | ✅ 通过 |
| 3. 变量现值面板 | `data-variable-panel` + 变量行 + 敏感行脱敏 | panel present，header「变量现值4 项」，**4 行**：`project.dw_name=datara_dw`、`project.retry_max=3`、`global.biz_date=2026-10-28`、`builtin.version=0.1.0`；无 sensitive 行（`data-variable-masked` 为空） | ✅ 通过（见备注） |
| 4. 变量下发到 dbx | 宿主下发 `datara:variables`，dbx 回 `datara:variables-ack` | 仅收到 `datara:bridge-ready`；**ack count=0**（宿主下发失败） | ❌ **失败（P0）** |
| 4b. 桥接诊断 | 定位故障点 | 普通对象载荷 `sent` 且 iframe 收到；Proxy 载荷抛 `DataCloneError`；手动普通载荷后 dbx 回 `ack count=1` | ✅ 诊断完成 |
| 5. SQL 变量直执行（干净状态＝真实用户路径） | 不弹参数弹窗，直接发起执行 | **弹出 `prepareSqlParameterDialog`**（dialogCount=2，弹窗文本含「SQL 参数…参数名 `global.biz_date`…SQL 预览 `SELECT * FROM t WHERE dt = ''`」） | ❌ **失败** |
| 5'. SQL 直执行（对照：手动灌快照） | 验证 dbx 侧替换逻辑本身 | 步骤 4b 手动把 `biz_date` 灌入 dbx 快照后执行 → **无弹窗**，`/ide/api/query/execute-multi` 发起执行 | ✅ 证明 dbx 侧正常 |

### 步骤 5 证据说明

- **干净状态（真实路径）**：重新加载页面后 dbx 仅发 `datara:bridge-ready`（无 ack），说明宿主自动下发未成功；此时输入 `SELECT * FROM t WHERE dt = '${global.biz_date}'` 并执行，**弹出参数弹窗**，`mentionsParameter=true`。
  - 截图：`.evidence/dbx-ide/03-dbx-editor-clean-state-after-run.png`
- **对照状态**：若先手动以普通对象载荷把 `biz_date` 灌入 dbx 快照，执行**不再弹窗**，并实际发起 `/ide/api/query/execute-multi`（返回 500 仅因测试用表 `t` 不存在）。
  - 截图：`.evidence/dbx-ide/02-dbx-editor-after-run.png`

> 步骤 4b 的手动载荷会污染 dbx 快照，因此脚本额外做了「干净状态复测」，二者结果一致地指向：**dbx 侧正常，宿主自动下发失败**。

### 备注

- 项目 33 无 sensitive 变量，故 `data-variable-masked` 行为空属预期（脱敏代码路径未被覆盖，非缺陷）。
- 控制台出现的 500 均为 dbx 侧 `/ide/api/schema/columns?...table=t` 与 `/ide/api/query/execute-multi`，由测试 SQL 引用不存在的表 `t` 引起，**非缺陷**；它同时证明执行请求确已发出。
- 执行按钮为 dbx 工具栏无文本图标按钮（无 aria/title），脚本按工具栏坐标（x≈272,y≈82，24×24）点击命中；编辑器为 CodeMirror 6（`.cm-content`，`contenteditable=true`）。

---

## 3. 发现的问题

### P0-1 宿主 `sendVariablesToDbx` 传入 Vue 3 响应式 Proxy → DataCloneError（阻塞）

- 位置：`datara-newweb/src/views/ide/DbxIdeView.vue`（`refreshVariables()` → `sendVariablesToDbx(entries.value)`）；`datara-newweb/src/services/rebuild/dbxVariableBridge.ts`。
- 现象：`entries.value` 是 `ref` 的响应式 Proxy 数组，`postMessage` structured clone 抛 `DataCloneError`。
- 后果：dbx 永远收不到变量 → SQL 变量直执行必然回落 `prepareSqlParameterDialog`。
- 建议：下发前做**纯对象深拷贝**（如 `JSON.parse(JSON.stringify(entries))` 或 `toRaw` + 递归克隆），再 `postMessage`。

### P1-2 `datara:bridge-ready` 补发逻辑为死代码

- 位置：`DbxIdeView.vue` `onMounted` → `window.addEventListener('datara:bridge-ready', onBridgeReady)`。
- 现象：`addEventListener` 的第一参数是**事件类型**（此处被当作 Event 名），而 dbx 用 `postMessage` 发送 `datara:bridge-ready`（属 `message` 事件）。该补发逻辑**永不触发**。
- 影响：即便修好 P0-1，dbx 晚于宿主就绪时也拿不到变量（本次实测中宿主靠 `refreshVariables()` 主动下发掩盖了此问题）。
- 建议：改为在 `message` 事件里判定 `event.data.type === 'datara:bridge-ready'` 后补发。

### P1-3 部署/镜像漂移（环境与任务前提不符）

- 任务前提：18091 运行 `datara-newweb:s16`。
- 实测：18091 容器 `datara-newweb-web` 用镜像 **`datara-newweb:s1-20261029-r3`**（dist `index-mC2Jh8UM.js` **不含** `dbx-ide-frame`/`datara:variables`/`/ide/`，nginx **无** `location /ide/`）。
- 而镜像 `datara-newweb:s16`（dist `index-DfW55u49.js`）**含**全部特性且 nginx 有 `location /ide/ { proxy_pass http://192.168.1.9:4224/ide/; proxy_buffering off; }`。
- 建议：在 18091 重新部署 s16（或修正任务前提），否则按 18091 验收必然失败。

### P2-4 nginx `/ide`（无尾斜杠）301 丢端口

- 现象：`location /ide/` 前缀匹配使裸 `/ide` 触发 301，`absolute_redirect` 默认用 `$host`（不含端口）→ `Location: http://192.168.1.9/ide/`，Chromium 跟随跳转后连 80 端口 `ERR_CONNECTION_REFUSED`。
- 建议：`absolute_redirect off;`（使用相对跳转）或显式设置 `port_in_redirect on;`。
- 本次规避：入口改用 `/p/33/ide`（走 `location /` → SPA）。

### P2-5 脱敏路径未被覆盖（记录，非缺陷）

- 项目 33 无 sensitive 变量，`data-variable-masked` 行预期为空；`maskSensitiveValue()` 的 `***` 分支本次未被实测覆盖。

---

## 4. 与设计预期的一致性小结

| 设计点 | 一致性 |
| --- | --- |
| 宿主路由 `/ide` → `DbxIdeView.vue`，iframe `#dbx-ide-frame` `src="/ide/"` | 一致（经 `/p/33/ide` 生效） |
| 变量桥 `datara:variables` / `datara:variables-ack`，origin 用 `window.location.origin` | 桥协议一致；**宿主发送侧失败** |
| 敏感变量 value 脱敏为 `***` | 逻辑存在；本次无敏感变量未触发 |
| `useSqlExecution.ts` 挂载点 `tryExternalSqlParameters`，未命中回落 `prepareSqlParameterDialog` | 一致；**未命中**（因宿主未下发），实测回落弹窗 |
| dbx 侧监听 `datara:variables` 并回 ack | 一致且正常（手动载荷实测 ack=1） |

---

## 5. 手动复现步骤（供人工复核）

1. 本机执行（token 仅经环境变量，不落盘）：
   ```powershell
   $keyLine = ssh root@192.168.1.9 'docker inspect datara-rebuild-api --format "{{range .Config.Env}}{{println .}}{{end}}" | grep REBUILD_VALIDATION_KEY'
   $key = ($keyLine -split '=',2)[1].Trim()
   $r = Invoke-RestMethod -Method Post -Uri 'http://192.168.1.9:18091/api/v1/rebuild/validation-token' `
       -Headers @{ 'x-backend-validation-key' = $key; 'x-backend-validation-scope' = 'high-priority-e2e' } `
       -ContentType 'application/json' -Body '{}'
   $env:DATARA_TEST_TOKEN = $r.data.token
   ```
2. 起临时验证容器（不碰 18091）：
   ```bash
   ssh root@192.168.1.9 "docker run -d --name datara-newweb-s16-verify --network datara_default -p 18093:80 datara-newweb:s16"
   ```
3. 运行脚本：
   ```powershell
   node deploy/dbx-ide-ui-verify.mjs --base http://192.168.1.9:18093 --out .evidence/dbx-ide
   ```
4. 人工在浏览器打开 `http://192.168.1.9:18093/p/33/ide`（注入 token 后），新建查询输入 `SELECT * FROM t WHERE dt = '${global.biz_date}'` 并执行 → **观察是否弹出「SQL 参数」弹窗**（当前会弹出）。
5. 清理：`docker rm -f datara-newweb-s16-verify`。

---

## 6. 证据清单

| 文件 | 说明 |
| --- | --- |
| `datara-newweb/.evidence/dbx-ide/01-host-ide-variable-panel.png` | 宿主 IDE 视图 + 变量现值面板（值已打码 `******`） |
| `datara-newweb/.evidence/dbx-ide/02-dbx-editor.png` | 编辑器输入 SQL（对照状态） |
| `datara-newweb/.evidence/dbx-ide/02-dbx-editor-after-run.png` | 对照状态执行后：无弹窗，结果面板显示 SQL 错误（表 `t` 不存在） |
| `datara-newweb/.evidence/dbx-ide/03-dbx-editor-clean-state.png` | 干净状态输入 SQL |
| `datara-newweb/.evidence/dbx-ide/03-dbx-editor-clean-state-after-run.png` | **干净状态执行后：弹出「SQL 参数」弹窗（关键证据）** |
| `datara-newweb/.evidence/dbx-ide/last-run.json` | 完整结构化实测结果（含桥接诊断、消息日志、api/badResponses、截图清单） |
| `datara-newweb/deploy/dbx-ide-ui-verify.mjs` | 验证脚本（含干净状态复测，避免手动载荷污染） |

> 截图右上角 `validation-e2e-runner` 为验证 token 的用户名（`datara-backend/rebuild/api/app.py`），非密钥。

---

## 7. 最终结论（首轮）

**部分通过（存在 P0 阻塞缺陷）。**

> 本轮结论已被 §8 重跑验收取代（三项缺陷修复后复测：**通过**）。

- 通过：iframe 集成与加载、变量现值面板展示、dbx 侧桥接与替换逻辑。
- 失败：**变量自动下发**（P0 DataCloneError）与 **SQL 变量直执行**（真实路径必然回落参数弹窗）。
- 处置建议：优先修复 P0-1（下发前深拷贝），并修复 P1-2（`message` 事件判定）与 P1-3（重新部署 s16）；修复后重跑本脚本复测步骤 4/5。
- 约束遵守：未修改任何前端/dbx 源码；未把 key/token/密码写入报告、URL、文件或截图；临时容器与探针脚本已清理。

---

## 8. 重跑验收（P0-1/P1-2/P2-4 修复后）

- 重跑日期：2026-10-29
- 宿主：`http://192.168.1.9:18091`（18091 正式验证栈，容器 `datara-newweb-web`，镜像 `datara-newweb:s1-20261029-r5`，dist `index-CE61-HFP.js`）——比任务书假设的 r4 更新，**无需再起临时容器**。
- dbx：`location /ide/ { proxy_pass http://192.168.1.9:4224/ide/; }`，nginx 含 `absolute_redirect off;`（P2-4 修复）。
- 入口：`/p/33/ide`（项目 33「电商全域数据治理项目」）。
- 脚本：`datara-newweb/deploy/dbx-ide-ui-verify-rerun.mjs`（复用并扩展首轮 `dbx-ide-ui-verify.mjs`：新增宿主帧 + dbx iframe 帧双端 message 日志、裸 `/ide` 301 相对 Location 校验、真实常量查询 `SELECT '${global.biz_date}' AS dt`、刷新按钮增量校验、route-mock 脱敏渲染验证）。
- 结果文件：`datara-newweb/.evidence/dbx-ide/last-run-rerun.json`（`2026-10-29T04:26:35Z → 04:26:56Z`，`consoleErrors=[]`、`pageErrors=[]`、`badResponses=[]`）。

### 8.1 六个验收点逐条结论

| # | 验收点 | 结论 | 关键证据 |
| --- | --- | --- | --- |
| 1 | `/ide` 页面加载 + 宿主头部（项目/环境组上下文、环境组 ID 输入、刷新按钮、变量管理入口） | ✅ 通过 | `GET /p/33/ide` → 200，finalPath `/p/33/ide`；`[data-dbx-context]` =「项目：电商全域数据治理项目 · 环境组：未指定」（脚本 JSON 抓取瞬间 projects 未加载显示「项目 #33」，截图已渲染项目名）；`input[data-environment-group]` 存在；`[data-variable-refresh]`=「刷新变量」且 `disabled=false`；`[data-variable-manage]`=「变量管理」且 `disabled=false`；iframe `src=/ide/`。截图 `r2-01-host-ide-variable-panel.png`。**注意：裸 `/ide` 不可直达宿主路由，见 8.4 N-1** |
| 2 | iframe `#dbx-ide-frame` 加载完成（同源 `/ide/`、frameLocator 可访问、静态资源 `/ide/assets`） | ✅ 通过 | `accessible=true`、`title=DBX`、`url=http://192.168.1.9:18091/ide/`、`readyState=complete`、脚本 `/ide/assets/index-CE61-HFP.js`。截图 `r2-02-after-variable-bridge.png` |
| 3 | 变量现值面板（`data-variable-panel` / `data-variable-value` / `data-variable-masked`） | ✅ 通过 | panel present，header「变量现值4 项」，`rowCount=4`：`project.dw_name=datara_dw`、`project.retry_max=3`、`global.biz_date=2026-10-28`、`builtin.version=0.1.0`。`maskedCount=0`——**项目 33 无 sensitive 变量**（全库仅 1 个项目、无 env scope 变量）；脱敏路径以 route-mock 覆盖（见 8.3）。截图 `r2-02` / `r2-06` |
| 4 | 变量自动下发：dbx 发 `datara:bridge-ready` 后宿主补发，iframe 内收到 `datara:variables` 且回 `datara:variables-ack` | ✅ 通过（P0-1 + P1-2 修复确认） | `bridgeReadyCount=1`、`ackCount=1`（`ackPayloadCount=4`）；iframe 侧收到 `datara:variables` **×2**（初次下发 + bridge-ready 补发），entries 4 条含真实值；`dataCloneError=[]`。`frameSawAck=false` 属预期：dbx 将 ack 回给 `event.source`（父窗），iframe 自身看不到 |
| 5 | SQL 变量直执行无弹窗（`${global.biz_date}` 形如 shell 占位符，key 含 scope 前缀） | ✅ 通过 | SQL `SELECT '${global.biz_date}' AS dt`，`Ctrl+Enter` 触发；`POST /ide/api/query/execute-multi` 发出且无 4xx/5xx；`dialogCount=0`、`mentionsParameter=false`、`mentionsBizDate=true`（结果区显示 `2026-10-28`）。截图 `r2-03-sql-entered.png` / `r2-04-sql-after-run.png` |
| 6 | 刷新按钮 `data-variable-refresh` 能重新拉取并重新下发 | ✅ 通过 | 点击后 `completeCalls 1→2`、`ackCount 1→2`、`frameVars 2→3`、`rePulledAndResent=true`；面板仍 4 行且值不变。截图 `r2-05-after-refresh.png` |

### 8.2 三个缺陷修复确认

| 缺陷 | 修复点 | 重跑证据 | 判定 |
| --- | --- | --- | --- |
| **P0-1** Proxy `DataCloneError` | `dbxVariableBridge.ts` `sendVariablesToDbx` 下发前 `entries.map((e) => ({ ...e }))` 深拷贝为普通对象 | `dataCloneError=[]`、`ackCount=1`（4 条）、console/page errors 全空 | ✅ 确认修复 |
| **P1-2** `datara:bridge-ready` 死代码 | `DbxIdeView.vue` 改为在 `message` 事件中判定 `event.data.type === 'datara:bridge-ready'` | `bridgeReadyCount=1`，iframe 收到 `datara:variables` 计数含 bridge-ready 补发（共 2 次） | ✅ 确认修复 |
| **P2-4** nginx `/ide` 301 丢端口 | nginx 增加 `absolute_redirect off;` | 裸 `/ide` → **301**，`Location: /ide/`（**相对**，未丢端口），跟随 → **200**，最终 URL `http://192.168.1.9:18091/ide/` | ✅ 确认修复 |

### 8.3 脱敏覆盖（补充）

项目 33 无 sensitive 变量，故以 `route-mock` 拦截 `POST /api/v1/rebuild/variables/complete` 注入 `project.api_secret`（`sensitive=true`）覆盖前端渲染与下发脱敏路径：

- 面板 `project.api_secret` 渲染为 `[data-variable-masked]`，文本 `***`；`bodyContainsSecret=false`。
- iframe 收到的 entries 中 `api_secret.sensitive=true, value='***'`；`frameEntryValueIsMasked=true`、`framePayloadContainsSecret=false`。
- 截图 `r2-06-sensitive-masked.png`。**未改动任何生产数据。**

### 8.4 新发现问题

- **N-1（P1，非阻塞）裸 `/ide` 直达不可达宿主路由**：nginx `location / { try_files $uri $uri/ /index.html; }` 与 `location /ide/` 前缀匹配叠加，使裸 `/ide` 命中 `$uri/` 目录规则 → 301 到 `/ide/`，而 `/ide/` 被反代到 dbx 独立页；宿主路由 `/ide`（`routes.ts` `{ path: '/ide', name: 'sql-ide' }`）直接访问/硬刷新时拿不到宿主头部与变量桥。SPA 内部客户端跳转（菜单「SQL IDE」入口）不受影响。建议 `location = /ide { try_files /index.html =404; }` 或将对外入口统一为 `/p/<id>/ide`。
- **N-2（P2，记录）真实 sensitive 变量路径未覆盖**：项目 33 无 sensitive 变量，脱敏仅由 route-mock 验证；建议后续补一条真实 sensitive 变量的端到端验收。
- 环境说明：18091 现镜像为 `s1-20261029-r5`（比任务书写的 r4 更新），首轮 P1-3（镜像漂移）已被 r5 覆盖，无遗留。

### 8.5 证据清单（重跑）

| 文件 | 说明 |
| --- | --- |
| `datara-newweb/.evidence/dbx-ide/r2-01-host-ide-variable-panel.png` | 宿主头部（项目名/环境组/环境组 ID 输入/刷新变量/变量管理）+ 变量现值面板 4 项（值已打码） |
| `datara-newweb/.evidence/dbx-ide/r2-02-after-variable-bridge.png` | 桥接完成后：面板 4 项 + iframe 就绪 |
| `datara-newweb/.evidence/dbx-ide/r2-03-sql-entered.png` | 编辑器输入 `SELECT '${global.biz_date}' AS dt` |
| `datara-newweb/.evidence/dbx-ide/r2-04-sql-after-run.png` | **执行后无弹窗**，结果 1 行 `2026-10-28`（关键证据） |
| `datara-newweb/.evidence/dbx-ide/r2-05-after-refresh.png` | 刷新按钮后重新拉取并重新下发 |
| `datara-newweb/.evidence/dbx-ide/r2-06-sensitive-masked.png` | route-mock 下 `project.api_secret` 面板渲染为 `***` |
| `datara-newweb/.evidence/dbx-ide/last-run-rerun.json` | 完整结构化实测结果（含双端消息日志、桥接诊断、刷新增量、脱敏、api/badResponses、截图清单） |
| `datara-newweb/deploy/dbx-ide-ui-verify-rerun.mjs` | 重跑验证脚本（复用并扩展首轮脚本） |

### 8.6 重跑最终结论

**通过。** P0-1（Proxy `DataCloneError`）、P1-2（`datara:bridge-ready` 死代码）、P2-4（`/ide` 301 丢端口）三项修复均经端到端实测确认生效；六个验收点全部通过，未出现 console/page error 或异常响应。遗留 2 项非阻塞问题：N-1 裸 `/ide` 直达被 nginx 遮蔽（建议统一入口）、N-2 真实 sensitive 变量路径待补测。约束遵守：未修改任何前端/dbx/nginx 源码；key 记 `dva****`、token 记 `tok_****`，未落盘、未入 URL、未进截图；截图对变量面板值统一打码。
