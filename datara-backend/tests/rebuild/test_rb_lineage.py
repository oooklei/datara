"""TDD 测试：rb/lineage/（B4-B lineage_analyzer）。

B4-B 新增：验证血缘分析器。
C6 = R5B-02：更新为 (impacts, unknown_reasons) 元组返回类型。
"""
from __future__ import annotations

from rebuild.rb.models.rb_models import ObjectRef, ImpactItem
from rebuild.rb.lineage.lineage_analyzer import LineageAnalyzer


def _make_ref() -> ObjectRef:
    return ObjectRef(
        datasource_id=101,
        database="mydb",
        catalog=None,
        schema="public",
        kind="table",
        name="users",
        parent=None,
    )


def _mock_get_definition(factory_result):
    """创建 mock get_definition service。"""
    def _service(*, datasource_id, object_ref):
        return factory_result
    return _service


class TestLineageAnalyzer:
    def test_analyze_no_service(self):
        analyzer = LineageAnalyzer()
        impacts, unknown_reasons = analyzer.analyze(
            datasource_id=101,
            object_ref=_make_ref(),
            source_version="etag-abc123",
        )
        assert impacts == []
        assert len(unknown_reasons) > 0

    def test_analyze_no_definition(self):
        service = _mock_get_definition(None)
        analyzer = LineageAnalyzer(get_definition_service=service)
        impacts, unknown_reasons = analyzer.analyze(
            datasource_id=101,
            object_ref=_make_ref(),
            source_version="etag-abc123",
        )
        assert impacts == []
        assert len(unknown_reasons) > 0

    def test_analyze_empty_definition(self):
        service = _mock_get_definition({"definitionText": ""})
        analyzer = LineageAnalyzer(get_definition_service=service)
        impacts, unknown_reasons = analyzer.analyze(
            datasource_id=101,
            object_ref=_make_ref(),
            source_version="etag-abc123",
        )
        assert impacts == []
        assert len(unknown_reasons) > 0

    def test_analyze_foreign_key_dependency(self):
        ddl = "CREATE TABLE orders (id INT, user_id INT, FOREIGN KEY (user_id) REFERENCES users(id));"
        service = _mock_get_definition({"definitionText": ddl})
        analyzer = LineageAnalyzer(get_definition_service=service)
        ref = ObjectRef(
            datasource_id=101,
            database="mydb",
            catalog=None,
            schema="public",
            kind="table",
            name="orders",
            parent=None,
        )
        impacts, unknown_reasons = analyzer.analyze(
            datasource_id=101,
            object_ref=ref,
            source_version="etag-abc123",
        )
        assert len(impacts) == 1
        assert impacts[0].relation_type == "dependent"
        assert impacts[0].object_ref.name == "users"

    def test_analyze_view_dependency(self):
        ddl = "CREATE VIEW user_view AS SELECT id, name FROM users WHERE active = 1;"
        service = _mock_get_definition({"definitionText": ddl})
        analyzer = LineageAnalyzer(get_definition_service=service)
        ref = ObjectRef(
            datasource_id=101,
            database="mydb",
            catalog=None,
            schema="public",
            kind="view",
            name="user_view",
            parent=None,
        )
        impacts, unknown_reasons = analyzer.analyze(
            datasource_id=101,
            object_ref=ref,
            source_version="etag-abc123",
        )
        assert len(impacts) == 1
        assert impacts[0].relation_type == "downstream"
        assert impacts[0].object_ref.name == "users"

    def test_analyze_multiple_dependencies(self):
        ddl = (
            "CREATE VIEW user_orders AS "
            "SELECT u.id, o.total "
            "FROM users u "
            "JOIN orders o ON u.id = o.user_id;"
        )
        service = _mock_get_definition({"definitionText": ddl})
        analyzer = LineageAnalyzer(get_definition_service=service)
        ref = ObjectRef(
            datasource_id=101,
            database="mydb",
            catalog=None,
            schema="public",
            kind="view",
            name="user_orders",
            parent=None,
        )
        impacts, unknown_reasons = analyzer.analyze(
            datasource_id=101,
            object_ref=ref,
            source_version="etag-abc123",
        )
        assert len(impacts) == 2
        names = {imp.object_ref.name for imp in impacts}
        assert names == {"users", "orders"}

    def test_analyze_self_reference_skipped(self):
        ddl = "CREATE TABLE users (id INT, parent_id INT REFERENCES users(id));"
        service = _mock_get_definition({"definitionText": ddl})
        analyzer = LineageAnalyzer(get_definition_service=service)
        impacts, unknown_reasons = analyzer.analyze(
            datasource_id=101,
            object_ref=_make_ref(),
            source_version="etag-abc123",
        )
        # Self-reference should be skipped
        assert len(impacts) == 0

    def test_analyze_schema_qualified_reference(self):
        ddl = "CREATE TABLE orders (id INT, FOREIGN KEY (user_id) REFERENCES analytics.users(id));"
        service = _mock_get_definition({"definitionText": ddl})
        analyzer = LineageAnalyzer(get_definition_service=service)
        ref = ObjectRef(
            datasource_id=101,
            database="mydb",
            catalog=None,
            schema="public",
            kind="table",
            name="orders",
            parent=None,
        )
        impacts, unknown_reasons = analyzer.analyze(
            datasource_id=101,
            object_ref=ref,
            source_version="etag-abc123",
        )
        assert len(impacts) == 1
        assert impacts[0].object_ref.schema == "analytics"
        assert impacts[0].object_ref.name == "users"
