"""Version 1 contracts: decimal strings, UTC instants and explicit A-factory scope."""
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, AfterValidator, BeforeValidator, field_validator, model_validator


def instant(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("时间必须包含时区")
    return value


Instant = Annotated[datetime, AfterValidator(instant)]
def decimal_input(value):
    if isinstance(value,float) or isinstance(value,bool):
        raise ValueError('精确小数须使用十进制字符串')
    return value


Rate = Annotated[Decimal, BeforeValidator(decimal_input), Field(ge=0, max_digits=18, decimal_places=6)]
Positive = Annotated[Decimal, BeforeValidator(decimal_input), Field(gt=0, max_digits=18, decimal_places=6)]
Qty = Annotated[int, Field(ge=0, le=2147483647, strict=True)]
Id = Annotated[str, Field(min_length=1, max_length=64)]
Evidence = Annotated[str, Field(min_length=2, max_length=2000)]
Currency = Literal["CNY", "HKD", "USD", "EUR"]


class DTO(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Command(DTO):
    factory_id: Literal["huakang-a"]
    operation_id: Annotated[str, Field(min_length=8, max_length=64)]
    expected_version: Qty = 0
    reason: str = Field(default="", max_length=2000)


class MachineCreate(Command):
    code: Id
    name: str = Field(min_length=1, max_length=128)
    model: str = Field(default="", max_length=128)
    width_mm: Positive | None = None
    height_mm: Positive | None = None
    ink_family: str = Field(default="unknown", max_length=64)
    maintenance: bool = False
    capability_evidence: str = Field(default="", max_length=2000)


class FixtureCreate(Command):
    code: Id
    revision: int = Field(ge=1)
    slots: int = Field(ge=1)
    width_mm: Positive
    height_mm: Positive


class ProductCreate(Command):
    code: Id
    name: str = Field(min_length=1, max_length=128)
    customer: str = Field(default="", max_length=128)


class ProcessCreate(Command):
    product_id: Id
    fixture_id: Id
    revision: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=128)
    ink_family: Id
    pieces_per_board: int = Field(ge=1)
    cycle_seconds: Positive | None = None
    width_mm: Positive
    height_mm: Positive
    faces: int = Field(default=1, ge=1)
    passes: int = Field(default=1, ge=1, le=20)


class FileConfirm(Command):
    first_article_evidence: Evidence


class FileUpload(Command):
    process_version_id: Id
    role: Literal["artwork", "preview", "production"]
    name: str
    sha256: str
    mime: str
    size_bytes: int


class PriceCreate(Command):
    product_id: Id
    basis: Literal["piece", "area"]
    rate: Rate
    currency: Currency
    rectangle_area: bool = False
    measured_area_m2: Positive | None = None
    evidence: Evidence

    @model_validator(mode="after")
    def area_basis(self):
        if self.basis == "area" and self.rectangle_area == (self.measured_area_m2 is not None):
            raise ValueError("面积计价必须且只能选择矩形面积或实测面积")
        return self


class WagePolicyCreate(Command):
    name: str = Field(min_length=1, max_length=128)
    basis: Literal["piece", "hour", "base_bonus"]
    rate: Rate
    bonus_rate: Rate = Decimal(0)
    currency: Currency
    evidence: Evidence


class DemandCreate(Command):
    code: Id
    product_id: Id
    source_type: Literal["manual", "order_line"] = "manual"
    source_line_id: str | None = Field(default=None, max_length=128)
    quantity: int = Field(gt=0)
    due_at: Instant
    priority: int = Field(default=0, ge=0, le=10)


class QuantityAction(Command):
    quantity: int = Field(gt=0)


class TaskCreate(Command):
    code: Id
    demand_id: Id
    process_version_id: Id
    file_version_id: Id
    price_policy_id: Id | None = None
    wage_policy_id: Id | None = None
    quantity: int = Field(gt=0)


class CompleteAccounting(Command):
    price_policy_id: Id | None = None
    wage_policy_id: Id | None = None


class ReferenceEfficiency(Command):
    name: str = Field(min_length=1,max_length=128)
    pieces_per_board: int = Field(gt=0)
    cycle_seconds: Positive
    available_seconds: Positive
    cost_amount: Rate | None = None
    currency: Currency
    evidence: Evidence


class RunCost(Command):
    run_id: Id
    business_date: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}$')
    cost_amount: Rate
    currency: Currency
    evidence: Evidence


class ScheduleItem(DTO):
    task_id: Id
    machine_id: Id
    start_at: Instant
    end_at: Instant
    task_version: Qty
    machine_version: Qty
    block_version: Qty = 0
    fixed: bool = False


class SchedulePreview(Command):
    blocks: list[ScheduleItem] = Field(min_length=1, max_length=100)


class ShiftCreate(Command):
    name: str = Field(min_length=1, max_length=128)
    business_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    start_at: Instant
    end_at: Instant
    breaks: list[tuple[Instant, Instant]] = Field(default_factory=list, max_length=10)


class ParticipationCreate(Command):
    shift_id: Id
    task_id: Id
    employee_id: Id
    employee_name: str = Field(min_length=1, max_length=128)
    start_at: Instant
    end_at: Instant
    role_coefficient: Positive = Decimal(1)


class ProductionConfirm(Command):
    task_id: Id
    batch_id: Id
    shift_id: Id
    pass_index: int = Field(ge=1)
    source_bucket: Literal["remaining", "rework"] = "remaining"
    processed: int = Field(gt=0)
    good: Qty
    rework: Qty
    scrap: Qty
    pending: Qty
    evidence: Evidence

    @model_validator(mode="after")
    def conservation(self):
        if self.processed != self.good + self.rework + self.scrap + self.pending:
            raise ValueError("加工数必须等于良品、返工、报废、待检之和")
        return self


class QualityResolve(Command):
    batch_id: Id
    shift_id: Id
    quantity: int = Field(gt=0)
    disposition: Literal["good", "rework", "scrap"]
    evidence: Evidence


class ReworkCreate(Command):
    batch_id: Id
    code: Id
    quantity: int = Field(gt=0)


class HandoverCreate(Command):
    batch_id: Id
    target: str = Field(min_length=1, max_length=128)
    receiver_id: str = Field(default="", max_length=64)
    quantity: int = Field(gt=0)
    business_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


class HandoverAction(QuantityAction):
    business_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    evidence: Evidence


class ShiftClose(Command):
    wip_handover: str = Field(default="", max_length=2000)


class InkSkuCreate(Command):
    code: Id
    supplier: str = Field(min_length=1, max_length=128)
    model: str = Field(min_length=1, max_length=128)
    ink_family: Id
    color: str = Field(min_length=1, max_length=32)
    capacity_ml: Positive


class InkMovement(Command):
    sku_id: Id
    lot: str = Field(default="unbatched", min_length=1, max_length=64)
    location: Id
    target_location: Id | None = None
    task_id: Id | None = None
    kind: Literal["receipt", "transfer", "consume", "return", "reverse", "stocktake_in", "stocktake_out"]
    quantity_ml: Positive
    cost_value: Rate | None = None
    currency: Currency
    reversal_of: Id | None = None
    business_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    evidence: Evidence


class ExpenseCreate(Command):
    category: Literal["direct", "department", "investment"]
    task_id: Id | None = None
    cost_amount: Rate
    currency: Currency
    business_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    allocation_end: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    evidence: Evidence


class WageConfirm(Command):
    task_id: Id
    shift_id: Id


class QuoteCalculate(DTO):
    factory_id: Literal["huakang-a"]
    available_seconds: Positive
    cycle_seconds: Positive
    pieces_per_board: int = Field(gt=0)
    cost_amount: Rate
    currency: Currency
    pricing_mode: Literal["markup", "margin"]
    ratio: Rate


class RunAllocation(DTO):
    task_id: Id
    batch_id: Id
    pass_index: int = Field(ge=1)
    slots: list[int] = Field(min_length=1, max_length=10000)
    full_boards: Qty
    tail_pieces: Qty
    share: Positive


class RunMatch(Command):
    allocations: list[RunAllocation] = Field(min_length=1, max_length=100)
    evidence: Evidence


class AgentCreate(Command):
    name: str = Field(min_length=1, max_length=128)


class SourceBind(Command):
    agent_id: Id
    machine_id: Id
    source_id: Id
    adapter_type: Literal["simulator", "generic_csv_log"]
    capabilities: dict = Field(default_factory=dict)


class Enroll(DTO):
    pairing_code: str = Field(min_length=24, max_length=128)
    enrollment_id: Id
    token: str = Field(min_length=43, max_length=128)


class AgentEvent(DTO):
    event_id: Id
    stream_id: Id
    sequence: int = Field(ge=1, le=2147483647)
    machine_id: Id
    source_id: Id
    binding_version: int = Field(ge=1, le=2147483647)
    kind: Literal["snapshot", "job_start", "job_progress", "job_complete", "job_failed", "job_cancelled"]
    observed_at: Instant
    adapter_type: Literal["simulator", "generic_csv_log"]
    adapter_version: str = Field(min_length=1, max_length=32)
    source_identity: dict
    evidence: dict
    payload: dict


class AgentBatch(DTO):
    schema_version: Literal[1]
    batch_id: Id
    events: list[dict] = Field(min_length=1, max_length=200)


class ExportCreate(Command):
    kind: Literal["tasks", "schedule", "production", "handovers", "ink", "wages", "daily", "monthly"]
    start_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    selected_ids: list[Id] = Field(default_factory=list, max_length=10000)


class ImportCommit(Command):
    pass


class BatchSplit(Command):
    quantity: Qty = Field(gt=0)


class BatchMerge(Command):
    other_batch_id: Id
    other_version: Qty


class HandoverCancel(Command):
    business_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
