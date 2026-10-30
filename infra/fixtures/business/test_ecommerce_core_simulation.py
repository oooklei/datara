"""Business checks for the isolated ecommerce capability fixture."""

import ecommerce_core_simulation as sim


def test_paid_revenue_excludes_failed_processing_and_pending_refund():
    fixture = sim.build_fixture()
    expected = fixture["expected"]
    assert expected["paid_orders"] == 4
    assert expected["gross_paid_cents"] == 36_000
    assert expected["successful_refund_cents"] == 6_000
    assert expected["net_paid_cents"] == 30_000


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
    assert [row["id"] for row in one["anomalies_not_loaded_into_valid_facts"]] == [
        "X001", "X002", "X003", "X004"
    ]
    assert all(row["id"].startswith("O") for row in one["orders"])
