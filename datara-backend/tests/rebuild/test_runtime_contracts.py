"""VAR-08: seven-level precedence chain tests (design §5).

Verifies that the precedence chain ``run > task > workflow > project > global >
env > builtin`` is correctly enforced: when the same variable name exists in
multiple scopes, the highest-precedence scope wins.
"""

from rebuild.variables.service import (
    PRECEDENCE,
    BUILTIN_VARIABLES,
    ResolvedVariable,
    VariableContext,
    VariableResolver,
)


def _make_resolver(
    definitions: dict[str, list[ResolvedVariable]] | None = None,
    run_values: dict[str, str] | None = None,
) -> VariableResolver:
    definitions = definitions or {}
    return VariableResolver(lambda owner_key: definitions.get(owner_key, []), run_values=run_values)


def test_precedence_chain_order():
    """VAR-08: PRECEDENCE tuple matches the design chain."""
    assert PRECEDENCE == ("run", "task", "workflow", "project", "global", "env", "builtin")


def test_run_overrides_all():
    """VAR-08: run scope overrides task/workflow/project/global."""
    resolver = _make_resolver(
        definitions={
            "global": [ResolvedVariable(name="x", scope="global", value="global", value_type="string")],
            "project:1": [ResolvedVariable(name="x", scope="project", value="project", value_type="string")],
            "workflow:1:100": [ResolvedVariable(name="x", scope="workflow", value="workflow", value_type="string")],
            "task:1:task-001": [ResolvedVariable(name="x", scope="task", value="task", value_type="string")],
        },
        run_values={"x": "run"},
    )
    context = VariableContext(project_id=1, workflow_id=100, task_id="task-001", attempt_no=1)
    assert resolver.resolve_name("run", "x", context) == "run"


def test_task_overrides_workflow_project_global():
    """VAR-08: task scope overrides workflow/project/global."""
    resolver = _make_resolver(
        definitions={
            "global": [ResolvedVariable(name="x", scope="global", value="global", value_type="string")],
            "project:1": [ResolvedVariable(name="x", scope="project", value="project", value_type="string")],
            "workflow:1:100": [ResolvedVariable(name="x", scope="workflow", value="workflow", value_type="string")],
            "task:1:task-001": [ResolvedVariable(name="x", scope="task", value="task", value_type="string")],
        },
    )
    context = VariableContext(project_id=1, workflow_id=100, task_id="task-001")
    # task wins over workflow/project/global
    assert resolver.resolve_name("task", "x", context) == "task"


def test_workflow_overrides_project_global():
    """VAR-08: workflow scope overrides project/global."""
    resolver = _make_resolver(
        definitions={
            "global": [ResolvedVariable(name="x", scope="global", value="global", value_type="string")],
            "project:1": [ResolvedVariable(name="x", scope="project", value="project", value_type="string")],
            "workflow:1:100": [ResolvedVariable(name="x", scope="workflow", value="workflow", value_type="string")],
        },
    )
    context = VariableContext(project_id=1, workflow_id=100)
    assert resolver.resolve_name("workflow", "x", context) == "workflow"


def test_project_overrides_global():
    """VAR-08: project scope overrides global."""
    resolver = _make_resolver(
        definitions={
            "global": [ResolvedVariable(name="x", scope="global", value="global", value_type="string")],
            "project:1": [ResolvedVariable(name="x", scope="project", value="project", value_type="string")],
        },
    )
    context = VariableContext(project_id=1)
    assert resolver.resolve_name("project", "x", context) == "project"


def test_global_overrides_builtin():
    """VAR-08: global scope overrides builtin."""
    resolver = _make_resolver(
        definitions={
            "global": [ResolvedVariable(name="version", scope="global", value="9.9.9", value_type="string")],
        },
    )
    context = VariableContext(project_id=1)
    assert resolver.resolve_name("global", "version", context) == "9.9.9"


def test_builtin_always_visible():
    """VAR-08: builtin variables are always visible."""
    resolver = _make_resolver()
    context = VariableContext(project_id=1)
    for name, value in BUILTIN_VARIABLES.items():
        assert resolver.resolve_name("builtin", name, context) == value


def test_catalog_dedup_first_wins():
    """VAR-08: catalog deduplicates by name, first occurrence (highest precedence) wins."""
    resolver = _make_resolver(
        definitions={
            "global": [ResolvedVariable(name="x", scope="global", value="global", value_type="string")],
            "project:1": [ResolvedVariable(name="x", scope="project", value="project", value_type="string")],
        },
    )
    context = VariableContext(project_id=1)
    catalog = resolver.catalog(context)
    x_items = [item for item in catalog if item.name == "x"]
    assert len(x_items) == 1
    assert x_items[0].value == "project"


def test_catalog_ordering_run_first():
    """VAR-08: catalog places run-scope items first."""
    resolver = _make_resolver(
        definitions={
            "global": [ResolvedVariable(name="g", scope="global", value="gv", value_type="string")],
        },
        run_values={"r": "rv"},
    )
    context = VariableContext(project_id=1, task_id="t1", attempt_no=1)
    catalog = resolver.catalog(context)
    names = [item.name for item in catalog]
    assert names[0] == "r"
    assert "g" in names


def test_visible_scopes_without_workflow_task():
    """VAR-08: workflow/task scopes are hidden when ids are absent."""
    resolver = _make_resolver()
    context = VariableContext(project_id=1)
    visible = resolver.visible_scopes(context)
    assert "workflow" not in visible
    assert "task" not in visible
    assert "run" in visible
    assert "project" in visible
    assert "global" in visible
    assert "env" in visible
    assert "builtin" in visible


def test_visible_scopes_with_workflow_task():
    """VAR-08: workflow/task scopes are visible when ids are present."""
    resolver = _make_resolver()
    context = VariableContext(project_id=1, workflow_id=100, task_id="task-001")
    visible = resolver.visible_scopes(context)
    assert "workflow" in visible
    assert "task" in visible


def test_seven_levels_all_resolve():
    """VAR-08: all seven levels resolve in a fully-populated context."""
    resolver = _make_resolver(
        definitions={
            "global": [ResolvedVariable(name="v", scope="global", value="global", value_type="string")],
            "project:1": [ResolvedVariable(name="v", scope="project", value="project", value_type="string")],
            "workflow:1:100": [ResolvedVariable(name="v", scope="workflow", value="workflow", value_type="string")],
            "task:1:task-001": [ResolvedVariable(name="v", scope="task", value="task", value_type="string")],
        },
        run_values={"v": "run"},
    )
    context = VariableContext(project_id=1, workflow_id=100, task_id="task-001", attempt_no=1)
    # Each scope resolves its own value
    assert resolver.resolve_name("run", "v", context) == "run"
    assert resolver.resolve_name("task", "v", context) == "task"
    assert resolver.resolve_name("workflow", "v", context) == "workflow"
    assert resolver.resolve_name("project", "v", context) == "project"
    assert resolver.resolve_name("global", "v", context) == "global"
    assert resolver.resolve_name("builtin", "version", context) == "0.1.0"
