from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.document_tools import enabled
from app.db import get_db
from app.schemas.collaborative_sheets import CellsInput, GrantsInput, RevisionInput, StateInput
from app.services.auth import AuthContext, get_current_user
from app.services import collaborative_sheets as service
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


@router.get("/{task_id}/download")
def download(task_id: str, user: User, db: DB, factory_id: str):
    task = service.get_task(db, user, factory_id, task_id, owner=True)
    content = service.download(task)
    return Response(content, media_type="application/vnd.ms-excel" if task.format == "xls" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(task.original_name),
                             "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
                             "X-Workbook-Revision": str(task.revision)})
