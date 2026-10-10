from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.carton_mark import CartonMarkAutoCheckResponse


class QcAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    request_id: str = Field(min_length=1, max_length=96, pattern=r"^[A-Za-z0-9_-]+$")
    action: Literal["核对通过", "发现异常", "重新自动核对", "作废"]
    note: str = Field(default="", max_length=1000)


class QcPhotoOut(BaseModel):
    id: str
    side: str
    file_name: str
    size_bytes: int
    sha256: str


class QcEventOut(BaseModel):
    revision: int
    kind: str
    status: str
    result: CartonMarkAutoCheckResponse | None = None
    error: str
    note: str
    actor_name: str
    created_at: str


class QcRecordOut(BaseModel):
    id: str
    factory_id: str
    template_id: str
    template_version: int
    template_snapshot: dict
    customer_name: str
    po: str
    item: str
    contract_number: str
    corrects_record_id: str | None
    note: str
    created_by_name: str
    created_at: str
    revision: int
    status: str
    photos: list[QcPhotoOut]
    events: list[QcEventOut]
