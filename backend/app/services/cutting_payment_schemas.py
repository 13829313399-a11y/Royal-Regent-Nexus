from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from pydantic import Field, StringConstraints, model_validator
from app.services.cutting_schemas import Command, Strict, Text
from app.services.cutting_settlement_schemas import Identity, Currency

Action = Literal['save', 'submit', 'return', 'confirm', 'reverse']
Money = Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=2, allow_inf_nan=False)]


class Allocation(Strict):
    settlement_id: Identity
    amount: Money


class Save(Command):
    document_id: Identity
    base_event_id: Identity | None = None
    day: Annotated[date, Field(ge=date(2000, 1, 1), le=date(2099, 12, 31))]
    voucher_no: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    method: Literal['bank', 'cash', 'cheque', 'other']
    evidence: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
    currency: Currency
    amount: Money
    basis_token: Text
    allocations: Annotated[list[Allocation], Field(min_length=1, max_length=1000)]
    replaces_document_id: Identity | None = None

    @model_validator(mode='after')
    def unique(self):
        if len({row.settlement_id for row in self.allocations}) != len(self.allocations):
            raise ValueError('同一结算单不能重复分配')
        if sum(row.amount for row in self.allocations) != self.amount:
            raise ValueError('付款金额必须全额分配，暂不支持预付款、超付或未分配余额')
        return self


class Decision(Command):
    document_id: Identity


class Recover(Strict):
    action: Action
    command: dict


def parse(action, body):
    return (Save if action == 'save' else Decision).model_validate(body)
