from typing import Annotated
from urllib.parse import quote

import asyncio
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Request, Query
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from app.api.document_tools import enabled
from app.db import get_db, SessionLocal
from app.schemas.collaborative_sheets import CellsInput, GrantsInput, RevisionInput, StateInput, SyncCellsInput
from app.services.auth import AuthContext, get_current_user
from app.services import collaborative_sheets as service
from app.services import collaborative_sheet_sync as sync
from app.services.collaborative_sheet_files import FILE_SIZE_ERROR, MAX_FILE_BYTES

router = APIRouter(prefix="/api/tools/collaborative-sheets", tags=["collaborative-sheets"], dependencies=[Depends(enabled)])
User = Annotated[AuthContext, Depends(get_current_user)]
DB = Annotated[Session, Depends(get_db)]


@router.get("/recipients")
def recipients(user: User, db: DB, factory_id: str):
    return service.recipients(db, user, factory_id)


@router.get("")
def list_tasks(user: User, db: DB, factory_id: str):
    return service.list_tasks(db, user, factory_id)


@router.post("", status_code=201)
def upload(user: User, db: DB, file: UploadFile = File(...), factory_id: str = Form(...), title: str = Form(default="")):
    service.scope(user, factory_id)
    data = file.file.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(413, FILE_SIZE_ERROR)
    return service.create(db, user, factory_id, title, file.filename or "workbook", data)


@router.get("/{task_id}")
def detail(task_id: str, user: User, db: DB, factory_id: str):
    return service.detail(db, service.get_task(db, user, factory_id, task_id), user)


@router.get("/{task_id}/participants")
def participants(task_id: str, user: User, db: DB, factory_id: str, response: Response):
    response.headers["Cache-Control"] = "private, no-store"
    return service.participant_status(db, user, factory_id, task_id)


@router.put("/{task_id}/grants")
def grants(task_id: str, payload: GrantsInput, user: User, db: DB, factory_id: str):
    return service.set_grants(db, service.get_task(db, user, factory_id, task_id, owner=True), user, payload)


@router.post("/{task_id}/state")
def state(task_id: str, payload: StateInput, user: User, db: DB, factory_id: str):
    return service.set_state(db, service.get_task(db, user, factory_id, task_id, owner=True), user, payload)


@router.patch("/{task_id}/cells")
def cells(task_id: str, payload: CellsInput, user: User, db: DB, factory_id: str):
    return service.save_cells(db, service.get_task(db, user, factory_id, task_id), user, payload)


@router.post("/{task_id}/submit")
def submit(task_id: str, payload: RevisionInput, user: User, db: DB, factory_id: str):
    return service.submit(db, service.get_task(db, user, factory_id, task_id), user, payload)


@router.patch("/{task_id}/sync")
def save_incremental(task_id: str, payload: SyncCellsInput, user: User, db: DB, factory_id: str):
    return sync.save(db, user, factory_id, task_id, payload)


@router.get("/{task_id}/changes")
def changes(task_id: str, user: User, db: DB, factory_id: str, response: Response, since: int = Query(ge=1)):
    response.headers["Cache-Control"] = "private, no-store"
    return sync.delta(db, service.get_task(db, user, factory_id, task_id, lightweight=True), user, since)


@router.get("/{task_id}/history")
def history(task_id: str, user: User, db: DB, factory_id: str, response: Response,
            before: int | None = Query(default=None, ge=1), actor: str | None = None,
            sheet: int | None = Query(default=None, ge=0, le=49), address: str | None = None):
    response.headers["Cache-Control"] = "private, no-store"
    return sync.history(db, service.get_task(db, user, factory_id, task_id, lightweight=True), before, actor, sheet, address)


def stream_revision(request, factory_id, task_id):
    # A fresh short session on every heartbeat rechecks logout, employment,
    # factory, department and task ACL; no idle connection/transaction is held.
    enabled()
    with SessionLocal() as db:
        user = get_current_user(request, db)
        task = service.get_task(db, user, factory_id, task_id, lightweight=True)
        return task.revision


@router.get("/{task_id}/stream")
async def stream(task_id: str, request: Request, factory_id: str):
    initial = await asyncio.to_thread(stream_revision, request, factory_id, task_id)
    async def events():
        revision = initial
        yield f"event: revision\ndata: {revision}\n\n"
        while not await request.is_disconnected():
            await asyncio.sleep(2)
            try:
                latest = await asyncio.to_thread(stream_revision, request, factory_id, task_id)
            except HTTPException:
                yield 'event: access_revoked\ndata: {}\n\n'
                return
            if latest != revision:
                revision = latest
                yield f"event: revision\ndata: {revision}\n\n"
            else:
                yield ': heartbeat\n\n'
    return StreamingResponse(events(), media_type="text/event-stream",
        headers={"Cache-Control": "private, no-store", "X-Accel-Buffering": "no"})


@router.get("/{task_id}/download")
def download(task_id: str, user: User, db: DB, factory_id: str):
    task = service.get_task(db, user, factory_id, task_id, owner=True)
    content = sync.download(task)
    return Response(content, media_type="application/vnd.ms-excel" if task.format == "xls" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(task.original_name),
                             "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
                             "X-Workbook-Revision": str(task.revision)})
