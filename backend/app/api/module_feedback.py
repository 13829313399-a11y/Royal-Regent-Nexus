from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from fastapi.routing import APIRoute
from pydantic import ValidationError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from app.db import get_db
from app.schemas.module_feedback import FeedbackCreate, FeedbackRead, FeedbackReply, Status
from app.services.auth import AuthContext, get_current_user
from app.services import module_feedback as service


class BoundedFeedbackRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def bounded(request: Request):
            if request.method == "POST":
                received = 0
                original = request._receive

                async def receive():
                    nonlocal received
                    event = await original()
                    received += len(event.get("body", b""))
                    if received > service.MAX_REQUEST_BYTES:
                        raise HTTPException(413, "反馈请求超过25MB附件限制")
                    return event

                request._receive = receive
            response = await handler(request)
            response.headers["Cache-Control"] = "private, no-store"
            return response

        return bounded


router = APIRouter(prefix="/api/module-feedback", tags=["module-feedback"], route_class=BoundedFeedbackRoute)


async def _multipart(request, schema):
    async with request.form(max_files=service.MAX_FILES, max_fields=1, max_part_size=65536) as form:
        if set(form.keys()) - {"payload", "files"} or len(form.getlist("payload")) != 1:
            raise HTTPException(422, "请提交反馈内容及附件")
        try:
            payload = schema.model_validate_json(form.get("payload"))
        except (ValidationError, TypeError, ValueError) as exc:
            raise HTTPException(422, "反馈字段无效，请检查必填内容、长度及材料选项") from exc
        raw = []
        for file in form.getlist("files"):
            if not isinstance(file, UploadFile):
                raise HTTPException(422, "附件格式无效")
            content = await file.read(service.MAX_FILE_BYTES + 1)
            if len(content) > service.MAX_FILE_BYTES:
                raise HTTPException(413, "单个附件不能超过10MB")
            raw.append((file.filename, content))
        uploads = await run_in_threadpool(service.validate_uploads, raw)
    return payload, uploads


@router.get("/capabilities")
def capabilities(factory_id: str, module: str = service.MODULE, user: AuthContext = Depends(get_current_user)):
    return service.capabilities(user, factory_id, module)


@router.get("")
def list_tickets(factory_id: str, module: str = service.MODULE, view: Literal["mine", "manage"] = "mine",
                 status: Status | None = None, q: str = Query("", max_length=160), page: int = Query(1, ge=1),
                 page_size: int = Query(20, ge=1, le=100), db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return service.list_tickets(db, user, factory_id, module, view, status, q, page, page_size)


@router.post("")
async def create(request: Request, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    payload, uploads = await _multipart(request, FeedbackCreate)
    return await run_in_threadpool(service.create_ticket, db, user, payload, uploads)


@router.get("/{ticket_id}")
def detail(ticket_id: str, factory_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return service.detail(db, user, ticket_id, factory_id)


@router.post("/{ticket_id}/messages")
async def reply(ticket_id: str, factory_id: str, request: Request,
                db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    # Check scope before doing image/workbook validation work.
    await run_in_threadpool(service.ticket_for_user, db, user, ticket_id, factory_id)
    payload, uploads = await _multipart(request, FeedbackReply)
    return await run_in_threadpool(service.reply, db, user, ticket_id, factory_id, payload, uploads)


@router.post("/{ticket_id}/read")
def mark_read(ticket_id: str, factory_id: str, payload: FeedbackRead,
              db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return service.mark_read(db, user, ticket_id, factory_id, payload.through_revision)


@router.get("/{ticket_id}/attachments/{attachment_id}")
def attachment(ticket_id: str, attachment_id: str, factory_id: str,
               db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    row = service.attachment(db, user, ticket_id, factory_id, attachment_id)
    return Response(row.content, media_type=row.content_type, headers={
        "Content-Disposition": "attachment; filename*=UTF-8''" + quote(row.file_name, safe=""),
        "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store",
        "Content-Security-Policy": "sandbox; default-src 'none'"})
