# T21 T5 live-chain rerun

Task anchor: `#e4c1a8f6 / T21=T5 final R8-V`.

## Scope and credential handling

The datasource and LLM configuration were read inside Python from `datara-backend/.env`. No credential value was printed, copied into this repository, or included in evidence. Database access used the supervisor-provided local SSH tunnel and the `dev_ro` account. All database statements were read-only; no write statement was issued.

## Verification results

| Sovereignty assertion | Evidence | Result |
|---|---|---|
| LLM key is injected without retaining it on the Vanna object | `rtk pytest tests/ai_copilot/test_adapter_sovereignty.py tests/ai_copilot/test_adapter_default_factory.py -q` → `10 passed`; adapter tests verify masked settings and no key on Vanna | PASS (unit contract); live generation could not complete |
| Execution uses a read-only channel | `SET SESSION TRANSACTION READ ONLY`; `SELECT 1` → `(1,)`; `SELECT CURRENT_USER()` → `dev_ro@%`; `SHOW FULL TABLES` in `ec_retail` → 21 tables | PASS (live read-only connection) |
| Projects/users are isolated | Same targeted unit command → `10 passed`; tests assert per-user/per-project Chroma paths | PASS (unit contract) |
| ChromaDB stays under Datara's data directory and is audited | Same targeted unit command → `10 passed`; tests assert `DATA_ROOT` containment and audit behavior | PASS (unit contract) |

## Online chain and remaining blocker

The database tunnel was reachable. With no `DATARA_T5_DS_DB` value present in `.env`, a connection without a selected schema returned only `ec_retail`, `information_schema`, and `performance_schema`; the 21-table catalog was then read from `ec_retail`.

The live chain was started with question “统计 dwd_i5_order_wide 中的订单总数和订单净额总和，只返回这两个汇总指标。” and `AdapterContext(user_id=1, project_id=1)`. The adapter emitted `generate_sql / memory_read_and_llm / started`, then `failed`, and raised its sanitized `VannaAdapterError`. A direct request to the configured SiliconFlow endpoint returned `APIConnectionError` (no HTTP status or provider response). No SQL was generated, no business-table query was issued, and no result explanation was produced.

The prior attempt's root cause is retained: direct access to `1.9:3310` failed with `PermissionError: [WinError 10013]`; the supervisor then established `127.0.0.1:3310 → 1.9:3310`, verified `SELECT 1`, 21 tables, and `dev_ro@%`, and changed only `DATARA_T5_DS_HOST` to `127.0.0.1`. The datasource chain now passes its connection stage; the remaining blocker is network access from this execution environment to `api.siliconflow.cn`. The full natural-language → LLM `generate_sql` → datasource query → explanation chain remains unverified pending endpoint reachability.

## Supervisor requested rerun (2026-10-19)

- Re-ran the configured adapter's live `generate_sql` call with the task's scoped context. Audit output was `started` then `failed`; the adapter returned sanitized `VannaAdapterError: SQL generation failed`. No SQL was produced, so no generated statement was sent to the datasource and no result explanation was attempted.
- Rechecked the datasource through the configured tunnel with a read-only session: `SELECT 1` → `1`; `CURRENT_USER()` → `dev_ro@%`; `SHOW FULL TABLES FROM ec_retail` → 21 tables.
- Re-ran `rtk pytest tests/ai_copilot/test_adapter_sovereignty.py tests/ai_copilot/test_adapter_default_factory.py -q` → `10 passed`.
- T21 remains blocked at live LLM SQL generation. This rerun did not execute any business-table query or database write.
