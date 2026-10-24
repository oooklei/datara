from rebuild.stream.processor import StreamProcessingError, aggregate_window, filter_events, fuse_streams, validate_event


def test_filter_validate_and_window_aggregate_are_deterministic():
    events = [{"kind": "order", "amount": 2}, {"kind": "skip", "amount": 9}, {"kind": "order", "amount": 4}]
    validate_event(events[0], {"kind": "str", "amount": "number"})
    selected = filter_events(events, {"kind": "order"})
    assert aggregate_window(selected, key_field="kind", value_field="amount", window_size=2) == [
        {"key": "order", "window_index": 0, "count": 2, "sum": 6.0, "average": 3.0}
    ]


def test_fusion_requires_all_named_streams_and_preserves_provenance():
    result = fuse_streams(
        {"orders": [{"id": 1, "amount": 4}], "customers": [{"id": 1, "name": "Ada"}]},
        key_field="id",
    )
    assert result == [{"key": 1, "sources": {"orders": {"id": 1, "amount": 4}, "customers": {"id": 1, "name": "Ada"}}}]


def test_processor_fails_closed_on_invalid_schema_and_numeric_input():
    try:
        validate_event({"amount": "4"}, {"amount": "number"})
        raise AssertionError("expected schema failure")
    except StreamProcessingError:
        pass
    try:
        aggregate_window([{"kind": "x", "amount": "bad"}], key_field="kind", value_field="amount", window_size=1)
        raise AssertionError("expected numeric failure")
    except StreamProcessingError:
        pass
