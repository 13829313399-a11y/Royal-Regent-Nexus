from typing import Annotated, Literal
from pydantic import Field, model_validator
from app.services.cutting_schemas import Strict, Command, Text
from app.services.cutting_planning_schemas import BusinessDate

Count = Annotated[int, Field(strict=True, ge=0, le=1000000000)]


class Pieces(Strict):
    code: Text
    good: Count = 0
    rejected: Count = 0
    scrap: Count = 0


class ProductionInput(Strict):
    task_id: Annotated[str, Field(pattern=r'^[A-Za-z0-9_-]{1,64}$')]
    plan_version: Annotated[int, Field(strict=True, ge=1)]
    day: BusinessDate
    mode: Literal['sets', 'parts']
    kind: Literal['daily', 'match', 'return', 'accept', 'handover']
    sets: Count = 0
    rejected: Count = 0
    scrap: Count = 0
    parts: Annotated[list[Pieces], Field(max_length=200)] = Field(default_factory=list)
    evidence: Annotated[str, Field(min_length=1, max_length=500)]
    exception_reason: Annotated[str, Field(max_length=500)] = ''

    @model_validator(mode='after')
    def shape(self):
        if len({p.code for p in self.parts}) != len(self.parts):
            raise ValueError('裁片部件不能重复')
        if self.kind == 'daily' and self.mode == 'parts':
            if self.sets or self.rejected or self.scrap or not self.parts:
                raise ValueError('裁片日报逐部件填片数，不同时填套数')
        elif self.parts:
            raise ValueError('只有裁片日报可填部件数量')
        if self.kind == 'match' and self.mode != 'parts':
            raise ValueError('直接报套任务不能再次核套')
        if self.kind != 'daily' and self.sets + (self.rejected if self.kind == 'accept' else 0) == 0:
            raise ValueError('本次业务数量必须大于零；日报允许明确填零')
        if self.kind not in {'daily', 'accept'} and (self.rejected or self.scrap):
            raise ValueError('该单据不接受不良或报废数')
        if self.kind == 'accept' and self.scrap:
            raise ValueError('外发验收使用合格及不合格套数，未判部分保留待验')
        return self


class ReportCommand(Command):
    document_id: Annotated[str, Field(pattern=r'^[A-Za-z0-9_-]{16,64}$')]
    entry: ProductionInput


class ReportDecision(Command):
    document_id: Annotated[str, Field(pattern=r'^[A-Za-z0-9_-]{16,64}$')]


class RecoverReport(Strict):
    action: Literal['save', 'post', 'void', 'review', 'discard']
    command: dict
