"""Task 26 workflow template library API contract."""

from common.models import WfDefinition


def _doc():
    return {
        "id": "wf_source",
        "name": "Source",
        "version": 4,
        "meta": {"profile": "dag"},
        "nodes": [
            {
                "id": "n_10",
                "type": "start",
                "position": {"x": 0, "y": 0},
                "data": {
                    "name": "Start",
                    "branches": [{"id": "br_7", "parentId": "n_10", "ref": "n_11:input"}],
                },
            },
            {"id": "n_11", "type": "end", "position": {"x": 100, "y": 0}, "data": {"name": "End"}},
        ],
        "edges": [{"id": "e_20", "source": "n_10", "target": "n_11", "kind": "flow"}],
        "variables": [{"id": "v_30", "name": "day", "value": "today"}],
        "groups": [{"id": "g_40", "name": "main", "nodeIds": ["n_10", "n_11"]}],
    }


def test_template_crud_and_version_chain(client):
    created = client.post(
        "/api/v1/workflow-templates",
        json={
            "name": "Daily load",
            "category": "ETL",
            "description": "Reusable",
            "templateJson": _doc(),
        },
    )
    assert created.status_code == 200
    row = created.json()["data"]
    assert row["version"] == 1

    listed = client.get("/api/v1/workflow-templates").json()["data"]
    assert [item["id"] for item in listed] == [row["id"]]
    assert client.get(f"/api/v1/workflow-templates/{row['id']}").json()["data"]["templateJson"] == _doc()

    changed = _doc()
    changed["nodes"][1]["data"]["name"] = "Finish"
    updated = client.put(
        f"/api/v1/workflow-templates/{row['id']}",
        json={
            "name": "Daily load v2",
            "category": "ETL",
            "description": "Updated",
            "templateJson": changed,
            "baseVersion": 1,
        },
    ).json()["data"]
    assert updated["version"] == 2
    versions = client.get(f"/api/v1/workflow-templates/{row['id']}/versions").json()["data"]
    assert [v["version"] for v in versions] == [2, 1]
    assert versions[1]["templateJson"] == _doc()

    assert client.delete(f"/api/v1/workflow-templates/{row['id']}").json()["data"] is True
    assert client.get(f"/api/v1/workflow-templates/{row['id']}").status_code == 404


def test_instantiate_creates_draft_with_all_graph_ids_regenerated(client, db_session):
    template = client.post(
        "/api/v1/workflow-templates",
        json={
            "name": "Daily load",
            "category": "ETL",
            "templateJson": _doc(),
        },
    ).json()["data"]

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
    assert [n["id"] for n in workflow["nodes"]] == ["n_12", "n_13"]
    assert workflow["edges"][0]["id"] == "e_21"
    assert workflow["variables"][0]["id"] == "v_31"
    assert workflow["groups"][0]["id"] == "g_41"
    assert workflow["nodes"][0]["data"]["branches"][0] == {
        "id": "br_8",
        "parentId": "n_12",
        "ref": "n_13:input",
    }
    persisted = db_session.get(WfDefinition, result["id"])
    assert persisted is not None and persisted.release_state == "offline"


def test_old_instance_reports_optional_upgrade_after_template_update(client):
    template = client.post("/api/v1/workflow-templates", json={"name": "Base", "templateJson": _doc()}).json()["data"]
    instance = client.post(f"/api/v1/workflow-templates/{template['id']}/instantiate", json={}).json()["data"]
    client.put(
        f"/api/v1/workflow-templates/{template['id']}",
        json={"name": "Base", "templateJson": _doc(), "baseVersion": 1},
    )

    status = client.get(f"/api/v1/workflow-templates/upgrade-status/{instance['id']}").json()["data"]
    assert status == {"upgradeAvailable": True, "templateId": template["id"], "currentVersion": 1, "latestVersion": 2}


def test_upgrade_preview_is_normalized_and_confirm_is_cas_guarded(client, db_session):
    template = client.post("/api/v1/workflow-templates", json={"name": "Base", "templateJson": _doc()}).json()["data"]
    instance = client.post(
        f"/api/v1/workflow-templates/{template['id']}/instantiate",
        json={"name": "Custom name"},
    ).json()["data"]
    changed = _doc()
    changed["nodes"][1]["data"]["name"] = "Finish"
    client.put(
        f"/api/v1/workflow-templates/{template['id']}",
        json={"name": "Base", "templateJson": changed, "baseVersion": 1},
    )
    preview = client.get(f"/api/v1/workflow-templates/{template['id']}/diff/{instance['id']}").json()["data"]
    assert preview["workflowVersion"] == 1
    assert preview["currentVersion"] == 1
    assert preview["latestVersion"] == 2
    assert [item["path"] for item in preview["diff"]] == ["nodes[1].data.name"]

    conflict = client.post(
        f"/api/v1/workflow-templates/{template['id']}/upgrade/{instance['id']}",
        json={
            "baseVersion": 999,
            "templateVersion": 1,
            "targetTemplateVersion": 2,
        },
    )
    assert conflict.status_code == 409
    row = db_session.get(WfDefinition, instance["id"])
    row.release_state = "online"
    db_session.commit()
    locked = client.post(
        f"/api/v1/workflow-templates/{template['id']}/upgrade/{instance['id']}",
        json={
            "baseVersion": 1,
            "templateVersion": 1,
            "targetTemplateVersion": 2,
        },
    )
    assert locked.status_code == 409
    row.release_state = "offline"
    db_session.commit()
    upgraded = client.post(
        f"/api/v1/workflow-templates/{template['id']}/upgrade/{instance['id']}",
        json={
            "baseVersion": 1,
            "templateVersion": 1,
            "targetTemplateVersion": 2,
        },
    )
    assert upgraded.status_code == 200
    doc = upgraded.json()["data"]
    assert doc["name"] == "Custom name"
    assert doc["nodes"][1]["data"]["name"] == "Finish"


def test_upgrade_rejects_wrong_template_and_stale_instance_template_version(client):
    first = client.post("/api/v1/workflow-templates", json={"name": "First", "templateJson": _doc()}).json()["data"]
    second = client.post("/api/v1/workflow-templates", json={"name": "Second", "templateJson": _doc()}).json()["data"]
    instance = client.post(f"/api/v1/workflow-templates/{first['id']}/instantiate", json={}).json()["data"]
    assert client.get(f"/api/v1/workflow-templates/{second['id']}/diff/{instance['id']}").status_code == 409
    stale = client.post(
        f"/api/v1/workflow-templates/{first['id']}/upgrade/{instance['id']}",
        json={
            "baseVersion": 1,
            "templateVersion": 0,
            "targetTemplateVersion": 1,
        },
    )
    assert stale.status_code == 409


def test_upgrade_rejects_template_changed_after_preview(client):
    template = client.post(
        "/api/v1/workflow-templates",
        json={"name": "Base", "templateJson": _doc()},
    ).json()["data"]
    instance = client.post(
        f"/api/v1/workflow-templates/{template['id']}/instantiate",
        json={},
    ).json()["data"]
    client.put(
        f"/api/v1/workflow-templates/{template['id']}",
        json={"name": "Base v2", "templateJson": _doc(), "baseVersion": 1},
    )
    preview = client.get(f"/api/v1/workflow-templates/{template['id']}/diff/{instance['id']}").json()["data"]
    client.put(
        f"/api/v1/workflow-templates/{template['id']}",
        json={"name": "Base v3", "templateJson": _doc(), "baseVersion": 2},
    )

    response = client.post(
        f"/api/v1/workflow-templates/{template['id']}/upgrade/{instance['id']}",
        json={
            "baseVersion": preview["workflowVersion"],
            "templateVersion": preview["currentVersion"],
            "targetTemplateVersion": preview["latestVersion"],
        },
    )

    assert response.status_code == 409


def test_upgrade_preview_includes_non_collection_graph_settings(client):
    source = _doc()
    source["meta"]["canvasMode"] = "compact"
    template = client.post(
        "/api/v1/workflow-templates",
        json={"name": "Base", "templateJson": source},
    ).json()["data"]
    instance = client.post(
        f"/api/v1/workflow-templates/{template['id']}/instantiate",
        json={},
    ).json()["data"]
    changed = _doc()
    changed["meta"]["canvasMode"] = "comfortable"
    client.put(
        f"/api/v1/workflow-templates/{template['id']}",
        json={"name": "Base", "templateJson": changed, "baseVersion": 1},
    )

    preview = client.get(f"/api/v1/workflow-templates/{template['id']}/diff/{instance['id']}").json()["data"]

    assert {item["path"] for item in preview["diff"]} == {"meta.canvasMode"}


def test_template_update_requires_matching_base_version_and_preserves_creator(client):
    template = client.post("/api/v1/workflow-templates", json={"name": "Base", "templateJson": _doc()}).json()["data"]
    stale = client.put(
        f"/api/v1/workflow-templates/{template['id']}",
        json={
            "name": "Changed",
            "templateJson": _doc(),
            "baseVersion": 9,
        },
    )
    assert stale.status_code == 409
    current = client.get(f"/api/v1/workflow-templates/{template['id']}").json()["data"]
    assert current["version"] == 1
    assert current["createdBy"] == template["createdBy"]


def test_template_update_requires_base_version(client):
    template = client.post(
        "/api/v1/workflow-templates",
        json={"name": "Base", "templateJson": _doc()},
    ).json()["data"]

    response = client.put(
        f"/api/v1/workflow-templates/{template['id']}",
        json={"name": "Changed", "templateJson": _doc()},
    )

    assert response.status_code == 422
