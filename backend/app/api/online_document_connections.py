"""Cookie-bound ONLYOFFICE connections; a cached editor JWT is not an ACL."""
import asyncio
import json
import re
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool
from starlette.responses import StreamingResponse
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from app.core.config import settings
from app.db import SessionLocal
from app.models.online_documents import OnlineDocument as Document, OnlineDocumentRevision as Revision
from app.services import auth, online_documents as service, online_document_protocol as protocol

router = APIRouter()
SOCKET_PATH = re.compile(r"(?:(?:[0-9][\w.-]*)/)?doc/(?P<key>[\w.=-]{1,128})/c/?$")
VIEW_KEY = re.compile(r"view-([a-f0-9]{32})-([1-9][0-9]*)$")
DYNAMIC_PATH = re.compile(r"(?:(?:[0-9][\w.-]*)/)?(?P<kind>cache/files|downloadas|savefile|printfile|downloadfile|upload)/(?P<key>[\w.=-]+)(?:/[\w.\-/=]*)?$")
FRAME_LIMIT = 16 * 1024 * 1024


def connection_policy(scope, key, principal=None, editing=None):
    # Request is only an adapter for existing cookie/account/session checks.
    request = Request({**scope, "type": "http", "method": "GET"})
    with SessionLocal() as db:
        service.enabled()
        user = auth.get_current_user(request, db)
        identity = f"{user.id}_{service.epoch(user)}"
        if principal is not None and identity != principal:
            raise HTTPException(403, "任职身份已变化")
        view = VIEW_KEY.fullmatch(key)
        doc = db.get(Document, view[1]) if view else db.scalar(select(Document).where(Document.editor_key == key))
        if not doc:
            raise HTTPException(404, "文档连接已失效")
        doc = service.get(db, user, doc.factory_id, doc.id)
        if view and not db.scalar(select(Revision.id).where(Revision.document_id == doc.id, Revision.revision == int(view[2]))):
            raise HTTPException(404, "文档版本不存在")
        mode = service.access(doc, user)
        if (not view or editing) and mode not in {"owner", "edit"}:
            raise HTTPException(403, "编辑权限已撤销")
        state = doc.participants.get(service.SHARING_STATE, {})
        if state.get("expires", 0) > service.time.time() and identity in state.get("targets", []):
            raise HTTPException(403, "正在撤销此连接的权限")
        return identity, not bool(view)


def cache_document_key(value):
    match = re.match(r"(view-[a-f0-9]{32}-[1-9][0-9]*|[a-f0-9]{32})(?:_|$)", value)
    if not match:
        raise HTTPException(403, "文档缓存地址无效")
    return match[1]


def check_token(token, key, principal, editing):
    payload = protocol.verify(token)
    document, editor = payload.get("document", {}), payload.get("editorConfig", {})
    if (document.get("key") != key or editor.get("user", {}).get("id") != principal or
            (not editing and (document.get("permissions", {}).get("edit") is not False or editor.get("mode") != "view"))):
        raise HTTPException(403, "编辑凭据与当前连接不一致")


def check_auth(data, key, principal, editing, handshake=False):
    if not isinstance(data, dict):
        raise HTTPException(403, "连接认证格式无效")
    tokens = [data.get("session") or data.get("token")] if handshake else [data.get("jwtSession") or data.get("jwtOpen")]
    for token in tokens:
        check_token(token, key, principal, editing)
    packet = data.get("data") if handshake else data
    if (not isinstance(packet, dict) or packet.get("docid") != key or
            packet.get("user", {}).get("id") != principal):
        raise HTTPException(403, "连接账号不匹配")
    if handshake:
        check_auth(packet, key, principal, editing)


def inspect_frame(frame, key, principal, editing, bound):
    if isinstance(frame, bytes):
        if not bound:
            raise HTTPException(403, "连接尚未认证")
        return bound
    if frame.startswith("40"):
        check_auth(json.loads(frame[2:]), key, principal, editing, handshake=True)
        return True
    if not bound:
        if frame not in {"2", "3", "2probe", "3probe", "5", "1"}:
            raise HTTPException(403, "连接尚未认证")
        return False
    if frame.startswith("42"):
        match = re.fullmatch(r"42[0-9]{0,9}(\[.*\])", frame, re.DOTALL)
        binary = False
    elif frame.startswith("45"):
        match = re.fullmatch(r"45[0-9]{1,3}-[0-9]{0,9}(\[.*\])", frame, re.DOTALL)
        binary = True
    elif frame in {"2", "3", "2probe", "3probe", "5", "1", "41"}:
        return True
    else:
        raise HTTPException(403, "不支持的连接消息")
    if not match:
        raise HTTPException(403, "连接消息格式无效")
    event = json.loads(match[1])
    if not isinstance(event, list) or len(event) != 2 or event[0] != "message":
        raise HTTPException(403, "连接事件无效")
    packet = json.loads(event[1]) if isinstance(event[1], str) else event[1]
    if binary and (not isinstance(packet, dict) or not isinstance(packet.get("type"), str)):
        raise HTTPException(403, "二进制事件必须声明消息类型")
    if isinstance(packet, dict) and packet.get("type") == "auth":
        if binary:
            raise HTTPException(403, "认证不能包含二进制附件")
        check_auth(packet, key, principal, editing)
    return True


@router.api_route("/office/{socket_path:path}", methods=["GET", "HEAD", "POST"])
async def document_http(request: Request, socket_path: str):
    if any(len(request.query_params.getlist(name)) != 1 for name in request.query_params) or any(
            len(request.headers.getlist(name)) > 1 for name in ("authorization", "authorizationjwt", "content-type", "host")):
        raise HTTPException(400, "文档请求参数重复")
    match = DYNAMIC_PATH.fullmatch(socket_path)
    if not match or ".." in socket_path or request.query_params.get("transport") or request.query_params.get("EIO"):
        raise HTTPException(403, "文档连接需要启用 WebSocket，请使用支持 WebSocket 的浏览器和网络")
    key = cache_document_key(match["key"])
    principal, editing = await run_in_threadpool(connection_policy, request.scope, key)
    if match["kind"] in {"upload", "savefile"} and not editing:
        raise HTTPException(403, "只读文档不能上传内容")
    origin = request.headers.get("origin")
    if origin and urlsplit(origin).netloc != request.headers.get("host"):
        raise HTTPException(403, "文档请求来源无效")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > protocol.MAX_BYTES:
            raise HTTPException(413, "文档请求过大")
    tokens = [request.query_params.get("token"), request.headers.get("authorizationjwt", "").removeprefix("Bearer "),
              request.headers.get("authorization", "").removeprefix("Bearer ")]
    commands = [dict(request.query_params)]
    if request.query_params.get("cmd"):
        if len(request.query_params["cmd"]) > 65536:
            raise HTTPException(413, "文档命令过大")
        try:
            commands.append(json.loads(request.query_params["cmd"]))
        except ValueError:
            raise HTTPException(400, "文档命令格式无效") from None
    if body and ("application/json" in request.headers.get("content-type", "") or bytes(body).lstrip().startswith((b"{", b"["))):
        try:
            payload = json.loads(body)
            if not isinstance(payload, dict):
                raise ValueError()
            commands.append(payload)
        except ValueError:
            raise HTTPException(400, "文档请求格式无效") from None
    for command in commands:
        if not isinstance(command, dict):
            raise HTTPException(400, "文档命令格式无效")
        for field in ("id", "key", "docid"):
            if field in command and command[field] != key:
                raise HTTPException(403, "文档命令与连接不一致")
        tokens.extend(command.get(field) for field in ("token", "tokenSession", "tokenDownload", "jwtOpen", "jwtSession"))
    for token in tokens:
        if token:
            await run_in_threadpool(check_token, token, key, principal, editing)
    headers = {name: value for name, value in request.headers.items()
               if name in {"content-type", "range", "authorizationjwt", "authorization"}}
    headers["X-Forwarded-Host"] = request.headers.get("host", "") + "/office"
    headers["X-Forwarded-Proto"] = "https" if request.headers.get("x-forwarded-proto") == "https" else request.url.scheme
    headers["Accept-Encoding"] = "identity"
    target = settings.onlyoffice_internal_url.rstrip("/") + "/" + socket_path
    if request.url.query:
        target += "?" + request.url.query
    client = httpx.AsyncClient(timeout=120, follow_redirects=False, trust_env=False)
    try:
        response = await client.send(client.build_request(request.method, target, content=bytes(body), headers=headers), stream=True)
    except Exception:
        await client.aclose()
        raise HTTPException(502, "文档资源暂时不可用") from None

    async def chunks():
        try:
            async for chunk in response.aiter_raw():
                await run_in_threadpool(connection_policy, request.scope, key, principal, editing)
                yield chunk
        finally:
            await response.aclose()
            await client.aclose()
    safe_headers = {k: v for k, v in response.headers.items()
                    if k in {"content-type", "content-length", "content-disposition", "content-range", "accept-ranges", "content-encoding"}}
    safe_headers["Cache-Control"] = "private, no-store"
    return StreamingResponse(chunks(), status_code=response.status_code, headers=safe_headers)


@router.websocket("/office/{socket_path:path}")
async def document_connection(socket: WebSocket, socket_path: str):
    tasks = []
    try:
        match = SOCKET_PATH.fullmatch(socket_path)
        if not match or socket.query_params.get("transport") != "websocket" or socket.query_params.get("EIO") != "4":
            raise HTTPException(403, "文档连接地址无效")
        origin = socket.headers.get("origin")
        if origin and urlsplit(origin).netloc != socket.headers.get("host"):
            raise HTTPException(403, "文档连接来源无效")
        key = match["key"]
        principal, editing = await run_in_threadpool(connection_policy, socket.scope, key)
        target = settings.onlyoffice_internal_url.rstrip("/")
        target = target.replace("https://", "wss://", 1).replace("http://", "ws://", 1)
        target += "/" + socket_path + "?" + socket.scope.get("query_string", b"").decode("ascii")
        # Never forward application cookies or authorization to the document server.
        async with connect(target, proxy=None, max_size=FRAME_LIMIT, max_queue=16,
                           open_timeout=15, close_timeout=2,
                           additional_headers={"X-Forwarded-Host": socket.headers.get("host", "") + "/office",
                                               "X-Forwarded-Proto": "https" if socket.url.scheme == "wss" or socket.headers.get("x-forwarded-proto") == "https" else "http"}) as upstream:
            await socket.accept()

            async def check():
                await run_in_threadpool(connection_policy, socket.scope, key, principal, editing)

            async def incoming():
                bound = False
                while True:
                    message = await socket.receive()
                    if message["type"] == "websocket.disconnect":
                        return
                    frame = message.get("bytes") if message.get("bytes") is not None else message.get("text", "")
                    await check()
                    bound = inspect_frame(frame, key, principal, editing, bound)
                    await upstream.send(frame)

            async def outgoing():
                async for frame in upstream:
                    await check()
                    if isinstance(frame, bytes):
                        await socket.send_bytes(frame)
                    else:
                        await socket.send_text(frame)

            async def monitor():
                while True:
                    await asyncio.sleep(1)
                    await check()

            tasks = [asyncio.create_task(job()) for job in (incoming, outgoing, monitor)]
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
    except (HTTPException, ValueError, KeyError, TypeError, ConnectionClosed, WebSocketDisconnect, OSError):
        pass  # No tokens, cookies or document traffic in logs/errors.
    finally:
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        try:
            await socket.close(code=1008)
        except (RuntimeError, WebSocketDisconnect):
            pass
