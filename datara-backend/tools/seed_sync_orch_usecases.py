#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""同步编排端点合一用例种子脚本：预置多 schema 数据 + 清理旧同步流 + 建 3 个预制同步工作流。

工作流结构（端点合一新拓扑，设计态画布不含执行组件；master 装载 doc 时
materialize_sync_exec 在 assert 入边处自动物化 sys_exec 执行节点，执行类型按
endpoint_select.baseMode 分拣，配置沿入边向上合并进执行参数）：
  源表基准：start → sql(清理) → endpoint_select(src_base) → field_map → condition_set → assert → end（不通过→notify）
  目标表基准：start → sql(清理) → endpoint_select(tgt_base) → field_map_union → condition_set → assert → end（不通过→notify）
  文件同步：start → sql(清理) → endpoint_select(file_sync) → field_map → condition_set → assert → end（不通过→notify）

幂等可重跑：多 schema 数据每次重置为各 5 行；用例先删后建保证最新图。
用法（服务器/容器内，需能连 MySQL）：
  python tools/seed_sync_orch_usecases.py
"""
import json

from sqlalchemy import func

from common.db import init_db, new_session
from common.dsconn import open_connection
from common.models import DataSource, WfDefinition, WfDefinitionLog

SRC_DS = "内置源库-ec_retail"
DW_DS = "内置数仓-datara_dw"
TAGS = ["同步"]

# 旧同步类节点 type 全集（已废弃的专业组件 + 旧单节点执行器 + 旧细项端点）：graph 命中即删。
# 注：field_map/field_map_union/condition_set 为端点合一新拓扑仍在用的配置组件，不在清理范围
OLD_NODE_TYPES = {
    "sync", "sync_template", "file_sync",
    "src_base_orchestration", "tgt_base_orchestration", "file_sync_orchestration",
    "src_select", "tgt_select",
}


# ---------- GraphDocument 构建 ----------

def node(uid, ntype, name, data, x=0, y=100):
    item = {"id": uid, "type": ntype, "position": {"x": x, "y": y}, "data": dict(data)}
    item["data"]["name"] = name
    return item


def edge(sid, tid, source_handle=None, ekind="flow", label=None):
    """GEdge（前端口径）：id/source/target/kind/sourceHandle/label；分支边带 kind+handle+label。"""
    e = {"id": "e_%s_%s" % (sid, tid), "source": sid, "target": tid, "kind": ekind}
    if source_handle:
        e["sourceHandle"] = source_handle
    if label:
        e["label"] = label
    return e


def chain_doc(wf_id, name, middle):
    """开始 → middle(sql/端点/映射/条件/对账) → 结束 + 消息通知。

    assert 双分支出口（GEdge 口径）：「通过」branch_true/success → end、「不通过」
    branch_false/failure → notify；engine 断言结果 chosen={id:success|failure} 经
    sourceHandle（branch.id）/label（branch.name）匹配路由，kind 为前端结构字段。
    """
    nodes = [node("nd_start", "start", "开始", {}, 100)]
    x = 300
    for item in middle:
        item["position"]["x"] = x  # 中段节点横向依次排开，避免画布坐标重叠
        nodes.append(item)
        x += 220
    nodes.append(node("nd_end", "end", "结束", {}, x))
    nodes.append(node("nd_notify", "notify", "消息通知",
                      {"template": "同步对账未通过"}, x, 260))
    edges = []
    for i in range(len(nodes) - 3):  # 主链线性连线：start → … → assert（末两位 end/notify 走分支出边）
        # 端点选择双输出口（§3.2）：ep→map 主链边与用户从源端表口拖边同形态，edge↔inputs 自洽
        # （UI 删边时 onEdgeRemoved 按 "nd_ep:sourceRef" 清引用）；flow 边 sourceHandle 运行时不被引擎消费
        edges.append(edge(nodes[i]["id"], nodes[i + 1]["id"],
                          "sourceRef" if nodes[i]["type"] == "endpoint_select" else None))
    edges.append(edge("nd_assert", "nd_end", "success", "branch_true", "通过"))
    edges.append(edge("nd_assert", "nd_notify", "failure", "branch_false", "不通过"))
    return {"id": wf_id, "name": name, "version": 1, "meta": {"profile": "dag"},
            "nodes": nodes, "edges": edges}


def sql_cleanup(table):
    """前置清理节点（数仓 DROP 目标表，配合执行节点 autoCreate 重建）。"""
    return node("nd_prep", "sql", "前置清理", {
        "datasource": DW_DS, "pre": "", "post": "",
        "sql": "DROP TABLE IF EXISTS %s" % table,
    })


def assert_node():
    return node("nd_assert", "assert", "对账校验", {
        "assertSrc": "upstream",
        "rules": [{"key": "rows", "value": "min=1"}],
        # onFail=warn 告警继续：不达标走「不通过」出口触发通知不断流；engine 缺省 fail 会使节点 FAILURE、下游全跳过，notify 分支永不激活，勿改回 fail
        "onFail": "warn",
    })


def doc_src_base(wf_id):
    """源表基准：endpoint_select(src_base) 单端点（源表精确 + 目标端 autoCreate），
    运行时物化 sync 执行（filterExpr → readerWhere 过滤）。"""
    return chain_doc(wf_id, "源表基准同步编排用例", [
        sql_cleanup("ods_order_sync"),
        node("nd_ep", "endpoint_select", "端点选择", {
            "baseMode": "src_base", "srcDs": SRC_DS, "srcTable": "ods_order",
            "tgtDs": DW_DS, "tgtTable": "ods_order_sync", "autoCreate": True}),
        node("nd_map", "field_map", "字段映射-复制",
             {"inputs": ["nd_ep:sourceRef"], "fieldMap": []}),
        node("nd_cond", "condition_set", "条件设定",
             {"inputs": ["nd_map:"], "filterExpr": "status = 'PAID'"}),
        assert_node(),
    ])


def doc_tgt_base(wf_id):
    """目标表基准：endpoint_select(tgt_base) probeResult 数组直写 3 个源 schema，
    运行时物化 sync 执行 + field_map_union 加 schema 标识列（→ src_flag）。"""
    return chain_doc(wf_id, "目标表基准同步编排用例", [
        sql_cleanup("ods_order_multi"),
        node("nd_ep", "endpoint_select", "端点选择", {
            "baseMode": "tgt_base", "srcDs": SRC_DS, "probe": True, "matchType": "exact",
            "tgtDs": DW_DS, "tgtTable": "ods_order_multi",
            "probeResult": [{"schema": "ec_retail", "table": "ods_order"},
                            {"schema": "ec_retail_east", "table": "ods_order"},
                            {"schema": "ec_retail_south", "table": "ods_order"}]}),
        node("nd_map", "field_map_union", "字段映射-联合",
             {"inputs": ["nd_ep:sourceRef"], "fieldMap": [], "addSchemaFlag": True,
              "srcSchemaField": "src_schema", "aggOperator": "union_all"}),
        node("nd_cond", "condition_set", "条件设定", {"inputs": ["nd_map:"]}),
        assert_node(),
    ])


def doc_file_sync(wf_id):
    """文件同步：endpoint_select(file_sync) 文件源细项键直写，
    运行时物化 file_sync 执行入仓。"""
    return chain_doc(wf_id, "文件同步编排用例", [
        sql_cleanup("ods_order_file"),
        node("nd_ep", "endpoint_select", "端点选择", {
            "baseMode": "file_sync", "filePath": "samples/orders_part.csv", "fileType": "csv",
            "fileDelimiter": ",", "fileEncoding": "utf-8", "fileHeaderRows": 1,
            "tgtDs": DW_DS, "tgtTable": "ods_order_file", "autoCreate": True}),
        node("nd_map", "field_map", "字段映射-复制",
             {"inputs": ["nd_ep:sourceRef"], "fieldMap": []}),
        node("nd_cond", "condition_set", "条件设定", {"inputs": ["nd_map:"]}),
        assert_node(),
    ])


WORKFLOWS = [
    ("wf_orch_src_base", "源表基准同步编排用例", doc_src_base),
    ("wf_orch_tgt_base", "目标表基准同步编排用例", doc_tgt_base),
    ("wf_orch_file_sync", "文件同步编排用例", doc_file_sync),
]


# ---------- 数据预置 / 清理 / 建流 ----------

def preset_schemas():
    """源库预置 ec_retail_east/south 多 schema 测试数据（幂等：每次重置为各 5 行）。"""
    session = new_session()
    try:
        ds = (
            session.query(DataSource)
            .filter(DataSource.name.like("%源库%"), DataSource.type == "mysql")
            .first()
        )
    finally:
        session.close()
    if ds is None:
        print("[seed-orch] 未找到名称含「源库」的 mysql 数据源，跳过 schema 预置")
        return
    conn = open_connection(ds)
    try:
        with conn.cursor() as cur:
            for suffix in ("east", "south"):
                schema = "ec_retail_%s" % suffix
                cur.execute("CREATE DATABASE IF NOT EXISTS `%s`" % schema)
                cur.execute("CREATE TABLE IF NOT EXISTS `%s`.ods_order LIKE ec_retail.ods_order" % schema)
                cur.execute("TRUNCATE TABLE `%s`.ods_order" % schema)
                cur.execute("INSERT INTO `%s`.ods_order SELECT * FROM ec_retail.ods_order LIMIT 5" % schema)
        conn.commit()
        print("[seed-orch] 多 schema 预置完成: ec_retail_east/ec_retail_south.ods_order 各 5 行")
    finally:
        conn.close()


def _delete_wf(db, wf):
    """删定义 + 版本日志（按 code 关联）。"""
    db.query(WfDefinitionLog).filter(WfDefinitionLog.wf_code == wf.code).delete()
    db.delete(wf)


def delete_old_workflows(db):
    """删除 graph 含旧同步组件节点的全部工作流定义（含版本日志）。"""
    deleted = 0
    for wf in db.query(WfDefinition).all():
        try:
            doc = json.loads(wf.graph_json) if wf.graph_json else {}
            types = {str(n.get("type") or "") for n in doc.get("nodes") or []}
        except (ValueError, TypeError):
            continue
        if types & OLD_NODE_TYPES:
            _delete_wf(db, wf)
            deleted += 1
            print("[seed-orch] 已删除旧同步工作流: %s (id=%s)" % (wf.name, wf.id))
    db.commit()
    return deleted


def create_workflows(db, owner_id=1):
    """先删后建 3 个编排用例（保证最新图）。返回新建数。"""
    created = 0
    for wf_id, name, builder in WORKFLOWS:
        old = db.query(WfDefinition).filter(WfDefinition.id == wf_id).first()
        if old is not None:
            _delete_wf(db, old)
        code = (db.query(func.max(WfDefinition.code)).scalar() or 0) + 1
        graph_json = json.dumps(builder(wf_id), ensure_ascii=False)
        db.add(WfDefinition(
            id=wf_id, code=code, name=name, version=1, release_state="offline",
            flag="yes", project_code="default", tags=TAGS,
            graph_json=graph_json, owner_id=owner_id,
        ))
        db.flush()
        db.add(WfDefinitionLog(
            wf_code=code, version=1, graph_json=graph_json,
            operator="seed", remark="同步编排端点合一用例（配置链，执行节点运行态物化）",
        ))
        created += 1
        print("[seed-orch] 已创建: %s %s (code=%s)" % (wf_id, name, code))
    db.commit()
    return created


def main():
    print("[seed-orch] 初始化数据库...", flush=True)
    init_db()
    db = new_session()
    try:
        preset_schemas()
        deleted = delete_old_workflows(db)
        created = create_workflows(db)
        total = db.query(func.count(WfDefinition.id)).scalar()
        print("[seed-orch] 完成: 删除旧流 %d 个，新建用例 %d 个，当前工作流总数 %d"
              % (deleted, created, total))
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
