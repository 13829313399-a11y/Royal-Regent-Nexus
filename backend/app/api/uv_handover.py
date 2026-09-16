from typing import Annotated, Any
from fastapi import APIRouter, Body, HTTPException
from sqlalchemy.exc import IntegrityError, OperationalError
from app.api.uv_printing import Db, User, Scope, authorize, envelope
from app.services import uv_handover as handover, uv_printing as core

router = APIRouter(prefix="/api/uv-printing", tags=["uv-printing-handover"])


@router.get("/handovers")
def list_handovers(db: Db, user: User, scope: Scope):
    authorize(db, user, scope["factory_id"])
    return envelope(core.page(handover.list_rows(db, scope["factory_id"], scope), scope))


def command(db, user, payload):
    authorize(db, user, payload.get("factory_id"))
    authorize(db, user, payload.get("factory_id"), "report")
    try:
        result = core.execute(db, payload["factory_id"], user.id, "handover-save", payload)
        db.commit()
        return envelope(result)
    except (IntegrityError, OperationalError):
        db.rollback()
        raise HTTPException(409, "该报工已存在核数记录或并发状态变化，请刷新后更新原记录")
    except Exception:
        db.rollback()
        raise


@router.post("/handovers")
def create_handover(db: Db, user: User, payload: Annotated[dict[str, Any], Body()]):
    if payload.get("id"):
        raise HTTPException(422, "更新核数记录须使用对象路径")
    return command(db, user, payload)


@router.post("/handovers/{handover_id}")
def update_handover(handover_id: str, db: Db, user: User, payload: Annotated[dict[str, Any], Body()]):
    if payload.get("id") != handover_id:
        raise HTTPException(422, "路径与核数对象不一致")
    return command(db, user, payload)
