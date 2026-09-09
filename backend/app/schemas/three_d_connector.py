"""Versioned, bounded internal messages; device secrets/raw MQTT are never accepted."""

from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Identifier = Annotated[str, Field(pattern=r"^[a-zA-Z0-9_-]{1,96}$")]


class Scope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    protocol_version: Literal[1] = 1
    factory_id: Literal["huakang-a"] = "huakang-a"
    site_id: Literal["3dsite-huakang-a-heyuan"] = "3dsite-huakang-a-heyuan"
    instance_id: Identifier


class Heartbeat(Scope):
    version: str = Field(min_length=1, max_length=64)


class LeaseRequest(Scope):
    printer_id: Identifier


class LeaseRef(LeaseRequest):
    leader_lease_id: Identifier


class SessionRef(LeaseRef):
    connection_session_id: Identifier


class SessionStart(SessionRef):
    generation: int = Field(ge=1, le=2147483647)


class StateEvent(SessionRef):
    event_id: Identifier
    sequence: int = Field(ge=1, le=9007199254740991)
    observed_at: datetime | None = None
    connected: bool
    state: Literal[
        "RUNNING", "PAUSE", "FINISH", "IDLE", "FAILED", "ERROR", "UNKNOWN", "STALE"
    ]
    current_file: str = Field(default="", max_length=512)
    device_job_key: str = Field(default="", max_length=128)
    progress_percent: int = Field(default=0, ge=0, le=100)
    remaining_minutes: int = Field(default=0, ge=0, le=100000)
    live_material: str = Field(default="", max_length=255)
    nozzle_temperature: float = Field(default=0, ge=0, le=500, allow_inf_nan=False)
    bed_temperature: float = Field(default=0, ge=0, le=200, allow_inf_nan=False)
    nozzle_target: float = Field(default=0, ge=0, le=500, allow_inf_nan=False)
    bed_target: float = Field(default=0, ge=0, le=200, allow_inf_nan=False)
    layer_num: int = Field(default=0, ge=0, le=100000)
    total_layers: int = Field(default=0, ge=0, le=100000)
    error_code: str = Field(default="", max_length=64)

    @field_validator("observed_at")
    @classmethod
    def aware(cls, value):
        if value is not None:
            if value.tzinfo is None:
                raise ValueError("timezone_required")
            return value.astimezone(UTC)
        return value

    @model_validator(mode="after")
    def state_matches_connection(self):
        if self.connected and (self.observed_at is None or self.state == "STALE"):
            raise ValueError("live_state_requires_observation")
        if not self.connected and self.state not in {"STALE", "UNKNOWN"}:
            raise ValueError("disconnected_state_cannot_finish_job")
        return self


class CommandRef(SessionRef):
    command_id: Identifier
    command_lease_id: Identifier


class CommandResult(CommandRef):
    status: Literal["succeeded", "unknown"]
    evidence_event_id: Identifier | None = None
    reason: Literal[
        "state_evidence",
        "evidence_timeout",
        "lease_lost",
        "send_uncertain",
        "disconnected",
    ]

    @model_validator(mode="after")
    def evidence_required(self):
        if self.status == "succeeded" and (
            not self.evidence_event_id or self.reason != "state_evidence"
        ):
            raise ValueError("success_requires_state_evidence")
        if self.status == "unknown" and (
            self.evidence_event_id or self.reason == "state_evidence"
        ):
            raise ValueError("unknown_has_no_success_evidence")
        return self
