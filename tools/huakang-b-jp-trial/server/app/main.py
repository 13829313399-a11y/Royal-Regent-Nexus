"""Loopback-only host for the independent Huakang B JP trial."""
from contextlib import asynccontextmanager
from pathlib import Path
from threading import BoundedSemaphore

from fastapi import FastAPI, HTTPException
from starlette.responses import JSONResponse
from starlette.staticfiles import StaticFiles

from app.db import Database

MAX_REQUEST_BYTES = 55 * 1024**2


class LocalBoundary:
    def __init__(self, app, authority):
        self.app = app
        self.authority = authority
        self.origin = "http://" + authority

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = scope.get("headers", [])
        hosts = [v.decode("latin-1") for k, v in headers if k.lower() == b"host"]
        origins = [v.decode("latin-1") for k, v in headers if k.lower() == b"origin"]
        if hosts != [self.authority] or (origins and origins != [self.origin]) or scope["method"] == "OPTIONS":
            return await JSONResponse({"detail": "请从本机试用版启动后打开的页面操作。"}, status_code=403)(scope, receive, send)
        lengths = [v for k, v in headers if k.lower() == b"content-length"]
        try:
            size = int(lengths[0]) if len(lengths) == 1 else 0
        except ValueError:
            size = -1
        if len(lengths) > 1 or size < 0 or size > MAX_REQUEST_BYTES:
            return await JSONResponse({"detail": "上传内容不可超过 55MB。"}, status_code=413)(scope, receive, send)
        consumed = 0

        async def bounded_receive():
            nonlocal consumed
            message = await receive()
            if message["type"] == "http.request":
                consumed += len(message.get("body", b""))
                if consumed > MAX_REQUEST_BYTES:
                    raise HTTPException(413, "上传内容不可超过 55MB。")
            return message

        async def private_send(message):
            if message["type"] == "http.response.start":
                message = dict(message)
                response_headers = list(message.get("headers", []))
                response_headers += [(b"x-content-type-options", b"nosniff"), (b"referrer-policy", b"no-referrer")]
                if scope["path"].startswith("/api/"):
                    response_headers.append((b"cache-control", b"no-store"))
                message["headers"] = response_headers
            await send(message)

        await self.app(scope, bounded_receive, private_send)


def create_app(data_dir, static_dir=None, host="127.0.0.1", port=8765):
    if host != "127.0.0.1" or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("单机试用版仅支持 127.0.0.1 本地端口。")
    database = Database(data_dir)

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            database.close()

    application = FastAPI(title="华康 B JP 问单单机试用", docs_url=None, redoc_url=None,
        openapi_url=None, lifespan=lifespan)
    application.state.database = database
    application.state.job_directory = Path(data_dir).resolve() / "tmp"
    application.state.job_directory.mkdir(parents=True, exist_ok=True)
    application.state.job_slot = BoundedSemaphore(1)
    application.add_middleware(LocalBoundary, authority=f"{host}:{port}")

    @application.get("/api/health")
    def health():
        return {"status": "ok", "service": "huakang-b-jp-trial", "schema": 1}

    from app.api.huakang_b_jp import router
    application.include_router(router)
    if static_dir is not None:
        directory = Path(static_dir).resolve()
        if not (directory / "index.html").is_file():
            database.close()
            raise RuntimeError("缺少试用页面文件，请重新完整解压试用包。")
        application.mount("/", StaticFiles(directory=directory, html=True), name="web")
    return application
