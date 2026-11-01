"""Render isolated MySQL 8 import and cleanup SQL for the ecommerce fixture.

The default command prints a read-only manifest. SQL rendering has no network
access; applying it is a separate 1.9 deployment step after baseline inventory.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ecommerce_core_simulation import NAMESPACE, build_fixture


SCHEMA = "ecom_sim_20261030"
FACT_TYPES = (
    "products", "campaigns", "orders", "payments", "payment_status_events",
    "fulfillments", "tracking_events", "refunds", "return_lines",
    "refund_status_events", "inventory", "inventory_movements", "events", "quality_anomalies",
)
FIXTURE = Path(__file__).with_name(f"{NAMESPACE}.json")


def load_fixture() -> dict[str, Any]:
    artifact = json.loads(FIXTURE.read_text(encoding="utf-8"))
    if artifact != build_fixture() or artifact.get("namespace") != NAMESPACE:
        raise ValueError("fixture artifact does not match the deterministic generator")
    return artifact


def fact_key(kind: str, row: dict[str, Any]) -> str:
    return f"{row['sku']}@{row['warehouse']}" if kind == "inventory" else str(row.get("id", row.get("sku")))


def literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if not isinstance(value, str):
        raise TypeError(f"unsupported fixture value: {type(value).__name__}")
    return f"CONVERT(0x{value.encode('utf-8').hex()} USING utf8mb4)"


def column_type(values: list[Any], name: str) -> str:
    if name == "biz_date":
        return "DATE"
    if name == "event_time":
        return "VARCHAR(35)"
    if all(value is None or isinstance(value, (dict, list)) for value in values):
        return "JSON"
    if all(value is None or isinstance(value, (bool, int)) for value in values):
        return "BIGINT"
    return "VARCHAR(255)"


def render_import(fixture: dict[str, Any]) -> str:
    if fixture.get("namespace") != NAMESPACE:
        raise ValueError("unexpected fixture namespace")
    statements = [
        "-- Isolated synthetic facts; no external payment or carrier receipt is asserted.",
        f"CREATE DATABASE IF NOT EXISTS `{SCHEMA}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;",
        f"USE `{SCHEMA}`;",
    ]
    for kind in FACT_TYPES:
        rows = fixture[kind]
        if not rows:
            raise ValueError(f"empty fixture fact type: {kind}")
        keys = [fact_key(kind, row) for row in rows]
        if len(keys) != len(set(keys)) or any(not key or key == "None" for key in keys):
            raise ValueError(f"duplicate or missing fact key in {kind}")
        columns = sorted(set().union(*(row.keys() for row in rows)))
        if any(row.get("fixture_namespace") != NAMESPACE for row in rows):
            raise ValueError(f"out-of-namespace row in {kind}")
        definitions = ["  `fact_key` VARCHAR(255) NOT NULL"]
        for name in columns:
            values = [row.get(name) for row in rows]
            nullable = " NOT NULL" if name in ("fixture_namespace", "event_time", "biz_date") else ""
            definitions.append(f"  `{name}` {column_type(values, name)}{nullable}")
        definitions.append("  PRIMARY KEY (`fixture_namespace`, `fact_key`)")
        definitions.append("  KEY `idx_biz_date` (`biz_date`)")
        statements.append(f"CREATE TABLE IF NOT EXISTS `{kind}` (\n" + ",\n".join(definitions) + "\n) ENGINE=InnoDB;")
        names = ["fact_key", *columns]
        quoted = ", ".join(f"`{name}`" for name in names)
        updates = ", ".join(f"`{name}`=VALUES(`{name}`)" for name in columns if name != "fixture_namespace")
        for row, key in zip(rows, keys):
            values = ", ".join(literal(value) for value in [key, *(row.get(name) for name in columns)])
            statements.append(f"INSERT INTO `{kind}` ({quoted}) VALUES ({values}) ON DUPLICATE KEY UPDATE {updates};")
    return "\n".join(statements) + "\n"


def render_cleanup() -> str:
    namespace = literal(NAMESPACE)
    return "\n".join(
        [f"USE `{SCHEMA}`;", *(f"DELETE FROM `{kind}` WHERE `fixture_namespace` = {namespace};" for kind in reversed(FACT_TYPES))]
    ) + "\n"


def manifest(fixture: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "namespace": NAMESPACE,
        "fact_counts": {kind: len(fixture[kind]) for kind in FACT_TYPES},
        "expected": fixture["expected"],
        "apply_requires": "1.9 isolated workdir, read-only baseline inventory, explicit MySQL target",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--render-import", type=Path)
    parser.add_argument("--render-cleanup", type=Path)
    args = parser.parse_args()
    fixture = load_fixture()
    if not args.render_import and not args.render_cleanup:
        print(json.dumps(manifest(fixture), ensure_ascii=False, indent=2))
        return
    for output, payload in ((args.render_import, render_import(fixture)), (args.render_cleanup, render_cleanup())):
        if output is None:
            continue
        if output.exists():
            parser.error(f"refusing to overwrite existing file: {output}")
        output.write_text(payload, encoding="utf-8")


if __name__ == "__main__":
    main()
