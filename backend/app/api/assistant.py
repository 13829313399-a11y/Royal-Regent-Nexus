from urllib.parse import urlsplit
from fastapi import APIRouter, Depends, Request, Query, UploadFile, File
from fastapi.responses import StreamingResponse, JSONResponse, Response
from fastapi.routing import APIRoute
from fastapi.exceptions import RequestValidationError
from sqlalchemy import select
from app.core.config import settings
from app import db as database
from app.models.assistant import AssistantMessage
from app.schemas.assistant import CreateSession, RenameSession, SendMessage, PageContext, ArtifactCreate, ArtifactVersion, FavoritePatch, ActionRequest
from app.services.assistant import service, runtime, capabilities, help_registry, storage, files, artifacts, visibility
from app.services.assistant.errors import AssistantError


def viewer(request: Request):
    # Auth DB session closes before a long-lived streaming response starts.
    user = runtime.authenticate(request)
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if request.headers.get("sec-fetch-site") == "cross-site":
            raise AssistantError("origin_forbidden", "请从系统页面发起请求。", 403)
        if origin:
            # Behind TLS termination, explicitly configure the public origin.
            allowed = {str(request.base_url).rstrip("/")} | set(settings.assistant_trusted_origins)
            if origin not in allowed:
                raise AssistantError("origin_forbidden", "请求来源不可信。", 403)
    return user


class AssistantRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def normalized(request):
            try:
                return await handler(request)
            except RequestValidationError:
                error = AssistantError("invalid_request", "请求字段或内容长度不符合要求，请核对消息和附件。")
                error.detail["request_id"] = getattr(request.state, "request_id", error.detail["request_id"])
                raise error from None
            except AssistantError as error:
                error.detail["request_id"] = getattr(request.state, "request_id", error.detail["request_id"])
                raise
        return normalized


router = APIRouter(prefix="/api/assistant", tags=["assistant"], route_class=AssistantRoute)


@router.get("/capabilities")
def get_capabilities(user=Depends(viewer)):
    value = capabilities.capabilities()
    if value["schema_status"] == "ready":
        value["search"]["last_result"] = service.last_search_result(user)
    return value


@router.get("/help/context")
def get_context(module_id: str, route_name: str, factory_id: str | None = None, user=Depends(viewer)):
    capabilities.require_enabled(schema=False)
    items = help_registry.context(user, PageContext(module_id=module_id, route_name=route_name, factory_id=factory_id))
    return dict(items=[help_registry.public(a) for a in items], status="ready" if all(a.status == "verified" for a in items) else "partial")


@router.get("/help/articles/{help_id}")
def article(help_id: str, user=Depends(viewer)):
    capabilities.require_enabled(schema=False)
    return help_registry.public(help_registry.get(user, help_id))


@router.post("/sessions")
def create(payload: CreateSession, user=Depends(viewer)):
    capabilities.require_enabled()
    return service.create(user, payload.client_request_id)


@router.get("/sessions")
def sessions(cursor: str = "", limit: int = Query(30, ge=1, le=100), q: str = Query("", max_length=160), favorites: bool = False, user=Depends(viewer)):
    capabilities.require_enabled()
    return service.sessions(user, cursor, limit, q, favorites)


@router.patch("/sessions/{sid}")
def rename(sid: str, payload: RenameSession, user=Depends(viewer)):
    capabilities.require_enabled()
    return service.rename(user, sid, payload)


@router.delete("/sessions/{sid}")
def remove(sid: str, user=Depends(viewer)):
    capabilities.require_enabled()
    done = service.remove(user, sid)
    return JSONResponse(dict(deletion_state="deleted" if done else "pending"), status_code=200 if done else 202)


@router.get("/sessions/{sid}/messages")
def messages(sid: str, cursor: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), user=Depends(viewer)):
    capabilities.require_enabled()
    return service.messages(user, sid, cursor, limit)


@router.post("/sessions/{sid}/messages")
def send(sid: str, payload: SendMessage, request: Request, user=Depends(viewer)):
    admitted = service.admit(user, sid, payload)
    if admitted["reused"]:
        return JSONResponse(admitted)
    admitted["session_id"] = sid
    return StreamingResponse(runtime.events(request, user, payload, admitted), media_type="text/event-stream",
                             headers={"Cache-Control": "private, no-store", "X-Accel-Buffering": "no"})


@router.get("/sessions/{sid}/runs/lookup")
def lookup(sid: str, client_request_id: str, user=Depends(viewer)):
    capabilities.require_enabled()
    return service.snapshot(user, sid=sid, request_id=client_request_id)


@router.get("/runs/{rid}")
def run(rid: str, user=Depends(viewer)):
    capabilities.require_enabled()
    return service.snapshot(user, rid=rid)


@router.post("/runs/{rid}/cancel")
def cancel(rid: str, user=Depends(viewer)):
    # A just-disabled feature must still allow stopping its outstanding runs.
    if not capabilities.schema_ready():
        raise AssistantError("schema_pending", "助手数据尚未准备完成。", 503)
    return service.cancel(user, rid)


@router.get("/sessions/{sid}/export")
def export(sid: str, user=Depends(viewer)):
    capabilities.require_enabled()
    with database.SessionLocal() as db:
        session = service.owned(db, user, sid)
        chunks = ["# " + session.title + "\n"]
        for m in db.scalars(select(AssistantMessage).where(AssistantMessage.session_id == sid).order_by(AssistantMessage.seq)):
            safe = service.message_out(m, user)
            chunks.append("\n## " + ("你" if m.role == "user" else "曜灵") + f" ({m.status})\n")
            for part in safe["content_parts"]:
                if part["type"] in ("text", "reasoning"):
                    chunks.append(part["text"] + "\n")
                elif part["type"] == "image_ref":
                    chunks.append("![主动上传的图片](" + storage.data_url(db, user, sid, part["attachment_id"]) + ")\n")
                elif part["type"] in ("tool_call", "tool_result"):
                    chunks.append("\n工具记录：\n\n~~~~json\n" + json_safe(part) + "\n~~~~\n")
                elif part["type"] == "evidence":
                    chunks.append("\n依据：\n" + artifacts.source_lines(part["sources"]) + "\n检索状态：" + json_safe(part["search"]))
            if safe["context_descriptor"]:
                chunks.append("\n页面上下文：" + json_safe(safe["context_descriptor"]) + "\n")
            for c in safe["help_citations"]:
                chunks.append("来源：" + c["id"] + " / " + c["version"] + "\n")
    return Response("\n".join(chunks), media_type="text/markdown; charset=utf-8", headers={"Cache-Control": "private, no-store", "Content-Disposition": 'attachment; filename="yaoling-conversation.md"'})


def json_safe(value):
    import json
    return json.dumps(value, ensure_ascii=False)


@router.post("/sessions/{sid}/attachments")
async def upload(sid: str, file: UploadFile = File(), user=Depends(viewer)):
    capabilities.require_enabled()
    if not capabilities.capabilities()["profiles"][0]["vision"]:
        raise AssistantError("vision_unavailable", "当前模型尚未验证图片理解。")
    data = await file.read(settings.assistant_max_file_bytes + 1)
    return storage.save(user, sid, data, file.content_type)


@router.get("/attachments/{ident}/content")
def attachment(ident: str, user=Depends(viewer)):
    capabilities.require_enabled()
    return Response(storage.content(user, ident), media_type="image/png", headers={"Cache-Control": "private, no-store"})


@router.delete("/attachments/{ident}")
def remove_attachment(ident: str, user=Depends(viewer)):
    capabilities.require_enabled()
    storage.content(user, ident, remove=True)
    return Response(status_code=204)


@router.post("/sessions/{sid}/files")
async def upload_document(sid: str, file: UploadFile = File(), user=Depends(viewer)):
    import asyncio
    capabilities.require_enabled()
    raw = await file.read(settings.assistant_max_file_bytes+1)
    return await asyncio.to_thread(files.save, user, sid, raw, file.filename)


@router.get("/files/{ident}")
def get_document(ident: str, user=Depends(viewer)):
    capabilities.require_enabled()
    return files.metadata(user, ident)


@router.get("/files/{ident}/content")
def document_content(ident: str, extracted: bool = False, user=Depends(viewer)):
    capabilities.require_enabled()
    data, media = files.content(user, ident, extracted)
    return Response(data, media_type=media, headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.delete("/files/{ident}")
def delete_document(ident: str, user=Depends(viewer)):
    capabilities.require_enabled()
    files.remove(user, ident)
    return Response(status_code=204)


@router.post("/sessions/{sid}/artifacts")
def create_artifact(sid: str, payload: ArtifactCreate, user=Depends(viewer)):
    capabilities.require_enabled()
    return artifacts.create(user, sid, payload)


@router.get("/artifacts")
def artifact_list(q: str = Query("", max_length=160), cursor: str = "", limit: int = Query(30, ge=1, le=100), user=Depends(viewer)):
    capabilities.require_enabled()
    return artifacts.listing(user, q, cursor, limit)


@router.get("/artifacts/{ident}")
def get_artifact(ident: str, revision: int | None = Query(None, ge=1), user=Depends(viewer)):
    capabilities.require_enabled()
    return artifacts.get(user, ident, revision)


@router.post("/artifacts/{ident}/versions")
def artifact_version(ident: str, payload: ArtifactVersion, user=Depends(viewer)):
    capabilities.require_enabled()
    return artifacts.revise(user, ident, payload)


@router.get("/artifacts/{ident}/export")
def artifact_export(ident: str, format: str = "md", revision: int | None = Query(None, ge=1), user=Depends(viewer)):
    capabilities.require_enabled()
    value, media = artifacts.export(user, ident, format, revision)
    return Response(value, media_type=media, headers={"Cache-Control": "private, no-store", "Content-Disposition": f'attachment; filename="yaoling-artifact.{format}"'})


@router.patch("/sessions/{sid}/favorite")
def favorite(sid: str, payload: FavoritePatch, user=Depends(viewer)):
    capabilities.require_enabled()
    return artifacts.favorite(user, sid, payload.favorite)


@router.get("/runs/{rid}/export")
def answer_export(rid: str, format: str = "md", user=Depends(viewer)):
    capabilities.require_enabled()
    snapshot = service.snapshot(user, rid=rid)
    answer = next(m for m in snapshot["items"] if m["role"] == "assistant")
    if answer.get("unavailable"):
        raise AssistantError("source_unavailable", "来源已失效，无法导出。", 410)
    value, media = artifacts.render("".join(p["text"] for p in answer["content_parts"] if p["type"] == "text"), "markdown", "曜灵回答", visibility.sources(answer["content_parts"]), format)
    return Response(value, media_type=media, headers={"Cache-Control": "private, no-store", "Content-Disposition": f'attachment; filename="yaoling-answer.{format}"'})


@router.post("/actions/resolve")
def resolve_action(payload: ActionRequest, user=Depends(viewer)):
    capabilities.require_enabled()
    snapshot = service.snapshot(user, rid=payload.run_id)
    message = next(m for m in snapshot["items"] if m["role"] == "assistant")
    actions = next((p["items"] for p in message["content_parts"] if p["type"] == "actions"), [])
    if payload.index >= len(actions):
        raise AssistantError("source_unavailable", "操作已失效，请重新查询。", 410)
    action = actions[payload.index]
    if action["type"] == "highlight":
        help_registry.get(user, action["help_id"])
    elif action["type"] == "open_record":
        from app.services.assistant.business import ROUTES, authorize
        name = next((n for n, (_, route) in ROUTES.items() if route == action["route_name"]), None)
        with database.SessionLocal() as db:
            authorize(db, user, name, action["query"].get("factory", "authorized"))
        if action["params"] or set(action["query"]) - {"factory", "entry"}:
            raise AssistantError("action_invalid", "导航参数未注册。")
    else:
        raise AssistantError("action_invalid", "操作未注册。")
    return action
