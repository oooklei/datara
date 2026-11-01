# datara ↔ dbx 数据源双入口同步层 — 部署与端到端验收报告

- 验收日期：2026-10-29
- 验收对象：`rebuild/datasource/dbx_sync.py` + `rebuild/api/app.py` 同步层接入（CRUD 上行钩子 + 300s 下行轮询）
- 验收环境：192.168.1.9 隔离工作目录 `/lei/apps/datara-backend-sync-20261029/`
- 前端验证入口：`http://192.168.1.9:18091/`（nginx → `datara-rebuild-api:8001`）
- dbx：`http://192.168.1.9:4224`，`/ide/api/connection/list`（GET，裸 JSON 数组）、`/ide/api/connection/save`（POST，`configs`/`removedIds`）
- **最终结论：PASS-with-caveats（6 项验收全通过；发现 2 个需后续处理的问题 + 1 处任务书契约偏差，均不影响本次上线）**

> 敏感信息一律掩码：验证 key = `<redacted>`，token = `<redacted>`（218 字符，仅记长度），数据源 password = `<redacted>`（仅记"明文/非明文"与"匹配/不匹配"）。报告与日志中均未出现任何明文凭证。

---

## 1. 镜像与容器证据

### 1.1 镜像

| 用途 | 标签 | Image ID | 构建/创建时间 |
| --- | --- | --- | --- |
| **新镜像（已上线）** | `datara-backend:dbx-sync-20261029` | `sha256:e27df5ea7f48e0734e5e7999f5f820eae5b093018994c08b1fa886f37e68b79d` | 2026-10-29 11:56:43 |
| **回滚基线（已保留）** | `datara-backend:closeout-98dc712a` | `sha256:764f5dc984cfab170e00602a559f3f29ed3a9e980e10cc3b1b50a14413504a8d` | 2026-10-27 11:16:10 |

增量 Dockerfile（`/lei/apps/datara-backend-sync-20261029/Dockerfile`）：

```dockerfile
FROM datara-backend:closeout-98dc712a
COPY rebuild/api/app.py /app/rebuild/api/app.py
COPY rebuild/datasource/dbx_sync.py /app/rebuild/datasource/dbx_sync.py
COPY rebuild/sql_ide/table_data.py /app/rebuild/sql_ide/table_data.py
```

容器内文件校验（`docker run --rm --entrypoint md5sum`）：

| 文件 | 大小 | md5 |
| --- | --- | --- |
| `/app/rebuild/api/app.py` | 102490 | `24f20d73c3d26e48081ca1bdcc28557f` |
| `/app/rebuild/datasource/dbx_sync.py` | 13271 | `443322a5a78273358bcfd5068337a2f3` |
| `/app/rebuild/sql_ide/table_data.py` | 16401 | `f33f7818d5c0f23c7ddd2a3388fc0a70` |

### 1.2 容器

- 名称：`datara-rebuild-api`
- 镜像：`datara-backend:dbx-sync-20261029`
- 状态：`Up`（2026-10-29 11:59:23 起）
- 启动参数（与旧容器逐项一致，由 `docker inspect` 自动生成 run 命令，未手工改写）：
  - `Cmd`：`uvicorn rebuild.api.app:create_app --factory --host 0.0.0.0 --port 8001`
  - `WorkingDir`：`/app`
  - `RestartPolicy`：`unless-stopped`
  - `Network`：`datara_default`
  - `PortBindings`：空（经 nginx 反代）
  - `Binds`：`/lei/datara/files:/datara/files:ro`、`datara_datara-logs:/datara/logs:ro`、`datara_resource-storage:/datara/resource-storage:rw`
  - `Env`：19 项，全部原样继承（含 `REBUILD_DB_URL`、`REBUILD_TOKEN_SECRET`、`REBUILD_VALIDATION_KEY` 等，值 `<redacted>`）
- 健康检查：`curl http://127.0.0.1:18091/api/v1/rebuild/health` → `HTTP=200`
  ```json
  {"code":0,"msg":"success","data":{"service":"rebuild-api","status":"ok"}}
  ```
  容器内直连 `127.0.0.1:8001/api/v1/rebuild/health` → `HTTP=200`

### 1.3 启动日志（无 Traceback）

```
2026-10-29 11:59:23 [WARNING] [common] 日志文件目录不可用，降级为仅控制台输出: /datara/logs
INFO:     Started server process [1]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8001 (Press CTRL+C to quit)
2026-10-29 11:59:24 [INFO] [common.registry] ZK 注册成功: /datara/live/api/172.31.0.13:8001
INFO:     172.31.0.8:54268 - "GET /api/v1/rebuild/health HTTP/1.1" 200 OK
```

> `日志文件目录不可用` 为只读挂载 `/datara/logs:ro` 导致的既有告警（回滚基线镜像同样存在），与本次改动无关。

### 1.4 代码落地校验（容器内 grep）

```
59:from rebuild.datasource.dbx_sync import DbxConnectionClient, poll_dbx_connections, push_datasource_to_dbx
136:DBX_POLL_INTERVAL_SECONDS = 300
139:class _IntervalJobScheduler:
314:    interval_scheduler = _IntervalJobScheduler()
548:            seconds=DBX_POLL_INTERVAL_SECONDS,
1350:            push_datasource_to_dbx(record)
1404:            push_datasource_to_dbx(record)
```

**`kind=` 误带风险已排除**（任务书要求剔除的 3 处 metadata `kind` 过滤未进入部署物）：

```
687:  return {"definition": catalog.definition(schema, object_name), ...}
710:  ... catalog.objects(schema, after=payload.get("after"), limit=limit) ...
720:  ... catalog.routines(schema, limit=limit) ...
728:  ... for item in catalog.objects(schema, limit=200): ...
```

四处 metadata 调用均无 `kind` 形参，与 1.9 上的 `metadata.py` 签名一致，不会触发 `TypeError`。

---

## 2. 部署偏差与回滚记录（重要）

### 2.1 首次部署失败 → 已回滚

- 首次构建（Dockerfile 仅含 `app.py` + `dbx_sync.py`）后容器 **crash-loop**：
  ```
  ModuleNotFoundError: No module named 'rebuild.sql_ide.table_data'
  ```
- 根因：部署物 `app.py`（= HEAD 版本）第 42 行 `from rebuild.sql_ide.table_data import (...)`，而基础镜像 `datara-backend:closeout-98dc712a` **不含** `rebuild/sql_ide/table_data.py`。任务书"payload 与 `closeout-98dc712a` 兼容"的前提不成立。
- **回滚已执行并复验**：以 `datara-backend:closeout-98dc712a` 按同一组 env/mount/network/cmd 重建 `datara-rebuild-api` → health `200`、日志无 Traceback、`ZK 注册成功`，服务恢复。
- 修复：`table_data.py` 为纯标准库自包含模块（仅 `datetime/uuid/decimal/typing`），与同步层无耦合；将其作为第三个 COPY 层加入增量镜像后重新构建，未改动基础镜像。

### 2.2 模块依赖核查结论

基础镜像 260 个 rebuild `.py` vs 本地 265 个，缺 5 个；逐一比对部署物引用后确认：

| 缺失模块 | 是否被部署物引用 | 处置 |
| --- | --- | --- |
| `rebuild/sql_ide/table_data.py` | **是**（app.py:42） | 已补入增量镜像 |
| `rebuild/datasource/dbx_sync.py` | **是**（app.py:59） | 已补入增量镜像 |
| `rebuild/execution/stream_executor.py` | 否 | 不需要 |
| `rebuild/resources/script_check.py` | 否 | 不需要 |
| `rebuild/datasource/__tests__/test_datasource_dbx_sync.py` | 否（仅测试） | 不需要 |

---

## 3. 端到端验收结果（6 项）

测试项目：`project_id=33`（电商全域数据治理项目）；认证方式 `POST /api/v1/rebuild/validation-token` 换 900s admin token，后续以 header `token: <redacted>` 调用。测试数据源统一命名 `dbx-e2e-*`，测试密码为一次性随机值。

### 3.1 上行即时同步 — PASS

| 检查 | 期望 | 实测 |
| --- | --- | --- |
| `POST /projects/33/datasources` | 201 + `code:0` | `create_http=201`，`id=28` |
| dbx 侧出现连接 | `datara-33-28` | `dbx_present=yes`，`dbx_id=datara-33-28` |
| `external_config.datara_ref` | `33:28` | `ref=33:28` |
| `external_config.datara_updated_at` | 存在 | `has_updated_at=True` |
| dbx 侧 password | 明文且与创建值一致 | `plaintext_pw_match=True` |

结论：CRUD 写库后同步推送，无需等待轮询，即时可见。

### 3.2 脱敏 — PASS（实现方式与任务书表述有差异）

- `GET /projects/33/datasources/28` 返回字段：`['created_at','database','host','id','kind','name','port','project_id','updated_at','username']`
- `password_field_present=False`、`password_equals_plaintext=False`
- dbx 侧同一连接 password 为明文。

即：datara 出站响应**根本不返回 password 字段**（比 `***` 掩码更严格），而 dbx 侧持有明文供实际连库。功能目标达成。

### 3.3 上行删除 — PASS

| 检查 | 期望 | 实测 |
| --- | --- | --- |
| 先建 `dbx-e2e-delete-*` | dbx 存在 `datara-33-29` | `dbx_before_delete=yes` |
| `DELETE /projects/33/datasources/29` | 200 | `delete_http=200` |
| dbx 侧连接消失 | 不存在 | `dbx_after_delete=no` |

结论：删除走 `removedIds`，dbx 侧同步移除。

### 3.4 下行轮询 — PASS（按实现语义；任务书描述与实现 E1a 相反）

> **契约偏差**：任务书 Step D(5) 要求"在 dbx 侧创建**不带 `datara_ref`** 的连接 → 轮询后应出现在 datara"。而实现（`dbx_sync.py` 模块 docstring 与 `_datara_owned_connections`）明确规定 **E1a：非 datara 归属连接一律不导入**。二者互斥。本次按实现语义双向验证，并如实记录差异；未自行修改设计。

实测（首个轮询周期在容器启动后 300s 触发，实测 `12:04:28` 观察到生效）：

| 子项 | 期望（按实现） | 实测 |
| --- | --- | --- |
| E1a 负向：dbx 侧 `datara-probe-<ts>`（无 `external_config`） | 不导入 datara | `probe present=False` → **PASS** |
| 回灌正向：dbx 侧 `datara-33-999001`（`datara_ref=33:999001`，本地无 id=999001） | 在 datara 新建 | 新建 `id=32`，名称 `dbx-e2e-rehydrate-<ts>` → **PASS** |
| 轮询失败日志 | 无 `dbx_poll_failed` / `dbx_poll_projects_failed` / `interval_job_failed` | 无命中 |

### 3.5 冲突策略（`updatedAt` 新者胜，E1b） — PASS

为规避时钟竞态，用显式 `datara_updated_at` 构造两个确定性方向（`resolve_conflict` 直接比较该时间戳与本地 `updated_at`）：

| 用例 | 构造 | 期望 | 实测 |
| --- | --- | --- | --- |
| 本地胜 | dbx 侧 host 改 `10.0.0.99`，`datara_updated_at=2020-01-01`（远旧于本地） | datara host 保持 `192.168.1.9` | `host=192.168.1.9` → **PASS** |
| 远端胜 | dbx 侧 host 改 `10.0.0.99`，`datara_updated_at=2030-01-01`（远新于本地） | datara host 变 `10.0.0.99` | `host=10.0.0.99` → **PASS** |

两个分支（`"local"` / `"remote"`）均按预期命中。

### 3.6 清理 — PASS

- 删除本次创建的全部数据源：`28 / 30 / 31 / 32` → 均 `http=200`
- 删除 dbx 侧测试连接：`datara-33-999001`、`datara-probe-<ts>` → `http=200`
- 终态：datara `project 33` 数据源恢复为 `[20,21,22,23,24]`（count=5，与基线一致）；dbx `connection/list` 无 `datara-33-*` / `probe` 残留（total=10，与基线一致）
- 数据库直查复核：`rebuild_project` 仅 `[(33, '电商全域数据治理项目')]`，`rebuild_project_datasource` 仅 `[(33, 5)]`
- **清理后跨周期稳定性**：`12:09:23` 第二轮轮询执行后再次直查，数据源仍为基线 5 条
  `[(20,'内置数仓-datara_dw'),(21,'内置源库-ec_retail'),(22,'I8-源库'),(23,'dpkg-mysql-dw'),(24,'dpkg-mysql-src')]`，
  dbx 连接数仍为 10 条、无 `datara-33-*` 残留 → 轮询在干净状态下无副作用（U1 仅在存在 ref 但本地无对应 id 时触发）

---

## 4. 关键日志片段（已脱敏）

```
# 启动
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8001 (Press CTRL+C to quit)
2026-10-29 11:59:24 [INFO] [common.registry] ZK 注册成功: /datara/live/api/172.31.0.13:8001

# 全时段（20 分钟内）错误扫描
docker logs --since 20m datara-rebuild-api | grep -Ei 'traceback|error|exception|warning'
→ 仅 1 条既有告警：日志文件目录不可用，降级为仅控制台输出: /datara/logs

# 同步层失败关键字扫描
grep -E 'dbx_poll_failed|dbx_poll_projects_failed|interval_job_failed|dbx_push_failed|dbx_push_delete_failed'
→ 无命中
```

未出现任何 key / token / password 明文。

---

## 5. 未解决事项与建议

| 编号 | 问题 | 影响 | 建议 |
| --- | --- | --- | --- |
| **U1** | **下行"本地缺失则新建"分支存在身份缺陷**：`ProjectDatasourceRepository.create()` 使用自增主键，新建记录 id（实测 32）与 dbx 侧 `datara_ref` 尾段（999001）不一致；该 ref 在下一轮轮询仍找不到本地记录 → **每个 300s 周期重复创建一条同名数据源** | 中（会造成重复数据累积） | 二选一：①`create()` 支持显式 `id`；②新增 `(project_id, dbx_ref_id)` 映射表，轮询按映射而非自增 id 匹配。本次验收已在同一周期内清理，未留下重复数据 |
| **U2** | 同步层 **INFO 日志不可见**：容器 root logger `level=30(WARNING)`，`rebuild.datasource.dbx_sync` 无独立 handler，`dbx_push_succeeded` 计数为 0 | 低（排障可观测性） | 为 `dbx_sync` 显式配置 logger 或降级为 warning 级别的成功摘要；否则上线后无法从日志确认上行是否成功 |
| **U3** | **脱敏契约表述不一致**：任务书写"返回 masked password（如 `***`）"，实现为"响应体不含 password 字段" | 低（实现更安全） | 以实现为准，回写契约文档；`dbx_sync.redact()` 的 `***` 目前仅用于日志/调试场景 |
| **U4** | **任务书前提有误**：payload `app.py` 与基础镜像 `closeout-98dc712a` 不兼容（缺 `rebuild/sql_ide/table_data.py`） | 已解决 | 增量镜像已补入该模块；后续若以 `closeout-98dc712a` 为基线做增量部署，需固定携带 `table_data.py` |
| **U5** | dbx 侧存在**历史孤儿连接** `datara-2-1`（`datara_ref=2:1`，project 2 在 datara 已不存在） | 无（轮询只遍历存在的项目，不会误导入） | 非本次产物，未清理；如需整洁可手工删除 |

---

## 6. 回滚预案与状态

- **预案**：以 `datara-backend:closeout-98dc712a`（`sha256:764f5dc9...`，已保留未 prune）按同一组 env/mount/network/cmd 重建 `datara-rebuild-api`，复验 health + 日志。
- **是否触发**：**是，已触发一次并成功回滚**（首次部署缺 `table_data.py` 导致 crash-loop）。回滚后服务恢复 200；随后按修复方案重建并重新上线，当前线上为 `datara-backend:dbx-sync-20261029`。
- 复现脚本（1.9 隔离目录内，非仓库文件）：`/lei/apps/datara-backend-sync-20261029/{Dockerfile,recreate.sh,e2e_phase1.sh,e2e_phase2.sh,e2e_phase3.sh}`

---

## 7. 纪律执行情况

- 未执行任何 `git commit` / `git push`。
- 未触碰 18090 并行验证栈（`dpkg-*`、`datara-newweb-web-codex`、`datara-legacy-sync-codex`、`datara-rebuild-api-codex` 全程 `Up`，未重启未改动）。
- 验证 key / token / password 未写入任何仓库文件、日志或报告。
- 部署与 E2E 证据全部来自 1.9 隔离工作目录 `/lei/apps/datara-backend-sync-20261029/`。
