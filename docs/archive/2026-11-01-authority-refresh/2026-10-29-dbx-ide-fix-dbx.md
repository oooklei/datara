# dbx 外部变量查找键口径验证 + 判定报告

- 日期：2026-10-29
- 角色：dbx 侧变量桥验证 + 重建 agent
- 任务：判定「datara 下发 `{scope, name}` 与 dbx `lookupExternalVariable` 的 `${scope}.${name}` 口径是否一致」，不一致则修复并重建 dbx 容器
- **判定结论：非缺陷（误判）。键口径一致，未改动 dbx 代码，未重建容器。**

---

## 1. 结论

产物稽核 agent 报告的「语义不一致」为**误判**。其前提「`tryExternalSqlParameters` 传的是裸 `parameter.name`」不成立：

- dbx 在 shell 语法 `${...}` 下取的是 `${` 与 `}` 之间的**完整内容**，因此 `${global.biz_date}` 的 `parameter.name` = `"global.biz_date"`（**含 scope 前缀**），不是裸名 `biz_date`。
- datara 下发 `{scope: "global", name: "biz_date"}`，dbx 侧 `${entry.scope}.${entry.name}` = `"global.biz_date"`。
- 两者**逐字符相等 → 命中**，替换链路本身正确。

UI 验收 agent 的对照实验（手动灌快照后 SQL 直执行无弹窗）与本机端到端复测结论一致，进一步佐证非缺陷。

---

## 2. 证据链（源码绑定）

### 2.1 dbx 侧：`parameter.name` 在 shell 语法下含 scope 前缀

文件：`192.168.1.9:/lei/apps/dbx/apps/desktop/src/lib/sql/sqlParameters.ts`

- 参数名正则允许点号分段（即允许 `scope.name` 形态）：
  ```ts
  // L64
  const PARAMETER_NAME_RE = /^[\p{L}_][\p{L}\p{N}_]*(?:\.[\p{L}_][\p{L}\p{N}_]*)*$/u;
  ```
- shell 占位符解析把 `${`…`}` 之间的内容整体作为 `name`，并令 `key = name`：
  ```ts
  // tryReadQuotedBracedPlaceholder（引号内）L1630-1641
  const name = sql.slice(nameStart, closeBrace).trim();
  if (!PARAMETER_NAME_RE.test(name)) return null;
  ...
  return { key: name, name, syntax, token: sql.slice(start, end), start, end };
  ```
- 引号外/片段形态同口径（`collectEmbeddedQuotedBracedPlaceholders` L1670-1684）：
  ```ts
  const name = sql.slice(i + 2, closeBrace).trim();
  ...
  occurrences.push({ key: name, name, syntax, token: ..., start: i, end: closeBrace + 1, replacement: "string-fragment" });
  ```
- `extractSqlParameterDescriptors`（L171-205）原样透传 `name: occurrence.name`、`key: occurrence.key`。

**推导**：SQL `SELECT * FROM t WHERE dt = '${global.biz_date}'`
→ 取 `${` 后、`}` 前内容 = `global.biz_date`
→ `SqlParameterDescriptor.name = "global.biz_date"`。

### 2.2 dbx 侧：`lookupExternalVariable` 比较 `${scope}.${name}`

文件：`192.168.1.9:/lei/apps/dbx/apps/desktop/src/lib/sql/externalVariables.ts` L18-22

```ts
export function lookupExternalVariable(key: string): string | null {
  const match = externalVariables.find((entry) => `${entry.scope}.${entry.name}` === key);
  if (!match || match.value === null) return null;
  return match.value;
}
```

调用点：`composables/useSqlExecution.ts` L358-371

```ts
const resolved = lookupExternalVariable(parameter.name);   // ← 传的是 "global.biz_date"
if (resolved === null) return null;
values[parameter.key] = { kind: "string", value: resolved };
```

即 `key = "global.biz_date"`，比较式 `${entry.scope}.${entry.name}`。

### 2.3 datara 侧：`name` 为裸名、`scope` 独立字段

文件：本机 `datara-backend/rebuild/variables/service.py`

- 变量名正则**不允许点号**（裸名）：
  ```python
  # L37
  _NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
  ```
- `complete()` 返回体中 `name` 取裸名、`scope` 取独立字段：
  ```python
  # L506-516
  items.append({
      "scope": item.scope,
      "name": item.name,          # 裸名，如 "biz_date"
      "value_type": item.value_type,
      "current_value": redact_sensitive_value(item.value, item.sensitive),
      "sensitive": item.sensitive,
      "description": item.description,
  })
  ```
- 目录按裸名聚合（`catalog()` L331：`catalog.setdefault(item.name, item)`），`ResolvedVariable.name` 亦为裸名。

文件：本机 `datara-newweb/src/services/rebuild/dbxVariableBridge.ts` L40-50

```ts
export function buildVariableEntries(items: VariableCompletionItem[]): ExternalVariableEntry[] {
  return items.map((item) => ({
    scope: item.scope,     // "global"
    name: item.name,       // "biz_date"
    ...
  }));
}
```

**推导**：datara 下发 `{scope: "global", name: "biz_date"}`
→ dbx `${entry.scope}.${entry.name}` = `"global.biz_date"`
→ 与 `parameter.name` 相等 → **命中**。

### 2.4 部署产物核对（192.168.1.9）

- `dist/index.html` 资源路径为 `/ide/assets/index-CE61-HFP.js`（符合 `/ide/assets/...` 约定）。
- 产物含 `datara:variables` 处理逻辑（`dist/assets/App-Cscnmwp_.js`），其查找实现与源码一致：
  ```js
  function lj(e){let t=sj.find(t=>`${t.scope}.${t.name}`===e);return!t||t.value===null?null:t.value}
  ```
- 消息处理器（同源校验 + 快照写入 + 回 ack）：
  ```js
  if(e.data?.type!==`datara:variables`||!Array.isArray(e.data.entries)||!r.includes(e.origin))return;
  let t=e.data.entries; cj(t), n.value=!0,
  e.source?.postMessage({type:`datara:variables-ack`,count:t.length},{targetOrigin:e.origin})
  ```
- 容器状态：`dbx` 容器 `Up`，`0.0.0.0:4224->4224`，`curl http://127.0.0.1:4224/ide/` 返回 `<title>DBX</title>`。

---

## 3. 端到端验证（关键）

脚本：本机 `datara-newweb/deploy/dbx-var-key-e2e.mjs`（新增，直连 dbx 容器，不经 datara 宿主）
目标：`http://192.168.1.9:4224/ide/`
载荷：与 datara 同形 `{scope: "global", name: "biz_date", valueType: "date", value: "2026-10-28", sensitive: false}`

实测结果（`.evidence/dbx-var-key/`，2026-10-29T03:07:39Z）：

| 检查项 | 结果 |
| --- | --- |
| 打开 `/ide/` | HTTP 200 |
| 注入后 dbx 回 ack | `datara:variables-ack` count=1 ✅ |
| 编辑器输入 | `SELECT * FROM t WHERE dt = '${global.biz_date}'` |
| 执行方式 | Ctrl+Enter |
| 原生参数弹窗 | `dialogCount = 0`，`mentionsParameter = false` ✅（无弹窗） |
| execute-multi 请求体 | `"sql":"SELECT * FROM t WHERE dt = '2026-10-28' LIMIT 100;"` ✅ |
| 请求体含字面值 `2026-10-28` | true ✅ |
| 请求体含占位符 `global.biz_date` | false ✅ |

**结论**：dbx 收到 `{scope:"global", name:"biz_date"}` 后，`${global.biz_date}` 被替换为 `2026-10-28` 并实际下发执行，无弹窗。键口径一致，替换链路端到端可用。

---

## 4. 附带发现（另一处、真实缺陷，不在本次口径范围，未修）

既有 UI 验收证据（`datara-newweb/.evidence/dbx-ide/last-run.json`）中，**干净状态复测**（不手动灌快照、仅依赖宿主自动下发）出现了原生参数弹窗：

- `sqlProbeCleanState.dialogProbe.dialogCount = 2`，`mentionsParameter = true`，弹窗文本含 `global.biz_date` / `${name}`。
- 同时 `variableBridge.ackCount = 0`（宿主自动下发未获 ack），控制台出现 `DataCloneError: ... could not be cloned`（宿主 bundle `index-DfW55u49.js`）。

根因（源码绑定，本机 `datara-newweb/src/views/ide/DbxIdeView.vue`）：

```ts
// L96
const entries = ref<ExternalVariableEntry[]>([])   // ← ref 包裹 → entries.value 为 Vue 响应式 Proxy
// L137
entries.value = buildVariableEntries(items)
// L144 / L155
sendVariablesToDbx(entries.value)                   // ← 把 Proxy 交给 postMessage
```

`dbxVariableBridge.ts` L56 `target.postMessage({ type, entries }, origin)` 对 Proxy 做结构化克隆 → **DataCloneError**，宿主自动下发**恒失败**，dbx 快照始终为空 → 真实用户路径必然回落参数弹窗。

判定：这是**宿主侧缺陷**（`entries.value` 应为 `toRaw`/浅拷贝后的纯对象），与 dbx 键口径无关。按任务约束「非缺陷不改 dbx 代码」，此处**仅上报、不修改**，建议由宿主侧（datara-newweb）线修复：`sendVariablesToDbx([...entries.value].map((e) => ({ ...e })))` 或在 `buildVariableEntries` 出口统一去 Proxy。

---

## 5. 未做改动清单

- 未修改 dbx 任何源码（`externalVariables.ts` / `useSqlExecution.ts` / `sqlParameters.ts` 均保持原样）。
- 未重新构建 dbx、未重建 dbx 容器（现有 `dist` 与容器已满足口径，无需变更）。
- 未触碰 dbx 数据卷 `/lei/apps/dbx/data`。
- 新增文件：`datara-newweb/deploy/dbx-var-key-e2e.mjs`（端到端验证脚本，任务要求产出）。
- 产出证据：`datara-newweb/.evidence/dbx-var-key/`（JSON + `after-run.png`）。

---

## 6. 复核指引

- 复核键口径：`sqlParameters.ts` L64 正则 + L1630/L1670 `name` 提取；`externalVariables.ts` L19 比较式；`service.py` L37/L509 裸名。
- 复核端到端：`cd datara-newweb && node deploy/dbx-var-key-e2e.mjs --base http://192.168.1.9:4224 --out ./.evidence/dbx-var-key`。
- 复核宿主缺陷：`src/views/ide/DbxIdeView.vue` L96/L144/L155 + `src/services/rebuild/dbxVariableBridge.ts` L56。
