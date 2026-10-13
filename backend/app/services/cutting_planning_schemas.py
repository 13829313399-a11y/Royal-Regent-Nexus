"""Versioned manual preplanning; no stock, output or cost postings."""
from datetime import date
from typing import Annotated, Literal
from pydantic import Field, PrivateAttr, StringConstraints, model_validator
from app.services.cutting_schemas import Strict, Command, Text

BusinessDate = Annotated[date, Field(ge=date(2000, 1, 1), le=date(2100, 12, 31))]
Sets = Annotated[int, Field(strict=True, ge=1, le=1000000000)]


class DailyPlan(Strict):
    day: BusinessDate
    sets: Sets


class MaterialDate(Strict):
    row: Annotated[int, Field(strict=True, ge=0, le=299)]
    expected_date: BusinessDate | None = None


class PlanTask(Strict):
    task_id: Annotated[str, Field(pattern=r'^[A-Za-z0-9_-]{1,64}$')]
    name: Text
    resource_id: Text
    resource_version: Annotated[int, Field(strict=True, ge=1)]
    target_sets: Sets
    date_basis: Literal['estimated', 'actual'] = 'estimated'
    preparation_workdays: Annotated[int, Field(strict=True, ge=0, le=365)] = 3
    resource_change_basis: Annotated[str, Field(max_length=500)] = ''
    materials: Annotated[list[MaterialDate], Field(max_length=300)]
    readiness_basis: Annotated[str, Field(max_length=500)] = ''
    actual_issue_date: BusinessDate | None = None
    actual_issue_reference: Annotated[str, Field(max_length=500)] = ''
    prerequisite_required: Annotated[bool, Field(strict=True)] = False
    prerequisite_change_reason: Annotated[str, Field(max_length=500)] = ''
    prerequisite_date: BusinessDate | None = None
    prerequisite_basis: Annotated[str, Field(max_length=500)] = ''
    actual_prerequisite_date: BusinessDate | None = None
    actual_prerequisite_reference: Annotated[str, Field(max_length=500)] = ''
    days: Annotated[list[DailyPlan], Field(max_length=730)]

    @model_validator(mode='after')
    def unique_rows(self):
        if len({r.row for r in self.materials}) != len(self.materials):
            raise ValueError('同一任务的物料行不可重复')
        if len({d.day for d in self.days}) != len(self.days):
            raise ValueError('同一任务的计划日期不可重复')
        if sum(d.sets for d in self.days) > self.target_sets:
            raise ValueError('日计划合计不得超过任务目标套数')
        if self.prerequisite_date or self.actual_prerequisite_date:
            self.prerequisite_required = True
        if self.prerequisite_date and not self.prerequisite_basis:
            raise ValueError('前置工序预计日期必须填写依据')
        if self.actual_issue_date and not self.actual_issue_reference:
            raise ValueError('实际领料日期须填写领料单号或凭据')
        if self.actual_issue_reference and not self.actual_issue_date:
            raise ValueError('填写领料凭据时须同时填写实际领料日期')
        if bool(self.actual_prerequisite_date) != bool(self.actual_prerequisite_reference):
            raise ValueError('前置工序实际就绪日期与凭据须同时填写')
        return self


class SavePlan(Command):
    reason: Annotated[str, Field(max_length=500)] = ''
    _reason_entered: bool = PrivateAttr(default=False)
    _note_normalized: bool = PrivateAttr(default=False)
    tasks: Annotated[list[PlanTask], Field(min_length=1, max_length=100)]
    removed_task_reasons: Annotated[dict[str, Annotated[str, StringConstraints(strip_whitespace=True, min_length=4, max_length=500)]], Field(max_length=100)] = Field(default_factory=dict)

    @model_validator(mode='after')
    def unique_tasks(self):
        if not self._note_normalized:
            self._reason_entered = bool(self.reason.strip())
            self._note_normalized = True
        self.reason = self.reason.strip() or '保存生产计划'
        if len({t.task_id for t in self.tasks}) != len(self.tasks):
            raise ValueError('执行任务编号不能重复')
        return self


class PublishPlan(Command):
    reason: Annotated[str, Field(max_length=500)] = ''
    _reason_entered: bool = PrivateAttr(default=False)
    _note_normalized: bool = PrivateAttr(default=False)
    draft_version: Annotated[int, Field(strict=True, ge=1)]

    @model_validator(mode='after')
    def operation_note(self):
        if not self._note_normalized:
            self._reason_entered = bool(self.reason.strip())
            self._note_normalized = True
        self.reason = self.reason.strip() or '发布生产计划'
        return self
