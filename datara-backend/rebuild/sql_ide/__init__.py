"""Pure-local SQL IDE planning helpers.

This package currently contains preview-only DDL policy and plan construction.
It has no datasource adapter and exposes no DDL execution path.
"""

from .ddl_diff import DdlDefinitionDiff, build_definition_diff
from .ddl_plan import DdlPlanInput, DdlPlanPreview, build_ddl_plan_preview
from .ddl_policy import DdlFinding, DdlPolicyResult, evaluate_ddl_policy

__all__ = [
    "DdlFinding",
    "DdlDefinitionDiff",
    "DdlPlanInput",
    "DdlPlanPreview",
    "DdlPolicyResult",
    "build_ddl_plan_preview",
    "build_definition_diff",
    "evaluate_ddl_policy",
]
