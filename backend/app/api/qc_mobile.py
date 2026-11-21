"""Scoped phone entry: a one-use QR grants inspection access, never a Nexus session."""
import base64
import hashlib
import io
import json
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db
from app.models.auth import AuthSession
from app.services.auth import get_current_user, authenticated_session_user
from app.api.qc_inspection import _ensure_permission
from app.api.qc_department import COMPANIES, ASSETS, NO_CACHE, inspection_sheet_request
from app.services import qc_inspection_sheet

router = APIRouter(prefix="/api/qc-mobile", tags=["qc-mobile"])
COOKIE = "qc_mobile_session"
TTL = 8 * 60 * 60
TOKEN = re.compile(r"^[A-Za-z0-9_-]{43}$")
HEADERS = {**NO_CACHE, "Referrer-Policy": "no-referrer"}


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
    if origin and origin != str(request.base_url).rstrip("/"):
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


@router.post("/pairings")
async def create_pairing(request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    data = await body(request)
    if set(data) != {"factory"} or data["factory"] not in COMPANIES:
        raise HTTPException(422, "请选择有效厂区")
    factory = data["factory"]
    _ensure_permission(db, user, "qc_inspection:read", factory)
    _ensure_permission(db, user, "qc_inspection:result_write", factory)
    origin = settings.qc_mobile_public_origin.rstrip("/")
    parsed = urlsplit(origin)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.path or parsed.query or parsed.fragment or parsed.username:
        raise HTTPException(503, "移动验货访问地址尚未配置")
    if settings.app_env == "production" and parsed.scheme != "https":
        raise HTTPException(503, "正式移动验货需要 HTTPS 地址")
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
    response.set_cookie(COOKIE, token, max_age=TTL, path="/api/qc-mobile", httponly=True, samesite="strict", secure=settings.effective_session_cookie_secure)
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


@router.get("/app/{asset:path}")
def app_asset(asset: str):
    name = asset or "index.html"
    if name not in {"index.html", "app.js", "app.css", "icon.svg", "remote.js", "qc-photo-shapes.js"}:
        raise HTTPException(404, "资源不存在")
    target = ASSETS / name if name == "qc-photo-shapes.js" else ASSETS / "mobile-inspection" / name
    return FileResponse(target, headers={**HEADERS, "X-Frame-Options": "DENY", "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"})
