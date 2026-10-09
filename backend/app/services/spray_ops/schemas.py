"""Typed public commands. Unknown input keys and floating point money are rejected."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, AfterValidator, model_validator


def decimal_input(value):
    if isinstance(value, (bool, float)):
        raise ValueError("数量和金额请使用十进制字符串")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError("请输入有效的十进制数量或金额") from error
    if not result.is_finite() or result.as_tuple().exponent < -6 or abs(result) >= Decimal("100000000000000"):
        raise ValueError("需要有限且最多六位小数的十进制数")
    return result


Amount = Annotated[Decimal, BeforeValidator(decimal_input)]
Qty = Annotated[Amount, Field(ge=0)]
Positive = Annotated[Amount, Field(gt=0)]
Text = Annotated[str, Field(min_length=1, max_length=255)]
Id = Annotated[str, Field(min_length=1, max_length=64)]
Factory = Literal["huaxing", "huadeng", "huakang-a", "huakang-b"]


def aware(value):
    if value.tzinfo is None:
        raise ValueError("时间必须包含时区")
    return value


Instant = Annotated[datetime, AfterValidator(aware)]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Command(Model):
    factory_id: Factory
    operation_id: Id
    expected_version: int = Field(ge=0)


class DatedCommand(Command):
    business_date: date


class CapabilityInput(Model):
    capability: Text
    hourly_capacity: Positive | None = None
    evidence: str = Field(default="", max_length=2000)


class CalendarInput(Model):
    start_at: Instant
    end_at: Instant
    kind: Literal["available", "maintenance", "absence"] = "available"
    reason: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def interval(self):
        if self.end_at <= self.start_at:
            raise ValueError("结束时间必须晚于开始时间")
        return self


class ResourceCreate(Command):
    code: Text
    name: Text
    kind: Literal["manual", "automatic", "pad", "tool", "crew"]
    capacity: int = Field(default=1, ge=1, le=1000)
    capabilities: list[CapabilityInput] = Field(default_factory=list, max_length=100)
    calendar: list[CalendarInput] = Field(default_factory=list, max_length=500)


class CalendarSet(Command):
    calendar: list[CalendarInput] = Field(max_length=500)


class StepInput(Model):
    code: Id
    name: Text
    capability: Text
    predecessors: list[Id] = Field(default_factory=list, max_length=100)
    tool_id: Id | None = None
    crew_id: Id | None = None
    input_unit: Text = "件"
    output_unit: Text = "件"
    output_ratio: Positive = Decimal(1)
    transfer_min: Positive = Decimal(1)
    drying_minutes: int = Field(default=0, ge=0, le=525600)
    prep_required: bool = True


class RouteCreate(Command):
    code: Text
    label: Text
    revision: int = Field(ge=1)
    confirmed: bool = False
    evidence: str = Field(default="", max_length=4000)
    steps: list[StepInput] = Field(min_length=1, max_length=100)


class LineInput(Model):
    item_no: Text
    part: Text
    color: Text
    quantity: Positive
    unit: Text = "件"
    due_date: date
    expected_arrival: date | None = None
    route_id: Id | None = None
    priority: int = Field(default=0, ge=0, le=100)
    split_allowed: bool = True
    commercial_price: Qty | None = None
    currency: Literal["CNY", "HKD", "USD"] = "CNY"
    price_evidence: str = Field(default="", max_length=2000)


class DemandCreate(DatedCommand):
    document_no: Text
    counterparty: Text
    source_factory: Factory | None = None
    source_type: Literal["manual", "excel", "reference"] = "manual"
    source_ref: str = Field(default="", max_length=255)
    note: str = Field(default="", max_length=4000)
    confirm: bool = True
    lines: list[LineInput] = Field(min_length=1, max_length=200)


class DemandAmend(DatedCommand):
    line_id: Id
    quantity: Positive
    due_date: date
    priority: int = Field(ge=0, le=100)
    reason: Text
    route_id: Id | None = None


class BatchCreate(DatedCommand):
    document_no: Text
    line_id: Id | None = None
    item_no: Text
    part: Text
    quantity: Positive
    accepted: Qty
    held: Qty = Decimal(0)
    rejected: Qty = Decimal(0)
    unit: Text = "件"
    source_ref: str = Field(default="", max_length=255)

    @model_validator(mode="after")
    def quantities(self):
        if self.accepted + self.held + self.rejected != self.quantity:
            raise ValueError("来料总数必须等于合格、待判和拒收之和")
        return self


class BatchMatch(Command):
    line_id: Id


class PreparationSet(Command):
    batch_id: Id
    step_id: Id
    ready_at: Instant
    expires_at: Instant | None = None
    evidence: Text


class TaskAllocationInput(Model):
    stock_id: Id
    quantity: Positive


class TaskInput(Model):
    step_id: Id
    resource_id: Id
    start_at: Instant
    end_at: Instant
    allocations: list[TaskAllocationInput] = Field(min_length=1, max_length=200)
    note: str = Field(default="", max_length=2000)


class PlanPreview(Command):
    label: Text = "排期方案"
    start_at: Instant
    end_at: Instant
    line_ids: list[Id] = Field(default_factory=list, max_length=500)
    replace_task_ids: list[Id] = Field(default_factory=list, max_length=500)
    tasks: list[TaskInput] | None = Field(default=None, max_length=500)


class PlanPublish(Command):
    base_revision: int = Field(ge=0)


class TaskStart(DatedCommand):
    actual_start: Instant


class ForecastCreate(Command):
    line_id: Id
    step_id: Id
    resource_id: Id
    start_at: Instant
    end_at: Instant
    expected_ready_at: Instant
    quantity: Positive
    condition: Text


class ForecastConvert(Command):
    allocations: list[TaskAllocationInput] = Field(min_length=1, max_length=200)


class Quantities(Model):
    processed: Qty
    good: Qty
    hold: Qty = Decimal(0)
    scrap: Qty = Decimal(0)
    normal: Qty
    overtime: Qty = Decimal(0)

    @model_validator(mode="after")
    def conservation(self):
        if self.processed != self.good + self.hold + self.scrap or self.processed != self.normal + self.overtime:
            raise ValueError("加工数=合格+待判+报废=正班+加班")
        return self


class ReportAllocationInput(Quantities):
    task_allocation_id: Id


class LaborInput(Model):
    employee_id: Id
    personal_quantity: Qty | None = None
    hours: Qty
    overtime_hours: Qty = Decimal(0)
    weight: Positive = Decimal(1)
    nonproductive_hours: Qty = Decimal(0)
    reason: str = Field(default="", max_length=2000)


class ReportRowInput(Quantities):
    task_id: Id
    allocations: list[ReportAllocationInput] = Field(min_length=1, max_length=200)
    labor: list[LaborInput] = Field(default_factory=list, max_length=200)
    reason: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def allocation_sums(self):
        for field in Quantities.model_fields:
            if sum(getattr(a, field) for a in self.allocations) != getattr(self, field):
                raise ValueError(f"分摊 {field} 列合计与日报行不一致")
        if (self.hold or self.scrap or self.processed == 0) and not self.reason:
            raise ValueError("待判、报废、无产值工时需填写原因")
        if len({a.task_allocation_id for a in self.allocations}) != len(self.allocations):
            raise ValueError("重复的订单分摊")
        if len({a.employee_id for a in self.labor}) != len(self.labor):
            raise ValueError("同一日报行不能重复员工")
        return self


class ReportCreate(DatedCommand):
    document_no: Text
    shift: Text
    source_ref: str = Field(default="", max_length=255)
    confirm: bool = True
    rows: list[ReportRowInput] = Field(min_length=1, max_length=200)


class ReasonCommand(DatedCommand):
    reason: Text


class ReportAmend(ReportCreate):
    reason: Text
    confirm: bool = False


class ReportLabor(ReasonCommand):
    row_id: Id
    labor: list[LaborInput] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def unique_employees(self):
        if len({row.employee_id for row in self.labor}) != len(self.labor):
            raise ValueError("员工不能重复")
        return self


class QualityDisposition(DatedCommand):
    good: Qty = Decimal(0)
    rework: Qty = Decimal(0)
    scrap: Qty = Decimal(0)
    reason: Text
    rework_step_id: Id | None = None


class EmployeeCreate(Command):
    code: Text
    name: Text


class DeliveryLineInput(Model):
    stock_id: Id
    quantity: Positive


class DeliveryCreate(DatedCommand):
    document_no: Text
    counterparty: Text
    warehouse_ref: str = Field(default="", max_length=128)
    dispatch: bool = True
    lines: list[DeliveryLineInput] = Field(min_length=1, max_length=200)


class AcceptanceLine(Model):
    delivery_line_id: Id
    accepted: Qty = Decimal(0)
    rejected: Qty = Decimal(0)
    reason: str = Field(default="", max_length=2000)


class DeliveryAccept(DatedCommand):
    lines: list[AcceptanceLine] = Field(min_length=1, max_length=200)


class ReturnCreate(DatedCommand):
    delivery_line_id: Id
    quantity: Positive
    reason: Text


class ContainerCreate(DatedCommand):
    counterparty: Text
    item: Text
    owner: Literal["ours", "theirs"]
    direction: Literal["in", "out"]
    recoverable: bool = True
    quantity: Positive
    delivery_id: Id | None = None
    source_ref: str = Field(default="", max_length=255)


class MaterialCreate(Command):
    code: Text
    name: Text
    unit: Text


class PurchaseLineInput(Model):
    material_id: Id
    quantity: Positive
    unit: Text
    price: Qty | None = None
    due_date: date


class PurchaseCreate(DatedCommand):
    document_no: Text
    supplier: Text
    currency: Literal["CNY", "HKD", "USD"] = "CNY"
    tax_basis: Text
    source_ref: str = Field(default="", max_length=255)
    lines: list[PurchaseLineInput] = Field(min_length=1, max_length=200)


class PurchaseCancel(DatedCommand):
    line_id: Id
    quantity: Positive
    reason: Text


class MaterialReceiptLine(Model):
    purchase_line_id: Id
    quantity: Positive
    unit: Text
    conversion_rule_id: Id | None = None


class MaterialReceiptCreate(DatedCommand):
    document_no: Text
    supplier: Text
    source_ref: str = Field(default="", max_length=255)
    lines: list[MaterialReceiptLine] = Field(min_length=1, max_length=200)


class MaterialMove(DatedCommand):
    kind: Literal["issue", "return", "consume"]
    quantity: Positive
    line_id: Id | None = None
    issue_id: Id | None = None
    reason: Text


class SavingCreate(DatedCommand):
    purchase_line_id: Id | None = None
    quantity: Positive
    old_price: Qty
    new_price: Qty
    currency: Literal["CNY", "HKD", "USD"]
    source_ref: Text


class UnitParameters(Model):
    from_unit: Text
    to_unit: Text
    factor: Positive


class ExchangeParameters(Model):
    from_currency: Literal["CNY", "HKD", "USD"]
    to_currency: Literal["CNY", "HKD", "USD"]
    factor: Positive


class PriceParameters(Model):
    price: Qty
    currency: Literal["CNY", "HKD", "USD"]


class WageParameters(Model):
    method: Literal["personal_piece", "team_piece", "hourly", "fixed_shift", "historical_normalized"]
    basis: Literal["processed", "good"]
    rate: Qty
    overtime_rate: Qty | None = None
    nonproductive_rate: Qty | None = None
    currency: Literal["CNY", "HKD", "USD"]
    exchange_rule_id: Id | None = None
    daily_guarantee: Qty = Decimal(0)
    reference_hours: Positive | None = None
    paid_hours: Positive | None = None


class RuleCreate(Command):
    code: Text
    label: Text
    kind: Literal["wage", "unit", "exchange", "operation_price"]
    revision: int = Field(ge=1)
    effective_from: date
    effective_until: date | None = None
    parameters: dict
    evidence: Text
    material_id: Id | None = None
    step_id: Id | None = None

    @model_validator(mode="after")
    def validate_parameters(self):
        cls = {"wage": WageParameters, "unit": UnitParameters, "exchange": ExchangeParameters, "operation_price": PriceParameters}[self.kind]
        self.parameters = cls.model_validate(self.parameters).model_dump(mode="json")
        if self.effective_until and self.effective_until < self.effective_from:
            raise ValueError("规则有效期错误")
        if self.kind == "unit" and not self.material_id:
            raise ValueError("单位换算必须限定物料 SKU")
        if self.kind == "operation_price" and not self.step_id:
            raise ValueError("工序价格必须指定工艺工序")
        return self


class PayrollAdjustment(Model):
    employee_id: Id
    subsidy: Qty = Decimal(0)
    adjustment: Amount = Decimal(0)
    evidence: Text


class PayrollTrial(DatedCommand):
    document_no: Text
    rule_id: Id
    row_rules: dict[str, Id] = Field(default_factory=dict, max_length=1000)
    adjustments: list[PayrollAdjustment] = Field(default_factory=list, max_length=500)


class ExpenseCreate(DatedCommand):
    document_no: Text
    category: Text
    kind: Literal["expense", "recovery", "investment", "memo"]
    amount: Qty
    currency: Literal["CNY", "HKD", "USD"]
    included: bool | None = None
    line_id: Id | None = None
    evidence: Text


class ExpenseConfirm(DatedCommand):
    included: bool
    reason: Text


class MaterialCostConfirm(DatedCommand):
    unit_cost: Qty
    evidence: Text


class ValueReport(DatedCommand):
    report_id: Id
    rule_id: Id


class SettlementSelection(Model):
    delivery_line_id: Id
    quantity: Positive


class SettlementCreate(DatedCommand):
    document_no: Text
    counterparty: Text
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    currency: Literal["CNY", "HKD", "USD"]
    rule_id: Id | None = None
    lines: list[SettlementSelection] = Field(min_length=1, max_length=500)


class CreditCreate(DatedCommand):
    return_id: Id
    settlement_line_id: Id
    quantity: Positive
    reason: Text


class PriceSet(DatedCommand):
    price: Qty
    evidence: Text


class PeriodChange(DatedCommand):
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    reason: Text
    fingerprint: str = Field(min_length=64, max_length=64)


class ImportUpload(Command):
    profile: str = Field(max_length=64)
    source_sha256: str = ""
    filename: str = ""


class HistoryPolicy(Command):
    mode: Literal["opening", "replay"]
    cutoff: date
    evidence: Text


class OpeningCreate(DatedCommand):
    document_no: Text
    line_id: Id
    quantity: Positive
    unit: Text
    state: Literal["white", "wip", "finished"]
    completed_step_ids: list[Id] = Field(default_factory=list, max_length=200)
    evidence: Text
    source_ref: str = Field(default="", max_length=255)


class ImportDocument(Model):
    document_key: Text
    sheet: Text
    coordinates: list[Text] = Field(min_length=1, max_length=2000)
    target: Literal["demand", "batch", "delivery", "return", "container", "report", "expense", "purchase", "material_receipt", "saving", "settlement", "reference", "opening"]
    values: dict
    reason: Text
    primary_source_confirmation: Text
    mode: Literal["current", "historical_reference", "opening", "replay"] = "current"


class ImportPreview(Command):
    source_id: Id
    profile: str = Field(max_length=64)
    business_month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    mappings: dict = Field(default_factory=dict)
    documents: list[ImportDocument] = Field(default_factory=list, max_length=500)


class ImportConfirm(Command):
    fingerprint: str = Field(min_length=64, max_length=64)
    document_key: Text


class ExportCreate(Command):
    kind: Literal["plan", "daily", "stock", "purchase", "material", "delivery", "settlement", "request", "operating"]
    from_date: date | None = None
    to_date: date | None = None
    entity_id: Id | None = None
    month: str = Field(default="", pattern=r"^(|\d{4}-(0[1-9]|1[0-2]))$")
    currency: Literal["CNY", "HKD", "USD"] = "CNY"
    base_revision: int = Field(ge=0)
