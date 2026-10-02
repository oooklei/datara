"""M-B2 ETL/计算类 9 组件底稿写入（五步循环第 3 步：实现）。

基于 docs/组件基线化/ 设计册第 2 节「八项表单规格（草案）」，把用户已确认的
规格草案构造为完整 BaselineSpec JSON，经 PUT /components/baseline/{type}/draft 写入
t_baseline_progress（status 由 pending → designing）。

用法（datara-backend 目录下）：
    python scripts/apply_m_b2_drafts.py           # dry-run（打印 9 组件规格摘要）
    python scripts/apply_m_b2_drafts.py --apply   # 实际写库
"""

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


# ---------------------------------------------------------------------------
# 9 个 M-B2 ETL/计算类组件的完整八段规格
# ---------------------------------------------------------------------------

SQL_SPEC = {
    "form": {
        "inputs": [], "outputs": [],
        "params": [
            {"key": "datasource", "label": "数据源", "uiType": "resource", "required": False, "visible": True,
             "cap": {"mode": "datasource", "dsTypes": ["mysql", "greatdb"]}},
            {"key": "sqlInsert", "label": "库/表侧栏选择器（点选插入，不替代手写）", "uiType": "mapEditor",
             "required": False, "visible": True, "cap": {"mode": "sqlInsert", "dsKey": "datasource"}},
            {"key": "sql", "label": "SQL 语句", "uiType": "text", "required": False, "visible": True, "multiline": True, "rows": 5},
            {"key": "pre", "label": "前置 SQL", "uiType": "text", "required": False, "visible": True, "multiline": True, "rows": 3},
            {"key": "post", "label": "后置 SQL", "uiType": "text", "required": False, "visible": True, "multiline": True, "rows": 3},
        ],
        "conditions": [
            {"id": "c-sql-insert", "when": {"field": "datasource", "op": "notEmpty"}, "show": ["sqlInsert"]},
        ],
        "constraints": [], "exclusions": [], "refs": [],
        "exports": [
            {"key": "results", "from": "output", "type": "array", "desc": "全语句摘要"},
            {"key": "row_count", "from": "output", "type": "number", "desc": "主查询行数"},
            {"key": "result_preview", "from": "output", "type": "object", "desc": "主查询预览（columns + rows）"},
            {"key": "lineage_edges", "from": "output", "type": "number", "desc": "血缘边数"},
            {"key": "lineage_fields", "from": "output", "type": "number", "desc": "血缘字段数"},
        ],
    },
    "lineage": {"assets": [
        {"role": "source", "pick": "datasource", "assetType": "table"},
        {"role": "target", "pick": "datasource", "assetType": "table"},
    ]},
    "render": {"icon": "⌨", "color": "#334155", "shape": "card", "summary": "SQL（查询/非查询/DDL，多语句顺序执行）"},
    "dropPolicy": {"snapToGrid": True, "autoName": "sql_{n}"},
    "paletteVisible": True,
}

SHELL_SPEC = {
    "form": {
        "inputs": [], "outputs": [],
        "params": [
            {"key": "script", "label": "脚本内容", "uiType": "text", "required": False, "visible": True, "multiline": True, "rows": 8},
            {"key": "env", "label": "环境变量（键值表，注入子进程）", "uiType": "rows", "required": False, "visible": True},
        ],
        "conditions": [], "constraints": [], "exclusions": [], "refs": [],
        "exports": [{"key": "stdout", "from": "output", "type": "object", "desc": "解析后的键值对输出"}],
    },
    "lineage": {"assets": [
        {"role": "source", "pick": "script", "assetType": "file"},
        {"role": "target", "pick": "script", "assetType": "file"},
    ]},
    "render": {"icon": "❯", "color": "#7c3aed", "shape": "card", "summary": "Shell（bash 脚本执行）"},
    "dropPolicy": {"snapToGrid": True, "autoName": "shell_{n}"},
    "paletteVisible": True,
}

PYTHON_SPEC = {
    "form": {
        "inputs": [], "outputs": [],
        "params": [
            {"key": "script", "label": "脚本内容", "uiType": "text", "required": False, "visible": True, "multiline": True, "rows": 8},
            {"key": "env", "label": "环境变量（键值表，注入子进程）", "uiType": "rows", "required": False, "visible": True},
            {"key": "requirements", "label": "依赖清单（requirements.txt 格式，仅校验/留痕）", "uiType": "text", "required": False, "visible": True, "multiline": True, "rows": 3},
            {"key": "requirementsHint", "label": "依赖需预装镜像层", "uiType": "hint", "required": False, "visible": True, "default": "依赖需预装镜像层，本期仅校验格式并打印日志提示"},
        ],
        "conditions": [], "constraints": [], "exclusions": [], "refs": [],
        "exports": [{"key": "stdout", "from": "output", "type": "object", "desc": "解析后的键值对输出"}],
    },
    "lineage": {"assets": [
        {"role": "source", "pick": "script", "assetType": "file"},
        {"role": "target", "pick": "script", "assetType": "file"},
    ]},
    "render": {"icon": "Py", "color": "#2563eb", "shape": "card", "summary": "Python（解释器执行脚本）"},
    "dropPolicy": {"snapToGrid": True, "autoName": "python_{n}"},
    "paletteVisible": True,
}

SSH_SPEC = {
    "form": {
        "inputs": [], "outputs": [],
        "params": [
            {"key": "execNodeTag", "label": "执行节点标签", "uiType": "select", "required": False, "visible": True, "options": []},
            {"key": "runtimeNode", "label": "运行时节点", "uiType": "resource", "required": False, "visible": True, "cap": {"mode": "runtimeNode"}},
            {"key": "script", "label": "脚本内容", "uiType": "text", "required": False, "visible": True, "multiline": True, "rows": 8},
        ],
        "conditions": [
            {"id": "c-runtime-node", "when": {"field": "execNodeTag", "op": "empty"}, "show": ["runtimeNode"]},
        ],
        "constraints": [], "exclusions": [], "refs": [],
        "exports": [{"key": "stdout", "from": "output", "type": "object", "desc": "解析后的键值对输出"}],
    },
    "lineage": {"assets": [
        {"role": "source", "pick": "script", "assetType": "file"},
        {"role": "target", "pick": "script", "assetType": "file"},
    ]},
    "render": {"icon": "⌖", "color": "#475569", "shape": "card", "summary": "SSH 脚本（I7 标签路由 + 运行时节点）"},
    "dropPolicy": {"snapToGrid": True, "autoName": "ssh_{n}"},
    "paletteVisible": True,
}

PROCEDURE_SPEC = {
    "form": {
        "inputs": [], "outputs": [],
        "params": [
            {"key": "datasource", "label": "数据源", "uiType": "resource", "required": False, "visible": True, "cap": {"mode": "datasource", "dsTypes": ["mysql", "greatdb"]}},
            {"key": "db", "label": "目标库（留空 = 数据源默认库）", "uiType": "text", "required": False, "visible": True},
            {"key": "procedure", "label": "过程名", "uiType": "text", "required": False, "visible": True},
            {"key": "args", "label": "过程参数（IN 传值 / OUT 回读）", "uiType": "rows", "required": False, "visible": True},
        ],
        "conditions": [], "constraints": [], "exclusions": [], "refs": [],
        "exports": [
            {"key": "affected", "from": "output", "type": "number", "desc": "影响行数"},
            {"key": "out_{key}", "from": "output", "type": "string", "desc": "OUT 参数值（动态键）"},
        ],
    },
    "lineage": {"assets": [
        {"role": "source", "pick": "datasource", "assetType": "table"},
        {"role": "target", "pick": "datasource", "assetType": "table"},
    ]},
    "render": {"icon": "⚙", "color": "#6d28d9", "shape": "card", "summary": "存储过程（CALL，OUT 参数注册 out_{key}）"},
    "dropPolicy": {"snapToGrid": True, "autoName": "procedure_{n}"},
    "paletteVisible": True,
}

HTTP_SPEC = {
    "form": {
        "inputs": [], "outputs": [],
        "params": [
            {"key": "url", "label": "URL", "uiType": "text", "required": False, "visible": True},
            {"key": "method", "label": "方法", "uiType": "select", "required": False, "visible": True, "default": "GET",
             "options": [{"value": "GET", "label": "GET"}, {"value": "HEAD", "label": "HEAD"}, {"value": "POST", "label": "POST"}, {"value": "PUT", "label": "PUT"}, {"value": "DELETE", "label": "DELETE"}, {"value": "PATCH", "label": "PATCH"}]},
            {"key": "headers", "label": "请求头（键值表）", "uiType": "rows", "required": False, "visible": True},
            {"key": "bodyType", "label": "请求体类型", "uiType": "select", "required": False, "visible": True, "default": "json",
             "options": [{"value": "json", "label": "JSON"}, {"value": "form", "label": "Form"}]},
            {"key": "body", "label": "请求体", "uiType": "text", "required": False, "visible": True, "multiline": True, "rows": 3},
            {"key": "successCodes", "label": "成功状态码", "uiType": "text", "required": False, "visible": True, "default": "2xx"},
            {"key": "extract", "label": "响应提取（输出名 → 点路径）", "uiType": "rows", "required": False, "visible": True},
            {"key": "timeout", "label": "超时（秒）", "uiType": "number", "required": False, "visible": True, "default": 30},
        ],
        "conditions": [
            {"id": "c-body-type", "when": {"field": "method", "op": "notIn", "value": ["GET", "HEAD"]}, "show": ["bodyType"]},
            {"id": "c-body", "when": {"field": "method", "op": "notIn", "value": ["GET", "HEAD"]}, "show": ["body"]},
        ],
        "constraints": [], "exclusions": [], "refs": [],
        "exports": [
            {"key": "status_code", "from": "output", "type": "number", "desc": "HTTP 状态码"},
            {"key": "{extract_name}", "from": "output", "type": "string", "desc": "提取的响应子集（动态键）"},
        ],
    },
    "lineage": {"assets": [
        {"role": "source", "pick": "url", "assetType": "file"},
        {"role": "target", "pick": "url", "assetType": "file"},
    ]},
    "render": {"icon": "⊕", "color": "#4f46e5", "shape": "card", "summary": "HTTP（成功码校验 + 点路径提取）"},
    "dropPolicy": {"snapToGrid": True, "autoName": "http_{n}"},
    "paletteVisible": True,
}

FILE_SPEC = {
    "form": {
        "inputs": [], "outputs": [],
        "params": [
            {"key": "mode", "label": "来源模式", "uiType": "select", "required": False, "visible": True, "default": "datasource",
             "options": [{"value": "datasource", "label": "数据源中心文件源"}, {"value": "manual", "label": "手动参数"}]},
            {"key": "datasource", "label": "文件源数据源", "uiType": "resource", "required": False, "visible": True, "cap": {"mode": "datasource", "dsTypes": ["file"]}},
            {"key": "path", "label": "文件路径（/datara/files 相对）", "uiType": "text", "required": False, "visible": True},
            {"key": "format", "label": "格式", "uiType": "select", "required": False, "visible": True,
             "options": [{"value": "csv", "label": "CSV"}, {"value": "excel", "label": "Excel"}, {"value": "txt", "label": "TXT"}]},
            {"key": "encoding", "label": "编码", "uiType": "select", "required": False, "visible": True, "default": "utf-8",
             "options": [{"value": "utf-8", "label": "UTF-8"}, {"value": "gbk", "label": "GBK"}, {"value": "utf-8-sig", "label": "UTF-8-SIG"}]},
            {"key": "delimiter", "label": "分隔符", "uiType": "text", "required": False, "visible": True, "default": ","},
            {"key": "header", "label": "首行表头", "uiType": "bool", "required": False, "visible": True, "default": True},
            {"key": "sheet", "label": "Sheet 名称（留空 = 首个）", "uiType": "text", "required": False, "visible": True},
            {"key": "register", "label": "注册临时数据", "uiType": "bool", "required": False, "visible": True, "default": True},
            {"key": "tmpName", "label": "临时数据名", "uiType": "text", "required": False, "visible": True, "placeholder": "匹配 ^[a-z][a-z0-9_]{2,31}$"},
            {"key": "kind", "label": "临时数据形态", "uiType": "select", "required": False, "visible": True, "default": "table",
             "options": [{"value": "table", "label": "表（批量物化）"}, {"value": "resultset", "label": "结果集（抽样 JSON）"}, {"value": "file", "label": "文件（登记路径）"}]},
            {"key": "targetDs", "label": "物化目标数据源", "uiType": "resource", "required": False, "visible": True, "cap": {"mode": "datasource", "dsTypes": ["mysql", "greatdb"]}},
            {"key": "retention", "label": "保留策略", "uiType": "select", "required": False, "visible": True, "default": "immediate",
             "options": [{"value": "immediate", "label": "立即清扫"}, {"value": "days", "label": "保留天数"}, {"value": "keep", "label": "永久保留"}]},
            {"key": "keepDays", "label": "保留天数", "uiType": "number", "required": False, "visible": True, "default": 0},
            {"key": "keepHint", "label": "保留策略说明", "uiType": "hint", "required": False, "visible": True, "default": "立即清扫=任务结束即删；保留天数=N 天后清扫；永久保留=不自动清扫"},
            {"key": "tmpHint", "label": "临时数据说明", "uiType": "hint", "required": False, "visible": True, "default": "注册后下游以 tmp.名称 变量引用"},
        ],
        "conditions": [
            {"id": "c-datasource", "when": {"field": "mode", "op": "eq", "value": "datasource"}, "show": ["datasource"]},
            {"id": "c-manual", "when": {"field": "mode", "op": "eq", "value": "manual"}, "show": ["path", "format", "encoding", "delimiter", "header", "sheet"]},
            {"id": "c-register", "when": {"field": "register", "op": "eq", "value": True}, "show": ["tmpName", "kind", "targetDs", "retention", "keepDays", "keepHint", "tmpHint"]},
        ],
        "constraints": [], "exclusions": [], "refs": [],
        "exports": [
            {"key": "rows_count", "from": "output", "type": "number", "desc": "数据行数"},
            {"key": "columns", "from": "output", "type": "number", "desc": "列数"},
            {"key": "tmp_name", "from": "output", "type": "string", "desc": "临时数据名"},
        ],
    },
    "lineage": {"assets": [
        {"role": "source", "pick": "path", "assetType": "file"},
        {"role": "target", "pick": "targetDs", "assetType": "table"},
    ]},
    "render": {"icon": "▦", "color": "#0e7490", "shape": "card", "summary": "文件读取（CSV/TXT/Excel → 临时工作数据）"},
    "dropPolicy": {"snapToGrid": True, "autoName": "file_{n}"},
    "paletteVisible": True,
}

ASSERT_SPEC = {
    "form": {
        "inputs": [], "outputs": [],
        "params": [
            {"key": "assertSrc", "label": "校验对象", "uiType": "select", "required": False, "visible": True, "default": "manual",
             "options": [{"value": "manual", "label": "手选数据源/表"}, {"value": "upstream", "label": "上游节点引用"}]},
            {"key": "assertUpstream", "label": "上游节点引用（可选）", "uiType": "resource", "required": False, "visible": True, "cap": {"mode": "upstreamOutputs"}},
            {"key": "assertDs", "label": "校验数据源", "uiType": "resource", "required": True, "visible": True, "cap": {"mode": "datasource", "dsTypes": ["mysql", "greatdb"]}},
            {"key": "assertTable", "label": "校验表（schema → 表）", "uiType": "resource", "required": True, "visible": True, "cap": {"mode": "table", "dsKey": "assertDs", "writeAs": "schemaTable"}},
            {"key": "rules", "label": "规则集（key=规则，value=参数）", "uiType": "rows", "required": True, "visible": True},
            {"key": "ruleColumns", "label": "规则列参考（手选表字段，可选）", "uiType": "resource", "required": False, "visible": True, "cap": {"mode": "table", "dsKey": "assertDs", "writeAs": "schemaTable"}},
            {"key": "rulesHint", "label": "规则说明", "uiType": "hint", "required": False, "visible": True, "default": "行数区间/主键唯一/非空率/自定义 SQL 断言"},
            {"key": "onFail", "label": "不达标动作", "uiType": "select", "required": False, "visible": True, "default": "fail",
             "options": [{"value": "fail", "label": "断流失败"}, {"value": "warn", "label": "告警放行"}]},
        ],
        "conditions": [
            {"id": "c-upstream", "when": {"field": "assertSrc", "op": "eq", "value": "upstream"}, "show": ["assertUpstream"]},
            {"id": "c-manual", "when": {"field": "assertSrc", "op": "eq", "value": "manual"}, "show": ["assertDs", "assertTable", "ruleColumns"]},
        ],
        "constraints": [], "exclusions": [], "refs": [],
        "exports": [
            {"key": "assert_ok", "from": "output", "type": "bool", "desc": "校验是否通过"},
            {"key": "failed", "from": "output", "type": "array", "desc": "不通过的规则列表"},
        ],
    },
    "lineage": {"assets": [
        {"role": "source", "pick": "assertDs", "assetType": "table"},
        {"role": "target", "pick": "assertTable", "assetType": "table"},
    ]},
    "render": {"icon": "⚑", "color": "#dc2626", "shape": "card", "summary": "数据校验（行数/主键/非空率/SQL 断言）"},
    "dropPolicy": {"snapToGrid": True, "autoName": "assert_{n}"},
    "paletteVisible": True,
}

NOTIFY_SPEC = {
    "form": {
        "inputs": [], "outputs": [],
        "params": [
            {"key": "channel", "label": "通道", "uiType": "select", "required": False, "visible": True, "default": "log",
             "options": [{"value": "log", "label": "仅日志"}, {"value": "webhook", "label": "Webhook"}]},
            {"key": "url", "label": "Webhook URL", "uiType": "text", "required": True, "visible": True},
            {"key": "trigger", "label": "触发时机", "uiType": "select", "required": False, "visible": True, "default": "on_success",
             "options": [{"value": "on_success", "label": "成功时"}, {"value": "on_failure", "label": "失败时"}, {"value": "always", "label": "总是"}]},
            {"key": "template", "label": "消息模板", "uiType": "text", "required": False, "visible": True, "multiline": True, "rows": 3},
            {"key": "notifyHint", "label": "内置变量提示", "uiType": "hint", "required": False, "visible": True, "default": "内置变量：wf.name / instance_id / node.name / sys.now"},
            {"key": "failHard", "label": "通知失败断流", "uiType": "bool", "required": False, "visible": True, "default": False},
        ],
        "conditions": [
            {"id": "c-webhook-url", "when": {"field": "channel", "op": "eq", "value": "webhook"}, "show": ["url"]},
        ],
        "constraints": [], "exclusions": [], "refs": [],
        "exports": [
            {"key": "notified", "from": "output", "type": "bool", "desc": "是否已通知"},
            {"key": "error", "from": "output", "type": "string", "desc": "错误信息（failHard=true 时）"},
        ],
    },
    "lineage": {"assets": [
        {"role": "source", "pick": "channel", "assetType": "file"},
        {"role": "target", "pick": "channel", "assetType": "file"},
    ]},
    "render": {"icon": "✉", "color": "#7c3aed", "shape": "card", "summary": "通知（webhook POST / 仅日志）"},
    "dropPolicy": {"snapToGrid": True, "autoName": "notify_{n}"},
    "paletteVisible": True,
}

M_B2_SPECS = {
    "sql": SQL_SPEC,
    "shell": SHELL_SPEC,
    "python": PYTHON_SPEC,
    "ssh": SSH_SPEC,
    "procedure": PROCEDURE_SPEC,
    "http": HTTP_SPEC,
    "file": FILE_SPEC,
    "assert": ASSERT_SPEC,
    "notify": NOTIFY_SPEC,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="M-B2 ETL/计算类 9 组件底稿写入（五步循环第 3 步）")
    parser.add_argument("--apply", action="store_true", help="实际写库（缺省 dry-run）")
    args = parser.parse_args()

    print("M-B2 ETL/计算类 9 组件底稿写入")
    print("=" * 60)
    for type_name, spec in M_B2_SPECS.items():
        param_count = len(spec["form"]["params"])
        inputs_count = len(spec["form"]["inputs"])
        outputs_count = len(spec["form"]["outputs"])
        cond_count = len(spec["form"]["conditions"])
        lineage_count = len(spec["lineage"]["assets"])
        export_count = len(spec["form"]["exports"])
        print(f"  {type_name:20s} inputs={inputs_count} outputs={outputs_count} "
              f"params={param_count} conditions={cond_count} lineage={lineage_count} exports={export_count}")

    if not args.apply:
        print("\n[dry-run] 未写库；确认后加 --apply 执行")
        return

    # DB 连接走 common.config.get_settings().db_url（容器 env / 本机配置），脚本自身不做环境覆盖
    from common.db import new_session
    from common.models import BaselineProgress

    session = new_session()
    created = overwritten = skipped = 0
    try:
        for type_name, spec in M_B2_SPECS.items():
            row = session.query(BaselineProgress).filter(BaselineProgress.type == type_name).first()
            spec_json = json.dumps(spec, ensure_ascii=False)
            if row is None:
                row = BaselineProgress(
                    type=type_name, status="designing",
                    draft_spec=spec_json, draft_rev=1,
                )
                session.add(row)
                created += 1
            elif row.status == "pending":
                row.draft_spec = spec_json
                row.draft_rev += 1
                row.status = "designing"
                overwritten += 1
            else:
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