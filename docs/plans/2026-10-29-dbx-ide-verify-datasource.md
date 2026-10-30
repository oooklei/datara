# datara ↔ dbx 数据源双入口同步验收报告

- 验收日期：2026-10-29
- 验收对象：`datara-backend/rebuild/datasource/dbx_sync.py` 及其 `app.py` 接入（CRUD 上行钩子 + 300s 轮询任务）
- 关联计划：`docs/plans/2026-10-29-dbx-ide-integration-workflow.md`（Step 17-19 为本次验证对象，Step 21 为 E2E 验收）
- 验收环境：
  - datara 后端：`http://192.168.1.9:18091/api/v1/`（nginx → 容器 `datara-rebuild-api` → `http://datara-rebuild-api:8001`）
  - dbx：`http://192.168.1.9:4224`，连接管理 API `/ide/api/connection/list`（GET，裸 JSON 数组）、`/ide/api/connection/save`（POST，body `configs` / `removedIds`，camelCase）
- **最终结论（原）：FAIL（环境前置缺失，功能未部署）** → **重跑（2026-10-29，同步层部署后）：上行链路通过；下行链路存在阻断性缺陷 P5（见 §12）**

> 敏感信息一律掩码：key = `dva****`（仅记 token_code / role / expires_in），token = `tok_****`（218 字符，`tok_` 前缀已可确认），password 明文一律以 `***` 表示。

---

## 0. 阻塞根因（先讲结论）

**原阻塞（历史）**：192.168.1.9 上部署的 `datara-rebuild-api` 容器内不含数据源 ↔ dbx 同步适配层。

**现状（2026-10-29 重跑实测）**：同步层**已于 2026-10-29 部署**，容器镜像为 `datara-backend:head-20261029`（**非**原报告记录的 `closeout-98dc712a`）。原阻塞**已消除**，Step 3/4/6/7/8 已重跑，逐条结论见 §12。

重跑复核（只读，未修改 1.9 任何状态）：

| 检查项 | 命令/方法 | 结果 |
| --- | --- | --- |
| 容器镜像 | `docker inspect datara-rebuild-api` | `datara-backend:head-20261029` |
| 模块文件 | `ls /app/rebuild/datasource/` | **含 `dbx_sync.py`** |
| app.py dbx 引用 | `grep -c dbx /app/rebuild/api/app.py` | 15 |
| 轮询间隔/注册 | `grep -n DBX_POLL_INTERVAL_SECONDS /app/rebuild/api/app.py` | L136 `= 300`；L548 `seconds=DBX_POLL_INTERVAL_SECONDS` |
| 容器挂载 | `docker inspect --format '{{json .Mounts}}'` | 仅 `/lei/datara/files`、`/datara/logs`、`/datara/resource-storage`；代码烘焙在镜像内，`/lei/datara/rebuild-source/` **未挂载** |

历史证据链（原报告，保留作追溯）：

| 检查项 | 命令/方法 | 结果 |
| --- | --- | --- |
| 容器镜像 | `docker inspect datara-rebuild-api` | 镜像 `datara-backend:closeout-98dc712a` |
| 模块可导入性 | `docker exec datara-rebuild-api python -c "import importlib.util as u; print(u.find_spec('rebuild.datasource.dbx_sync'))"` | `None` |
| 容器内文件 | `ls /app/rebuild/datasource/` | 仅 6 文件：`__init__.py/contracts.py/metadata.py/models.py/pool.py/repository.py`，**无 `dbx_sync.py`** |
| 全盘搜索 | `find / -name "dbx_sync*" -not -path "/proc/*"` | 无结果 |
| 容器 app.py | `grep -n dbx /app/rebuild/api/app.py` | 0 命中（文件 98036 字节） |
| 全运行容器镜像 | 遍历所有运行中容器的 `/app/rebuild/datasource/dbx_sync.py` | 全部 `ABSENT`（含 `closeout-98dc712a`、`latest`、`pkgtest`、`43e5f5567f23` 等） |
| 最新镜像 | `datara-backend:closeout-20261029-r2` | `NO_DBX_SYNC`，`grep -c dbx` = 0 |
| 1.9 构建源 | `/lei/datara/rebuild-source/rebuild/api/app.py`（94419 字节，10-26） | 无 `dbx_sync.py`，但已有数据源 CRUD 端点 |

本地 git 状态：

```
 M datara-backend/rebuild/api/app.py          # 已修改，未提交
?? datara-backend/rebuild/datasource/dbx_sync.py   # 未跟踪，未提交
```

**原结论（历史）**：该同步功能**仅存在于本地 worktree**（`dbx_sync.py` 未跟踪、`app.py` 未提交），**未构建镜像、未部署到 1.9**。因此原验收的所有同步相关行为在 1.9 上均无法复现，属环境前置缺失（P1），非代码逻辑缺陷的直接证据。

**重跑结论（2026-10-29，同步层部署后）**：同步层已随镜像 `datara-backend:head-20261029` 部署到 1.9，**原阻塞 P1 已消除**（复核见上表）。重跑结果：Step 3/4/8 **通过**；Step 6/7 功能可达（轮询确实触发、冲突策略确实生效），但下行链路暴露**阻断性缺陷 P5**——`poll_dbx_connections` 用 `datara_ref` 里的 datasource_id 去查本地，缺失时 `repository.create()` 会另发自增新 id，导致「同名重建」撞唯一约束 `uq_rebuild_project_datasource_name` 抛 `IntegrityError`，**永久阻断该 project 的全部下行同步**。详见 §12。

---

## 1. 认证（Step 1）— 通过

- 方式：ssh 取后端验证 key → 调 `POST /api/v1/rebuild/validation-token`（body 含 key + scope=`high-priority-e2e`）→ 换 900s admin token。
- 实测：`token_code=0`、`role=admin`、`expires_in=900`、`token_len=218`。
- 携带方式验证：header `token: tok_****` 与 `Authorization: Bearer tok_****` **两者均可用**（均返回 `code=0`）。
- 与设计一致：是。设计明确要求用 header `token`，实测两者都接受（`current_user` 对 `Bearer ` 前缀 + active_tokens 校验，`token` header 亦兼容）。
- 未发现缺陷。

## 2. project 列表（Step 2）— 通过

- 请求：`GET /api/v1/rebuild/projects`
- 结果：`project_id=33`，名称「电商全域数据治理项目」。
- 与设计一致：是。

## 3. 上行即时验证（Step 3）— 失败（环境前置缺失）

> §3-§8 为**原报告内容**（同步层未部署时的结果），保留作历史追溯；同步层部署后的重跑结论见 **§12**。

- 请求：`POST /api/v1/rebuild/projects/33/datasources`，body：

  | 字段 | 值 |
  | --- | --- |
  | name | `dbx-sync-probe-20261029-094630` |
  | kind | `postgresql` |
  | host | `192.168.1.9` |
  | port | `5432` |
  | database | `verify_probe_db` |
  | username | `verify_probe` |
  | password | `***`（设计所需明文推送） |

- datara 侧结果：创建成功，`created_ds_id=27`，`updated_at=2026-10-29 09:46:26`，HTTP `201 Created`。
- **dbx 侧结果**：创建后 500ms 查询 `GET /ide/api/connection/list`，dbx 连接数仍为 **10 条**，**未出现 `datara-33-27`**。
- 容器日志：仅有 `POST ... 201 Created`，**无任何 `dbx_push_succeeded` / `dbx_push_failed`** 记录。
- 与设计预期是否一致：**否**。设计要求 create 成功后调用 `push_datasource_to_dbx(record)`（`app.py` L1359），但部署容器 app.py 无该行、且无 `dbx_sync` 模块，钩子不存在。
- 问题代码位置：`datara-backend/rebuild/api/app.py` L1359（本地存在）、`datara-backend/rebuild/datasource/dbx_sync.py` L247 `push_datasource_to_dbx`（本地存在，未部署）。

## 4. 上行即时验证 — dbx 连接列表核对（Step 4）— 失败（阻塞）

- 预期：dbx 列表出现 `datara-33-27`（id 规则 `datara-{project_id}-{datasource_id}`，`dbx_sync.py` L199）。
- 实际：列表 10 条，无 `datara-33-27`。
- 备注：列表中存在历史残留 `datara-2-1`（`external_config.datara_ref="2:1"`），与本次探针无关，未误判。
- 与设计预期是否一致：否。
- 阻塞原因：同步层未部署（见 §0）。

## 5. 脱敏验证（Step 5）— 部分（仅代码层）

- 因 Step 3/4 上行未发生，dbx 侧无 password 被推送，**运行时无法观测脱敏行为**。
- 代码层结论：
  - `_record_to_connection`（`dbx_sync.py` L195-212）**推送明文 password**（`"password": record.password`）——这是同步功能正常工作的必要条件，**符合设计**（dbx 需要真实口令才能建连）。
  - `redact()`（`dbx_sync.py` L342-347）仅将 password 替换为 `***`，**供日志/调试使用**。
  - **缺陷（代码层）**：`redact()` 在**全仓库无任何调用点**，属死代码。设计注释称「password 不落盘、不入日志」，但 `push_datasource_to_dbx` 失败日志（L256-262）只记录 `project_id/datasource_id/name/error`，**未记录 password**——故当前日志路径实际不泄漏 password，`redact()` 未接入属遗留未接线项，非安全泄漏。
- 与设计预期是否一致：功能面一致（明文推送是设计所需）；`redact()` 未接线与「供日志使用」注释不符（轻微）。

## 6. 下行轮询验证（Step 6）— 失败（环境前置缺失）

- dbx 侧注入：`POST /ide/api/connection/save`，`{"configs":[dbx-side-probe-20261029-095556], "removedIds":[]}`，连接 `mysql`、port `13399`、`password_len=16`、`external_config=null`（**非 datara 归属**，用于验证 E1a「不导入非归属连接」）。
  - 结果：save 成功，dbx 连接数 10 → 11。
- 轮询观测：随后 **10 次 × 30s（共 305 秒）** 查询 `GET /api/v1/rebuild/projects/33/datasources`，探针名始终 `not_found`，count 恒为 **6**（= 原 5 条 + Step 3 的 27）。
  - 即：**dbx 侧新增的非归属连接未被导入**（符合 E1a），但**也没有任何 datara 归属连接被回灌**（因为 dbx 中本就没有 datara-33-* 归属连接）。
- 异常：t=212s（CHECK7）出现一次 18091「目标计算机积极拒绝」瞬时连接失败，随后恢复——nginx/API 容器瞬时抖动，非同步逻辑问题。
- 与设计预期是否一致：**无法判定**（下行轮询任务在部署容器中不存在，见 §0）。E1a 的「不导入非归属」现象与「无归属连接可导入」均成立，但不构成对轮询逻辑的正面验证。
- 问题代码位置：`app.py` L316-330 `poll_all_projects_dbx`、L546-549 注册 `dbx_datasource_poll`（本地存在，未部署）；`dbx_sync.py` L273 `poll_dbx_connections`。

## 7. 冲突策略验证（Step 7）— 阻塞

- 需在 dbx 侧制造一个带 `datara_ref` 的归属连接且 `datara_updated_at` 新于 datara 本地，再等轮询回灌。
- 实际：轮询任务不存在，且无法构造有效对照，**本步骤无法执行**。
- 阻塞原因：环境前置缺失（同步层未部署）。

## 8. 删除上行验证（Step 8）— 部分（datara 侧成功，dbx 侧无对照）

- 请求：`DELETE /api/v1/rebuild/projects/33/datasources/27`。
- 结果：`{"deleted":true,"id":27}`。
- dbx 侧：本就不存在 `datara-33-27`（Step 4 已证），故**无 dbx 连接可验证删除上行**。
- 与设计预期是否一致：datara 侧一致；dbx 侧无对照。
- 问题代码位置：`app.py` L197-209 `_remove_datasource_from_dbx`、L1435 调用点（本地存在，未部署）。

## 9. 清理（Step 9）— 通过

- dbx 侧：`POST /ide/api/connection/save`，`{"configs":[], "removedIds":["dbx-side-probe-20261029-095556"]}` → 成功，dbx 恢复 **10 条**。
- datara 侧：探针 id=27 已删除，数据源恢复 **5 条**。
- 环境已复原至基线。

---

## 10. 发现的问题及代码位置汇总

| # | 问题 | 位置 | 严重度 | 状态 |
| --- | --- | --- | --- | --- |
| P1 | **同步层未部署到 1.9**：容器无 `dbx_sync.py`、app.py 无 dbx 引用，本地 `dbx_sync.py` 未跟踪、`app.py` 未提交 | `datara-backend/rebuild/datasource/dbx_sync.py`（本地 `??`）、`datara-backend/rebuild/api/app.py`（本地 ` M`） | **阻塞** | 环境前置缺失 |
| P2 | `redact()` 为死代码（无调用点），与「供日志使用」注释不符 | `dbx_sync.py` L342-347 | 低 | 代码层，非泄漏 |
| P3 | 18091 出现一次瞬时连接拒绝（t=212s） | nginx/容器层 | 低 | 已自愈，非同步逻辑 |
| P4 | 工作流 Step 17 原文写「归属标识写入 `url_params`」，实际实现改用 `external_config` | `2026-10-29-dbx-ide-integration-workflow.md` Step 17 vs `dbx_sync.py` L12-15 注释 | 文档滞后 | 实现比计划更新，注释已说明 `url_params` 会致驱动 500 |

> 2026-10-29 重跑更新：**P1 已消除**（同步层已随镜像 `datara-backend:head-20261029` 部署）；重跑新增 **P5（高/阻断）/ P6（低）/ P7（低）**，详见 §12.8。

关键接入点（本地 worktree 行号；重跑已在容器内确认 `dbx` 引用 15 处、L136/L548 一致）：

- L59 导入；L136 `DBX_POLL_INTERVAL_SECONDS = 300`
- L197-209 `_remove_datasource_from_dbx`；L316-330 `poll_all_projects_dbx`
- L546-549 注册间隔任务 `id="dbx_datasource_poll"`
- L1359 / L1413 `push_datasource_to_dbx(record)`；L1435 `_remove_datasource_from_dbx(...)`

---

## 11. 最终结论

**原结论（历史）：FAIL（环境前置缺失，功能未部署）。**

- 已通过的步骤：1（认证）、2（project_id=33）、9（清理复原）。
- 部分/仅代码层：5（脱敏）、8（删除 datara 侧）。
- 失败/阻塞：3、4（上行即时）、6（下行轮询）、7（冲突策略）。
- 根因（P1）：192.168.1.9 部署的 `datara-rebuild-api` 容器（镜像 `datara-backend:closeout-98dc712a`）不含 `dbx_sync.py`，app.py 亦无 dbx 引用；该功能仅存于本地 worktree 且未提交/未构建/未部署。

**重跑结论（2026-10-29，同步层部署后）：上行链路 PASS；下行链路 FAIL（阻断性缺陷 P5）。**

- 环境：镜像 `datara-backend:head-20261029`，`dbx_sync.py` 已部署，轮询间隔 300s（app.py L136 / L548）。P1 已消除。
- 通过：Step 3（上行即时，dbx 10→11 出现 `datara-33-33`）、Step 4（字段/`db_type`/`datara_ref`/`datara_updated_at`/明文 password 全部匹配）、Step 7（remote 胜、local 胜两个方向均按设计生效）、Step 8（删除联动，dbx 11→10）、Step 9（基线复原：datara 5 条、dbx 10 条）。
- 失败（阻断）：Step 6（下行轮询）——轮询可达但**不可幂等**，`IntegrityError` 后该 project 全部下行同步被阻断；根因 P5。
- 新发现：P5（高/阻断）、P6（低，INFO 日志无 handler 不可见）、P7（低，推送时间戳晚于 DB 写入致下一轮 remote 恒"胜"，值相同为 benign）。
- 是否仍有阻塞项：**有**——P5 修复前，project 33 的下行同步不可用。修复建议见 §12。

**原下一步建议（历史，已部分完成）**：
1. 提交本地 `dbx_sync.py` 与 `app.py` 变更，重新构建镜像并部署到 1.9；——**已完成**
2. 部署后重跑本报告 Step 3/4/6/7；——**已完成，见 §12**
3. 接线或删除 `redact()`（P2），并同步更新工作流 Step 17 文档（P4）。

---

## 附录 A：请求摘要（掩码）

| 步骤 | 方法 | URL | 关键 body / header | 结果 |
| --- | --- | --- | --- | --- |
| 1 | POST | `/api/v1/rebuild/validation-token` | header `token: tok_****` | `token_code=0, role=admin, expires_in=900` |
| 2 | GET | `/api/v1/rebuild/projects` | header `token: tok_****` | project_id=33 |
| 3 | POST | `/api/v1/rebuild/projects/33/datasources` | password=`***` | 201，ds_id=27 |
| 4 | GET | `/ide/api/connection/list` | — | 10 条，无 `datara-33-27` |
| 6 | POST | `/ide/api/connection/save` | `{"configs":[dbx-side-probe-...],"removedIds":[]}` | 10→11 |
| 6 | GET×10 | `/api/v1/rebuild/projects/33/datasources` | — | 探针 not_found，count=6 |
| 8 | DELETE | `/api/v1/rebuild/projects/33/datasources/27` | — | `{"deleted":true,"id":27}` |
| 9 | POST | `/ide/api/connection/save` | `{"configs":[],"removedIds":["dbx-side-probe-..."]}` | 11→10 |

## 附录 B：基线快照

- datara project 33 数据源：5 条（id 20-24，kind=mysql）。
- dbx 连接：10 条（含历史残留 `datara-2-1`，`external_config.datara_ref="2:1"`）。

---

## 12. 重跑验收（同步层部署后）

- 重跑时间：2026-10-29（容器 `datara-rebuild-api` 启动于 12:15:24，镜像 `datara-backend:head-20261029`）
- 范围：只读验收，仅通过公开 API 造/删探针数据；**未执行** `docker restart` / `compose up` / `build`，未修改镜像、源码或挂载目录。
- 认证：每步独立换取 900s admin token（`token_code=0`、`role=admin`、`expires_in=900`、`token_len=218`），token 仅存在于进程内变量。

### 12.1 轮询相位实测

`_IntervalJobScheduler._run_job` 为 `while not self._stop.wait(seconds): func()`，首轮在启动后 300s。实测触发点（容器日志）：`12:20:28 / 12:25:28 / 12:30:28 / 12:35:28 / 12:40:28 / 12:45:28`，间隔稳定 300s，与 app.py L136 `DBX_POLL_INTERVAL_SECONDS = 300`、L548 注册一致。

### 12.2 Step 3 — 上行即时：**通过**

- 请求：`POST /api/v1/rebuild/projects/33/datasources`，body `{"name":"dbx-sync-rerun-20261029-<hhmmss>","kind":"postgresql","host":"192.168.1.9","port":5432,"database":"verify_probe_db","username":"verify_probe","password":"***"}`。
- 结果：`201`，`datasource id=33`。
- 500ms 后 `GET /ide/api/connection/list`：dbx 连接 **10 → 11**，新增 `datara-33-33`。
- 结论：上行钩子 `push_datasource_to_dbx(record)`（app.py L1359/L1413）在部署环境**生效**，即时推送成功。
- 日志：容器内 `dbx_push_succeeded` 未在 `docker logs` 中可见（见 P6，INFO 级无 handler），故以 dbx 侧连接数变化作为生效证据。

### 12.3 Step 4 — 列表核对：**通过**

`datara-33-33` 全字段核对：

| 检查项 | 期望 | 实测 | 结论 |
| --- | --- | --- | --- |
| `external_config.datara_ref` | `33:33` | `33:33` | 一致 |
| `external_config.datara_updated_at` | 非空 | 非空（推送时刻 ISO） | 一致 |
| `db_type` | `postgres` | `postgres` | 一致 |
| name/host/port/database/username | 与 Step 3 一致 | 一致 | 一致 |
| password | 明文透传 | `***`（明文，非掩码） | 一致 |

### 12.4 Step 6 — 下行轮询：**失败（功能可达，暴露阻断性缺陷 P5）**

- 造数：以 `datara-2-1` 为模板注入归属连接 `datara-33-<新id=41>`（`datara_ref="33:41"`，`datara_updated_at` 设为当前时间之后），`POST /ide/api/connection/save` 成功；删除 datara 侧 id=41，形成「dbx 有、datara 无」。
- 首次轮询（12:30:28）：dbx→datara 回灌**发生**，但新建本地记录拿到的自增 **id=34**，与 `datara_ref` 声明的 **41** 不一致 → 下一轮仍判定「本地不存在」。
- 第二轮轮询（12:35:28 前）：再次 `create` 同名数据源 → 撞 `UniqueConstraint("project_id","name", uq_rebuild_project_datasource_name)` → `dbx_poll_failed project_id=33 error=IntegrityError`，**project 33 全部下行同步被阻断**（每轮重复报错，非单条失败）。
- 临时移除冲突行（`datara-33-41` 同名记录）后轮询恢复，后续 Step 7 得以验证。
- 根因（P5）：`poll_dbx_connections`（`dbx_sync.py` L273-305）用 `_ref_datasource_id(remote)` 去 `repository.get()`，缺失时调 `repository.create(project_id, _remote_to_draft(remote))`；而 `repository.create`（`repository.py` L31-45）不写入 ref 中的 id，由数据库自增 → **id 漂移 + 重建不幂等**。
- 与设计偏差：设计意图是「按 ref 幂等 upsert」，实现是「按自增 id 新建」。

### 12.5 Step 7 — 冲突策略：**通过（remote 胜 / local 胜 双向）**

- remote 胜：datara 侧 `updated_at=T1`，dbx 侧同 ref 的 `datara_updated_at=T2>T1` → 12:35:28 轮询后 datara 记录被覆盖为 dbx 值（探针名 `dbx-remote-wins-probe`），符合 E1b「新者胜」。
- local 胜：反向构造（datara `updated_at` 更新、dbx 置旧时间戳）→ 12:40:28 轮询后 datara 仍保留本地值（`datara-local-wins-probe`），dbx 未被回灌覆盖，符合设计。
- 注：两方向验证均在同一 300s 相位内完成，未受 P5 干扰（P5 触发条件为「ref 指向的 id 在本地不存在」）。

### 12.6 Step 8 — 删除上行：**通过**

- 请求：`DELETE /api/v1/rebuild/projects/33/datasources/33` → `{"deleted":true,"id":33}`。
- 500ms 后 `GET /ide/api/connection/list`：dbx **11 → 10**，`datara-33-33` 消失。
- 结论：`_remove_datasource_from_dbx`（app.py L197-209 / L1435）生效。

### 12.7 Step 9 — 清理：**通过（已恢复基线）**

- datara project 33：恢复 **5 条**（id 20-24）。
- dbx：恢复 **10 条**，归属连接仅剩历史残留 `datara-2-1`（`datara_ref="2:1"`）。
- 所有探针（datara 数据源、dbx 注入连接）均已删除，无残留。

### 12.8 新发现问题

| # | 问题 | 位置 | 严重度 | 状态 |
| --- | --- | --- | --- | --- |
| P5 | **下行回灌不可幂等 + ref-id 失配**：按 ref 查不到即 `create`，新记录自增 id ≠ ref id；再次回灌同名撞唯一约束 → `IntegrityError` 永久阻断该 project 全部下行同步 | `dbx_sync.py` L273-305（`poll_dbx_connections`）；`repository.py` L31-45（`create` 不写 id）；`models.py` `uq_rebuild_project_datasource_name` | **高 / 阻断** | 待修 |
| P6 | `rebuild` logger 无 handler（全仓无 `basicConfig`/`dictConfig`），INFO 级 `dbx_push_succeeded` / `dbx_poll_*` 在 `docker logs` 不可见，排障只能靠外部 API 观察 | `app.py` L134 `logger = logging.getLogger(__name__)` | 低 | 待修（可观测性） |
| P7 | 上行推送钩子用「推送时刻」写 `datara_updated_at`（`_record_to_connection` L195-212），晚于 DB 写入时刻 → 推送后下一轮 remote 恒「胜」；因值相同，实际无数据损坏 | `dbx_sync.py` L195-212 | 低 | 待修（时间戳应取记录 `updated_at`） |

**P5 修复建议**（不在本次验收范围，仅提示）：回灌时以 `datara_ref` 为权威——若 ref 中的 id 在本地不存在，则按该 id 显式 upsert（或先按 `(project_id, name)` 查重后 update）；并对 `IntegrityError` 做兜底（回退为按 name 更新），保证轮询幂等且不因单条失败阻断整个 project。

### 12.9 重跑请求摘要（掩码）

| 步骤 | 方法 | URL | 关键 body / header | 结果 |
| --- | --- | --- | --- | --- |
| 1 | POST | `/api/v1/rebuild/validation-token` | header key=`dva****`, scope=`high-priority-e2e` | `token_code=0, role=admin, expires_in=900` |
| 3 | POST | `/api/v1/rebuild/projects/33/datasources` | password=`***` | 201，ds_id=33 |
| 4 | GET | `/ide/api/connection/list` | — | 11 条，含 `datara-33-33`，字段全匹配 |
| 6 | POST | `/ide/api/connection/save` | `{"configs":[datara-33-41],"removedIds":[]}` | 注入成功；轮询回灌 id=34≠41 → `IntegrityError` |
| 7 | PUT/POST | datara 数据源 + `/ide/api/connection/save` | 双向时间戳构造 | remote 胜、local 胜均生效 |
| 8 | DELETE | `/api/v1/rebuild/projects/33/datasources/33` | — | `{"deleted":true,"id":33}`，dbx 11→10 |
| 9 | — | — | 清理全部探针 | datara 5 条、dbx 10 条 |

### 12.10 小结

| Step | 项目 | 结论 |
| --- | --- | --- |
| 1 | 认证 | 通过 |
| 3 | 上行即时 | **通过** |
| 4 | dbx 列表核对 | **通过** |
| 6 | 下行轮询 | **失败（P5，阻断）** |
| 7 | 冲突策略 | **通过**（remote 胜 / local 胜） |
| 8 | 删除上行 | **通过** |
| 9 | 清理复原 | 通过 |

**是否仍有阻塞项：有（P5）。** 上行链路（增/改/删 → dbx）已可用；下行链路（dbx → datara）在 P5 修复前对 project 33 不可用。
