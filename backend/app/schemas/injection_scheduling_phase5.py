from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.injection_scheduling_execution import (
    MaterialReadinessStatus,
    PriorityCode,
)


class StrictWriteModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InjectionSchedulingErpOrderItem(StrictWriteModel):
    external_id: str = Field(min_length=1, max_length=128)
    external_version: str = Field(min_length=1, max_length=128)
    order_no: str = Field(min_length=1, max_length=128)
    item_no: str = Field(default="", max_length=128)
    product_name: str = Field(default="", max_length=255)
    mold_id: str | None = Field(default=None, max_length=96)
    order_quantity: float = Field(gt=0)
    source_completed_quantity: float = Field(default=0, ge=0)
    delivery_start_date: date | None = None
    delivery_due_date: date | None = None
    priority_code: PriorityCode = "NORMAL"
    material_readiness_status: MaterialReadinessStatus = "unknown"
    warehouse_text: str = Field(default="", max_length=255)
    remark: str = Field(default="", max_length=2000)
    occurred_at: datetime
    lineage: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "external_id",
        "external_version",
        "order_no",
        "item_no",
        "product_name",
        "warehouse_text",
        "remark",
    )
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("mold_id")
    @classmethod
    def normalize_mold_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("occurred_at 必须包含时区")
        return value

    @model_validator(mode="after")
    def validate_business_values(self):
        if self.source_completed_quantity > self.order_quantity:
            raise ValueError("ERP 已完成数不能大于订单数量")
        if (
            self.delivery_start_date is not None
            and self.delivery_due_date is not None
            and self.delivery_start_date > self.delivery_due_date
        ):
            raise ValueError("开始交货期不能晚于交货完成期")
        return self


class InjectionSchedulingErpSyncBatch(StrictWriteModel):
    factory_id: str
    source_key: str = Field(min_length=1, max_length=96)
    cursor: str = Field(min_length=1, max_length=255)
    orders: list[InjectionSchedulingErpOrderItem] = Field(min_length=1, max_length=500)

    @field_validator("factory_id", "source_key", "cursor")
    @classmethod
    def strip_batch_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("orders")
    @classmethod
    def require_unique_events(cls, value: list[InjectionSchedulingErpOrderItem]):
        event_keys = [(item.external_id, item.external_version) for item in value]
        if len(event_keys) != len(set(event_keys)):
            raise ValueError("同一 ERP 批次不能包含重复的订单版本")
        return value


class InjectionSchedulingIntegrationCursorOut(BaseModel):
    source_type: Literal["ERP", "DEVICE"]
    source_key: str
    cursor: str
    status: Literal["ACTIVE", "ERROR", "NOT_CONFIGURED"]
    last_received_at: str
    last_success_at: str
    last_error: str
    event_count: int
    revision: int


class InjectionSchedulingErpSyncResult(BaseModel):
    factory_id: str
    source_key: str
    cursor: str
    created_count: int
    updated_count: int
    skipped_count: int
    order_ids: list[str]
    audit_sequence: int
    integration: InjectionSchedulingIntegrationCursorOut


class InjectionSchedulingDeviceProductionEvent(StrictWriteModel):
    external_event_id: str = Field(min_length=1, max_length=128)
    machine_code: str = Field(min_length=1, max_length=64)
    task_id: str | None = Field(default=None, max_length=96)
    occurred_at: datetime
    cumulative_quantity: float = Field(ge=0)
    cycle_seconds: float | None = Field(default=None, gt=0, le=86400)
    units_per_cycle: float = Field(default=1, gt=0, le=10000)
    downtime_minutes: int = Field(default=0, ge=0, le=1440)
    status: Literal["RUNNING", "BLOCKED", "COMPLETED"] = "RUNNING"
    exception_code: str = Field(default="", max_length=64)
    exception_detail: str = Field(default="", max_length=2000)

    @field_validator(
        "external_event_id",
        "machine_code",
        "exception_code",
        "exception_detail",
    )
    @classmethod
    def strip_event_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("task_id")
    @classmethod
    def normalize_task_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @field_validator("occurred_at")
    @classmethod
    def require_event_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("occurred_at 必须包含时区")
        return value


class InjectionSchedulingDeviceEventBatch(StrictWriteModel):
    factory_id: str
    source_key: str = Field(min_length=1, max_length=96)
    cursor: str = Field(min_length=1, max_length=255)
    events: list[InjectionSchedulingDeviceProductionEvent] = Field(
        min_length=1, max_length=500
    )

    @field_validator("factory_id", "source_key", "cursor")
    @classmethod
    def strip_batch_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("events")
    @classmethod
    def require_unique_event_ids(
        cls, value: list[InjectionSchedulingDeviceProductionEvent]
    ):
        event_ids = [item.external_event_id for item in value]
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("同一设备批次不能包含重复事件 ID")
        return value


class InjectionSchedulingDeviceEventResult(BaseModel):
    external_event_id: str
    task_id: str
    order_id: str
    machine_id: str
    normalized_increment_quantity: float
    observation_created: bool
    replayed: bool


class InjectionSchedulingDeviceBatchResult(BaseModel):
    factory_id: str
    source_key: str
    cursor: str
    applied_count: int
    skipped_count: int
    calibrated_mold_count: int
    events: list[InjectionSchedulingDeviceEventResult]
    integration: InjectionSchedulingIntegrationCursorOut


class InjectionSchedulingCalibrationRequest(StrictWriteModel):
    factory_id: str
    mold_ids: list[str] = Field(default_factory=list, max_length=500)
    minimum_sample_count: int = Field(default=3, ge=3, le=100)

    @field_validator("factory_id")
    @classmethod
    def strip_factory(cls, value: str) -> str:
        return value.strip()

    @field_validator("mold_ids")
    @classmethod
    def normalize_mold_ids(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value if item.strip()]
        if len(normalized) != len(set(normalized)):
            raise ValueError("mold_ids 不能重复")
        return normalized


class InjectionSchedulingSpeedModelOut(BaseModel):
    id: str
    factory_id: str
    mold_id: str
    mold_no: str
    sample_count: int
    calibrated_cycle_seconds: float
    units_per_cycle: float
    calibrated_units_per_hour: float
    confidence: float
    status: Literal["ACTIVE", "INSUFFICIENT_DATA"]
    source_window_start: str
    source_window_end: str
    last_observed_at: str
    revision: int
    updated_at: str


class InjectionSchedulingCalibrationResult(BaseModel):
    factory_id: str
    calibrated_count: int
    insufficient_count: int
    models: list[InjectionSchedulingSpeedModelOut]
    audit_sequence: int


class InjectionSchedulingMetricOut(BaseModel):
    value: float
    numerator: float
    denominator: float
    unit: str
    sample_count: int
    formula: str


class InjectionSchedulingAnalyticsOverviewOut(BaseModel):
    factory_id: str
    date_from: str
    date_to: str
    generated_at: str
    plan_accuracy: InjectionSchedulingMetricOut
    mold_change_count: InjectionSchedulingMetricOut
    overdue_rate: InjectionSchedulingMetricOut
    machine_utilization: InjectionSchedulingMetricOut
    integration_statuses: list[InjectionSchedulingIntegrationCursorOut]
    speed_models: list[InjectionSchedulingSpeedModelOut]
    device_interface_configured: bool
    notes: list[str]
