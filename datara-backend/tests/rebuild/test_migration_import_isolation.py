import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("module_name", [
    "rebuild.component_spec.migrations",
    "rebuild.execution.migrations",
    "rebuild.identity.migrations",
    "rebuild.llm.migrations",
    "rebuild.metrics.migrations",
    "rebuild.runtime_node.migrations",
    "rebuild.sec.migrations",
    "rebuild.sshnode.migrations",
    "rebuild.stream.migrations",
    "rebuild.variables.migrations",
    "rebuild.workflow.migrations",
])
def test_importing_domain_migrations_does_not_register_governance_tables(module_name):
    script = f"""
from rebuild.common.db import Base
import {module_name}
tables = set(Base.metadata.tables)
assert 'rebuild_schema_migration' in tables
assert 'rebuild_governance_asset' not in tables
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
        cwd=Path(__file__).resolve().parents[2],
    )
    assert completed.returncode == 0, completed.stderr
