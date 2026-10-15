# R3-S9 live source schema audit for I18-I23 reader allowlists

- Captured: 2026-10-15 05:19 Asia/Shanghai
- Host/container/schema: `192.168.1.9` / `datara-mysql-meta` / `datara_meta`; MySQL version 8.0.46, established in same session's I22 evidence.
- Authority: user-approved MySQL root, strictly read-only. Metadata and counts were read under `SET TRANSACTION READ ONLY; START TRANSACTION; ... COMMIT`; no DDL/DML/GRANT/restart/configuration/deployment/import.
- Scope: the code-declared I18-I23 source tables only (26 tables). `COUNT(*)` aggregate results below are exact; no row payload was read for this cross-domain audit.

## Exact allowlist counts

```text
I18 t_biz_domain=4; t_dw_layer=5; t_engine_type=3; t_dw_model=3;
    t_dw_model_field=27; t_dw_model_relation=2; t_dw_model_version=1 (45 total)
I19 t_meta_table_ext=0; t_meta_tag=0; t_meta_tagging=0
I20 t_indicator=0; t_indicator_version=0
I21 t_qc_rule=0; t_qc_task=0; t_qc_run=0; t_qc_exception=0; t_qc_report=0; t_qc_alarm_policy=0
I22 t_std_approval=1; t_std_check_report=0; t_std_code=1; t_std_code_value=1;
    t_std_element=0; t_std_mapping=0; t_std_naming_rule=0 (3 total)
I23 t_user=4
```

## Reader-contract comparison

- I18 (7/7 tables), I19 (3/3), I20 (2/2), I22 (7/7), and the six non-password columns in I23 all exist with observed names/types matching their fixed reader contract. I23 target read columns were separately rechecked through a precise metadata filter excluding the password column; no credential values were queried.
- I21 has three physical-contract differences, even though its six tables currently have zero rows:
  - `t_qc_rule.update_time` is in the reader allowlist but absent from live schema.
  - `t_qc_task.owner`, `remark`, and `create_time` are in the reader allowlist but absent from live schema.
  - `t_qc_exception.handled_by` is in the reader allowlist but absent from live schema.
- Other I21 allowlisted columns were present. No declared foreign keys were returned for these I21 tables. The old reader therefore cannot select from the live I21 schema and must not be used against it until its contract/mapping is corrected and tested.
- Index definitions for all 26 tables were inspected; they are not needed to authorize payload access. No schema change was made.

## Scope incident and handling

The first broad `information_schema.COLUMNS` inspection selected metadata for every column of each allowlisted table, which incidentally returned the name/type metadata for `t_user.user_pwd`. It did **not** select any value from that column and no password/hash/credential value appeared in output. This exceeded the predeclared I23 metadata filter (a query-scope process deviation), so it is recorded rather than concealed. A second query retrieved I23 metadata only for the six declared reader columns and exact aggregate count. Future I23 inspection must keep the metadata query constrained to those six columns; no `user_pwd` column access is needed.

## Disposition

Schema-audit status: partial/pass for I18/I19/I20/I22/I23 reader contracts; **blocked for I21**. The I21 reader/mapping must be corrected against live evidence before source snapshot/parity work. All I21 counts are zero but this does not waive schema/API/empty-set behavior. No data was imported or modified.
