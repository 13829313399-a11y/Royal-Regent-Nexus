from fastapi import APIRouter, Depends, Query, Request, Response, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app.db import SessionLocal
from app.services.auth import get_current_user
from app.services.work_center import service
from app.schemas.work_center import UserStatePatch, UserStateBatch, PreferencesPatch

router = APIRouter(prefix="/api/work-center", tags=["work-center"])


def session(request: Request):
    with SessionLocal() as db:
        # Set before the first read, including session/identity resolution.
        if request.method == "GET" and db.bind.dialect.name == "postgresql":
            db.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        elif request.method == "GET" and db.bind.dialect.name == "sqlite":
            db.connection().exec_driver_sql("BEGIN")
        yield db


def viewer(request: Request, response: Response, db: Session = Depends(session)):
    response.headers["Cache-Control"] = "no-store"
    user = get_current_user(request, db)
    # Supplier login credentials do not imply internal portal membership.
    if user.permissions and all(p.startswith("carton_supplier:") for p in user.permissions):
        raise HTTPException(403, "供应商账号不使用内部事项工作台")
    return user


@router.get("/snapshot")
def snapshot(view: str = "todo", factory_scope: str = "authorized", module: str = "", q: str = Query("", max_length=160),
             unread_only: bool = False, due: str = "all", cursor: str | None = Query(None, max_length=2048),
             limit: int = Query(30, ge=1, le=100), selected_id: str | None = Query(None, max_length=512),
             db: Session = Depends(session), user=Depends(viewer)):
    args = dict(view=view, factory_scope=factory_scope, module=module, q=q,
                unread_only=unread_only, due=due, cursor=cursor, limit=limit, selected_id=selected_id)
    try:
        with db.begin_nested():
            return service.snapshot(db, user, **args)
    except SQLAlchemyError:
        from app.services.work_center.registry import probe_sources
        unavailable = probe_sources(db, user)
        if not unavailable:
            raise HTTPException(503, "事项暂时无法同步，请稍后重试")
        try:
            with db.begin_nested():
                return service.snapshot(db, user, **args)
        except SQLAlchemyError:
            raise HTTPException(503, "事项暂时无法同步，请稍后重试")


@router.get("/entries/{entry_id}")
def detail(entry_id: str, db: Session = Depends(session), user=Depends(viewer)):
    return service.detail(db, user, entry_id)


@router.get("/entries/{entry_id}/events")
def events(entry_id: str, cursor: str | None = None, limit: int = Query(5, ge=1, le=100), db: Session = Depends(session), user=Depends(viewer)):
    return service.events(db, user, entry_id, cursor, limit)


@router.patch("/entries/{entry_id}/user-state")
def patch_state(entry_id: str, payload: UserStatePatch, db: Session = Depends(session), user=Depends(viewer)):
    result = service.patch_state(db, user, entry_id, payload)
    db.commit()
    return result


@router.post("/user-state/batch")
def batch(payload: UserStateBatch, db: Session = Depends(session), user=Depends(viewer)):
    from app.services.transaction_lock import lock_transaction
    epoch, _ = service.context(db, user)
    # Acquire outside savepoints: PostgreSQL releases locks obtained inside a
    # rolled-back savepoint, while the transaction lock cache survives it.
    for entry_id in sorted({item.id for item in payload.items}):
        lock_transaction(db, "work-center-state", f"{user.id}:{epoch}:{entry_id}")
    results = []
    for item in payload.items:
        try:
            with db.begin_nested():
                result = service.patch_state(db, user, item.id, UserStatePatch.model_validate(item.model_dump(exclude={"id"}, exclude_unset=True)))
            results.append({"id": item.id, "status": "ok", "entry": result})
        except HTTPException as error:
            results.append({"id": item.id, "status": "error", "code": error.status_code, "message": error.detail})
    db.commit()
    return {"results": results}


@router.get("/preferences")
def get_preferences(db: Session = Depends(session), user=Depends(viewer)):
    return service.preferences(db, user)


@router.patch("/preferences")
def patch_preferences(payload: PreferencesPatch, db: Session = Depends(session), user=Depends(viewer)):
    result = service.preferences(db, user, payload)
    db.commit()
    return result
