"""V3 business result boundary. Existing v1/v2 wire records remain readable.

The domain supplies times, definitions and unknowns. This validator must never
make an old cache fresh, infer a missing total, or register model-provided links.
"""
from datetime import date, datetime
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator, model_validator


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


def aware_timestamp(value):
    if value is not None and datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is None:
        raise ValueError("timestamp must include its timezone")
    return value


class Scope(Record):
    factory_ids: list[str]
    module_id: str
    filters: dict[str, str | int | float | bool | list | None]
    resource_refs: list[str]
    coverage: Literal["authorized_scope", "selected_resources", "filtered_scope"]
    label: str

    @field_validator("factory_ids", "resource_refs")
    @classmethod
    def unique(cls, values):
        if len(values) != len(set(values)):
            raise ValueError("duplicate scope references")
        return values


class Freshness(Record):
    state: Literal["fresh", "stale", "unknown", "not_applicable"]
    max_age_seconds: int | None = Field(ge=0)
    cache_hit: bool
    cache_created_at: str | None
    policy_id: str

    _timestamp = field_validator("cache_created_at")(aware_timestamp)


class Metric(Record):
    value: StrictInt | StrictStr | None
    unit: str
    definition_id: str
    status: Literal["known", "unknown", "not_applicable"]
    currency: str | None = None

    @model_validator(mode="after")
    def consistent(self):
        if (self.status == "known") != (self.value is not None):
            raise ValueError("unknown or inapplicable metric must be null")
        if isinstance(self.value, str) and not re.fullmatch(r"-?(?:0|[1-9]\d*)(?:\.\d+)?", self.value):
            raise ValueError("metric string must be a finite decimal")
        return self


class Unknown(Record):
    field: str
    reason: str


class Action(Record):
    action_id: str
    kind: Literal["navigate", "open_source", "refresh", "export"]
    label: str
    resource_ref: str | None


class ToolResult(Record):
    record_type: Literal["tool_result"]
    contract_version: Literal[3]
    tool_name: str
    tool_version: str
    tool_call_id: str
    run_id: str
    step_id: str
    status: Literal["ok", "empty", "partial", "unknown", "not_connected", "forbidden", "stale", "failed"]
    scope: Scope
    requested_at: str
    as_of: str | None
    observed_at: str | None
    retrieved_at: str
    timezone: str
    business_date: str | None = None
    data_mode: Literal["snapshot", "telemetry", "historical", "unavailable"]
    freshness: Freshness
    metrics: dict[str, Metric]
    rows: list[dict[str, Any]]
    total_count: int | None = Field(ge=0)
    returned_count: int = Field(ge=0)
    truncated: bool
    next_cursor: str | None
    definitions: dict[str, str]
    unknown_fields: list[Unknown]
    source_refs: list[str]
    allowed_actions: list[Action]
    diagnostic_code: str | None

    _timestamps = field_validator("requested_at", "as_of", "observed_at", "retrieved_at")(aware_timestamp)

    @field_validator("business_date")
    @classmethod
    def calendar_date(cls, value):
        if value is not None and date.fromisoformat(value).isoformat() != value:
            raise ValueError("business date must be an ISO calendar date")
        return value

    @model_validator(mode="after")
    def consistent(self):
        if self.returned_count != len(self.rows):
            raise ValueError("returned count must match actual rows")
        if self.total_count is not None and self.returned_count > self.total_count:
            raise ValueError("returned count exceeds exact total")
        if self.next_cursor is not None and not self.truncated:
            raise ValueError("cursor requires an incomplete page")
        if self.status == "empty" and (self.total_count != 0 or self.rows or self.truncated or self.next_cursor):
            raise ValueError("empty requires a successful exact zero query")
        if self.status in {"forbidden", "not_connected", "failed"}:
            if self.rows or self.metrics or self.total_count is not None or self.source_refs or self.allowed_actions or self.scope.resource_refs:
                raise ValueError("unavailable result cannot contain business facts or references")
        if self.status == "ok" and (self.truncated or self.freshness.state == "stale" or self.total_count == 0):
            raise ValueError("partial/stale/empty results must not claim ok")
        if self.freshness.cache_hit and self.freshness.cache_created_at is None:
            raise ValueError("cached result must preserve its creation time")
        if self.freshness.state == "fresh" and self.as_of is None:
            raise ValueError("fresh requires a known data timestamp")
        if len(self.source_refs) != len(set(self.source_refs)):
            raise ValueError("duplicate sources")
        if any(metric.definition_id not in self.definitions for metric in self.metrics.values()):
            raise ValueError("every metric needs a versioned definition")
        return self


def validate_result(value, *, registered_sources, registered_resources, row_fields):
    """Enforce server-created evidence and domain projection at the final edge."""
    result = ToolResult.model_validate(value)
    if not set(result.source_refs) <= set(registered_sources):
        raise ValueError("source reference was not registered by this run")
    if any("resource_ref" in row and not isinstance(row["resource_ref"], str) for row in result.rows):
        raise ValueError("resource reference must be an opaque string")
    references = (set(result.scope.resource_refs) | {a.resource_ref for a in result.allowed_actions if a.resource_ref}
                  | {row["resource_ref"] for row in result.rows if isinstance(row.get("resource_ref"), str)})
    if not references <= set(registered_resources):
        raise ValueError("resource reference was not authorized by the domain")
    if any(set(row) - set(row_fields) for row in result.rows):
        raise ValueError("row contains fields outside the domain projection")
    return result.model_dump(mode="json")
