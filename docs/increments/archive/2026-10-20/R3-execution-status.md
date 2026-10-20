# R3 Execution Status (authoritative continuation record)

## 2026-10-15：I18 双侧摘要稳定性修复与复验

- source digest 去除动态 `captured_at`；source reader 专项 5 passed，TDD 先 RED 后 GREEN。全 Backend `816 passed, 1 xfailed`，Ruff、compileall、diff-check 通过。
- 远端发现 target snapshot 文件部署滞后，已备份并单独同步 `legacy_source_reader.py`、`snapshot_repository.py`，仅重启隔离 `datara-rebuild-api`；最终 running/healthy。部署 hash 和备份路径见远程证据文档。
- Playwright 真实页面两轮 `R3S9-20261015140154-db7020`、`R3S9-20261015140204-080915` 均 10/10，source digest 两轮均 `a0227040f719c0064e51f3377378677022238d909b68c922d36275a218efbf3e`，target digest 两轮均 `044e357c04b28ea09489348b913f4392915e29445cf2b2fb437db27246455b22`；两轮均 45/44/1/0/0，确认未输入、导入未点击，浏览器错误 0。修复前的不稳定摘要 run/截图保留。
- READ ONLY 目标核验 batch/item/项目 #3 I18 model=0/0/0；import gate unset（默认关闭）、近 30 分钟 importer route=0。人工审阅最新完整计划及恢复方案并亲自确认仍未完成；R3-S9/R3 保持 PARTIAL，不合 main，不启动 R4 GREEN/P4 执行者 2。

Date: 2026-10-15 Asia/Shanghai
Workspace: `D:\需求\数据治理工具\Datara`
Status: R3-S1 through R3-S8 are complete for their stated scopes; R3 remains PARTIAL pending I18-I23 parity/import gates. R3-S9 is IN_PROGRESS: v2 schema is deployed to the isolated rebuild target, read-only preflight is ready with zero conflicts, the fixed-allowlist I18 source reader and project-authorized dry-run API are live, and the standalone validation page passed the real Playwright control loop on port 18091. User explicitly approved MySQL root for source reads only; the reader sets a read-only transaction and performs no source DDL/DML. Latest UI evidence `evidence/R3/r3s9-20261014174030-e03460.json` reports 45 source rows, 0 existing target identities, 12 planned creates, 0 unchanged, 0 conflicts, 33 blocked rows, and 37 visible issues: 2 `invalid_relation_field_pairs`, 4 `unresolved_reference`, 4 `pending_identity_missing_from_batch`, and 27 `dependency_not_importable`. The malformed relation-field records are surfaced as blockers; no values are inferred. Target schema snapshot backup SHA-256: `ea00016f184ad4abc771a6d7374eca929bc98c5a3c3fa792192c29e9c857e213`. Local gates on 2026-10-15: full `pytest tests -q` 619 passed; S9 browser-page static tests 4 passed; `ruff check rebuild`, `python -m compileall -q rebuild`, `vue-tsc --noEmit`, Vite production build and runner syntax check passed. Full repository Ruff still reports 18 pre-existing findings in legacy tests outside the rebuild domain. No source writes, target business-data imports, or formal frontend changes occurred. R3-S9 import/parity, remaining I19-I23 mapping, recovery/concurrency drills, and later increments remain open.

## R3-S9 live preview checkpoint

- The initial live run was correctly retained as FAIL evidence while the target schema was absent; after the backed-up additive v2 schema was applied, the first retry exposed MySQL identifier normalization in the read-only preflight. Preflight now compares ordered index columns/uniqueness and unique-constraint columns, not dialect-generated names. The target preflight is read-only and reports v2 `completed`, 40 expected governance tables present, zero missing tables, zero conflicts.
- The next page-led run revealed two source `t_dw_model_relation` rows store bare field strings instead of the documented JSON arrays. No field meaning was inferred. Mapping now returns an explicit `invalid_relation_field_pairs` blocking issue for each malformed row, allowing the rest of the dry-run summary to render; invalid relations remain ineligible for import.
- Browser-use previously failed twice to bind/read the same isolated page, so `browser-use=BLOCKED`; Playwright drove the exact page and controls on `http://192.168.1.9:18091/rebuild-validation-r3-s9.html`. Final run `R3S9-20261014173522-b820b6` passed 7/7 checks, with screenshot and JSON under `evidence/R3/`. Remote `datara-rebuild-api` logs recorded the actual dry-run POST as `200 OK` twice. No key/token was stored in the page or evidence.
- Source access used root only after explicit user approval, within the API's read-only MySQL transaction and fixed seven-table/column allowlist. Source reads returned 45 rows; no source DDL/DML, target business row import, old service restart, or formal frontend modification occurred. The isolated target had a verified pre-v2 snapshot (`gzip -t` passed; SHA-256 recorded above) before the additive migration. A previous empty failed-backup artifact remains preserved separately and was not used.
- Verification: backend full suite 619 passed; S9 page tests 4 passed; rebuild-domain Ruff and compileall passed; `vue-tsc --noEmit` and Vite build passed; runner syntax check passed. Full-repository Ruff was attempted and still finds 18 legacy-style violations in unrelated tests; no unrelated lint cleanup was made. S9 is not closed: mapping completeness for I19-I23, human review of 33 blocked rows, import idempotency/recovery/parity, and remaining S9 acceptance steps are open. No import write is authorized by this preview result.

## R3-S9 approved source-shape mapping update (2026-10-15)

The user explicitly approved two exact I18 migration mappings after reviewing the live read-only evidence: the source business-domain value `交易` may resolve to the observed source domain identity `交易领域`; and a non-empty bare relation-field identifier may be represented as a one-element field array. The code scopes the alias to that exact identity pair and preserves all unknown values as unresolved. It converts bare values only when they are valid identifiers; malformed values, unequal pairs, invalid arrays, and absent model identities remain blocking issues. The missing legacy model ID `1` referenced by version row `1` remains unresolved and has not been fabricated or remapped.

The earlier 45/12/33 preview is the pre-approval baseline only. The approved mapping has passed its focused local tests (30 passed); a fresh full suite and live page-led dry-run are required to establish updated counts. No legacy source or target business data has been written. User approval permits these mapping rules, not I18 import; target writes still require the S9 dry-run review, snapshot, and per-plan acceptance gates.

The next fresh read-only source snapshot on 2026-10-15 showed the current domain name is `交易域` (not the previously observed `交易领域`): 4 domains, 3 models, 27 fields, 2 relations, and 1 version (45 total rows). The earlier approved target alias was therefore stale. The user subsequently approved the exact current mapping `交易` → `交易域`; this replaces the earlier alias and remains exact-match only. The post-approval Playwright run `R3S9-20261014180718-e0d5e3` passed all 7 control checks: 45 source rows, 0 target rows, 42 planned creates, 0 unchanged, 0 conflicts, and 3 blocked rows. The domain references now resolve. The remaining four issues are confined to three source rows: version row `1` has unresolved/missing model ID `1`, relation row `1` references absent source field `order_id`, and relation row `2` references absent target field `dt`. Evidence JSON and screenshot are in `evidence/R3/`; the isolated API returned HTTP 200 and remained healthy. No target business data was imported.

### R3-S9 approval follow-up (2026-10-15)

The user explicitly confirmed the current exact alias `交易` → `交易域`, superseding the earlier stale `交易领域` target. Local mapping tests (23 passed), full backend suite (621 passed), rebuild Ruff, and compileall passed. The isolated API was redeployed after local/staged SHA-256 matched (`a8cde075875f576ae2db739ab274bdbf0870c7f05e43f05bc942fb56bb4a85eb`); health is `running healthy`. The same Playwright page run `R3S9-20261014180718-e0d5e3` passed all 7 checks, with 45 source rows, 0 target rows, 42 creates, 0 unchanged, 0 conflicts, and 3 blocked records. It returned four issues on those three records: missing version model ID `1` (two identity issues), relation row `1` missing source field `order_id`, and relation row `2` missing target field `dt`. The source database remains root-read-only under the fixed seven-table allowlist; no target business import is authorized. JSON and screenshot evidence use the run ID above.

### Latest approved I18 dispositions (2026-10-15)

The earlier blocked counts above are historical and were superseded after the user's exact row-scoped approvals. Relation `#1/source` maps `order_id` → `order_no`; relation `#2/target` maps `dt` → `order_date`. Version row `#1` is explicitly `skipped` with reason `approved_missing_model_reference`, only while its reviewed missing-model precondition remains true. The source row is preserved. The page displays both original→mapped field pairs and the skipped row/reason.

Final S9 read-only Playwright run `R3S9-20261014182427-6498d0` passed 9/9 checks with zero browser errors: 45 source rows, target identity count 0, 44 creates, 0 unchanged, 1 skipped, 0 conflicts, and 0 blocked. API returned HTTP 200; no target business import occurred. Evidence: `evidence/R3/r3s9-20261014182427-6498d0.json` and matching summary PNG. Full backend suite 626 passed; Ruff, compileall, S9 page static tests (5 passed), runner syntax, and `git diff --check` passed. The first post-deploy UI pass exposed a renderer field-name mismatch; run `R3S9-20261014182343-86a184` failed only its mapping-display assertion, the renderer was corrected to display the API's `original_field`/`mapped_field`, and the final run above closed it. Overall I18-I23 parity/import, recovery/concurrency and wider R3 acceptance remain open.

The `skipped` disposition is currently a validated dry-run plan result; it has not yet been persisted as a `MigrationItemRecord`. Durable per-source migration checkpoints, target import, and exact post-import parity remain implementation/approval gates, not completed work.

## R3-S9 I22 live schema checkpoint (2026-10-15 05:02 +08:00)

User-approved MySQL root read-only access was used against `datara-mysql-meta` on `192.168.1.9` (MySQL 8.0.46), limited to `datara_meta` I22's seven `t_std_*` tables. A READ ONLY transaction queried column/type/nullability/default metadata, index and FK metadata, and aggregate counts only. No payload rows, source mutations, grants, restarts, target imports, or credentials were involved. The live schema matched the dated inventory and confirmed that several columns from the old I22 proposal do not physically exist. Full capture: `evidence/R3/s9-i22-live-schema-20261015.md`; historical no-URL preflight now has a dated addendum and is not overwritten.

This unblocks an I22 fixed-allowlist local reader and pure mapper under their own impact analyses and commits. It does not provision `REBUILD_LEGACY_META_URL`, so the backend API source dry-run gate remains separate. R3-S9 remains IN_PROGRESS/PARTIAL; no target business data was written.

I22 reader sub-batch A is locally complete: TDD RED→GREEN; 7 focused tests, 32 I18-I22 reader regressions, and full backend suite 716 passed (64.38s); Ruff/compileall passed. Evidence `evidence/R3/s9-i22-reader-local-20261015.txt`. Status is only `LOCAL_SUBSTEP_PASS / INTEGRATION_GATE_PENDING`; no API runtime URL/config, service deployment, payload read, target import, or browser/log/middleware/resource gate was performed.

I22 mapper sub-batch B is locally complete: TDD RED→GREEN; reader+mapper focused suite 15 passed, final full backend suite 724 passed (71.64s), Ruff/compileall/diff-check passed. Evidence `evidence/R3/s9-i22-mapper-local-20261015.txt`. The only currently non-empty approval sample points to absent `t_std_code#2`; it remains explicitly unresolved (not skipped). No target import authorization, runtime API connection, deployment, or UI/log/middleware/resource gate was exercised. R3-S9 remains IN_PROGRESS/PARTIAL.

The live reader allowlist audit captured exact counts and schema metadata for I18-I23 under root-read-only scope. It found I21 reader drift (`t_qc_rule.update_time`; `t_qc_task.owner/remark/create_time`; `t_qc_exception.handled_by` absent) and all six I21 tables currently have zero rows. Evidence `evidence/R3/s9-live-reader-schema-audit-20261015.md`. One broad information_schema query returned only the `t_user.user_pwd` column name/type metadata (never a value); this query-scope deviation is disclosed in evidence and followed by a precise I23 allowlist-only metadata query. I21 source reads are blocked until contract repair. No imports or source writes occurred.

I21 contract repair locally completed: reader allowlist now matches live physical columns; mapper marks schema-absent owner/remark/handler/time fields via `source_schema_missing_columns` notes and null source timestamps. I21 reader/mapper 22 passed; full backend suite 725 passed (54.19s); Ruff/compileall passed. Evidence `evidence/R3/s9-i21-live-schema-reader-fix-20261015.txt`. No business rows were fetched and no runtime/API/deploy/import/frontend action occurred; S9 remains partial.

## R3-S1 closure

- The isolated rebuild schema and dedicated source profile were inventoried read-only on 192.168.1.9.
- Evidence: `evidence/R3/remote-schema-inventory.txt` and `evidence/R3/source-reconciliation.md`.
- The live `datara_meta` BASE TABLE count is 57, while the earlier R0 inventory reports 56; this is recorded as an unresolved historical count discrepancy, not silently normalized.
- The alleged legacy `t_mask_rule` and `t_access_log` tables do not exist in the live schema or legacy ORM. There is no source data to migrate from them. No masking feature is to be built under the user’s internal-system decision.
- Existing I18-I23 tables are inventoried; migration remains read-only/dry-run until R3-S7.
- Rebuild API had zero recent API/worker error markers at the S1 inventory timestamp; later R1 runtime closure is in `evidence/R1/remote-runtime-closure.txt`.

## R3-S2 completion

Added canonical governance contracts and local SQLite failure tests: shared DB timestamp conventions; stable asset/field/tag/lineage/standard/metric/migration identities; project-scoped authorization; quality-run row counters; migration batch and per-item checkpoints; audit event records; idempotency and conflict behavior. The S2 checkpoint was 26 passed. Final S2 Ruff and compile checks passed after formatting correction; current full rebuild suite is 34 passed with S4 included. Evidence: `evidence/R3/s2-local-contracts.txt` and `evidence/R3/s4-governance-api-local.txt`. No R3 migration/API schema was deployed remotely.

The following increment-local source files changed after R2: `docker-compose.rebuild.yml`, the R1 runner/evidence, R3 impact/evidence documents, and rebuild authentication/configuration files listed in the R1 carry-forward record. R3-S2 additionally changed only `rebuild/governance/` and its focused test. R2 generator outputs and shared/legacy API tables remain out of scope. The rebuild API is isolated on 192.168.1.9; no legacy API service or old business table was changed.

S3 had its own pre-impact analysis at `R3-S3-开始前影响分析.md`; local acceptance is in `evidence/R3/s3-migration-tests.txt`. The migration runner is versioned/additive/idempotent with failed-state recovery; remote MySQL migration remains deferred to R3-S6. S4 has its own pre-impact analysis at `R3-S4-开始前影响分析.md`; the new API is isolated under `rebuild/governance/`, uses a service/repository boundary for project access and audit persistence, and limits app startup schema creation to I1 core tables. S4 local evidence is in `evidence/R3/s4-governance-api-local.txt`; the rebuilt full suite is now 35 passed. S5 has a product-reference pre-impact analysis at `R3-S5-开始前影响分析.md`; its standalone OpenMetadata-inspired catalog/detail governance page is implemented in `datara-web/public/rebuild-validation-r3.html`, and `datara-web/deploy/test_governance_validation_page.py` is 3 passed. `pnpm build` (`vue-tsc -b && vite build`) and `git diff --check` passed. These are local gates only; remote page controls, R3 schema migration/import, remote runtime/log checks and database reconciliation are outstanding. S5 evidence is not an end-to-end PASS.

## R3-S5 local closure and S6 gate

- Page: standalone public HTML validation workbench, reference-organized Catalog → asset detail tabs → lineage/quality → governance/audit; no formal SPA routes/menu/components changed.
- Auth boundary: no login UI, verification key or token in HTML/URL/storage; runner-injected in-memory token only.
- Local checks: governance validation page tests 3 passed; whole rebuild backend suite 40 passed after adding S6 read-only preflight/target-guard tests; Ruff and compileall passed; `pnpm build` passed; `git diff --check` passed. Vite’s pre-existing large-chunk warnings are recorded, not treated as compile errors.
- Not done: no remote R3 migration; no S5 page deployed; no Playwright/browser interaction, DB rows or service log evidence. R3 remains open.
- S6 result: isolated `datara_rebuild_i0` migration `r3_0001_governance_catalog` completed, postflight conflicts=0, 12 governance tables exist and exact row counts remain 0, revision count=1 and second apply skipped idempotently. MySQL Boolean/TINYINT(1) preflight false-positive was corrected by TDD and retested; final backend suite 41 passed, Ruff/compileall passed. S4 router was atomically activated with only `datara-rebuild-api` restart; health healthy, 11 governance OpenAPI paths, 10-minute error markers 0. Complete remote details/backup hashes are in `evidence/R3/s6-remote-readonly.txt`; local tests in `evidence/R3/s6-local-preflight.txt`. No legacy I18-I23 rows imported; no DROP or data write.
- S6 status: implementation/migration/API registration PASS for its stated schema gate; R3 stays PARTIAL. Before S7, create/review `R3-S7-开始前影响分析.md`. S7 must serve `rebuild-validation-r3.html` on 18091, inject token only via protected runner, operate real page controls using browser-use then Playwright fallback on adapter failure, and reconcile each created row/audit timestamp with API, MySQL, container logs. Legacy asset import/parity is still outstanding and must remain visible in R3-S8 acceptance.

## Remote R1 deployment note

The previous compose service definition was absent from the active remote base file despite an orphaned running container. Deployment now uses the additive `docker-compose.rebuild.yml` overlay and an isolated `/lei/datara/rebuild-source/rebuild` mount, rather than replacing the remote base compose file. The overlay is validated with `docker compose config --quiet`; only `datara-rebuild-api` was recreated. Web stays on 18091.

## R3-S7 UI and persistence closure

- Playwright drove the exact deployed reference-driven page after browser-use timed out on its original call and one same-page retry (30s each). Run `R3V-20261014112022-4fc8a6` passed all 20 UI assertions with zero unexpected browser errors; evidence: `evidence/R3/s7-playwright-db-reconciliation.txt`, same-run JSON and PNG.
- Real controls persisted two assets/four fields, one tag/link, one quality rule, one lineage edge, one standard, one metric, and seven audit events. Duplicate standard produced and rendered HTTP 409; logout revoked token and follow-up returned 401.
- Read-only MySQL reconciliation matched record IDs/actions/timestamps; created/updated/generated timestamp null counts were zero; quality runs remained zero and matched the actual empty history. API healthy and 10-minute error markers zero. No Web restart, rebuild, legacy-schema write, or test-fixture cleanup.
- Two earlier successful-control-but-failed assertions were runner timing/expected-negative-control classification issues and have regression tests; actual UI defects found in earlier runs were fixed and the final full control path rerun passed.
- Overall R3 remains PARTIAL pending I18-I23 legacy import/mapping and exact row/relationship parity. No R4 authorization implied.

## Legacy QC retirement closure (R3 audit batch 1)

- User instruction: “想办法修复完成，继续推进，一直按计划执行下去，直到全部完成（如没有遇阻）”. Scope followed the previously issued QC removal work order; this does not close overall R3.
- Commit `1cb03f8` deletes only the legacy QC router and private SQL engine; Qc ORM/table mappings remain. Local backend suite: 583 passed; Ruff, compileall, and diff checks passed.
- After read-only consumer scan and backup, retired QC only in remote `datara-api`; no DB changes or other service restarts. Remote QC OpenAPI count=0, health=UP, standard=24 routes, governance service 11 routes healthy, QC tables preserved with 0 rows each. Pre-deployment access-log history was only ~8.5h; two post-deployment 404 requests are the deliberate Playwright retirement probes.
- browser-use could not bind the tab after a single retry. Playwright used the same R3 URL on 18091; final `R3V-20261014132741-7af32d` passed 21/21 assertions with zero browser errors, including actual governance-form controls and retired-route 404. Evidence: `evidence/R3/batch1-postdeploy-20261014.txt` and same-run JSON/PNG.
- Old image rollback tag: `datara-backend:pre-qc-retirement-1cb03f8`. Overall R3 remains PARTIAL for I18-I23 legacy import/mapping/parity and other planned gates.

## R3-S8/S9 legacy governance carry-forward

### I23 identity preview approval and current implementation gate — 2026-10-15

- User approved source-only READ ONLY selection of `datara_meta.t_user(id,user_name,user_role,state,create_time,update_time)`; `user_pwd` remains excluded. User approved a short-lived endpoint-only `legacy:i23:preview` capability and a one-time AOCI observe acknowledgement; no target writes/import, account/role changes, scope policy changes, or formal frontend changes are authorized.
- Detailed impact analysis, capability contract, and 9 implementation steps are recorded in `R3-S9-开始前影响分析.md` and `2026-10-14-datara-platform-rebuild.md`.
- AOCI observe acknowledgement transaction `d17064b5e17a4567c1dea253` applied as explicitly authorized. Subsequent Maintain returned blocked with no semantic candidate batch (`aligned=false`; 125 targets, 112 source files missing/unbaselined); the tool’s cognition receipt points at the main repository root rather than this worktree. No Entry authoring, orphan removal, or scope-policy mutation was performed. AOCI alignment remains unresolved.
- Working-tree preservation: `.aoci/baseline.json` was dirty before this run and remains uncommitted; the unrelated untracked nested test tree `datara-backend/datara-backend/` is preserved. Neither is part of I23 staging.
- I23 implementation/control result: backend suite 734 passed; rebuild Ruff/compileall, page static tests 5 passed, runner syntax and diff-check passed. Deployment limited to the isolated rebuild source mount and one 18091 page; only `datara-rebuild-api` restarted and is healthy. The initial staged import preflight safely stopped before restart when it found `legacy_i23_mapping.py` absent remotely; that module was added and its presence/import verified before the one restart. Final Playwright run `R3S9I23-20261014222209-50244b` passed 12/12. Four legacy source identities, one same-name target candidate, zero existing mappings; explicit UI selection yields one identity candidate and three unresolved target-user blockers. Scoped token returns 401 on ordinary project API, six-source-column boundary/credential-field absence verified, parity/import explicitly false, no UI import or account-change control, browser errors 0. API recent error markers 0; `datara-mysql-meta` healthy; I18 importer remains false. Evidence: `evidence/R3/s9-i23-preview-remote-deploy-20261015.md` and same-run JSON/PNG.
- I23 result is `I23_PREVIEW_CONTROL_PASS / IDENTITY_PARITY_PENDING / IMPORT_NOT_AUTHORIZED`; R3-S9/R3 remain IN_PROGRESS/PARTIAL. Vue/Vite production build is blocked by unrelated pre-existing TypeScript errors in unchanged `PageInspector.vue` and its test; formal frontend remained frozen.

- The prior CRLF transport error was resolved by stripping carriage returns before remote execution; the exact-count read-only script completed successfully. Evidence: `evidence/R3/s8-source-inventory-20261014.md`; old schema 57 tables, isolated target 16 tables, I18 exact 45 rows, I22 exact 3 rows, I23 users 4; I19/I20/I21 source tables are currently empty. Counts are the dated inventory, not a guarantee of unchanged live state.
- The S8 comparison confirmed that current generic R3 tables do not represent all I18 model/version/relation, I20 dimensions/versions, I21 task/exception/report/alarm, or I22 code/naming/mapping/approval/check-report semantics.
- User decision 2026-10-14: option A approved—extend the new Backend's normalized models and fully carry forward legacy I18-I23. Decision record: design §6; normalized entity contract: design §5.2; implementation plan: plan §7. Legacy source database remains read-only; only isolated `datara_rebuild_i0` may receive additive schema and migration writes.
- R3-S9 impact analysis and plan are complete. The additive v2 schema/migration is committed, and pure mappers/contracts cover all seven I18 source tables. They require an explicit destination project and source-identity resolution, preserve source business timestamps and snapshot text, and expand paired relation fields into normalized child rows. Same-batch identities use symbolic references; graph validation checks batch membership and model relation field names. The offline dry-run plan contract requires a project-bound target snapshot containing capture time/digest, source identity→target IDs/fingerprints, field metadata and occupied unique keys; it classifies create/unchanged/conflict/blocked and cascades blocked parents to their children. A target snapshot repository now reads project-scoped normalized I18 rows through SELECT-only ORM queries, rebuilds semantic fingerprints, and checks natural-key occupancy; its SQLite integration contract passes. Local gates: `pytest tests/rebuild -q` 72 passed; full `pytest tests -q` 609 passed; Ruff, compileall and `git diff --check` passed. It is not yet connected to API or verified against remote MySQL. No source reader/import, frontend/API dry-run, remote backup/import, exact parity, idempotency/fault/concurrency or rollback evidence has been completed. R3 remains PARTIAL.

## 2026-10-15 P1-P4 流水线状态续记（覆盖前述 admin 登录待验证状态）

- R3-S9 仍是当前唯一未验收增量：`PARTIAL / REMOTE_VALIDATION_CLOSEOUT`，未合回 main。
- 标准 admin provisioning/login 已完成：仅隔离库新增一个 admin 与一条身份审计；凭据在 1.9 root-only mode 0600 文件，不入页面、日志或证据。项目列表 admin 全局可见性缺陷已按既有 RBAC 修复；未改 project #3 owner/member。API 仅备份并替换两个文件、仅重启隔离 `datara-rebuild-api`，当前 healthy。
- 最终真实控件 run `R3S9-20261015125654-0356f5` 以标准 admin token 操作真实 18091 页面，10/10 PASS：project #3 选择，dry-run 200，45 source/44 create/1 skipped/0 conflict/block；人工确认短语未输入、按钮保持 disabled、import 未调用。失败 run `R3S9-20261015124843-dc81df` 保留。证据位于 `evidence/R3/r3s9-admin-project-list-remote-20261015.txt` 和成对 JSON/PNG。
- 远端 2026-10-15 20:58 +08:00：`REBUILD_LEGACY_I18_IMPORT_ENABLED=false`；最近 30 分钟 login/projects/dry-run/import 请求 6/6/4/0，服务 error markers 0；API/Web、MySQL/Redis/Kafka/ZooKeeper 正常。无 I18 目标业务 DML。
- P1：R4-SYNC 仅影响分析与 `xfail/pending-acceptance` 契约 RED；全量 `pytest tests -q` 最新 `811 passed, 1 xfailed`。R3 验收并合回 main 前不得开始 R4 GREEN。
- P2：主计划已改为 R0-R8 九个增量；R5-IDE 内 R5-A/R5-B 独立门禁，R9 统计产出归 R4/R8。
- P3：本轮权限变更及真实控件 run 即时取证，失败/通过 JSON/PNG 均保留。
- P4：第二执行者尚未启动；R3 合回 main 后才可从最新 main 的独立 worktree 开始，只写 `datara-web/` 与专属 evidence。当前不得合并/并行实现。

## 2026-10-15：I18 导入服务端范围防线与最新远程复核

- 针对“页面门禁不能替代服务端范围授权”的审查，已用 TDD 增加双重服务端约束：项目非 #3 在打开 source reader 前拒绝；最新 source/target snapshot digest 复核后，只接受恰好 45 项的获批计划（44 create + 精确孤儿版本 #1 skipped，其余计数必须为 0），不满足则在 importer 构造前拒绝。未扩展原批准业务范围。
- 本地验证：专项 11 passed；完整 `pytest tests -q` 815 passed, 1 xfailed；Ruff、compileall、diff-check、验证页 4 项合同测试、runner 语法及 `vue-tsc --noEmit` 均通过。
- 远程仅替换隔离挂载的 `governance/api.py`、`legacy_migration_service.py`，事前备份且核验新旧 SHA-256；`datara-rebuild-api` healthy，导入开关默认关闭，最近 15 分钟 importer route=0。未重启其它服务，未写旧源或目标业务数据。细节及备份位置见 `evidence/R3/r3s9-import-scope-guard-remote-final-20261015.md`。
- 最新真实控件 run `R3S9-20261015132632-d31f45` 10/10 PASS：标准 admin 会话、项目 #3、真实后端 dry-run 200、45/44/0/1/0/0、人工确认未输入、按钮仍禁用、未调用 importer；成对 JSON/PNG 已存证。browser-use 同一页面绑定首次及一次重试均未建立可用认证会话，按既定 fallback 改用同页 Playwright 控件验证；不把 API-only 作为 UI 验收。
- 本轮源 digest 含采集时间 `captured_at`；与较早 run digest 不同不等同于业务行差异。本轮只对当前摘要做预览绑定。
- 早期已批准 run 的 JSON 只有聚合计数和两条字段映射，没有完整行计划/digest；尽管最新控件 run 计数相同，仍无法据此证明逐条 identity 与早先获批范围完全一致。须由人审阅最新完整计划与恢复方案。
- 人工必须审阅最新 run 的恢复方案和 44-create/1-skip 计划，并在真实页面亲自确认；自动化未键入确认短语、未点导入、未发导入请求，I18 目标业务 DML=0。因此 R3-S9/R3 仍 `PARTIAL / REMOTE_VALIDATION_CLOSEOUT`，未合回 main；R4 GREEN 和 P4 第二执行者均未启动。


## 2026-10-16 S9 backend review fixes (local only)

- Applied the preflight review: checksum, column, PK, ordered index, unique constraint/index equivalence, unexpected unique shapes, FK delete actions, and CHECK expressions are compared before migration apply.
- Applied the I18 mapping review: non-positive/non-integer t_dw_model_field.seq is a blocking dry-run issue and the original order is not rewritten; null er_pos is persisted as JSON null, distinct from {}. Legacy datasource IDs remain preserved only in legacy_datasource_id until a verified target mapping exists.
- Verification in the isolated codex/r3-s9 worktree: focused preflight, mapping, dry-run, and dry-run API suite 55 passed; changed-file Ruff clean; git diff --check clean apart from existing CRLF normalization warnings. No import or target business DML was run. The exact user confirmation gate, R3 acceptance, and main integration remain outstanding.


## 2026-10-16 S9 unique-index semantic preflight fix

- The review found that a partial unique index could be mistaken for a full UniqueConstraint when only column names were compared. Preflight now counts a unique index as constraint-equivalent only when it has plain column names and no WHERE/predicate, expression, collation, operator-class, or prefix-length semantics; expected unique indexes use the same check.
- Added a regression using inspector dialect metadata for sqlite_where; the existing full-key unique-index equivalence test still passes. Focused preflight/mapping/dry-run/API suite: 57 passed; changed-file Ruff: clean; git diff --check: clean.
- The previously appended dry-run sequence-blocking test is normal source text (no literal backslash-n corruption) and is included in the 57-pass run. R3-S9 remains partial pending the human import-confirmation phrase, import/parity validation, acceptance, and main integration.

- Full backend verification on 2026-10-16 after review fixes: pytest tests -q 827 passed, 0 failed, 1 expected xfailed (R4-SYNC remains pending-acceptance); compileall and changed-file Ruff passed. No import, deploy, or target business DML was run.

## 2026-10-16 S9 isolated page deployment

- Published the reviewed Trae page source to the existing 18091 static web bind mount after backing up the prior file. Local, staged, remote-file, and served-response SHA-256 all match: b02ec8e3a844bad68a1fb12cddf91ee47b1e294e2eef924ff5515c141c288fd6. Prior page and backup hash: 21e5f90892f540494bd85b332887696fe585e70ef5af48b43b97d166122d3d24.
- Only the isolated HTML file changed; datara-web stayed running and no API/container restart occurred. No credential or confirmation phrase was entered; no importer call, target business DML, or parity claim was made.
- Evidence: evidence/R3/r3s9-page-only-final-deploy-20261016.txt. R3-S9 remains PARTIAL / REMOTE_VALIDATION_CLOSEOUT pending the user-only digest-bound confirmation/import/parity and acceptance gates; main integration remains gated.

- **Historical checkpoint as of 2026-10-14**: R3-S9 impact analysis and plan were complete; implementation had not started at that timestamp. This checkpoint is superseded by the 2026-10-15 P1-P4 pipeline state below: implementation now exists on `.worktrees/r3-s9`, but is not merged and overall R3 remains PARTIAL pending the explicit import confirmation and remaining parity/closure gates.

## 2026-10-15 P1-P4 流水线与所有权状态（权威追加）

- 裁定已生效：每增量收口至少一轮真实控件操作真实后端；中间低风险步骤用 API JSON 留证；认证/权限/DDL/导入/确认闸/破坏性操作即时取证。失败证据保留，诚实自评、TDD 红绿、显式人工确认及 token/key 红线不变。
- **流水线当前位**：R3-S9 在 `D:\需求\数据治理工具\Datara\.worktrees\r3-s9` 处于 `PARTIAL / REMOTE_VALIDATION_CLOSEOUT`。真实页面 admin 项目可见性与 I18 dry-run 控件已通过；但用户确认短语未输入、导入未调用且隔离导入 flag 仍为 false，R3 未验收、未合入 main。该 worktree 的代码/证据不等同于 main 已包含或整体 PASS。
- **允许的并行 RED**：下一增量 R4-SYNC 的影响分析与 `pending-acceptance`/`xfail` 契约测试已在 R3 工作树准备；该测试不破坏主测试集，不能触发 R4 实现/部署。当前阶段：R3=S9 远程验证收口；R4=影响分析/契约 RED；R4 GREEN=禁止，直到 R3 验收并合回 main。
- P2 目标为 9 个增量（R0-R4、R5-IDE、R6-R8）；R5-IDE 的 R5-A/R5-B 分别验收，R9 统计产出并入 R4/R8、消费展示归 R7。
- P4 第二执行者未启动；R3 合回 main 后才可由最新 main 创建项目内隔离 worktree。执行者 1 独占 Backend；执行者 2 仅写 `datara-web/` 与专属 evidence 子目录；不得提前启动或交叉改写。
- 最新全后端门禁为 `811 passed, 1 xfailed`；该 XFAIL 是 R4-SYNC pending-acceptance 契约 RED，主套件保持绿色。仅为来源 worktree 实测，不代表 R3 变更已进入 main。
- 此状态仅记录流水线和文件所有权，不等同于 R3 通过、已执行数据导入或授权启动 R4 GREEN。

### 2026-10-16：R3 与 Trae S9 合入 main（代码集成，不代表业务验收）

- 按用户指令，在独立集成 worktree 合并 `codex/r3-s9` 与 `trae/r3-s9-fe-fix`，随后快进至 `main`，HEAD `6342d5b`。集成期自动合并无冲突；main 原有本地更改先 stash，再全部恢复。两份重叠进度文档已保留两侧记录并追加本节；原 stash 保留作恢复点。
- 合入验证：`datara-backend/tests/rebuild` 为 290 passed、0 failed、1 个计划内 R4 xfail；R3-S9 前端契约 14 passed；两个 Node runner `--check` 与集成差异检查通过。R4 xfail 仍为 pending-acceptance。
- headed run `R3S9-20261015191204-61df20` 在 project-list 返回 401。源码确认普通路由要求签名 token 且 token 在当前 API 进程的 `active_tokens` 集合；I18 导入另要求持久化用户身份及 `EDIT_DEFINITION`，ADMIN 有此权限。验证 key 目前签发 DEV runner token 或 I23 preview capability，均不能完成 I18 导入。标准 rebuild `/login` token TTL 为 86400 秒，重启 API 会清空进程内注册表；当前代码没有 root-only 的短期 ADMIN token 签发器。
- 因此 R3-S9 仍为 `PARTIAL / REMOTE_VALIDATION_CLOSEOUT`：该 401 run 尚未重跑成功，人工 digest-bound 确认、真实导入、导入后只读 parity 与 R3 acceptance 均未发生。此合入只完成源码/验证页集成，不构成导入授权或增量验收；不启动 R4 GREEN 或 P4 第二执行者。