import logging
import re
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError

from app.api.auth import router as auth_router
from app.api.document_tools import router as document_tools_router
from app.api.pdf_rename import router as pdf_rename_router
from app.api.carton_mark import router as carton_mark_router
from app.api.carton_procurement import router as carton_procurement_router
from app.api.carton_supplier_settlement import router as carton_supplier_settlement_router
from app.api.carton_supplier_portal import router as carton_supplier_portal_router
from app.api.customer_order import router as customer_order_router
from app.api.customer_order_ledger import router as customer_order_ledger_router
from app.api.directory import router as directory_router
from app.api.iam import router as iam_router
from app.api.identity import router as identity_router
from app.api.indonesia_invoice import router as indonesia_invoice_router
from app.api.injection_scheduling import router as injection_scheduling_router
from app.api.customer_price_settings import router as customer_price_settings_router
from app.api.internal_quote import (
    customer_price_artifact_router,
)
from app.api.internal_quote import (
    router as internal_quote_router,
)
from app.api.molding_sample import router as molding_sample_router
from app.api.pricing import router as pricing_router
from app.api.qc_inspection import router as qc_inspection_router
from app.api.raw_material import router as raw_material_router
from app.api.system import router as system_router
from app.api.work_center import router as work_center_router
from app.api.three_d_connector import router as three_d_connector_router
from app.api.three_d_printing import router as three_d_printing_router
from app.api.spray_operations import router as spray_operations_router
from app.api.uv_operations import router as uv_operations_router
from app.api.uv_agent import router as uv_agent_router
from app.core.config import settings
from app.db import init_db

request_timing_logger = logging.getLogger("uvicorn.error")
sweep_logger = logging.getLogger("app.three_d_sweep")


def sweep_three_d_open_runs(*, boot=False) -> None:
    """Settle auto runs whose printer already finished without a terminal event.

    `boot=True` is the start-up/reconnect settlement: a run left open by a crash or a
    long outage is closed from the full status the Connector pushes on connect.
    """
    from app.core.time import business_now
    from app.db import SessionLocal
    from app.services.three_d_connector import FACTORY
    from app.services.three_d_run_reconciliation import sweep_open_runs

    with SessionLocal() as db:
        try:
            result = sweep_open_runs(
                db,
                factory_id=FACTORY,
                now=business_now(),
                actor="system:boot-sweep" if boot else "system:state-sweep",
                ignore_state_since=boot,
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
    if result.settled or result.settled_for_other_job or result.stale_open:
        sweep_logger.info("three_d_state_sweep %s", result.as_dict())


async def three_d_sweep_loop() -> None:
    import asyncio

    # One immediate settlement pass at start-up, then the periodic sweep.
    try:
        await asyncio.to_thread(sweep_three_d_open_runs, boot=True)
    except Exception:
        sweep_logger.warning("three_d_boot_sweep_failed", exc_info=True)
    interval = max(15, settings.three_d_reconciliation_sweep_seconds)
    while True:
        try:
            await asyncio.to_thread(sweep_three_d_open_runs)
        except asyncio.CancelledError:
            raise
        except Exception:
            sweep_logger.warning("three_d_state_sweep_failed", exc_info=True)
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio

    init_db()
    from app.services.three_d_live import hub
    hub.start()
    sweep_task = asyncio.create_task(three_d_sweep_loop())
    from app.services.three_d_telemetry_rollups import worker as telemetry_rollup_worker
    rollup_task = asyncio.create_task(telemetry_rollup_worker())
    from app.services.uv_operations.exports import worker as uv_export_worker
    uv_export_task = asyncio.create_task(uv_export_worker()) if settings.uv_ops_enabled else None
    from app.services.identity_outbox import worker as identity_worker
    identity_task = asyncio.create_task(identity_worker()) if settings.iam_identity_writes_enabled else None
    try:
        yield
    finally:
        rollup_task.cancel()
        try:
            await rollup_task
        except asyncio.CancelledError:
            pass
        if identity_task:
            identity_task.cancel()
            try:
                await identity_task
            except asyncio.CancelledError:
                pass
        if uv_export_task:
            uv_export_task.cancel()
            try:
                await uv_export_task
            except asyncio.CancelledError:
                pass
        sweep_task.cancel()
        try:
            await sweep_task
        except asyncio.CancelledError:
            pass
        await hub.stop()


app = FastAPI(title=settings.app_name, lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def handle_request_validation_error(
    request: Request,
    exc: RequestValidationError,
):
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
app.include_router(document_tools_router)
app.include_router(pdf_rename_router)
app.include_router(carton_mark_router)
app.include_router(carton_procurement_router)
app.include_router(carton_supplier_settlement_router)
app.include_router(carton_supplier_portal_router)
app.include_router(customer_order_router)
app.include_router(customer_order_ledger_router)
app.include_router(directory_router)
app.include_router(internal_quote_router)
app.include_router(customer_price_artifact_router)
app.include_router(customer_price_settings_router)
app.include_router(indonesia_invoice_router)
app.include_router(injection_scheduling_router)
app.include_router(iam_router)
app.include_router(identity_router)
app.include_router(molding_sample_router)
app.include_router(pricing_router)
app.include_router(raw_material_router)
app.include_router(qc_inspection_router)
app.include_router(system_router)
app.include_router(work_center_router)
from app.api.three_d_operations import router as three_d_operations_router
app.include_router(three_d_operations_router)
app.include_router(three_d_printing_router)
app.include_router(spray_operations_router)
app.include_router(uv_operations_router)
app.include_router(uv_agent_router)
app.include_router(three_d_connector_router)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}
