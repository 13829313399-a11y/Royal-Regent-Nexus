from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.core.config import settings
from app.services.uv_ingest import ingest_batch

router = APIRouter(prefix="/uv-printing", tags=["uv-ingest"])


class IngestBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    factory_id: Annotated[str, Field(min_length=1, max_length=32)]
    events: Annotated[list[Any], Field(min_length=1, max_length=100)]


@router.post("/ingest/events")
def events(payload: IngestBatch, authorization: Annotated[str | None, Header()] = None, db: Session = Depends(get_db)):
    if not settings.uv_printing_enabled:
        raise HTTPException(503, "UV打印尚未启用")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "独立连接器认证必需")
    return ingest_batch(db, authorization[7:], payload.factory_id, payload.events)
