"""Validation contract for the seven stream producer runtime modes."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FixedRateConfig(StrictModel):
    mode: str = Field(default="fixed_rate", pattern="^fixed_rate$")
    rows_per_sec: int = Field(gt=0)
    columns: list[str] = Field(min_length=1)


class RandomConfig(StrictModel):
    mode: str = Field(default="random", pattern="^random$")
    interval_ms: tuple[int, int]
    columns: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def valid_interval(self):
        if self.interval_ms[0] < 0 or self.interval_ms[1] < self.interval_ms[0]:
            raise ValueError("interval_ms must be [min,max] with 0 <= min <= max")
        return self


class AbnormalConfig(StrictModel):
    mode: str = Field(default="abnormal", pattern="^abnormal$")
    base: FixedRateConfig
    abnormal_ratio: float = Field(ge=0, le=1)
    abnormal_values: list[Any]


class DuplicateConfig(StrictModel):
    mode: str = Field(default="duplicate", pattern="^duplicate$")
    base: FixedRateConfig
    duplicate_ratio: float = Field(ge=0, le=1)


class DelayedConfig(StrictModel):
    mode: str = Field(default="delayed", pattern="^delayed$")
    base: FixedRateConfig
    delay_ms: tuple[int, int]

    @model_validator(mode="after")
    def valid_interval(self):
        if self.delay_ms[0] < 0 or self.delay_ms[1] < self.delay_ms[0]:
            raise ValueError("delay_ms must be [min,max] with 0 <= min <= max")
        return self


class OutOfOrderConfig(StrictModel):
    mode: str = Field(default="out_of_order", pattern="^out_of_order$")
    base: FixedRateConfig
    skew_ms: tuple[int, int]

    @model_validator(mode="after")
    def valid_interval(self):
        if self.skew_ms[0] < 0 or self.skew_ms[1] < self.skew_ms[0]:
            raise ValueError("skew_ms must be [min,max] with 0 <= min <= max")
        return self


class BurstConfig(StrictModel):
    mode: str = Field(default="burst", pattern="^burst$")
    base: FixedRateConfig
    burst_every_sec: int = Field(gt=0)
    burst_count: int = Field(gt=0)


SCHEMAS = {
    "fixed_rate": FixedRateConfig,
    "random": RandomConfig,
    "abnormal": AbnormalConfig,
    "duplicate": DuplicateConfig,
    "delayed": DelayedConfig,
    "out_of_order": OutOfOrderConfig,
    "burst": BurstConfig,
}


def validate_runtime_config(config: dict[str, Any]) -> dict[str, Any]:
    """Validate a mode-tagged config and return its normalized JSON payload."""
    if not isinstance(config, dict):
        raise ValueError("runtime_config must be an object")
    mode = config.get("mode")
    schema = SCHEMAS.get(mode)
    if schema is None:
        raise ValueError("runtime_config.mode must be one of: " + ", ".join(SCHEMAS))
    try:
        return schema.model_validate(config).model_dump(mode="json")
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc
