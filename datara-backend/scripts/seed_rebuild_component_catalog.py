"""C-spec-01 A1 seed：datara_meta 组件目录（已发布态）收敛复制到 datara_rebuild_i0 三表。

背景（s356 裁定 A1 派单）：rebuild_i0 新库 t_component/t_component_version/t_component_log
为空，rebuild 侧组件目录读链（GET /api/v1/rebuild/components/spec 等）缺数据阻塞 F3。
本脚本把 datara_meta 中 state='published' 的组件、其 published 版本快照（与读链
published_document 同条件：component_id==Component.id AND version==published_version
AND state='published'）及审计日志收敛复制到 rebuild_i0，使 rebuild 目录读链立即可用。

形态（s356 裁定）：独立幂等种子脚本，非迁移——不写 rebuild_schema_migration 台账。
两侧同构：rebuild/component_spec/revisions/v0001_component_catalog.py 即用
common.models 三类建表，故本脚本单模型集双引擎操作两侧。

职责边界（D-09）：upload 能力（sourceMode/resourceRef/c-resource-mode）的
**结构性保证**由版本化迁移 rebuild/component_spec/revisions/
v0002_component_catalog_upload.py 承担；本 seed 仅灌入演示数据，其
_normalize_spec_json 仍做等价归一化以保持演示数据形状与读链一致，但不作为
upload 能力的权威来源。

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
import json
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


def _normalize_spec_json(value: str | None, type_name: str | None = None) -> str | None:
    """Upgrade legacy catalog documents to the rebuilt eight-section form DSL.

    The legacy metadata catalog predates the rebuilt component contract and
    commonly omits ``form`` altogether.  Preserve all declared fields while
    adding only the missing canonical sections; executable/unknown declarations
    are still rejected by the API's normal publication validator.
    """
    if not value:
        return value
    try:
        spec = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return value
    if not isinstance(spec, dict):
        return value
    sections = ("inputs", "outputs", "params", "conditions", "constraints", "exclusions", "refs", "exports")

    def normalize_legacy_picks(node):
        if isinstance(node, dict):
            for key in list(node):
                if key == "pick" and not isinstance(node[key], dict):
                    # Legacy lineage rows used the bare ``datasource`` token;
                    # the rebuilt DSL only permits a structured pick object.
                    node.pop(key)
                else:
                    normalize_legacy_picks(node[key])
        elif isinstance(node, list):
            for child in node:
                normalize_legacy_picks(child)

    normalize_legacy_picks(spec)
    form = spec.get("form")
    if form is None:
        spec["form"] = {section: [] for section in sections}
    elif isinstance(form, dict):
        spec["form"] = {section: form.get(section, []) if isinstance(form.get(section, []), list) else [] for section in sections}
    else:
        spec["form"] = {section: [] for section in sections}
    # Increment 7: expose immutable resource-version references for the three
    # executable data components.  This is declarative only; the resource
    # service validates project ownership and concrete versions at save/run.
    # D-09：此处归一化仅服务于演示数据形状；upload 能力的结构性保证由版本化
    # 迁移 v0002_component_catalog_upload 承担（见模块 docstring 职责边界）。
    resource_kind = {"sql": "sql", "python": "python", "shell": "shell"}.get((type_name or "").lower())
    if resource_kind:
        params = spec["form"]["params"]
        keys = {item.get("key") for item in params if isinstance(item, dict)}
        if "sourceMode" not in keys:
            params.append({"key": "sourceMode", "label": "内容来源", "uiType": "select",
                           "required": True, "visible": True, "default": "inline",
                           "options": [{"label": "内联内容", "value": "inline"},
                                       {"label": "资源版本", "value": "resource"}]})
        if "resourceRef" not in keys:
            extensions = {"sql": [".sql"], "python": [".py", ".zip"], "shell": [".sh", ".bash"]}[resource_kind]
            params.append({"key": "resourceRef", "label": "资源版本", "uiType": "resource",
                           "required": False, "visible": True,
                           "cap": {"mode": "resource", "kind": resource_kind,
                                   "extensions": extensions, "versioned": True,
                                   "allowLatest": False}})
        if not any(isinstance(item, dict) and item.get("id") == "c-resource-mode"
                   for item in spec["form"]["conditions"]):
            spec["form"]["conditions"].append({"id": "c-resource-mode",
                "when": {"field": "sourceMode", "op": "eq", "value": "resource"},
                "show": ["resourceRef"]})
    return json.dumps(spec, ensure_ascii=False, separators=(",", ":"))


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
    synthetic_dependency = False
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
            dst.spec_json = _normalize_spec_json(dst.spec_json, src.type)

        # The legacy metadata catalogue predates the rebuilt dependency node.
        # Materialize the governed builtin from the shell declaration when it
        # is absent, so NORMAL workflows have the full target palette.
        if "dependent" not in exist_c:
            # On a fresh target ``exist_v`` is empty even though the shell row
            # has just been staged above.  Fall back to the loaded source row
            # so dependency creation is correct on the first apply, not only
            # after an accidental second run.
            template = exist_v.get(("shell", 1)) or next(
                (row for row in versions if row.type == "shell" and row.version == 1),
                None,
            )
            if template is not None:
                dep = Component(
                    type="dependent", name="依赖", category="NORMAL", profile="dag",
                    scope="builtin", execution_model="dag-engine", executor="dependency",
                    executable=True, state="published", published_version=1, draft_rev=0,
                    description="工作流依赖组件", tags=["dependency"],
                )
                rebuild_session.add(dep)
                rebuild_session.flush()
                dep_spec = json.loads(template.spec_json)
                dep_spec["summary"] = "依赖工作流或任务"
                dep_spec["description"] = "等待依赖完成后继续执行"
                dep_version = ComponentVersion(
                    component_id=dep.id, type="dependent", version=1, state="published",
                    spec_json=json.dumps(dep_spec, ensure_ascii=False, separators=(",", ":")),
                    spec_hash=template.spec_hash, remark="generated from legacy catalogue",
                )
                rebuild_session.add(dep_version)
                created["component"] += 1
                created["version"] += 1
                synthetic_dependency = True

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
            expected_c = len(components) + (1 if synthetic_dependency else 0)
            expected_v = len(versions) + (1 if synthetic_dependency else 0)
            print(f"[verify] rebuild_i0 t_component={n_c} t_component_version={n_v} t_component_log={n_l}（预期 {expected_c}/{expected_v}/{len(logs)}）")
            # ---- C2 复核：items==components（rebuild 侧计数须与 meta 侧种子集一致，不等即 abort） ----
            if n_c != expected_c or n_v != expected_v:
                print(
                    f"[abort] C2 复核失败：rebuild_i0 计数 ({n_c}/{n_v}) 与预期种子集 ({expected_c}/{expected_v}) 不一致：需人工核查",
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
