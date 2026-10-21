"""C-spec-01 A1 seed：datara_meta 组件目录（已发布态）收敛复制到 datara_rebuild_i0 三表。

背景（s356 裁定 A1 派单）：rebuild_i0 新库 t_component/t_component_version/t_component_log
为空，rebuild 侧组件目录读链（GET /api/v1/rebuild/components/spec 等）缺数据阻塞 F3。
本脚本把 datara_meta 中 state='published' 的组件、其 published 版本快照（与读链
published_document 同条件：component_id==Component.id AND version==published_version
AND state='published'）及审计日志收敛复制到 rebuild_i0，使 rebuild 目录读链立即可用。

形态（s356 裁定）：独立幂等种子脚本，非迁移——不写 rebuild_schema_migration 台账。
两侧同构：rebuild/component_spec/revisions/v0001_component_catalog.py 即用
common.models 三类建表，故本脚本单模型集双引擎操作两侧。

幂等（先查后写，主键级 UPDATE 收敛）：
- t_component        按 type 唯一键（uk：type）
- t_component_version 按 uk_comp_type_ver(type, version)
- t_component_log    按 id 主键
新增行显式携带 meta 侧原 id（保 component_version.component_id 引用与自增不破坏）；
已存在行整行覆盖为 meta 侧现值。t_component_log 为历史记录复制语义（s356 裁定字面
「写 rebuild_i0 三表」）。

用法（rebuild-api 容器内执行，REBUILD_DB_URL 现成零注入；META_DB_URL 缺省回落
common.config.get_settings().db_url）：
    python scripts/seed_rebuild_component_catalog.py           # dry-run（只读+计数）
    python scripts/seed_rebuild_component_catalog.py --apply   # 单事务实写+三表复核
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from sqlalchemy import and_, create_engine, func
from sqlalchemy.orm import sessionmaker

from common.models import Component, ComponentLog, ComponentVersion


def _meta_url() -> str:
    url = os.getenv("META_DB_URL")
    if url:
        return url
    from common.config import get_settings

    return get_settings().db_url


def _rebuild_url() -> str:
    return os.getenv("REBUILD_DB_URL") or ""


def _copy_row(target, source) -> None:
    """全列自动复制（expire_on_commit=False 下全列 loaded），过滤 SQLAlchemy 内部态。"""
    for key, value in source.__dict__.items():
        if key.startswith("_sa"):
            continue
        setattr(target, key, value)


def main() -> int:
    parser = argparse.ArgumentParser(description="datara_meta 组件目录 seed 到 rebuild_i0（幂等，默认 dry-run）")
    parser.add_argument("--apply", action="store_true", help="实写 rebuild_i0（缺省 dry-run）")
    args = parser.parse_args()

    rebuild_url = _rebuild_url()
    if not rebuild_url:
        print("[abort] REBUILD_DB_URL 未设置（rebuild 侧惯例必填）：中止", file=sys.stderr)
        return 2
    meta_url = _meta_url()

    meta_engine = create_engine(meta_url, pool_pre_ping=True, pool_recycle=3600, pool_size=5, max_overflow=10)
    rebuild_engine = create_engine(rebuild_url, pool_pre_ping=True, pool_recycle=3600, pool_size=5, max_overflow=10)
    meta_session = sessionmaker(bind=meta_engine, expire_on_commit=False)()
    rebuild_session = sessionmaker(bind=rebuild_engine, expire_on_commit=False)()

    created = {"component": 0, "version": 0, "log": 0}
    updated = {"component": 0, "version": 0, "log": 0}
    try:
        # ---- 读侧：受控只读 datara_meta（预期 18/18/31，随搬语义=现存组件全量日志） ----
        components = (
            meta_session.query(Component)
            .filter(Component.state == "published")
            .order_by(Component.id)
            .all()
        )
        comp_ids = [row.id for row in components]
        versions = (
            meta_session.query(ComponentVersion)
            .join(
                Component,
                and_(
                    ComponentVersion.component_id == Component.id,
                    ComponentVersion.version == Component.published_version,
                ),
            )
            .filter(
                Component.id.in_(comp_ids),
                ComponentVersion.state == "published",
            )
            .order_by(ComponentVersion.id)
            .all()
        )
        logs = (
            meta_session.query(ComponentLog)
            .filter(ComponentLog.component_id.in_(comp_ids))
            .order_by(ComponentLog.id)
            .all()
        )
        print(
            f"[read] meta t_component(published)={len(components)} "
            f"t_component_version(published snapshot)={len(versions)} "
            f"t_component_log={len(logs)}"
        )

        # ---- C2 不变量断言（s362 裁定）：每 published 组件应恰有一份 published 快照，不等即 abort ----
        if len(components) != len(versions):
            print(
                f"[abort] C2 不变量断言失败：published 组件数 {len(components)} != published 版本快照数 {len(versions)}：中止不写",
                file=sys.stderr,
            )
            return 3

        # ---- 写侧预载现存（先查后写幂等） ----
        exist_c = {row.type: row for row in rebuild_session.query(Component).all()}
        exist_v = {(row.type, row.version): row for row in rebuild_session.query(ComponentVersion).all()}
        exist_l = {row.id: row for row in rebuild_session.query(ComponentLog).all()}

        # t_component：type 唯一键收敛，保留原 id
        for src in components:
            dst = exist_c.get(src.type)
            if dst is None:
                dst = Component()
                rebuild_session.add(dst)
                created["component"] += 1
            else:
                updated["component"] += 1
            _copy_row(dst, src)

        # t_component_version：uk_comp_type_ver(type, version) 收敛，保留原 id
        for src in versions:
            dst = exist_v.get((src.type, src.version))
            if dst is None:
                dst = ComponentVersion()
                rebuild_session.add(dst)
                created["version"] += 1
            else:
                updated["version"] += 1
            _copy_row(dst, src)

        # t_component_log：id 主键收敛（历史记录复制语义）
        for src in logs:
            dst = exist_l.get(src.id)
            if dst is None:
                dst = ComponentLog()
                rebuild_session.add(dst)
                created["log"] += 1
            else:
                updated["log"] += 1
            _copy_row(dst, src)

        print(
            f"[plan] create component={created['component']} version={created['version']} log={created['log']}; "
            f"overwrite component={updated['component']} version={updated['version']} log={updated['log']}"
        )

        if args.apply:
            rebuild_session.commit()
            print("[write] committed（单事务）")
            n_c = rebuild_session.query(func.count(Component.id)).scalar()
            n_v = rebuild_session.query(func.count(ComponentVersion.id)).scalar()
            n_l = rebuild_session.query(func.count(ComponentLog.id)).scalar()
            print(f"[verify] rebuild_i0 t_component={n_c} t_component_version={n_v} t_component_log={n_l}（预期 18/18/31）")
            # ---- C2 复核：items==components（rebuild 侧计数须与 meta 侧种子集一致，不等即 abort） ----
            if n_c != len(components) or n_v != len(versions):
                print(
                    f"[abort] C2 复核失败：rebuild_i0 计数 ({n_c}/{n_v}) 与 meta 侧种子集 ({len(components)}/{len(versions)}) 不一致：需人工核查",
                    file=sys.stderr,
                )
                return 3
        else:
            rebuild_session.rollback()
            print("[dry-run] 未写入（已回滚保险）；加 --apply 实写")
    except Exception:
        rebuild_session.rollback()
        raise
    finally:
        meta_session.close()
        rebuild_session.close()
        meta_engine.dispose()
        rebuild_engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
