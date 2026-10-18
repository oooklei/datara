"""TDD 测试：rb 包骨架冒烟测试。

IMPL-B2 新增：验证 8 子包 + migrations.py 结构完整。
"""
from __future__ import annotations

import importlib

import pytest


class TestRbPackageSkeleton:
    """验证 rb 包 8 子包结构完整。"""

    def test_rb_package_exists(self):
        import rebuild.rb
        assert rebuild.rb is not None

    def test_facade_subpackage(self):
        mod = importlib.import_module("rebuild.rb.facade")
        assert mod is not None

    def test_policy_subpackage(self):
        mod = importlib.import_module("rebuild.rb.policy")
        assert mod is not None

    def test_impact_subpackage(self):
        mod = importlib.import_module("rebuild.rb.impact")
        assert mod is not None

    def test_executor_subpackage(self):
        mod = importlib.import_module("rebuild.rb.executor")
        assert mod is not None

    def test_ledger_subpackage(self):
        mod = importlib.import_module("rebuild.rb.ledger")
        assert mod is not None

    def test_models_subpackage(self):
        mod = importlib.import_module("rebuild.rb.models")
        assert mod is not None

    def test_errors_subpackage(self):
        mod = importlib.import_module("rebuild.rb.errors")
        assert mod is not None

    def test_migrations_module(self):
        mod = importlib.import_module("rebuild.rb.migrations")
        assert mod is not None

    def test_eight_subpackages_no_more(self):
        """验证 7 子包 + migrations.py 模块，无第 8 子包。"""
        import os
        import rebuild.rb
        rb_dir = os.path.dirname(rebuild.rb.__file__)
        subdirs = [d for d in os.listdir(rb_dir) if os.path.isdir(os.path.join(rb_dir, d)) and not d.startswith("_")]
        assert len(subdirs) == 7
        assert "facade" in subdirs
        assert "policy" in subdirs
        assert "impact" in subdirs
        assert "executor" in subdirs
        assert "ledger" in subdirs
        assert "models" in subdirs
        assert "errors" in subdirs
        assert "migrations" not in subdirs  # migrations 是 .py 不是子包
        assert os.path.isfile(os.path.join(rb_dir, "migrations.py"))
