import logging
import re
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.ai import router as ai_router
from app.api.ai_actions import router as ai_actions_router
from app.api.auth import router as auth_router
from app.api.carton_mark import router as carton_mark_router
from app.api.carton_procurement import router as carton_procurement_router
from app.api.customer_order import router as customer_order_router
from app.api.iam import router as iam_router
from app.api.indonesia_invoice import router as indonesia_invoice_router
from app.api.injection_scheduling import router as injection_scheduling_router
from app.api.injection_scheduling_execution import (
    router as injection_scheduling_execution_router,
)
from app.api.injection_scheduling_export import (
    router as injection_scheduling_export_router,
)
from app.api.injection_scheduling_import import (
    router as injection_scheduling_import_router,
)
from app.api.injection_scheduling_matching import (
    router as injection_scheduling_matching_router,
)
from app.api.injection_scheduling_phase5 import (
    router as injection_scheduling_phase5_router,
)
from app.api.injection_scheduling_profiles import (
    router as injection_scheduling_profiles_router,
)
from app.api.injection_scheduling_scheduler import (
    router as injection_scheduling_scheduler_router,
)
from app.api.injection_scheduling_shared import (
    router as injection_scheduling_shared_router,
)
from app.api.internal_quote import (
    customer_price_artifact_router,
)
from app.api.internal_quote import (
    router as internal_quote_router,
)
from app.api.molding_sample import router as molding_sample_router
from app.api.pricing import router as pricing_router
from app.api.raw_material import router as raw_material_router
from app.api.qc_inspection import router as qc_inspection_router
from app.api.system import router as system_router
from app.api.three_d_printing import router as three_d_printing_router
from app.api.tools import router as tools_router
from app.core.config import settings
from app.db import init_db

request_timing_logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def handle_request_validation_error(
    request: Request,
    exc: RequestValidationError,
):
    if request.url.path == "/api/ai/responses":
        return JSONResponse(
            status_code=422,
            content={
                "detail": {
                    "code": "AI_INVALID_REQUEST",
                    "message": "请求格式不正确，请检查消息内容后重试。",
                    "retryable": False,
                }
            },
        )
    return await request_validation_exception_handler(request, exc)


@app.middleware("http")
async def record_request_timing(request: Request, call_next):
    started_at = perf_counter()
    supplied_request_id = request.headers.get("x-request-id", "").strip()
    request_id = (
        supplied_request_id
        if re.fullmatch(r"[A-Za-z0-9._-]{1,128}", supplied_request_id)
        else uuid4().hex
    )
    request.state.request_id = request_id
    response = None
    content_length = request.headers.get("content-length", "")
    if (
        request.url.path == "/api/ai/responses"
        and content_length.isdecimal()
        and int(content_length) > settings.ai_max_request_bytes
    ):
        response = JSONResponse(
            status_code=413,
            content={
                "detail": {
                    "code": "AI_REQUEST_TOO_LARGE",
                    "message": "AI 请求内容超过允许上限，请减少图片后重试。",
                    "retryable": False,
                }
            },
        )

    if response is None:
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (perf_counter() - started_at) * 1000
            request_timing_logger.error(
                "request_timing method=%s path=%s status=500 duration_ms=%.2f request_id=%s",
                request.method,
                request.url.path,
                duration_ms,
                request_id,
            )
            raise

    duration_ms = (perf_counter() - started_at) * 1000
    response.headers["X-Request-ID"] = request_id
    response.headers["Server-Timing"] = f"app;dur={duration_ms:.2f}"
    if request.url.path.startswith("/api/ai/"):
        response.headers["Cache-Control"] = "private, no-store, no-transform"
    if request.url.path == "/api/ai/responses":
        response.headers["X-Accel-Buffering"] = "no"
    if request.url.path != "/health":
        route = request.scope.get("route")
        route_path = getattr(route, "path", request.url.path)
        request_timing_logger.info(
            "request_timing method=%s path=%s status=%s duration_ms=%.2f request_id=%s",
            request.method,
            route_path,
            response.status_code,
            duration_ms,
            request_id,
        )
    return response


app.include_router(auth_router)
app.include_router(ai_router)
app.include_router(ai_actions_router)
app.include_router(carton_mark_router)
app.include_router(carton_procurement_router)
app.include_router(customer_order_router)
app.include_router(internal_quote_router)
app.include_router(customer_price_artifact_router)
app.include_router(indonesia_invoice_router)
app.include_router(injection_scheduling_router)
app.include_router(injection_scheduling_execution_router)
app.include_router(injection_scheduling_export_router)
app.include_router(injection_scheduling_import_router)
app.include_router(injection_scheduling_matching_router)
app.include_router(injection_scheduling_scheduler_router)
app.include_router(injection_scheduling_phase5_router)
app.include_router(injection_scheduling_profiles_router)
app.include_router(injection_scheduling_shared_router)
app.include_router(iam_router)
app.include_router(molding_sample_router)
app.include_router(pricing_router)
app.include_router(raw_material_router)
app.include_router(qc_inspection_router)
app.include_router(system_router)
app.include_router(three_d_printing_router)
app.include_router(tools_router)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}
