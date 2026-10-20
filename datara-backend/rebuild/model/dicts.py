"""I18 数仓建模字典种子（五步迁移第②步：旧 `common/db.py:59-92` 照抄）。

分层/规范文案对齐 `prototype/assets/data.js` 的 `DB.dwLayers`。
`count == 0` 守卫与插入非原子，多进程并发首启时由主键/唯一约束兜底，
后提交者捕获 `IntegrityError` 回滚跳过（单实例部署不触发）。

调用方：`rebuild/api/app.py` 的 `ensure_model_schema()`（lifespan 内幂等调用）。
"""

from __future__ import annotations

import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from rebuild.model.models import BizDomainRecord, DwLayerRecord, EngineTypeRecord

logger = logging.getLogger("rebuild.model")


def seed_model_dicts(session: Session) -> None:
    """写入分层/业务域/引擎字典种子（幂等，存在即跳过）。"""
    if session.query(DwLayerRecord).count() == 0:
        session.add_all([
            DwLayerRecord(code="ODS", name="原始数据层", rule="ods_源库名_源表名，保留原始字段", color="#0891b2", seq=1),
            DwLayerRecord(code="DWD", name="明细数据层", rule="dwd_业务_过程，一个过程一张表", color="#1668dc", seq=2),
            DwLayerRecord(code="DWS", name="汇总数据层", rule="dws_主题_粒度，预聚合指标", color="#7c3aed", seq=3),
            DwLayerRecord(code="ADS", name="应用数据层", rule="ads_应用_场景，直接服务报表", color="#16a34a", seq=4),
            DwLayerRecord(code="DIM", name="维度层", rule="dim_维度名，全局唯一", color="#d97706", seq=5),
        ])
    if session.query(BizDomainRecord).count() == 0:
        session.add_all([
            BizDomainRecord(name="交易域"), BizDomainRecord(name="用户域"),
            BizDomainRecord(name="商品域"), BizDomainRecord(name="流量域"),
        ])
    if session.query(EngineTypeRecord).count() == 0:
        session.add_all([
            EngineTypeRecord(name="MySQL", ddl="mysql", xc=False),
            EngineTypeRecord(name="Apache Doris", ddl="doris", xc=False),
            EngineTypeRecord(name="GreatDB", ddl="greatdb", xc=True),
        ])
    try:
        session.commit()
        logger.info("字典种子就绪（分层/业务域/引擎，空库路径写入）")
    except IntegrityError:
        session.rollback()
        logger.warning("字典种子并发竞争：另一进程已写入，本次跳过")
