# SYNC-E2E-04

- Result: FAIL (product defect after target commit; no code changes made).
- Runtime: 192.168.1.9, deployed candidate ba17df2.
- Product objects: project 32, source datasource 18, target datasource 19, SYNC workflow 30.
- Draft graph: endpoint_select -> field_map -> condition_set; trial snapshot 7; instance 10.
- Product sync wrote `ec_retail.fixture_order_detail_source` to `datara_dw.fixture_order_detail_actual`.
- `infra/fixtures/business/verify.sh synced`: PASS; 4 actual rows exactly match expected.
- Trial/task: FAILED; task `sys_exec_endpoint` attempt 1 FAILED.
- Workflow/trial stats: success=0, failure=1 (required success=4, failure=0 not met).
- Minimum root cause: runtime inserts `lineage_writeback.project_id`, but deployed table lacks `project_id`; MySQL 1054 occurs after the target batch committed.
- Auth: high-priority-e2e token stayed in memory, logout HTTP 200; no token/key/password persisted.
- Boundaries: no direct SQL write to actual; no legacy Redis session API; no AOCI.
- Evidence: `result.json`, `root-cause-schema.txt`, `api-correlation.log`, `openapi.json`.
