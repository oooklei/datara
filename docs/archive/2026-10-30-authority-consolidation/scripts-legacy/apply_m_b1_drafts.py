"""M-B1 同步类 9 组件底稿写入（五步循环第 3 步：实现）。

基于 docs/组件基线化/ 设计册第 2 节「八项表单规格（草案）」，把用户已确认的
规格草案构造为完整 BaselineSpec JSON，经 PUT /components/baseline/{type}/draft 写入
t_baseline_progress（status 由 pending → designing）。

与 export_baseline_drafts.py 的关系：
- export_baseline_drafts.py 是机械迁移（formFields→params，showIf 丢弃），产初始底稿；
- 本脚本是语义完整的规格写入（八段全填：inputs/outputs/params/conditions/constraints/
  refs/exports + lineage），产 M-B1 设计底稿。

幂等：进度行已存在且 status=designing（已有 M-B1 底稿）则跳过；status=pending（仅有
机械迁移底稿）则覆盖为语义完整版。

用法（datara-backend 目录下）：
    python scripts/apply_m_b1_drafts.py           # dry-run（打印 9 组件规格摘要）
    python scripts/apply_m_b1_drafts.py --apply   # 实际写库
"""

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


# ---------------------------------------------------------------------------
# 9 个 M-B1 同步类组件的完整八段规格（基于设计册草案 + 用户确认的 8 项决策）
# ---------------------------------------------------------------------------

ENDPOINT_SELECT_SPEC = {
    "form": {
        "inputs": [],
        "outputs": [
            {"key": "sourceRef", "label": "源端表", "uiType": "text", "required": True, "visible": True},
            {"key": "targetRef", "label": "目标端表", "uiType": "text", "required": True, "visible": True},
        ],
        "params": [
            {
                "key": "baseMode",
                "label": "基准类型",
                "uiType": "select",
                "required": True,
                "visible": True,
                "default": "src_base",
                "options": [
                    {"value": "src_base", "label": "源表基准（源端选表）"},
                    {"value": "tgt_base", "label": "目标表基准（目标端选表，源端探测）"},
                    {"value": "file_sync", "label": "文件同步（文件源）"},
                ],
            },
            {
                "key": "srcDs",
                "label": "源数据源",
                "uiType": "resource",
                "required": True,
                "visible": True,
                "group": "源端",
                "cap": {"mode": "datasource", "dsTypes": ["mysql", "greatdb"]},
            },
            {
                "key": "srcTable",
                "label": "源表",
                "uiType": "resource",
                "required": True,
                "visible": True,
                "cap": {"mode": "table", "dsKey": "srcDs", "writeAs": "schemaTable"},
            },
            {
                "key": "probe",
                "label": "联动探测匹配表",
                "uiType": "bool",
                "required": False,
                "visible": True,
                "default": False,
            },
            {
                "key": "matchType",
                "label": "匹配规则",
                "uiType": "select",
                "required": False,
                "visible": True,
                "default": "exact",
                "options": [
                    {"value": "exact", "label": "完全同名"},
                    {"value": "prefix", "label": "前部分命名相同"},
                ],
            },
            {
                "key": "matchPrefix",
                "label": "匹配前缀",
                "uiType": "text",
                "required": False,
                "visible": True,
                "placeholder": "如 ods_order",
            },
            {
                "key": "probeResult",
                "label": "参与 schema/表",
                "uiType": "text",
                "required": False,
                "visible": True,
                "placeholder": "逗号分隔，留空 = 探测全部",
            },
            {
                "key": "filePath",
                "label": "文件路径",
                "uiType": "text",
                "required": True,
                "visible": True,
                "group": "文件源",
                "placeholder": "如 samples/orders.csv",
            },
            {
                "key": "fileType",
                "label": "文件类型",
                "uiType": "select",
                "required": False,
                "visible": True,
                "default": "csv",
                "options": [
                    {"value": "csv", "label": "CSV"},
                    {"value": "txt", "label": "TXT"},
                    {"value": "excel", "label": "Excel"},
                ],
            },
            {
                "key": "fileDelimiter",
                "label": "分隔符",
                "uiType": "text",
                "required": False,
                "visible": True,
                "default": ",",
            },
            {
                "key": "fileEncoding",
                "label": "编码",
                "uiType": "select",
                "required": False,
                "visible": True,
                "default": "utf-8",
                "options": [
                    {"value": "utf-8", "label": "UTF-8"},
                    {"value": "gbk", "label": "GBK"},
                    {"value": "gb18030", "label": "GB18030"},
                ],
            },
            {
                "key": "fileHeaderRows",
                "label": "表头行数",
                "uiType": "number",
                "required": False,
                "visible": True,
                "default": 1,
            },
            {
                "key": "fileSheet",
                "label": "Sheet 名称",
                "uiType": "text",
                "required": False,
                "visible": True,
                "placeholder": "留空 = 首个",
            },
            {
                "key": "tgtDs",
                "label": "目标数据源",
                "uiType": "resource",
                "required": True,
                "visible": True,
                "group": "目标端",
                "cap": {"mode": "datasource", "dsTypes": ["mysql", "greatdb"]},
            },
            # 决策 1：tgtTable 单字段化（双 key 同名分型 → 单字段 + constraints.requiredIf）
            {
                "key": "tgtTable",
                "label": "目标表",
                "uiType": "resource",
                "required": False,
                "visible": True,
                "cap": {"mode": "table", "dsKey": "tgtDs", "writeAs": "schemaTable"},
            },
            {
                "key": "autoCreate",
                "label": "目标表不存在则新建",
                "uiType": "bool",
                "required": False,
                "visible": True,
                "default": True,
            },
        ],
        "conditions": [
            {"id": "c-src-ds", "when": {"field": "baseMode", "op": "ne", "value": "file_sync"}, "show": ["srcDs"]},
            {"id": "c-src-table", "when": {"field": "baseMode", "op": "eq", "value": "src_base"}, "show": ["srcTable"]},
            {"id": "c-probe", "when": {"field": "baseMode", "op": "eq", "value": "tgt_base"}, "show": ["probe"]},
            {"id": "c-match", "when": {"field": "baseMode", "op": "eq", "value": "tgt_base"}, "show": ["matchType"]},
            {"id": "c-prefix", "when": {"field": "matchType", "op": "eq", "value": "prefix"}, "show": ["matchPrefix"]},
            {
                "id": "c-probe-res",
                "when": {"field": "baseMode", "op": "eq", "value": "tgt_base"},
                "show": ["probeResult"],
            },
            {
                "id": "c-file-path",
                "when": {"field": "baseMode", "op": "eq", "value": "file_sync"},
                "show": ["filePath", "fileType", "fileHeaderRows"],
            },
            {
                "id": "c-file-txt",
                "when": {"field": "fileType", "op": "ne", "value": "excel"},
                "show": ["fileDelimiter", "fileEncoding"],
            },
            {"id": "c-file-xls", "when": {"field": "fileType", "op": "eq", "value": "excel"}, "show": ["fileSheet"]},
        ],
        "constraints": [
            {
                "field": "tgtTable",
                "type": "requiredIf",
                "value": {"field": "baseMode", "op": "eq", "value": "tgt_base"},
                "msg": "目标表基准：目标表必选",
            },
            {
                "field": "srcTable",
                "type": "requiredIf",
                "value": {"field": "baseMode", "op": "eq", "value": "src_base"},
                "msg": "源表基准：源表必选",
            },
        ],
        "exclusions": [],
        "refs": [],
        "exports": [],
    },
    "lineage": {"assets": []},
    "render": {
        "icon": "⇤",
        "color": "#0369a1",
        "shape": "card",
        # 决策 2：summary 声明化（旧函数 → render.summaryRules 模板字符串）
        "summary": "同步端点选择（运行时按 baseMode 分型渲染）",
    },
    "dropPolicy": {"snapToGrid": True, "autoName": "endpoint_select_{n}", "maxInstances": 0},
    "paletteVisible": True,
}


FIELD_MAP_SPEC = {
    "form": {
        "inputs": [
            {
                "key": "inputs",
                "label": "输入（上游节点输出）",
                "uiType": "resource",
                "required": True,
                "visible": True,
                "cap": {"mode": "upstreamOutputs", "max": 2},
            },
        ],
        "outputs": [
            {
                "key": "outputs",
                "label": "输出",
                "uiType": "resource",
                "required": False,
                "visible": True,
                "cap": {"mode": "upstreamOutputs", "max": 5},
            },
        ],
        "params": [
            {
                "key": "fieldMap",
                "label": "字段映射",
                "uiType": "mapEditor",
                "required": False,
                "visible": True,
                "cap": {
                    "mode": "columnMap",
                    "srcNodeType": "endpoint_select",
                    "tgtNodeType": "endpoint_select",
                    "srcDsKey": "srcDs",
                    "srcTableKey": "srcTable",
                    "tgtDsKey": "tgtDs",
                    "tgtTableKey": "tgtTable",
                    "fmSrcIndex": 0,
                    "fmTgtIndex": 1,
                },
            },
        ],
        "conditions": [],
        "constraints": [],
        "exclusions": [],
        "refs": [],
        "exports": [],
    },
    "lineage": {"assets": []},
    "render": {
        "icon": "⇄",
        "color": "#0369a1",
        "shape": "card",
        "summary": "字段映射-复制",
    },
    "dropPolicy": {"snapToGrid": True, "autoName": "field_map_{n}"},
    "paletteVisible": True,
}


FIELD_MAP_UNION_SPEC = {
    "form": {
        "inputs": [
            {
                "key": "inputs",
                "label": "输入（上游节点输出）",
                "uiType": "resource",
                "required": True,
                "visible": True,
                "cap": {"mode": "upstreamOutputs", "max": 2},
            },
        ],
        "outputs": [
            {
                "key": "outputs",
                "label": "输出",
                "uiType": "resource",
                "required": False,
                "visible": True,
                "cap": {"mode": "upstreamOutputs", "max": 5},
            },
        ],
        "params": [
            {
                "key": "fieldMap",
                "label": "字段映射",
                "uiType": "mapEditor",
                "required": False,
                "visible": True,
                "cap": {
                    "mode": "columnMap",
                    "srcNodeType": "endpoint_select",
                    "tgtNodeType": "endpoint_select",
                    "srcDsKey": "srcDs",
                    "srcTableKey": "srcTable",
                    "tgtDsKey": "tgtDs",
                    "tgtTableKey": "tgtTable",
                    "fmSrcIndex": 1,
                    "fmTgtIndex": 0,
                },
            },
            {
                "key": "addSchemaFlag",
                "label": "记录来源标识列",
                "uiType": "bool",
                "required": False,
                "visible": True,
                "default": True,
            },
            {
                "key": "srcSchemaField",
                "label": "标识列名",
                "uiType": "text",
                "required": False,
                "visible": True,
                "default": "src_schema",
            },
            {
                "key": "aggOperator",
                "label": "聚合算子",
                "uiType": "select",
                "required": False,
                "visible": True,
                "default": "union_all",
                "options": [
                    {"value": "union_all", "label": "union all 追加合并"},
                    {"value": "union_distinct", "label": "合并去重"},
                ],
            },
        ],
        "conditions": [
            {
                "id": "c-schema-flag",
                "when": {"field": "addSchemaFlag", "op": "eq", "value": True},
                "show": ["srcSchemaField"],
            },
        ],
        "constraints": [],
        "exclusions": [],
        # refs 显式空注记（srcSchemaField 不声明 upstream 引用域，系统追加列语义）
        "refs": [],
        "exports": [],
    },
    "lineage": {"assets": []},
    "render": {
        "icon": "⇉",
        "color": "#0369a1",
        "shape": "card",
        "summary": "字段映射-联合",
    },
    "dropPolicy": {"snapToGrid": True, "autoName": "field_map_union_{n}"},
    "paletteVisible": True,
}


CONDITION_SET_SPEC = {
    "form": {
        "inputs": [
            {
                "key": "inputs",
                "label": "输入（上游节点输出）",
                "uiType": "resource",
                "required": True,
                "visible": True,
                "cap": {"mode": "upstreamOutputs", "max": 3},
            },
        ],
        "outputs": [
            {
                "key": "outputs",
                "label": "输出",
                "uiType": "resource",
                "required": False,
                "visible": True,
                "cap": {"mode": "upstreamOutputs", "max": 3},
            },
        ],
        "params": [
            {
                "key": "filterExpr",
                "label": "筛选条件（WHERE）",
                "uiType": "text",
                "required": False,
                "visible": True,
                "multiline": True,
                "rows": 3,
                "hint": "留空=全量同步；如 create_time > last_sync_time AND status = 1",
            },
            {
                "key": "incrementalColumn",
                "label": "增量列名",
                "uiType": "text",
                "required": False,
                "visible": True,
                "hint": "留空=全量同步；必须是上游真实存在的列",
            },
            {
                "key": "incrementalExpr",
                "label": "增量条件表达式",
                "uiType": "text",
                "required": False,
                "visible": True,
                "placeholder": "如 yyyyMMdd-1",
            },
        ],
        "conditions": [
            {
                "id": "c-incr-expr",
                "when": {"field": "incrementalColumn", "op": "notEmpty"},
                "show": ["incrementalExpr"],
            },
        ],
        "constraints": [],
        "exclusions": [],
        # 决策 4：dataScope 映射 — refs.scopes 含 upstream（增量列值域闸门）
        "refs": [
            {"field": "filterExpr", "scopes": ["wf", "time"]},
            {"field": "incrementalExpr", "scopes": ["time"]},
        ],
        "exports": [],
    },
    "lineage": {"assets": []},
    "render": {
        "icon": "⚿",
        "color": "#0369a1",
        "shape": "card",
        "summary": "条件设定",
    },
    "dropPolicy": {"snapToGrid": True, "autoName": "condition_set_{n}"},
    "paletteVisible": True,
}


SYNC_SPEC = {
    "form": {
        "inputs": [],
        "outputs": [],  # runtimeOnly：无设计态数据面声明
        "params": [
            # 决策 5：常量 text 函数字面量化
            {
                "key": "chainHint",
                "label": "说明",
                "uiType": "hint",
                "required": False,
                "visible": True,
                "default": "数据同步（运行态执行组件，配置经 master 合并自 endpoint_select）",
            },
            {
                "key": "batchSize",
                "label": "批大小",
                "uiType": "number",
                "required": False,
                "visible": True,
                "default": 1000,
            },
            {
                "key": "errorThreshold",
                "label": "错误阈值（坏行容忍条数）",
                "uiType": "number",
                "required": False,
                "visible": True,
                "default": 0,
            },
            {
                "key": "truncate",
                "label": "写入前清空目标（TRUNCATE）",
                "uiType": "bool",
                "required": False,
                "visible": True,
                "default": False,
            },
        ],
        "conditions": [],
        "constraints": [],
        "exclusions": [],
        "refs": [],
        "exports": [
            {"key": "read_rows", "from": "output", "type": "number", "desc": "读取行数"},
            {"key": "write_rows", "from": "output", "type": "number", "desc": "写入行数"},
            {"key": "bad_rows", "from": "output", "type": "number", "desc": "坏行数"},
            {"key": "skipped_rows", "from": "output", "type": "number", "desc": "跳过行数"},
            {"key": "rows_per_sec", "from": "output", "type": "number", "desc": "速率（行/秒）"},
            {"key": "batch_id", "from": "output", "type": "string", "desc": "批次号（=instance_id）"},
            {"key": "schemas_included", "from": "output", "type": "array", "desc": "参与 schema 清单"},
        ],
    },
    "lineage": {
        "assets": [
            # 声明级血缘锚点（动态合并，以数据源引用字段为 pick）
            {"role": "source", "pick": "srcDs", "assetType": "table"},
            {"role": "target", "pick": "tgtDs", "assetType": "table"},
        ]
    },
    "render": {
        "icon": "⇊",
        "color": "#0369a1",
        "shape": "card",
        "summary": "数据同步（运行态，配置经 master 合并）",
    },
    "dropPolicy": {"snapToGrid": True},
    "paletteVisible": False,  # runtimeOnly
}


FILE_SYNC_SPEC = {
    "form": {
        "inputs": [],
        "outputs": [],  # runtimeOnly
        "params": [
            # 决策 5：常量 text 函数字面量化
            {
                "key": "chainHint",
                "label": "说明",
                "uiType": "hint",
                "required": False,
                "visible": True,
                "default": "文件入仓执行（运行态，配置经 master 合并自 endpoint_select baseMode=file_sync）",
            },
            # 决策 6：defaults 并入 params.default
            {
                "key": "writeMode",
                "label": "写入模式",
                "uiType": "select",
                "required": False,
                "visible": True,
                "default": "append",
                "options": [
                    {"value": "append", "label": "追加"},
                    {"value": "overwrite", "label": "覆盖（先 TRUNCATE）"},
                    {"value": "src_flag", "label": "标识列（每行落来源文件标识）"},
                ],
            },
            {
                "key": "flagColumn",
                "label": "标识列名",
                "uiType": "text",
                "required": False,
                "visible": True,
                "default": "src_schema",
            },
            {
                "key": "autoCreate",
                "label": "目标表不存在时自动建表",
                "uiType": "bool",
                "required": False,
                "visible": True,
                "default": True,
            },
            {
                "key": "fieldMap",
                "label": "字段映射（兜底）",
                "uiType": "mapEditor",
                "required": False,
                "visible": True,
                "default": [],
                "cap": {"mode": "columnMap"},
            },
        ],
        "conditions": [
            {
                "id": "c-flag-col",
                "when": {"field": "writeMode", "op": "eq", "value": "src_flag"},
                "show": ["flagColumn"],
            },
        ],
        "constraints": [],
        "exclusions": [],
        "refs": [],
        "exports": [
            {"key": "rows_read", "from": "output", "type": "number", "desc": "读取行数"},
            {"key": "rows_written", "from": "output", "type": "number", "desc": "写入行数"},
            {"key": "rows_skipped", "from": "output", "type": "number", "desc": "忽略行数"},
            {"key": "batch_id", "from": "output", "type": "string", "desc": "批次号（=instance_id）"},
        ],
    },
    "lineage": {
        "assets": [
            {"role": "source", "pick": "filePath", "assetType": "file"},
            {"role": "target", "pick": "tgtDs", "assetType": "table"},
        ]
    },
    "render": {
        "icon": "⇣",
        "color": "#0369a1",
        "shape": "card",
        "summary": "文件入仓执行（运行态，配置经 master 合并）",
    },
    "dropPolicy": {"snapToGrid": True},
    "paletteVisible": False,  # runtimeOnly
}


def _template_spec(
    key: str, label: str, desc: str, base_mode: str, fmap_type: str, icon: str, add_schema: bool = None
) -> dict:
    """构造 src_base / tgt_base / file_sync 编排模板的声明式 chain。"""
    nodes = [
        {"id": "n_start", "type": "start"},
        {"id": "n_cleanup", "type": "shell", "data": {"name": "前置清理"}},
        {"id": "n_endpoint", "type": "endpoint_select", "data": {"baseMode": base_mode}},
        {"id": "n_fmap", "type": fmap_type},
        {"id": "n_cond", "type": "condition_set"},
        {"id": "n_assert", "type": "assert"},
        {"id": "n_end", "type": "end"},
    ]
    edges = [
        {"source": "n_start", "target": "n_cleanup"},
        {"source": "n_cleanup", "target": "n_endpoint"},
        {"source": "n_endpoint", "target": "n_fmap"},
        {"source": "n_fmap", "target": "n_cond"},
        {"source": "n_cond", "target": "n_assert"},
        {"source": "n_assert", "sourceHandle": "success", "target": "n_end"},
    ]
    # tgt_base 用 field_map_union 带初始数据
    if fmap_type == "field_map_union":
        nodes[3] = {
            "id": "n_fmap",
            "type": "field_map_union",
            "data": {"addSchemaFlag": True, "aggOperator": "union_all"},
        }
    # tgt_base 含探测配置
    if base_mode == "tgt_base":
        nodes[2] = {"id": "n_endpoint", "type": "endpoint_select", "data": {"baseMode": "tgt_base", "probe": True}}

    return {
        "form": {
            "inputs": [],
            "outputs": [],
            "params": [],
            "conditions": [],
            "constraints": [],
            "exclusions": [],
            "refs": [],
            "exports": [],
        },
        "lineage": {"assets": []},
        "render": {
            "icon": icon,
            "color": "#0369a1",
            "shape": "card",
            "summary": "%s（编排模板）" % label,
        },
        # 决策 8：模板链声明化（build 函数 → template.chain）
        "template": {
            "modes": [
                {
                    "key": key,
                    "label": label,
                    "desc": desc,
                    "chain": {"nodes": nodes, "edges": edges},
                    "hooks": {"assertFailNotify": "消息通知节点接入位（对账不通过）"},
                }
            ],
        },
        "dropPolicy": {"snapToGrid": True, "autoName": "%s_{n}" % key},
        "paletteVisible": True,
    }


M_B1_SPECS = {
    "endpoint_select": ENDPOINT_SELECT_SPEC,
    "field_map": FIELD_MAP_SPEC,
    "field_map_union": FIELD_MAP_UNION_SPEC,
    "condition_set": CONDITION_SET_SPEC,
    "sync": SYNC_SPEC,
    "file_sync": FILE_SYNC_SPEC,
    "src_base_orch": _template_spec(
        "src_base", "源表基准", "已知源库表 → 目标表（可新建），字段复制映射 + 筛选条件", "src_base", "field_map", "⇥"
    ),
    "tgt_base_orch": _template_spec(
        "tgt_base",
        "目标表基准",
        "以目标表为基准探测多 schema 源表，union all 联合 + 来源标识",
        "tgt_base",
        "field_map_union",
        "⇤",
    ),
    "file_sync_orch": _template_spec(
        "file_sync", "文件同步", "CSV/TXT/Excel 文件 → 库表入仓，字段复制映射 + 筛选条件", "file_sync", "field_map", "⇣"
    ),
}


def main() -> None:
    parser = argparse.ArgumentParser(description="M-B1 同步类 9 组件底稿写入（五步循环第 3 步）")
    parser.add_argument("--apply", action="store_true", help="实际写库（缺省 dry-run）")
    args = parser.parse_args()

    print("M-B1 同步类 9 组件底稿写入")
    print("=" * 60)
    for type_name, spec in M_B1_SPECS.items():
        param_count = len(spec["form"]["params"])
        inputs_count = len(spec["form"]["inputs"])
        outputs_count = len(spec["form"]["outputs"])
        cond_count = len(spec["form"]["conditions"])
        has_template = "template" in spec
        print(
            f"  {type_name:20s} inputs={inputs_count} outputs={outputs_count} "
            f"params={param_count} conditions={cond_count} template={has_template}"
        )

    if not args.apply:
        print("\n[dry-run] 未写库；确认后加 --apply 执行")
        return

    from common.db import new_session
    from common.models import BaselineProgress

    session = new_session()
    created = overwritten = skipped = 0
    try:
        for type_name, spec in M_B1_SPECS.items():
            row = session.query(BaselineProgress).filter(BaselineProgress.type == type_name).first()
            spec_json = json.dumps(spec, ensure_ascii=False)
            if row is None:
                row = BaselineProgress(
                    type=type_name,
                    status="designing",
                    draft_spec=spec_json,
                    draft_rev=1,
                )
                session.add(row)
                created += 1
            elif row.status == "pending":
                # 仅有机械迁移底稿 → 覆盖为语义完整版
                row.draft_spec = spec_json
                row.draft_rev += 1
                row.status = "designing"
                overwritten += 1
            else:
                # status=designing → 已有 M-B1 底稿，跳过
                skipped += 1
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    print(f"\n[apply] 新建 {created}，覆盖 pending→designing {overwritten}，跳过已有 {skipped}（共 9）")


if __name__ == "__main__":
    main()
