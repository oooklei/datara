# EVIDENCE_READY — IMPL-v4-01（claude 载体）

- **票据**：IMPL-v4-01 · A 组后端收口：LLM-01-FE 节点 A 八文件 + rebuild/llm + runtime_node + run_stats + revisions v0002/v0004 + component_spec 迁移 + 8 个配套 test
- **域 / 优先级**：DELIVERY / P1（base=P1，effective=P1，priority_basis=权威设计关键路径 LLM 域；停机在飞残留首位）
- **依赖**：DEC-v4-D03 / DEC-v4-D04（v3-0006 已裁定，depends_satisfied）
- **指派依据**：Flow 事件 `v3-0016-dispatch-assigned-impl-v4-01`（assigned_to=**claude**）；票面 `outbox/flow/fl-dispatch-impl-v4-01.json`
- **水位锚**：启动时 `v3-0006-decision-rulings-d01-d04`；提交时盘面 `v3-0020-evidence-ready-impl-v4-03`
- **载体**：claude（Execution）｜**性质**：本机静态稽核 + 代码审查 + 证据包；**不含 1.9 远测结论**（远测经 Integration 租约执行，见 §6）
- **日期**：2026-10-22

---

## 1. 票据路径逐项核验（9/9 在位 + 内容稽核）

| # | 路径 | git 态 | 核验结果 |
|---|---|---|---|
| 1 | `datara-backend/rebuild/llm/` | ??（新增整域） | 8 件：`__init__.py`/`api.py`/`crypto.py`/`migrations.py`/`models.py`/`provider.py`/`repository.py`/`resolver.py` + `revisions/v0001_llm_model.py`。六端点 + AES-256-GCM + 掩码回显 + 默认位唯一索引 + DB-first resolver，逐件与 §5E 对齐 |
| 2 | `datara-backend/rebuild/runtime_node/` | ??（新增整域） | 7 件：`__init__.py`/`api.py`/`migrations.py`/`models.py`/`service.py`/`sftp.py` + `revisions/v0001_runtime_node_registry.py`。B6 冻结九字段 payload（auth 不回显）、404/4101、400/4002、502/5002、`LS_MAX_ENTRIES=500` 目录优先截断 |
| 3 | `datara-backend/rebuild/execution/run_stats.py` | ??（新增） | `RunStatisticsService`：finalize/get/list；`_SECRET_PARTS` 七键擦洗（`password/passwd/secret/token/private_key/connection_string/credential` → `***`）；reconcile detail upsert + 陈旧删除 |
| 4 | `datara-backend/rebuild/execution/revisions/v0002_run_statistics.py` | ??（新增） | revision `r9_0002_run_statistics`，down_revision `r9_0001_execution_tables`；已注册入 `EXECUTION_MIGRATIONS`（execution/migrations.py:22-25） |
| 5 | `datara-backend/rebuild/governance/revisions/v0004_token_digest_hardening.py` | ??（新增） | revision `r3_0004_token_digest_hardening`；已注册为 `R3_GOVERNANCE_MIGRATIONS` 第四修订（governance/migrations.py 尾部）；`tables=` 未声明（ALTER 型检查式修订，设计如此）；`postflight()` 返回 READY/PENDING |
| 6 | `datara-backend/rebuild/component_spec/migrations.py` | ??（新增） | `COMPONENT_SPEC_MIGRATIONS` + `apply_component_spec_migrations`（MigrationRunner 后 `validate_schema` fail-closed） |
| 7 | `datara-backend/rebuild/component_spec/revisions/` | ??（新增） | `v0001_component_catalog.py`（revision `i4_0001_component_catalog`）+ `__init__.py` |
| 8 | `datara-newweb/src/services/rebuild/llmApi.ts` | ??（新增） | 六方法 + 单 BASE + `preserveEnvelopeCode` + camel↔snake + `LLM_PROVIDERS`/`LLM_CONTRACT_METHODS`/`LLM_ERROR_CODES`；**L110 已按 D04 修正为 409/4092**（见 §3） |
| 9 | `datara-newweb/src/services/rebuild/__tests__/llmApi.contract.test.ts` | ??（新增） | 五例：六方法冻结 + 路由/动词映射；写向 snake 词形 + 读向掩码 camel 归一（断言完整 key 零出现）；`elapsed_ms→elapsedMs`；稳定码保码透传（409/4092 默认禁删与停用、409/4091 名称冲突、404/4041、502/5021） |

**配套 test（8 件，标题口径）**：7 件新增（`test_component_spec_migrations.py` / `test_execution_run_statistics.py` / `test_identity_token_digest_migration.py` / `test_llm_api_and_resolver.py` / `test_llm_model_and_crypto.py` / `test_model_lineage_edge_shape_a.py` / `test_runtime_node_api.py`）+ 1 件在飞修改（`test_execution_migrations.py`，覆盖 `EXECUTION_MIGRATIONS` 双修订 + downgrade + MySQL GET_LOCK 冲突）。8 件全部通读，断言与实现逐条对上。

## 2. 后端契约对齐矩阵（节点 A 证据链 · Execution 侧）

| FE 断言（llmApi.ts / contract test） | 后端事实源 | 判定 |
|---|---|---|
| DELETE 默认模型 → 409/4092 | `repository.delete` 抛 `ValueError("default model cannot be deleted")` → `api.py` `except ValueError → _error(409, 4092)` | **PASS** |
| PUT 停用默认模型 → 409/4092 | `repository` ValueError → 409/4092 | **PASS** |
| POST/PUT 名称唯一或默认位冲突 → 409/4091 | `IntegrityError` → 409/4091 | **PASS** |
| 不存在 → 404/4041 | `LookupError` → 404/4041 | **PASS** |
| POST /{id}/test 出站失败 → 502/5021 | `LlmProviderError` → 502/5021 | **PASS** |
| 响应只回掩码 | `crypto.mask_api_key`：≤8 全掩码，否则 `"*"*min(8,len-4)+尾4位` | **PASS** |
| api_key 仅出现在写请求体 | `_payload` 用 `mask_api_key(cipher.decrypt(...))`；密文列 `api_key_cipher` 从不外泄 | **PASS** |
| 权限闸门 | `Permission.MANAGE_USER`（后端闸门，前端不做客户端权限判定） | **PASS** |
| 默认位唯一 | 部分唯一索引 `uq_rebuild_llm_model_single_default`（`func.nullif(is_default, False)`） | **PASS** |
| 路由挂载 | `app.py` L1128-1132，仅 `LLM_ENCRYPTION_KEY` 注入时挂载 | **PASS** |

**节点 A/B 证据链闭合口径**：本席交付的是**节点 A（代码 + 本机静态稽核）**段；**节点 B（1.9 远测）**段须经 Integration 租约执行，本件不含其结论（见 §6）。LLM-01-FE 节点 B 的既有口径（v2 `cl-report-llm-01-fe-node-b-scope-ruling`）= 「vitest 契约 GREEN（先 RED 后 GREEN）+ 真实后端 8001 联通佐证；页面级 Playwright 归 R2 接线票」——本票 acceptance 已收敛为「1.9 全量 pytest GREEN」，两者不冲突（前者为 FE 面、后者为 BE 面）。

## 3. DEC-v4-D04 / F-1 修正证据（已执行）

- **位置**：`datara-newweb/src/services/rebuild/llmApi.ts` **L110**
- **原**：`/** \`DELETE /rebuild/llm-models/{id}\` —— 删除（默认模型禁删 409/4091；404/4041）。 */`
- **现**：`/** \`DELETE /rebuild/llm-models/{id}\` —— 删除（默认模型禁删 409/4092；404/4041）。 */`
- **依据**：DEC-v4-D04 —— `repository.py` L56-57 默认模型 delete 抛 `ValueError`；`api.py` L116 `except ValueError → 409/4092`。409/4091 仅 `IntegrityError`（name/default 冲突）兜底，非「默认模型禁删」语义。
- **一致性**：同文件 L74-76 `LLM_ERROR_CODES.semanticConflict = 4092`、L73 `conflict = 4091` 原本即正确；契约测试 DELETE 用例断言 `code: 4092`。修正后注释串、枚举、契约测试、后端四处一致。
- **性质**：纯注释，零行为影响。**PASS**。

## 4. DEC-v4-D03 勘误登记（随证据包提交）

见独立登记件 `outbox/claude/2026-10-22-EXEC-IMPL-v4-01-errata-D03.md`。要点：§5E.3（权威设计 v3 L786）与 WBS 15.6（L458）所载 `src/api/llm.ts` 系设计早期表述；**代码现实正位 = `datara-newweb/src/services/rebuild/llmApi.ts`**（函数名 `list/create/update/remove/testModel/setDefault`）。设计文档不在本票 paths 内，实施线**未改动** `docs/increments/**`，仅登记勘误候 E 组清理或后续文档窗处理。

## 5. DEC-v4-D01 适用性判定（不触及）

D01（选项① L3-04 口径：后端闸门 + FE 403 显式错误态）适用范围为 **PROJ-FE-01**（项目成员视图）。本票 9 条 paths 内**无** `ProjectMembersView.vue` / `routes.ts` / `menu.ts` / 成员管理端点，节点 A 范围**不触及 L3-04** → **D01 不适用，无需执行**。LLM 域的权限闸门已按同一原则实现在后端（`Permission.MANAGE_USER`，见 §2），前端不做客户端权限判定，与 D01 口径同向。

## 6. 1.9 远测与租约请求（节点 B 段）

- **验收项**：「1.9 全量 pytest GREEN」须在 192.168.1.9 执行；本机零测试执行（TEST-ENVIRONMENT-POLICY：本机结果只作诊断线索）。
- **已提交租约请求**：`outbox/claude/2026-10-22-EXEC-IMPL-v4-01-lease-request.md`（target_host=192.168.1.9，business_key=`IMPL-v4-01:REMOTE_TEST:a-group`，deliverable=全量 pytest GREEN + 节点 A 证据链闭合复核）。
- **证据落位**：1.9 隔离工作目录（沿用 `/lei/` 隔离树，不写共享路径）。
- **状态链**：`ASSIGNED → IN_PROGRESS →` **EVIDENCE_READY** →（待）Integration ENV_VERIFIED → Acceptance PASS → 集成窗提交。

## 7. 静态稽核结果（本机，仅静态/类型/逻辑）

| 项 | 命令 | 结果 |
|---|---|---|
| Python 语法 | `python -m py_compile`（A 组 18 个 .py，排除 `__pycache__`） | **SYNTAX_EXIT=0** |
| FE 类型 | `npx vue-tsc -b`（datara-newweb） | **EXIT 0** |
| 迁移注册链 | `apply_execution_migrations` / `apply_llm_migrations` / `apply_component_spec_migrations` 引用面 + revision/checksum 绑定 | **PASS**（v0002↔`r9_0002`、v0004↔`r3_0004`、component↔`i4_0001` 均自洽） |
| NO_SECRET | AKIA / PRIVATE KEY / ghp_ / xox / password\|api_key\|secret 赋值模式扫描（A 组全路径） | **0 真实命中** |
| 未执行项 | pytest / vitest / Playwright / 1.9 联调 —— **未覆盖**（本机禁测，如实标记非 PASS） |

## 8. 报 Ops / Flow 事项

1. **⚠️ 新发现（D1/D2，需裁定）：`apply_runtime_node_migrations` 为死代码**
   - 事实：`rebuild/runtime_node/migrations.py::apply_runtime_node_migrations`（L16）与 `RUNTIME_NODE_MIGRATIONS`（L6）**全仓无任何调用点**（仅模块内自引用）；revision `i17_0002_runtime_node_registry` **永不入账** `rebuild_schema_migration`。
   - 运行态**不受影响**：`rebuild_runtime_node` 表由 `app.py` lifespan 的 `Base.metadata.create_all(engine, tables=[... RuntimeNodeRecord.__table__ ...])` 建表，种子行由 `ensure_runtime_node_schema()`（B6 seed）写入。
   - 对比：`apply_llm_migrations`（app.py:364）与 `apply_component_spec_migrations`（app.py:363）**均已挂载**并入账；`apply_execution_migrations`（execution/migrations.py:30）**同样未挂载**（execution 表亦走 create_all）。
   - `git diff --stat datara-backend/rebuild/api/app.py` 为空 → **非 v2→v3 合并回归，属既有盘面**。
   - **越界说明**：修复需改 `datara-backend/rebuild/api/app.py`，**不在本票 9 条 paths 内** → 本席**不自行修复**，报 Ops/Flow 裁定（D1：挂载并账 / D2：跨票处理；或认定设计如此则删除死模块并同步 INC17 证据口径）。
   - 附带：`runtime_node/revisions/v0001_runtime_node_registry.py` 文件名 `v0001_` 与内部 revision `i17_0002_` 编号不一致（纯命名，非功能）。
2. **EXC-v4-01 仍候用户裁定**（注册表 mailbox/state_view 双址）；本席只读不改，以 `governance-state.json` 为运行权威。
3. **IMPL-v4-03 并行**：trae 线 EVIDENCE_READY（v3-0020），与本票无路径交集（其 paths 为 e2e/playwright/tsconfig.node.json），无锁冲突。

## 9. 边界遵守声明

- 动作：只读稽核 + 本机静态/类型校验 + `llmApi.ts` L110 注释修正（D04）+ 本 outbox 输出（证据包 3 件）。
- **未**执行任何测试（pytest/vitest/Playwright）；**未**做 1.9 远测；**未**写 STATE/mailbox/队列投影（Flow 单写）；**未** commit、**未** push（push=USER_ONLY）；**未**加载/调用 AOCI；**未**弹窗用户；**未**改动 `docs/increments/**` 与 `datara-backend/rebuild/api/app.py`（均在 paths 外）。
- 困难/歧义/冲突均经本件 §8 报 Ops，未自行终局裁定。

—— Execution（claude），IMPL-v4-01 EVIDENCE_READY 提交。
