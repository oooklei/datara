import infra.seed_ecommerce_demo as seed
from infra.seed_ecommerce_demo import (
    PROJECT_NAME,
    build_blueprints,
    prime_stream_observation,
    reconcile_demo,
    run_formal_sample,
)


def test_demo_project_name_matches_the_product_navigation_default():
    assert PROJECT_NAME == "电商全域数据治理项目"


class FakeApi:
    def __init__(self):
        self.projects = []
        self.workflows = []
        self.details = {}
        self.jobs = []
        self.next_project = 33
        self.next_workflow = 100
        self.next_job = 200
        self.next_version = 900
        self.next_instance = 500
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
        if path.endswith("/datasources"):
            return {"items": [
                {"datasource_id": 11, "name": "内置源库-ec_retail"},
                {"datasource_id": 12, "name": "内置数仓-datara_dw"},
            ]}
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
        if path == "/api/v1/rebuild/dependency/saves":
            return {"saved": True, "version": 1, "config_id": 301}
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
        if path.endswith("/publish"):
            definition_id = int(path.split("/")[-2])
            row = {"id": self.next_version, "definition_id": definition_id, "version": 1, "status": "PUBLISHED"}
            self.next_version += 1
            return row
        if path == "/api/v1/rebuild/execution/workflow-instances":
            codes = [node["code"] for node in build_blueprints()[0]["nodes"]]
            row = {
                "instance_id": self.next_instance,
                "workflow_id": body["workflow_id"],
                "workflow_version_id": body["publish_version"],
                "instance_type": "FORMAL",
                "status": "PENDING",
                "tasks": [
                    {"task_instance_id": 700 + index, "task_id": code, "status": "PENDING", "current_attempt_no": 0}
                    for index, code in enumerate(codes)
                ],
            }
            self.next_instance += 1
            return row
        raise AssertionError((path, body))


def test_blueprints_cover_the_user_visible_normal_sync_and_stream_samples():
    flows = build_blueprints()
    assert [flow["workflow_type"] for flow in flows] == ["NORMAL", "SYNC", "STREAM"]
    assert {node["type"] for node in flows[0]["nodes"]} == {"sql", "python", "shell", "dependent"}
    sql_node = next(node for node in flows[0]["nodes"] if node["type"] == "sql")
    dependency = next(node for node in flows[0]["nodes"] if node["type"] == "dependent")
    assert sql_node["params"]["execute"] is True
    assert dependency["params"]["dependency_id"] == "configured-at-seed"
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


def test_normal_sample_publishes_the_graph_and_starts_one_formal_instance():
    runner = getattr(seed, "run_formal_sample", None)
    assert callable(runner)
    assert getattr(seed, "run_normal_sample", None) is None  # 试运行(trial) 域已废弃
    api = FakeApi()
    result = runner(api, project_id=33, workflow_id=100)
    assert result["instance_type"] == "FORMAL"
    assert result["status"] == "PENDING"
    assert result["task_count"] == 4
    assert all(task["status"] == "PENDING" for task in result["tasks"])
    published = next(body for path, body in api.calls if path.endswith("/publish"))
    assert published == {"project_id": 33, "remark": "seeded demo publish"}
    run_body = next(body for path, body in api.calls if path == "/api/v1/rebuild/execution/workflow-instances")
    assert run_body == {
        "project_id": 33,
        "workflow_id": 100,
        "instance_type": "FORMAL",
        "trigger_type": "MANUAL",
        "publish_version": 900,
    }
