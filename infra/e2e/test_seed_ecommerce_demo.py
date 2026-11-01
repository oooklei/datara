import json

import infra.seed_ecommerce_demo as seed


class FakeApi:
    def __init__(self):
        self.workflows = []
        self.calls = []
        self.hide_workflows = False

    def get(self, path, params=None):
        self.calls.append(("GET", path, params))
        if path == "/api/v1/rebuild/projects":
            return {"list": [{"id": 33, "name": seed.PROJECT_NAME}]}
        if path == "/api/v1/rebuild/orchestration/datasources":
            return [{"id": "source-id", "type": "MYSQL", "project_id": 33}]
        if path == "/api/v1/rebuild/orchestration/session":
            return {"projectCode": "98765", "token": "short-lived-embed"}
        if path == "/api/v1/rebuild/orchestration/workflow-definitions":
            if self.hide_workflows:
                return {"list": []}
            return {"list": [row for row in self.workflows if params["search_val"] in row["name"]]}
        raise AssertionError((path, params))

    def create_ds_workflow(self, project_code, embed_token, form):
        self.calls.append(("POST", project_code, embed_token, form))
        row = {"code": len(self.workflows) + 100, "name": form["name"]}
        self.workflows.append(row)
        return row

    def post(self, path, body=None, params=None):
        self.calls.append(("POST_GATEWAY", path, body, params))
        return {"id": 456} if path.endswith("/start") else {}


def test_sql_workflow_form_uses_native_ds_sql_task_and_dbx_connection():
    form = seed.sql_workflow_form("订单对账", "SELECT 1", "dbx-source", "MYSQL")
    task = json.loads(form["taskDefinitionJson"])[0]
    params = json.loads(task["taskParams"])
    relation = json.loads(form["taskRelationJson"])[0]
    assert task["taskType"] == "SQL"
    assert params["datasource"] == "dbx-source"
    assert params["type"] == "MYSQL"
    assert params["sql"] == "SELECT 1"
    assert relation["preTaskCode"] == 0
    assert relation["postTaskCode"] == task["code"]
    assert json.loads(form["locations"])[0]["taskCode"] == task["code"]
    assert json.loads(form["globalParams"]) == []


def test_reconcile_injects_fixture_variables_into_workflow_global_params():
    api = FakeApi()
    seed.reconcile_demo(api, connection_id="source-id")

    created = [call[3] for call in api.calls if call[0] == "POST"]
    assert len(created) == 3
    for form in created:
        props = {row["prop"]: row["value"] for row in json.loads(form["globalParams"])}
        assert props["project.ecom_sim_20261030_biz_date"] == "2026-10-23"
        assert props["project.ecom_sim_20261030_safety_stock"] == "10"
        assert props["project.ecom_sim_20261030_source_schema"] == "ecom_sim_20261030"
        assert all(row["direct"] == "IN" for row in json.loads(form["globalParams"]))


def test_reconcile_creates_three_current_dags_once_without_legacy_workflow_calls():
    api = FakeApi()
    first = seed.reconcile_demo(api, connection_id="source-id")
    second = seed.reconcile_demo(api, connection_id="source-id")

    assert first["project_id"] == 33
    assert first["project_code"] == "98765"
    assert len(first["workflows"]) == len(seed.WORKFLOWS) == 3
    assert all(row["created"] for row in first["workflows"])
    assert all(not row["created"] for row in second["workflows"])
    assert [row["name"] for row in api.workflows] == [name for name, _ in seed.WORKFLOWS]
    assert all(call[1] == "98765" and call[2] == "short-lived-embed"
               for call in api.calls if call[0] == "POST")
    assert not any("/rebuild/workflows" in call[1] or "/rebuild/execution" in call[1]
                   for call in api.calls if call[0] == "GET")


def test_reconcile_rejects_connection_outside_project():
    api = FakeApi()
    try:
        seed.reconcile_demo(api, connection_id="foreign")
    except RuntimeError as exc:
        assert "not visible" in str(exc)
    else:
        raise AssertionError("foreign connection was accepted")
    assert not any(call[0] == "POST" for call in api.calls)


def test_reconcile_fails_when_created_dag_is_missing_from_task_center():
    api = FakeApi()
    api.hide_workflows = True
    try:
        seed.reconcile_demo(api, connection_id="source-id")
    except RuntimeError as exc:
        assert "not visible in Datara task center" in str(exc)
    else:
        raise AssertionError("missing workflow was reported as successful")


def test_ds_save_sends_only_the_scoped_embed_token(monkeypatch):
    requests_seen = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"code": 0, "data": {"code": 12345}}

    def post(url, *, data, headers, timeout):
        requests_seen.append((url, data, headers, timeout))
        return Response()

    monkeypatch.setattr(seed.requests, "post", post)
    api = seed.HttpApi("http://localhost:8090", "datara-bearer")
    result = api.create_ds_workflow("98765", "embed-token", {"name": "sample"})

    assert result["code"] == 12345
    url, data, headers, _ = requests_seen[0]
    assert url.endswith("/dolphinscheduler/projects/98765/workflow-definition")
    assert data == {"name": "sample"}
    assert headers == {"X-Datara-Embed-Token": "embed-token"}
    assert "datara-bearer" not in str(requests_seen)


def test_formal_sample_uses_current_release_and_start_routes():
    api = FakeApi()
    result = seed.reconcile_demo(api, connection_id="source-id")
    run = seed.run_formal_sample(api, result)

    assert run == {"id": 456}
    assert api.calls[-2:] == [
        ("POST_GATEWAY", "/api/v1/rebuild/orchestration/workflow-definitions/100/release", None,
         {"project_id": 33, "release_state": "ONLINE"}),
        ("POST_GATEWAY", "/api/v1/rebuild/orchestration/workflow-instances/start",
         {"projectId": 33, "workflowDefinitionCode": 100, "dryRun": False}, None),
    ]
