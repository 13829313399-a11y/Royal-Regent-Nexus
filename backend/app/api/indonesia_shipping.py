"""Session-authenticated, factory-bound adapter for the complete RR-Portal module.

No upstream URL, signing key or upstream bearer token is exposed to the browser.
Business permissions are evaluated explicitly in legacy/shadow/enforce alike.
"""
import base64
import hashlib
import hmac
import json
import time
from urllib.parse import quote, urlsplit

import httpx2 as httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from starlette.background import BackgroundTask
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db
from app.services.auth import AuthContext, authorization_decision, get_current_user
from app.services.permission_codes import INDONESIA_SHIPPING_DOMAINS

router = APIRouter(prefix="/api/indonesia-shipping", tags=["indonesia-shipping"])
FACTORIES = frozenset({"huakang-a", "huakang-b", "huakang-c", "huakang-d", "huadeng", "huaxing"})
API_DOMAINS = {
    "products": "products", "images": "products", "dictionaries": "products",
    "materials": "materials", "customers": "customers", "schedules": "schedules",
    "purchase": "purchase", "material-alerts": "purchase", "quotes": "quotes",
    "molding-pos": "molding", "outbound": "outbound", "shipments": "shipments",
}
READ_METHODS = {"GET", "HEAD"}
SAFE_HEADERS = {"content-type", "content-disposition", "content-range", "accept-ranges", "last-modified", "x-blob-version"}


def allowed(user: AuthContext, factory: str, action: str) -> bool:
    return authorization_decision(user, "indonesia_shipping:" + action, factory, "sales-business")[0]


def authorize(user: AuthContext, factory: str, action: str = "read") -> None:
    if factory not in FACTORIES:
        raise HTTPException(422, "请选择明确的生产厂区")
    if user.force_password_change:
        raise HTTPException(403, "请先完成 Nexus 账号密码修改", headers={"X-Nexus-Shipping-Session": "invalid"})
    if not allowed(user, factory, "read"):
        raise HTTPException(403, "没有当前厂区业务部的印尼走货权限", headers={"X-Nexus-Shipping-Session": "invalid"})
    if not allowed(user, factory, action):
        raise HTTPException(403, "没有当前厂区业务部的印尼走货权限")


def upstream_for(factory: str) -> tuple[str, str]:
    upstream = settings.indonesia_shipping_upstreams.get(factory, "").rstrip("/")
    key = settings.indonesia_shipping_bridge_key.get_secret_value()
    parsed = urlsplit(upstream)
    if (not upstream or parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in {"", "/"} or len(key.encode()) < 32):
        raise HTTPException(503, "当前厂区的印尼走货服务尚未配置")
    # An accidental duplicate binding is never a valid factory fallback.
    endpoints = [value.rstrip("/") for value in settings.indonesia_shipping_upstreams.values()]
    if endpoints.count(upstream) != 1:
        raise HTTPException(503, "印尼走货服务厂区配置重复，请联系管理员")
    return upstream, key


def identity_key(user: AuthContext, session_id: str = "") -> str:
    identity = user.identity or {}
    return hashlib.sha256(json.dumps([user.id, user.authorization_version, identity.get("employment_epoch"), identity.get("identity_version"), identity.get("effective_context_key"), session_id]).encode()).hexdigest()


def session_payload(user: AuthContext, factory: str, session_id: str = "") -> dict:
    return {
        "displayName": user.display_name, "identity": identity_key(user, session_id),
        "userbqrpower": "".join("1" if allowed(user, factory, f"{domain}_read") else "0" for domain in INDONESIA_SHIPPING_DOMAINS),
        "usereditpower": "".join("1" if allowed(user, factory, f"{domain}_read") and allowed(user, factory, f"{domain}_write") else "0" for domain in INDONESIA_SHIPPING_DOMAINS),
        "nexus": True, "factoryId": factory,
        "serverNow": (user.identity or {}).get("server_now"),
        "nextTransitionAt": (user.identity or {}).get("next_transition_at"),
        # Keep a false value for already-loaded clients; historical grants are inert.
        "databaseManage": False,
    }


def bridge_token(user: AuthContext, factory: str, key: str) -> str:
    def encode(value):
        return base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode()).rstrip(b"=")
    now = int(time.time())
    payload = session_payload(user, factory)
    claims = {"iss": "RoyalRegentNexus", "aud": "IndoShippingNexus", "sub": user.id,
              "unique_name": user.username, "nexus_factory": factory, "nexus_bridge": "1",
              "nexus_display_name": user.display_name,
              "nexus_employment_epoch": str((user.identity or {}).get("employment_epoch") or ""),
              "userbqrpower": payload["userbqrpower"], "usereditpower": payload["usereditpower"],
              "iat": now, "nbf": now - 2, "exp": now + 60}
    value = encode({"alg": "HS256", "typ": "JWT"}) + b"." + encode(claims)
    signature = base64.urlsafe_b64encode(hmac.new(key.encode(), value, hashlib.sha256).digest()).rstrip(b"=")
    return (value + b"." + signature).decode()


def required_action(path: str, method: str) -> str:
    # Reject ambiguous paths before httpx/.NET can normalize them differently.
    if "\\" in path or "%" in path or any(p in {".", ".."} for p in path.split("/")) or "//" in path:
        raise HTTPException(400, "无效的模块路径")
    parts = path.lower().strip("/").split("/")
    if parts[0] != "api":
        if method not in READ_METHODS:
            raise HTTPException(405, "静态页面不支持此操作")
        return "read"
    if len(parts) < 2:
        raise HTTPException(404, "接口不存在")
    resource = parts[1]
    if resource in {"session", "health"} and len(parts) == 2 and method in READ_METHODS:
        return "read"
    if resource == "users":
        raise HTTPException(403, "账号和权限统一由 Nexus 管理，原系统账号功能已停用")
    if resource == "db":
        raise HTTPException(403, "原系统数据库管理已停用，请使用对应业务页面维护资料")
    domain = API_DOMAINS.get(resource)
    if domain is None:
        raise HTTPException(403, "接口未注册或不允许独立登录")
    return domain + ("_read" if method in READ_METHODS else "_write")


def csrf_guard(request: Request) -> None:
    if request.method not in READ_METHODS:
        if request.headers.get("x-nexus-shipping") != "1" or request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(403, "请求来源无效，请重新打开印尼走货模块")


def authorize_resource(user: AuthContext, factory: str, path: str, method: str, action: str) -> None:
    authorize(user, factory, action)
    if action.endswith("_write"):
        authorize(user, factory, action.removesuffix("_write") + "_read")
    # The original product workspace requires both product and material bits;
    # details expose full material records, and rename/delete update both domains.
    if path.lower().strip("/").split("/")[:2] == ["api", "products"]:
        authorize(user, factory, "materials_read")
        if method not in READ_METHODS:
            authorize(user, factory, "materials_write")


async def open_upstream(user, factory, path, method="GET", query="", body=b"", headers=None):
    upstream, key = upstream_for(factory)
    client = httpx.AsyncClient(timeout=settings.indonesia_shipping_timeout_seconds, follow_redirects=False, trust_env=False)
    forwarded = {"Authorization": "Bearer " + bridge_token(user, factory, key), "Accept-Encoding": "identity"}
    forwarded.update(headers or {})
    url = upstream + "/" + quote(path, safe="/") + ("?" + query if query else "")
    try:
        response = await client.send(client.build_request(method, url, headers=forwarded, content=body), stream=True)
        return client, response
    except httpx.HTTPError:
        await client.aclose()
        raise HTTPException(503, "印尼走货服务暂时无法连接，请稍后重试") from None


@router.get("/{factory}/status")
async def status(factory: str, request: Request, user: AuthContext = Depends(get_current_user)):
    authorize(user, factory)
    client, response = await open_upstream(user, factory, "api/health")
    try:
        if response.status_code != 200:
            raise HTTPException(503, "印尼走货服务未就绪，请联系管理员")
        return {"ready": True, **session_payload(user, factory, getattr(request.state, "auth_session_id", ""))}
    finally:
        await response.aclose()
        await client.aclose()


@router.api_route("/{factory}/app/{path:path}", methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"])
async def proxy(factory: str, path: str, request: Request, user: AuthContext = Depends(get_current_user), db: Session = Depends(get_db)):
    action = required_action(path, request.method)
    authorize_resource(user, factory, path, request.method, action)
    csrf_guard(request)
    upstream_for(factory)
    if path.lower().rstrip("/") == "api/session":
        return JSONResponse(session_payload(user, factory, getattr(request.state, "auth_session_id", "")), headers={"Cache-Control": "no-store"})
    if path.lower().startswith("api/") and request.headers.get("x-nexus-shipping-identity") != identity_key(user, getattr(request.state, "auth_session_id", "")):
        raise HTTPException(409, "账号或权限已变化，请刷新印尼走货工作区后重试", headers={"X-Nexus-Shipping-Session": "invalid"})
    # Do not hold the initial authentication snapshot while a client uploads a file.
    db.rollback()
    limit = settings.indonesia_shipping_max_upload_mb * 1024 * 1024
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > limit:
            raise HTTPException(413, "文件超过印尼走货模块上传大小限制")
        body.extend(chunk)
    try:
        user = get_current_user(request, db)
        authorize_resource(user, factory, path, request.method, action)
        if path.lower().startswith("api/") and request.headers.get("x-nexus-shipping-identity") != identity_key(user, getattr(request.state, "auth_session_id", "")):
            raise HTTPException(409, "账号或权限已变化，请刷新印尼走货工作区后重试", headers={"X-Nexus-Shipping-Session": "invalid"})
    finally:
        db.rollback()
    headers = {name: request.headers[name] for name in ("content-type", "accept", "range", "if-modified-since", "x-expected-version") if name in request.headers}
    client, response = await open_upstream(user, factory, path, request.method, request.url.query, bytes(body), headers)
    async def close():
        await response.aclose()
        await client.aclose()
    output_headers = {name: value for name, value in response.headers.items() if name.lower() in SAFE_HEADERS}
    output_headers.update({"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "X-Frame-Options": "SAMEORIGIN"})
    # Never relay redirects, upstream cookies, auth headers or absolute upstream URLs.
    if 300 <= response.status_code < 400 and response.status_code != 304:
        await close()
        raise HTTPException(502, "印尼走货服务返回了无效跳转")
    if "text/html" in response.headers.get("content-type", "") and request.method == "GET":
        content = (await response.aread()).decode("utf-8")
        await close()
        base = f"/api/indonesia-shipping/{factory}/app/"
        content = content.replace("<head>", f'<head><base href="{base}"><meta name="nexus-shipping-base" content="{base}">', 1)
        output_headers["Content-Security-Policy"] = "frame-ancestors 'self'; object-src 'none'; base-uri 'self'"
        return Response(content, status_code=response.status_code, headers=output_headers)
    return StreamingResponse(response.aiter_raw(), status_code=response.status_code, headers=output_headers, background=BackgroundTask(close))
