from decimal import Decimal
from datetime import date
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Code = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Quantity = Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=6, allow_inf_nan=False)]
Kind = Literal['material', 'resource', 'bom']


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Material(Strict):
    name: Text
    category: Literal['fabric', 'accessory']
    unit: Text
    specification: Annotated[str, Field(max_length=200)] = ''
    color: Annotated[str, Field(max_length=120)] = ''
    source_reference: Text


class CalendarException(Strict):
    day: Annotated[date, Field(ge=date(2000, 1, 1), le=date(2100, 12, 31))]
    working: Annotated[bool, Field(strict=True)]
    reason: Annotated[str, StringConstraints(min_length=1, max_length=200)]


class WorkCalendar(Strict):
    weekdays: Annotated[list[Annotated[int, Field(strict=True, ge=1, le=7)]], Field(min_length=1, max_length=7)]
    exceptions: Annotated[list[CalendarException], Field(max_length=730)] = []
    basis: Annotated[str, StringConstraints(min_length=1, max_length=500)]

    @model_validator(mode='after')
    def unique_days(self):
        if len(set(self.weekdays)) != len(self.weekdays) or len({e.day for e in self.exceptions}) != len(self.exceptions):
            raise ValueError('工作周及日历例外日期不可重复')
        return self


class Resource(Strict):
    name: Text
    execution: Literal['internal', 'outsourced']
    process: Literal['cutting'] = 'cutting'
    calendar: WorkCalendar | None = None
    preparation_workdays: Annotated[int, Field(strict=True, ge=0, le=365)] = 3
    contact: Annotated[str, Field(max_length=120)] = ''
    source_reference: Text


class Part(Strict):
    code: Code
    name: Text
    pieces_per_set: Annotated[int, Field(strict=True, ge=1, le=100000)]


class Requirement(Strict):
    material_id: Text
    material_version: Annotated[int, Field(strict=True, ge=1)]
    part_codes: Annotated[list[Code], Field(min_length=1, max_length=200)]
    quantity_per_set: Quantity
    unit: Text
    required_for_cutting: bool
    stage: Text
    note: Annotated[str, Field(max_length=300)] = ''


class Bom(Strict):
    name: Text
    item_no: Code
    style: Text
    color: Text
    source_reference: Text
    parts: Annotated[list[Part], Field(min_length=1, max_length=200)]
    requirements: Annotated[list[Requirement], Field(min_length=1, max_length=300)]

    @model_validator(mode='after')
    def consistent_parts(self):
        codes = [p.code for p in self.parts]
        if len(set(codes)) != len(codes):
            raise ValueError('部件编码不能重复')
        for row in self.requirements:
            if len(set(row.part_codes)) != len(row.part_codes) or not set(row.part_codes) <= set(codes):
                raise ValueError('物料适用部件必须来自当前 BOM，且不能重复')
        return self


class Command(Strict):
    factory_id: Literal['huakang-c']
    operation_id: Annotated[str, StringConstraints(pattern=r'^[A-Za-z0-9_-]{16,64}$')]
    expected_version: Annotated[int, Field(strict=True, ge=0)]
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class Save(Command):
    kind: Kind
    code: Code
    data: dict


class StateChange(Command):
    status: Literal['active', 'inactive', 'published']


DATA_MODELS = {'material': Material, 'resource': Resource, 'bom': Bom}


class ReceiveOrder(Command):
    dispatch_id: Text


class BindBom(Command):
    bom_id: Text
    bom_version: Annotated[int, Field(strict=True, ge=1)]
    target_sets: Annotated[int, Field(strict=True, ge=1, le=1000000000)]
    quantity_basis: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    bom_match_basis: Annotated[str, StringConstraints(max_length=500)] = ''


class DemandLine(Strict):
    row: Annotated[int, Field(strict=True, ge=0, le=299)]
    quantity: Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=6, allow_inf_nan=False)]
    purchase_mode: Literal['purchase', 'no_purchase'] = 'purchase'
    no_purchase_reason: Annotated[str, StringConstraints(max_length=500)] = ''

    @model_validator(mode='after')
    def purchase_basis(self):
        if self.purchase_mode == 'purchase' and self.quantity <= 0:
            raise ValueError('需要采购时数量必须大于零')
        if self.purchase_mode == 'no_purchase' and (self.quantity != 0 or not self.no_purchase_reason):
            raise ValueError('本次不采购必须数量为零并填写原因')
        return self


class SubmitRequisition(Command):
    lines: Annotated[list[DemandLine], Field(min_length=1, max_length=300)]


class EtaBatch(Strict):
    row: Annotated[int, Field(strict=True, ge=0, le=299)]
    quantity: Quantity
    expected_date: date
    supplier: Text
    purchase_reference: Text


class ReplyEta(Command):
    requisition_version: Annotated[int, Field(strict=True, ge=1)]
    batches: Annotated[list[EtaBatch], Field(max_length=1000)]


class WithdrawRequisition(Command):
    requisition_version: Annotated[int, Field(strict=True, ge=1)]


class ReconcileRequisition(WithdrawRequisition):
    disposition: Literal['not_ordered', 'cancelled_or_reallocated']
    evidence: Annotated[str, StringConstraints(min_length=4, max_length=500)]
    all_handled: Annotated[bool, Field(strict=True)]

    @model_validator(mode='after')
    def entire_requisition_handled(self):
        if not self.all_handled:
            raise ValueError('只有整张旧需求均已核对处置，才可解除等待')
        return self


OrderAction = Literal['receive', 'bom', 'requisition', 'eta', 'withdraw', 'reconcile', 'plan', 'plan-publish']
WorkflowStatus = Literal['awaiting_receipt', 'cancelled_receipt', 'cancelled', 'reconciliation',
                         'awaiting_bom', 'awaiting_submission', 'awaiting_reply', 'partial_reply', 'complete_reply', 'no_purchase']


class RecoverOperation(Strict):
    action: OrderAction
    command: dict


class OperationIdentity(Strict):
    factory_id: Literal['huakang-c']
    operation_id: Annotated[str, StringConstraints(pattern=r'^[A-Za-z0-9_-]{16,64}$')]
