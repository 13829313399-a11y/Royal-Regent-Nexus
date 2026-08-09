from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest
from app.core.time import business_now
from app.db import Base
from app.models import injection_scheduling_import  # noqa: F401
from app.models.injection_scheduling_execution import (
    InjectionSchedulingOrder,
)
from app.models.injection_scheduling_shared import (
    InjectionSchedulingLegacyMoldCopyBinding,
    InjectionSchedulingMoldReservation,
    InjectionSchedulingPhysicalMoldAsset,
    InjectionSchedulingRolloutPolicy,
)
from app.services.injection_scheduling_execution import (
    _physical_asset_for_new_task,
    _release_task_reservation,
)
from app.services.injection_scheduling_scheduler.run_service import (
    _expire_tentative_reservations,
    _tentative_hold_expires_at,
)
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def _asset(asset_id: str = "asset-legacy-1") -> InjectionSchedulingPhysicalMoldAsset:
    return InjectionSchedulingPhysicalMoldAsset(
        id=asset_id,
        mold_definition_id="definition-legacy",
        owner_scope_type="FACTORY",
        owner_scope_id="huaxing",
        asset_code="LEGACY-M-001-1",
        serial_no="",
        current_factory_id="huaxing",
        current_location="A区",
        status="AVAILABLE",
        actual_cavity_count=None,
        available_from="2026-08-09T08:00:00+08:00",
        revision=2,
        source_mold_id="mold-legacy",
        source_copy_no=1,
        verified_by="asset-reviewer",
        verified_at="2026-08-09T08:00:00+08:00",
        created_at="2026-08-09T07:00:00+08:00",
    )


def _reservation(
    *,
    reservation_id: str,
    asset_id: str,
    status: str,
    task_id: str | None,
    start: str,
    finish: str,
    expires_at: str = "",
) -> InjectionSchedulingMoldReservation:
    return InjectionSchedulingMoldReservation(
        id=reservation_id,
        physical_asset_id=asset_id,
        factory_id="huaxing",
        plan_id="plan-test",
        task_id=task_id,
        window_start=start,
        window_end=finish,
        status=status,
        revision=1,
        expires_at=expires_at,
        idempotency_key=f"test:{reservation_id}",
        source_kind="TEST",
        created_by="tester",
        created_at="2026-08-09T08:00:00+08:00",
        released_at="",
    )


def test_active_legacy_binding_is_used_by_new_tasks_and_conflicts_are_shared():
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        asset = _asset()
        db.add_all(
            [
                asset,
                InjectionSchedulingLegacyMoldCopyBinding(
                    id="legacy-binding-1",
                    factory_id="huaxing",
                    mold_id="mold-legacy",
                    mold_copy_no=1,
                    physical_asset_id=asset.id,
                    status="ACTIVE",
                    revision=1,
                    activated_by="asset-reviewer",
                    activated_at="2026-08-09T08:00:00+08:00",
                ),
            ]
        )
        db.commit()
        order = InjectionSchedulingOrder(
            source_type="MANUAL",
            source_ref="",
            mold_id="mold-legacy",
        )

        resolved = _physical_asset_for_new_task(
            db,
            order=order,
            factory_id="huaxing",
            requested_asset_id=None,
            mold_copy_no=1,
            planned_start="2026-08-10T08:00:00+08:00",
            planned_finish="2026-08-10T12:00:00+08:00",
        )
        assert resolved.id == asset.id

        db.add(
            _reservation(
                reservation_id="legacy-task-reservation",
                asset_id=asset.id,
                status="ACTIVE",
                task_id="legacy-task-1",
                start="2026-08-10T09:00:00+08:00",
                finish="2026-08-10T11:00:00+08:00",
            )
        )
        db.commit()
        with pytest.raises(HTTPException) as exc_info:
            _physical_asset_for_new_task(
                db,
                order=order,
                factory_id="huaxing",
                requested_asset_id=None,
                mold_copy_no=1,
                planned_start="2026-08-10T10:00:00+08:00",
                planned_finish="2026-08-10T13:00:00+08:00",
            )
        assert exc_info.value.detail["code"] == "PHYSICAL_MOLD_ASSET_RESERVED"


def test_tentative_hold_expires_and_active_task_release_is_persisted():
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        asset = _asset("asset-hold-1")
        db.add_all(
            [
                asset,
                InjectionSchedulingRolloutPolicy(
                    factory_id="huaxing",
                    demand_mode="MANUAL_CONFIRM",
                    master_data_mode="PROPOSAL_ONLY",
                    business_contract_status="UNSIGNED",
                    price_activation_enabled=False,
                    tentative_hold_ttl_minutes=15,
                    revision=1,
                    updated_by="system",
                    updated_by_name="",
                    updated_at="2026-08-09T08:00:00+08:00",
                ),
                _reservation(
                    reservation_id="expired-preview-hold",
                    asset_id=asset.id,
                    status="TENTATIVE",
                    task_id=None,
                    start="2026-08-10T08:00:00+08:00",
                    finish="2026-08-10T12:00:00+08:00",
                    expires_at=(business_now() - timedelta(minutes=1)).isoformat(
                        timespec="seconds"
                    ),
                ),
                _reservation(
                    reservation_id="active-task-hold",
                    asset_id=asset.id,
                    status="ACTIVE",
                    task_id="task-to-cancel",
                    start="2026-08-11T08:00:00+08:00",
                    finish="2026-08-11T12:00:00+08:00",
                ),
            ]
        )
        db.commit()

        assert _expire_tentative_reservations(db, factory_id="huaxing") == 1
        _release_task_reservation(
            db,
            task_id="task-to-cancel",
            timestamp="2026-08-09T09:00:00+08:00",
        )
        db.commit()

        expired = db.get(InjectionSchedulingMoldReservation, "expired-preview-hold")
        released = db.get(InjectionSchedulingMoldReservation, "active-task-hold")
        assert expired.status == "EXPIRED"
        assert expired.released_at
        assert released.status == "RELEASED"
        assert released.released_at == "2026-08-09T09:00:00+08:00"
        expires_at = _tentative_hold_expires_at(db, "huaxing")
        delta = business_now().fromisoformat(expires_at) - business_now()
        assert 14 * 60 <= delta.total_seconds() <= 15 * 60
