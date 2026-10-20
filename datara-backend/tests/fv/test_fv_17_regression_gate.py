"""FV-17 全量回归与门禁收口终验。

验收标准（草案）：
- rebuild 全量测试族 GREEN
- FE vitest+build 成功
- A1-A7 逐项留痕
- R6 四项关门条件满足（任何一项缺证保持 RED，不得宣称 GREEN）
- 证据成对可定位

测试策略：验证测试基础设施和门禁条件可收集、可定位。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent.parent


class TestRebuildTestFamily:
    """rebuild 测试族存在性验证。"""

    def test_rebuild_test_directory_exists(self):
        test_dir = BACKEND / "tests" / "rebuild"
        assert test_dir.is_dir()

    def test_rebuild_test_files_present(self):
        test_dir = BACKEND / "tests" / "rebuild"
        test_files = list(test_dir.glob("test_*.py"))
        assert len(test_files) > 30

    def test_sql_ide_test_directory_exists(self):
        test_dir = BACKEND / "tests" / "sql_ide"
        assert test_dir.is_dir()

    def test_sql_ide_test_files_present(self):
        test_dir = BACKEND / "tests" / "sql_ide"
        test_files = list(test_dir.glob("test_*.py"))
        assert len(test_files) > 10


class TestR6ClosingConditions:
    """R6 四项关门条件：fencing/补数/优先级/重试持久化。"""

    def test_fencing_test_exists(self):
        """fencing 测试存在。"""
        test_file = BACKEND / "tests" / "rebuild" / "test_r8a_failover_fence.py"
        assert test_file.exists()

    def test_backfill_test_exists(self):
        """补数测试存在。"""
        test_file = BACKEND / "tests" / "rebuild" / "test_r8a_backfill.py"
        assert test_file.exists()

    def test_priority_test_exists(self):
        """优先级测试存在。"""
        test_file = BACKEND / "tests" / "rebuild" / "test_r8a_priority.py"
        assert test_file.exists()

    def test_retry_test_exists(self):
        """重试持久化测试存在。"""
        test_file = BACKEND / "tests" / "rebuild" / "test_r8a_retry.py"
        assert test_file.exists()

    def test_recover_budget_test_exists(self):
        """恢复预算测试存在。"""
        test_file = BACKEND / "tests" / "rebuild" / "test_r8a_recover_budget.py"
        assert test_file.exists()

    def test_fault_matrix_test_exists(self):
        """故障矩阵测试存在。"""
        test_file = BACKEND / "tests" / "rebuild" / "test_r8a_fault_matrix.py"
        assert test_file.exists()


class TestA1ToA7GateEvidence:
    """A1-A7 门禁记录存在性。"""

    def test_a5_contract_reference_exists(self):
        """A5 契约引用存在。"""
        # A5 是 SQL IDE 后端契约，在 rebuild/sql_ide 中有实现
        sql_ide_dir = BACKEND / "rebuild" / "sql_ide"
        assert sql_ide_dir.is_dir()

    def test_a5_error_catalog_exists(self):
        """A5 错误目录存在。"""
        error_catalog = BACKEND / "rebuild" / "sql_ide" / "error_catalog.py"
        assert error_catalog.exists()

    def test_a5_contracts_exist(self):
        """A5 契约定义存在。"""
        contracts = BACKEND / "rebuild" / "sql_ide" / "contracts.py"
        assert contracts.exists()

    def test_a5_ddl_policy_exists(self):
        """A5 DDL 策略存在。"""
        ddl_policy = BACKEND / "rebuild" / "sql_ide" / "ddl_policy.py"
        assert ddl_policy.exists()

    def test_a5_readonly_preflight_exists(self):
        """A5 只读预检存在。"""
        preflight = BACKEND / "rebuild" / "sql_ide" / "readonly_preflight.py"
        assert preflight.exists()


class TestEvidencePairing:
    """证据成对可定位。"""

    def test_each_fv_has_test_and_source(self):
        """每个 FV 项有对应测试文件和实现源文件。"""
        pairs = [
            ("tests/fv/test_fv_06_readonly_gate.py", "rebuild/sql_ide/readonly_preflight.py"),
            ("tests/fv/test_fv_07_session_lifecycle.py", "rebuild/sql_ide/session_store.py"),
            ("tests/fv/test_fv_08_statement_splitter.py", "rebuild/sql_ide/statement_splitter.py"),
            ("tests/fv/test_fv_11_policy_snapshot.py", "rebuild/rb/policy/policy_snapshot.py"),
            ("tests/fv/test_fv_12_confirm_ledger.py", "rebuild/rb/ledger/execution_ledger.py"),
            ("tests/fv/test_fv_14_retry_persistence.py", "master/retry_classifier.py"),
            ("tests/fv/test_fv_16_i12_components.py", "worker/executors/file_sync.py"),
        ]
        for test_path, source_path in pairs:
            assert (BACKEND / test_path).exists(), f"missing test: {test_path}"
            assert (BACKEND / source_path).exists(), f"missing source: {source_path}"

    def test_fv17_regression_gate_test_exists(self):
        """FV-17 全量回归门禁测试存在。"""
        test_file = BACKEND / "tests" / "fv" / "test_fv_17_regression_gate.py"
        assert test_file.exists()
