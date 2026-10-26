from pathlib import Path

import seed_product_fixture as fixture
from seed_product_fixture import API_PREFIX, Settings, ensure_demo_identities


class FakeTransport:
    def __init__(self) -> None:
        self.users = [
            {"id": 1, "username": "dev", "role": "developer", "status": "enabled"},
            {"id": 3, "username": "admin", "role": "admin", "status": "enabled"},
        ]
        self.members = {33: [], 35: []}
        self.calls: list[tuple[str, str, dict | None]] = []

    def request(self, method, path, *, headers=None, json_body=None):
        self.calls.append((method, path, json_body))
        if method == "GET" and path == f"{API_PREFIX}/users":
            return {"data": {"list": self.users}}
        if method == "POST" and path == f"{API_PREFIX}/users":
            row = {"id": len(self.users) + 2, **json_body, "status": "enabled"}
            self.users.append(row)
            return {"data": row}
        if method == "PATCH" and path.endswith("/password"):
            return {"data": {"id": int(path.split("/")[-2])}}
        if method == "GET" and path.endswith("/members"):
            project_id = int(path.split("/")[-2])
            return {"data": {"list": self.members[project_id]}}
        if method == "POST" and path.endswith("/members"):
            project_id = int(path.split("/")[-2])
            user = next(row for row in self.users if row["username"] == json_body["username"])
            self.members[project_id].append({"user_id": user["id"], "role": json_body["role"]})
            return {"data": {"project_id": project_id}}
        raise AssertionError((method, path, json_body))


def test_demo_identity_seed_is_repeatable_and_grants_ecommerce_projects(tmp_path: Path):
    password_file = tmp_path / "rebuild-admin-password"
    settings = Settings({"DATARA_ADMIN_PASSWORD_FILE": str(password_file)})
    transport = FakeTransport()
    projects = [
        {"id": 33, "name": "电商数据全域治理项目"},
        {"id": 35, "name": "INFRA-DATA-01 电商闭环验证"},
    ]

    first = ensure_demo_identities(settings, transport, {"Authorization": "Bearer test"}, projects)
    second = ensure_demo_identities(settings, transport, {"Authorization": "Bearer test"}, projects)

    assert {row["username"] for row in transport.users} == {"admin", "dev", "analyst", "viewer"}
    assert first["memberships_created"] == 6
    assert second["memberships_created"] == 0
    assert password_file.read_text(encoding="utf-8") == "Admin@123\n"
    assert {row["role"] for row in transport.members[35]} == {"developer", "operator", "viewer"}


class ModelTransport:
    def __init__(self) -> None:
        self.models: list[dict] = []
        self.versions: dict[int, list[dict]] = {}
        self.edges: list[dict] = []
        self.calls: list[tuple[str, str, dict | None]] = []

    def request(self, method, path, *, headers=None, json_body=None):
        self.calls.append((method, path, json_body))
        if method == "GET" and path == f"{API_PREFIX}/models":
            return {"data": {"list": [dict(row) for row in self.models], "total": len(self.models), "layers": [], "domains": []}}
        if method == "POST" and path == f"{API_PREFIX}/models":
            row = {"id": len(self.models) + 1, "version": 1, "status": "draft", **json_body}
            self.models.append(row)
            self.versions[row["id"]] = []
            return {"data": {"id": row["id"]}}
        if method == "GET" and path.startswith(f"{API_PREFIX}/models/") and path != f"{API_PREFIX}/models/er" and not path.endswith("/versions"):
            model_id = int(path.split("/")[-1])
            return {"data": next(row for row in self.models if row["id"] == model_id)}
        if method == "PUT" and path.endswith("/fields"):
            model_id = int(path.split("/")[-2])
            model = next(row for row in self.models if row["id"] == model_id)
            model["version"] += 1
            model["fields"] = json_body["fields"]
            return {"data": {"rev": model["version"]}}
        if path.endswith("/versions"):
            model_id = int(path.split("/")[-2])
            if method == "GET":
                return {"data": self.versions[model_id]}
            version = {"id": len(self.versions[model_id]) + 1, "version": 1, **json_body}
            self.versions[model_id].append(version)
            return {"data": version}
        if method == "GET" and path == f"{API_PREFIX}/models/er":
            return {"data": {"nodes": [], "edges": self.edges}}
        if method == "PUT" and path == f"{API_PREFIX}/models/er":
            self.edges.extend(json_body["relations"]["added"])
            return {"data": {"saved": True}}
        raise AssertionError((method, path, json_body))


def test_demo_model_seed_is_repeatable_and_builds_lineage():
    ensure_demo_models = getattr(fixture, "ensure_demo_models", None)
    assert callable(ensure_demo_models)
    transport = ModelTransport()
    auth = {"Authorization": "Bearer test"}

    first = ensure_demo_models(transport, auth)
    second = ensure_demo_models(transport, auth)

    assert first == {"models_created": 3, "versions_created": 3, "relations_created": 2}
    assert second == {"models_created": 0, "versions_created": 0, "relations_created": 0}
    assert [row["code"] for row in transport.models] == [
        "ods_ecommerce_orders", "dwd_ecommerce_orders_detail", "dws_ecommerce_order_daily",
    ]
    assert all(row.get("fields") for row in transport.models)
    assert sum(len(rows) for rows in transport.versions.values()) == 3
    assert len(transport.edges) == 2
