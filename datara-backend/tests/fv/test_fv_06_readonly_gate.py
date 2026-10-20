"""FV-06 R5-A 只读态边界与门禁终验。

验收标准（草案）：
- 真实只读 DB 权限为第一道门、AST/dialect 只读分类为第二道门
- 写操作与无法安全分类语句 fail-closed 整批拒绝
- 错误映射稳定域码，不泄漏 driver 原文/连接串/密钥

测试策略：全部 mock/内存，禁真实写库。
"""

from __future__ import annotations

import pytest

from rebuild.sql_ide.error_catalog import build_error_envelope, http_status_for
from rebuild.sql_ide.errors import map_connection_error, map_driver_error
from rebuild.sql_ide.readonly_preflight import (
    ReadonlyBatchPreflightError,
    ReadonlyStatement,
    preflight_readonly_batch,
)


class TestReadonlyBatchPreflight:
    """preflight_readonly_batch 只读分类门禁。"""

    def test_simple_select_approved(self):
        statements = preflight_readonly_batch("SELECT 1", dialect="mysql")
        assert len(statements) == 1
        assert isinstance(statements[0], ReadonlyStatement)
        assert statements[0].index == 0
        assert "SELECT" in statements[0].sql.upper()

    def test_union_select_approved(self):
        statements = preflight_readonly_batch("SELECT 1 UNION SELECT 2", dialect="mysql")
        assert len(statements) == 1

    def test_multiple_selects_approved(self):
        statements = preflight_readonly_batch("SELECT 1; SELECT 2", dialect="mysql")
        assert len(statements) == 2
        assert [s.index for s in statements] == [0, 1]

    def test_insert_rejected(self):
        with pytest.raises(ReadonlyBatchPreflightError):
            preflight_readonly_batch("INSERT INTO t VALUES (1)", dialect="mysql")

    def test_update_rejected(self):
        with pytest.raises(ReadonlyBatchPreflightError):
            preflight_readonly_batch("UPDATE t SET x=1", dialect="mysql")

    def test_delete_rejected(self):
        with pytest.raises(ReadonlyBatchPreflightError):
            preflight_readonly_batch("DELETE FROM t", dialect="mysql")

    def test_create_table_rejected(self):
        with pytest.raises(ReadonlyBatchPreflightError):
            preflight_readonly_batch("CREATE TABLE t (id INT)", dialect="mysql")

    def test_drop_table_rejected(self):
        with pytest.raises(ReadonlyBatchPreflightError):
            preflight_readonly_batch("DROP TABLE t", dialect="mysql")

    def test_alter_table_rejected(self):
        with pytest.raises(ReadonlyBatchPreflightError):
            preflight_readonly_batch("ALTER TABLE t ADD COLUMN c INT", dialect="mysql")

    def test_truncate_rejected(self):
        with pytest.raises(ReadonlyBatchPreflightError):
            preflight_readonly_batch("TRUNCATE TABLE t", dialect="mysql")

    def test_mixed_batch_rejected(self):
        """写操作混入 SELECT 批次 → 整批拒绝。"""
        with pytest.raises(ReadonlyBatchPreflightError):
            preflight_readonly_batch("SELECT 1; INSERT INTO t VALUES (1)", dialect="mysql")

    def test_select_into_rejected(self):
        with pytest.raises(ReadonlyBatchPreflightError):
            preflight_readonly_batch("SELECT * INTO new_table FROM t", dialect="mysql")

    def test_select_for_update_rejected(self):
        with pytest.raises(ReadonlyBatchPreflightError):
            preflight_readonly_batch("SELECT * FROM t FOR UPDATE", dialect="mysql")

    def test_unknown_function_rejected(self):
        """未知函数无法证明无副作用 → 拒绝。"""
        with pytest.raises(ReadonlyBatchPreflightError):
            preflight_readonly_batch("SELECT unknown_func(x) FROM t", dialect="mysql")

    def test_safe_function_approved(self):
        """白名单安全函数通过。"""
        statements = preflight_readonly_batch("SELECT COUNT(*), MAX(id) FROM t", dialect="mysql")
        assert len(statements) == 1

    def test_empty_sql_rejected(self):
        with pytest.raises(ReadonlyBatchPreflightError):
            preflight_readonly_batch("", dialect="mysql")

    def test_whitespace_sql_rejected(self):
        with pytest.raises(ReadonlyBatchPreflightError):
            preflight_readonly_batch("   ", dialect="mysql")

    def test_empty_dialect_rejected(self):
        with pytest.raises(ReadonlyBatchPreflightError):
            preflight_readonly_batch("SELECT 1", dialect="")

    def test_none_sql_rejected(self):
        with pytest.raises(ReadonlyBatchPreflightError):
            preflight_readonly_batch(None, dialect="mysql")

    def test_none_dialect_rejected(self):
        with pytest.raises(ReadonlyBatchPreflightError):
            preflight_readonly_batch("SELECT 1", dialect=None)

    def test_unsupported_dialect_rejected(self):
        # sqlglot 不支持的方言 → 解析失败 → 拒绝
        with pytest.raises(ReadonlyBatchPreflightError):
            preflight_readonly_batch("SELECT 1", dialect="hive_warehouse_special")

    def test_postgresql_dialect_approved(self):
        statements = preflight_readonly_batch("SELECT 1", dialect="postgresql")
        assert len(statements) == 1

    def test_postgresql_alias(self):
        statements = preflight_readonly_batch("SELECT 1", dialect="postgres")
        assert len(statements) == 1

    def test_sqlite_dialect_approved(self):
        statements = preflight_readonly_batch("SELECT 1", dialect="sqlite")
        assert len(statements) == 1

    def test_parse_error_rejected(self):
        """语法错误 → fail-closed 拒绝。"""
        with pytest.raises(ReadonlyBatchPreflightError):
            preflight_readonly_batch("SELECT FROM WHERE", dialect="mysql")

    def test_subquery_with_safe_functions(self):
        statements = preflight_readonly_batch(
            "SELECT COALESCE(MAX(id), 0) FROM t WHERE id IN (SELECT id FROM s)",
            dialect="mysql",
        )
        assert len(statements) == 1


class TestErrorMapping:
    """错误映射稳定域码，不泄漏 driver 原文/连接串/密钥。"""

    def test_connection_error_hides_details(self):
        original = RuntimeError("Connection refused to 192.168.1.9:3310 with password secret123")
        mapped = map_connection_error(original)
        assert mapped.details["errorCode"] == "DATASOURCE_UNAVAILABLE"
        # 不泄漏原始消息
        assert "192.168.1.9" not in str(mapped)
        assert "secret123" not in str(mapped)
        assert "Connection refused" not in str(mapped)

    def test_driver_error_hides_details(self):
        original = Exception("MySQL Error 1064: syntax error near 'SELCT'")
        mapped = map_driver_error(original)
        assert mapped.details["errorCode"] == "DRIVER_ERROR"
        assert "1064" not in str(mapped)
        assert "SELCT" not in str(mapped)

    def test_timeout_error_mapped(self):
        original = TimeoutError("connection timed out after 30s")
        mapped = map_driver_error(original)
        assert mapped.details["errorCode"] == "EXECUTION_TIMEOUT"
        assert "30s" not in str(mapped)


class TestErrorCatalog:
    """稳定域错误码与 HTTP 映射。"""

    def test_known_error_codes(self):
        assert http_status_for("INVALID_REQUEST") == 400
        assert http_status_for("UNAUTHENTICATED") == 401
        assert http_status_for("PERMISSION_DENIED") == 403
        assert http_status_for("RESOURCE_NOT_FOUND") == 404
        assert http_status_for("POLICY_BLOCKED") == 409
        assert http_status_for("IDEMPOTENCY_CONFLICT") == 409
        assert http_status_for("RESULT_EXPIRED") == 410
        assert http_status_for("CAPABILITY_CONDITION_NOT_MET") == 422
        assert http_status_for("RATE_LIMITED") == 429
        assert http_status_for("DATASOURCE_UNAVAILABLE") == 502
        assert http_status_for("DRIVER_ERROR") == 502
        assert http_status_for("EXECUTION_TIMEOUT") == 504

    def test_unknown_error_code_raises(self):
        with pytest.raises(ValueError, match="unknown SQL IDE error code"):
            http_status_for("TOTALLY_UNKNOWN_CODE")

    def test_build_error_envelope(self):
        envelope = build_error_envelope("POLICY_BLOCKED")
        assert envelope["code"] == 409
        assert envelope["data"]["errorCode"] == "POLICY_BLOCKED"

    def test_build_error_envelope_with_details(self):
        envelope = build_error_envelope("DRIVER_ERROR", details={"key": "value"})
        assert envelope["data"]["details"] == {"key": "value"}

    def test_build_error_envelope_unknown_raises(self):
        with pytest.raises(ValueError):
            build_error_envelope("NONEXISTENT")
