"""临时工作数据生命周期（I4 设计文档 §5.4）。

- 注册：worker C22 执行器（executors/file.py）upsert t_tmp_data（uk_tmp_name 幂等，重试覆盖）
- 收口：master 实例终态（engine._finalize）→ retention=immediate 清扫；
  retention=keep 且实例成功 → RENAME 去前缀转正式表（失败告警不阻断）
- 过期：retention=days 的 expire_at 到期 → F50 clean_logs.sh 清扫（脚本侧）
- 手动清理：api DELETE /tmp-data/{id}（run_instance 权限点）
- 状态机：active → consumed(转正式表) / cleaned(清扫)；expired 由 F50 按到期行删除
"""

import re
from typing import Optional

from sqlalchemy.orm import Session

from common.db import new_session
from common.dsconn import open_connection, resolve_file_path
from common.log import get_logger
from common.models import DataSource, TmpData

logger = get_logger("common.tmpdata")

TMP_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{2,31}$")


def tmp_table_name(instance_id: str, node_id: str, name: str) -> str:
    """临时表名 {instance_id}_{node_id}_{name}；RENAME 去前缀即正式表名（设计 §5.2）。"""
    return "%s_%s_%s" % (instance_id, node_id, name)


def _target_ds(session: Session, row: TmpData) -> Optional[DataSource]:
    if row.target_ds_id is None:
        return None
    return session.get(DataSource, row.target_ds_id)


def clean_tmp_data(session: Session, row: TmpData) -> bool:
    """清扫单条临时数据实体：table→DROP / file→删文件 / resultset→无实体。

    返回是否成功；失败仅告警，调用方保持 active 供重试（F50/手动清理）。
    """
    try:
        if row.kind == "table":
            ds = _target_ds(session, row)
            if ds is None or not row.ref:
                logger.warning("临时数据 %s(%s) 目标数据源缺失，跳过 DROP", row.name, row.ref)
                return True  # 无实体可清，视为成功
            conn = open_connection(ds)
            try:
                with conn.cursor() as cur:
                    cur.execute("DROP TABLE IF EXISTS `%s`.`%s`" % (ds.db_name, row.ref))
                conn.commit()
            finally:
                conn.close()
        elif row.kind == "file" and row.ref:
            path = resolve_file_path(row.ref)
            if path.is_file():
                path.unlink()
        return True
    except Exception as exc:  # noqa: BLE001 清扫失败告警（不阻断收口）
        logger.error("临时数据清扫失败: %s(%s/%s) %r", row.name, row.kind, row.ref, exc)
        return False


def _promote(session: Session, row: TmpData) -> None:
    """转正式表：RENAME 去前缀（临时表 → name），ref 更新为正式名，status=consumed。"""
    ds = _target_ds(session, row)
    formal = row.name
    if ds is None or not row.ref:
        logger.warning("临时数据 %s 转正式表失败：目标数据源缺失", row.name)
        return
    try:
        conn = open_connection(ds)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "RENAME TABLE `%s`.`%s` TO `%s`.`%s`" % (ds.db_name, row.ref, ds.db_name, formal)
                )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 失败告警不阻断（设计 §5.2）
        logger.error("临时数据转正式表失败: %s ref=%s %r", row.name, row.ref, exc)
        return
    row.ref = formal
    row.status = "consumed"
    logger.info("临时数据已转正式表: %s → %s.%s", row.name, ds.db_name, formal)


def finalize_instance_tmp(instance_id: str, success: bool) -> None:
    """master 实例终态收口：immediate → 清扫置 cleaned；keep+成功+table → 转正式表。

    days 策略不动（expire_at 到期由 F50 清扫）；调用方兜 try/except 不阻断终态。
    """
    session = new_session()
    try:
        rows = (
            session.query(TmpData)
            .filter(TmpData.instance_id == instance_id, TmpData.status == "active")
            .all()
        )
        for row in rows:
            if row.retention == "immediate":
                if clean_tmp_data(session, row):
                    row.status = "cleaned"
                    logger.info("临时数据已清理: %s(%s/%s)", instance_id, row.name, row.kind)
            elif row.retention == "keep" and success and row.kind == "table":
                _promote(session, row)
        session.commit()
    finally:
        session.close()
