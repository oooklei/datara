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
RUN_ID = "SIM_RUN_20261030_01"
SOURCE_SYSTEM = "datara_synthetic_fixture"


def build_fixture() -> dict:
    products = [
        {"sku": "SKU-A", "product_code": "SIM-PROD-A", "name": "Cotton T-shirt", "specs": {"color": "blue", "size": "M"}},
        {"sku": "SKU-B", "product_code": "SIM-PROD-B", "name": "Cotton T-shirt", "specs": {"color": "black", "size": "L"}},
        {"sku": "SKU-C", "product_code": "SIM-PROD-C", "name": "Travel bag", "specs": {"color": "gray", "size": "standard"}},
        {"sku": "SKU-D", "product_code": "SIM-PROD-D", "name": "Desk lamp", "specs": {"color": "white", "size": "standard"}},
    ]
    campaigns = [
        {"id": "PROMO-A", "name": "Autumn launch", "starts_at": "2026-10-20T00:00:00+08:00", "ends_at": "2026-10-22T23:59:59+08:00"},
        {"id": "PROMO-B", "name": "Member offer", "starts_at": "2026-10-22T00:00:00+08:00", "ends_at": "2026-10-24T23:59:59+08:00"},
    ]
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
        {"sku": "SKU-B", "warehouse": "WH-EAST", "on_hand": 0, "reserved": 0, "damaged": 0, "available": 0},
    ]
    inventory_movements = [
        {"id": "IM001", "sku": "SKU-A", "warehouse": "WH-EAST", "kind": "reserve", "qty": 2, "from_status": "available", "to_status": "reserved"},
        {"id": "IM002", "sku": "SKU-B", "warehouse": "WH-WEST", "kind": "reserve", "qty": 2, "from_status": "available", "to_status": "reserved"},
        {"id": "IM003", "sku": "SKU-B", "warehouse": "WH-WEST", "kind": "ship", "qty": 1, "from_status": "reserved", "to_status": "shipped"},
        {"id": "IM004", "sku": "SKU-D", "warehouse": "WH-WEST", "kind": "reserve", "qty": 1, "from_status": "available", "to_status": "reserved"},
    ]
    payment_status_events = [
        {"id": "PS001", "payment": "P002", "intent_id": "PI-O002", "status": "failed"},
        {"id": "PS002", "payment": "P003", "intent_id": "PI-O002", "status": "processing"},
        {"id": "PS003", "payment": "P003", "intent_id": "PI-O002", "status": "succeeded"},
        {"id": "PS004", "payment": "P004", "intent_id": "PI-O003", "status": "processing"},
    ]
    tracking_events = [
        {"id": "T001", "fulfillment": "F001", "shipment_id": "SHIP-F001", "carrier_label": "SYNTHETIC-CARRIER", "status": "shipped"},
        {"id": "T002", "fulfillment": "F001", "shipment_id": "SHIP-F001", "carrier_label": "SYNTHETIC-CARRIER", "status": "delivered"},
        {"id": "T003", "fulfillment": "F002", "shipment_id": "SHIP-F002", "carrier_label": "SYNTHETIC-CARRIER", "status": "shipped"},
        {"id": "T004", "fulfillment": "F003", "shipment_id": "SHIP-F003", "carrier_label": "SYNTHETIC-CARRIER", "status": "delivered"},
        {"id": "T005", "fulfillment": "F004", "shipment_id": "SHIP-F004", "carrier_label": "SYNTHETIC-CARRIER", "status": "delivered"},
    ]
    return_lines = [
        {"id": "RL001", "order": "O004", "sku": "SKU-C", "qty": 1, "refund": "R001", "status": "received"},
        {"id": "RL002", "order": "O006", "sku": "SKU-D", "qty": 1, "refund": "R002", "status": "requested"},
    ]
    refund_status_events = [
        {"id": "RS001", "refund": "R001", "status": "pending"},
        {"id": "RS002", "refund": "R001", "status": "succeeded"},
        {"id": "RS003", "refund": "R002", "status": "pending"},
    ]
    events = [
        {"id": "E001", "name": "view_promotion", "buyer": "U001", "promotion": "PROMO-A", "order": None},
        {"id": "E002", "name": "view_item", "buyer": "U001", "promotion": "PROMO-A", "order": None},
        {"id": "E003", "name": "add_to_cart", "buyer": "U001", "promotion": "PROMO-A", "order": None},
        {"id": "E004", "name": "purchase", "buyer": "U001", "promotion": "PROMO-A", "order": "O001"},
        {"id": "E005", "name": "view_promotion", "buyer": "U002", "promotion": "PROMO-A", "order": None},
        {"id": "E006", "name": "begin_checkout", "buyer": "U002", "promotion": "PROMO-A", "order": "O003"},
        {"id": "E007", "name": "refund", "buyer": "U003", "promotion": "PROMO-B", "order": "O004"},
        {"id": "E008", "name": "click_promotion", "buyer": "U002", "promotion": "PROMO-A", "order": None},
    ]
    anomalies = [
        {"id": "X001", "rule": "order_duplicate", "reference": "O001", "observed_value": "O001", "expected": "duplicate business key"},
        {"id": "X002", "rule": "orphan_order_item", "reference": "O999", "observed_value": "missing_order", "expected": "missing order"},
        {"id": "X003", "rule": "refund_exceeds_paid", "reference": "O004", "observed_value": "6000", "expected": "refund > succeeded payment"},
        {"id": "X004", "rule": "inventory_negative", "reference": "SKU-B@WH-WEST", "observed_value": "-1", "expected": "available < 0"},
        {"id": "X005", "rule": "enum_out_of_range", "reference": "P006", "observed_value": "expired", "expected": "status not in accepted enum"},
        {"id": "X006", "rule": "amount_imbalance", "reference": "O001", "observed_value": "10000 != 2*5000", "expected": "order amount mismatch"},
        {"id": "X007", "rule": "time_inversion", "reference": "O002", "observed_value": "2026-10-20T09:05 < order 2026-10-21T09:00", "expected": "payment before order"},
        {"id": "X008", "rule": "unauthorized_access", "reference": "U005", "observed_value": "viewer->admin_report", "expected": "access denied"},
    ]
    fixture = {
        "namespace": NAMESPACE,
        "currency": "CNY",
        "synthetic": True,
        "products": products,
        "campaigns": campaigns,
        "orders": orders,
        "payments": payments,
        "payment_status_events": payment_status_events,
        "fulfillments": fulfillments,
        "tracking_events": tracking_events,
        "refunds": refunds,
        "return_lines": return_lines,
        "refund_status_events": refund_status_events,
        "inventory": inventory,
        "inventory_movements": inventory_movements,
        "events": events,
        "quality_anomalies": anomalies,
    }
    add_provenance(fixture)
    fixture["expected"] = summarize(fixture)
    validate(fixture)
    return fixture


def add_provenance(fixture: dict) -> None:
    """Give each synthetic fact its own event time and cleanup namespace."""
    times = {
        "products": ["2026-10-19T08:00:00+08:00"] * 4,
        "campaigns": ["2026-10-20T00:00:00+08:00", "2026-10-22T00:00:00+08:00"],
        "orders": [f"2026-10-{day}T09:00:00+08:00" for day in (20, 21, 21, 22, 22, 23)],
        "payments": [
            "2026-10-20T09:05:00+08:00", "2026-10-21T09:05:00+08:00",
            "2026-10-21T09:15:00+08:00", "2026-10-21T09:10:00+08:00",
            "2026-10-22T09:05:00+08:00", "2026-10-22T09:10:00+08:00",
            "2026-10-23T09:05:00+08:00",
        ],
        "payment_status_events": [
            "2026-10-21T09:05:00+08:00", "2026-10-21T09:14:00+08:00",
            "2026-10-21T09:15:00+08:00", "2026-10-21T09:10:00+08:00",
        ],
        "fulfillments": [
            "2026-10-20T16:00:00+08:00", "2026-10-21T16:00:00+08:00",
            "2026-10-22T16:00:00+08:00", "2026-10-23T16:00:00+08:00",
        ],
        "tracking_events": [
            "2026-10-20T16:00:00+08:00", "2026-10-21T12:00:00+08:00",
            "2026-10-21T16:00:00+08:00", "2026-10-23T12:00:00+08:00",
            "2026-10-24T12:00:00+08:00",
        ],
        "refunds": ["2026-10-23T14:00:00+08:00", "2026-10-24T14:00:00+08:00"],
        "return_lines": ["2026-10-23T10:00:00+08:00", "2026-10-24T10:00:00+08:00"],
        "refund_status_events": [
            "2026-10-23T14:00:00+08:00", "2026-10-23T15:00:00+08:00",
            "2026-10-24T14:00:00+08:00",
        ],
        "inventory": ["2026-10-24T18:00:00+08:00"] * 5,
        "inventory_movements": [
            "2026-10-20T09:01:00+08:00", "2026-10-21T09:01:00+08:00",
            "2026-10-21T16:00:00+08:00", "2026-10-23T09:01:00+08:00",
        ],
        "events": [
            "2026-10-20T08:00:00+08:00", "2026-10-20T08:10:00+08:00",
            "2026-10-20T08:20:00+08:00", "2026-10-20T09:06:00+08:00",
            "2026-10-21T08:00:00+08:00", "2026-10-21T08:30:00+08:00",
            "2026-10-23T15:00:00+08:00", "2026-10-21T08:05:00+08:00",
        ],
        "quality_anomalies": ["2026-10-25T10:00:00+08:00"] * 8,
    }
    for kind, timestamps in times.items():
        rows = fixture[kind]
        assert len(rows) == len(timestamps), kind
        for row, event_time in zip(rows, timestamps):
            if "biz_date" in row:
                assert row["biz_date"] == event_time[:10]
            row.update(
                fixture_namespace=NAMESPACE, source_system=SOURCE_SYSTEM, run_id=RUN_ID,
                event_time=event_time, biz_date=event_time[:10],
            )
            if kind in {"orders", "payments", "refunds"}:
                row["currency"] = fixture["currency"]
    for payment in fixture["payments"]:
        payment["intent_id"] = f"PI-{payment['order']}"
    for fulfillment in fixture["fulfillments"]:
        fulfillment["shipment_id"] = f"SHIP-{fulfillment['id']}"
        tracking = [row for row in fixture["tracking_events"] if row["fulfillment"] == fulfillment["id"]]
        fulfillment["status_as_of"] = max(row["event_time"] for row in tracking)
    for inventory in fixture["inventory"]:
        inventory["incoming"] = 0


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
        "payment_retry_orders": sorted(order for order, count in Counter(p["order"] for p in fixture["payments"]).items() if count > 1),
        "returned_qty": sum(line["qty"] for line in fixture["return_lines"]),
        "stockout_locations": sorted(f"{row['sku']}@{row['warehouse']}" for row in fixture["inventory"] if row["available"] == 0),
        "campaign_exposures": sum(event["name"] == "view_promotion" for event in fixture["events"]),
        "campaign_clicks": sum(event["name"] == "click_promotion" for event in fixture["events"]),
        "quality_anomaly_ids": [row["id"] for row in fixture["quality_anomalies"]],
    }


def validate(fixture: dict) -> None:
    orders = {row["id"]: row for row in fixture["orders"]}
    payments = {row["id"]: row for row in fixture["payments"]}
    products = {row["sku"]: row for row in fixture["products"]}
    fulfillments = {row["id"]: row for row in fixture["fulfillments"]}
    refunds = {row["id"]: row for row in fixture["refunds"]}
    campaigns = {row["id"]: row for row in fixture["campaigns"]}
    assert len(orders) == len(fixture["orders"])
    assert len(payments) == len(fixture["payments"])
    assert len(products) == len(fixture["products"])
    for kind in ("products", "campaigns", "orders", "payments", "payment_status_events", "fulfillments",
                 "tracking_events", "refunds", "return_lines", "refund_status_events", "inventory",
                 "inventory_movements", "events", "quality_anomalies"):
        for row in fixture[kind]:
            assert row["fixture_namespace"] == NAMESPACE
            assert row["source_system"] == SOURCE_SYSTEM and row["run_id"] == RUN_ID
            assert row["biz_date"] == row["event_time"][:10]
    for order in fixture["orders"]:
        assert order["sku"] in products
    for payment in fixture["payments"]:
        assert payment["order"] in orders
        assert payment["amount_cents"] > 0
        assert payment["event_time"] >= orders[payment["order"]]["event_time"]
        assert payment["currency"] == fixture["currency"]
    for event in fixture["payment_status_events"]:
        assert event["payment"] in payments
        assert event["intent_id"] == payments[event["payment"]]["intent_id"]
    for fulfillment in fixture["fulfillments"]:
        assert fulfillment["order"] in orders and fulfillment["sku"] == orders[fulfillment["order"]]["sku"]
        assert fulfillment["event_time"] >= orders[fulfillment["order"]]["event_time"]
    for event in fixture["tracking_events"]:
        assert event["fulfillment"] in fulfillments
        assert event["shipment_id"] == fulfillments[event["fulfillment"]]["shipment_id"]
        assert event["carrier_label"].startswith("SYNTHETIC-")
    for refund in fixture["refunds"]:
        assert refund["order"] in orders
        assert payments[refund["payment"]]["order"] == refund["order"]
        assert refund["qty"] <= orders[refund["order"]]["qty"]
        assert refund["event_time"] >= payments[refund["payment"]]["event_time"]
        assert refund["currency"] == fixture["currency"]
    for line in fixture["return_lines"]:
        assert line["refund"] in refunds
        assert (line["order"], line["sku"], line["qty"]) == tuple(refunds[line["refund"]][key] for key in ("order", "sku", "qty"))
    for event in fixture["refund_status_events"]:
        assert event["refund"] in refunds
    for row in fixture["inventory"]:
        assert row["on_hand"] == row["available"] + row["reserved"] + row["damaged"]
        assert row["sku"] in products and row["incoming"] >= 0
    inventory_keys = {(row["sku"], row["warehouse"]) for row in fixture["inventory"]}
    assert len(inventory_keys) == len(fixture["inventory"])
    for movement in fixture["inventory_movements"]:
        assert (movement["sku"], movement["warehouse"]) in inventory_keys
        assert movement["qty"] > 0
    for event in fixture["events"]:
        assert event["promotion"] in campaigns
        assert event["order"] is None or event["order"] in orders
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
