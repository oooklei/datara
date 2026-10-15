# R3-S9 I18 relation endpoint read-only inspection

Date: 2026-10-15 Asia/Shanghai
Scope: allowlisted I18 source tables only; executed through the deployed `LegacyI18SourceReader`, which opens a read-only transaction and rolls it back. No target import or source mutation was performed.

## Source facts

- Domains: `1=交易域`, `2=用户域`, `3=商品域`, `4=流量域`.
- Models: `2=订单原始表` (`biz_domain=交易`), `3=订单明细表` (`biz_domain=交易`), `4=订单日统计` (`biz_domain=交易`). The approved exact alias `交易` → `交易域` resolves these references.
- Model 2 fields include `order_no`, `order_date`, but not `order_id`.
- Model 3 fields include `order_id`, `order_no`, `order_date`, but not `dt`.
- Model 4 fields include `order_date`, but not `dt`.
- Relation 1 is model 2 → model 3, with source/target field pair `order_id` → `order_id`. The target endpoint exists, but the source endpoint is absent.
- Relation 2 is model 3 → model 4, with source/target field pair `order_id` → `dt`. The source endpoint exists, but the target endpoint is absent.
- Version row 1 references model ID 1; the allowlisted source snapshot contains models 2, 3, and 4 only.

## Disposition

On 2026-10-15, the user approved exactly two relation endpoint substitutions: relation `#1` source field `order_id` → `order_no`, and relation `#2` target field `dt` → `order_date`. These are scoped by relation ID and endpoint; no fuzzy or global field aliasing is allowed. The mapping plan must expose each original and mapped field name.

The user also approved marking `t_dw_model_version#1` as skipped/rejected because it references missing model ID `1`. Preserve the source row and its source snapshot; do not delete or alter the source record. The skip is valid only while the exact precondition remains true: one version row with ID `1`, its `model_id` equals `1`, and no model row has ID `1`. A changed precondition must fail closed for human review.

These approvals authorize only the row-scoped mapping and skip disposition in the read-only dry-run plan; they do not authorize source writes or target business-data import. The earlier live run `R3S9-20261014180718-e0d5e3` is pre-approval evidence (45 source rows, 0 target rows, 42 planned creates, 0 unchanged, 0 conflicts, 3 blocked rows, four issues).

Post-approval run `R3S9-20261014182427-6498d0` passed 9/9 real-page Playwright checks with zero browser errors. The API returned HTTP 200; the UI showed 45 source rows, 0 target identities, 44 creates, 0 unchanged, 1 skipped, 0 conflicts, and 0 blocked. The two approved endpoint mappings and version skip reason were visible in the plan table. JSON and screenshot are `r3s9-20261014182427-6498d0.json` and `r3s9-20261014182427-6498d0-summary.png`. The isolated API container was `running healthy`; no target business import was executed.

The first post-approval runner pass `R3S9-20261014182343-86a184` reached the live API and correctly observed 44 creates/1 skip/0 blocked, but failed the UI mapping-display assertion because the renderer expected `from/to` while the API contract uses `original_field/mapped_field`. The page renderer was corrected, and the subsequent 9/9 run above passed. Both results remain in evidence for traceability.
