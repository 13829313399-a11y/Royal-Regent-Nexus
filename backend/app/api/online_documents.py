import json
from typing import Annotated, Literal
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.db import get_db
from app.models.auth import AuthSession
from app.models.online_documents import OnlineDocument as Document, OnlineDocumentRevision as Revision, OnlineDocumentPlacement as Placement
from app.services import auth, online_documents as service, online_document_protocol as protocol
from app.services import online_document_management as management
from app.services import online_document_folders as folders
from app.services import online_document_copy
from app.services.document_tools import storage
from app.services.identity_policy import lock_mutation

def no_cache(response: Response):
    response.headers["Cache-Control"] = "private, no-store"


router = APIRouter(prefix="/api/tools/online-documents", tags=["online-documents"], dependencies=[Depends(service.enabled), Depends(no_cache)])
DB = Annotated[Session, Depends(get_db)]


def authenticated_user(request: Request, db: DB):
    if request.method not in {"GET", "HEAD"}:
        lock_mutation(db)
    return auth.get_current_user(request, db)


User = Annotated[auth.AuthContext, Depends(authenticated_user)]


class NewDocument(BaseModel):
    title: str = Field(default="", max_length=190)
    format: Literal["docx", "xlsx"]
    folder_id: str | None = Field(default=None, min_length=16, max_length=64)


class NewFolder(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9-]{16,64}$")
    name: str = Field(min_length=1, max_length=100)


class MoveItem(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    expected_version: int = Field(ge=0)


class MoveDocuments(BaseModel):
    request_id: str = Field(pattern=r"^[a-zA-Z0-9-]{16,64}$")
    folder_id: str | None = Field(default=None, min_length=16, max_length=64)
    documents: list[MoveItem] = Field(min_length=1, max_length=200)


class RenameDocument(BaseModel):
    title: str = Field(min_length=1, max_length=190)
    expected_title: str = Field(max_length=190)
    expected_version: int = Field(ge=1)


class RenameFolder(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    expected_name: str = Field(min_length=1, max_length=100)
    expected_version: int = Field(ge=1)


class CopyDocument(BaseModel):
    request_id: str = Field(pattern=r"^[a-zA-Z0-9-]{16,64}$")
    expected_revision: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=190)
    folder_id: str | None = Field(default=None, min_length=16, max_length=64)


class Grant(BaseModel):
    user_id: str = Field(max_length=64)
    access: Literal["view", "edit"]
    epoch: int = Field(ge=1)


class Grants(BaseModel):
    grants: list[Grant] = Field(max_length=50)
    version: str = Field(default="", max_length=64)


class ManagementCommand(BaseModel):
    request_id: str = Field(pattern=r"^[a-zA-Z0-9-]{16,64}$")
    expected_version: int = Field(ge=1)


class RestoreCommand(ManagementCommand):
    revision: int = Field(ge=1)


class InputRange(BaseModel):
    sheet: str = Field(min_length=1, max_length=31)
    ranges: list[str] = Field(max_length=30)


class ProtectionCommand(ManagementCommand):
    enabled: bool
    rules: list[InputRange] = Field(default_factory=list, max_length=100)


@router.get("")
def listing(user: User, db: DB, factory_id: str, deleted: bool = False, folder_id: str | None = None,
            sort: Literal['updated', 'name', 'name_desc', 'recent'] = 'updated', recent_ids: str = Query(default='', max_length=6500)):
    ids = list(dict.fromkeys(filter(None, recent_ids.split(','))))
    if len(ids) > 100 or any(len(value) > 64 for value in ids):
        raise HTTPException(422, "最近使用记录超出范围")
    return service.listing(db, user, factory_id, deleted, folder_id, sort, ids)


@router.get("/folders")
def folder_list(user: User, db: DB, factory_id: str):
    return folders.listing(db, user, factory_id)


@router.post("/folders", status_code=201)
def folder_create(payload: NewFolder, user: User, db: DB, factory_id: str):
    return folders.create(db, user, factory_id, payload.id, payload.name)


@router.delete("/folders/{folder_id}")
def folder_remove(folder_id: str, user: User, db: DB, factory_id: str):
    return folders.remove(db, user, factory_id, folder_id)


@router.patch("/folders/{folder_id}")
def folder_rename(folder_id: str, payload: RenameFolder, user: User, db: DB, factory_id: str):
    return folders.rename(db, user, factory_id, folder_id, payload.name, payload.expected_name, payload.expected_version)


@router.post("/move")
def move_documents(payload: MoveDocuments, user: User, db: DB, factory_id: str):
    return folders.move(db, user, factory_id, payload.model_dump())


@router.get("/recipients")
def recipients(user: User, db: DB, factory_id: str):
    return service.recipients(db, user, factory_id)


@router.post("", status_code=201)
def create(payload: NewDocument, user: User, db: DB, factory_id: str):
    return service.create(db, user, factory_id, payload.title, payload.format, folder_id=payload.folder_id)


@router.post("/upload", status_code=201)
def upload(user: User, db: DB, factory_id: str = Form(...), file: UploadFile = File(...), folder_id: str | None = Form(default=None)):
    service.scope(user, factory_id)
    extension = Path(file.filename or "").suffix.lstrip(".").lower()
    return service.create(db, user, factory_id, file.filename or "", extension, file.file.read(protocol.MAX_BYTES + 1), folder_id=folder_id)


@router.get("/{document_id}")
def detail(document_id: str, user: User, db: DB, factory_id: str):
    result = service.summary(service.get(db, user, factory_id, document_id), user)
    if result['access'] == 'owner':
        placement = db.get(Placement, document_id)
        result.update(folder_id=placement.folder_id if placement else None, placement_version=placement.version if placement else 0)
    return result


@router.put("/{document_id}/grants")
def share(document_id: str, payload: Grants, user: User, db: DB, factory_id: str):
    return service.share(db, service.get(db, user, factory_id, document_id, lock=True, owner=True), user, payload.grants, payload.version)


@router.patch("/{document_id}/title")
def rename(document_id: str, payload: RenameDocument, user: User, db: DB, factory_id: str):
    return service.rename(db, service.get(db, user, factory_id, document_id, lock=True, owner=True),
                          user, payload.title, payload.expected_title, payload.expected_version)


@router.post("/{document_id}/copy", status_code=201)
def copy_document(document_id: str, payload: CopyDocument, user: User, db: DB, factory_id: str):
    return online_document_copy.duplicate(db, user, factory_id, document_id, payload.model_dump())


@router.get("/{document_id}/history")
def history(document_id: str, user: User, db: DB, factory_id: str, before: int = 0):
    return management.records(db, service.get(db, user, factory_id, document_id, owner=True), user, before=before)


@router.get("/{document_id}/events")
def events(document_id: str, user: User, db: DB, factory_id: str, before: str = ""):
    return management.event_records(db, service.get(db, user, factory_id, document_id, owner=True, include_deleted=True), user, before)


@router.get("/{document_id}/history/{number}/download")
def download_revision(document_id: str, number: int, user: User, db: DB, factory_id: str):
    doc = service.get(db, user, factory_id, document_id, owner=True)
    row = management.version(db, doc, user, number)
    data = management.read_asset(row)
    from urllib.parse import quote
    return Response(data, media_type=storage.MIME[doc.format], headers={"Cache-Control": "private, no-store",
                    "X-Content-Type-Options": "nosniff", "Content-Disposition": "attachment; filename*=UTF-8''" + quote(f"{doc.title}-版本{number}.{doc.format}")})


@router.post("/{document_id}/restore")
def restore(document_id: str, payload: RestoreCommand, user: User, db: DB, factory_id: str):
    return management.command(db, service.get(db, user, factory_id, document_id, owner=True, lock=True), user, "restore", payload.model_dump())


@router.post("/{document_id}/trash")
def trash(document_id: str, payload: ManagementCommand, user: User, db: DB, factory_id: str):
    return management.command(db, service.get(db, user, factory_id, document_id, owner=True, lock=True, include_deleted=True), user, "trash", payload.model_dump())


@router.post("/{document_id}/recover")
def recover(document_id: str, payload: ManagementCommand, user: User, db: DB, factory_id: str):
    return management.command(db, service.get(db, user, factory_id, document_id, owner=True, lock=True, include_deleted=True), user, "recover", payload.model_dump())


@router.get("/{document_id}/protection")
def protection(document_id: str, user: User, db: DB, factory_id: str):
    return management.protection_settings(db, service.get(db, user, factory_id, document_id, owner=True), user)


@router.put("/{document_id}/protection")
def set_protection(document_id: str, payload: ProtectionCommand, user: User, db: DB, factory_id: str):
    return management.command(db, service.get(db, user, factory_id, document_id, owner=True, lock=True), user, "protection", payload.model_dump())


@router.post("/{document_id}/editor")
def editor(document_id: str, request: Request, user: User, db: DB, factory_id: str):
    session = db.scalar(select(AuthSession).where(AuthSession.token_hash == auth.hash_session_token(request.cookies.get(auth.SESSION_COOKIE_NAME, ""))))
    if not session or session.user_id != user.id or session.status != "active":
        raise HTTPException(401, "请重新登录")
    return service.editor(db, service.get(db, user, factory_id, document_id, lock=True), user, session.id)


@router.post("/{document_id}/save")
def save(document_id: str, user: User, db: DB, factory_id: str):
    return service.start_save(db, service.get(db, user, factory_id, document_id, lock=True, edit=True))


@router.post("/{document_id}/release-unopened")
def release_unopened(document_id: str, user: User, db: DB, factory_id: str):
    return service.release_unopened(db, service.get(db, user, factory_id, document_id, lock=True, edit=True))


@router.get("/{document_id}/download")
def download(document_id: str, user: User, db: DB, factory_id: str):
    doc = service.get(db, user, factory_id, document_id)
    return FileResponse(storage.resolve(doc.storage_key), filename=doc.title + "." + doc.format,
                        media_type=storage.MIME[doc.format], headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/{document_id}/source")
def source(document_id: str, token: str, db: DB):
    payload = protocol.verify(token)
    doc = db.get(Document, document_id)
    if payload.get("purpose") in {"source", "source-view"} and payload.get("document") == document_id and doc and payload.get("exp"):
        from datetime import datetime
        from app.models.auth import AuthUser
        session = db.get(AuthSession, payload.get("session_id"))
        account = db.get(AuthUser, payload.get("user_id"))
        expiry = auth.parse_time(session.expires_at) if session else None
        if not session or session.status != "active" or not expiry or expiry <= datetime.now() or not account or account.status != "active" or account.force_password_change or session.user_id != account.id:
            raise HTTPException(403, "文件读取会话无效")
        user = auth.build_auth_context(db, account)
        service.get(db, user, doc.factory_id, doc.id)
        if payload.get("generation", 1) != doc.access_generation:
            raise HTTPException(403, "文件读取链接已失效，请重新打开文档")
        if service.epoch(user) != payload.get("epoch"):
            raise HTTPException(403, "文件读取会话无效")
        if payload.get("purpose") == "source-view":
            version = db.scalar(select(Revision).where(Revision.document_id == doc.id, Revision.revision == payload.get("revision")))
            if not version:
                raise HTTPException(403, "文件读取会话无效")
            return FileResponse(storage.resolve(version.storage_key), media_type=storage.MIME[doc.format], headers={"Cache-Control": "no-store"})
    else:
        raise HTTPException(403, "文件读取会话无效")
    if (payload.get("purpose") != "source" or payload.get("document") != document_id or
            not doc or not doc.editor_key or payload.get("key") != doc.editor_key or not payload.get("exp")):
        raise HTTPException(403, "文件读取会话无效")
    return FileResponse(storage.resolve(doc.editor_source), media_type=storage.MIME[doc.format],
                        filename=doc.title + "." + doc.format, headers={"Cache-Control": "no-store"})


@router.post("/{document_id}/callback")
async def callback(document_id: str, request: Request, db: DB):
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > 128 * 1024:
            raise HTTPException(413, "回调内容过大")
    try:
        body = json.loads(data)
        token = request.headers.get("AuthorizationJwt", "").removeprefix("Bearer ") or body.get("token", "")
        signed = protocol.verify(token)
        payload = signed.get("payload", signed)
        if not isinstance(payload, dict):
            raise ValueError()
    except (ValueError, AttributeError):
        raise HTTPException(422, "回调格式无效") from None
    # Never merge unsigned body fields into the verified payload.
    return await run_in_threadpool(service.callback, db, document_id, payload)
