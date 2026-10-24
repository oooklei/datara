from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.wf_variable import _validate_name  # noqa: E402


@pytest.mark.parametrize("name", ["count", "_date", "wf.v1", "source-id"])
def test_variable_name_accepts_resolver_safe_names(name):
    assert _validate_name(name) is None


@pytest.mark.parametrize("name", ["", "  ", "run.instanceId", "tmp.table", "1st", "a/b"])
def test_variable_name_rejects_reserved_or_ambiguous_names(name):
    assert _validate_name(name) is not None
