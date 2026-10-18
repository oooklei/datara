"""TDD 测试：rb_errors.py（§5.1 RbErrorCode 枚举）。

RED 先行：先写测试确认错误码存在且唯一，再验证 GREEN。
"""
from __future__ import annotations

from rebuild.rb.errors.rb_errors import RbErrorCode


class TestRbErrorCode:
    """验证 12 个稳定域错误码存在且值唯一。"""

    EXPECTED_CODES = {
        "POLICY_BLOCKED",
        "SOURCE_VERSION_CONFLICT",
        "SNAPSHOT_EXPIRED",
        "SNAPSHOT_MISMATCH",
        "CONFIRM_PHRASE_INVALID",
        "CONFIRM_PHRASE_MISMATCH",
        "DDL_EXECUTION_FAILED",
        "ROLLBACK_FAILED",
        "LINEAGE_UNKNOWN",
        "LINEAGE_UNSUPPORTED",
        "WRITE_PERMISSION_DENIED",
        "OBJECT_AMBIGUOUS",
        "OBJECT_NOT_VISIBLE",
        "CAPABILITY_CONDITION_NOT_MET",
        "CAPABILITY_UNSUPPORTED",
        "CAPABILITY_UNKNOWN",
    }

    def test_all_codes_exist(self):
        """所有预期错误码都存在于 RbErrorCode 类。"""
        for code_name in self.EXPECTED_CODES:
            assert hasattr(RbErrorCode, code_name), f"Missing: {code_name}"

    def test_code_values_match_names(self):
        """错误码的值与名称一致（稳定域错误枚举约定）。"""
        for code_name in self.EXPECTED_CODES:
            value = getattr(RbErrorCode, code_name)
            assert value == code_name, f"{code_name} value mismatch: {value}"

    def test_codes_are_unique(self):
        """所有错误码值唯一。"""
        values = [getattr(RbErrorCode, name) for name in self.EXPECTED_CODES]
        assert len(values) == len(set(values)), "Duplicate error codes found"

    def test_code_format(self):
        """错误码格式为 UPPER_SNAKE_CASE。"""
        for code_name in self.EXPECTED_CODES:
            value = getattr(RbErrorCode, code_name)
            assert value == value.upper(), f"{code_name} not uppercase"
            assert "_" in value or value.isupper(), f"{code_name} not snake_case"

    def test_policy_blocked(self):
        assert RbErrorCode.POLICY_BLOCKED == "POLICY_BLOCKED"

    def test_source_version_conflict(self):
        assert RbErrorCode.SOURCE_VERSION_CONFLICT == "SOURCE_VERSION_CONFLICT"

    def test_ddl_execution_failed(self):
        assert RbErrorCode.DDL_EXECUTION_FAILED == "DDL_EXECUTION_FAILED"

    def test_rollback_failed(self):
        assert RbErrorCode.ROLLBACK_FAILED == "ROLLBACK_FAILED"
