import asyncio
import json
from fastapi import APIRouter, Depends, Request, Response, Query, UploadFile, File, Form
from fastapi.responses import StreamingResponse, FileResponse
from starlette.concurrency import run_in_threadpool
from app.core.config import settings
from app.db import SessionLocal
from app.services.auth import get_current_user
from app.services.identity_policy import lock_mutation
from app.services.internal_members import require_internal, is_internal
from app.services.collaboration import core, assets, references
from app.schemas.collaboration import (ProfilePatch, PreferencesPatch, DirectRequest, MessageRequest,
    DraftPatch, ReadRequest, ConversationPreferencesPatch, AppreciationRequest, AppreciationPatch, Reference)
from app.models.collaboration import Message, Appreciation

router = APIRouter(prefix="/api/collaboration", tags=["collaboration"])


def session(request: Request):
    with SessionLocal() as db:
        if request.method == "GET":
            if db.bind.dialect.name == "postgresql":
                db.connection(execution_options={"isolation_level": "REPEATABLE READ"})
            else:
                db.connection().exec_driver_sql("BEGIN")
        else:
            lock_mutation(db)
        yield db


def viewer(request: Request, response: Response, db=Depends(session)):
    response.headers["Cache-Control"] = "no-store"
    if not settings.collaboration_enabled:
        core.fail("COLLABORATION_DISABLED", "成员协作尚未开启", 403)
    return require_internal(get_current_user(request, db))


@router.get("/capabilities")
def capabilities(request: Request, response: Response, db=Depends(session)):
    response.headers["Cache-Control"] = "no-store"
    user = get_current_user(request, db)
    eligible = is_internal(user)
    return dict(enabled=settings.collaboration_enabled, eligible=eligible, owner=core.owner(user),
        features=dict(profiles=True, messaging=True, attachments=True, appreciations=True, public_appreciations=False,
                      business_references=["molding_sample", "internal_quote"]) if settings.collaboration_enabled and eligible else {},
        limits=dict(message_characters=4000, attachments=6, image_bytes=15*1024*1024, document_bytes=25*1024*1024))


@router.get("/me/profile")
def profile(db=Depends(session), user=Depends(viewer)):
    return core.get_profile(db, user)


@router.patch("/me/profile")
def update_profile(payload: ProfilePatch, db=Depends(session), user=Depends(viewer)):
    return core.patch_profile(db, user, payload)


@router.get("/me/preferences")
def preferences(db=Depends(session), user=Depends(viewer)):
    return core.preferences(db, core.identity(user))


@router.patch("/me/preferences")
def update_preferences(payload: PreferencesPatch, db=Depends(session), user=Depends(viewer)):
    return core.patch_preferences(db, user, payload)


@router.get("/me/contacts")
def contacts(page: int = Query(1, ge=1), db=Depends(session), user=Depends(viewer)):
    from app.services.directory import list_directory_members
    return list_directory_members(db, viewer=user, page=page, contacts_only=True)


@router.put("/me/contacts/{target_id}")
def add_contact(target_id: str, db=Depends(session), user=Depends(viewer)):
    return core.contact(db, user, target_id, True)


@router.delete("/me/contacts/{target_id}")
def delete_contact(target_id: str, db=Depends(session), user=Depends(viewer)):
    return core.contact(db, user, target_id, False)


@router.get("/bootstrap")
def bootstrap(db=Depends(session), user=Depends(viewer)):
    return core.bootstrap(db, user)


@router.post("/conversations/direct")
def direct(payload: DirectRequest, db=Depends(session), user=Depends(viewer)):
    return core.direct(db, user, payload.peer_user_id)


@router.get("/conversations")
def conversations(cursor: str | None = Query(None, max_length=512), limit: int = Query(30, ge=1, le=100),
                  include_archived: bool = False, db=Depends(session), user=Depends(viewer)):
    return core.conversations(db, user, cursor, limit, include_archived)


@router.get("/conversations/{cid}")
def conversation(cid: str, db=Depends(session), user=Depends(viewer)):
    row, _ = core.conversation(db, user, cid)
    return core.conversation_out(db, user, row)


@router.get("/appreciations/{aid}")
def appreciation(aid: str, db=Depends(session), user=Depends(viewer)):
    row = db.get(Appreciation, aid)
    if not row:
        core.fail("APPRECIATION_NOT_FOUND", "感谢卡不可查看", 404)
    return core.appreciation_out(db, user, row)


@router.get("/conversations/{cid}/messages")
def messages(cid: str, before_seq: int | None = Query(None, ge=1), after_seq: int | None = Query(None, ge=0),
             limit: int = Query(50, ge=1, le=100), db=Depends(session), user=Depends(viewer)):
    if before_seq is not None and after_seq is not None:
        core.fail("INVALID_PAGINATION", "前向和后向游标不可同时使用", 422)
    return core.messages(db, user, cid, before_seq, after_seq, limit)


@router.post("/conversations/{cid}/messages")
def send(cid: str, payload: MessageRequest, db=Depends(session), user=Depends(viewer)):
    return core.send(db, user, cid, payload)


@router.get("/messages/by-client-id/{client_id}")
def submitted(client_id: str, db=Depends(session), user=Depends(viewer)):
    return core.submitted(db, user, client_id)


@router.post("/messages/{mid}/retract")
def retract(mid: str, db=Depends(session), user=Depends(viewer)):
    return core.retract(db, user, mid)


@router.post("/conversations/{cid}/read")
def read(cid: str, payload: ReadRequest, db=Depends(session), user=Depends(viewer)):
    return core.mark_read(db, user, cid, payload.through_message_seq)


@router.patch("/conversations/{cid}/preferences")
def conversation_preferences(cid: str, payload: ConversationPreferencesPatch, db=Depends(session), user=Depends(viewer)):
    return core.conversation_preferences(db, user, cid, payload)


@router.get("/conversations/{cid}/draft")
def draft(cid: str, db=Depends(session), user=Depends(viewer)):
    return core.get_draft(db, user, cid)


@router.patch("/conversations/{cid}/draft")
def update_draft(cid: str, payload: DraftPatch, db=Depends(session), user=Depends(viewer)):
    return core.patch_draft(db, user, cid, payload)


@router.get("/conversations/{cid}/search")
def search(cid: str, q: str = Query(min_length=1, max_length=100), before_seq: int | None = Query(None, ge=1),
           limit: int = Query(30, ge=1, le=100), db=Depends(session), user=Depends(viewer)):
    return core.messages(db, user, cid, before_seq=before_seq, limit=limit, q=q)


@router.get("/sync")
def sync(cursor: str = Query(max_length=512), limit: int = Query(100, ge=1, le=100), db=Depends(session), user=Depends(viewer)):
    return core.sync(db, user, cursor, limit)


def stream_batch(request, cursor):
    # Threadpool work owns and closes its short DB snapshot before waiting.
    with SessionLocal() as db:
        if db.bind.dialect.name == "postgresql":
            db.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        else:
            db.connection().exec_driver_sql("BEGIN")
        if not settings.collaboration_enabled:
            core.fail("COLLABORATION_DISABLED", "协作已关闭", 403)
        user = require_internal(get_current_user(request, db))
        return core.sync(db, user, cursor)


@router.get("/events")
async def events(request: Request, cursor: str = Query(max_length=512)):
    last_id = request.headers.get("last-event-id")
    if last_id and last_id != cursor:
        core.fail("AMBIGUOUS_CURSOR", "事件恢复位置不一致", 422)
    first = await run_in_threadpool(stream_batch, request, cursor)

    async def generate():
        current, batch, ticks, initial = cursor, first, 0, True
        while not await request.is_disconnected():
            if batch["events"] or initial:
                initial = False
                current = batch["cursor"]
                yield "event: sync\ndata: " + json.dumps(batch, ensure_ascii=False) + "\n\n"
            else:
                if ticks % 15 == 0:
                    yield ": keepalive\n\n"
                await asyncio.sleep(1)
                ticks += 1
            try:
                batch = await run_in_threadpool(stream_batch, request, current)
            except core.HTTPException as error:
                kind = "session_ended" if error.status_code in {401, 403} else "reset_required"
                yield f"event: {kind}\ndata: {{}}\n\n"
                return
    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@router.post("/conversations/{cid}/attachments")
async def upload(cid: str, request: Request, file: UploadFile = File(), client_upload_id: str = Form(min_length=8, max_length=96)):
    # Decode outside the write transaction. Authenticate once before reading bytes.
    def check():
        with SessionLocal() as db:
            if not settings.collaboration_enabled:
                core.fail("COLLABORATION_DISABLED", "成员协作尚未开启", 403)
            core.conversation(db, require_internal(get_current_user(request, db)), cid)
    await run_in_threadpool(check)
    content = await file.read(25 * 1024 * 1024 + 1)
    filename, mime = await run_in_threadpool(assets.validate, content, file.filename or "")
    def save():
        with SessionLocal() as db:
            lock_mutation(db)
            user = require_internal(get_current_user(request, db))
            return assets.upload(db, user, cid, client_upload_id, filename, mime, content)
    return await run_in_threadpool(save)


@router.get("/attachments/{aid}/content")
def content(aid: str, db=Depends(session), user=Depends(viewer)):
    row = assets.readable(db, user, aid)
    return FileResponse(assets.path_for(row.storage_key), media_type=row.mime, filename=row.filename,
        content_disposition_type="inline" if row.mime.startswith("image/") else "attachment",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox"})


@router.delete("/attachments/{aid}")
def delete_attachment(aid: str, db=Depends(session), user=Depends(viewer)):
    return assets.cancel(db, user, aid)


@router.post("/references/preview")
def preview_reference(payload: Reference, peer_user_id: str, db=Depends(session), user=Depends(viewer)):
    peer = core.peer_context(db, peer_user_id)
    own = references.project(db, user, payload.model_dump())
    return {"reference": own, "peer_can_view": references.project(db, peer, payload.model_dump())["available"] if own["available"] else False}


@router.get("/messages/{mid}/reference")
def reference(mid: str, db=Depends(session), user=Depends(viewer)):
    row = db.get(Message, mid)
    if not row:
        core.fail("MESSAGE_NOT_FOUND", "消息不可查看", 404)
    core.conversation(db, user, row.conversation_id)
    return references.project(db, user, row.reference) if row.reference and not row.retracted_at else {"available": False, "label": "该业务记录当前不可查看"}


@router.post("/appreciations")
def appreciate(payload: AppreciationRequest, db=Depends(session), user=Depends(viewer)):
    return core.appreciate(db, user, payload)


@router.get("/me/appreciations")
def appreciations(sent: bool = False, cursor: str | None = Query(None, max_length=512), limit: int = Query(30, ge=1, le=100),
                  db=Depends(session), user=Depends(viewer)):
    return core.appreciations(db, user, sent, cursor, limit)


@router.patch("/appreciations/{aid}")
def update_appreciation(aid: str, payload: AppreciationPatch, db=Depends(session), user=Depends(viewer)):
    return core.patch_appreciation(db, user, aid, payload)
