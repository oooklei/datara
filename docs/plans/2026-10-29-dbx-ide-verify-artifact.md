# dbx ↔ datara 产物一致性稽核报告

- 稽核日期：2026-10-29
- 稽核对象：dbx 前端补丁源码 / dbx dist 产物 / dbx 容器挂载 / datara 前端 dist 产物 / datara 自研 IDE 归档 / 契约测试 / 本地 git 状态
- 关联计划：`docs/plans/2026-10-29-dbx-ide-integration-workflow.md`
- 稽核环境：本机 `d:\需求\数据治理工具\Datara`（代码/测试）+ 192.168.1.9（部署/容器，ssh root，只读检查）
- 性质：**只读稽核，未修改任何源码、产物或容器配置**
- **最终结论：产物存在性与一致性 PASS（7 项全通过）；另发现 2 项跨产物语义不一致风险（见 §8），不影响产物判定，但会导致"外部变量自动代入"在运行时不可用。**

> 脱敏约定：本报告不记录任何 token / key / password 明文。dbx 容器环境变量中的口令一律写作 `***`。

---

## 1. dbx 源码补丁存在性 — PASS

检查命令（1.9）：`ls -l` + `grep -n` 目标 4 个文件。

| 文件 | 大小/mtime | 关键标记 |
| --- | --- | --- |
| `apps/desktop/src/lib/sql/externalVariables.ts` | 752B，10-29 08:31 | 导出齐全：`ExternalVariableEntry`、`setExternalVariables`、`clearExternalVariables`、`lookupExternalVariable`、`externalVariableSnapshot` |
| `apps/desktop/src/composables/useExternalVariableBridge.ts` | 1137B，10-29 08:31 | `export const DATARA_VARIABLES_MESSAGE = "datara:variables"`（L4）；回执 `datara:variables-ack`（L17）；`allowedOrigins` 默认 `[window.location.origin]`；`onMounted` 向 `window.parent` 发 `datara:bridge-ready` |
| `apps/desktop/src/composables/useSqlExecution.ts` | 51572B，10-29 08:32 | L262 `const externalResolved = tryExternalSqlParameters(sql, context.connection);`；L358 定义；未命中（`null`）后回落 `prepareSqlParameterDialog`，再回落 `continueExecute` |
| `apps/desktop/src/App.vue` | 222090B，10-29 08:32 | L60 import、L1141 setup 顶层调用 `useExternalVariableBridge();` |

结论：4 个补丁文件全部在位，关键标记与方案要求逐条对应。

---

## 2. dbx dist 补丁烤入 + `/ide` 基路径 — PASS

1.9 上 `/lei/apps/dbx/dist/`：

- `index.html` 24740B、`assets/App-Cscnmwp_.js` 818283B，mtime 均为 **2026-10-29 08:52**，晚于全部源码 mtime（08:31/08:32）→ 构建晚于补丁落盘。
- `index.html` 内资源引用全部为 `/ide/` 前缀（`grep -o /ide/... | sort -u`）：
  `/ide/assets/index-CE61-HFP.js`、`/ide/assets/index-Cd4yscaW.css`、`/ide/assets/preload-helper-CUdEKMCz.js`、`/ide/assets/rolldown-runtime-Dd_uD5pT.js`、`/ide/assets/safeStorage-CqBeTkCx.js`、`/ide/assets/tauriRuntime-BY5TgTJX.js`、`/ide/assets/ui-C4wMOoOy.js`、`/ide/connection-dialog-legacy.css`、`/ide/favicon.png`
  → 与 `VITE_DBX_BASE_PATH=/ide` 构建结果一致，无根绝对路径（`/assets/...`）残留。
- 产物 JS 字符串命中（grep -rl）：
  - `datara:variables` → `assets/App-Cscnmwp_.js`（1 文件）
  - `datara:variables-ack` → 同文件
  - `datara:bridge-ready` → 同文件
- `externalVariables` / `tryExternalSqlParameters` 在产物中 **0 命中**：属压缩后标识符改名（预期），不作为 FAIL。替代证据为上述协议字符串命中 + §1 源码标记。

容器内同一份产物（挂载点）复核：`docker exec dbx grep -rl datara:variables /app/static/assets` → `/app/static/assets/App-Cscnmwp_.js`。

HTTP 实测（1.9 本机）：`GET /ide/` → 200（24740B，与 dist/index.html 同尺寸），`GET /ide/assets/App-Cscnmwp_.js` → 200 `text/javascript`。

---

## 3. dbx 容器挂载与启动日志 — PASS

`docker inspect dbx`：

| 项 | 实际值 |
| --- | --- |
| 挂载 | `/lei/apps/dbx/backups → /app/backups (rw)`、`/lei/apps/dbx/data → /app/data (rw)`、**`/lei/apps/dbx/dist → /app/static (ro)`** |
| 镜像 | `t8y2/dbx@sha256:8c0f6ae1bb92e494b26f398780bed8c409740d142892a86fea05f39359783588` |
| 环境 | `DBX_PUBLIC_BASE_PATH=/ide`、`DBX_STATIC_DIR=/app/static`、`DBX_DISABLE_PASSWORD=true`、`DBX_BACKUP_ROOT=/app/backups`、`DBX_PASSWORD=***`（已掩码）、`TZ=Asia/Shanghai` |
| 端口 | `4224:4224` |

启动日志（`docker logs dbx`）含：

```
INFO dbx_web: DBX Web server starting on http://0.0.0.0:4224
INFO dbx_web: Serving DBX Web under context path /ide
INFO dbx_web: Password protection is disabled
```

`/lei/apps/dbx/deploy-1.9/docker-compose.yml`（mtime 10-29 09:02）内容与上述运行态逐条吻合：固定 digest 镜像、`DBX_PUBLIC_BASE_PATH=/ide`、`DBX_STATIC_DIR=/app/static`、`DBX_DISABLE_PASSWORD=true`、`/lei/apps/dbx/dist:/app/static:ro`。旁存 `docker-compose.yml.bak-20261029`（改动前备份）。

附注：日志尾部有一条 `tower_http::trace::on_failure ... 500`（10-29 01:23），属请求级异常记录，与产物/挂载无关。

---

## 4. datara 前端 dist 产物 — PASS

1.9 容器 `datara-newweb-web`，`/usr/share/nginx/html/`：`index.html` + `assets/index-mC2Jh8UM.js` + `assets/index-BB4EhaxB.css`（单 bundle 构建）。

| 检查 | 结果 |
| --- | --- |
| `index.html` 引用 | `/assets/index-mC2Jh8UM.js`、`/assets/index-BB4EhaxB.css`（与 assets 文件名一一对应） |
| `grep -c dbx-ide-frame` | 1 |
| `grep -c datara:variables` | 命中该 JS（`-l`） |
| `grep -c datara:bridge-ready` | 1 |
| `grep -c -F '***'`（脱敏掩码） | 3 |
| `grep -c data-variable-masked` | 1 |
| 文案抽样 | `数据开发` 2 处、`变量现值` 1 处、`环境组` 3 处（DbxIdeView 已烤入） |

一致性交叉验证（本机 `datara-newweb/dist` vs 容器）：**MD5 完全相同**

- `assets/index-mC2Jh8UM.js` → `BEA2942937804A223F584675EA34C4C5`（本地 / 容器一致）
- `index.html` → `520CF7B46F21DD00B92693957870F64B`（本地 / 容器一致）

容器无 bind mount（前端产物烘焙进镜像），容器 Created `2026-10-29T01:59:36Z`（+08 09:59）。

链路实测（1.9 本机）：`GET http://127.0.0.1:18091/` → 200；`GET http://127.0.0.1:18091/ide/` → 200（nginx 反代 `location /ide/ → http://192.168.1.9:4224/ide/`，见 `deploy/wsl-frontend/nginx.conf` L46-48）。

---

## 5. datara 归档完整性 — PASS

- `docs/archive/2026-10-29-dbx-ide/` 共 **21 个文件**：
  - `views/__tests__/` **7 个**：`globalProjectContext` / `ideHistoryDrawer` / `ideHoverMenu` / `ideShortcuts` / `ideView` / `resultGrid` / `sqlCodeEditor`（均 `.contract.test.ts`）
  - `views/ide/` **14 个**：`CsvImportDialog.vue`、`IdeView.vue`、`ResultGrid.vue`、`SqlCodeEditor.vue`、`TableDataDialog.vue`、`csvParse.ts`、`__tests__/csvParse.test.ts`、`__tests__/ideUxV3.contract.test.ts`、`ddl/{DdlEditorView,DdlSnapshotMeta,SourceDdlEditor,StructuredDdlEditor}.vue`、`ddl/__tests__/ddlEditorView.contract.test.ts`、`ddl/objectSourceKinds.ts`
- `datara-newweb/src/views/ide/` **仅剩 `DbxIdeView.vue`**。
- git 侧为 `git mv` 语义：21 条 `R`（重命名）记录，其中 6 条带 `M`（归档前有内容改动）。
- 外部消费者检索（全仓 grep 归档文件路径/模块名）：命中的 33 个文件全部是**文档/证据/台账**（`docs/**`、`.codex-evidence/**`、`datara-newweb/COPY_LEDGER.md`、`datara-newweb/src/services/rebuild/CONTRACT_REGISTRY.md`、`aoci.code.txt`）；**代码侧消费者 0**。
  - 唯一命中的 `datara-web/src/router/routes.ts:52` 指向的是**另一独立旧应用** `datara-web/src/views/ide/IdeView.vue`（文件确实存在），与本次归档的 `datara-newweb` 文件无关。
- 现存路由仅指向新视图：`datara-newweb/src/router/routes.ts` L38 `import DbxIdeView`、L77 `{ path: '/ide', name: 'sql-ide', component: DbxIdeView }`。

---

## 6. 契约测试与类型检查 — PASS

本机 `datara-newweb`：

- `npx vitest run src/views/__tests__/dbxVariableBridge.contract.test.ts` → **4 tests passed**（`Test Files 1 passed (1)`，Duration 850ms）。断言覆盖：协议常量 `datara:variables`、脱敏 `***`、iframe 未挂载返回 `false`、按 origin 下发 payload。
- `npx vue-tsc --noEmit` → **EXIT=0**（无输出、无类型错误）。

---

## 7. 本机 git 状态核对

`git status --short` 中与本次 dbx IDE 集成**直接相关**的变更：

| 类别 | 路径 | 状态 |
| --- | --- | --- |
| 新增前端桥 | `datara-newweb/src/services/rebuild/dbxVariableBridge.ts` | `??` 未跟踪 |
| 新增契约测试 | `datara-newweb/src/views/__tests__/dbxVariableBridge.contract.test.ts` | `??` 未跟踪 |
| 新增宿主视图 | `datara-newweb/src/views/ide/DbxIdeView.vue`（`src/views/ide/` 整目录为未跟踪） | `??` 未跟踪 |
| 路由切换 | `datara-newweb/src/router/routes.ts`（`IdeView → DbxIdeView`，2 处） | `M` |
| 项目分段壳切换 | `datara-newweb/src/views/ProjectSegmentView.vue`（`ide` 段组件替换，2 处） | `M` |
| 反代 | `deploy/wsl-frontend/nginx.conf`（+18 行，`location /ide/` SSE 直通） | `M` |
| 后端同步适配 | `datara-backend/rebuild/datasource/dbx_sync.py` | `??` 未跟踪 |
| 后端接入 | `datara-backend/rebuild/api/app.py`（+129/-10，含 `_remove_datasource_from_dbx` 等 15 处 hunk） | `M` |
| 归档 git mv | `docs/archive/2026-10-29-dbx-ide/**`（21 文件，21 条 `R`） | `R`/`RM` |
| 部署资产 | `deploy/dbx/2026-10-29-baseline.md` | `??` 未跟踪 |
| 计划/报告 | `docs/plans/`（含本报告） | `??` 未跟踪 |

**与本次集成无关**的未提交变更（同 worktree 其他工作线遗留，未逐一追责）：`datara-backend/rebuild/{datasource/metadata.py,resources/*,runtime_node/service.py}`、`datara-newweb` 下大量 `views/**`、`components/DetailDrawer.vue`、`layouts/AppShell.vue`、`navigation/menu.ts`、`services/rebuild/{resourceApi,sqlIdeApi}.ts`、`package.json/lock`、`CodeEditor.vue`、`DepOpsSubNav.vue`、`ResourceScriptEditorDialog.vue`、`docs/increments/2026-10-28-*`、`docs/evidence/**` 等。

结论：本次集成引入的变更**全部处于未提交状态**，尚无任何提交固化。

---

## 8. 额外发现：跨产物语义不一致（不影响产物判定，但影响运行时可用性）

> 以下为静态读源发现，未做浏览器 E2E；两处均为 datara 与 dbx 两侧"协议形状"不一致，产物本身确实都已包含各自实现。

### 8.1 `bridge-ready` 握手通道不一致（中）

- dbx 侧：`useExternalVariableBridge.ts` 用 `window.parent?.postMessage({ type: "datara:bridge-ready" }, "*")`（postMessage）。
- datara 侧：`DbxIdeView.vue` L161 用 `window.addEventListener('datara:bridge-ready', onBridgeReady)`（DOM 事件监听）。
- `postMessage` 不会派发同名 DOM 事件，故 `onBridgeReady` 永不触发。影响面：仅 iframe 就绪晚于宿主变量拉取完成时的"补发兜底"失效（首次 `refreshVariables()` 后的即时下发不受影响）。

### 8.2 变量查找键口径不一致（高）

- datara 下发的条目形如 `{ scope: 'project'|'env'|'global', name: 'db_name', value, sensitive }`。
- dbx `lookupExternalVariable(key)` 的比较式是 `` `${entry.scope}.${entry.name}` === key ``，即期望 `"project.db_name"`。
- dbx `tryExternalSqlParameters` 传入的是 `parameter.name`（`sqlParameters.ts` 中 `name` 为 SQL 占位符里的裸名，如 `db_name`），不带 scope 前缀。
- 推论：查找恒不命中 → `tryExternalSqlParameters` 恒返回 `null` → 恒回落 `prepareSqlParameterDialog` 原生参数对话框。即"外部变量自动代入"链路当前不可用，SQL 执行仍走人工填参。
- 附带无害差异：dbx 侧 `ExternalVariableEntry` 未声明 `valueType/description/unavailableReason`，多余字段被忽略，不报错。

建议由实施线决定是否修正（本稽核未改动任何代码）：8.1 改为监听 `message` 事件并校验 `event.data.type`；8.2 统一键口径（dbx 侧按 `scope.name` 匹配，或 datara 侧补 scope 前缀）。

---

## 9. 验证局限

- 产物为压缩/混淆输出，无法按函数名（`externalVariables`、`tryExternalSqlParameters`）直接验证；已改用协议字符串（`datara:variables`、`datara:variables-ack`、`datara:bridge-ready`）作为等价证据。
- 未执行浏览器 E2E（iframe 实际渲染、变量下发与回执的可视化验证）；本报告仅覆盖产物与静态契约层面。
- dbx dist 未做逐文件 hash 与源码构建复现比对，仅以 mtime 顺序（源码 08:31/08:32 < dist 08:52）+ 协议字符串命中作为"补丁已烤入"证据。
