"""TDD 测试：impact_snapshot 适配 (impacts, unknown_reasons) 元组返回（C10）。

C10 = R5B-02：ImpactSnapshotService 正确消费 LineageAnalyzer 新返回类型。
- 真实依赖：analyzer 返回 impacts，snapshot 正确携带
- Mock 无关系：analyzer 返回 ([], [])，snapshot impacts 为空
- 方言不支持：analyzer 返回 unknown_reasons，snapshot 正确携带
- 权限拒绝：dependency_query 抛异常 → analyzer 不崩溃

测试一律 mock/内存库，禁止对目标库真实写入。
"""
from __future__ import annotations

from hashlib import sha256

import pytest

from rebuild.rb.models.rb_models import ObjectRef
from rebuild.rb.impact.impact_snapshot import ImpactSnapshotService
from rebuild.rb.lineage.lineage_analyzer import LineageAnalyzer


def _make_ref(
    name: str = "users",
    schema: str = "public",
    kind: str = "table",
) -> ObjectRef:
    return ObjectRef(
        datasource_id=101,
        database="mydb",
        catalog=None,
        schema=schema,
        kind=kind,
        name=name,
        parent=None,
    )


def _mock_get_definition(factory_result):
    def _service(*, datasource_id, object_ref):
        return factory_result
    return _service


class TestImpactSnapshotWithLineageAnalyzer:
    """验证 ImpactSnapshotService 正确消费 (impacts, unknown_reasons) 元组。"""

    def test_real_dependencies_flow_to_snapshot(self):
        """真实依赖：analyzer 返回 impacts，snapshot 正确携带。"""
        ddl = "CREATE TABLE orders (id INT, FOREIGN KEY (user_id) REFERENCES users(id));"
        analyzer = LineageAnalyzer(get_definition_service=_mock_get_definition({"definitionText": ddl}))
        service = ImpactSnapshotService(analyzer=analyzer)
        snapshot = service.preview_and_snapshot(
            project_id=1, datasource_id=101,
            object_ref=_make_ref(name="orders"),
            source_version="etag-abc123",
            next_ddl_text="ALTER TABLE orders ADD COLUMN email VARCHAR(255);",
        )
        assert snapshot.snapshot_id is not None
        assert len(snapshot.impacts) >= 1
        assert snapshot.unknown_reasons == []

    def test_mock_no_relationships(self):
        """Mock 无关系：无依赖 DDL → impacts=[] + unknown_reasons=[]。"""
        ddl = "CREATE TABLE orders (id INT, name VARCHAR(50));"
        analyzer = LineageAnalyzer(get_definition_service=_mock_get_definition({"definitionText": ddl}))
        service = ImpactSnapshotService(analyzer=analyzer)
        snapshot = service.preview_and_snapshot(
            project_id=1, datasource_id=101,
            object_ref=_make_ref(name="orders"),
            source_version="etag-abc123",
            next_ddl_text="ALTER TABLE orders ADD COLUMN email VARCHAR(255);",
        )
        assert snapshot.impacts == []
        assert snapshot.unknown_reasons == []

    def test_unsupported_dialect_fail_closed(self):
        """方言不支持：analyzer 返回 unknown_reasons，snapshot 正确携带。"""
        ddl = "CREATE TABLE test (id INT, UNKNOWN_SYNTAX_!!@#);"
        analyzer = LineageAnalyzer(get_definition_service=_mock_get_definition({"definitionText": ddl}))
        service = ImpactSnapshotService(analyzer=analyzer)
        snapshot = service.preview_and_snapshot(
            project_id=1, datasource_id=101,
            object_ref=_make_ref(name="test"),
            source_version="etag-abc123",
            next_ddl_text="ALTER TABLE test ADD COLUMN email VARCHAR(255);",
        )
        assert len(snapshot.unknown_reasons) > 0
        assert snapshot.impacts == []

    def test_dependency_query_permission_denied(self):
        """权限拒绝：dependency_query 抛异常 → analyzer 不崩溃。"""
        ddl = "CREATE TABLE orders (id INT);"

        class PermissionDeniedQuery:
            def get_dependencies(self, *, datasource_id, schema, table):
                raise PermissionError("Access denied to information_schema")

        analyzer = LineageAnalyzer(
            get_definition_service=_mock_get_definition({"definitionText": ddl}),
            dependency_query=PermissionDeniedQuery(),
        )
        service = ImpactSnapshotService(analyzer=analyzer)
        snapshot = service.preview_and_snapshot(
            project_id=1, datasource_id=101,
            object_ref=_make_ref(name="orders"),
            source_version="etag-abc123",
            next_ddl_text="ALTER TABLE orders ADD COLUMN email VARCHAR(255);",
        )
        # 当前实现：异常被静默跳过，impacts 为空（不崩溃）
        assert snapshot.impacts == []

    def test_no_analyzer_returns_lineage_unavailable(self):
        """无 analyzer → snapshot 携带 lineage_unavailable。"""
        service = ImpactSnapshotService(analyzer=None)
        snapshot = service.preview_and_snapshot(
            project_id=1, datasource_id=101,
            object_ref=_make_ref(),
            source_version="etag-abc123",
            next_ddl_text="ALTER TABLE users ADD COLUMN email VARCHAR(255);",
        )
        assert snapshot.impacts == []
        assert "lineage_unavailable" in snapshot.unknown_reasons

    def test_snapshot_digest_binds_next_ddl(self):
        """snapshot 的 next_ddl_digest 绑定 next_ddl_text。"""
        ddl = "CREATE TABLE orders (id INT);"
        analyzer = LineageAnalyzer(get_definition_service=_mock_get_definition({"definitionText": ddl}))
        service = ImpactSnapshotService(analyzer=analyzer)
        next_ddl = "ALTER TABLE orders ADD COLUMN email VARCHAR(255);"
        snapshot = service.preview_and_snapshot(
            project_id=1, datasource_id=101,
            object_ref=_make_ref(name="orders"),
            source_version="etag-abc123",
            next_ddl_text=next_ddl,
        )
        assert snapshot.next_ddl_digest == sha256(next_ddl.encode("utf-8")).hexdigest()

    def test_get_snapshot_roundtrip(self):
        """get_snapshot 应返回同一 snapshot。"""
        service = ImpactSnapshotService(analyzer=None)
        snapshot = service.preview_and_snapshot(
            project_id=1, datasource_id=101,
            object_ref=_make_ref(),
            source_version="etag-abc123",
            next_ddl_text="ALTER TABLE users ADD COLUMN email VARCHAR(255);",
        )
        retrieved = service.get_snapshot(snapshot.snapshot_id)
        assert retrieved is not None
        assert retrieved.snapshot_id == snapshot.snapshot_id
        assert retrieved.unknown_reasons == snapshot.unknown_reasons

    def test_validate_snapshot_success_with_lineage(self):
        """validate_snapshot 应通过（版本和 DDL 一致）。"""
        ddl = "CREATE TABLE orders (id INT);"
        analyzer = LineageAnalyzer(get_definition_service=_mock_get_definition({"definitionText": ddl}))
        service = ImpactSnapshotService(analyzer=analyzer)
        next_ddl = "ALTER TABLE orders ADD COLUMN email VARCHAR(255);"
        snapshot = service.preview_and_snapshot(
            project_id=1, datasource_id=101,
            object_ref=_make_ref(name="orders"),
            source_version="etag-abc123",
            next_ddl_text=next_ddl,
        )
        validated = service.validate_snapshot(
            snapshot_id=snapshot.snapshot_id,
            project_id=1, datasource_id=101,
            object_ref=_make_ref(name="orders"),
            source_version="etag-abc123",
            next_ddl_text=next_ddl,
        )
        assert validated.snapshot_id == snapshot.snapshot_id

    def test_validate_snapshot_ddl_mismatch(self):
        """DDL 变更后 validate_snapshot 应抛异常。"""
        ddl = "CREATE TABLE orders (id INT);"
        analyzer = LineageAnalyzer(get_definition_service=_mock_get_definition({"definitionText": ddl}))
        service = ImpactSnapshotService(analyzer=analyzer)
        snapshot = service.preview_and_snapshot(
            project_id=1, datasource_id=101,
            object_ref=_make_ref(name="orders"),
            source_version="etag-abc123",
            next_ddl_text="ALTER TABLE orders ADD COLUMN email VARCHAR(255);",
        )
        with pytest.raises(Exception) as exc_info:
            service.validate_snapshot(
                snapshot_id=snapshot.snapshot_id,
                project_id=1, datasource_id=101,
                object_ref=_make_ref(name="orders"),
                source_version="etag-abc123",
                next_ddl_text="ALTER TABLE orders ADD COLUMN phone VARCHAR(20);",
            )
        assert "SNAPSHOT_MISMATCH" in str(exc_info.value)
