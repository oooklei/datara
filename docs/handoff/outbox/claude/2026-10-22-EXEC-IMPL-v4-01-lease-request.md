# 租约请求 · RT-IMPL-V4-01-A-GROUP（致 Integration）

- **请求席**：Execution（claude）｜**票据**：IMPL-v4-01（A 组后端收口，P1）
- **受理席**：Integration（租约管理）｜**执行席**：claude-lane-loop-executor
- **目标环境**：192.168.1.9｜**水位**：`v3-0020-evidence-ready-impl-v4-03`
- **请求时间**：2026-10-22

---

## 1. 请求项

| 字段 | 值 |
|---|---|
| business_key | `IMPL-v4-01:REMOTE_TEST:a-group` |
| deliverable | ① 1.9 全量 pytest GREEN（含 A 组 8 个配套 test）；② 节点 A 证据链闭合复核 |
| target_host | 192.168.1.9 |
| lessee | I1_INTEGRATION |
| executor | claude-lane-loop-executor |
| lease_until | 随本窗（候 Integration 设定） |
| evidence_dir | 1.9 隔离工作目录（沿用 `/lei/` 隔离树，**禁写共享路径**） |

## 2. 执行内容

1. **全量 pytest**：`datara-backend` 全量测试套（含本票 8 个配套 test：`test_llm_api_and_resolver.py` / `test_llm_model_and_crypto.py` / `test_runtime_node_api.py` / `test_execution_run_statistics.py` / `test_execution_migrations.py` / `test_identity_token_digest_migration.py` / `test_component_spec_migrations.py` / `test_model_lineage_edge_shape_a.py`）。
2. **节点 A 证据链闭合复核**：LLM 六端点挂载实证（`/api/v1/rebuild/llm-models` 401 `code:1001` + `/{id}/test` 405）、`rebuild_llm_model` 密文断言、`mask_api_key` 口径。
3. **MySQL 专有路径**（sqlite 上按设计跳过者）：`v0004` 的 `MODIFY` 可空/收窄、`v0002` 的 MySQL 语义 —— 须在 1.9 MySQL 上取真实结论（本条为 `test_identity_token_digest_migration.py` 自述的 `integration_needed` 面）。

## 3. 前置与边界

- **租约申请先于任何 1.9 执行**（TEST-ENVIRONMENT-POLICY §1/§4）；本请求即该前置。
- 本机（实施席）**零测试执行**：已完成的仅静态稽核（`py_compile` SYNTAX_EXIT=0 / `vue-tsc -b` EXIT 0）+ 代码审查 + 证据包。
- 本席**不写** `control/remote-test-queue.json`（控制面文件，他席职权）；登记归属请 Integration/Flow 定。
- 证据十字段（business_key / target_host / deliverable_identity / environment_or_lease_id / commands / start_end_time / exit_codes / result_summary / raw_log_paths / executor）由执行席落 1.9 隔离目录。

## 4. 回执请求

请 Integration 回执：`LEASE_GRANTED`（含 lease_id / lease_until / 隔离工作目录绝对路径）或 `LEASE_DEFERRED`（含原因）。回执前本席不进 1.9 执行段。

—— Execution（claude），IMPL-v4-01 租约请求。
