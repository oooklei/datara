from common.models import TRunNodeArtifact


def test_node_artifact_is_persisted_with_signature_and_refs(db_session):
    row = TRunNodeArtifact(
        run_id="run-1",
        node_id="n1",
        node_signature="a" * 64,
        artifact_fingerprint="b" * 64,
        refs={"table": "tmp_orders"},
    )
    db_session.add(row)
    db_session.commit()
    found = db_session.query(TRunNodeArtifact).filter_by(run_id="run-1", node_id="n1").one()
    assert found.node_signature == "a" * 64
    assert found.refs == {"table": "tmp_orders"}
