import re
from datetime import date, timedelta
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.time import business_now
from app.db import get_db
from app.schemas.injection_scheduling_phase5 import (
    InjectionSchedulingAnalyticsOverviewOut,
    InjectionSchedulingCalibrationRequest,
    InjectionSchedulingCalibrationResult,
    InjectionSchedulingDeviceBatchResult,
    InjectionSchedulingDeviceEventBatch,
    InjectionSchedulingErpSyncBatch,
    InjectionSchedulingErpSyncResult,
)
from app.services.auth import (
    AuthContext,
    ensure_permission_in_scope,
    get_current_user,
    has_permission_in_scope,
)
from app.services.injection_scheduling import (
    SCHEDULING_DEPARTMENTS,
    require_injection_scheduling_factory,
)
from app.services.injection_scheduling_phase5 import (
    analytics_overview,
    ingest_device_events,
    rebuild_speed_models,
    sync_erp_orders,
)

router = APIRouter(prefix="/api/injection-scheduling", tags=["injection-scheduling"])

DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[AuthContext, Depends(get_current_user)]


def _request_id(request: Request) -> str:
    supplied = request.headers.get("x-request-id", "").strip()
    if re.fullmatch(r"[A-Za-z0-9._-]{1,128}", supplied):
        return supplied
    return uuid4().hex


def _ensure_permission(
    db: Session, user: AuthContext, permission: str, factory_id: str
) -> str:
    factory_id = require_injection_scheduling_factory(factory_id)
    if any(
        has_permission_in_scope(user, permission, factory_id, department)
        for department in SCHEDULING_DEPARTMENTS
    ):
        return factory_id
    ensure_permission_in_scope(
        db, user, permission, factory_id, SCHEDULING_DEPARTMENTS[0]
    )
    return factory_id


@router.post(
    "/integrations/erp/order-batches",
    response_model=InjectionSchedulingErpSyncResult,
)
def post_erp_order_batch(
    payload: InjectionSchedulingErpSyncBatch,
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
):
    _ensure_permission(
        db, current_user, "injection_scheduling:import", payload.factory_id
    )
    return sync_erp_orders(db, payload, current_user, _request_id(request))


@router.post(
    "/integrations/devices/production-events",
    response_model=InjectionSchedulingDeviceBatchResult,
)
def post_device_production_events(
    payload: InjectionSchedulingDeviceEventBatch,
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
):
    _ensure_permission(
        db, current_user, "injection_scheduling:report", payload.factory_id
    )
    return ingest_device_events(db, payload, current_user, _request_id(request))


@router.post(
    "/calibration/speed-models/rebuild",
    response_model=InjectionSchedulingCalibrationResult,
)
def post_speed_model_rebuild(
    payload: InjectionSchedulingCalibrationRequest,
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
):
    _ensure_permission(
        db, current_user, "injection_scheduling:manage_rules", payload.factory_id
    )
    return rebuild_speed_models(db, payload, current_user, _request_id(request))


@router.get(
    "/analytics/overview",
    response_model=InjectionSchedulingAnalyticsOverviewOut,
)
def get_analytics_overview(
    factory_id: str,
    db: DbSession,
    current_user: CurrentUser,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
):
    factory_id = _ensure_permission(
        db, current_user, "injection_scheduling:read", factory_id
    )
    resolved_to = date_to or business_now().date()
    resolved_from = date_from or (resolved_to - timedelta(days=29))
    return analytics_overview(db, factory_id, resolved_from, resolved_to)
