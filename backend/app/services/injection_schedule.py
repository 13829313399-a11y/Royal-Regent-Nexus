from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from hashlib import sha256
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.core.time import business_now, parse_business_timestamp
from app.models.injection_schedule import (
    InjectionMachineMaster,
    InjectionMoldMaster,
    InjectionOrderMaster,
    InjectionScheduleAuditEvent,
    InjectionScheduleFactoryState,
    InjectionScheduleRuleConfig,
    InjectionScheduleTask,
    InjectionScheduleValidationRun,
    InjectionScheduleVersion,
)
from app.schemas.injection_schedule import (
    InjectionScheduleCommand,
    InjectionScheduleVersionCreateRequest,
)
from app.services.auth import AuthContext
from app.services.injection_schedule_excel import canonical_json, normalize_key
from app.services.injection_schedule_import import (
    DEFAULT_RULE_CONFIG,
    add_audit_event,
    ensure_factory_defaults,
    json_list,
    json_object,
    list_machine_masters,
    list_mold_masters,
    list_order_masters,
    now_text,
    revision_conflict,
    serialize_rule_config,
)
from app.services.injection_schedule_rules import (
    calculate_transition_setup,
    canonical_color_key,
    normalize_rule_config,
)
from app.services.injection_schedule_validation import (
    build_version_data_hash,
    latest_version_conflicts,
    load_validation_run,
    validate_capabilities,
    validate_delivery_due_date,
    validate_dimensions,
    validate_machine_class,
    validate_material,
    validate_robot_requirement,
    validate_shot_capacity,
    validate_text_requirement,
    validate_version,
)


def load_version(
    db: Session,
    factory_id: str,
    version_id: str,
    *,
    for_update: bool = False,
) -> InjectionScheduleVersion:
    statement = select(InjectionScheduleVersion).where(
            InjectionScheduleVersion.id == version_id,
            InjectionScheduleVersion.factory_id == factory_id,
        )
    if for_update:
        statement = statement.with_for_update()
    version = db.scalar(statement)
    if version is None:
        raise HTTPException(status_code=404, detail="未找到该厂区的排程版本")
    return version


def lock_version_dependencies(
    db: Session,
    version: InjectionScheduleVersion,
) -> None:
    tasks = list(
        db.scalars(
            select(InjectionScheduleTask)
            .where(
                InjectionScheduleTask.factory_id == version.factory_id,
                InjectionScheduleTask.version_id == version.id,
            )
            .order_by(InjectionScheduleTask.id)
            .with_for_update()
        ).all()
    )
    lock_task_master_dependencies(db, version.factory_id, tasks)
    db.scalar(
        select(InjectionScheduleRuleConfig)
        .where(InjectionScheduleRuleConfig.factory_id == version.factory_id)
        .with_for_update()
    )


def lock_task_master_dependencies(
    db: Session,
    factory_id: str,
    tasks: list[InjectionScheduleTask],
) -> tuple[
    dict[str, InjectionOrderMaster],
    dict[str, InjectionMachineMaster],
    dict[str, InjectionMoldMaster],
]:
    """Lock task masters in the global order: order -> machine -> mold."""

    order_ids = sorted({item.order_id for item in tasks})
    machine_ids = sorted({item.machine_id for item in tasks})
    mold_ids = sorted({item.mold_id for item in tasks if item.mold_id})
    orders: list[InjectionOrderMaster] = []
    if order_ids:
        orders = list(
            db.scalars(
                select(InjectionOrderMaster)
                .where(
                    InjectionOrderMaster.factory_id == factory_id,
                    InjectionOrderMaster.id.in_(order_ids),
                )
                .order_by(InjectionOrderMaster.id)
                .execution_options(populate_existing=True)
                .with_for_update()
            ).all()
        )
    machines: list[InjectionMachineMaster] = []
    if machine_ids:
        machines = list(
            db.scalars(
                select(InjectionMachineMaster)
                .where(
                    InjectionMachineMaster.factory_id == factory_id,
                    InjectionMachineMaster.id.in_(machine_ids),
                )
                .order_by(InjectionMachineMaster.id)
                .execution_options(populate_existing=True)
                .with_for_update()
            ).all()
        )
    mold_codes = sorted(
        {
            normalize_key(item.mold_code)
            for item in orders
            if normalize_key(item.mold_code)
        }
    )
    molds: list[InjectionMoldMaster] = []
    if mold_ids or mold_codes:
        predicates = []
        if mold_ids:
            predicates.append(InjectionMoldMaster.id.in_(mold_ids))
        if mold_codes:
            predicates.append(
                InjectionMoldMaster.normalized_mold_code.in_(mold_codes)
            )
        molds = list(
            db.scalars(
                select(InjectionMoldMaster)
                .where(
                    InjectionMoldMaster.factory_id == factory_id,
                    or_(*predicates),
                )
                .order_by(InjectionMoldMaster.id)
                .execution_options(populate_existing=True)
                .with_for_update()
            ).all()
        )
    return (
        {item.id: item for item in orders},
        {item.id: item for item in machines},
        {item.normalized_mold_code: item for item in molds},
    )


def master_revision_snapshot(
    orders: dict[str, InjectionOrderMaster],
    machines: dict[str, InjectionMachineMaster],
    molds: dict[str, InjectionMoldMaster],
) -> dict[str, dict[str, int]]:
    return {
        "orders": {item.id: item.revision for item in orders.values()},
        "machines": {item.id: item.revision for item in machines.values()},
        "molds": {item.id: item.revision for item in molds.values()},
    }


def verify_master_revision_snapshot(
    db: Session,
    factory_id: str,
    expected: dict[str, dict[str, int]],
) -> None:
    model_by_group = {
        "orders": InjectionOrderMaster,
        "machines": InjectionMachineMaster,
        "molds": InjectionMoldMaster,
    }
    for group_name, model in model_by_group.items():
        expected_revisions = expected[group_name]
        if not expected_revisions:
            continue
        current_revisions = dict(
            db.execute(
                select(model.id, model.revision)
                .where(
                    model.factory_id == factory_id,
                    model.id.in_(sorted(expected_revisions)),
                )
                .order_by(model.id)
            ).all()
        )
        if current_revisions != expected_revisions:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "master_revision_changed",
                    "message": "刷新期间主数据发生变化，请重试",
                    "entity_group": group_name,
                    "expected_revisions": expected_revisions,
                    "current_revisions": current_revisions,
                },
            )


def list_versions(
    db: Session,
    factory_id: str,
) -> list[dict[str, Any]]:
    versions = db.scalars(
        select(InjectionScheduleVersion)
        .where(InjectionScheduleVersion.factory_id == factory_id)
        .order_by(
            InjectionScheduleVersion.version_no.desc(),
            InjectionScheduleVersion.id.desc(),
        )
    ).all()
    return [serialize_version(item) for item in versions]


def create_version(
    db: Session,
    factory_id: str,
    payload: InjectionScheduleVersionCreateRequest,
    actor: AuthContext,
    *,
    clone_reason: str = "",
    source_batch_id_override: str | None = None,
    commit: bool = True,
    exact_clone: bool = False,
) -> dict[str, Any]:
    timestamp = now_text()
    state, config = ensure_factory_defaults(db, factory_id, actor.id, timestamp)
    state_revision = state.revision
    version_no = state.next_version_no
    allocated = db.execute(
        update(InjectionScheduleFactoryState)
        .where(
            InjectionScheduleFactoryState.factory_id == factory_id,
            InjectionScheduleFactoryState.revision == state_revision,
        )
        .values(
            next_version_no=InjectionScheduleFactoryState.next_version_no + 1,
            revision=InjectionScheduleFactoryState.revision + 1,
            updated_at=timestamp,
        )
    )
    if allocated.rowcount != 1:
        db.rollback()
        current = db.get(InjectionScheduleFactoryState, factory_id)
        raise revision_conflict(
            factory_id,
            state_revision,
            current.revision if current is not None else None,
        )

    base_version = (
        load_version(db, factory_id, payload.base_version_id)
        if payload.base_version_id
        else None
    )
    plan_base = parse_business_timestamp(payload.plan_base_at)
    if plan_base is None:
        plan_base = business_now().replace(second=0, microsecond=0)
    business_date = payload.business_date.strip() or plan_base.date().isoformat()
    source_batch_id = (
        source_batch_id_override
        if source_batch_id_override is not None
        else base_version.source_batch_id
        if base_version is not None
        else latest_confirmed_batch_id(db, factory_id)
    )
    version = InjectionScheduleVersion(
        id=f"ISV-{uuid4().hex.upper()}",
        factory_id=factory_id,
        version_no=version_no,
        name=payload.name.strip() or f"排程版本 V{version_no}",
        status="draft",
        revision=1,
        business_date=business_date,
        plan_base_at=plan_base.strftime("%Y-%m-%d %H:%M:%S"),
        base_version_id=base_version.id if base_version is not None else None,
        source_batch_id=source_batch_id,
        rules_snapshot_json=(
            base_version.rules_snapshot_json
            if exact_clone and base_version is not None
            else canonical_json(
                normalize_rule_config(json_object(config.config_json))
            )
        ),
        rule_config_revision=(
            base_version.rule_config_revision
            if exact_clone and base_version is not None
            else config.revision
        ),
        data_hash="",
        validation_hash="",
        summary_json="{}",
        created_by=actor.id,
        created_by_name=actor.display_name,
        created_at=timestamp,
        updated_by=actor.id,
        updated_at=timestamp,
    )
    db.add(version)
    db.flush()
    if base_version is not None:
        clone_version_tasks(db, base_version, version, actor, timestamp)
    else:
        create_imported_assignment_tasks(db, version, actor, timestamp)
    if not exact_clone:
        recompute_all_lanes(db, version, actor, timestamp)
    version.summary_json = canonical_json(version_summary(db, version))
    version.data_hash = build_version_data_hash(db, version)
    add_audit_event(
        db,
        factory_id=factory_id,
        entity_type="schedule_version",
        entity_id=version.id,
        action="cloned_as_draft" if base_version is not None else "draft_created",
        actor=actor,
        reason=clone_reason,
        new_revision=1,
        after={
            "version_no": version_no,
            "base_version_id": version.base_version_id,
            "plan_base_at": version.plan_base_at,
            "summary": json_object(version.summary_json),
        },
    )
    if commit:
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise
        db.refresh(version)
    else:
        db.flush()
    return serialize_version(version)


def clone_version_as_draft(
    db: Session,
    factory_id: str,
    version_id: str,
    *,
    name: str,
    reason: str,
    actor: AuthContext,
) -> dict[str, Any]:
    source = load_version(db, factory_id, version_id)
    return create_version(
        db,
        factory_id,
        InjectionScheduleVersionCreateRequest(
            name=name or f"{source.name}（副本）",
            business_date=source.business_date,
            plan_base_at=source.plan_base_at,
            base_version_id=source.id,
        ),
        actor,
        clone_reason=reason,
    )


def create_imported_assignment_tasks(
    db: Session,
    version: InjectionScheduleVersion,
    actor: AuthContext,
    timestamp: str,
) -> None:
    machines = list(
        db.scalars(
            select(InjectionMachineMaster).where(
                InjectionMachineMaster.factory_id == version.factory_id
            )
        ).all()
    )
    machine_by_code = {item.machine_code: item for item in machines}
    molds = list(
        db.scalars(
            select(InjectionMoldMaster).where(
                InjectionMoldMaster.factory_id == version.factory_id
            )
        ).all()
    )
    mold_by_code = {item.normalized_mold_code: item for item in molds}
    orders = list(
        db.scalars(
            select(InjectionOrderMaster)
            .where(
                InjectionOrderMaster.factory_id == version.factory_id,
                InjectionOrderMaster.status == "open",
                InjectionOrderMaster.outstanding_qty > 0,
            )
            .order_by(InjectionOrderMaster.source_row, InjectionOrderMaster.id)
        ).all()
    )
    sequences: Counter[str] = Counter()
    for order in orders:
        machine = machine_by_code.get(order.imported_assigned_machine_code)
        if machine is None:
            continue
        sequence_no = sequences[machine.id]
        sequences[machine.id] += 1
        mold = mold_by_code.get(normalize_key(order.mold_code))
        risk_level, risk_reasons = assignment_precheck(
            order,
            machine,
            mold,
            shot_safety_factor(version),
            json_object(version.rules_snapshot_json),
        )
        db.add(
            InjectionScheduleTask(
                id=f"IST-{uuid4().hex.upper()}",
                factory_id=version.factory_id,
                version_id=version.id,
                order_id=order.id,
                machine_id=machine.id,
                mold_id=mold.id if mold is not None else None,
                sequence_no=sequence_no,
                planned_qty=order.outstanding_qty,
                planned_start_at="",
                planned_finish_at="",
                setup_hours=0,
                duration_hours=0,
                locked=False,
                split_group_id="",
                parent_task_id="",
                order_no_snapshot=order.order_no,
                product_code_snapshot=order.product_code,
                product_name_snapshot=order.product_name,
                delivery_due_date_snapshot=order.delivery_due_date,
                mold_code_snapshot=mold.mold_code if mold is not None else order.mold_code,
                color_snapshot=canonical_color_key(order.pigment, order.color),
                color_rank_snapshot=order.color_rank,
                material_snapshot=order.material,
                machine_code_snapshot=machine.machine_code,
                source="import",
                recommendation_score=None,
                score_breakdown_json="[]",
                constraint_snapshot_json="[]",
                recommendation_context_hash="",
                risk_level=risk_level,
                risk_reasons_json=canonical_json(risk_reasons),
                order_revision_snapshot=order.revision,
                machine_revision_snapshot=machine.revision,
                mold_revision_snapshot=mold.revision if mold is not None else 0,
                revision=1,
                created_by=actor.id,
                created_at=timestamp,
                updated_by=actor.id,
                updated_at=timestamp,
            )
        )
    db.flush()


def clone_version_tasks(
    db: Session,
    source: InjectionScheduleVersion,
    target: InjectionScheduleVersion,
    actor: AuthContext,
    timestamp: str,
) -> None:
    source_tasks = db.scalars(
        select(InjectionScheduleTask)
        .where(
            InjectionScheduleTask.factory_id == source.factory_id,
            InjectionScheduleTask.version_id == source.id,
        )
        .order_by(
            InjectionScheduleTask.machine_id,
            InjectionScheduleTask.sequence_no,
            InjectionScheduleTask.id,
        )
    ).all()
    for source_task in source_tasks:
        db.add(
            InjectionScheduleTask(
                id=f"IST-{uuid4().hex.upper()}",
                factory_id=target.factory_id,
                version_id=target.id,
                order_id=source_task.order_id,
                machine_id=source_task.machine_id,
                mold_id=source_task.mold_id,
                sequence_no=source_task.sequence_no,
                planned_qty=source_task.planned_qty,
                planned_start_at=source_task.planned_start_at,
                planned_finish_at=source_task.planned_finish_at,
                setup_hours=source_task.setup_hours,
                duration_hours=source_task.duration_hours,
                locked=source_task.locked,
                split_group_id=source_task.split_group_id,
                parent_task_id=source_task.id,
                order_no_snapshot=source_task.order_no_snapshot,
                product_code_snapshot=source_task.product_code_snapshot,
                product_name_snapshot=source_task.product_name_snapshot,
                delivery_due_date_snapshot=source_task.delivery_due_date_snapshot,
                mold_code_snapshot=source_task.mold_code_snapshot,
                color_snapshot=source_task.color_snapshot,
                color_rank_snapshot=source_task.color_rank_snapshot,
                material_snapshot=source_task.material_snapshot,
                machine_code_snapshot=source_task.machine_code_snapshot,
                source=source_task.source,
                execution_status=source_task.execution_status,
                protected=source_task.protected,
                recommendation_score=source_task.recommendation_score,
                score_breakdown_json=source_task.score_breakdown_json,
                constraint_snapshot_json=source_task.constraint_snapshot_json,
                recommendation_context_hash=source_task.recommendation_context_hash,
                risk_level=source_task.risk_level,
                risk_reasons_json=source_task.risk_reasons_json,
                order_revision_snapshot=source_task.order_revision_snapshot,
                machine_revision_snapshot=source_task.machine_revision_snapshot,
                mold_revision_snapshot=source_task.mold_revision_snapshot,
                revision=1,
                created_by=actor.id,
                created_at=timestamp,
                updated_by=actor.id,
                updated_at=timestamp,
            )
        )
    db.flush()


def apply_schedule_commands(
    db: Session,
    factory_id: str,
    version_id: str,
    *,
    expected_revision: int,
    reason: str,
    request_id: str,
    commands: list[InjectionScheduleCommand],
    actor: AuthContext,
    ip_address: str = "",
) -> dict[str, Any]:
    version = load_version(db, factory_id, version_id)
    if version.status != "draft":
        raise HTTPException(status_code=409, detail="已发布版本不可修改，请复制为新草稿")
    before_tasks = task_change_snapshot(db, version)
    timestamp = now_text()
    result = db.execute(
        update(InjectionScheduleVersion)
        .where(
            InjectionScheduleVersion.id == version_id,
            InjectionScheduleVersion.factory_id == factory_id,
            InjectionScheduleVersion.status == "draft",
            InjectionScheduleVersion.revision == expected_revision,
        )
        .values(
            revision=InjectionScheduleVersion.revision + 1,
            data_hash="",
            validation_hash="",
            updated_by=actor.id,
            updated_at=timestamp,
        )
    )
    if result.rowcount != 1:
        db.rollback()
        current = load_version(db, factory_id, version_id)
        raise revision_conflict(version_id, expected_revision, current.revision)
    db.flush()
    db.expire_all()
    version = load_version(db, factory_id, version_id)
    affected_machine_ids: set[str] = set()
    command_touched_task_ids: set[str] = set()
    try:
        for command in commands:
            apply_one_command(
                db,
                version,
                command,
                actor,
                timestamp,
                affected_machine_ids,
                command_touched_task_ids,
                recommendation_version_revision=expected_revision,
            )
            # A command batch is ordered and atomic. Make each command's lane
            # mutations visible to the next command even though SessionLocal
            # intentionally disables autoflush.
            db.flush()
        normalize_lane_sequences(db, version, affected_machine_ids)
        mark_implicit_task_revisions(
            db,
            version,
            affected_machine_ids,
            before_tasks,
            command_touched_task_ids,
            actor,
            timestamp,
        )
        recommendation_only = (
            len(commands) == 1
            and bool(commands[0].recommendation_context_hash)
            and commands[0].type == "assign"
        )
        if not recommendation_only:
            recompute_lanes(
                db,
                version,
                affected_machine_ids,
                actor,
                timestamp,
                command_touched_task_ids=command_touched_task_ids,
            )
            enforce_phase3_command_time_windows(
                db,
                version,
                affected_machine_ids,
                commands,
                command_touched_task_ids,
                actor,
                timestamp,
            )
        version.summary_json = canonical_json(version_summary(db, version))
        version.data_hash = build_version_data_hash(db, version)
        after_tasks = task_change_snapshot(db, version)
        add_audit_event(
            db,
            factory_id=factory_id,
            entity_type="schedule_version",
            entity_id=version.id,
            action="commands_applied",
            actor=actor,
            request_id=request_id,
            ip_address=ip_address,
            reason=reason,
            old_revision=expected_revision,
            new_revision=expected_revision + 1,
            before={"tasks": before_tasks},
            after={
                "commands": [command.model_dump() for command in commands],
                "tasks": after_tasks,
                "affected_machine_ids": sorted(affected_machine_ids),
            },
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.expire_all()
    version = load_version(db, factory_id, version_id)
    return {
        "version": serialize_version(version),
        "tasks": list_tasks(db, version),
        "conflicts": [],
        "affected_machine_ids": sorted(affected_machine_ids),
    }


def apply_one_command(
    db: Session,
    version: InjectionScheduleVersion,
    command: InjectionScheduleCommand,
    actor: AuthContext,
    timestamp: str,
    affected_machine_ids: set[str],
    command_touched_task_ids: set[str],
    *,
    recommendation_version_revision: int | None = None,
) -> None:
    if command.type == "assign":
        order = load_order_for_version(db, version, command.order_id or "")
        machine = load_machine_for_version(db, version, command.machine_id or "")
        allocated_qty = sum(
            db.scalars(
                select(InjectionScheduleTask.planned_qty).where(
                    InjectionScheduleTask.factory_id == version.factory_id,
                    InjectionScheduleTask.version_id == version.id,
                    InjectionScheduleTask.order_id == order.id,
                    InjectionScheduleTask.execution_status.not_in(
                        ("completed", "cancelled")
                    ),
                )
            ).all()
        )
        planned_qty = command.planned_qty or order.outstanding_qty - allocated_qty
        if planned_qty <= 0 or allocated_qty + planned_qty > order.outstanding_qty + 1e-6:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "planned_qty_exceeds_outstanding",
                    "message": "计划数量超过订单剩余欠数",
                    "outstanding_qty": order.outstanding_qty,
                    "already_planned_qty": allocated_qty,
                },
            )
        mold = find_order_mold(db, version.factory_id, order)
        risk_level, risk_reasons = assignment_precheck(
            order,
            machine,
            mold,
            shot_safety_factor(version),
            json_object(version.rules_snapshot_json),
        )
        enforce_assignment_precheck(command, risk_level, risk_reasons)
        lane_count = len(
            db.scalars(
                select(InjectionScheduleTask.id).where(
                    InjectionScheduleTask.factory_id == version.factory_id,
                    InjectionScheduleTask.version_id == version.id,
                    InjectionScheduleTask.machine_id == machine.id,
                )
            ).all()
        )
        target_index = (
            min(command.target_index, lane_count)
            if command.target_index is not None
            else lane_count
        )
        recommendation_candidate: dict[str, Any] | None = None
        if command.recommendation_context_hash:
            from app.services.injection_schedule_recommendation import (
                verify_recommendation_for_assignment,
            )

            recommendation_candidate = verify_recommendation_for_assignment(
                db,
                factory_id=version.factory_id,
                version_id=version.id,
                version_revision=recommendation_version_revision or version.revision,
                order_id=order.id,
                machine_id=machine.id,
                target_index=target_index,
                planned_qty=planned_qty,
                recommendation_context_hash=command.recommendation_context_hash,
            )
            if (
                recommendation_candidate["status"] == "manual_review"
                and not command.manual_confirmation
            ):
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "manual_confirmation_required",
                        "message": "推荐仍有未知硬约束，必须填写人工确认原因",
                        "constraints": recommendation_candidate["hard_constraints"],
                    },
                )
        persisted_risk_level = (
            "normal"
            if recommendation_candidate is not None
            and recommendation_candidate["status"] == "eligible"
            else "unknown"
            if recommendation_candidate is not None
            else risk_level
        )
        persisted_risk_reasons = (
            [
                item["message"]
                for item in recommendation_candidate["hard_constraints"]
                if item["status"] != "pass"
            ]
            if recommendation_candidate is not None
            else risk_reasons
        )
        if command.manual_confirmation and recommendation_candidate is not None:
            persisted_risk_reasons.append(
                f"人工确认：{command.manual_confirmation_reason.strip()}"
            )
        recommendation_estimate = (
            recommendation_candidate["score"]["estimated"]
            if recommendation_candidate is not None
            and recommendation_candidate["score"] is not None
            else None
        )
        recommendation_transition = (
            recommendation_candidate["score"]["transition"]
            if recommendation_candidate is not None
            and recommendation_candidate["score"] is not None
            else None
        )
        if (
            recommendation_candidate is not None
            and recommendation_transition is not None
            and recommendation_transition["next_task_id"]
        ):
            next_task = load_task_for_version(
                db,
                version,
                recommendation_transition["next_task_id"],
            )
            next_task.setup_hours = (
                float(recommendation_transition["setup_minutes_after"]) / 60
            )
            next_task.revision += 1
            next_task.updated_by = actor.id
            next_task.updated_at = timestamp
            command_touched_task_ids.add(next_task.id)
        target_sequence = prepare_lane_insert(
            db,
            version,
            machine.id,
            target_index,
        )
        task = InjectionScheduleTask(
            id=f"IST-{uuid4().hex.upper()}",
            factory_id=version.factory_id,
            version_id=version.id,
            order_id=order.id,
            machine_id=machine.id,
            mold_id=mold.id if mold is not None else None,
            sequence_no=target_sequence,
            planned_qty=planned_qty,
            planned_start_at=(
                recommendation_estimate["production_start_at"]
                if recommendation_estimate is not None
                else ""
            ),
            planned_finish_at=(
                recommendation_estimate["finish_at"]
                if recommendation_estimate is not None
                else ""
            ),
            setup_hours=(
                float(recommendation_transition["setup_minutes_before"]) / 60
                if recommendation_transition is not None
                else 0
            ),
            duration_hours=(
                float(recommendation_estimate["duration_hours"])
                if recommendation_estimate is not None
                else 0
            ),
            locked=False,
            split_group_id="",
            parent_task_id="",
            order_no_snapshot=order.order_no,
            product_code_snapshot=order.product_code,
            product_name_snapshot=order.product_name,
            delivery_due_date_snapshot=order.delivery_due_date,
            mold_code_snapshot=mold.mold_code if mold is not None else order.mold_code,
            color_snapshot=canonical_color_key(order.pigment, order.color),
            color_rank_snapshot=order.color_rank,
            material_snapshot=order.material,
            machine_code_snapshot=machine.machine_code,
            source="recommendation" if recommendation_candidate is not None else "manual",
            recommendation_score=(
                recommendation_candidate["score"]["total"]
                if recommendation_candidate is not None
                and recommendation_candidate["score"] is not None
                else None
            ),
            score_breakdown_json=canonical_json(
                recommendation_candidate["score"]["breakdown"]
                if recommendation_candidate is not None
                and recommendation_candidate["score"] is not None
                else []
            ),
            constraint_snapshot_json=canonical_json(
                recommendation_candidate["hard_constraints"]
                if recommendation_candidate is not None
                else []
            ),
            recommendation_context_hash=command.recommendation_context_hash,
            risk_level=persisted_risk_level,
            risk_reasons_json=canonical_json(persisted_risk_reasons),
            order_revision_snapshot=order.revision,
            machine_revision_snapshot=machine.revision,
            mold_revision_snapshot=mold.revision if mold is not None else 0,
            revision=1,
            created_by=actor.id,
            created_at=timestamp,
            updated_by=actor.id,
            updated_at=timestamp,
        )
        db.add(task)
        command_touched_task_ids.add(task.id)
        affected_machine_ids.add(machine.id)
        db.flush()
        return

    if command.type == "refresh_masters":
        task_statement = (
            select(InjectionScheduleTask)
            .where(
                InjectionScheduleTask.factory_id == version.factory_id,
                InjectionScheduleTask.version_id == version.id,
            )
            .order_by(InjectionScheduleTask.id)
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        if command.task_id:
            task_statement = task_statement.where(
                InjectionScheduleTask.id == command.task_id
            )
        tasks = list(db.scalars(task_statement).all())
        if command.task_id and not tasks:
            raise HTTPException(
                status_code=404,
                detail="未找到该草稿中的排程任务",
            )
        if not tasks:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "no_tasks_to_refresh",
                    "message": "当前草稿没有可刷新主数据快照的任务",
                },
            )
        orders, machines, molds = lock_task_master_dependencies(
            db,
            version.factory_id,
            tasks,
        )
        locked_revisions = master_revision_snapshot(
            orders,
            machines,
            molds,
        )
        blocked_reasons: list[str] = []
        refreshed: list[
            tuple[
                InjectionScheduleTask,
                InjectionOrderMaster,
                InjectionMachineMaster,
                InjectionMoldMaster | None,
                str,
                list[str],
            ]
        ] = []
        for target_task in tasks:
            order = orders.get(target_task.order_id)
            if order is None:
                raise HTTPException(
                    status_code=404,
                    detail="未找到该厂区的订单主数据",
                )
            machine = machines.get(target_task.machine_id)
            if machine is None:
                raise HTTPException(
                    status_code=404,
                    detail="未找到该厂区的机台主数据",
                )
            mold = molds.get(normalize_key(order.mold_code))
            risk_level, risk_reasons = assignment_precheck(
                order,
                machine,
                mold,
                shot_safety_factor(version),
                json_object(version.rules_snapshot_json),
            )
            if risk_level == "blocked":
                blocked_reasons.extend(
                    f"任务 {target_task.id}：{reason}"
                    for reason in risk_reasons
                )
            refreshed.append(
                (
                    target_task,
                    order,
                    machine,
                    mold,
                    risk_level,
                    risk_reasons,
                )
            )
        if blocked_reasons:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "assignment_blocked",
                    "message": "当前主数据存在已知硬约束冲突，不能重新确认",
                    "reasons": blocked_reasons,
                },
            )
        for target_task, order, machine, mold, risk_level, risk_reasons in refreshed:
            target_task.mold_id = mold.id if mold is not None else None
            refresh_task_master_snapshot(
                target_task,
                order,
                machine,
                mold,
            )
            target_task.risk_level = risk_level
            target_task.risk_reasons_json = canonical_json(risk_reasons)
            target_task.revision += 1
            target_task.updated_by = actor.id
            target_task.updated_at = timestamp
            command_touched_task_ids.add(target_task.id)
            affected_machine_ids.add(target_task.machine_id)
        verify_master_revision_snapshot(
            db,
            version.factory_id,
            locked_revisions,
        )
        return

    task = load_task_for_version(db, version, command.task_id or "")
    if command.type in {"move", "reorder", "split"} and task.locked:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "task_locked",
                "message": "任务已锁定，不能移动、排序或拆单",
                "task_id": task.id,
            },
        )
    if command.type in {"move", "reorder", "split", "unlock"} and (
        task.protected
        or task.execution_status in {"running", "completed", "cancelled"}
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "task_protected",
                "message": "任务已开机、已完成或受保护，不能移动、排序、拆单或解锁",
                "task_id": task.id,
            },
        )
    if command.type == "lock":
        task.locked = True
        task.revision += 1
        task.updated_by = actor.id
        task.updated_at = timestamp
        command_touched_task_ids.add(task.id)
        affected_machine_ids.add(task.machine_id)
        return
    if command.type == "unlock":
        task.locked = False
        task.revision += 1
        task.updated_by = actor.id
        task.updated_at = timestamp
        command_touched_task_ids.add(task.id)
        affected_machine_ids.add(task.machine_id)
        return
    if command.type == "reorder":
        task.sequence_no = 2_000_000
        db.flush()
        task.sequence_no = prepare_lane_insert(
            db,
            version,
            task.machine_id,
            command.target_index or 0,
            excluded_task_id=task.id,
        )
        task.revision += 1
        task.updated_by = actor.id
        task.updated_at = timestamp
        command_touched_task_ids.add(task.id)
        affected_machine_ids.add(task.machine_id)
        return
    if command.type == "move":
        machine = load_machine_for_version(db, version, command.machine_id or "")
        order = load_order_for_version(db, version, task.order_id)
        mold = find_order_mold(db, version.factory_id, order)
        risk_level, risk_reasons = assignment_precheck(
            order,
            machine,
            mold,
            shot_safety_factor(version),
            json_object(version.rules_snapshot_json),
        )
        enforce_assignment_precheck(command, risk_level, risk_reasons)
        affected_machine_ids.update((task.machine_id, machine.id))
        same_lane = task.machine_id == machine.id
        if same_lane:
            task.sequence_no = 2_000_000
            db.flush()
        target_sequence = prepare_lane_insert(
            db,
            version,
            machine.id,
            command.target_index or 0,
            excluded_task_id=task.id if same_lane else "",
        )
        task.machine_id = machine.id
        task.mold_id = mold.id if mold is not None else None
        task.sequence_no = target_sequence
        task.risk_level = risk_level
        task.risk_reasons_json = canonical_json(risk_reasons)
        refresh_task_master_snapshot(task, order, machine, mold)
        task.revision += 1
        task.updated_by = actor.id
        task.updated_at = timestamp
        command_touched_task_ids.add(task.id)
        return
    if command.type == "split":
        split_qty = float(command.split_qty or 0)
        if split_qty <= 0 or split_qty >= task.planned_qty:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "invalid_split_qty",
                    "message": "拆单数量必须大于 0 且小于原任务计划数",
                    "task_id": task.id,
                },
            )
        target_machine = (
            load_machine_for_version(db, version, command.machine_id)
            if command.machine_id
            else load_machine_for_version(db, version, task.machine_id)
        )
        order = load_order_for_version(db, version, task.order_id)
        mold = find_order_mold(db, version.factory_id, order)
        risk_level, risk_reasons = assignment_precheck(
            order,
            target_machine,
            mold,
            shot_safety_factor(version),
            json_object(version.rules_snapshot_json),
        )
        enforce_assignment_precheck(command, risk_level, risk_reasons)
        target_sequence = prepare_lane_insert(
            db,
            version,
            target_machine.id,
            command.target_index
            if command.target_index is not None
            else task.sequence_no + 1,
        )
        split_group_id = task.split_group_id or f"ISG-{uuid4().hex.upper()}"
        task.planned_qty -= split_qty
        task.split_group_id = split_group_id
        task.revision += 1
        task.updated_by = actor.id
        task.updated_at = timestamp
        new_task = InjectionScheduleTask(
            id=f"IST-{uuid4().hex.upper()}",
            factory_id=version.factory_id,
            version_id=version.id,
            order_id=task.order_id,
            machine_id=target_machine.id,
            mold_id=mold.id if mold is not None else None,
            sequence_no=target_sequence,
            planned_qty=split_qty,
            planned_start_at="",
            planned_finish_at="",
            setup_hours=0,
            duration_hours=0,
            locked=False,
            split_group_id=split_group_id,
            parent_task_id=task.id,
            order_no_snapshot=order.order_no,
            product_code_snapshot=order.product_code,
            product_name_snapshot=order.product_name,
            delivery_due_date_snapshot=order.delivery_due_date,
            mold_code_snapshot=mold.mold_code if mold is not None else order.mold_code,
            color_snapshot=canonical_color_key(order.pigment, order.color),
            color_rank_snapshot=order.color_rank,
            material_snapshot=order.material,
            machine_code_snapshot=target_machine.machine_code,
            source=task.source,
            recommendation_score=task.recommendation_score,
            score_breakdown_json=task.score_breakdown_json,
            constraint_snapshot_json=task.constraint_snapshot_json,
            recommendation_context_hash=task.recommendation_context_hash,
            risk_level=risk_level,
            risk_reasons_json=canonical_json(risk_reasons),
            order_revision_snapshot=order.revision,
            machine_revision_snapshot=target_machine.revision,
            mold_revision_snapshot=mold.revision if mold is not None else 0,
            revision=1,
            created_by=actor.id,
            created_at=timestamp,
            updated_by=actor.id,
            updated_at=timestamp,
        )
        db.add(new_task)
        command_touched_task_ids.update((task.id, new_task.id))
        affected_machine_ids.update((task.machine_id, target_machine.id))
        db.flush()
        return
    raise HTTPException(status_code=422, detail="不支持的排程命令")


def refresh_task_master_snapshot(
    task: InjectionScheduleTask,
    order: InjectionOrderMaster,
    machine: InjectionMachineMaster,
    mold: InjectionMoldMaster | None,
) -> None:
    task.order_revision_snapshot = order.revision
    task.machine_revision_snapshot = machine.revision
    task.mold_revision_snapshot = mold.revision if mold is not None else 0
    task.order_no_snapshot = order.order_no
    task.product_code_snapshot = order.product_code
    task.product_name_snapshot = order.product_name
    task.delivery_due_date_snapshot = order.delivery_due_date
    task.color_snapshot = canonical_color_key(order.pigment, order.color)
    task.color_rank_snapshot = order.color_rank
    task.material_snapshot = order.material
    task.mold_code_snapshot = (
        mold.mold_code if mold is not None else order.mold_code
    )
    task.machine_code_snapshot = machine.machine_code


def enforce_assignment_precheck(
    command: InjectionScheduleCommand,
    risk_level: str,
    risk_reasons: list[str],
) -> None:
    if risk_level == "blocked":
        raise HTTPException(
            status_code=422,
            detail={
                "code": "assignment_blocked",
                "message": "机台与订单存在已知硬约束冲突",
                "reasons": risk_reasons,
            },
        )
    if risk_level == "unknown" and not command.manual_confirmation:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "manual_confirmation_required",
                "message": "资料不足，只能在填写人工确认原因后保存到草稿",
                "reasons": risk_reasons,
            },
        )
    if command.manual_confirmation:
        risk_reasons.append(
            f"人工确认：{command.manual_confirmation_reason.strip()}"
        )


def shot_safety_factor(version: InjectionScheduleVersion) -> float:
    rules = json_object(version.rules_snapshot_json)
    try:
        return float(rules.get("shot_safety_factor") or 0.85)
    except (TypeError, ValueError):
        return 0.85


def assignment_precheck(
    order: InjectionOrderMaster,
    machine: InjectionMachineMaster,
    mold: InjectionMoldMaster | None,
    safety_factor: float = 0.85,
    rules: dict[str, Any] | None = None,
) -> tuple[str, list[str]]:
    from app.services.injection_schedule_recommendation import (
        evaluate_phase3_master_constraints,
    )

    normalized_rules = normalize_rule_config(
        rules or {"shot_safety_factor": safety_factor}
    )
    checks = evaluate_phase3_master_constraints(
        order.factory_id,
        order,
        mold,
        machine,
        normalized_rules,
    )
    blocked = [
        str(check["message"]) for check in checks if check["status"] == "fail"
    ]
    unknown = [
        str(check["message"]) for check in checks if check["status"] == "unknown"
    ]
    if not normalized_rules.get("availability_calendar_verified_through"):
        unknown.append("未配置已核验的停机日历覆盖截止时间")
    if blocked:
        return "blocked", blocked + unknown
    if unknown:
        if not bool(
            normalized_rules.get(
                "allow_missing_data_in_draft_with_manual_confirmation"
            )
        ):
            return (
                "blocked",
                ["当前版本规则禁止将未知硬约束保存到草稿。", *unknown],
            )
        return "unknown", unknown
    return "normal", []


def enforce_phase3_command_time_windows(
    db: Session,
    version: InjectionScheduleVersion,
    machine_ids: set[str],
    commands: list[InjectionScheduleCommand],
    command_touched_task_ids: set[str],
    actor: AuthContext,
    timestamp: str,
) -> None:
    if not machine_ids:
        return
    from app.services.injection_schedule_recommendation import (
        evaluate_scheduled_task_time_window,
    )

    machines = {
        item.id: item
        for item in db.scalars(
            select(InjectionMachineMaster).where(
                InjectionMachineMaster.factory_id == version.factory_id,
                InjectionMachineMaster.id.in_(sorted(machine_ids)),
            )
        ).all()
    }
    tasks = list(
        db.scalars(
            select(InjectionScheduleTask).where(
                InjectionScheduleTask.factory_id == version.factory_id,
                InjectionScheduleTask.version_id == version.id,
                InjectionScheduleTask.machine_id.in_(sorted(machine_ids)),
            )
        ).all()
    )
    rules = normalize_rule_config(json_object(version.rules_snapshot_json))
    failures: list[str] = []
    unknowns: list[str] = []
    risk_failures: list[str] = []
    for task in tasks:
        missing_transition_fields = [
            field_name
            for field_name, value in (
                ("mold_code_snapshot", task.mold_code_snapshot),
                ("color_snapshot", task.color_snapshot),
                ("material_snapshot", task.material_snapshot),
            )
            if normalize_key(value) in {"", "UNKNOWN", "未知", "待确认"}
        ]
        if missing_transition_fields:
            unknowns.append(
                f"任务 {task.id} 缺少相邻换型快照："
                f"{', '.join(missing_transition_fields)}"
            )
        if task.risk_level == "blocked":
            reasons = json_list(task.risk_reasons_json)
            risk_failures.append(
                f"任务 {task.id}："
                + ("；".join(str(item) for item in reasons) or "硬约束已阻断")
            )
        elif task.risk_level == "unknown":
            reasons = json_list(task.risk_reasons_json)
            unknowns.append(
                f"任务 {task.id}："
                + ("；".join(str(item) for item in reasons) or "硬约束资料不足")
            )
        machine = machines.get(task.machine_id)
        if machine is None:
            failures.append(f"任务 {task.id} 的机台不存在")
            continue
        check = evaluate_scheduled_task_time_window(task, machine, rules)
        if check["status"] == "fail":
            failures.append(f"任务 {task.id}：{check['message']}")
        elif check["status"] == "unknown":
            unknowns.append(f"任务 {task.id}：{check['message']}")
            if task.risk_level == "normal":
                task.risk_level = "unknown"
                reasons = json_list(task.risk_reasons_json)
                reasons.append(str(check["message"]))
                task.risk_reasons_json = canonical_json(list(dict.fromkeys(reasons)))
                if task.id not in command_touched_task_ids:
                    task.revision += 1
                    command_touched_task_ids.add(task.id)
                task.updated_by = actor.id
                task.updated_at = timestamp
    if failures:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "time_window_blocked",
                "message": "排程占用已知停机或锁定时间窗",
                "reasons": failures,
            },
        )
    if unknowns and not bool(
        rules.get("allow_missing_data_in_draft_with_manual_confirmation")
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "missing_data_policy_blocked",
                "message": "当前版本规则禁止将未知硬约束保存到草稿",
                "reasons": unknowns,
            },
        )
    if risk_failures:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "assignment_blocked",
                "message": "命令执行后仍存在已知或规则禁止的硬约束",
                "reasons": risk_failures,
            },
        )
    relevant_commands = [
        item
        for item in commands
        if item.type in {"assign", "move", "reorder", "split"}
    ]
    if unknowns and relevant_commands and not all(
        item.manual_confirmation for item in relevant_commands
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "manual_confirmation_required",
                "message": "硬约束或停机日历资料不足，必须填写人工确认原因",
                "reasons": unknowns,
            },
        )


def normalize_lane_sequences(
    db: Session,
    version: InjectionScheduleVersion,
    machine_ids: set[str],
) -> None:
    for machine_id in sorted(machine_ids):
        lane = list(
            db.scalars(
                select(InjectionScheduleTask)
                .where(
                    InjectionScheduleTask.factory_id == version.factory_id,
                    InjectionScheduleTask.version_id == version.id,
                    InjectionScheduleTask.machine_id == machine_id,
                )
                .order_by(
                    InjectionScheduleTask.sequence_no,
                    InjectionScheduleTask.created_at,
                    InjectionScheduleTask.id,
                )
            ).all()
        )
        for index, task in enumerate(lane):
            task.sequence_no = 1_000_000 + index
        db.flush()
        for index, task in enumerate(lane):
            task.sequence_no = index
        db.flush()


def prepare_lane_insert(
    db: Session,
    version: InjectionScheduleVersion,
    machine_id: str,
    target_index: int,
    *,
    excluded_task_id: str = "",
) -> int:
    lane = list(
        db.scalars(
            select(InjectionScheduleTask)
            .where(
                InjectionScheduleTask.factory_id == version.factory_id,
                InjectionScheduleTask.version_id == version.id,
                InjectionScheduleTask.machine_id == machine_id,
                InjectionScheduleTask.id != excluded_task_id
                if excluded_task_id
                else InjectionScheduleTask.id.is_not(None),
            )
            .order_by(
                InjectionScheduleTask.sequence_no,
                InjectionScheduleTask.created_at,
                InjectionScheduleTask.id,
            )
        ).all()
    )
    bounded_index = max(0, min(target_index, len(lane)))
    for index, task in enumerate(lane):
        task.sequence_no = 1_000_000 + index
    db.flush()
    for index, task in enumerate(lane):
        task.sequence_no = index * 2 + 1
    db.flush()
    return bounded_index * 2


def mark_implicit_task_revisions(
    db: Session,
    version: InjectionScheduleVersion,
    machine_ids: set[str],
    before_tasks: list[dict[str, Any]],
    command_touched_task_ids: set[str],
    actor: AuthContext,
    timestamp: str,
) -> None:
    """Give implicitly shifted lane tasks one revision for the command batch."""

    if not machine_ids:
        return
    before_by_id = {item["id"]: item for item in before_tasks}
    tasks = db.scalars(
        select(InjectionScheduleTask).where(
            InjectionScheduleTask.factory_id == version.factory_id,
            InjectionScheduleTask.version_id == version.id,
            InjectionScheduleTask.machine_id.in_(sorted(machine_ids)),
        )
    ).all()
    for task in tasks:
        before = before_by_id.get(task.id)
        if before is None or task.id in command_touched_task_ids:
            continue
        if (
            task.machine_id != before["machine_id"]
            or task.sequence_no != before["sequence_no"]
        ):
            task.revision += 1
            task.updated_by = actor.id
            task.updated_at = timestamp
            command_touched_task_ids.add(task.id)
    db.flush()


def recompute_all_lanes(
    db: Session,
    version: InjectionScheduleVersion,
    actor: AuthContext,
    timestamp: str,
) -> None:
    machine_ids = set(
        db.scalars(
            select(InjectionScheduleTask.machine_id).where(
                InjectionScheduleTask.factory_id == version.factory_id,
                InjectionScheduleTask.version_id == version.id,
            )
        ).all()
    )
    recompute_lanes(db, version, machine_ids, actor, timestamp)


def recompute_lanes(
    db: Session,
    version: InjectionScheduleVersion,
    machine_ids: set[str],
    actor: AuthContext,
    timestamp: str,
    *,
    command_touched_task_ids: set[str] | None = None,
) -> None:
    if not machine_ids:
        return
    rules = normalize_rule_config(json_object(version.rules_snapshot_json))
    minimum_task_hours = float(rules.get("minimum_task_hours") or 0.25)
    safety_factor = float(rules.get("shot_safety_factor") or 0.85)
    plan_base = parse_business_timestamp(version.plan_base_at) or business_now()
    touched_task_ids = command_touched_task_ids or set()
    sorted_machine_ids = sorted(machine_ids)
    machines = {
        item.id: item
        for item in db.scalars(
            select(InjectionMachineMaster).where(
                InjectionMachineMaster.factory_id == version.factory_id,
                InjectionMachineMaster.id.in_(sorted_machine_ids),
            )
        ).all()
    }
    all_tasks = list(
        db.scalars(
            select(InjectionScheduleTask)
            .where(
                InjectionScheduleTask.factory_id == version.factory_id,
                InjectionScheduleTask.version_id == version.id,
                InjectionScheduleTask.machine_id.in_(sorted_machine_ids),
            )
            .order_by(
                InjectionScheduleTask.machine_id,
                InjectionScheduleTask.sequence_no,
                InjectionScheduleTask.id,
            )
        ).all()
    )
    lanes: dict[str, list[InjectionScheduleTask]] = defaultdict(list)
    for task in all_tasks:
        lanes[task.machine_id].append(task)
    order_ids = {task.order_id for task in all_tasks}
    orders = {
        item.id: item
        for item in db.scalars(
            select(InjectionOrderMaster).where(
                InjectionOrderMaster.factory_id == version.factory_id,
                InjectionOrderMaster.id.in_(sorted(order_ids)),
            )
        ).all()
    }
    mold_codes = {
        normalize_key(order.mold_code)
        for order in orders.values()
        if normalize_key(order.mold_code)
    }
    molds = {
        item.normalized_mold_code: item
        for item in db.scalars(
            select(InjectionMoldMaster).where(
                InjectionMoldMaster.factory_id == version.factory_id,
                InjectionMoldMaster.normalized_mold_code.in_(
                    sorted(mold_codes)
                ),
            )
        ).all()
    }
    for machine_id in sorted_machine_ids:
        machine = machines.get(machine_id)
        if machine is None:
            raise HTTPException(status_code=404, detail="未找到该厂区的机台")
        cursor = plan_base
        available_at = parse_business_timestamp(machine.available_at)
        if available_at is not None and available_at > cursor:
            cursor = available_at
        lane = lanes.get(machine_id, [])
        previous_task: InjectionScheduleTask | None = None
        for task in lane:
            before_recompute = (
                task.planned_start_at,
                task.planned_finish_at,
                float(task.setup_hours or 0),
                float(task.duration_hours or 0),
                task.risk_level,
                task.risk_reasons_json,
            )
            already_command_touched = task.id in touched_task_ids
            order = orders.get(task.order_id)
            if order is None:
                raise HTTPException(status_code=404, detail="未找到该厂区的订单")
            mold = molds.get(normalize_key(order.mold_code))
            transition = (
                calculate_transition_setup(
                    from_mold_code=previous_task.mold_code_snapshot,
                    from_color=previous_task.color_snapshot,
                    from_color_rank=previous_task.color_rank_snapshot,
                    from_material=previous_task.material_snapshot,
                    to_mold_code=task.mold_code_snapshot,
                    to_color=task.color_snapshot,
                    to_color_rank=task.color_rank_snapshot,
                    to_material=task.material_snapshot,
                    machine_class=machine.machine_class,
                    rules=rules,
                )
                if previous_task is not None
                else {"setup_minutes": 0.0}
            )
            setup_hours = float(transition["setup_minutes"]) / 60
            duration_hours = max(
                task.planned_qty / order.daily_target_qty * 24
                if order.daily_target_qty
                else 24.0,
                minimum_task_hours,
            )
            existing_start = parse_business_timestamp(task.planned_start_at)
            existing_finish = parse_business_timestamp(task.planned_finish_at)
            if task.locked and existing_start is not None and existing_finish is not None:
                cursor = max(cursor, existing_finish)
            else:
                cursor = cursor + timedelta(hours=setup_hours)
                task.planned_start_at = cursor.strftime("%Y-%m-%d %H:%M:%S")
                cursor = cursor + timedelta(hours=duration_hours)
                task.planned_finish_at = cursor.strftime("%Y-%m-%d %H:%M:%S")
            risk_level, risk_reasons = assignment_precheck(
                order,
                machine,
                mold,
                safety_factor,
                rules,
            )
            missing_snapshot_fields = [
                field_name
                for field_name, value in (
                    ("mold_code_snapshot", task.mold_code_snapshot),
                    ("color_snapshot", task.color_snapshot),
                    ("material_snapshot", task.material_snapshot),
                )
                if normalize_key(value) in {"", "UNKNOWN", "未知", "待确认"}
            ]
            if missing_snapshot_fields:
                snapshot_reason = (
                    "相邻换型快照缺失："
                    + ", ".join(missing_snapshot_fields)
                )
                risk_reasons.append(snapshot_reason)
                if not bool(
                    rules.get(
                        "allow_missing_data_in_draft_with_manual_confirmation"
                    )
                ):
                    risk_level = "blocked"
                    risk_reasons.insert(
                        0,
                        "当前版本规则禁止将未知硬约束保存到草稿。",
                    )
                elif risk_level == "normal":
                    risk_level = "unknown"
            task.setup_hours = setup_hours
            task.duration_hours = duration_hours
            task.risk_level = risk_level
            task.risk_reasons_json = canonical_json(risk_reasons)
            after_recompute = (
                task.planned_start_at,
                task.planned_finish_at,
                float(task.setup_hours or 0),
                float(task.duration_hours or 0),
                task.risk_level,
                task.risk_reasons_json,
            )
            if after_recompute != before_recompute:
                if not already_command_touched:
                    task.revision += 1
                task.updated_by = actor.id
                task.updated_at = timestamp
            previous_task = task
    db.flush()


def validate_schedule_version(
    db: Session,
    factory_id: str,
    version_id: str,
    expected_revision: int,
    actor: AuthContext,
) -> dict[str, Any]:
    version = load_version(db, factory_id, version_id, for_update=True)
    if version.status != "draft":
        raise HTTPException(
            status_code=409,
            detail="已发布或已归档版本不可重新校验，请复制为新草稿",
        )
    if version.revision != expected_revision:
        raise revision_conflict(version.id, expected_revision, version.revision)
    lock_version_dependencies(db, version)
    validation = validate_version(
        db,
        version,
        actor,
        persist=True,
        commit=False,
    )
    if build_version_data_hash(db, version) != validation["data_hash"]:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "code": "validation_stale",
                "message": "校验期间排程或主数据已变化，请重试",
                "entity_id": version.id,
            },
        )
    updated = db.execute(
        update(InjectionScheduleVersion)
        .where(
            InjectionScheduleVersion.id == version.id,
            InjectionScheduleVersion.factory_id == factory_id,
            InjectionScheduleVersion.status == "draft",
            InjectionScheduleVersion.revision == expected_revision,
        )
        .values(
            data_hash=validation["data_hash"],
            validation_hash=validation["result_hash"],
            updated_by=actor.id,
            updated_at=now_text(),
        )
    )
    if updated.rowcount != 1:
        db.rollback()
        current = load_version(db, factory_id, version_id)
        raise revision_conflict(version_id, expected_revision, current.revision)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return validation


def publish_version(
    db: Session,
    factory_id: str,
    version_id: str,
    *,
    expected_revision: int,
    validation_run_id: str | None,
    reason: str,
    actor: AuthContext,
    request_id: str = "",
    ip_address: str = "",
) -> dict[str, Any]:
    version = load_version(db, factory_id, version_id, for_update=True)
    if version.status != "draft":
        raise HTTPException(status_code=409, detail="仅草稿版本可以发布")
    if version.revision != expected_revision:
        raise revision_conflict(version.id, expected_revision, version.revision)
    lock_version_dependencies(db, version)
    current_hash = build_version_data_hash(db, version)
    if validation_run_id:
        supplied = load_validation_run(db, factory_id, validation_run_id)
        if (
            supplied is None
            or supplied.version_id != version.id
            or supplied.version_revision != expected_revision
            or supplied.data_hash != current_hash
        ):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "validation_stale",
                    "message": "校验结果与当前草稿不一致，请重新校验",
                    "entity_id": version.id,
                },
            )

    validation = validate_version(
        db,
        version,
        actor,
        persist=True,
        commit=False,
    )
    if validation["blocking_count"]:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "code": "publish_blocked",
                "message": "草稿仍有阻断项或资料未知，不能发布",
                "blocking_count": validation["blocking_count"],
                "items": [
                    item for item in validation["items"] if item["blocking"]
                ][:50],
            },
        )

    if build_version_data_hash(db, version) != validation["data_hash"]:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "code": "validation_stale",
                "message": "发布校验期间排程或主数据已变化，请重新校验",
                "entity_id": version.id,
            },
        )

    timestamp = now_text()
    previous = db.scalar(
        select(InjectionScheduleVersion).where(
            InjectionScheduleVersion.factory_id == factory_id,
            InjectionScheduleVersion.status == "published",
            InjectionScheduleVersion.id != version.id,
        ).with_for_update()
    )
    if previous is not None:
        previous_revision = previous.revision
        superseded = db.execute(
            update(InjectionScheduleVersion)
            .where(
                InjectionScheduleVersion.id == previous.id,
                InjectionScheduleVersion.factory_id == factory_id,
                InjectionScheduleVersion.status == "published",
                InjectionScheduleVersion.revision == previous_revision,
            )
            .values(
                status="superseded",
                revision=InjectionScheduleVersion.revision + 1,
                superseded_at=timestamp,
                updated_by=actor.id,
                updated_at=timestamp,
            )
        )
        if superseded.rowcount != 1:
            db.rollback()
            current_previous = load_version(db, factory_id, previous.id)
            raise revision_conflict(
                previous.id,
                previous_revision,
                current_previous.revision,
            )
        add_audit_event(
            db,
            factory_id=factory_id,
            entity_type="schedule_version",
            entity_id=previous.id,
            action="superseded",
            actor=actor,
            request_id=request_id,
            ip_address=ip_address,
            reason=reason,
            old_revision=previous_revision,
            new_revision=previous_revision + 1,
            before={"status": "published"},
            after={"status": "superseded", "superseded_by_version_id": version.id},
        )
        db.flush()
    published = db.execute(
        update(InjectionScheduleVersion)
        .where(
            InjectionScheduleVersion.id == version.id,
            InjectionScheduleVersion.factory_id == factory_id,
            InjectionScheduleVersion.status == "draft",
            InjectionScheduleVersion.revision == expected_revision,
        )
        .values(
            status="published",
            revision=InjectionScheduleVersion.revision + 1,
            data_hash=validation["data_hash"],
            validation_hash=validation["result_hash"],
            published_by=actor.id,
            published_by_name=actor.display_name,
            published_at=timestamp,
            publish_reason=reason,
            updated_by=actor.id,
            updated_at=timestamp,
        )
    )
    if published.rowcount != 1:
        db.rollback()
        current = load_version(db, factory_id, version_id)
        raise revision_conflict(version_id, expected_revision, current.revision)
    state, _ = ensure_factory_defaults(db, factory_id, actor.id, timestamp)
    state_updated = db.execute(
        update(InjectionScheduleFactoryState)
        .where(
            InjectionScheduleFactoryState.factory_id == factory_id,
            InjectionScheduleFactoryState.revision == state.revision,
        )
        .values(
            current_published_version_id=version.id,
            revision=InjectionScheduleFactoryState.revision + 1,
            updated_at=timestamp,
        )
    )
    if state_updated.rowcount != 1:
        db.rollback()
        current_state = db.get(InjectionScheduleFactoryState, factory_id)
        raise revision_conflict(
            factory_id,
            state.revision,
            current_state.revision if current_state is not None else None,
        )
    add_audit_event(
        db,
        factory_id=factory_id,
        entity_type="schedule_version",
        entity_id=version.id,
        action="published",
        actor=actor,
        request_id=request_id,
        ip_address=ip_address,
        reason=reason,
        old_revision=expected_revision,
        new_revision=expected_revision + 1,
        before={
            "previous_published_version_id": previous.id if previous is not None else ""
        },
        after={
            "validation_run_id": validation["id"],
            "data_hash": validation["data_hash"],
            "result_hash": validation["result_hash"],
        },
    )
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.expire_all()
    return serialize_version(load_version(db, factory_id, version_id))


def version_detail(
    db: Session,
    factory_id: str,
    version_id: str,
) -> dict[str, Any]:
    version = load_version(db, factory_id, version_id)
    return {
        "version": serialize_version(version),
        "tasks": list_tasks(db, version),
        "conflicts": latest_version_conflicts(db, factory_id, version.id),
    }


def get_workspace(
    db: Session,
    factory_id: str,
    version_id: str | None = None,
) -> dict[str, Any]:
    state = db.get(InjectionScheduleFactoryState, factory_id)
    config = db.get(InjectionScheduleRuleConfig, factory_id)
    published_version_id = (
        state.current_published_version_id if state is not None else ""
    )
    active = (
        load_version(db, factory_id, version_id)
        if version_id
        else db.scalar(
            select(InjectionScheduleVersion)
            .where(
                InjectionScheduleVersion.factory_id == factory_id,
                InjectionScheduleVersion.status == "draft",
            )
            .order_by(InjectionScheduleVersion.version_no.desc())
        )
        or (
            load_version(db, factory_id, published_version_id)
            if published_version_id
            else None
        )
    )
    return {
        "factory_id": factory_id,
        "mode": "formal",
        "active_version": serialize_version(active) if active is not None else None,
        "versions": list_versions(db, factory_id),
        "machines": list_machine_masters(db, factory_id),
        "molds": list_mold_masters(db, factory_id),
        "orders": list_order_masters(db, factory_id),
        "tasks": list_tasks(db, active) if active is not None else [],
        "conflicts": latest_version_conflicts(db, factory_id, active.id)
        if active is not None
        else [],
        "rule_config": serialize_rule_config(config)
        if config is not None
        else {
            "factory_id": factory_id,
            "config": DEFAULT_RULE_CONFIG,
            "revision": 0,
            "updated_by": "",
            "updated_at": "",
        },
        "workspace_revision": active.revision
        if active is not None
        else state.revision
        if state is not None
        else 0,
    }


def diff_version(
    db: Session,
    factory_id: str,
    version_id: str,
    against_version_id: str | None = None,
) -> dict[str, Any]:
    version = load_version(db, factory_id, version_id)
    if against_version_id:
        against = load_version(db, factory_id, against_version_id)
    elif version.base_version_id:
        against = load_version(db, factory_id, version.base_version_id)
    else:
        state = db.get(InjectionScheduleFactoryState, factory_id)
        against = (
            load_version(db, factory_id, state.current_published_version_id)
            if state is not None
            and state.current_published_version_id
            and state.current_published_version_id != version.id
            else None
        )
    current = aggregate_version_tasks(db, version)
    before = aggregate_version_tasks(db, against) if against is not None else {}
    order_ids = sorted(set(current) | set(before))
    items: list[dict[str, Any]] = []
    for order_id in order_ids:
        old = before.get(order_id)
        new = current.get(order_id)
        if old == new:
            continue
        change_type = (
            "added"
            if old is None
            else "removed"
            if new is None
            else "moved"
            if old["machine_ids"] != new["machine_ids"]
            else "quantity_changed"
            if old["planned_qty"] != new["planned_qty"]
            else "rescheduled"
        )
        items.append(
            {
                "order_id": order_id,
                "order_no": str((new or old or {}).get("order_no") or ""),
                "change_type": change_type,
                "before": old,
                "after": new,
            }
        )
    summary = dict(Counter(item["change_type"] for item in items))
    current_metrics = version_operational_metrics(db, version)
    before_metrics = version_operational_metrics(db, against)
    split_orders = sum(
        1
        for order_id in set(current) & set(before)
        if current[order_id].get("task_count", 0)
        > before[order_id].get("task_count", 0)
    )
    locked_changes = sum(
        abs(
            int(current.get(order_id, {}).get("locked_task_count", 0))
            - int(before.get(order_id, {}).get("locked_task_count", 0))
        )
        for order_id in set(current) | set(before)
    )
    changed_delivery_dates = sum(
        1
        for order_id in set(current) & set(before)
        if current[order_id].get("delivery_due_date", "")
        != before[order_id].get("delivery_due_date", "")
    )
    current_conflicts = version_conflict_signatures(db, version)
    before_conflicts = version_conflict_signatures(db, against)
    added_conflicts = sum((current_conflicts - before_conflicts).values())
    resolved_conflicts = sum((before_conflicts - current_conflicts).values())
    changeover_delta = round(
        current_metrics["changeover_minutes"]
        - before_metrics["changeover_minutes"]
    )
    mold_change_delta = (
        current_metrics["mold_change_count"]
        - before_metrics["mold_change_count"]
    )
    return {
        "version_id": version.id,
        "against_version_id": against.id if against is not None else None,
        "summary": {
            key: summary.get(key, 0)
            for key in (
                "added",
                "removed",
                "moved",
                "rescheduled",
                "quantity_changed",
            )
        }
        | {
            "split_orders": split_orders,
            "split_order_count": split_orders,
            "locked_changes": locked_changes,
            "lock_change_count": locked_changes,
            "changed_delivery_dates": changed_delivery_dates,
            "delivery_date_change_count": changed_delivery_dates,
            "added_conflict_count": added_conflicts,
            "added_conflicts": added_conflicts,
            "resolved_conflict_count": resolved_conflicts,
            "resolved_conflicts": resolved_conflicts,
            "changeover_minutes_delta": changeover_delta,
            "changeover_delta": changeover_delta,
            "mold_change_count_delta": mold_change_delta,
            "task_count_before": before_metrics["task_count"],
            "task_count_after": current_metrics["task_count"],
            "locked_task_count_before": before_metrics["locked_task_count"],
            "locked_task_count_after": current_metrics["locked_task_count"],
            "conflict_count_before": sum(before_conflicts.values()),
            "conflict_count_after": sum(current_conflicts.values()),
            "mold_change_count_before": before_metrics["mold_change_count"],
            "mold_change_count_after": current_metrics["mold_change_count"],
        },
        "items": items,
    }


def aggregate_version_tasks(
    db: Session,
    version: InjectionScheduleVersion | None,
) -> dict[str, dict[str, Any]]:
    if version is None:
        return {}
    tasks = list(
        db.scalars(
            select(InjectionScheduleTask).where(
                InjectionScheduleTask.factory_id == version.factory_id,
                InjectionScheduleTask.version_id == version.id,
            )
        ).all()
    )
    machines = {
        item.id: item.machine_code
        for item in db.scalars(
            select(InjectionMachineMaster).where(
                InjectionMachineMaster.factory_id == version.factory_id
            )
        ).all()
    }
    grouped: dict[str, list[InjectionScheduleTask]] = defaultdict(list)
    for task in tasks:
        grouped[task.order_id].append(task)
    return {
        order_id: {
            "order_no": next(
                (
                    item.order_no_snapshot
                    for item in rows
                    if item.order_no_snapshot
                ),
                "",
            ),
            "planned_qty": sum(item.planned_qty for item in rows),
            "machine_ids": sorted({item.machine_id for item in rows}),
            "machine_codes": sorted(
                {
                    item.machine_code_snapshot
                    or machines.get(item.machine_id, "")
                    for item in rows
                }
            ),
            "mold_ids": sorted({item.mold_id or "" for item in rows}),
            "mold_codes": sorted(
                {item.mold_code_snapshot for item in rows if item.mold_code_snapshot}
            ),
            "planned_start_at": min(
                (item.planned_start_at for item in rows if item.planned_start_at),
                default="",
            ),
            "planned_finish_at": max(
                (item.planned_finish_at for item in rows if item.planned_finish_at),
                default="",
            ),
            "delivery_due_date": next(
                (
                    item.delivery_due_date_snapshot
                    for item in rows
                    if item.delivery_due_date_snapshot
                ),
                "",
            ),
            "delivery_slack_hours": delivery_slack_hours(rows),
            "task_count": len(rows),
            "locked_task_count": sum(bool(item.locked) for item in rows),
            "split_group_count": len(
                {item.split_group_id for item in rows if item.split_group_id}
            ),
            "changeover_minutes": round(
                sum(item.setup_hours for item in rows) * 60
            ),
        }
        for order_id, rows in grouped.items()
    }


def delivery_slack_hours(
    tasks: list[InjectionScheduleTask],
) -> float | None:
    due_value = next(
        (
            item.delivery_due_date_snapshot
            for item in tasks
            if item.delivery_due_date_snapshot
        ),
        "",
    )
    finish_value = max(
        (item.planned_finish_at for item in tasks if item.planned_finish_at),
        default="",
    )
    finish = parse_business_timestamp(finish_value)
    try:
        due = date.fromisoformat(due_value)
    except ValueError:
        return None
    if finish is None:
        return None
    due_at = datetime.combine(due, time.max)
    return round((due_at - finish.replace(tzinfo=None)).total_seconds() / 3600, 2)


def version_operational_metrics(
    db: Session,
    version: InjectionScheduleVersion | None,
) -> dict[str, int]:
    if version is None:
        return {
            "task_count": 0,
            "locked_task_count": 0,
            "mold_change_count": 0,
            "changeover_minutes": 0,
        }
    tasks = list(
        db.scalars(
            select(InjectionScheduleTask)
            .where(
                InjectionScheduleTask.factory_id == version.factory_id,
                InjectionScheduleTask.version_id == version.id,
            )
            .order_by(
                InjectionScheduleTask.machine_id,
                InjectionScheduleTask.sequence_no,
                InjectionScheduleTask.id,
            )
        ).all()
    )
    mold_change_count = 0
    previous_by_machine: dict[str, str] = {}
    for task in tasks:
        mold_key = task.mold_code_snapshot or task.mold_id or ""
        previous = previous_by_machine.get(task.machine_id)
        if previous is not None and mold_key and previous != mold_key:
            mold_change_count += 1
        previous_by_machine[task.machine_id] = mold_key
    return {
        "task_count": len(tasks),
        "locked_task_count": sum(bool(item.locked) for item in tasks),
        "mold_change_count": mold_change_count,
        "changeover_minutes": round(sum(item.setup_hours for item in tasks) * 60),
    }


def version_conflict_signatures(
    db: Session,
    version: InjectionScheduleVersion | None,
) -> Counter[tuple[str, str, str, str]]:
    if version is None:
        return Counter()
    task_order_ids = {
        item.id: item.order_id
        for item in db.scalars(
            select(InjectionScheduleTask).where(
                InjectionScheduleTask.factory_id == version.factory_id,
                InjectionScheduleTask.version_id == version.id,
            )
        ).all()
    }
    return Counter(
        (
            task_order_ids.get(item["task_id"], ""),
            item["constraint_code"],
            item["status"],
            item["message"],
        )
        for item in latest_version_conflicts(
            db,
            version.factory_id,
            version.id,
        )
    )


def list_tasks(
    db: Session,
    version: InjectionScheduleVersion,
) -> list[dict[str, Any]]:
    tasks = list(
        db.scalars(
            select(InjectionScheduleTask)
            .where(
                InjectionScheduleTask.factory_id == version.factory_id,
                InjectionScheduleTask.version_id == version.id,
            )
            .order_by(
                InjectionScheduleTask.machine_id,
                InjectionScheduleTask.sequence_no,
                InjectionScheduleTask.id,
            )
        ).all()
    )
    order_ids = {item.order_id for item in tasks}
    machine_ids = {item.machine_id for item in tasks}
    mold_ids = {item.mold_id for item in tasks if item.mold_id}
    orders = {
        item.id: item
        for item in db.scalars(
            select(InjectionOrderMaster).where(
                InjectionOrderMaster.factory_id == version.factory_id,
                InjectionOrderMaster.id.in_(order_ids),
            )
        ).all()
    } if order_ids else {}
    machines = {
        item.id: item
        for item in db.scalars(
            select(InjectionMachineMaster).where(
                InjectionMachineMaster.factory_id == version.factory_id,
                InjectionMachineMaster.id.in_(machine_ids),
            )
        ).all()
    } if machine_ids else {}
    molds = {
        item.id: item
        for item in db.scalars(
            select(InjectionMoldMaster).where(
                InjectionMoldMaster.factory_id == version.factory_id,
                InjectionMoldMaster.id.in_(mold_ids),
            )
        ).all()
    } if mold_ids else {}
    return [
        serialize_task(
            item,
            orders.get(item.order_id),
            machines.get(item.machine_id),
            molds.get(item.mold_id) if item.mold_id else None,
        )
        for item in tasks
    ]


def serialize_version(version: InjectionScheduleVersion) -> dict[str, Any]:
    return {
        "id": version.id,
        "factory_id": version.factory_id,
        "version_no": version.version_no,
        "name": version.name,
        "status": version.status,
        "revision": version.revision,
        "business_date": version.business_date,
        "plan_base_at": version.plan_base_at,
        "base_version_id": version.base_version_id,
        "source_batch_id": version.source_batch_id,
        "rules_snapshot": json_object(version.rules_snapshot_json),
        "rule_config_revision": version.rule_config_revision,
        "data_hash": version.data_hash,
        "validation_hash": version.validation_hash,
        "summary": json_object(version.summary_json),
        "created_by": version.created_by,
        "created_by_name": version.created_by_name,
        "created_at": version.created_at,
        "updated_by": version.updated_by,
        "updated_at": version.updated_at,
        "published_by": version.published_by,
        "published_by_name": version.published_by_name,
        "published_at": version.published_at,
        "publish_reason": version.publish_reason,
        "superseded_at": version.superseded_at,
    }


def serialize_task(
    task: InjectionScheduleTask,
    order: InjectionOrderMaster | None,
    machine: InjectionMachineMaster | None,
    mold: InjectionMoldMaster | None,
) -> dict[str, Any]:
    return {
        "id": task.id,
        "factory_id": task.factory_id,
        "version_id": task.version_id,
        "order_id": task.order_id,
        "order_no": task.order_no_snapshot,
        "product_code": task.product_code_snapshot,
        "product_name": task.product_name_snapshot,
        "delivery_due_date": task.delivery_due_date_snapshot,
        "mold_id": task.mold_id,
        "mold_code": task.mold_code_snapshot,
        "color": task.color_snapshot,
        "color_rank": task.color_rank_snapshot,
        "material": task.material_snapshot,
        "machine_id": task.machine_id,
        "machine_code": task.machine_code_snapshot,
        "sequence_no": task.sequence_no,
        "planned_qty": task.planned_qty,
        "planned_start_at": task.planned_start_at,
        "planned_finish_at": task.planned_finish_at,
        "setup_hours": task.setup_hours,
        "duration_hours": task.duration_hours,
        "locked": bool(task.locked),
        "split_group_id": task.split_group_id,
        "parent_task_id": task.parent_task_id,
        "source": task.source,
        "execution_status": task.execution_status,
        "protected": bool(task.protected),
        "recommendation_score": task.recommendation_score,
        "score_breakdown": json_list(task.score_breakdown_json),
        "constraint_snapshot": json_list(task.constraint_snapshot_json),
        "recommendation_context_hash": task.recommendation_context_hash,
        "risk_level": task.risk_level,
        "risk_reasons": json_list(task.risk_reasons_json),
        "revision": task.revision,
    }


def version_summary(
    db: Session,
    version: InjectionScheduleVersion,
) -> dict[str, Any]:
    tasks = list(
        db.scalars(
            select(InjectionScheduleTask).where(
                InjectionScheduleTask.factory_id == version.factory_id,
                InjectionScheduleTask.version_id == version.id,
            )
        ).all()
    )
    return {
        "task_count": len(tasks),
        "machine_count": len({item.machine_id for item in tasks}),
        "order_count": len({item.order_id for item in tasks}),
        "locked_task_count": sum(bool(item.locked) for item in tasks),
        "risk_task_count": sum(item.risk_level != "normal" for item in tasks),
        "planned_qty": sum(item.planned_qty for item in tasks),
    }


def task_change_snapshot(
    db: Session,
    version: InjectionScheduleVersion,
) -> list[dict[str, Any]]:
    return [
        {
            "id": item["id"],
            "order_id": item["order_id"],
            "machine_id": item["machine_id"],
            "sequence_no": item["sequence_no"],
            "planned_qty": item["planned_qty"],
            "planned_start_at": item["planned_start_at"],
            "planned_finish_at": item["planned_finish_at"],
            "setup_hours": item["setup_hours"],
            "duration_hours": item["duration_hours"],
            "locked": item["locked"],
            "risk_level": item["risk_level"],
            "risk_reasons": item["risk_reasons"],
            "revision": item["revision"],
        }
        for item in list_tasks(db, version)
    ]


def latest_confirmed_batch_id(db: Session, factory_id: str) -> str:
    from app.models.injection_schedule import InjectionScheduleImportBatch

    return (
        db.scalar(
            select(InjectionScheduleImportBatch.id)
            .where(
                InjectionScheduleImportBatch.factory_id == factory_id,
                InjectionScheduleImportBatch.status == "confirmed",
            )
            .order_by(
                InjectionScheduleImportBatch.confirmed_at.desc(),
                InjectionScheduleImportBatch.id.desc(),
            )
        )
        or ""
    )


def load_task_for_version(
    db: Session,
    version: InjectionScheduleVersion,
    task_id: str,
) -> InjectionScheduleTask:
    task = db.scalar(
        select(InjectionScheduleTask).where(
            InjectionScheduleTask.id == task_id,
            InjectionScheduleTask.factory_id == version.factory_id,
            InjectionScheduleTask.version_id == version.id,
        )
    )
    if task is None:
        raise HTTPException(status_code=404, detail="未找到该草稿中的排程任务")
    return task


def load_order_for_version(
    db: Session,
    version: InjectionScheduleVersion,
    order_id: str,
) -> InjectionOrderMaster:
    order = db.scalar(
        select(InjectionOrderMaster).where(
            InjectionOrderMaster.id == order_id,
            InjectionOrderMaster.factory_id == version.factory_id,
        )
    )
    if order is None:
        raise HTTPException(status_code=404, detail="未找到该厂区的订单")
    return order


def load_machine_for_version(
    db: Session,
    version: InjectionScheduleVersion,
    machine_id: str,
) -> InjectionMachineMaster:
    machine = db.scalar(
        select(InjectionMachineMaster).where(
            InjectionMachineMaster.id == machine_id,
            InjectionMachineMaster.factory_id == version.factory_id,
        )
    )
    if machine is None:
        raise HTTPException(status_code=404, detail="未找到该厂区的机台")
    return machine


def find_order_mold(
    db: Session,
    factory_id: str,
    order: InjectionOrderMaster,
) -> InjectionMoldMaster | None:
    normalized = normalize_key(order.mold_code)
    if not normalized:
        return None
    return db.scalar(
        select(InjectionMoldMaster).where(
            InjectionMoldMaster.factory_id == factory_id,
            InjectionMoldMaster.normalized_mold_code == normalized,
        )
    )


def list_audit_events(
    db: Session,
    factory_id: str,
    limit: int,
) -> list[dict[str, Any]]:
    events = db.scalars(
        select(InjectionScheduleAuditEvent)
        .where(InjectionScheduleAuditEvent.factory_id == factory_id)
        .order_by(
            InjectionScheduleAuditEvent.created_at.desc(),
            InjectionScheduleAuditEvent.id.desc(),
        )
        .limit(max(1, min(limit, 500)))
    ).all()
    return [
        {
            "id": item.id,
            "factory_id": item.factory_id,
            "entity_type": item.entity_type,
            "entity_id": item.entity_id,
            "action": item.action,
            "actor_id": item.actor_id,
            "actor_name": item.actor_name,
            "request_id": item.request_id,
            "ip_address": item.ip_address,
            "reason": item.reason,
            "old_revision": item.old_revision,
            "new_revision": item.new_revision,
            "before": json_object(item.before_json),
            "after": json_object(item.after_json),
            "created_at": item.created_at,
        }
        for item in events
    ]
