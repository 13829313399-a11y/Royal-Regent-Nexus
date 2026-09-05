from hmac import compare_digest

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db
from app.schemas import three_d_connector as schema
from app.services import three_d_connector as service


def require_connector(request: Request):
    if (
        not settings.three_d_connector_enabled
        or len(settings.three_d_connector_token) < 32
    ):
        raise HTTPException(503, "云端连接器接口尚未启用")
    supplied = request.headers.get("X-Three-D-Connector-Token", "")
    if not compare_digest(supplied.encode(), settings.three_d_connector_token.encode()):
        raise HTTPException(401, "云端连接器认证失败")


router = APIRouter(
    prefix="/api/internal/three-d-connector",
    tags=["three-d-connector"],
    dependencies=[Depends(require_connector)],
)


@router.post("/heartbeat")
def heartbeat(payload: schema.Heartbeat, db: Session = Depends(get_db)):
    return service.heartbeat(db, payload)


@router.post("/printers")
def list_printers(payload: schema.Scope, db: Session = Depends(get_db)):
    return service.list_printers(db, payload)


@router.post("/reconcile")
def reconcile(payload: schema.SessionRef, db: Session = Depends(get_db)):
    return service.reconcile(db, payload)


@router.post("/leases/acquire")
def acquire(payload: schema.LeaseRequest, db: Session = Depends(get_db)):
    return service.acquire(db, payload)


@router.post("/leases/renew")
def renew(payload: schema.LeaseRef, db: Session = Depends(get_db)):
    return service.renew(db, payload)


@router.post("/leases/release")
def release(payload: schema.LeaseRef, db: Session = Depends(get_db)):
    return service.release(db, payload)


@router.post("/sessions/start")
def start_session(payload: schema.SessionStart, db: Session = Depends(get_db)):
    return service.start_session(db, payload)


@router.post("/events")
def store_event(payload: schema.StateEvent, db: Session = Depends(get_db)):
    return service.store_event(db, payload)


@router.post("/commands/claim")
def claim_command(payload: schema.SessionRef, db: Session = Depends(get_db)):
    return service.claim_command(db, payload)


@router.post("/commands/dispatch")
def dispatch_command(payload: schema.CommandRef, db: Session = Depends(get_db)):
    return service.dispatch_command(db, payload)


@router.post("/commands/ack")
def acknowledge_command(payload: schema.CommandResult, db: Session = Depends(get_db)):
    return service.acknowledge_command(db, payload)
