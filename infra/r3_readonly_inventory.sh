#!/usr/bin/env bash
set -euo pipefail

# R3 read-only source inventory. Credentials are consumed inside the MySQL
# container and are never printed or copied to the host/evidence.
printf 'R3_INVENTORY_AT=%s\n' "$(date -Is)"
docker exec datara-mysql-meta sh -lc 'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"; mysql -uroot -N -B -e "
SELECT table_schema, COUNT(*)
FROM information_schema.tables
WHERE table_schema IN (0x6461746172615F6D657461, 0x6461746172615F72656275696C645F6930)
GROUP BY table_schema ORDER BY table_schema;
SELECT table_schema, table_type, COUNT(*)
FROM information_schema.tables
WHERE table_schema IN (0x6461746172615F6D657461, 0x6461746172615F72656275696C645F6930)
GROUP BY table_schema, table_type ORDER BY table_schema, table_type;
SELECT table_name, table_type
FROM information_schema.tables
WHERE table_schema=0x6461746172615F6D657461
ORDER BY table_name;
SELECT table_name, engine, table_rows, create_time, update_time
FROM information_schema.tables
WHERE table_schema=0x6461746172615F6D657461
  AND table_name IN ('"'"'t_dw_layer'"'"','"'"'t_biz_domain'"'"','"'"'t_engine_type'"'"','"'"'t_dw_model'"'"','"'"'t_dw_model_field'"'"','"'"'t_dw_model_relation'"'"','"'"'t_dw_model_version'"'"','"'"'t_meta_table_ext'"'"','"'"'t_meta_tag'"'"','"'"'t_meta_tagging'"'"','"'"'t_indicator'"'"','"'"'t_indicator_version'"'"','"'"'t_qc_rule'"'"','"'"'t_qc_task'"'"','"'"'t_qc_run'"'"','"'"'t_qc_exception'"'"','"'"'t_qc_report'"'"','"'"'t_qc_alarm_policy'"'"','"'"'t_std_element'"'"','"'"'t_std_code'"'"','"'"'t_std_code_value'"'"','"'"'t_std_naming_rule'"'"','"'"'t_std_mapping'"'"','"'"'t_std_approval'"'"','"'"'t_std_check_report'"'"','"'"'t_mask_rule'"'"','"'"'t_access_log'"'"','"'"'t_user'"'"')
ORDER BY table_name;
SELECT table_name, column_name, column_type, is_nullable, column_key, extra
FROM information_schema.columns
WHERE table_schema=0x6461746172615F6D657461
  AND table_name IN ('"'"'t_meta_table_ext'"'"','"'"'t_meta_tag'"'"','"'"'t_meta_tagging'"'"','"'"'t_indicator'"'"','"'"'t_indicator_version'"'"','"'"'t_qc_rule'"'"','"'"'t_qc_task'"'"','"'"'t_qc_run'"'"','"'"'t_qc_exception'"'"','"'"'t_qc_report'"'"','"'"'t_qc_alarm_policy'"'"','"'"'t_std_element'"'"','"'"'t_std_code'"'"','"'"'t_std_code_value'"'"','"'"'t_std_naming_rule'"'"','"'"'t_std_mapping'"'"','"'"'t_std_approval'"'"','"'"'t_std_check_report'"'"','"'"'t_mask_rule'"'"','"'"'t_access_log'"'"','"'"'t_user'"'"')
ORDER BY table_name, ordinal_position;
SELECT table_name, column_name, column_type, column_default, extra
FROM information_schema.columns
WHERE table_schema=0x6461746172615F72656275696C645F6930
ORDER BY table_name, ordinal_position;
"'

for container in datara-rebuild-api datara-api datara-worker; do
  docker logs --since=10m "$container" 2>&1 | awk -v name="$container" '/ERROR|Traceback|Exception/ {n++} END {printf "LOG_SCAN container=%s window=10m error_markers=%d\n", name, n+0}'
done
