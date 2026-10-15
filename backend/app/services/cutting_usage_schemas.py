from decimal import Decimal
from typing import Annotated, Literal
from pydantic import Field, model_validator
from app.services.cutting_schemas import Command, Strict, Text
from app.services.cutting_planning_schemas import BusinessDate

Nonnegative = Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=6, allow_inf_nan=False)]


class UsageCommand(Command):
    issue_id: Text
    day: BusinessDate
    consumed_quantity: Nonnegative
    loss_quantity: Nonnegative
    counted_remaining: Nonnegative

    @model_validator(mode='after')
    def has_use(self):
        if self.consumed_quantity + self.loss_quantity <= 0:
            raise ValueError('本次实际耗用与损耗合计须大于0；仅盘点调整留待后续批次')
        return self


class UsageDecision(Command):
    document_id: Text
    day: BusinessDate


class UsageCorrection(UsageCommand):
    document_id: Text


class BatchCost(Command):
    issue_id: Text
    day: BusinessDate
    unit_cost: Nonnegative
    currency: Literal['CNY', 'HKD', 'USD']
    price_reference: Annotated[str, Field(min_length=4, max_length=500)]


class AllocationRow(Strict):
    issue_id: Text
    completed_quantity: Nonnegative


class CostAllocation(Command):
    issue_id: Text
    day: BusinessDate
    basis_token: Text
    allocations: Annotated[list[AllocationRow], Field(min_length=1, max_length=2000)]
    materials_complete: Annotated[bool, Field(strict=True)]
    public_material_pending: Annotated[bool, Field(strict=True)]

    @model_validator(mode='after')
    def unique_issues(self):
        if len({r.issue_id for r in self.allocations}) != len(self.allocations):
            raise ValueError('同一归集确认不能重复填写原实发')
        return self


class RecoverUsage(Strict):
    action: Literal['post', 'void', 'review', 'price', 'correct', 'allocate']
    command: dict
