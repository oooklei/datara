"""脚本开发资源 → 海豚资源中心同步（编排节点可选资源文件）。

DAG 画布为海豚原生 UI：SQL/Python/Shell 节点的「资源文件」下拉读海豚资源
中心（``GET /resources/list``），而 datara 脚本只存 resources 域，不同步则
下拉恒为空。

形态约定（海豚 3.4.3 fork 实测语义，2026-11-01 探针验证）：
- ``AbstractResourceTransformer`` 仅接受根目录 ``currentDir=/``，文件不可
  落子目录，故以项目前缀命名避免跨项目同名冲突：
  ``datara-p{project_id}-{name}``。
- ``fullName`` 为含存储根的完整路径（如 ``/tmp/dolphinscheduler/default/
  resources/{name}``），覆盖更新必须先按 ``name`` 从列表定位真实
  ``fullName``，不可自行拼接。
- 幂等：列表命中 → ``PUT /resources`` 覆盖内容；未命中 → ``POST /resources``
  根目录创建；创建竞态回「已存在」时重查后改走覆盖。

同步失败由调用方以尽力而为语义处理（脚本保存不因此失败），存量脚本可经
``POST /api/v1/rebuild/orchestration/script-resources/sync``（admin）回填。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import sessionmaker

from rebuild.orchestration.ds_client import DsClient, DsClientError
from rebuild.resources.models import ResourceRecord
from rebuild.resources.repository import ResourceDomainError, ResourceRepository

#: 可作为编排「资源文件」选用的脚本类型（SQL/Python/Shell 同链路）。
SCRIPT_KINDS = ("sql", "python", "shell")

RESOURCE_FILE_TYPE = "FILE"


def script_resource_name(project_id: int, name: str) -> str:
    """datara 资源在海豚资源中心的落地名（带项目前缀，杜绝跨项目同名覆盖）。"""
    return f"datara-p{project_id}-{name.strip()}"


def _flat_file_nodes(client: DsClient) -> list[dict[str, Any]]:
    """海豚资源树拍平（含目录子节点），供按 name 定位。"""
    data = client.call("GET", "/resources/list", query={"type": RESOURCE_FILE_TYPE})
    if isinstance(data, dict) and isinstance(data.get("totalList"), list):
        items = data["totalList"]
    elif isinstance(data, list):
        items = data
    else:
        items = []
    flat: list[dict[str, Any]] = []
    stack = [item for item in items if isinstance(item, dict)]
    while stack:
        node = stack.pop(0)
        flat.append(node)
        children = node.get("children")
        if isinstance(children, list):
            stack.extend(child for child in children if isinstance(child, dict))
    return flat


def _find_file_node(client: DsClient, ds_name: str) -> dict[str, Any] | None:
    return next(
        (
            node
            for node in _flat_file_nodes(client)
            if str(node.get("name") or "") == ds_name and not node.get("children")
        ),
        None,
    )


def _overwrite(client: DsClient, ds_name: str, full_name: str, content: bytes) -> dict[str, Any]:
    client.call(
        "PUT",
        "/resources",
        form={"type": RESOURCE_FILE_TYPE, "fullName": full_name, "name": ds_name},
        files={"file": (ds_name, content, "application/octet-stream")},
    )
    return {"action": "updated", "name": ds_name, "fullName": full_name}


def sync_script_resource(
    client: DsClient, *, project_id: int, name: str, content: bytes
) -> dict[str, Any]:
    """同步单个资源：命中即覆盖，未命中即根目录创建；返回 ``{action, name, fullName?}``。"""
    ds_name = script_resource_name(project_id, name)
    target = _find_file_node(client, ds_name)
    if target is not None:
        return _overwrite(client, ds_name, str(target.get("fullName") or ""), content)
    try:
        client.call(
            "POST",
            "/resources",
            form={"type": RESOURCE_FILE_TYPE, "name": ds_name, "currentDir": "/"},
            files={"file": (ds_name, content, "application/octet-stream")},
        )
    except DsClientError:
        # 并发同名创建时海豚回「已存在」类业务错误：重查后改走覆盖；
        # 重查仍不存在则如实抛出（真实失败，不能吞）。
        target = _find_file_node(client, ds_name)
        if target is None:
            raise
        return _overwrite(client, ds_name, str(target.get("fullName") or ""), content)
    return {"action": "created", "name": ds_name}


def sync_project_scripts(
    client: DsClient,
    session_factory: sessionmaker,
    *,
    project_id: int | None = None,
) -> list[dict[str, Any]]:
    """把 resources 域脚本（sql/python/shell 最新版）全量同步到海豚资源中心。

    单条失败不中断整体（记入该项 ``error``），返回逐项结果供回填接口透出。
    """
    with session_factory() as session:
        query = session.query(ResourceRecord).filter(ResourceRecord.kind.in_(SCRIPT_KINDS))
        if project_id is not None:
            query = query.filter(ResourceRecord.project_id == project_id)
        metas = [(row.project_id, row.id, row.name, row.latest_version) for row in query.all()]
    results: list[dict[str, Any]] = []
    for res_project_id, resource_id, name, version in metas:
        item: dict[str, Any] = {
            "project_id": res_project_id,
            "resourceId": resource_id,
            "name": name,
            "version": version,
        }
        with session_factory() as session:
            try:
                payload = ResourceRepository(session).read_version_text(res_project_id, resource_id, version)
            except ResourceDomainError as exc:
                item["error"] = f"{exc.code}: {exc.msg}"
                results.append(item)
                continue
        try:
            outcome = sync_script_resource(
                client, project_id=res_project_id, name=name, content=payload["content"].encode("utf-8")
            )
            item["dsName"] = outcome["name"]
            item["action"] = outcome["action"]
            if "fullName" in outcome:
                item["fullName"] = outcome["fullName"]
        except DsClientError as exc:
            item["error"] = f"{exc.code}: {exc.msg}"
        results.append(item)
    return results
