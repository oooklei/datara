import pytest

from rebuild.sql_ide.variables import SqlIdeVariableResolver, VariableResolutionError


class MappingResolver:
    def __init__(self, values):
        self.values = values

    def resolve_name(self, scope, name, context):
        return self.values.get(f"{scope}.{name}")


def test_resolve_replaces_scoped_variables_and_returns_digests():
    resolver = SqlIdeVariableResolver(
        MappingResolver({"project.table_name": "orders", "global.limit": "20"})
    )

    result = resolver.resolve(
        sql="select * from ${project.table_name} limit ${global.limit}",
        project_id=7,
        datasource_id=3,
    )

    assert result["resolved_sql"] == "select * from orders limit 20"
    assert result["snapshot_ref"].startswith("sha256:")
    assert len(result["digest"]) == 64


def test_resolve_recursively_expands_variable_values():
    resolver = SqlIdeVariableResolver(
        MappingResolver(
            {
                "project.table_name": "${global.table_prefix}_orders",
                "global.table_prefix": "sales",
            }
        )
    )

    result = resolver.resolve(sql="select * from ${project.table_name}", project_id=7, datasource_id=3)

    assert result["resolved_sql"] == "select * from sales_orders"


@pytest.mark.parametrize(
    "sql",
    ["select ${project.missing}", "select ${project.open", "select ${unscoped}"],
)
def test_missing_or_unclosed_variable_fails_closed(sql):
    resolver = SqlIdeVariableResolver(MappingResolver({}))

    with pytest.raises(VariableResolutionError):
        resolver.resolve(sql=sql, project_id=7, datasource_id=3)


def test_cyclic_variable_expansion_fails_closed():
    resolver = SqlIdeVariableResolver(
        MappingResolver(
            {
                "project.first": "${project.second}",
                "project.second": "${project.first}",
            }
        )
    )

    with pytest.raises(VariableResolutionError, match="cycle"):
        resolver.resolve(sql="select ${project.first}", project_id=7, datasource_id=3)
