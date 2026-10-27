from infra.seed_ecommerce_demo import PROJECT_NAME, build_blueprints, prime_stream_observation, reconcile_demo


class FakeApi:
    def __init__(self):
        self.projects = []
        self.workflows = []
        self.details = {}
        self.jobs = []
        self.next_project = 33
        self.next_workflow = 100
        self.next_job = 200
        self.calls = []

    def get(self, path, params=None):
        if path == "/api/v1/rebuild/projects":
            return {"list": self.projects}
        if path == "/api/v1/rebuild/workflows":
            return [row for row in self.workflows if row["project_id"] == params["project_id"]]
        if path.startswith("/api/v1/rebuild/workflows/"):
            return self.details[int(path.rsplit("/", 1)[1])]
        if path == "/api/v1/rebuild/components/spec":
            types = {node["type"] for flow in build_blueprints() if flow["workflow_type"] == params["workflow_type"] for node in flow["nodes"]}
            return {"items": [{"type": item, "publishedVersion": 1} for item in types]}
        if path == "/api/v1/rebuild/stream/jobs":
            return [row for row in self.jobs if row["project_id"] == params["project_id"]]
        raise AssertionError((path, params))

    def post(self, path, body):
        self.calls.append((path, body))
        if path == "/api/v1/rebuild/projects":
            row = {"id": self.next_project, **body}
            self.projects.append(row)
            return row
        if path == "/api/v1/rebuild/workflows":
            row = {"definition_id": self.next_workflow, **body}
            self.next_workflow += 1
            self.workflows.append(row)
            self.details[row["definition_id"]] = {**row, "draft": {"nodes": [], "edges": []}}
            return row
        if path.endswith("/nodes"):
            workflow_id = int(path.split("/")[-2])
            rows = self.details[workflow_id]["draft"]["nodes"]
            rows[:] = [row for row in rows if row["node_code"] != body["node_code"]]
            rows.append(body)
            return body
        if path.endswith("/edges"):
            workflow_id = int(path.split("/")[-2])
            rows = self.details[workflow_id]["draft"]["edges"]
            key = (body["from_node"], body["to_node"])
            rows[:] = [row for row in rows if (row["from_node"], row["to_node"]) != key]
            rows.append(body)
            return body
        if path == "/api/v1/rebuild/stream/jobs":
            row = {"id": self.next_job, "state": "CREATED", **body}
            self.next_job += 1
            self.jobs.append(row)
            return row
        if path.startswith("/api/v1/rebuild/stream/jobs/"):
            return {"ok": True}
        raise AssertionError((path, body))


def test_blueprints_cover_the_user_visible_normal_sync_and_stream_samples():
    flows = build_blueprints()
    assert [flow["workflow_type"] for flow in flows] == ["NORMAL", "SYNC", "STREAM"]
    assert {node["type"] for node in flows[0]["nodes"]} == {"sql", "python", "shell", "dependent"}
    assert {node["type"] for node in flows[1]["nodes"]} == {
        "src_base_orch", "tgt_base_orch", "file_sync_orch", "endpoint_select",
        "field_map", "field_map_union", "condition_set",
    }
    assert {node["type"] for node in flows[2]["nodes"]} == {"stream_input", "stream_fuse", "stream_output", "page_board"}


def test_reconcile_is_idempotent_and_keeps_one_product_project_and_three_workflows():
    api = FakeApi()
    first = reconcile_demo(api)
    second = reconcile_demo(api)

    assert first["project_name"] == PROJECT_NAME
    assert second["project_id"] == first["project_id"]
    assert len(api.projects) == 1
    assert len(api.workflows) == 3
    assert len(api.jobs) == 1
    assert all(api.details[row["definition_id"]]["draft"]["nodes"] for row in api.workflows)


def test_prime_stream_observation_uses_the_runtime_produce_and_fuse_contracts():
    api = FakeApi()

    prime_stream_observation(api, {"stream_job_created": True, "stream_job_id": 200})

    produce = next(body for path, body in api.calls if path.endswith("/produce"))
    fuse = next(body for path, body in api.calls if path.endswith("/fuse"))
    assert produce["count"] == 12
    assert produce["payload"]["business"] == "ecommerce-order"
    assert set(fuse["streams"]) == {"orders", "payments"}
    assert fuse["key_field"] == "order_id"
