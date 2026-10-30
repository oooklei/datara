# P0-7 R2 安全补丁 GREEN 证据（Trae 线，2026-10-17）

任务来源：心跳 #76 裁定一 —— R2 两处安全缺口并入 P0-7，由 Trae 在 P0-4 收口后优先补：

1. `GET /run-snapshot` 越权：无 project 维度授权与过滤（原 api.py:215-228，91256dc 引入的契约面）。
2. `POST /variables/complete` env 域暴露进程环境变量**值**（原 service.py:348-360）。

## 一、改动清单（锚点）

| # | 文件 | 改动 |
|---|------|------|
| 1 | datara-backend/rebuild/variables/models.py | `TaskInstanceVariableRuntimeRecord` 新增 `project_id` 列（Integer, nullable；NULL=旧行，fail-closed 不可读） |
| 2 | datara-backend/rebuild/variables/repository.py | `write_snapshot_rows` 帧校验 project_id（可选，出现时必须 int>=1）并落列；`read_snapshot` 签名追加必填 `project_id`，查询追加 `project_id ==` 过滤（跨 project instance_id 返回空列表） |
| 3 | datara-backend/rebuild/variables/api.py | `get_run_snapshot`：`project_id` 必填 Query（缺失 → 400 code 4001）；`authorized_session(project_id, Permission.VIEW_ALL, ...)` 项目级授权（匿名 401/1001、非成员 403/1003） |
| 4 | datara-backend/rebuild/variables/service.py | `complete()` env 分支：只回环境变量**名**（`current_value=None, sensitive=True, description="process environment variable (value withheld)"`），前缀匹配大小写不敏感 |
| 5 | datara-backend/tests/rebuild/test_r2_variables_api.py | 既有 run-snapshot 段更新（行带 project_id、GET 带 project_id）；新增 `test_run_snapshot_project_scoping_and_auth`（401/400/403/200/跨项目隔离/NULL 旧行六段）与 `test_env_completion_withholds_values` |
| 6 | datara-web/src/services/rebuild/variableApi.ts | `getRunSnapshot(instanceId, projectId, attemptNo?)`：签名加必填 projectId，wire `project_id`（getJson 自动 snake 化、undefined 丢弃保 attempt_no 省略语义） |
| 7 | datara-web/src/views/rebuild/validation/variable/VariableValidationView.vue | onSnapshot 调用点同步（复用顶部定义表单 `form.projectId`） |
| 8 | datara-web/src/views/rebuild/validation/variable/variableApi.contract.test.ts | 两用例更新：URL 断言含 `project_id=5` |

范围收敛：只修 #76 点名两缺口。`resolve_name` env 分支与 `preview_resolution` 的 env 值回显**未动**（见披露 1）。

## 二、门禁

| 门禁 | 结果 |
|------|------|
| `pytest tests/rebuild`（BE） | **334 passed, 1 xfailed**（332 基线零回归 + 2 新增） |
| `vitest run`（FE） | **872 passed / 93 files** |
| `vue-tsc --noEmit`（FE） | **0 错误**（EXIT=0） |

## 三、E2E 证据

### BE HTTP 冒烟（uvicorn factory + rebuild_e2e_r2.db，真实服务）

| 断言 | 结果 |
|------|------|
| dev 读自己项目 instance 7001 | 200 `{code:0}`，1 行（resolved_value=500） |
| 缺 project_id | 400 `{code:4001, msg:"project_id is required"}` |
| NULL 旧行 instance 7002 | 200 空列表（fail-closed） |
| 匿名 | 401 `{code:1001}` |
| complete prefix="PAT" | env 项 PATH/PATHEXT，`current_value` 全 None、`sensitive` 全 True、description 含 withheld |

### Playwright 走查（headless Chromium，vite dev :5173 → BE :8000）

| 步骤 | 结果 |
|------|------|
| 登录 dev | 200 有 token |
| 补全前缀 "PAT" → 搜索补全 | 「搜索补全 完成」；env 2 行，现值列全 `—`（withheld） |
| 实例ID 7001 → 查询快照 | 「查询运行快照 完成」；1 行 resolvedValue=500 |
| 实例ID 7002（NULL 旧行） → 查询快照 | 0 行（fail-closed） |
| 网络捕获 | 3/3 全 200；`GET /run-snapshot?instance_id=7001&project_id=1&attempt_no=1` —— FE wire 级证明 project_id 已上链 |

产物：`p07-variable-e2e-20261017.json`、`p07-variable-e2e-20261017.png`（本目录）。

## 四、窄口径披露（5 条）

1. **§5 Q11 preview env 回显留裁定**：`resolve_name("env", ...)` 与 `preview_resolution` 仍按声明 §5 Q11「敏感值明文」回显真实 env 值。#76 只点名 run-snapshot 越权与 env completion 两缺口，本补丁范围收敛不动 preview；如监督线裁定 preview env 也需脱敏，另行小补丁。
2. **快照表 project_id 未加索引**：读路径走既有 `ix_variable_runtime_instance_attempt`（instance_id+attempt_no），project 过滤在快照表行数规模下可接受；如需复合索引随 R3 schema 迁移一并处理。
3. **e2e db 以 `ALTER TABLE ADD COLUMN` 加列**（SQLite，本地验证用）；生产 schema 迁移归 R3 管线，不在本补丁。
4. **NULL 旧行为变更是修复预期**：旧行为任何 project 可读（越权缺口本身），fail-closed 后旧行全不可读——属安全修复的既定语义。
5. **FE 变量页快照面板复用 `form.projectId`**（顶部定义表单的项目ID），未新增独立输入框；契约面（A2）已同步 run-snapshot `project_id` 必填。

## 五、红线自检

- 包络 `{code,msg,data}`：错误分支 4001/1001/1003 全部走包络，与既有端点一致。
- snake_case wire：`project_id` 服务端收发全 snake；FE getJson 自动 snake/camel 深度映射。
- token header 鉴权形态不变；Bearer 回退保留。
- 契约面变更（run-snapshot 新增必填 project_id）为 #76 裁定授权，FE 契约测试已同步并全绿。

## 六、遗留

- 无 P0-7 阻塞遗留。preview env 回显披露等待监督线裁定（披露 1）。
