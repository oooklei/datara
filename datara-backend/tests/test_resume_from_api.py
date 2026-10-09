from common.models import Command, WfDefinition, WorkflowInstance


def test_resume_from_queues_scoped_command(client, db_session):
    db_session.add(WfDefinition(id="wf-resume", code=101, name="resume", graph_json='{"nodes": [], "edges": []}'))
    db_session.add(WorkflowInstance(instance_id="run-resume", wf_code=101, state="failure"))
    db_session.commit()

    response = client.post(
        "/api/v1/workflow-definitions/wf-resume/runs/run-resume/resume-from",
        json={"fromNodeIds": ["n2", "n1"]},
    )
    assert response.status_code == 200
    command = db_session.query(Command).one()
    assert command.command_type == "RESUME_FROM"
    assert command.command_param == {"instanceId": "run-resume", "fromNodeIds": ["n1", "n2"]}


def test_resume_from_rejects_instance_from_another_workflow(client, db_session):
    db_session.add(WfDefinition(id="wf-a", code=101, name="a"))
    db_session.add(WorkflowInstance(instance_id="run-other", wf_code=202, state="failure"))
    db_session.commit()
    response = client.post(
        "/api/v1/workflow-definitions/wf-a/runs/run-other/resume-from",
        json={"fromNodeIds": ["n1"]},
    )
    assert response.status_code == 404
