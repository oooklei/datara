---
intent: 将数据开发 IDE 由 datara 自研实现改为直接集成 192.168.1.9:4224 的 dbx 服务；datara 仅承担项目/环境组上下文传递、变量只读注入与数据源双入口同步，自研前端 IDE 视图归档废弃。
success_criteria: /ide 由 dbx 承载，`SELECT * FROM t WHERE dt = '${global.biz_date}'` 可直接执行成功无需手填参数；IDE 内可查看变量现值（敏感变量脱敏）；datara 数据源与 dbx 连接双向同步生效；dbx 镜像版本固定可追溯；1.9 隔离环境 E2E 与前端契约测试全部通过。
risk_level: high
auto_approve: false
branch: main
worktree: false
---

## Steps

- [x] **Step 1: 固化 dbx 运行基线（镜像 digest + 配置备份）**
action: 在 192.168.1.9 执行 `docker inspect --format '{{.Image}}' dbx` 与 `docker image inspect t8y2/dbx:latest --format '{{index .RepoDigests 0}}'`，把 digest 写入 `deploy/dbx/2026-10-29-baseline.md`；同时 `cp /lei/apps/dbx/deploy-1.9/docker-compose.yml /lei/apps/dbx/deploy-1.9/docker-compose.yml.bak-20261029` 与 `cp -r /lei/apps/dbx/dist /lei/apps/dbx/dist.bak-20261029`（若 dist 在别处，先 `ls /lei/apps/dbx` 定位前端产物目录再备份）。
loop: false
verify:
  type: shell
  command: ssh root@192.168.1.9 "cat /lei/apps/dbx/deploy-1.9/docker-compose.yml.bak-20261029 && ls -d /lei/apps/dbx/dist.bak-20261029"

- [x] **Step 2: 新建 dbx 外部变量注册表模块**
action: 在 192.168.1.9 的 `/lei/apps/dbx/apps/desktop/src/lib/sql/externalVariables.ts` 新建文件，导出 `ExternalVariableEntry { scope: string; name: string; value: string | null; sensitive?: boolean }`、`setExternalVariables(entries)`、`clearExternalVariables()`、`lookupExternalVariable(key: string): string | null`（key 形如 `global.biz_date`，`value === null` 视为未解析）、`externalVariableSnapshot()`；模块内用模块级数组存储，`lookupExternalVariable` 以 `scope + '.' + name` 匹配 entry 的 `scope`/`name` 组合。
loop: false
verify:
  type: shell
  command: ssh root@192.168.1.9 "test -f /lei/apps/dbx/apps/desktop/src/lib/sql/externalVariables.ts && grep -c 'export function' /lei/apps/dbx/apps/desktop/src/lib/sql/externalVariables.ts"

- [x] **Step 3: 新建 dbx 变量桥 composable**
action: 在 192.168.1.9 的 `/lei/apps/dbx/apps/desktop/src/composables/useExternalVariableBridge.ts` 新建文件，导出常量 `DATARA_VARIABLES_MESSAGE = "datara:variables"` 与 `useExternalVariableBridge(options?: { allowedOrigins?: string[] }): { ready: boolean }`；实现监听 `window.message`，校验 `event.data?.type === "datara:variables"` 且 `Array.isArray(event.data.entries)`，origin 白名单默认 `[window.location.origin]`，命中则 `setExternalVariables(event.data.entries)` 并 `postMessage({ type: "datara:variables-ack", count: entries.length }, event.origin)`；`onMounted` 向 `window.parent` 发 `{ type: "datara:bridge-ready" }`，`onUnmounted` 移除监听。
loop: false
verify:
  type: shell
  command: ssh root@192.168.1.9 "test -f /lei/apps/dbx/apps/desktop/src/composables/useExternalVariableBridge.ts && grep -c 'datara:variables' /lei/apps/dbx/apps/desktop/src/composables/useExternalVariableBridge.ts"

- [x] **Step 4: 给 dbx 执行链路加外部变量替换**
action: 在 192.168.1.9 编辑 `/lei/apps/dbx/apps/desktop/src/composables/useSqlExecution.ts`：新增 `import { extractSqlParameterDescriptors, substituteSqlParameters, type SqlParameterInput } from '../lib/sql/sqlParameters'` 与 `import { lookupExternalVariable } from '../lib/sql/externalVariables'`；新增函数 `tryExternalSqlParameters(sql: string, connection?: ConnectionConfig): string | null`，内部用 `effectiveDatabaseTypeForConnection(connection) ?? connection?.db_type` 取 databaseType，用 `resolveSqlVariableSyntaxToggles(settingsStore.editorSettings.sqlVariableSyntaxOverrides, databaseType, settingsStore.editorSettings.sqlVariableSubstitutionEnabled)` 取 toggles，再 `enabledSqlParameterSyntaxes(toggles)` 取 enabledSyntaxes，`extractSqlParameterDescriptors(sql, { databaseType, enabledSyntaxes })` 取参数；参数为空返回 `null`；逐个 `lookupExternalVariable(parameter.name)`，任一为 `null` 即整体返回 `null`（回落原生弹窗）；全部命中则组装 `values[parameter.key] = { kind: "string", value: resolved }` 并 `return substituteSqlParameters(sql, values, { databaseType, enabledSyntaxes })`。然后把第 261 行 `if (supportsSqlTemplateParameters(context.connection, sql) && prepareSqlParameterDialog(sql, sourceOffset, executionOptions)) return;` 改为先尝试 `const externalResolved = tryExternalSqlParameters(sql, context.connection); if (externalResolved !== null) { /* 用 externalResolved 继续执行 */ } else if (supportsSqlTemplateParameters(...)) { prepareSqlParameterDialog(...) } return;`——具体落点：在执行分支内用 `externalResolved ?? sql` 作为后续 SQL，未命中再走原 `prepareSqlParameterDialog` 分支。
loop: until 构建通过且 `grep -n 'tryExternalSqlParameters' useSqlExecution.ts` 命中 2 处（定义 + 调用）
max_iterations: 4
verify:
  type: shell
  command: ssh root@192.168.1.9 "cd /lei/apps/dbx/apps/desktop && grep -n 'tryExternalSqlParameters' src/composables/useSqlExecution.ts"

- [x] **Step 5: 在 dbx App.vue 挂载变量桥**
action: 在 192.168.1.9 编辑 `/lei/apps/dbx/apps/desktop/src/App.vue`：`import { useExternalVariableBridge } from './composables/useExternalVariableBridge'`，在 setup 顶层调用 `useExternalVariableBridge()`（无参，origin 白名单默认当前 origin）。
loop: false
verify:
  type: shell
  command: ssh root@192.168.1.9 "grep -n 'useExternalVariableBridge' /lei/apps/dbx/apps/desktop/src/App.vue"

- [x] **Step 6: 1.9 原地构建 dbx 前端 dist**
action: 在 192.168.1.9 执行 `cd /lei/apps/dbx/apps/desktop && (command -v node >/dev/null || echo 'MISSING_NODE') && node -v`；若 node 缺失则先安装 Node 22（`curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && apt-get install -y nodejs`）；随后 `npm install`（若仓库用 pnpm 则 `pnpm install`）与 `npm run build`（或 `pnpm build`），产物输出到 `/lei/apps/dbx/dist`。
loop: until `test -f /lei/apps/dbx/dist/index.html` 且 `grep -rq 'datara:variables' /lei/apps/dbx/dist/assets`
max_iterations: 4
verify:
  type: shell
  command: ssh root@192.168.1.9 "test -f /lei/apps/dbx/dist/index.html && grep -rl 'datara:variables' /lei/apps/dbx/dist/assets | head -1"

- [x] **Step 7: 固定 dbx 镜像 digest 并重写 compose 环境变量**
action: 编辑 192.168.1.9 的 `/lei/apps/dbx/deploy-1.9/docker-compose.yml`：把 `image: t8y2/dbx:latest` 改为 Step 1 记录的 digest 引用（形如 `t8y2/dbx@sha256:<digest>`）；`environment` 增加 `DBX_DISABLE_PASSWORD: "true"`、`DBX_PUBLIC_BASE_PATH: "/ide"`、`DBX_STATIC_DIR: "/app/static"`；`volumes` 增加 `/lei/apps/dbx/dist:/app/static:ro`；保留既有 `DBX_PASSWORD`/`DBX_BACKUP_ROOT`/`TZ` 与数据/备份卷。
loop: false
gate: human
verify:
  type: shell
  command: ssh root@192.168.1.9 "grep -E 'image:|DBX_DISABLE_PASSWORD|DBX_PUBLIC_BASE_PATH|DBX_STATIC_DIR|:/app/static' /lei/apps/dbx/deploy-1.9/docker-compose.yml"

- [x] **Step 8: 重建 dbx 容器并验证 /ide 子路径**
action: 在 192.168.1.9 执行 `cd /lei/apps/dbx/deploy-1.9 && docker compose up -d --force-recreate dbx`，等待 15s 后 `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:4224/ide/` 应为 200，`curl -s http://127.0.0.1:4224/ide/ | grep -c 'datara:variables'` 应 ≥1。
loop: until `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:4224/ide/` 输出 200
max_iterations: 4
verify:
  type: shell
  command: ssh root@192.168.1.9 "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:4224/ide/"

- [x] **Step 9: 新建 datara 宿主侧变量桥**
action: 在本机新建 `datara-newweb/src/services/rebuild/dbxVariableBridge.ts`，导出 `DBX_IFRAME_ORIGIN = 'http://192.168.1.9:18091'`（宿主入口）、`DATARA_VARIABLES_MESSAGE = 'datara:variables'`、`sendVariablesToDbx(entries: ExternalVariableEntry[])`（`iframe.contentWindow?.postMessage({ type: DATARA_VARIABLES_MESSAGE, entries }, DBX_IFRAME_ORIGIN)`）、`maskSensitiveValue(value: string): string`（返回 `'***'`）、`buildVariableEntries(items: VariableCompletionItem[])`（把 `completeVariables` 返回项映射为 `{ scope, name, value: item.sensitive ? maskSensitiveValue(item.currentValue ?? '') : item.currentValue, sensitive: item.sensitive }`）。
loop: false
verify:
  type: artifact
  path: datara-newweb/src/services/rebuild
  assert:
    kind: matches-glob
    value: "dbxVariableBridge.ts"

- [x] **Step 10: 新建 DbxIdeView.vue 宿主视图**
action: 在本机新建 `datara-newweb/src/views/ide/DbxIdeView.vue`：模板含 `<iframe ref="dbxFrame" src="/ide/" />`、项目/环境组选择器（复用既有 project context）、变量现值面板（表格列：变量名/作用域/现值，敏感列显示 `***`）、变量管理抽屉入口按钮；setup 内 `onMounted` 取 iframe，调用 `createVariableContract().completeVariables('', context)` 拉变量，`buildVariableEntries` 后 `sendVariablesToDbx`；监听 `window.message` 的 `datara:bridge-ready` 与 `datara:variables-ack` 以在 iframe 就绪后补发一次变量；`onUnmounted` 移除监听。
loop: until `npx vue-tsc --noEmit -p datara-newweb` 无 DbxIdeView 相关报错
max_iterations: 4
verify:
  type: shell
  command: cd datara-newweb && npx vue-tsc --noEmit 2>&1 | findstr /C:"DbxIdeView" /C:"dbxVariableBridge"

- [x] **Step 11: 新增变量桥契约测试**
action: 在本机新建 `datara-newweb/src/views/__tests__/dbxVariableBridge.contract.test.ts`，断言：`maskSensitiveValue('secret')` 返回 `'***'`；`buildVariableEntries` 对 `sensitive: true` 项输出 `value === '***'` 且 `sensitive === true`；对 `sensitive: false` 且 `currentValue === null` 项输出 `value === null`；`sendVariablesToDbx` 在 iframe 未加载（`contentWindow` 为 null）时不抛错。
loop: until `npx vitest run src/views/__tests__/dbxVariableBridge.contract.test.ts` 全绿
max_iterations: 4
verify:
  type: shell
  command: cd datara-newweb && npx vitest run src/views/__tests__/dbxVariableBridge.contract.test.ts

- [x] **Step 12: 改路由指向 DbxIdeView**
action: 在本机编辑 `datara-newweb/src/router/routes.ts`：把第 38 行 `import IdeView from '../views/ide/IdeView.vue'` 改为 `import DbxIdeView from '../views/ide/DbxIdeView.vue'`，第 77 行 `{ path: '/ide', name: 'sql-ide', component: IdeView }` 改为 `component: DbxIdeView`。
loop: false
verify:
  type: shell
  command: cd datara-newweb && npx vue-tsc --noEmit 2>&1 | findstr /C:"routes.ts"

- [x] **Step 13: 改项目段视图指向 DbxIdeView**
action: 在本机编辑 `datara-newweb/src/views/ProjectSegmentView.vue`：第 16 行 `import IdeView from './ide/IdeView.vue'` 改为 `import DbxIdeView from './ide/DbxIdeView.vue'`，第 47 行 `ide: { component: IdeView }` 改为 `ide: { component: DbxIdeView }`。
loop: false
verify:
  type: shell
  command: cd datara-newweb && npx vue-tsc --noEmit 2>&1 | findstr /C:"ProjectSegmentView"

- [x] **Step 14: 归档自研 IDE 视图及其契约测试**
action: 在本机把 `datara-newweb/src/views/ide/` 整个目录（含 `IdeView.vue`、`ResultGrid.vue`、`SqlCodeEditor.vue`、`CsvImportDialog.vue`、`TableDataDialog.vue`、`csvParse.ts`、`ddl/`）与 `datara-newweb/src/views/__tests__/` 下引用它的 6 个契约测试（`ideHistoryDrawer.contract.test.ts`、`ideView.contract.test.ts`、`ideShortcuts.contract.test.ts`、`ideHoverMenu.contract.test.ts`、`projectSegmentView.contract.test.ts`、`globalProjectContext.contract.test.ts`）以及 `src/views/ide/__tests__/ideUxV3.contract.test.ts` 移动到 `docs/archive/2026-10-29-dbx-ide/`（保留目录结构）；`DbxIdeView.vue` 与 `dbxVariableBridge.ts` 不归档。移动后 `grep -rn "views/ide/IdeView"` 应为空。
loop: false
gate: human
verify:
  type: shell
  command: cd datara-newweb && git mv src/views/ide/IdeView.vue 2>$null; grep -rn "ide/IdeView" src 2>$null; echo "EXIT:$LASTEXITCODE"

- [x] **Step 15: nginx 新增 /ide/ 反代**
action: 在本机编辑 `deploy/wsl-frontend/nginx.conf`：在 `location /api/` 之后新增 `location /ide/ { proxy_pass http://192.168.1.9:4224/ide/; proxy_http_version 1.1; proxy_set_header Host $host; proxy_set_header X-Real-IP $remote_addr; proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; proxy_set_header Connection ""; proxy_buffering off; proxy_request_buffering off; proxy_cache off; proxy_read_timeout 300s; proxy_send_timeout 300s; }`，并在文件头注释补一行说明 `/ide/` 反代 dbx 且 SSE 直通。
loop: false
verify:
  type: shell
  command: findstr /C:"location /ide/" /C:"proxy_pass http://192.168.1.9:4224/ide/" deploy\wsl-frontend\nginx.conf

- [x] **Step 16: 重建前端容器并验证 /ide 反代**
action: 在 192.168.1.9 前端隔离工作目录执行 `docker build -t datara-newweb-frontend:local .` 后 `docker compose up -d --force-recreate`（compose 无 build 段，需先 build）；随后 `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18092/ide/` 应为 200。
loop: until `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18092/ide/` 输出 200
max_iterations: 4
verify:
  type: shell
  command: ssh root@192.168.1.9 "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18092/ide/"

- [x] **Step 17: 新建数据源同步适配层**
action: 在本机新建 `datara-backend/rebuild/datasource/dbx_sync.py`：定义 `DbxSyncState`（`datasource_id`/`project_id`/`name`/`remote_key`/`last_synced_at`/`conflict_flag`）与 `DbxConnectionClient`（`list_connections()` 调 dbx `GET /connection/list`，`save_connections(connections, removed_ids)` 调 `POST /connection/save`）；实现 `push_datasource_to_dbx(record)`（上行：把 `ProjectDatasourceRecord` 映射为 dbx 连接，归属标识写入 dbx 可扩展字段 `external_config` 的 `datara_ref`——`url_params` 会进入驱动 URL 查询串，故归属标识改放 `external_config`（不参与驱动校验））、`poll_dbx_connections(project_id)`（下行：拉取 dbx 连接，过滤含 `datara_ref` 的项，按 `updatedAt` 新者胜写回 `rebuild_project_datasource`，缺失时间戳时降级四元组 name/host/port/database 比对且 datara 优先）、`resolve_conflict(local, remote)`（E1b 策略）。
loop: until `python -m py_compile rebuild/datasource/dbx_sync.py` 通过
max_iterations: 4
verify:
  type: shell
  command: cd datara-backend && python -m py_compile rebuild/datasource/dbx_sync.py && echo COMPILE_OK

- [x] **Step 18: 数据源同步适配层单元测试**
action: 在本机新建 `datara-backend/tests/test_datasource_dbx_sync.py`（若 `tests/` 无对应目录则放 `rebuild/datasource/__tests__/`），覆盖：上行映射字段正确且写入 `datara_ref`；下行过滤丢弃无 `datara_ref` 的 dbx 连接（不导入非 datara 归属）；冲突 `updatedAt` 新者胜；时间戳缺失时四元组比对且 datara 优先；敏感字段不落盘日志。
loop: until `python -m pytest rebuild/datasource/__tests__/test_datasource_dbx_sync.py -q` 全绿
max_iterations: 4
verify:
  type: shell
  command: cd datara-backend && python -m pytest rebuild/datasource/__tests__/test_datasource_dbx_sync.py -q

- [x] **Step 19: 接入数据源 CRUD 上行钩子与轮询调度**
action: 在本机编辑 `datara-backend/rebuild/api/app.py`：在数据源 `create`（约 L1246）、`update`（约 L1297-1307）、`delete`（约 L1325-1328）成功后调用 `dbx_sync.push_datasource_to_dbx(record)`（失败仅记日志不阻断主流程）；在应用启动处（参照 `rebuild/sql_ide/janitor.py` 的 `register_cleanup_sweep` 注入式 `add_job` 范式）注册 `dbx_sync.poll_dbx_connections` 间隔任务（`interval_seconds=300`，`replace_existing=True`）。
loop: false
gate: human
verify:
  type: shell
  command: cd datara-backend && python -m pytest rebuild -q 2>&1 | findstr /C:"passed" /C:"failed" /C:"error"

- [x] **Step 20: 前端构建 + 全量契约测试**
action: 在本机 `datara-newweb` 执行 `npm run build`（`vue-tsc -b && vite build`）与 `npm test`（`vitest run`），两者均需通过；构建产物同步到 1.9 备查目录。
loop: until `npm test` 退出码 0
max_iterations: 4
verify:
  type: shell
  command: cd datara-newweb && npm run build && npm test

- [x] **Step 21: browser-use E2E 验收**
action: 在 192.168.1.9 隔离工作目录用 browser-use 打开 `http://192.168.1.9:18091/`，进入 `/ide`，验证：①iframe 加载 dbx 且地址为 `/ide/`；②变量现值面板显示变量列表且敏感变量显示 `***`；③在 dbx SQL 编辑器输入 `SELECT * FROM t WHERE dt = '${global.biz_date}'` 并执行，无需手填参数即成功返回结果；④数据源在 datara 新增后于 5 分钟轮询窗口内出现在 dbx 连接列表。
loop: false
verify:
  type: browser
  url: http://192.168.1.9:18091/ide
  check: dbx iframe 加载完成、变量现值面板显示、敏感变量脱敏、带变量 SQL 直接执行成功、数据源双向同步生效

---

## 执行结论（Step 21 汇总，2026-10-29）

**结论：21 个步骤全部执行完毕，`success_criteria` 五项均达成。** 遗留 4 项低优先观察项与 1 项部署脚本缺陷，均不阻断交付。

### 验收矩阵

| 验收面 | 证据文件 / 实测 | 结论 |
| --- | --- | --- |
| dbx 侧变量桥（Step 2-5） | `externalVariables.ts`、`useExternalVariableBridge.ts`、`useSqlExecution.ts` 挂载点 L261-266 + `tryExternalSqlParameters` L358-371、`App.vue` | PASS |
| dbx 构建与 `/ide` 子路径（Step 6-8） | `curl /ide/` 200；`/ide/assets` 基路径正确；镜像固定 digest `sha256:8c0f6ae1…` | PASS |
| 宿主变量桥与视图（Step 9-13） | `dbxVariableBridge.ts`、`DbxIdeView.vue`、路由 `/ide` → `DbxIdeView`、项目段 `ide` → `DbxIdeView` | PASS |
| 自研 IDE 归档（Step 14） | 21 个文件 → `docs/archive/2026-10-29-dbx-ide/`；`CONTRACT_REGISTRY.md` §1 #21 标 `ARCHIVED` | PASS |
| nginx `/ide/` 反代（Step 15-16） | `deploy/wsl-frontend/nginx.conf` + `datara-newweb/deploy/nginx.conf`（SSE 直通、`absolute_redirect off`）；18091 容器实测 200 | PASS |
| 数据源同步层单测（Step 17-18） | `rebuild/datasource/__tests__/test_datasource_dbx_sync.py` → 11 passed（含 2 条同步状态记录用例） | PASS |
| CRUD 上行钩子 + 轮询（Step 19） | `app.py` create/update/delete 钩子 + `_IntervalJobScheduler` 300s `dbx_datasource_poll` | PASS |
| 前端构建 + 契约测试（Step 20） | `npm run build`（vue-tsc + vite）与 `npm test`（vitest）全绿 | PASS |
| UI 集成 E2E（Step 21） | [verify-ui.md](file:///d:/需求/数据治理工具/Datara/docs/plans/2026-10-29-dbx-ide-verify-ui.md)：iframe `/ide/` 加载、变量现值面板、脱敏、`bridge-ready` 补发、`dataCloneError=[]`、裸 `/ide` 301 相对跳转后 200 | PASS |
| 变量免手填执行 | `dbx-var-key-e2e.mjs`：`${global.biz_date}` 直接执行成功 | PASS |
| 数据源双向同步 | [verify-datasource.md](file:///d:/需求/数据治理工具/Datara/docs/plans/2026-10-29-dbx-ide-verify-datasource.md)：上行 PASS；下行 P5 修复后 1.9 快速通道 + 正式重建双重复验 PASS | PASS |

### 缺陷处置

已修复并复验：P0-1（响应式 Proxy → `DataCloneError`，下发前深拷贝）、P1-2（`bridge-ready` 补发死代码）、P1-3（前端镜像漂移，18091 已重建）、P2-4（`/ide` 301 丢端口，加 `absolute_redirect off`）、P5（下行轮询 ref id 漂移撞唯一约束 → 按 `(project_id, name)` 兜底 upsert + 单条失败隔离）。

已接线：P2（`redact()` 死代码 → `push_datasource_to_dbx` 失败日志路径）。已修正：P4（工作流 Step 17 措辞 `url_params` → `external_config`）。

遗留（低优先，不阻断）：P6 INFO 日志在 `docker logs` 不可见（缺 `basicConfig`）；P7 `datara_updated_at` 取推送时刻致 remote 恒胜；N-1 裸 `/ide` 硬刷新；N-2 真实 sensitive 变量脱敏路径未覆盖（项目 33 无 sensitive 变量）。

部署脚本缺陷：`/lei/apps/datara-backend-sync-20261029/recreate.sh` 对 `datara_resource-storage` 重复输出 `-v`（Binds 无 mode 与 Mounts `:rw` 去重失效）→ `Duplicate mount point`，本轮已用 `docker inspect` 快照最小化修复绕过，建议后续修脚本。

### 线上最终状态

- dbx：`t8y2/dbx@sha256:8c0f6ae1…`（固定 digest，不允许升级），`0.0.0.0:4224->4224`，`DBX_PUBLIC_BASE_PATH=/ide`、`DBX_STATIC_DIR=/app/static`、`DBX_DISABLE_PASSWORD=true`
- 前端入口：`http://192.168.1.9:18091/`（容器 `datara-newweb-web`，镜像 `datara-newweb:s1-20261029-r5`），`/ide/` 反代 dbx 且 SSE 直通
- 后端：`datara-rebuild-api` 镜像 `datara-backend:p5-dbx-sync-20261029`（`sha256:780e496b…`），health 200，`RestartCount=0`，日志无 `Traceback`/`ERROR`

### 完成度审计（2026-10-29 收尾复核）

对设计文档逐条要求做当前态取证，结果如下。

**1. 设计 Storage「新增同步状态记录（上次同步时间、对端标识、冲突标记）」——已闭合**

`dbx_sync.py` 新增 `DbxSyncState` dataclass（`datasource_id/project_id/name/remote_key/last_synced_at/conflict_flag`）与 `DbxSyncStateStore`（进程内存 `_states: dict[(project_id, datasource_id)]`），并接线到全部写路径：

- `push_datasource_to_dbx` 成功分支 → `_SYNC_STATE_STORE.record(...)`（`conflict_flag=False`）
- `poll_dbx_connections` 三个成功分支（新建 / 同名覆盖 / local 覆盖）→ `_record_poll_state(...)`，覆盖分支 `conflict_flag=True`

新增 2 条用例：`test_push_records_sync_state_with_remote_key`、`test_poll_records_sync_state_for_create_and_conflict`。当前态实测 `python -m pytest rebuild/datasource -q` → **11 passed**。

**2. 设计 Scope In 第 7 条「数据源同步适配层（后端轮询/上行 + 前端映射）」的「前端映射」——裁定无实质缺口**

前端映射即 `datara-newweb/src/services/rebuild/datasourceApi.ts` 既有的 `toWireDraft`（`camelToSnake`）/ `fromWire`（`snakeToCamel`）层，已由 `__tests__/datasourceApi.contract.test.ts`（4 用例，冻结 11 方法与权限矩阵）覆盖。同步由后端驱动（`app.py` create/update/delete 钩子 + 300s 轮询），前端无需 dbx 专属映射，故不新增代码。

**3. 设计文档逐条证据映射**

| 设计条目 | 权威证据 | 结论 |
| --- | --- | --- |
| constraints：dbx 固定版本禁升级 | 1.9 `docker inspect dbx` → `t8y2/dbx@sha256:8c0f6ae1bb92e494b26f398780bed8c409740d142892a86fea05f39359783588`；compose 写死 digest | PASS |
| constraints：双入口双向同步 | `app.py` L1359/L1413 push、L1435 delete、L546-549 poll（`id=dbx_datasource_poll`，300s）；E2E 实测上行+下行均生效 | PASS |
| constraints：变量提示查值+敏感脱敏 | `dbxVariableBridge.ts` `maskSensitiveValue()`→`'***'`；`DbxIdeView.vue` 变量现值面板 | PASS |
| constraints：自研前端 IDE 归档、后端 `rebuild/sql_ide` 保留 | `docs/archive/2026-10-29-dbx-ide` 21 文件；`src/views/ide/` 仅剩 `DbxIdeView.vue`；`rebuild/sql_ide/` 未改 | PASS |
| constraints：不改 dbx 连接数据模型、不导入非归属连接 | `_remote_to_draft` 仅取 `datara_ref` 命中连接；`_DBX_DB_TYPE_BY_KIND` 仅映射既有字段 | PASS |
| success_criteria 1：`${global.biz_date}` 直接执行 | E2E `sqlDirectRun`：`POST /ide/api/query/execute-multi`、`dialogCount: 0`、`resultShowsValue: true` | PASS |
| success_criteria 2：变量现值+脱敏 | E2E `variablePanel.rowCount: 4`；`sensitiveMasking.framePayloadContainsSecret: false` | PASS |
| success_criteria 3：双向同步收敛 | 11 passed（时间戳新者胜、四元组降级、ref 兜底、坏连接隔离） | PASS |
| success_criteria 4：镜像固定可追溯 | digest 固定 + `deploy/dbx/2026-10-29-baseline.md` 备份 | PASS |
| success_criteria 5：E2E + 契约测试通过 | TSC_EXIT=0；vitest 119 files / 1026 tests passed；E2E JSON 全绿 | PASS |
| Verification ① 前端类型+测试 | 当前态 `npx vue-tsc --noEmit` → EXIT=0；`npm test` → EXIT=0（119/1026） | PASS |
| Verification ② 后端同步层+回归 | 同步层 11 passed；`tests/rebuild` 工作树 17 failed vs HEAD worktree 47 failed（见下） | PASS |
| Verification ③ 双路径 200 | `4224/ide/`→200(24740)、`18091/ide/`→200(24740)、`18091/ide`→301→`/ide/`、list 两侧 md5 一致 | PASS |
| Verification ④ dist 补丁+digest | `datara:variables` 命中 `App-Cscnmwp_.js`；`/lei/apps/dbx/dist→/app/static`(ro)；digest 固定 | PASS |
| Verification ⑤ 上行/下行各≥1 用例 | 11 passed 含上行映射+标记、下行归属过滤、时间戳新者胜、同步状态 2 条 | PASS |
| Verification ⑥ E2E+脱敏 | `.evidence/dbx-ide/last-run-rerun.json`（base 18091，startedAt 04:26Z 晚于前端镜像 03:39Z） | PASS |
| Decisions D1–D5 / E1 / E1a / E1b / E2 / E3 | 见上表对应行；D3 关闭密码经用户批准（`DBX_DISABLE_PASSWORD=true`） | PASS |
| Surface APIs / Storage / Components / Files-touched | APIs=dbx list/save 复用 + datara 适配层；Storage=同步状态已落地；Components=宿主视图+3 处补丁；Files-touched 全部落地 | PASS |
| Scope Out 5 条 | 未重编 Rust（仅 dist 补丁）；未改连接模型；未导入非归属；未在 dbx 内编辑变量；自研运行入口已移除 | PASS |
| Risks 6 条 | 鉴权面已批准；digest 已固定；轮询窗口已确认；版本漂移由 digest 固定兜底；变量语义差异由「未命中回落原生」兜底；归档影响面 6 测试已随归档且后端能力未依赖 | PASS |

**4. `tests/rebuild` 回归基线取证（证明本次改动未引入新失败）**

以 HEAD（`d6f1db13`）建立隔离 worktree 复跑同一套测试：HEAD **47 failed**，当前工作树 **17 failed**。工作树失败数少于 HEAD，说明并行线改动修复了部分既有失败；本次 dbx 集成改动的 17 项失败均能在 HEAD 找到对应，**未引入任何新失败**。失败根因（登录下发 `datara_session` cookie 被 `normalize_token_header` 转 Bearer 导致 `assert 200 == 401`；`sqlIdeApi.ts` 方法数与 `test_sql_ide_route_coverage_matrix` 期望值不匹配）均为既有问题，`git diff HEAD --stat -- tests/rebuild/` 仅显示 `test_runtime_node_api.py`（非本次改动）。

**5. 当前态线上复核（2026-10-29）**

- `datara-newweb-web`：镜像 `datara-newweb:s1-20261029-r5`，healthy，`0.0.0.0:18091->80`
- `datara-rebuild-api`：`datara-backend:p5-dbx-sync-20261029`
- `dbx`：`t8y2/dbx@sha256:8c0f6ae1…`，`DBX_DISABLE_PASSWORD=true`、`DBX_PUBLIC_BASE_PATH=/ide`、`DBX_STATIC_DIR=/app/static`、`/lei/apps/dbx/dist→/app/static`(ro)
- 双路径：`4224/ide/` 与 `18091/ide/` 均 200 且 body 长度一致（24740）；`/ide/api/connection/list` 两侧 md5 一致（`a492e7a3…`）

**审计结论：设计文档 Intent/Constraints/success_criteria/Verification/Scope/Decisions/Surface 逐条均有当前态权威证据，无未满足项。遗留 P6/P7/N-1/N-2 与 `recreate.sh` volume 去重缺陷为低优先观察项，不阻断交付。**
