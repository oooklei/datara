from datetime import datetime

import pytest

from rebuild.stream.legacy_bridge import from_legacy_state, to_legacy_state
from rebuild.stream.producer import build_producer
from rebuild.stream.producer_schema import validate_runtime_config


BASE = {"rows_per_sec": 10, "columns": ["id", "name"]}
VALID = [
    {"mode": "fixed_rate", **BASE},
    {"mode": "random", "interval_ms": [0, 2], "columns": ["id"]},
    {"mode": "abnormal", "base": BASE, "abnormal_ratio": 0.5, "abnormal_values": ["bad"]},
    {"mode": "duplicate", "base": BASE, "duplicate_ratio": 1},
    {"mode": "delayed", "base": BASE, "delay_ms": [0, 1]},
    {"mode": "out_of_order", "base": BASE, "skew_ms": [0, 1]},
    {"mode": "burst", "base": BASE, "burst_every_sec": 2, "burst_count": 4},
]


@pytest.mark.parametrize("config", VALID)
def test_each_mode_validates_and_emits_common_event(config, monkeypatch):
    monkeypatch.setattr("rebuild.stream.producer.time.sleep", lambda _seconds: None)
    producer = build_producer(config, seed=7).open(3)
    event = producer.next()
    assert set(event) == {"source", "ts", "data"}
    assert event["source"] == "stream-producer"
    datetime.fromisoformat(event["ts"])
    assert producer.offset == 4


@pytest.mark.parametrize("config", [
    {"mode": "fixed_rate", "rows_per_sec": 0, "columns": ["id"]},
    {"mode": "random", "interval_ms": [5, 1], "columns": ["id"]},
    {"mode": "abnormal", "base": BASE, "abnormal_ratio": 2, "abnormal_values": ["x"]},
    {"mode": "duplicate", "base": BASE, "duplicate_ratio": -1},
    {"mode": "delayed", "base": BASE, "delay_ms": [-1, 2]},
    {"mode": "out_of_order", "base": BASE, "skew_ms": [2, 1]},
    {"mode": "burst", "base": BASE, "burst_every_sec": 0, "burst_count": 2},
])
def test_each_mode_rejects_invalid_config(config):
    with pytest.raises(ValueError):
        validate_runtime_config(config)


def test_duplicate_mode_repeats_previous_data(monkeypatch):
    monkeypatch.setattr("rebuild.stream.producer.time.sleep", lambda _seconds: None)
    producer = build_producer(VALID[3], seed=1)
    first = producer.next()
    second = producer.next()
    assert first["data"] == second["data"]


def test_burst_mode_emits_configured_batch_without_inter_row_pacing(monkeypatch):
    sleeps = []
    monkeypatch.setattr("rebuild.stream.producer.time.sleep", sleeps.append)
    producer = build_producer(VALID[6], seed=1)
    batch = producer.next_batch()
    assert len(batch) == 4
    assert producer.offset == 4
    assert len(sleeps) == 1


def test_fixed_rate_uses_configured_rows_per_second(monkeypatch):
    sleeps = []
    monkeypatch.setattr("rebuild.stream.producer.time.sleep", sleeps.append)
    build_producer(VALID[0]).next()
    assert sleeps == [pytest.approx(0.1)]


def test_random_mode_respects_interval_bounds(monkeypatch):
    sleeps = []
    monkeypatch.setattr("rebuild.stream.producer.time.sleep", sleeps.append)
    config = {"mode": "random", "interval_ms": [1, 2], "columns": ["id"]}
    build_producer(config, seed=2).next()
    assert len(sleeps) == 1 and 0.001 <= sleeps[0] <= 0.002


def test_abnormal_mode_injects_configured_value(monkeypatch):
    monkeypatch.setattr("rebuild.stream.producer.time.sleep", lambda _seconds: None)
    config = {"mode": "abnormal", "base": BASE, "abnormal_ratio": 1, "abnormal_values": ["bad"]}
    assert build_producer(config, seed=3).next()["data"]["id"] == "bad"


def test_delayed_mode_observes_configured_delay(monkeypatch):
    sleeps = []
    monkeypatch.setattr("rebuild.stream.producer.time.sleep", sleeps.append)
    config = {"mode": "delayed", "base": BASE, "delay_ms": [5, 5]}
    build_producer(config, seed=3).next()
    assert sleeps == [pytest.approx(0.1), pytest.approx(0.005)]


def test_out_of_order_mode_backdates_event_timestamp(monkeypatch):
    monkeypatch.setattr("rebuild.stream.producer.time.sleep", lambda _seconds: None)
    config = {"mode": "out_of_order", "base": BASE, "skew_ms": [1000, 1000]}
    before = datetime.now().astimezone()
    event_time = datetime.fromisoformat(build_producer(config, seed=3).next()["ts"])
    assert event_time < before


@pytest.mark.parametrize(("new", "legacy"), [
    ("STARTING", "starting"), ("RUNNING", "running"), ("RECOVERING", "reconnecting"),
    ("STOPPED", "stopped"), ("FAILED", "failed"),
])
def test_legacy_state_bridge_round_trip(new, legacy):
    assert to_legacy_state(new) == legacy
    assert from_legacy_state(legacy) == new


def test_legacy_state_bridge_maps_unrepresentable_states_safely():
    assert to_legacy_state("PAUSED") == "stopped"
    with pytest.raises(ValueError):
        from_legacy_state("paused")
