"""HTTP command validation. Unknown fields are rejected rather than discarded."""
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Id = Annotated[str, Field(min_length=1, max_length=128)]
Qty = Annotated[int, Field(strict=True, ge=0, le=2_000_000_000)]
Value = Annotated[Decimal, Field(ge=0, max_digits=24, decimal_places=6, allow_inf_nan=False)]
Shift = Literal["day", "night"]


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid")
    factory_id: Literal["huakang-a"]
    operation_id: Id
    expected_version: Annotated[int, Field(strict=True, ge=0)]


class Product(Command):
    id: Id | None = None
    product_no: Id
    name: Annotated[str, Field(min_length=1, max_length=255)]
    customer_name: str = ""
    external_ref: str | None = None
    external_ref_kind: Literal["order", "quotation", "none"] = "none"
    aliases: list[str] = Field(default_factory=list, max_length=100)
    is_active: bool = True


class Process(Command):
    product_id: Id
    version_label: Id
    effective_from: date
    material: str = ""
    pieces_per_board: Annotated[int, Field(strict=True, gt=0)] | None = None
    board_seconds: Annotated[int, Field(strict=True, gt=0)] | None = None
    width_cm: Value | None = None
    length_cm: Value | None = None
    machine_area_m2: Value | None = None
    ink_reference_ml: Value | None = None


class Rate(Command):
    id: Id | None = None
    rate_kind: Literal["commercial", "piece_wage", "area"]
    product_id: Id | None = None
    process_version_id: Id | None = None
    machine_id: Id | None = None
    price_group: Id | None = None
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
    unit_price: Value
    effective_from: date
    effective_to: date | None = None
    note: str = ""

    @model_validator(mode="after")
    def valid_range(self):
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("生效终日不能早于开始日")
        if self.machine_id and self.price_group:
            raise ValueError("机台覆盖与价组覆盖不能同时指定")
        return self


class Machine(Command):
    id: Id | None = None
    code: Id | None = None
    name: str | None = None
    brand: str | None = None
    model: str | None = None
    price_group: str | None = None
    admin_status: Literal["normal", "maintenance", "disabled"] = "normal"
    ink_material: Literal["hard", "soft", "other"] = "other"
    note: str = ""
    enabled: bool = True


class Worker(Command):
    id: Id | None = None
    employee_profile_id: Id | None = None
    employee_no: Id
    display_name: Annotated[str, Field(min_length=1, max_length=128)]
    role: Literal["operator", "foreman", "master", "assistant"] = "operator"
    employ_state: Literal["active", "left"] = "active"
    left_on: date | None = None
    note: str = ""


class ShiftTemplate(Command):
    id: Id | None = None
    label: Id
    shift: Shift
    start_local: Annotated[str, Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")]
    end_local: Annotated[str, Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")]
    effective_from: date
    effective_to: date | None = None
    break_minutes: Annotated[int, Field(strict=True, ge=0, lt=1440)] = 0
    note: str = ""

    @model_validator(mode="after")
    def validate_times(self):
        start, end = [int(v[:2]) * 60 + int(v[3:]) for v in (self.start_local, self.end_local)]
        if start == end or self.break_minutes >= (end-start) % 1440:
            raise ValueError("班次跨度必须大于休息时间")
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("班次生效终日不能早于开始日")
        return self


class Quality(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reported_qty: Qty
    good_qty: Qty
    defective_qty: Qty
    pending_qty: Qty
    semi_finished_qty: Qty

    @model_validator(mode="after")
    def conserve(self):
        delta = self.reported_qty - self.good_qty - self.defective_qty - self.pending_qty - self.semi_finished_qty
        if delta:
            raise ValueError(f"质量数量不守恒，差异 {delta} 件")
        return self


class Allocation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: Id
    piece_qty: Annotated[int, Field(strict=True, gt=0)]
    job_version: Annotated[int, Field(strict=True, ge=1)]


class Report(Command, Quality):
    business_date: date
    shift: Shift
    shift_template_version_id: Id
    machine_id: Id
    product_id: Id
    process_version_id: Id
    worker_ids: list[Id] = Field(default_factory=list, max_length=500)
    notes: str = ""
    source_allocations: list[Allocation] = Field(default_factory=list, max_length=500)
    evidence_job_ids: list[Id] = Field(default_factory=list, max_length=500)

    @field_validator("worker_ids", "evidence_job_ids")
    @classmethod
    def unique_ids(cls, values):
        if len(values) != len(set(values)):
            raise ValueError("不能重复选择同一记录")
        return values


class ReportCommand(Command):
    report_id: Id


class QualityCommand(ReportCommand):
    quality: Quality
    reason: Annotated[str, Field(min_length=1, max_length=2000)]


class Correction(ReportCommand):
    correction: Report
    reason: Annotated[str, Field(min_length=1, max_length=2000)]


class Void(ReportCommand):
    reason: Annotated[str, Field(min_length=1, max_length=2000)]


class Assignment(Command):
    business_date: date
    shift: Shift
    machine_id: Id
    worker_ids: list[Id] = Field(max_length=500)
    note: str = ""

    @field_validator("worker_ids")
    @classmethod
    def unique_workers(cls, values):
        if len(values) != len(set(values)):
            raise ValueError("排班人员不能重复")
        return values


class Reconcile(Command):
    job_id: Id
    product_id: Id | None = None
    process_version_id: Id | None = None
    confirmed_unit: Literal["piece", "board", "cycle", "unknown"]
    confirmed_piece_qty: Qty | None = None
    note: str
    ignore: bool = False


COMMAND_SCHEMAS = {"product": Product, "process": Process, "rate": Rate, "machine": Machine,
    "worker": Worker, "shift-template": ShiftTemplate, "assignment": Assignment,
    "report": Report, "confirm": ReportCommand, "quality": QualityCommand,
    "correction": Correction, "void": Void, "reconcile": Reconcile}
