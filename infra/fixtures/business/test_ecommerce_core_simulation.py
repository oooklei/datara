"""Business checks for the isolated ecommerce capability fixture."""

import ecommerce_core_simulation as sim


def test_paid_revenue_excludes_failed_processing_and_pending_refund():
    fixture = sim.build_fixture()
    expected = fixture["expected"]
    assert expected["paid_orders"] == 4
    assert expected["gross_paid_cents"] == 36_000
    assert expected["successful_refund_cents"] == 6_000
    assert expected["net_paid_cents"] == 30_000
    assert expected["payment_retry_orders"] == ["O002"]
    assert expected["returned_qty"] == 2
    assert expected["stockout_locations"] == ["SKU-B@WH-EAST"]
    assert (expected["campaign_exposures"], expected["campaign_clicks"]) == (2, 1)


def test_repeat_and_partial_fulfillment_are_derived_from_linked_facts():
    fixture = sim.build_fixture()
    assert fixture["expected"]["repeat_buyers"] == ["U001"]
    assert fixture["expected"]["partial_fulfillment_orders"] == ["O002"]
    assert {row["order"] for row in fixture["refunds"]} <= {row["id"] for row in fixture["orders"]}


def test_dirty_cases_are_separate_and_fixture_is_reproducible():
    one = sim.build_fixture()
    two = sim.build_fixture()
    assert one == two
    assert one["namespace"] == sim.NAMESPACE
    assert [row["id"] for row in one["quality_anomalies"]] == [
        "X001", "X002", "X003", "X004", "X005", "X006", "X007", "X008"
    ]
    assert all(row["id"].startswith("O") for row in one["orders"])


def test_sku_inventory_payment_shipping_and_return_facts_are_linked():
    fixture = sim.build_fixture()
    assert {row["sku"] for row in fixture["products"]} == {row["sku"] for row in fixture["orders"]}
    assert {row["warehouse"] for row in fixture["inventory"] if row["sku"] == "SKU-B"} == {"WH-EAST", "WH-WEST"}
    assert {row["intent_id"] for row in fixture["payments"] if row["order"] == "O002"} == {"PI-O002"}
    assert [row["status"] for row in fixture["payment_status_events"] if row["payment"] == "P003"] == ["processing", "succeeded"]
    assert {row["fulfillment"] for row in fixture["tracking_events"]} == {row["id"] for row in fixture["fulfillments"]}
    assert {row["refund"] for row in fixture["return_lines"]} == {row["id"] for row in fixture["refunds"]}
    assert {row["name"] for row in fixture["events"]} >= {"view_promotion", "click_promotion", "add_to_cart", "purchase"}


def test_each_fact_has_cleanup_namespace_and_independent_event_time():
    fixture = sim.build_fixture()
    for kind in ("products", "campaigns", "orders", "payments", "payment_status_events", "fulfillments",
                 "tracking_events", "refunds", "return_lines", "refund_status_events", "inventory",
                 "inventory_movements", "events", "quality_anomalies"):
        assert all(row["fixture_namespace"] == sim.NAMESPACE for row in fixture[kind])
        assert all(row["biz_date"] == row["event_time"][:10] for row in fixture[kind])
    order_times = {row["id"]: row["event_time"] for row in fixture["orders"]}
    assert all(row["event_time"] > order_times[row["order"]] for row in fixture["payments"])
    assert all(row["carrier_label"] == "SYNTHETIC-CARRIER" for row in fixture["tracking_events"])
