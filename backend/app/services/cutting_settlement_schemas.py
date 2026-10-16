from decimal import Decimal
from typing import Annotated, Literal
from pydantic import Field, StringConstraints, model_validator
from app.services.cutting_schemas import Command, Strict, Text
from app.services.cutting_period_schemas import Month

Identity = Annotated[str, StringConstraints(pattern=r'^[A-Za-z0-9_-]{16,64}$')]
Currency = Literal['CNY', 'HKD', 'USD']
Action = Literal['price', 'save', 'submit', 'return', 'confirm', 'reopen']


class Price(Command):
    line_id: Text
    task_id: Text
    context_token: Text
    unit_price: Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=6, allow_inf_nan=False)]
    currency: Currency
    evidence: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class Selection(Strict):
    line_id: Text
    acceptance_id: Text
    sets: Annotated[int, Field(strict=True, ge=1, le=1000000000)]


class Save(Command):
    document_id: Identity
    month: Month
    basis_token: Text
    selections: Annotated[list[Selection], Field(min_length=1, max_length=1000)]
    vendor_evidence: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] = ''
    vendor_confirmation_token: str = Field(default='', max_length=64)

    @model_validator(mode='after')
    def unique(self):
        if len({(s.line_id, s.acceptance_id) for s in self.selections}) != len(self.selections):
            raise ValueError('验收明细不能重复选择')
        return self


class Decision(Command):
    document_id: Identity


class Recover(Strict):
    action: Action
    command: dict


def parse(action, body):
    return (Price if action == 'price' else Save if action == 'save' else Decision).model_validate(body)
