# R3-S9 I22 live source-schema preflight

- Captured: 2026-10-15 05:02 Asia/Shanghai (host clock 2026-10-14 21:02 UTC)
- Host: `192.168.1.9`; container: `datara-mysql-meta`; server: MySQL `8.0.46`; schema: `datara_meta`
- Authorization: user-approved use of MySQL root strictly for read-only inspection. No source DDL/DML, GRANT, restart, or credential/config change.
- Method: ran `SET TRANSACTION READ ONLY; START TRANSACTION;` and queried only `information_schema.COLUMNS`, `STATISTICS`, `KEY_COLUMN_USAGE`, and counts from the fixed seven-table I22 allowlist; completed with `COMMIT`. No application payload columns or credentials were selected. Root password remained inside the container environment and was not emitted.
- Scope: `t_std_approval`, `t_std_check_report`, `t_std_code`, `t_std_code_value`, `t_std_element`, `t_std_mapping`, `t_std_naming_rule` only.

## Live columns

Format: `table.column | type | nullable | default metadata | ordinal`. `NULL` default metadata means the server reports no explicit column default; it is not a sampled row value.

```text
t_std_approval.id | int | NO | NULL | 1
t_std_approval.biz_type | varchar(16) | NO | NULL | 2
t_std_approval.biz_id | int | NO | NULL | 3
t_std_approval.action | varchar(16) | NO | NULL | 4
t_std_approval.payload_json | json | YES | NULL | 5
t_std_approval.status | varchar(16) | NO | NULL | 6
t_std_approval.opinion | varchar(255) | NO | NULL | 7
t_std_approval.create_time | datetime | NO | NULL | 8
t_std_check_report.id | int | NO | NULL | 1
t_std_check_report.scope | varchar(16) | NO | NULL | 2
t_std_check_report.summary_json | json | YES | NULL | 3
t_std_check_report.issues_json | json | YES | NULL | 4
t_std_check_report.status | varchar(16) | NO | NULL | 5
t_std_check_report.create_time | datetime | NO | NULL | 6
t_std_code.id | int | NO | NULL | 1
t_std_code.code | varchar(64) | NO | NULL | 2
t_std_code.name | varchar(128) | NO | NULL | 3
t_std_code.remark | varchar(255) | NO | NULL | 4
t_std_code.status | varchar(16) | NO | NULL | 5
t_std_code.version | int | NO | NULL | 6
t_std_code.create_time | datetime | NO | NULL | 7
t_std_code_value.id | int | NO | NULL | 1
t_std_code_value.std_code_id | int | NO | NULL | 2
t_std_code_value.c | varchar(64) | NO | NULL | 3
t_std_code_value.n | varchar(128) | NO | NULL | 4
t_std_code_value.seq | int | NO | NULL | 5
t_std_code_value.remark | varchar(255) | NO | NULL | 6
t_std_element.id | int | NO | NULL | 1
t_std_element.code | varchar(64) | NO | NULL | 2
t_std_element.cn | varchar(128) | NO | NULL | 3
t_std_element.en | varchar(128) | NO | NULL | 4
t_std_element.data_type | varchar(32) | NO | NULL | 5
t_std_element.length | int | YES | NULL | 6
t_std_element.status | varchar(16) | NO | NULL | 7
t_std_element.version | int | NO | NULL | 8
t_std_element.owner | varchar(64) | NO | NULL | 9
t_std_element.remark | varchar(255) | NO | NULL | 10
t_std_element.create_time | datetime | NO | NULL | 11
t_std_element.update_time | datetime | NO | NULL | 12
t_std_mapping.id | int | NO | NULL | 1
t_std_mapping.name | varchar(128) | NO | NULL | 2
t_std_mapping.target | varchar(255) | NO | NULL | 3
t_std_mapping.element_id | int | YES | NULL | 4
t_std_mapping.code_id | int | YES | NULL | 5
t_std_mapping.status | varchar(16) | NO | NULL | 6
t_std_mapping.diff | varchar(255) | NO | NULL | 7
t_std_naming_rule.id | int | NO | NULL | 1
t_std_naming_rule.name | varchar(128) | NO | NULL | 2
t_std_naming_rule.rule_type | varchar(16) | NO | NULL | 3
t_std_naming_rule.pattern | varchar(255) | NO | NULL | 4
t_std_naming_rule.target | varchar(32) | NO | NULL | 5
t_std_naming_rule.enabled | tinyint(1) | NO | NULL | 6
```

## Constraints and current source counts

- Each table has primary key `id`.
- Unique indexes: `t_std_code.code`, `t_std_element.code`.
- Non-unique index: `t_std_code_value.std_code_id`.
- No other indexes and no declared foreign keys across the seven tables were returned by `information_schema`.
- Exact counts at capture: approval 1; check_report 0; code 1; code_value 1; element 0; mapping 0; naming_rule 0. These are aggregate counts only; no row payload was read.
- All seven tables use InnoDB. Live counts match the 2026-10-14 snapshot.
- Live schema confirms the old inventory rather than the stale design description: `t_std_element` has no `format/domain/cat`; approval has no `proposer/reason/approver/handled_at`; mapping uses `code_id` and `diff`, not `code_std_id/last_check_json`.

## Decision and scope boundary

This live evidence unblocks development of an I22 read-only source snapshot reader and a pure, fail-closed mapper strictly against these observed columns. The mapping must retain raw IDs/values and timestamps, use source identities for relationships (there are no DB-enforced FKs), and reject dangling links or unsupported enum states rather than infer semantics. It does not authorize target import, source writes, target DDL, service deployment, or frontend changes. Those require their existing separate gates.

## Read-only relationship spot-check addendum — 2026-10-15 05:12 +08:00

- Under the same user authorization, a second read-only transaction selected only the declared columns of the one `t_std_code`, one `t_std_code_value`, and one `t_std_approval` row. No other table data was selected.
- The code-value row references existing `t_std_code#1`. The approval row has `biz_type=code` and `biz_id=2`, which does not exist in the current code-set snapshot; its JSON payload was read for relationship verification but its contents are not copied into this evidence. The mapper must preserve `legacy_business_id=2`, keep canonical `standard_id` null, and mark `t_std_code#2` unresolved; it must not infer a replacement from payload, name, or another row.
- This confirms that the source approval is not safely importable under current facts. It is not implicitly skipped; a later import plan must block it or obtain an explicit row-scoped disposition. No source write or target import occurred.
