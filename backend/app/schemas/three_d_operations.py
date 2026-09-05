from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Spool(Strict):
    material: str = Field(min_length=1, max_length=255)
    lot: str = Field(min_length=1, max_length=128)
    color: str = Field(default="", max_length=64)
    supplier: str = Field(default="", max_length=255)
    initial_g: float = Field(gt=0, le=100000, allow_inf_nan=False)
    remaining_g: float = Field(ge=0, le=100000, allow_inf_nan=False)
    low_g: float = Field(default=100, ge=0, le=100000, allow_inf_nan=False)
    machine_no: int | None = Field(default=None, ge=1, le=11)
    slot: int | None = Field(default=None, ge=0, le=15)

    @model_validator(mode="after")
    def valid(self):
        if self.remaining_g > self.initial_g:
            raise ValueError("remaining_exceeds_initial")
        if (self.slot is None) != (self.machine_no is None):
            raise ValueError("machine_and_slot_required_together")
        return self


class Demand(Strict):
    department: str = Field(min_length=1, max_length=128)
    cost_center: str = Field(min_length=1, max_length=128)
    product_id: str = Field(min_length=1, max_length=96)
    quantity: int = Field(ge=1, le=100000)
    due_date: date
    priority: Literal["high", "normal", "low"] = "normal"
    file_ids: list[str] = Field(default_factory=list, max_length=10)
    note: str = Field(default="", max_length=2000)


class FileAlias(Strict):
    product_id: str = Field(min_length=1, max_length=96)
    file_name: str = Field(min_length=1, max_length=512)
    file_id: str = Field(default="", max_length=96)
    version: str = Field(min_length=1, max_length=64)


class Profile(Strict):
    machine_no: int = Field(ge=1, le=11)
    materials: list[str] = Field(max_length=30)
    product_ids: list[str] = Field(default_factory=list, max_length=100)
    service_interval_hours: float = Field(
        default=250, gt=0, le=10000, allow_inf_nan=False
    )
    maintenance_blocked: bool = False


class SaveResource(Strict):
    factory_id: Literal["huakang-a"] = "huakang-a"
    resource_key: str = Field(min_length=1, max_length=128)
    revision: int = Field(default=0, ge=0)
    idempotency_key: str = Field(min_length=8, max_length=128)
    reason: str = Field(min_length=1, max_length=500)
    data: dict


class Action(Strict):
    factory_id: Literal["huakang-a"] = "huakang-a"
    revision: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=128)
    reason: str = Field(min_length=1, max_length=500)
    action: Literal[
        "approve", "reject", "schedule", "complete", "cancel", "archive", "match"
    ]
    target_id: str = Field(default="", max_length=96)
    feedback: str = Field(default="", max_length=2000)


class FileMetadata(Strict):
    name: str = Field(min_length=1, max_length=255)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    size: int = Field(gt=0, le=10485760)
    extension: Literal[".3mf", ".stl", ".gcode", ".pdf", ".png", ".jpg"]


class RunEvidence(Strict):
    record_id: str = Field(min_length=1, max_length=96)
    spool_ids: list[str] = Field(default_factory=list, max_length=16)
    file_ids: list[str] = Field(default_factory=list, max_length=10)
    quality: Literal["pending", "passed", "failed"] = "pending"
    note: str = Field(min_length=1, max_length=2000)
