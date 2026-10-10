"""Task 26 workflow template library API contract."""

from common.models import WfDefinition


def _doc():
    return {
        "id": "wf_source",
        "name": "Source",
        "version": 4,
        "meta": {"profile": "dag"},
        "nodes": [
            {"id": "n_10", "type": "start", "position": {"x": 0, "y": 0}, "data": {"name": "Start"}},
            {"id": "n_11", "type": "end", "position": {"x": 100, "y": 0}, "data": {"name": "End"}},
        ],
        "edges": [{"id": "e_20", "source": "n_10", "target": "n_11", "kind": "flow"}],
        "variables": [{"id": "v_30", "name": "day", "value": "today"}],
        "groups": [{"id": "g_40", "name": "main", "nodeIds": ["n_10", "n_11"]}],
    }


def test_template_crud_and_version_chain(client):
    created = client.post("/api/v1/workflow-templates", json={
        "name": "Daily load", "category": "ETL", "description": "Reusable", "templateJson": _doc(),
    })
    assert created.status_code == 200
    row = created.json()["data"]
    assert row["version"] == 1

    listed = client.get("/api/v1/workflow-templates").json()["data"]
    assert [item["id"] for item in listed] == [row["id"]]
    assert client.get(f"/api/v1/workflow-templates/{row['id']}").json()["data"]["templateJson"] == _doc()

    changed = _doc()
    changed["nodes"][1]["data"]["name"] = "Finish"
    updated = client.put(f"/api/v1/workflow-templates/{row['id']}", json={
        "name": "Daily load v2", "category": "ETL", "description": "Updated", "templateJson": changed,
    }).json()["data"]
    assert updated["version"] == 2
    versions = client.get(f"/api/v1/workflow-templates/{row['id']}/versions").json()["data"]
    assert [v["version"] for v in versions] == [2, 1]
    assert versions[1]["templateJson"] == _doc()

    assert client.delete(f"/api/v1/workflow-templates/{row['id']}").json()["data"] is True
    assert client.get(f"/api/v1/workflow-templates/{row['id']}").status_code == 404


def test_instantiate_creates_draft_with_all_graph_ids_regenerated(client, db_session):
    template = client.post("/api/v1/workflow-templates", json={
        "name": "Daily load", "category": "ETL", "templateJson": _doc(),
    }).json()["data"]

    response = client.post(f"/api/v1/workflow-templates/{template['id']}/instantiate", json={"name": "My daily load"})
    assert response.status_code == 200
    result = response.json()["data"]
    workflow = client.get(f"/api/v1/workflow-definitions/{result['id']}").json()["data"]

    assert workflow["name"] == "My daily load"
    assert workflow["version"] == 1
    assert workflow["meta"]["templateId"] == template["id"]
    assert workflow["meta"]["templateVersion"] == 1
    assert {n["id"] for n in workflow["nodes"]}.isdisjoint({"n_10", "n_11"})
    assert workflow["edges"][0]["id"] != "e_20"
    assert workflow["edges"][0]["source"] == workflow["nodes"][0]["id"]
    assert workflow["edges"][0]["target"] == workflow["nodes"][1]["id"]
    assert workflow["variables"][0]["id"] != "v_30"
    assert workflow["groups"][0]["id"] != "g_40"
    assert workflow["groups"][0]["nodeIds"] == [n["id"] for n in workflow["nodes"]]
    persisted = db_session.get(WfDefinition, result["id"])
    assert persisted is not None and persisted.release_state == "offline"


def test_old_instance_reports_optional_upgrade_after_template_update(client):
    template = client.post("/api/v1/workflow-templates", json={"name": "Base", "templateJson": _doc()}).json()["data"]
    instance = client.post(f"/api/v1/workflow-templates/{template['id']}/instantiate", json={}).json()["data"]
    client.put(f"/api/v1/workflow-templates/{template['id']}", json={"name": "Base", "templateJson": _doc()})

    status = client.get(f"/api/v1/workflow-templates/upgrade-status/{instance['id']}").json()["data"]
    assert status == {"upgradeAvailable": True, "templateId": template["id"], "currentVersion": 1, "latestVersion": 2}

