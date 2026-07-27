import json
from uuid import uuid4

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.internal_quote import InternalQuotePricingBaseline
from app.schemas.internal_quote import (
    InternalQuoteFreightBaselineRow,
    InternalQuoteMachineBaselineRow,
    InternalQuoteMaterialBaselineRow,
    InternalQuotePricingBaselineOut,
    InternalQuotePricingBaselineUpdateRequest,
)
from app.services.auth import (
    AuthContext,
    add_auth_audit,
    ensure_permission_in_scope,
    now_text,
)
from app.services.internal_quote_calculator import (
    DEFAULT_FREIGHT,
    DEFAULT_MACHINE_PRICES,
    DEFAULT_MATERIAL_PRICES,
    FREIGHT_ROUTE_DEFINITIONS,
)


BASELINE_DEPARTMENT = "sales-business"
BASELINE_READ_PERMISSION = "internal_quote:baseline_read"
BASELINE_MANAGE_PERMISSION = "internal_quote:baseline_manage"
INITIAL_BASELINE_ID = "IQB-HUAXING-INITIAL"
INITIAL_BASELINE_FACTORY_ID = "huaxing"
INITIAL_BASELINE_WORKSHOP_CODE = "huaxing-workshop"
INITIAL_BASELINE_WORKSHOP_NAME = "华兴"


def _default_material_rows() -> list[InternalQuoteMaterialBaselineRow]:
    return [
        InternalQuoteMaterialBaselineRow(
            material=material,
            grade=grade,
            price_hkd_lb=price,
        )
        for material, grade, price in DEFAULT_MATERIAL_PRICES
    ]


def _default_machine_rows() -> list[InternalQuoteMachineBaselineRow]:
    return [
        InternalQuoteMachineBaselineRow(
            machine_range=machine_range,
            machine=machine,
            shift_price_hkd=price,
        )
        for machine_range, machine, price in DEFAULT_MACHINE_PRICES
    ]


def _default_freight_routes() -> list[InternalQuoteFreightBaselineRow]:
    return [
        InternalQuoteFreightBaselineRow(
            route_key=route_key,
            route_name=label,
            capacity_key=capacity_key,
            freight_hkd=DEFAULT_FREIGHT["cost_hkd"][default_cost_key],
            lifting_hkd="0",
        )
        for route_key, label, capacity_key, _default_capacity_key, default_cost_key
        in FREIGHT_ROUTE_DEFINITIONS
    ]


def _json_rows(value: str, row_type):
    try:
        rows = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        rows = []
    if not isinstance(rows, list):
        return []
    return [row_type.model_validate(row) for row in rows if isinstance(row, dict)]


def _json_freight_routes(value: str) -> list[InternalQuoteFreightBaselineRow]:
    try:
        stored = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        stored = []
    if isinstance(stored, list):
        routes: list[InternalQuoteFreightBaselineRow] = []
        for row in stored:
            if not isinstance(row, dict):
                continue
            try:
                routes.append(InternalQuoteFreightBaselineRow.model_validate(row))
            except ValueError:
                continue
        if routes:
            return routes
    # Compatibility with the initial fixed-key implementation used before the
    # dynamic route list was released.
    if isinstance(stored, dict):
        routes = _default_freight_routes()
        return [
            row.model_copy(update={"freight_hkd": str(stored.get(row.route_key, row.freight_hkd))})
            for row in routes
        ]
    return _default_freight_routes()


def _baseline_out(
    baseline: InternalQuotePricingBaseline | None,
    factory_id: str,
    workshop_code: str,
) -> InternalQuotePricingBaselineOut:
    if baseline is None:
        return InternalQuotePricingBaselineOut(
            factory_id=factory_id,
            workshop_code=workshop_code,
            workshop_name="华兴",
            revision=0,
            source_type="default",
            material_prices=_default_material_rows(),
            machine_prices=_default_machine_rows(),
            freight_routes=_default_freight_routes(),
            updated_by="",
            updated_by_name="",
            updated_at="",
        )
    return InternalQuotePricingBaselineOut(
        factory_id=baseline.factory_id,
        workshop_code=baseline.workshop_code,
        workshop_name=baseline.workshop_name,
        revision=baseline.revision,
        source_type="custom",
        material_prices=_json_rows(
            baseline.material_prices_json,
            InternalQuoteMaterialBaselineRow,
        ),
        machine_prices=_json_rows(
            baseline.machine_prices_json,
            InternalQuoteMachineBaselineRow,
        ),
        freight_routes=_json_freight_routes(baseline.freight_routes_json),
        updated_by=baseline.updated_by,
        updated_by_name=baseline.updated_by_name,
        updated_at=baseline.updated_at,
    )


def _find_baseline(
    db: Session,
    factory_id: str,
    workshop_code: str,
) -> InternalQuotePricingBaseline | None:
    return db.scalar(
        select(InternalQuotePricingBaseline).where(
            InternalQuotePricingBaseline.factory_id == factory_id,
            InternalQuotePricingBaseline.workshop_code == workshop_code,
        )
    )


def seed_internal_quote_pricing_baseline_defaults(db: Session) -> None:
    """Import the accepted Huaxing rr2 baseline once without overwriting user edits."""
    if _find_baseline(
        db,
        INITIAL_BASELINE_FACTORY_ID,
        INITIAL_BASELINE_WORKSHOP_CODE,
    ) is not None:
        return

    timestamp = now_text()
    db.add(
        InternalQuotePricingBaseline(
            id=INITIAL_BASELINE_ID,
            factory_id=INITIAL_BASELINE_FACTORY_ID,
            workshop_code=INITIAL_BASELINE_WORKSHOP_CODE,
            workshop_name=INITIAL_BASELINE_WORKSHOP_NAME,
            material_prices_json=json.dumps(
                [row.model_dump() for row in _default_material_rows()],
                ensure_ascii=False,
                sort_keys=True,
            ),
            machine_prices_json=json.dumps(
                [row.model_dump() for row in _default_machine_rows()],
                ensure_ascii=False,
                sort_keys=True,
            ),
            freight_routes_json=json.dumps(
                [row.model_dump() for row in _default_freight_routes()],
                ensure_ascii=False,
                sort_keys=True,
            ),
            revision=1,
            created_by="system",
            created_by_name="系统导入",
            created_at=timestamp,
            updated_by="system",
            updated_by_name="系统导入",
            updated_at=timestamp,
        )
    )
    db.commit()


def get_pricing_baseline(
    db: Session,
    factory_id: str,
    workshop_code: str,
    user: AuthContext,
) -> InternalQuotePricingBaselineOut:
    ensure_permission_in_scope(
        db,
        user,
        BASELINE_READ_PERMISSION,
        factory_id,
        BASELINE_DEPARTMENT,
    )
    return _baseline_out(_find_baseline(db, factory_id, workshop_code), factory_id, workshop_code)


def update_pricing_baseline(
    db: Session,
    factory_id: str,
    workshop_code: str,
    payload: InternalQuotePricingBaselineUpdateRequest,
    user: AuthContext,
    request: Request | None = None,
) -> InternalQuotePricingBaselineOut:
    ensure_permission_in_scope(
        db,
        user,
        BASELINE_MANAGE_PERMISSION,
        factory_id,
        BASELINE_DEPARTMENT,
    )
    baseline = _find_baseline(db, factory_id, workshop_code)
    current_revision = baseline.revision if baseline is not None else 0
    if payload.revision != current_revision:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "报价基数已被其他人更新，请刷新后重试",
                "current_revision": current_revision,
            },
        )

    timestamp = now_text()
    material_prices_json = json.dumps(
        [row.model_dump() for row in payload.material_prices],
        ensure_ascii=False,
        sort_keys=True,
    )
    machine_prices_json = json.dumps(
        [row.model_dump() for row in payload.machine_prices],
        ensure_ascii=False,
        sort_keys=True,
    )
    freight_routes = (
        payload.freight_routes
        if payload.freight_routes is not None
        else _json_freight_routes(baseline.freight_routes_json if baseline is not None else "[]")
    )
    freight_routes_json = json.dumps(
        [row.model_dump() for row in freight_routes],
        ensure_ascii=False,
        sort_keys=True,
    )
    if baseline is None:
        baseline = InternalQuotePricingBaseline(
            id=f"IQB-{uuid4().hex.upper()}",
            factory_id=factory_id,
            workshop_code=workshop_code,
            workshop_name=payload.workshop_name,
            material_prices_json=material_prices_json,
            machine_prices_json=machine_prices_json,
            freight_routes_json=freight_routes_json,
            revision=1,
            created_by=user.id,
            created_by_name=user.display_name,
            created_at=timestamp,
            updated_by=user.id,
            updated_by_name=user.display_name,
            updated_at=timestamp,
        )
        db.add(baseline)
    else:
        baseline.workshop_name = payload.workshop_name
        baseline.material_prices_json = material_prices_json
        baseline.machine_prices_json = machine_prices_json
        baseline.freight_routes_json = freight_routes_json
        baseline.revision += 1
        baseline.updated_by = user.id
        baseline.updated_by_name = user.display_name
        baseline.updated_at = timestamp

    add_auth_audit(
        db,
        "internal_quote_baseline_updated",
        username=user.username,
        user_id=user.id,
        detail=(
            f"报价基数更新：{factory_id}/{workshop_code}，"
            f"revision {current_revision}->{baseline.revision}，"
            f"材料 {len(payload.material_prices)} 项，机型 {len(payload.machine_prices)} 项，"
            f"运输方案 {len(freight_routes)} 项"
        ),
        request=request,
    )
    db.commit()
    db.refresh(baseline)
    return _baseline_out(baseline, factory_id, workshop_code)
