"""Deterministic, isolated ecommerce facts for Datara capability verification.

This generator writes one JSON artifact. It does not connect to a live database,
create users, reset passwords, or mutate the existing project 33 baseline.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


NAMESPACE = "ECOM_SIM_20261030"


def build_fixture() -> dict:
    orders = [
        {"id": "O001", "buyer": "U001", "sku": "SKU-A", "qty": 2, "unit_cents": 5000, "biz_date": "2026-10-20", "channel": "campaign"},
        {"id": "O002", "buyer": "U001", "sku": "SKU-B", "qty": 2, "unit_cents": 3000, "biz_date": "2026-10-21", "channel": "organic"},
        {"id": "O003", "buyer": "U002", "sku": "SKU-A", "qty": 1, "unit_cents": 5000, "biz_date": "2026-10-21", "channel": "campaign"},
        {"id": "O004", "buyer": "U003", "sku": "SKU-C", "qty": 2, "unit_cents": 6000, "biz_date": "2026-10-22", "channel": "campaign"},
        {"id": "O005", "buyer": "U004", "sku": "SKU-B", "qty": 1, "unit_cents": 3000, "biz_date": "2026-10-22", "channel": "organic"},
        {"id": "O006", "buyer": "U005", "sku": "SKU-D", "qty": 1, "unit_cents": 8000, "biz_date": "2026-10-23", "channel": "organic"},
    ]
    payments = [
        {"id": "P001", "order": "O001", "attempt": 1, "status": "succeeded", "amount_cents": 10000},
        {"id": "P002", "order": "O002", "attempt": 1, "status": "failed", "amount_cents": 6000},
        {"id": "P003", "order": "O002", "attempt": 2, "status": "succeeded", "amount_cents": 6000},
        {"id": "P004", "order": "O003", "attempt": 1, "status": "processing", "amount_cents": 5000},
        {"id": "P005", "order": "O004", "attempt": 1, "status": "succeeded", "amount_cents": 12000},
        {"id": "P006", "order": "O005", "attempt": 1, "status": "canceled", "amount_cents": 3000},
        {"id": "P007", "order": "O006", "attempt": 1, "status": "succeeded", "amount_cents": 8000},
    ]
    fulfillments = [
        {"id": "F001", "order": "O001", "sku": "SKU-A", "qty": 2, "warehouse": "WH-EAST", "status": "delivered"},
        {"id": "F002", "order": "O002", "sku": "SKU-B", "qty": 1, "warehouse": "WH-WEST", "status": "shipped"},
        {"id": "F003", "order": "O004", "sku": "SKU-C", "qty": 2, "warehouse": "WH-EAST", "status": "delivered"},
        {"id": "F004", "order": "O006", "sku": "SKU-D", "qty": 1, "warehouse": "WH-WEST", "status": "delivered"},
    ]
    refunds = [
        {"id": "R001", "order": "O004", "payment": "P005", "sku": "SKU-C", "qty": 1, "status": "succeeded", "amount_cents": 6000},
        {"id": "R002", "order": "O006", "payment": "P007", "sku": "SKU-D", "qty": 1, "status": "pending", "amount_cents": 1000},
    ]
    inventory = [
        {"sku": "SKU-A", "warehouse": "WH-EAST", "on_hand": 20, "reserved": 2, "damaged": 1, "available": 17},
        {"sku": "SKU-B", "warehouse": "WH-WEST", "on_hand": 8, "reserved": 2, "damaged": 0, "available": 6},
        {"sku": "SKU-C", "warehouse": "WH-EAST", "on_hand": 10, "reserved": 2, "damaged": 0, "available": 8},
        {"sku": "SKU-D", "warehouse": "WH-WEST", "on_hand": 3, "reserved": 1, "damaged": 0, "available": 2},
    ]
    events = [
        {"id": "E001", "name": "view_promotion", "buyer": "U001", "promotion": "PROMO-A", "order": None},
        {"id": "E002", "name": "view_item", "buyer": "U001", "promotion": "PROMO-A", "order": None},
        {"id": "E003", "name": "add_to_cart", "buyer": "U001", "promotion": "PROMO-A", "order": None},
        {"id": "E004", "name": "purchase", "buyer": "U001", "promotion": "PROMO-A", "order": "O001"},
        {"id": "E005", "name": "view_promotion", "buyer": "U002", "promotion": "PROMO-A", "order": None},
        {"id": "E006", "name": "begin_checkout", "buyer": "U002", "promotion": "PROMO-A", "order": "O003"},
        {"id": "E007", "name": "refund", "buyer": "U003", "promotion": "PROMO-B", "order": "O004"},
    ]
    anomalies = [
        {"id": "X001", "rule": "order_duplicate", "reference": "O001", "expected": "duplicate business key"},
        {"id": "X002", "rule": "orphan_order_item", "reference": "O999", "expected": "missing order"},
        {"id": "X003", "rule": "refund_exceeds_paid", "reference": "O004", "expected": "refund > succeeded payment"},
        {"id": "X004", "rule": "inventory_negative", "reference": "SKU-B@WH-WEST", "expected": "available < 0"},
    ]
    fixture = {
        "namespace": NAMESPACE,
        "currency": "CNY",
        "synthetic": True,
        "orders": orders,
        "payments": payments,
        "fulfillments": fulfillments,
        "refunds": refunds,
        "inventory": inventory,
        "events": events,
        "anomalies_not_loaded_into_valid_facts": anomalies,
    }
    fixture["expected"] = summarize(fixture)
    validate(fixture)
    return fixture


def summarize(fixture: dict) -> dict:
    paid_orders = {p["order"] for p in fixture["payments"] if p["status"] == "succeeded"}
    paid = [o for o in fixture["orders"] if o["id"] in paid_orders]
    paid_by_buyer = Counter(o["buyer"] for o in paid)
    gross = sum(p["amount_cents"] for p in fixture["payments"] if p["status"] == "succeeded")
    refunds = sum(r["amount_cents"] for r in fixture["refunds"] if r["status"] == "succeeded")
    return {
        "paid_orders": len(paid_orders),
        "gross_paid_cents": gross,
        "successful_refund_cents": refunds,
        "net_paid_cents": gross - refunds,
        "repeat_buyers": sorted(buyer for buyer, count in paid_by_buyer.items() if count >= 2),
        "partial_fulfillment_orders": sorted(o["id"] for o in paid if 0 < sum(f["qty"] for f in fixture["fulfillments"] if f["order"] == o["id"]) < o["qty"]),
        "quality_anomaly_ids": [row["id"] for row in fixture["anomalies_not_loaded_into_valid_facts"]],
    }


def validate(fixture: dict) -> None:
    orders = {row["id"]: row for row in fixture["orders"]}
    payments = {row["id"]: row for row in fixture["payments"]}
    assert len(orders) == len(fixture["orders"])
    assert len(payments) == len(fixture["payments"])
    for payment in fixture["payments"]:
        assert payment["order"] in orders
        assert payment["amount_cents"] > 0
    for refund in fixture["refunds"]:
        assert refund["order"] in orders
        assert payments[refund["payment"]]["order"] == refund["order"]
        assert refund["qty"] <= orders[refund["order"]]["qty"]
    for row in fixture["inventory"]:
        assert row["on_hand"] == row["available"] + row["reserved"] + row["damaged"]
    assert fixture["expected"] == summarize(fixture)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Write one namespaced JSON fixture")
    args = parser.parse_args()
    fixture = build_fixture()
    payload = json.dumps(fixture, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        if args.output.name != f"{NAMESPACE}.json":
            parser.error(f"output file must be named {NAMESPACE}.json")
        if args.output.exists():
            parser.error("output already exists; remove it explicitly after checking its contents")
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")


if __name__ == "__main__":
    main()
