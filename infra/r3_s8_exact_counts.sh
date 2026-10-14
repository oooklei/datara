#!/usr/bin/env bash
set -euo pipefail

printf 'R3_S8_EXACT_COUNTS_AT=%s\n' "$(date -Is)"
docker exec datara-mysql-meta sh -lc 'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"; mysql -uroot -N -B -e "
SELECT '"'"'legacy'"'"', '"'"'t_biz_domain'"'"', COUNT(*) FROM datara_meta.t_biz_domain
UNION ALL SELECT '"'"'legacy'"'"', '"'"'t_dw_layer'"'"', COUNT(*) FROM datara_meta.t_dw_layer
UNION ALL SELECT '"'"'legacy'"'"', '"'"'t_engine_type'"'"', COUNT(*) FROM datara_meta.t_engine_type
UNION ALL SELECT '"'"'legacy'"'"', '"'"'t_dw_model'"'"', COUNT(*) FROM datara_meta.t_dw_model
UNION ALL SELECT '"'"'legacy'"'"', '"'"'t_dw_model_field'"'"', COUNT(*) FROM datara_meta.t_dw_model_field
UNION ALL SELECT '"'"'legacy'"'"', '"'"'t_dw_model_relation'"'"', COUNT(*) FROM datara_meta.t_dw_model_relation
UNION ALL SELECT '"'"'legacy'"'"', '"'"'t_dw_model_version'"'"', COUNT(*) FROM datara_meta.t_dw_model_version
UNION ALL SELECT '"'"'legacy'"'"', '"'"'t_meta_table_ext'"'"', COUNT(*) FROM datara_meta.t_meta_table_ext
UNION ALL SELECT '"'"'legacy'"'"', '"'"'t_meta_tag'"'"', COUNT(*) FROM datara_meta.t_meta_tag
UNION ALL SELECT '"'"'legacy'"'"', '"'"'t_meta_tagging'"'"', COUNT(*) FROM datara_meta.t_meta_tagging
UNION ALL SELECT '"'"'legacy'"'"', '"'"'t_indicator'"'"', COUNT(*) FROM datara_meta.t_indicator
UNION ALL SELECT '"'"'legacy'"'"', '"'"'t_indicator_version'"'"', COUNT(*) FROM datara_meta.t_indicator_version
UNION ALL SELECT '"'"'legacy'"'"', '"'"'t_qc_alarm_policy'"'"', COUNT(*) FROM datara_meta.t_qc_alarm_policy
UNION ALL SELECT '"'"'legacy'"'"', '"'"'t_qc_exception'"'"', COUNT(*) FROM datara_meta.t_qc_exception
UNION ALL SELECT '"'"'legacy'"'"', '"'"'t_qc_report'"'"', COUNT(*) FROM datara_meta.t_qc_report
UNION ALL SELECT '"'"'legacy'"'"', '"'"'t_qc_rule'"'"', COUNT(*) FROM datara_meta.t_qc_rule
UNION ALL SELECT '"'"'legacy'"'"', '"'"'t_qc_run'"'"', COUNT(*) FROM datara_meta.t_qc_run
UNION ALL SELECT '"'"'legacy'"'"', '"'"'t_qc_task'"'"', COUNT(*) FROM datara_meta.t_qc_task
UNION ALL SELECT '"'"'legacy'"'"', '"'"'t_std_approval'"'"', COUNT(*) FROM datara_meta.t_std_approval
UNION ALL SELECT '"'"'legacy'"'"', '"'"'t_std_check_report'"'"', COUNT(*) FROM datara_meta.t_std_check_report
UNION ALL SELECT '"'"'legacy'"'"', '"'"'t_std_code'"'"', COUNT(*) FROM datara_meta.t_std_code
UNION ALL SELECT '"'"'legacy'"'"', '"'"'t_std_code_value'"'"', COUNT(*) FROM datara_meta.t_std_code_value
UNION ALL SELECT '"'"'legacy'"'"', '"'"'t_std_element'"'"', COUNT(*) FROM datara_meta.t_std_element
UNION ALL SELECT '"'"'legacy'"'"', '"'"'t_std_mapping'"'"', COUNT(*) FROM datara_meta.t_std_mapping
UNION ALL SELECT '"'"'legacy'"'"', '"'"'t_std_naming_rule'"'"', COUNT(*) FROM datara_meta.t_std_naming_rule
UNION ALL SELECT '"'"'legacy'"'"', '"'"'t_user'"'"', COUNT(*) FROM datara_meta.t_user
UNION ALL SELECT '"'"'target'"'"', '"'"'rebuild_governance_asset'"'"', COUNT(*) FROM datara_rebuild_i0.rebuild_governance_asset
UNION ALL SELECT '"'"'target'"'"', '"'"'rebuild_governance_asset_field'"'"', COUNT(*) FROM datara_rebuild_i0.rebuild_governance_asset_field
UNION ALL SELECT '"'"'target'"'"', '"'"'rebuild_governance_asset_tag'"'"', COUNT(*) FROM datara_rebuild_i0.rebuild_governance_asset_tag
UNION ALL SELECT '"'"'target'"'"', '"'"'rebuild_governance_lineage_edge'"'"', COUNT(*) FROM datara_rebuild_i0.rebuild_governance_lineage_edge
UNION ALL SELECT '"'"'target'"'"', '"'"'rebuild_governance_quality_rule'"'"', COUNT(*) FROM datara_rebuild_i0.rebuild_governance_quality_rule
UNION ALL SELECT '"'"'target'"'"', '"'"'rebuild_governance_quality_run'"'"', COUNT(*) FROM datara_rebuild_i0.rebuild_governance_quality_run
UNION ALL SELECT '"'"'target'"'"', '"'"'rebuild_governance_semantic_metric'"'"', COUNT(*) FROM datara_rebuild_i0.rebuild_governance_semantic_metric
UNION ALL SELECT '"'"'target'"'"', '"'"'rebuild_governance_standard'"'"', COUNT(*) FROM datara_rebuild_i0.rebuild_governance_standard
UNION ALL SELECT '"'"'target'"'"', '"'"'rebuild_governance_tag'"'"', COUNT(*) FROM datara_rebuild_i0.rebuild_governance_tag;
SELECT '"'"'target'"'"', '"'"'rebuild_governance_migration_batch'"'"', COUNT(*) FROM datara_rebuild_i0.rebuild_governance_migration_batch;
SELECT '"'"'target'"'"', '"'"'rebuild_governance_migration_item'"'"', COUNT(*) FROM datara_rebuild_i0.rebuild_governance_migration_item;
"'
