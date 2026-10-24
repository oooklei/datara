"""Deterministic stream transform, window aggregation, and fusion primitives."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Mapping


class StreamProcessingError(ValueError):
    """Raised when a stream sample cannot satisfy the declared processor contract."""


def validate_event(event: Mapping[str, Any], schema: Mapping[str, str]) -> None:
    for field, expected in schema.items():
        if field not in event:
            raise StreamProcessingError(f"missing schema field: {field}")
        value = event[field]
        actual = "number" if isinstance(value, (int, float)) and not isinstance(value, bool) else type(value).__name__
        if actual != expected:
            raise StreamProcessingError(f"field {field} has type {actual}, expected {expected}")


def filter_events(events: Iterable[Mapping[str, Any]], predicate: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    """Apply a declarative equality predicate; no executable callback is accepted."""
    predicate = predicate or {}
    if not isinstance(predicate, Mapping):
        raise StreamProcessingError("predicate must be an object")
    return [dict(event) for event in events if all(event.get(key) == value for key, value in predicate.items())]


def aggregate_window(
    events: Iterable[Mapping[str, Any]],
    *,
    key_field: str,
    value_field: str,
    window_size: int,
) -> list[dict[str, Any]]:
    if not key_field or not value_field or window_size < 1:
        raise StreamProcessingError("key_field, value_field and positive window_size are required")
    buckets: dict[Any, list[float]] = defaultdict(list)
    for event in events:
        if key_field not in event or value_field not in event:
            raise StreamProcessingError("aggregation field is missing")
        value = event[value_field]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise StreamProcessingError(f"aggregation value {value!r} is not numeric")
        buckets[event[key_field]].append(float(value))
    result: list[dict[str, Any]] = []
    for key, values in buckets.items():
        for offset in range(0, len(values), window_size):
            window = values[offset : offset + window_size]
            result.append({
                "key": key,
                "window_index": offset // window_size,
                "count": len(window),
                "sum": sum(window),
                "average": sum(window) / len(window),
            })
    return result


def fuse_streams(streams: Mapping[str, Iterable[Mapping[str, Any]]], *, key_field: str) -> list[dict[str, Any]]:
    """Inner-fuse named streams on a key, retaining source provenance."""
    if not streams or not key_field:
        raise StreamProcessingError("streams and key_field are required")
    indexed: dict[Any, dict[str, dict[str, Any]]] = defaultdict(dict)
    for source, events in streams.items():
        for event in events:
            if key_field not in event:
                raise StreamProcessingError(f"fusion field {key_field} is missing from {source}")
            indexed[event[key_field]][source] = dict(event)
    return [
        {"key": key, "sources": source_events}
        for key, source_events in indexed.items()
        if len(source_events) == len(streams)
    ]
