from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


Material = Literal["screenshot", "steps", "expected_result", "original_file", "order_reference"]
Status = Literal["submitted", "needs_info", "in_progress", "awaiting_verification", "resolved"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class FeedbackContext(StrictModel):
    page: str = Field(default="", max_length=160)
    section: str = Field(default="", max_length=160)
    customer_code: str = Field(default="", max_length=64)
    order_id: str = Field(default="", max_length=64)
    order_reference: str = Field(default="", max_length=255)
    product_no: str = Field(default="", max_length=255)
    batch_id: str = Field(default="", max_length=64)
    error_message: str = Field(default="", max_length=1000)
    file_names: list[str] = Field(default_factory=list, max_length=10)
    app_version: str = Field(default="", max_length=80)

    @field_validator("file_names")
    @classmethod
    def safe_file_names(cls, values):
        if any(not v or len(v) > 255 or any(c in v for c in "/\\\r\n\0") for v in values):
            raise ValueError("仅允许文件名，不能包含路径")
        return values


class FeedbackCreate(StrictModel):
    factory_id: str = Field(min_length=1, max_length=64)
    module: Literal["customer-order-center"] = "customer-order-center"
    title: str = Field(min_length=2, max_length=160)
    category: Literal["bug", "suggestion", "question"] = "bug"
    emoji: Literal["", "😕", "🐢", "🐞", "💡", "👍"] = ""
    body: str = Field(default="", max_length=10000)
    context: FeedbackContext = Field(default_factory=FeedbackContext)
    client_request_id: str = Field(min_length=8, max_length=96, pattern=r"^[A-Za-z0-9_-]+$")


class FeedbackReply(StrictModel):
    expected_revision: int = Field(ge=1)
    client_request_id: str = Field(min_length=8, max_length=96, pattern=r"^[A-Za-z0-9_-]+$")
    action: Literal["reply", "start", "request_info", "ready", "resolve", "reopen"] = "reply"
    body: str = Field(default="", max_length=10000)
    requested_materials: list[Material] = Field(default_factory=list, max_length=5)
    provided_materials: list[Material] = Field(default_factory=list, max_length=5)
    release_note: str = Field(default="", max_length=2000)

    @field_validator("requested_materials", "provided_materials")
    @classmethod
    def unique_materials(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("材料项目不能重复")
        return value


class FeedbackRead(StrictModel):
    through_revision: int = Field(ge=0)
