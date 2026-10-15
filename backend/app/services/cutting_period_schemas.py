from typing import Annotated, Literal
from pydantic import Field, model_validator
from app.services.cutting_schemas import Command, Strict, Text
from app.services.cutting_usage_schemas import Nonnegative

Month = Annotated[str, Field(pattern=r'^20\d{2}-(0[1-9]|1[0-2])$')]


class MonthAllocation(Strict):
    issue_id: Text
    completed_quantity: Nonnegative
    opening_completed_quantity: Nonnegative = 0


class PeriodSave(Command):
    month: Month
    basis_token: Text
    allocations: Annotated[list[MonthAllocation], Field(max_length=10000)]
    materials_complete: Annotated[bool, Field(strict=True)]
    public_material_pending: Annotated[bool, Field(strict=True)]
    opening_verified: Annotated[bool, Field(strict=True)]
    unrecorded_opening: Annotated[bool, Field(strict=True)]
    exceptions_reviewed: Annotated[bool, Field(strict=True)]

    @model_validator(mode='after')
    def unique_issues(self):
        if len({r.issue_id for r in self.allocations}) != len(self.allocations):
            raise ValueError('原实发不得重复归集')
        return self


class PeriodDecision(Command):
    month: Month


class RecoverPeriod(Strict):
    action: Literal['save', 'submit', 'return', 'lock', 'reopen']
    command: dict
