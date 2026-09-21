"""血缘运行时采集（I5 设计文档 §4，F24）：worker 侧 SQL 成功语句 → 血缘落库。

- 旁路原则：解析/落库任何异常仅记日志，绝不影响任务执行与终态
- 语句来源 = param_resolved 实际执行成功语句（与 [sql] 日志同源，变量已替换）
- 幂等：uk(wf_code, instance_id, node_id, stmt_no, from_table, to_table) 先查后插，
  同 instance 重放（重试/容错认领）不产生重复行；整体重跑（新实例号）产生新
  实例维度的血缘行（追溯需要），查询端按 wf/node/stmt 维度去重呈现
- 临时表映射（设计 §3.2）：落库前 t_tmp_data.ref（同实例）→ 注册名并置
  tmp_flag=1，图上显示 raw_txt 等注册名；解析器保持纯函数不掺库查询
"""

from common.db import new_session
from common.log import get_logger
from common.models import (
    LineageEdge,
    LineageField,
    TmpData,
    TaskInstance,
    WfDefinition,
    WorkflowInstance,
)
from common.sqlparser import parse_sql_lineage

logger = get_logger("worker.lineage")


def _tmp_name_map(session, instance_id: str) -> dict:
    """同实例 t_tmp_data：ref（实体引用）→ 注册名（仅 table/resultset 可入血缘）。"""
    amap: dict = {}
    rows = (
        session.query(TmpData)
        .filter(TmpData.instance_id == instance_id, TmpData.kind.in_(("table", "resultset")))
        .all()
    )
    for row in rows:
        if row.ref and row.name:
            amap[row.ref] = row.name
    return amap


def _map_table(name: str, tmp_map: dict) -> tuple:
    """临时表名 → (注册名, True)；普通表原样。匹配裸 ref 或 `库名.ref` 尾段。"""
    if name in tmp_map:
        return tmp_map[name], True
    for ref, reg in tmp_map.items():
        if name.endswith("." + ref):
            return reg, True
    return name, False


def _ctx_info(session, ctx) -> tuple:
    """(wf_code, wf_name, node_id, node_name)：任务实例/运行实例/定义逐级容错。"""
    node_id = node_name = ""
    task = session.get(TaskInstance, ctx.task_id)
    if task is not None:
        node_id = task.node_id or ""
        node_name = task.name or ""
    wf_code, wf_name = 0, ""
    wi = (
        session.query(WorkflowInstance)
        .filter(WorkflowInstance.instance_id == ctx.instance_id)
        .first()
    )
    if wi is not None:
        wf_code = int(wi.wf_code or 0)
        wd = session.query(WfDefinition).filter(WfDefinition.code == wf_code).first()
        if wd is not None:
            wf_name = wd.name or ""
    return wf_code, wf_name, node_id, node_name


def collect_sql_lineage(ctx, stmts: list, ds_name: str, default_db: str) -> tuple:
    """成功语句逐条解析落库；返回 (表级边数, 字段映射数)。异常全兜底（旁路）。"""
    if not stmts:
        return 0, 0
    try:
        return _collect(ctx, stmts, ds_name, default_db)
    except Exception as exc:  # noqa: BLE001 血缘旁路绝不阻断任务
        ctx.log("[lineage] 血缘采集异常（不影响任务）: %r" % exc)
        logger.error("血缘采集异常: taskId=%s %r", ctx.task_id, exc)
        return 0, 0


def collect_sync_lineage(ctx, edges: list, ds_name: str) -> tuple:
    """C17 同步血缘落库（I6 设计文档 §7，裁定④）：表级边 + 字段映射。

    - edges: [{from, to, stmt, fields: [{from_field, to_field}]}]，from 可为空串（文件源无来源表）
    - 幂等/临时表映射（读端 ${tmp.*} 物理表名 → 注册名）/旁路兜底与 collect_sql_lineage 同口径
    - stmt_no 取 edges 序号（同实例重放不翻倍，uk 同 _collect）
    """
    if not edges:
        return 0, 0
    try:
        return _collect_sync(ctx, edges, ds_name)
    except Exception as exc:  # noqa: BLE001 血缘旁路绝不阻断任务
        ctx.log("[lineage] 同步血缘采集异常（不影响任务）: %r" % exc)
        logger.error("同步血缘采集异常: taskId=%s %r", ctx.task_id, exc)
        return 0, 0


def _collect_sync(ctx, edges: list, ds_name: str) -> tuple:
    edge_count = field_count = 0
    session = new_session()
    try:
        wf_code, wf_name, node_id, node_name = _ctx_info(session, ctx)
        tmp_map = _tmp_name_map(session, ctx.instance_id)
        for stmt_no, item in enumerate(edges, start=1):
            from_reg, from_tmp = _map_table(str(item.get("from") or ""), tmp_map)
            to_reg, to_tmp = _map_table(str(item.get("to") or ""), tmp_map)
            if not to_reg:
                continue
            stmt = str(item.get("stmt") or "")[:2000]
            edge = (
                session.query(LineageEdge)
                .filter(
                    LineageEdge.wf_code == wf_code,
                    LineageEdge.instance_id == ctx.instance_id,
                    LineageEdge.node_id == node_id,
                    LineageEdge.stmt_no == stmt_no,
                    LineageEdge.from_table == from_reg,
                    LineageEdge.to_table == to_reg,
                )
                .first()
            )
            if edge is None:
                edge = LineageEdge(
                    wf_code=wf_code, wf_name=wf_name,
                    instance_id=ctx.instance_id, task_id=ctx.task_id,
                    node_id=node_id, node_name=node_name, ds_name=ds_name,
                    stmt_no=stmt_no, stmt=stmt,
                    from_table=from_reg, to_table=to_reg,
                    tmp_flag=to_tmp or from_tmp,
                )
                session.add(edge)
                session.flush()
            edge_count += 1
            for fm in item.get("fields") or []:
                from_field = str(fm.get("from_field") or "")
                to_field = str(fm.get("to_field") or "")
                if not to_field:
                    continue
                exists = (
                    session.query(LineageField)
                    .filter(
                        LineageField.edge_id == edge.id,
                        LineageField.to_field == to_field,
                        LineageField.from_table == from_reg,
                        LineageField.from_field == from_field,
                    )
                    .first()
                )
                if exists is None:
                    session.add(LineageField(
                        edge_id=edge.id, to_field=to_field,
                        from_table=from_reg, from_field=from_field,
                        transform="",
                    ))
                    field_count += 1
        session.commit()
        ctx.log("[lineage] 同步血缘: 表级边 %d / 字段映射 %d（临时表映射 %d）"
                % (edge_count, field_count, len(tmp_map)))
    finally:
        session.close()
    return edge_count, field_count


def _collect(ctx, stmts: list, ds_name: str, default_db: str) -> tuple:
    edge_count = field_count = 0
    session = new_session()
    try:
        wf_code, wf_name, node_id, node_name = _ctx_info(session, ctx)
        tmp_map = _tmp_name_map(session, ctx.instance_id)
        for stmt_no, stmt in enumerate(stmts, start=1):
            for parsed in parse_sql_lineage(stmt, default_db):
                if not parsed.to_tables:
                    continue  # 纯 SELECT/SHOW 等无目标 → 不落
                for to_table in parsed.to_tables:
                    to_reg, to_tmp = _map_table(to_table, tmp_map)
                    # 每来源表一条边；无来源（INSERT..VALUES/纯 DDL）落 from='' 单边
                    edge_ids: dict = {}
                    for from_table in parsed.from_tables or [""]:
                        from_reg, from_tmp = _map_table(from_table, tmp_map)
                        edge = (
                            session.query(LineageEdge)
                            .filter(
                                LineageEdge.wf_code == wf_code,
                                LineageEdge.instance_id == ctx.instance_id,
                                LineageEdge.node_id == node_id,
                                LineageEdge.stmt_no == stmt_no,
                                LineageEdge.from_table == from_reg,
                                LineageEdge.to_table == to_reg,
                            )
                            .first()
                        )
                        if edge is None:
                            edge = LineageEdge(
                                wf_code=wf_code, wf_name=wf_name,
                                instance_id=ctx.instance_id, task_id=ctx.task_id,
                                node_id=node_id, node_name=node_name, ds_name=ds_name,
                                stmt_no=stmt_no, stmt=parsed.stmt,
                                from_table=from_reg, to_table=to_reg,
                                tmp_flag=to_tmp or from_tmp,
                            )
                            session.add(edge)
                            session.flush()  # 取自增 edge.id
                        edge_ids[from_reg] = edge.id
                    edge_count += len(edge_ids)
                    if not parsed.fields:
                        continue
                    # 字段映射按 from_table 挂边；无归属（常量/CTE 列）挂第一条边
                    first_edge = next(iter(edge_ids.values()))
                    for fm in parsed.fields:
                        f_reg, _t = _map_table(fm.from_table, tmp_map)
                        eid = edge_ids.get(f_reg, first_edge)
                        exists = (
                            session.query(LineageField)
                            .filter(
                                LineageField.edge_id == eid,
                                LineageField.to_field == fm.to_field,
                                LineageField.from_table == f_reg,
                                LineageField.from_field == fm.from_field,
                            )
                            .first()
                        )
                        if exists is None:
                            session.add(LineageField(
                                edge_id=eid, to_field=fm.to_field,
                                from_table=f_reg, from_field=fm.from_field,
                                transform=fm.transform,
                            ))
                            field_count += 1
        session.commit()
    finally:
        session.close()
    ctx.log("[lineage] 血缘采集: 语句 %d 条 → 表级边 %d / 字段映射 %d（临时表映射 %d）"
            % (len(stmts), edge_count, field_count, len(tmp_map)))
    return edge_count, field_count
