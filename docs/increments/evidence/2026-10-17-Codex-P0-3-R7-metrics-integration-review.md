# Codex P0-3 R7 Metrics 集成复核

- 日期：2026-10-17
- 复核范围：canonical main 中 c0f8ee5 之后的 R7 metrics 实现、测试和现存验证 evidence。
- 复核方式：只读检查提交、源码、测试及 evidence；本次未运行测试或修改实现。
- 建议结论：**六端点实现 + SQLite/Playwright 联调窄口径 PASS；项目授权隔离、真实统计数据生产链及迁移证据仍 RED/待裁定。**

## 1. 窄口径已验证

本节判断限于冻结 FE 契约对应的六个查询端点、应用装配和本地演示环境联调，不代表 R7 生产数据闭环已经完成。

### 1.1 提交链与交付物

在本次复核基线 HEAD `280b00c` 中可见以下提交链：

| Commit | 交付 | 复核锚点 |
|---|---|---|
| `15a8d99` | 六张 metrics 统计/关联表模型 | `datara-backend/rebuild/metrics/models.py` |
| `6cfb85f` | 时间窗查询仓储及 kind 校验 | `datara-backend/rebuild/metrics/repository.py` |
| `60cfa50` | 六个冻结契约 POST 端点、统一包络及 token 鉴权 | `datara-backend/rebuild/metrics/api.py` |
| `d3d83bc` | app factory 建表装配及 router 挂载 | `datara-backend/rebuild/api/app.py` |
| `52a46a8` | 六端点契约、过滤、鉴权测试 | `datara-backend/tests/rebuild/test_r7_metrics_api.py` |
| `0579d43` / `c7026e1` | Playwright E2E 网络/步骤 JSON 与整页截图 | `docs/increments/evidence/R7/r7-be-e2e-20261017.json`、`r7-be-e2e-20261017.png` |
| `4c4c0ab` | P0-3 执行记录 | `docs/increments/evidence/R7/trae-r7-e2e-20261017.txt` |
| `f485177` | E2E Vite 环境重新预构建记录 | `docs/increments/evidence/R7/trae-r7-vite-dev-20261017.log` |

### 1.2 六端点与冻结契约

- API 在 `datara-backend/rebuild/metrics/api.py:25-68` 声明 `from` 字段别名、统一时间窗入参、token header 优先/Bearer 兼容、`{code,msg,data}` 成功/错误包络。
- 六个 POST 路由分别位于 `api.py:70-149`：`workflow-result-stats`、`task-instance-data-stats`、`task-data-stat-segments`、`task-data-error-samples`、`quality-rule-links`、`lineage-writebacks`。后者接受 `sql|sync|workflow|all`，非法 kind 归为 4001。
- `datara-backend/rebuild/metrics/repository.py:38-52` 检查 from/to 必填、起止顺序、offset 和 limit；`:64-180` 提供对应六类时间窗分页查询。统计 MetricValue JSON 按原结构解码返回，未重新推导 `known/estimated`。
- app factory 的导入、建表列表和 lifespan 初始化可见于 `datara-backend/rebuild/api/app.py:33-41,129-151`；metrics router 挂载于 `app.py:717-720`，路径前缀为 `/api/v1/rebuild/metrics`。

### 1.3 契约测试及联调证据

- `datara-backend/tests/rebuild/test_r7_metrics_api.py:77-112` 对六条路由逐一发请求并断言 200、成功包络及代表字段；覆盖 MetricValue 未知/估算标记透传。
- 同文件 `:115-136` 覆盖 lineage kind 过滤、非法 kind 与倒置时间窗；`:139-153` 覆盖匿名 401 和 Bearer 兼容。
- `docs/increments/evidence/R7/trae-r7-e2e-20261017.txt:19-47` 记录实施方报告的 BE 全量 pytest `318 passed, 1 xfailed`、FE 定向契约 `11 passed`，以及登录后六端点 200、表格行数和错误窗口冒烟结果。本次为只读复核，没有重新运行这些测试。
- `docs/increments/evidence/R7/r7-be-e2e-20261017.json:1-157` 保存登录、六个请求、响应状态、步骤和行数断言；整页截图由同目录 `r7-be-e2e-20261017.png` 保存。执行说明 `trae-r7-e2e-20261017.txt:29-46,59-63` 明确说明使用本地 SQLite、注入演示数据及 Playwright headless Chromium，并披露内嵌 WebView 缓存故障及替代方式。

据此，**六查询接口的冻结契约接线、app factory 路由可达性以及 SQLite/Playwright 本地集成演示有可追溯实现和 evidence**。这支持窄口径 P0-3 PASS。

## 2. 全域/生产 GREEN 缺口

### 2.1 项目级授权隔离未实现（阻断全域 GREEN）

metrics API 的 `principal` 在 `datara-backend/rebuild/metrics/api.py:43-49` 仅检查 token 是否存在于 `active_tokens` 并调用 token verify；`window_guard` 在 `:57-65` 没有执行 project membership、项目角色或资源范围授权。六张 metrics 模型在 `datara-backend/rebuild/metrics/models.py` 未定义 `project_id`。FE `datara-web/src/services/rebuild/metricsApi.ts` 的 `TimeWindowQuery` 仅含 `from/to/offset/limit`，无 projectId。

既有 handoff Q1 明确记载：“FE 注入当前 projectId，所有资源/依赖/统计/观摩读写遵守项目授权”（`docs/handoff/2026-10-16-并行协作分工.md:1253-1258`，其中 Q1 在 `:1256`）。当前六端点以时间窗查询全表，不可据此证明租户隔离；持有任一有效 token 的账户目前能读取相应时间窗内的统计行。

**关闭条件**：补齐 projectId/项目归属模型、成员与角色授权、查询强制项目过滤，以及跨项目拒绝测试；或者由治理责任方给出明确范围裁定，说明为何 R7 统计豁免该项目隔离要求。在此之前，全域/生产 GREEN 保持 RED。

### 2.2 真实统计数据生产链未被 E2E 证明

本批实现提供六张表和读取接口；现有 E2E 记录明示通过 SQLite 向六表“注入演示数据”（`trae-r7-e2e-20261017.txt:29-33`）。它证明演示数据经 BE 查询并被验证页消费，不证明真实工作流、任务执行器、同步任务或质量规则生产者会可靠、幂等地写入这些表，也不证明生产数据的定义与统计口径已经闭环。

**关闭条件**：给出与权威 R7/R4/R6 责任边界一致的数据生产者、写入/关联策略、幂等性和运行证据；以真实或可追溯的运行产物验证六类数据来源。若 P0-3 任务范围仅限六个查询端点，数据生产链应另列后续任务，不应将其工作状态混写为本批未完成代码。

### 2.3 生产 schema 升级与数据库验证未覆盖

`create_app` 在 lifespan 中执行 `Base.metadata.create_all`，锚点为 `datara-backend/rebuild/api/app.py:129-151`；证据使用新建/演示 SQLite 数据库（`trae-r7-e2e-20261017.txt:29-33`）。本次未发现与 R7 六表对应的版本化 migration、已有数据库升级演练或非 SQLite 数据库验证证据。因此当前 evidence 证明本地 app factory 可以创建表并工作，不能证明部署到既有生产 schema 的升级安全性、回滚策略或目标数据库行为。

**关闭条件**：提交版本化 schema 迁移及其目标数据库验证/升级 evidence，或由数据库治理责任方确认该环境明确采用其他受控建表流程。

### 2.4 时间窗标准化口径仍是开放项

`parse_window` 在 `datara-backend/rebuild/metrics/repository.py:38-52` 验证字符串非空并使用字典序比较 from/to；工作流日期查询在 `:64-68` 截取输入前十个字符，其他查询直接以字符串与数据库时间列比较。实现及 FE 契约注释均把 ISO-8601 时区/格式与 offset/limit 口径列为 B2 #4 开放项（FE `datara-web/src/services/rebuild/metricsApi.ts` 文件头及 `TimeWindowQuery` 注释）。

该项不阻断当前“FE 原样传参、BE 按已记录方式过滤”的窄口径契约验证，但未完成时间戳解析、时区归一和跨数据库行为定义之前，不应声称时间窗语义已正式冻结或对所有 ISO 表示等价。

### 2.5 更新时间列的 DB 级更新行为未由本批 evidence 证明

`datara-backend/rebuild/metrics/models.py` 各表为 `created_at`/`updated_at` 声明 `server_default`，并为 `updated_at` 声明 `server_onupdate`。本批查询接口不修改这些表，现有 E2E 只验证建表及读取；因此没有证据证明目标数据库会在后续 UPDATE 时自动刷新 `updated_at`。若相关验收要求数据库在每次行更新时生成最新更新时间，须补触发器/数据库机制或其他实现及实测证据。

## 3. 最终建议

建议在任务台账和后续通报中采用以下精确表述：

> **P0-3 窄口径 PASS：六端点冻结契约实现、main app factory/router 装配、契约测试及 SQLite/Playwright 六端点联调证据已具备。全域/生产 GREEN 仍 RED/待裁定：项目授权隔离、真实统计数据生产链及版本化迁移/目标数据库证据尚未闭环；时间窗时区语义仍为开放项。**

本结论为 Codex 独立只读复核建议。是否关闭 P0-3、是否将上述遗留拆分为后续任务，以及生产范围是否豁免项目隔离，按监督线和项目治理裁定执行。
