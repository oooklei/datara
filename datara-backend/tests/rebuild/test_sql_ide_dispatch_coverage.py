"""Keep the SQL IDE route contract and application dispatch in lockstep."""

import ast
from pathlib import Path

from rebuild.sql_ide.routes import _ROUTE_SPECS


APP = Path(__file__).resolve().parents[2] / "rebuild" / "api" / "app.py"


def test_every_sql_ide_operation_has_a_dispatch_branch() -> None:
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    dispatch = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "sql_ide_dispatch"
    )
    operations: set[str] = set()
    for node in ast.walk(dispatch):
        if isinstance(node, ast.Compare) and isinstance(node.left, ast.Name) and node.left.id == "operation":
            for comparator in node.comparators:
                if isinstance(comparator, ast.Constant) and isinstance(comparator.value, str):
                    operations.add(comparator.value)
                elif isinstance(comparator, ast.Set):
                    operations.update(
                        item.value for item in comparator.elts
                        if isinstance(item, ast.Constant) and isinstance(item.value, str)
                    )
    declared = {spec[2] for spec in _ROUTE_SPECS}
    assert declared <= operations

