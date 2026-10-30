"""Deterministic SQL plans for isolated ecommerce facts; no database is touched."""

import pytest

import render_ecommerce_sim_sql as importer


def test_import_plan_covers_every_fact_and_only_uses_isolated_schema():
    fixture = importer.load_fixture()
    sql = importer.render_import(fixture)
    assert f"CREATE DATABASE IF NOT EXISTS `{importer.SCHEMA}`" in sql
    assert "DROP " not in sql and "TRUNCATE " not in sql
    for kind in importer.FACT_TYPES:
        assert f"CREATE TABLE IF NOT EXISTS `{kind}`" in sql
        assert sql.count(f"INSERT INTO `{kind}` ") == len(fixture[kind])
    assert "PRIMARY KEY (`fixture_namespace`, `fact_key`)" in sql
    assert "SYNTHETIC-CARRIER" not in sql  # Values are UTF-8 hex literals, not loose SQL text.


def test_cleanup_is_confined_to_exact_namespace_and_never_drops_tables():
    sql = importer.render_cleanup()
    assert sql.count("DELETE FROM") == len(importer.FACT_TYPES)
    assert "WHERE `fixture_namespace` =" in sql
    assert "DROP " not in sql and "TRUNCATE " not in sql


def test_import_rejects_unowned_or_duplicate_facts_before_rendering():
    fixture = importer.load_fixture()
    fixture["orders"][0]["fixture_namespace"] = "another"
    with pytest.raises(ValueError, match="out-of-namespace"):
        importer.render_import(fixture)
    fixture = importer.load_fixture()
    fixture["orders"].append(fixture["orders"][0].copy())
    with pytest.raises(ValueError, match="duplicate"):
        importer.render_import(fixture)
