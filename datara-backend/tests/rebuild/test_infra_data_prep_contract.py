from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from fastapi.testclient import TestClient

from rebuild.api.app import create_app


ROOT = Path(__file__).resolve().parents[3]
FIXTURE_DIR = ROOT / "infra" / "fixtures" / "business"
SCRIPT = FIXTURE_DIR / "seed_product_fixture.py"
FILE_SYNC_PATH = "/datara/files/fixtures/orders_file_sync.csv"
API_PREFIX = "/api/v1/rebuild"


def load_seed_module():
    spec = importlib.util.spec_from_file_location("seed_product_fixture", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeTransport:
    def __init__(self, *, existing: bool = True):
        self.existing = existing
        self.calls: list[dict] = []
        self.models = (
            [
                {"id": 61, "code": "ods_ecommerce_orders", "name": "电商订单原始层", "layer": "ODS", "engine": "mysql", "version": 2, "status": "draft", "fields": [{"name": "order_id"}]},
                {"id": 62, "code": "dwd_ecommerce_orders_detail", "name": "电商订单明细", "layer": "DWD", "engine": "mysql", "version": 2, "status": "draft", "fields": [{"name": "order_id"}]},
                {"id": 63, "code": "dws_ecommerce_order_daily", "name": "电商订单日汇总", "layer": "DWS", "engine": "mysql", "version": 2, "status": "draft", "fields": [{"name": "stat_date"}]},
            ]
            if existing
            else []
        )
        self.versions = {row["id"]: ([{"id": 1, "version": 2}] if existing else []) for row in self.models}
        self.edges = (
            [
                {"id": 1, "source": "61", "target": "62"},
                {"id": 2, "source": "62", "target": "63"},
            ]
            if existing
            else []
        )

    def request(self, method, path, *, headers=None, json_body=None):
        call = {"method": method, "path": path, "headers": dict(headers or {}), "json": json_body}
        self.calls.append(call)
        if path == "/api/v1/rebuild/validation-token":
            return {"code": 0, "data": {"token": "short-lived-secret"}}
        if method == "GET" and path == "/api/v1/rebuild/projects":
            rows = [{"id": 41, "name": "INFRA-DATA-01 电商闭环验证"}] if self.existing else []
            return {"code": 0, "data": {"list": rows}}
        if method == "POST" and path == "/api/v1/rebuild/projects":
            return {"code": 0, "data": {"id": 41, "name": json_body["name"]}}
        if method == "GET" and path == "/api/v1/rebuild/users":
            rows = (
                [
                    {"id": 1, "username": "admin", "role": "admin", "status": 1},
                    {"id": 2, "username": "dev", "role": "developer", "status": 1},
                    {"id": 3, "username": "analyst", "role": "operator", "status": 1},
                    {"id": 4, "username": "viewer", "role": "viewer", "status": 1},
                ]
                if self.existing
                else []
            )
            return {"code": 0, "data": {"list": rows}}
        if method == "POST" and path == "/api/v1/rebuild/users":
            next_id = 1 if not self.existing else 5
            return {"code": 0, "data": {"id": next_id, "username": json_body["username"], "role": json_body["role"], "status": 1}}
        if method == "PATCH" and path.startswith("/api/v1/rebuild/users/") and path.endswith("/password"):
            return {"code": 0, "data": {"id": 1, "username": "admin", "status": 1, "revoked_tokens": 0}}
        if method == "GET" and path.endswith("/members"):
            rows = (
                [{"user_id": 2, "username": "dev"}, {"user_id": 3, "username": "analyst"}, {"user_id": 4, "username": "viewer"}]
                if self.existing
                else []
            )
            return {"code": 0, "data": {"list": rows}}
        if method == "POST" and path.endswith("/members"):
            return {"code": 0, "data": {"saved": True}}
        if method == "GET" and path == "/api/v1/rebuild/models":
            return {"code": 0, "data": {"list": [dict(row) for row in self.models], "total": len(self.models), "layers": [], "domains": []}}
        if method == "POST" and path == "/api/v1/rebuild/models":
            row = {"id": 61 + len(self.models), "version": 1, "status": "draft", "fields": [], **json_body}
            self.models.append(row)
            self.versions[row["id"]] = []
            return {"code": 0, "data": {"id": row["id"]}}
        if method == "GET" and path == "/api/v1/rebuild/models/er":
            return {"code": 0, "data": {"nodes": [], "edges": self.edges}}
        if method == "PUT" and path == "/api/v1/rebuild/models/er":
            self.edges.extend(json_body["relations"]["added"])
            return {"code": 0, "data": {"saved": True}}
        if method == "GET" and path.startswith("/api/v1/rebuild/models/") and not path.endswith("/versions"):
            model_id = int(path.split("/")[-1])
            return {"code": 0, "data": next(row for row in self.models if row["id"] == model_id)}
        if method == "PUT" and path.endswith("/fields"):
            model_id = int(path.split("/")[-2])
            row = next(item for item in self.models if item["id"] == model_id)
            row["version"] += 1
            row["fields"] = json_body["fields"]
            return {"code": 0, "data": {"rev": row["version"]}}
        if path.endswith("/versions"):
            model_id = int(path.split("/")[-2])
            if method == "GET":
                return {"code": 0, "data": self.versions[model_id]}
            version = {"id": len(self.versions[model_id]) + 1, "version": 2, **json_body}
            self.versions[model_id].append(version)
            return {"code": 0, "data": version}
        if method == "GET" and path == "/api/v1/rebuild/projects/41/datasources":
            rows = ([{"id": 51, "name": "INFRA-DATA-01 source"}, {"id": 52, "name": "INFRA-DATA-01 dw"}] if self.existing else [])
            return {"code": 0, "data": {"items": rows}}
        if method == "POST" and path == "/api/v1/rebuild/projects/41/datasources":
            datasource_id = 51 if json_body["name"].endswith("source") else 52
            return {"code": 0, "data": {"id": datasource_id, "name": json_body["name"]}}
        if method == "GET" and path == "/api/v1/rebuild/variables?project_id=41&scopes=project":
            rows = [{"scope": "project", "name": "fixture_key"}] if self.existing else []
            return {"code": 0, "data": rows}
        if method == "POST" and path == "/api/v1/rebuild/variables?project_id=41":
            return {"code": 0, "data": {"saved": True}}
        raise AssertionError(f"unexpected request: {method} {path}")


def live_env(tmp_path: Path) -> dict[str, str]:
    key_file = tmp_path / "validation.key"
    key_file.write_text("long-lived-secret\n", encoding="utf-8")
    return {"DATARA_API_BASE": "http://rebuild.test:18091/api-proxy", "DATARA_VALIDATION_KEY_FILE": str(key_file), "DATARA_FIXTURE_MYSQL_PASSWORD": "mysql-secret"}


def allow_validation_host(monkeypatch, module):
    monkeypatch.setattr(module, "host_addresses", lambda: {"127.0.0.1", "192.168.1.9"})


def test_seed_exchanges_key_and_reuses_existing_objects(monkeypatch, tmp_path):
    module = load_seed_module()
    allow_validation_host(monkeypatch, module)
    transport = FakeTransport(existing=True)
    summary = module.seed(module.Settings.from_env(live_env(tmp_path)), transport)
    assert summary["project_id"] == 41
    assert summary["datasource_ids"] == {"source": 51, "dw": 52}
    assert summary["variable_names"] == ["fixture_key"]
    assert summary["file_sync_path"] == FILE_SYNC_PATH
    assert summary["demo_identities"] == {
        "usernames": ["admin", "dev", "analyst", "viewer"],
        "memberships_created": 0,
    }
    assert summary["models"] == {"models_created": 0, "versions_created": 0, "relations_created": 0}
    assert transport.calls[0] == {"method": "POST", "path": "/api/v1/rebuild/validation-token", "headers": {"X-Backend-Validation-Key": "long-lived-secret", "X-Backend-Validation-Scope": "high-priority-e2e"}, "json": None}
    assert all(call["headers"] == {"Authorization": "Bearer short-lived-secret"} for call in transport.calls[1:])
    assert not any("resources" in call["path"] for call in transport.calls)
    # Existing identities are only password-refreshed; no project/datasource/variable is recreated.
    assert [call["path"] for call in transport.calls if call["method"] == "POST"] == [
        "/api/v1/rebuild/validation-token"
    ]


def test_seed_creates_missing_project_datasources_and_variable(monkeypatch, tmp_path):
    module = load_seed_module()
    allow_validation_host(monkeypatch, module)
    transport = FakeTransport(existing=False)
    summary = module.seed(module.Settings.from_env(live_env(tmp_path)), transport)
    posts = [call for call in transport.calls if call["method"] == "POST"]
    assert posts[1]["path"] == "/api/v1/rebuild/projects"
    assert posts[1]["json"] == {"name": "INFRA-DATA-01 电商闭环验证", "description": "INFRA-DATA-01 deterministic product closure fixture"}
    user_posts = [call for call in posts if call["path"] == "/api/v1/rebuild/users"]
    assert [call["json"] for call in user_posts] == [
        {"username": "admin", "password": "Admin@123", "role": "admin"},
        {"username": "dev", "password": "Dev@123", "role": "developer"},
        {"username": "analyst", "password": "Analyst@123", "role": "operator"},
        {"username": "viewer", "password": "Viewer@123", "role": "viewer"},
    ]
    assert summary["demo_identities"] == {
        "usernames": ["admin", "dev", "analyst", "viewer"],
        "memberships_created": 3,
    }
    datasource_posts = [call for call in posts if call["path"].endswith("/datasources")]
    assert [call["json"]["name"] for call in datasource_posts] == ["INFRA-DATA-01 source", "INFRA-DATA-01 dw"]
    assert [call["json"]["database"] for call in datasource_posts] == ["ec_retail", "datara_dw"]
    variable_post = next(call for call in posts if "/variables?" in call["path"])
    assert variable_post["json"] == {"scope": "project", "name": "fixture_key", "value_type": "string", "value": "INFRA-DATA-01", "description": "Deterministic isolated validation fixture key"}
    assert summary["datasource_ids"] == {"source": 51, "dw": 52}
    assert summary["file_sync_path"] == FILE_SYNC_PATH
    assert summary["models"] == {"models_created": 3, "versions_created": 3, "relations_created": 2}


def test_seed_rejects_non_validation_host_before_key_or_network(monkeypatch, tmp_path):
    module = load_seed_module()
    monkeypatch.setattr(module, "host_addresses", lambda: {"127.0.0.1", "192.168.1.8"})
    monkeypatch.setattr(Path, "read_text", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("read key")))
    transport = FakeTransport()
    try:
        module.seed(module.Settings.from_env(live_env(tmp_path)), transport)
    except module.HostGuardError as exc:
        assert "192.168.1.9" in str(exc)
    else:
        raise AssertionError("non-validation host was accepted")
    assert transport.calls == []


def test_dry_run_returns_before_guard_key_or_network(monkeypatch, capsys):
    module = load_seed_module()
    monkeypatch.setattr(module, "host_addresses", lambda: (_ for _ in ()).throw(AssertionError("host guard")))
    monkeypatch.setattr(Path, "read_text", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("read key")))
    monkeypatch.setattr(module, "UrllibTransport", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("network transport")))
    assert module.main(["--dry-run"], environ={}) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["dry_run"] is True
    assert payload["object_types"] == ["identity", "project-member", "project", "datasource:source", "datasource:dw", "variable", "model", "model-field", "model-version", "model-relation", "file_sync:csv"]
    assert payload["file_sync_path"] == FILE_SYNC_PATH
    assert not any("resources" in endpoint for endpoint in payload["endpoints"])
    assert f"{API_PREFIX}/users" in payload["endpoints"]
    assert f"{API_PREFIX}/projects/{{project_id}}/members" in payload["endpoints"]
    assert f"{API_PREFIX}/models/{{model_id}}/versions" in payload["endpoints"]


def test_main_prints_only_non_sensitive_json(monkeypatch, tmp_path, capsys):
    module = load_seed_module()
    allow_validation_host(monkeypatch, module)
    transport = FakeTransport()
    monkeypatch.setattr(module, "UrllibTransport", lambda _base: transport)
    assert module.main([], environ=live_env(tmp_path)) == 0
    output = capsys.readouterr()
    assert json.loads(output.out)["file_sync_path"] == FILE_SYNC_PATH
    combined = output.out + output.err
    for secret in ("long-lived-secret", "short-lived-secret", "mysql-secret"):
        assert secret not in combined


def test_real_rebuild_api_contract_supports_token_project_and_variable(tmp_path, monkeypatch):
    monkeypatch.setenv("REBUILD_RESOURCE_STORAGE_DIR", str(tmp_path))
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="infra-data-contract-secret", validation_key="server-held-key")
    with TestClient(app) as client:
        exchange = client.post("/api/v1/rebuild/validation-token", headers={"X-Backend-Validation-Key": "server-held-key", "X-Backend-Validation-Scope": "high-priority-e2e"})
        assert exchange.status_code == 200
        auth = {"Authorization": f"Bearer {exchange.json()['data']['token']}"}
        created = client.post("/api/v1/rebuild/projects", headers=auth, json={"name": "INFRA-DATA-01 电商闭环验证", "description": "contract"})
        assert created.status_code == 200
        project_id = created.json()["data"]["id"]
        listed = client.get("/api/v1/rebuild/projects", headers=auth)
        assert any(row["id"] == project_id for row in listed.json()["data"]["list"])
        variable = client.post(f"/api/v1/rebuild/variables?project_id={project_id}", headers=auth, json={"scope": "project", "name": "fixture_key", "value": "INFRA-DATA-01"})
        assert variable.status_code == 200
        assert variable.json()["data"] == {"saved": True, "scope": "project", "name": "fixture_key"}


def test_prepare_and_docs_define_shared_file_sync_path():
    prepare = (FIXTURE_DIR / "prepare.sh").read_text(encoding="utf-8")
    readme = (FIXTURE_DIR / "README.md").read_text(encoding="utf-8")
    assert "files/fixtures/orders_file_sync.csv" in prepare
    assert 'cp "$FIXTURE_DIR/files/orders_file_sync.csv"' in prepare
    assert FILE_SYNC_PATH in readme
    assert "baseMode=file_sync" in readme
    assert "filePath" in readme and "fileType=csv" in readme
    assert "/api/v1/rebuild/resources/uploads" not in readme
