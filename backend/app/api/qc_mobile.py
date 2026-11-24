"""Scoped phone entry: a one-use QR grants inspection access, never a Nexus session."""
import asyncio
import base64
import hashlib
import io
import json
import re
import secrets
import socket
import sqlite3
import time
from contextlib import contextmanager
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db
from app.models.auth import AuthSession
from app.services.auth import get_current_user, authenticated_session_user
from app.api.qc_inspection import _ensure_permission
from app.api.qc_department import COMPANIES, ASSETS, NO_CACHE, inspection_sheet_request, upstream
from app.services import qc_inspection_sheet

router = APIRouter(prefix="/api/qc-mobile", tags=["qc-mobile"])
COOKIE = "qc_mobile_session"
TTL = 8 * 60 * 60
TOKEN = re.compile(r"^[A-Za-z0-9_-]{43}$")
HEADERS = {**NO_CACHE, "Referrer-Policy": "no-referrer"}
MOBILE_ASSETS = frozenset({"index.html", "app.js", "app.css", "icon.svg", "remote.js", "qc-photo-shapes.js"})
MOBILE_READY = {"service": "qc-mobile", "ready": True}
DNS_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"


def production():
    return settings.app_env.strip().lower() in {"production", "prod"}


def configured_origin():
    origin = settings.qc_mobile_public_origin.strip().rstrip("/")
    try:
        parsed = urlsplit(origin)
        port = parsed.port
    except ValueError as exc:
        raise HTTPException(503, "移动验货访问地址配置不正确") from exc
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.path
            or any(sign in origin for sign in "?#") or parsed.username is not None or port == 0):
        raise HTTPException(503, "移动验货访问地址尚未配置或不正确")
    if production():
        host = parsed.hostname
        try:
            address = ip_address(host)
        except ValueError:
            valid_host = (len(host) <= 253 and re.fullmatch(rf"(?:{DNS_LABEL}\.)+{DNS_LABEL}", host)
                          and not host.rsplit(".", 1)[1].isdigit() and not host.endswith((".local", ".localhost")))
        else:
            valid_host = address.version == 4 and address.is_global and not address.is_multicast and not address.is_reserved
        if parsed.scheme != "https" or port not in (None, 443) or not valid_host:
            raise HTTPException(503, "正式移动验货需要配置 HTTPS 域名或固定公网 IPv4，请联系管理员")
        origin = f"https://{host}"
    return origin, parsed


def production_request_origin(request):
    origin, parsed = configured_origin()
    # The outer gateway terminates TLS. Match its preserved Host to the
    # configured authority, without trusting client-supplied forwarding headers.
    if request.headers.get("host", "").lower() not in {parsed.hostname, f"{parsed.hostname}:443"}:
        raise HTTPException(503, "请从公司正式 HTTPS 地址打开验货台并重新扫码")
    return origin


def ready_assets():
    if not all(mobile_asset_path(name).is_file() for name in MOBILE_ASSETS):
        raise HTTPException(503, "移动验货页面资源不完整，请联系管理员")


async def production_dependencies_ready(factory=None):
    ready_assets()
    required = {COMPANIES[factory]} if factory else set(COMPANIES.values())
    try:
        # /api/health is public on the private sidecar and cannot detect
        # mismatched gateway credentials. Companies is protected and read-only.
        result = await asyncio.wait_for(upstream("GET", "api/companies", [], b""), timeout=2)
        if result.status_code == 200:
            companies = result.json().get("companies")
            if isinstance(companies, list):
                available = {item["id"] for item in companies if isinstance(item, dict) and isinstance(item.get("id"), str)}
                if required <= available:
                    return
    except (HTTPException, TimeoutError, ValueError, AttributeError):
        pass
    raise HTTPException(503, "QC 验货服务暂时不可用，请稍后重试")


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


@contextmanager
def store():
    folder = Path(settings.qc_department_data_dir) / "_mobile"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "pairings.sqlite3"
    with sqlite3.connect(path, timeout=10) as conn:
        path.chmod(0o600)
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE IF NOT EXISTS grants (id TEXT PRIMARY KEY, ticket_hash TEXT UNIQUE, session_hash TEXT UNIQUE, parent_session TEXT NOT NULL, actor TEXT NOT NULL, auth_version INTEGER NOT NULL, factory TEXT NOT NULL, ticket_expires REAL NOT NULL, session_expires REAL NOT NULL DEFAULT 0, claimed INTEGER NOT NULL DEFAULT 0)")
        conn.execute("DELETE FROM grants WHERE ticket_expires < ? AND session_expires < ?", (time.time(), time.time()))
        conn.commit()
        yield conn


async def body(request, limit=4096):
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403, "不接受跨站写入")
    origin = request.headers.get("origin")
    expected = production_request_origin(request) if production() else str(request.base_url).rstrip("/")
    if origin and origin != expected:
        raise HTTPException(403, "请求来源不匹配")
    if request.headers.get("content-type", "").split(";")[0].lower() != "application/json":
        raise HTTPException(415, "请使用 JSON 提交")
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > limit:
            raise HTTPException(413, "提交内容过大")
    request._body = bytes(raw)
    try:
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError()
        return result
    except (ValueError, UnicodeError):
        raise HTTPException(400, "无效 JSON") from None


def validate(grant, db, request):
    parent = db.get(AuthSession, grant["parent_session"])
    user = authenticated_session_user(db, parent, method=request.method, path=request.url.path)
    if user.id != grant["actor"] or user.authorization_version != grant["auth_version"]:
        raise HTTPException(401, "账号权限已变化，请重新扫码")
    _ensure_permission(db, user, "qc_inspection:read", grant["factory"])
    _ensure_permission(db, user, "qc_inspection:result_write", grant["factory"])
    return user


def phone(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get(COOKIE, "")
    if not TOKEN.fullmatch(token):
        raise HTTPException(401, "请从验货台重新扫码")
    with store() as conn:
        grant = conn.execute("SELECT * FROM grants WHERE session_hash=? AND session_expires>?", (digest(token), time.time())).fetchone()
    if not grant:
        raise HTTPException(401, "移动验货已过期，请重新扫码")
    return dict(grant), validate(grant, db, request)


async def check_lan_entry(parsed, port):
    """Check only the dedicated HTTP listener on a locally assigned private IP."""
    host = parsed.hostname
    if host == "localhost" or host.endswith(".localhost"):
        raise HTTPException(503, "手机不能访问电脑的本机地址，请配置当前局域网地址")
    try:
        address = ip_address(host)
    except ValueError:
        # Named addresses are not the optional local-listener configuration.
        return
    if address.is_loopback or address.is_unspecified:
        raise HTTPException(503, "手机不能访问电脑的本机地址，请配置当前局域网地址")
    if parsed.scheme != "http" or not address.is_private:
        return
    family = socket.AF_INET6 if address.version == 6 else socket.AF_INET
    try:
        with socket.socket(family) as probe:
            probe.bind((host, 0))
    except OSError as exc:
        raise HTTPException(503, "移动验货地址已不在这台电脑上，请更新 Wi-Fi 地址后重启") from exc
    authority = f"[{address}]" if address.version == 6 else str(address)
    try:
        async with httpx.AsyncClient(timeout=1.5, trust_env=False, follow_redirects=False) as client:
            response = await client.get(f"http://{authority}:{port or 80}/api/qc-mobile/ready")
            response.raise_for_status()
            if response.json() == MOBILE_READY:
                return
    except (httpx.HTTPError, ValueError):
        pass
    raise HTTPException(503, "手机专用服务未就绪，请确认移动验货服务已启动")


@router.post("/pairings")
async def create_pairing(request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    data = await body(request)
    if set(data) != {"factory"} or data["factory"] not in COMPANIES:
        raise HTTPException(422, "请选择有效厂区")
    factory = data["factory"]
    _ensure_permission(db, user, "qc_inspection:read", factory)
    _ensure_permission(db, user, "qc_inspection:result_write", factory)
    origin, parsed = configured_origin()
    if production():
        await production_dependencies_ready(factory)
    else:
        await check_lan_entry(parsed, parsed.port)
    import qrcode
    token, pairing_id = secrets.token_urlsafe(32), secrets.token_hex(16)
    expires = time.time() + 300
    with store() as conn:
        conn.execute("DELETE FROM grants WHERE parent_session=? AND factory=? AND claimed=0", (request.state.auth_session_id, factory))
        conn.execute("INSERT INTO grants(id,ticket_hash,parent_session,actor,auth_version,factory,ticket_expires) VALUES(?,?,?,?,?,?,?)", (pairing_id, digest(token), request.state.auth_session_id, user.id, user.authorization_version, factory, expires))
    url = origin + "/api/qc-mobile/app/#pair=" + token
    output = io.BytesIO()
    qrcode.make(url).save(output, format="PNG")
    return JSONResponse({"id": pairing_id, "url": url, "qr": "data:image/png;base64," + base64.b64encode(output.getvalue()).decode(), "expiresAt": expires, "factory": factory, "actor": user.display_name or user.username}, headers=HEADERS)


@router.get("/health")
async def production_health(request: Request):
    if not production():
        raise HTTPException(404, "仅用于正式 HTTPS 入口检查")
    try:
        production_request_origin(request)
        await production_dependencies_ready()
    except HTTPException as exc:
        return JSONResponse({"service": "qc-mobile", "ready": False}, status_code=exc.status_code, headers=HEADERS)
    return JSONResponse(MOBILE_READY, headers=HEADERS)


@router.post("/exchange")
async def exchange(request: Request, db: Session = Depends(get_db)):
    data = await body(request)
    if set(data) != {"ticket"} or not isinstance(data["ticket"], str) or not TOKEN.fullmatch(data["ticket"]):
        raise HTTPException(422, "二维码无效，请重新生成")
    token = secrets.token_urlsafe(32)
    with store() as conn:
        conn.execute("BEGIN IMMEDIATE")
        grant = conn.execute("SELECT * FROM grants WHERE ticket_hash=? AND claimed=0 AND ticket_expires>?", (digest(data["ticket"]), time.time())).fetchone()
        if not grant:
            raise HTTPException(401, "二维码已使用或过期，请在电脑重新生成")
        validate(grant, db, request)
        conn.execute("UPDATE grants SET claimed=1,session_hash=?,session_expires=? WHERE id=?", (digest(token), time.time()+TTL, grant["id"]))
    response = JSONResponse({"ok": True}, headers=HEADERS)
    response.set_cookie(COOKIE, token, max_age=TTL, path="/api/qc-mobile", httponly=True, samesite="strict", secure=production() or settings.effective_session_cookie_secure)
    return response


@router.get("/context")
def context(auth=Depends(phone)):
    grant, user = auth
    return JSONResponse({"factory": grant["factory"], "actor": {"id": user.id, "name": user.display_name or user.username}, "scope": grant["id"], "expiresAt": grant["session_expires"]}, headers=HEADERS)


@router.post("/logout")
async def logout(request: Request, auth=Depends(phone)):
    await body(request)
    with store() as conn:
        conn.execute("DELETE FROM grants WHERE id=?", (auth[0]["id"],))
    response = JSONResponse({"ok": True}, headers=HEADERS)
    response.delete_cookie(COOKIE, path="/api/qc-mobile")
    return response


@router.api_route("/sheet/{path:path}", methods=["GET", "POST"])
async def sheet(path: str, request: Request, db: Session = Depends(get_db), auth=Depends(phone)):
    grant, user = auth
    permitted = (request.method == "GET" and (path in {"entries", "options"} or re.fullmatch(r"entries/[^/]+(?:/photos/[^/]+|/photo-info)?", path))) or (request.method == "POST" and re.fullmatch(r"entries/[^/]+/(save|photos|remove-photo|submit|photo-annotations)", path))
    if not permitted:
        raise HTTPException(404, "移动验货未开放此操作")
    if request.method == "POST":
        payload = await body(request, 15*1024*1024 if path.endswith("/photos") else 1024*1024)
    if request.method == "GET" and re.fullmatch(r"entries/[^/]+", path):
        with qc_inspection_sheet.store() as conn:
            item = qc_inspection_sheet.unpack(conn, qc_inspection_sheet.get(conn, grant["factory"], path.split('/')[1]))
        return JSONResponse(item, headers=HEADERS)
    response = await inspection_sheet_request(path, request, db, user, grant["factory"])
    if request.method == 'POST' and path.endswith('/photos'):
        with qc_inspection_sheet.store() as conn:
            photo = conn.execute('SELECT id FROM photos WHERE entry_id=? AND origin=?', (path.split('/')[1], 'upload:'+payload['requestKey'])).fetchone()
        data = json.loads(response.body)
        data['uploadedPhotoId'] = photo['id'] if photo else None
        return JSONResponse(data, headers=HEADERS)
    return response


def mobile_asset_path(name):
    return ASSETS / name if name == "qc-photo-shapes.js" else ASSETS / "mobile-inspection" / name


@router.get("/app/{asset:path}")
def app_asset(asset: str):
    name = asset or "index.html"
    if name not in MOBILE_ASSETS:
        raise HTTPException(404, "资源不存在")
    return FileResponse(mobile_asset_path(name), headers={**HEADERS, "X-Frame-Options": "DENY", "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"})
