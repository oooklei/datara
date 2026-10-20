"""Small deterministic-friendly event producers for the seven runtime modes."""

from __future__ import annotations

import random
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator

from rebuild.stream.producer_schema import validate_runtime_config


class StreamProducer:
    """Resumable iterator yielding the common ``{source, ts, data}`` event."""

    def __init__(self, config: dict[str, Any], source: str = "stream-producer", *, seed: int | None = None):
        self.config = validate_runtime_config(config)
        self.source = source
        self.random = random.Random(seed)
        self.offset = 0
        self._previous: dict[str, Any] | None = None
        self._last_event_time: datetime | None = None
        self._suppress_pacing = False

    def open(self, offset: int = 0) -> "StreamProducer":
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise ValueError("offset must be a non-negative integer")
        self.offset = offset
        return self

    def __iter__(self) -> Iterator[dict[str, Any]]:
        while True:
            yield from self.next_batch()

    def next_batch(self) -> list[dict[str, Any]]:
        """Emit one event normally or the configured burst-sized event batch."""
        if self.config["mode"] != "burst":
            return [self.next()]
        base = self.config["base"]
        period = base["rows_per_sec"] * self.config["burst_every_sec"]
        count = self.config["burst_count"] if self.offset % period == 0 else 1
        batch = []
        for index in range(count):
            self._suppress_pacing = index > 0
            batch.append(self.next())
        self._suppress_pacing = False
        return batch

    def next(self) -> dict[str, Any]:
        config = self.config
        mode = config["mode"]
        base = config.get("base", config)
        idx = self.offset
        self.offset += 1
        now = datetime.now(timezone.utc)
        if self._suppress_pacing:
            delay_ms = 0
        elif mode == "random":
            lo, hi = config["interval_ms"]
            delay_ms = self.random.randint(lo, hi)
            if delay_ms:
                time.sleep(delay_ms / 1000)
        elif mode == "fixed_rate":
            delay_ms = 1000 / base["rows_per_sec"]
            if delay_ms:
                time.sleep(delay_ms / 1000)
        else:
            delay_ms = 1000 / base["rows_per_sec"]
            if delay_ms:
                time.sleep(delay_ms / 1000)

        columns = base["columns"]
        data = {column: self._sample(column, idx) for column in columns}
        ts = now
        if mode == "abnormal" and self.random.random() < config["abnormal_ratio"] and columns:
            data[columns[0]] = self.random.choice(config["abnormal_values"] or ["__abnormal__"])
        elif mode == "duplicate" and self._previous is not None and self.random.random() < config["duplicate_ratio"]:
            data = dict(self._previous)
        elif mode == "delayed":
            lo, hi = config["delay_ms"]
            delay = self.random.randint(lo, hi)
            if delay:
                time.sleep(delay / 1000)
        elif mode == "out_of_order":
            lo, hi = config["skew_ms"]
            ts -= timedelta(milliseconds=self.random.randint(lo, hi))
        self._previous = dict(data)
        self._last_event_time = ts
        return {"source": self.source, "ts": ts.isoformat(), "data": data}

    def _sample(self, column: str, index: int) -> Any:
        # Preserve stable data across resume while allowing arbitrary column names.
        if column.lower().endswith(("id", "count", "amount", "value")):
            return index
        return f"{column}-{index}"


def build_producer(config: dict[str, Any], source: str = "stream-producer", *, seed: int | None = None) -> StreamProducer:
    return StreamProducer(config, source, seed=seed)
