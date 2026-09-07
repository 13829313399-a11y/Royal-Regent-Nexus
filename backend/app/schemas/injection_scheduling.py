from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt

FactoryId = Literal["huaxing", "huadeng", "huakang-a", "huakang-b"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Query(StrictModel):
    factory_id: FactoryId
    filter: dict | None = None
    search: dict | None = None
    sort: list[dict] = Field(default_factory=list, max_length=10)
    columns: list[str] = Field(default_factory=list, max_length=150)
    page_size: int = Field(100, ge=1, le=500)
    cursor: int | None = Field(None, ge=0)


class Write(StrictModel):
    factory_id: FactoryId
    base_revision: int = Field(ge=0)
    client_operation_id: str = Field(min_length=8, max_length=128)


class RecordWrite(Write):
    data: dict[str, Any] = Field(default_factory=dict)
    record_revision: int | None = Field(None, ge=1)


class BulkWrite(Write):
    rows: list[dict] = Field(max_length=1000)


class ScheduleScope(StrictModel):
    mode: Literal["UNSCHEDULED", "SELECTED", "ALL_UNSTARTED"] = "UNSCHEDULED"
    demand_ids: list[str] = Field(default_factory=list, max_length=10000)
    machine_ids: list[str] = Field(default_factory=list, max_length=1000)


class ScheduleWrite(Write):
    scope: ScheduleScope = Field(default_factory=ScheduleScope)
    save: bool = True


class MoveWrite(Write):
    run_id: str | None = None
    demand_id: str | None = None
    machine_id: str
    before_run_id: str | None = None
    allow_oversized: bool = False
    pinned: bool | None = None


class RunAction(Write):
    reason: str = Field("", max_length=2000)
    target_machine_id: str | None = None


class GroupWrite(Write):
    demand_ids: list[str] = Field(min_length=2, max_length=100)
    machine_id: str
    allow_oversized: bool = False


class RelocateWrite(Write):
    destination_factory_id: FactoryId
    available_at: str | None = None
    notes: str = Field("", max_length=2000)
    record_revision: int | None = Field(None, ge=1)


class ReportWrite(Write):
    run_id: str
    production_date: str
    shift_code: Literal["DAY", "NIGHT"]
    segment_key: str = Field("default", min_length=1, max_length=64)
    physical_shots: StrictInt = Field(ge=0, le=1000000000)
    good_units: dict[str, StrictInt] = Field(default_factory=dict)
    scrap_units: dict[str, StrictInt] = Field(default_factory=dict)
    report_revision: int = Field(0, ge=0)


class ImportApply(Write):
    matches: dict[str, str] = Field(default_factory=dict)
    skip_rows: list[int] = Field(default_factory=list)


class ExportQuery(Query):
    window_start: str
    window_days: int = Field(14, ge=1, le=366)
    editable_formulas: bool = False
