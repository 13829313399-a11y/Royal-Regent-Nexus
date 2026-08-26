from __future__ import annotations

import json
from dataclasses import replace
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.injection_scheduling_execution import InjectionSchedulingAuditEvent
from app.models.injection_scheduling_import import (
    InjectionSchedulingImportProfile,
    InjectionSchedulingImportProfileFactory,
)
from app.services.auth import AuthContext
from app.services.injection_scheduling_execution import _actor_name, _audit, _now
from app.services.injection_scheduling_profiles import (
    BUILTIN_IMPORT_PROFILES,
    ImportProfile,
    profile_config,
    profile_config_json,
    profile_definition_digest,
    profile_from_config,
    profile_header_fingerprint,
    profile_template_signature,
)


def _profile_from_record(
    record: InjectionSchedulingImportProfile,
    factories: tuple[str, ...],
) -> ImportProfile:
    try:
        config = json.loads(record.config_json)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Profile {record.id} 配置不是合法 JSON") from exc
    profile = profile_from_config(config)
    if profile_definition_digest(profile) != record.definition_sha256:
        raise RuntimeError(f"Profile {record.id} 定义摘要不一致，拒绝用于导入")
    if profile.document_kind != record.document_kind:
        raise RuntimeError(f"Profile {record.id} document_kind 与受控列不一致")
    return replace(profile, status=record.status, factories=factories)


def active_profiles_for_factory(
    db: Session,
    factory_id: str,
    document_kind: str = "PLANNED_SCHEDULE",
) -> tuple[ImportProfile, ...]:
    rows = db.execute(
        select(
            InjectionSchedulingImportProfile, InjectionSchedulingImportProfileFactory
        )
        .join(
            InjectionSchedulingImportProfileFactory,
            InjectionSchedulingImportProfileFactory.profile_id
            == InjectionSchedulingImportProfile.id,
        )
        .where(
            InjectionSchedulingImportProfileFactory.factory_id == factory_id,
            InjectionSchedulingImportProfile.status == "ACTIVE",
            InjectionSchedulingImportProfile.document_kind == document_kind,
        )
        .order_by(
            InjectionSchedulingImportProfile.profile_family,
            InjectionSchedulingImportProfile.revision.desc(),
        )
    ).all()
    selected: list[ImportProfile] = []
    seen_families: set[str] = set()
    for profile, binding in rows:
        if profile.profile_family in seen_families:
            continue
        seen_families.add(profile.profile_family)
        selected.append(_profile_from_record(profile, (binding.factory_id,)))
    return tuple(selected)


def active_profile_by_structural_signature(
    db: Session,
    *,
    factory_id: str,
    structural_signature: str,
    document_kind: str,
) -> ImportProfile | None:
    matches = [
        profile
        for profile in active_profiles_for_factory(
            db, factory_id, document_kind=document_kind
        )
        if profile.recognition_config.get("structural_layout_signature")
        == structural_signature
    ]
    if not matches:
        return None
    return max(
        matches,
        key=lambda item: (item.revision, item.profile_family),
    )


def profile_revision_for_factory(
    db: Session,
    *,
    factory_id: str,
    profile_id: str,
    profile_revision: int,
    allowed_statuses: tuple[str, ...] = ("ACTIVE",),
) -> ImportProfile | None:
    row = db.execute(
        select(
            InjectionSchedulingImportProfile,
            InjectionSchedulingImportProfileFactory,
        )
        .join(
            InjectionSchedulingImportProfileFactory,
            InjectionSchedulingImportProfileFactory.profile_id
            == InjectionSchedulingImportProfile.id,
        )
        .where(
            InjectionSchedulingImportProfile.id == profile_id,
            InjectionSchedulingImportProfile.revision == profile_revision,
            InjectionSchedulingImportProfile.status.in_(allowed_statuses),
            InjectionSchedulingImportProfileFactory.factory_id == factory_id,
        )
    ).one_or_none()
    if row is None:
        return None
    profile, binding = row
    return _profile_from_record(profile, (binding.factory_id,))


def profile_record_out(
    db: Session, record: InjectionSchedulingImportProfile
) -> dict[str, Any]:
    factories = tuple(
        db.scalars(
            select(InjectionSchedulingImportProfileFactory.factory_id)
            .where(InjectionSchedulingImportProfileFactory.profile_id == record.id)
            .order_by(InjectionSchedulingImportProfileFactory.factory_id)
        ).all()
    )
    _profile_from_record(record, factories)
    return {
        "id": record.id,
        "profile_code": record.profile_code,
        "profile_family": record.profile_family,
        "revision": record.revision,
        "lifecycle_revision": record.lifecycle_revision,
        "name": record.name,
        "description": record.description,
        "status": record.status,
        "factories": list(factories),
        "definition_sha256": record.definition_sha256,
        "template_signature": record.template_signature,
        "header_fingerprint": record.header_fingerprint,
        "renderer_code": record.renderer_code,
        "document_kind": record.document_kind,
        "source_namespace_id": record.source_namespace_id,
        "recognition": json.loads(record.recognition_json),
        "config": json.loads(record.config_json),
        "created_by": record.created_by,
        "created_by_name": record.created_by_name,
        "created_at": record.created_at,
        "reviewed_by": record.reviewed_by,
        "reviewed_by_name": record.reviewed_by_name,
        "reviewed_at": record.reviewed_at,
        "retired_by": record.retired_by,
        "retired_by_name": record.retired_by_name,
        "retired_at": record.retired_at,
    }


def list_profile_records(
    db: Session, factory_id: str
) -> list[InjectionSchedulingImportProfile]:
    return list(
        db.scalars(
            select(InjectionSchedulingImportProfile)
            .join(
                InjectionSchedulingImportProfileFactory,
                InjectionSchedulingImportProfileFactory.profile_id
                == InjectionSchedulingImportProfile.id,
            )
            .where(InjectionSchedulingImportProfileFactory.factory_id == factory_id)
            .order_by(
                InjectionSchedulingImportProfile.profile_family,
                InjectionSchedulingImportProfile.revision.desc(),
            )
        ).all()
    )


def create_profile_revision(
    db: Session,
    *,
    factory_id: str,
    profile_family: str,
    profile_code: str,
    name: str,
    description: str,
    expected_family_revision: int,
    request_id: str,
    config: dict[str, Any],
    user: AuthContext,
    commit: bool = True,
) -> InjectionSchedulingImportProfile:
    latest_record = db.scalar(
        select(InjectionSchedulingImportProfile)
        .where(InjectionSchedulingImportProfile.profile_family == profile_family)
        .order_by(InjectionSchedulingImportProfile.revision.desc())
        .limit(1)
        .with_for_update()
    )
    current_revision = latest_record.revision if latest_record is not None else 0
    if current_revision != expected_family_revision:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Profile family revision 已变化，请重新加载",
                "expected_revision": expected_family_revision,
                "current_revision": current_revision,
            },
        )
    next_revision = current_revision + 1
    if db.scalar(
        select(InjectionSchedulingImportProfile.id).where(
            InjectionSchedulingImportProfile.profile_code == profile_code
        )
    ):
        raise HTTPException(status_code=409, detail="profile_code 已存在")
    profile_id = f"isprofile-{uuid4().hex}"
    controlled_config = json.loads(json.dumps(config, ensure_ascii=False))
    controlled_config.update(
        {
            "profile_id": profile_id,
            "profile_code": profile_code,
            "profile_family": profile_family,
            "revision": next_revision,
            "name": name,
            "factories": [factory_id],
            "status": "PROFILE_DRAFT",
        }
    )
    try:
        profile = profile_from_config(controlled_config)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    timestamp = _now()
    actor_name = _actor_name(user)
    record = InjectionSchedulingImportProfile(
        id=profile_id,
        profile_code=profile_code,
        profile_family=profile_family,
        revision=next_revision,
        lifecycle_revision=1,
        name=name,
        description=description,
        status="PROFILE_DRAFT",
        config_json=profile_config_json(profile),
        definition_sha256=profile_definition_digest(profile),
        template_signature=profile_template_signature(profile),
        header_fingerprint=profile_header_fingerprint(profile),
        renderer_code=profile.renderer_code,
        document_kind=profile.document_kind,
        source_namespace_id=profile.source_namespace_id,
        recognition_json=json.dumps(
            profile_config(profile).get("recognition", {}),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ),
        created_by=user.id,
        created_by_name=actor_name,
        created_at=timestamp,
        reviewed_by="",
        reviewed_by_name="",
        reviewed_at="",
        retired_by="",
        retired_by_name="",
        retired_at="",
    )
    db.add(record)
    db.add(
        InjectionSchedulingImportProfileFactory(
            id=f"{profile_id}:{factory_id}",
            profile_id=profile_id,
            factory_id=factory_id,
            created_by=user.id,
            created_by_name=actor_name,
            created_at=timestamp,
        )
    )
    try:
        db.flush()
        _audit(
            db,
            factory_id=factory_id,
            event_type="import_profile_revision_created",
            entity_type="import_profile",
            entity_id=profile_id,
            entity_revision=next_revision,
            request_id=request_id,
            detail={
                "profile_family": profile_family,
                "profile_code": profile_code,
                "definition_sha256": record.definition_sha256,
            },
            user=user,
        )
        if commit:
            db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Profile revision 或 profile_code 已被其他操作占用，请重新加载",
        ) from exc
    return record


def create_active_workbench_profile_revision(
    db: Session,
    *,
    factory_id: str,
    profile_family: str,
    profile_code: str,
    name: str,
    description: str,
    expected_family_revision: int,
    request_id: str,
    config: dict[str, Any],
    user: AuthContext,
    commit: bool = True,
) -> InjectionSchedulingImportProfile:
    """Save a clerk-corrected mapping as an immediately usable factory template.

    The simplified workbench intentionally has no profile approval step.  The
    older profile-governance routes retain their submitter/reviewer separation;
    this helper is only used by the workbench import contract and records a
    distinct audit event.  Existing shared profiles remain active so a
    factory-local correction cannot disable imports in another factory.
    """

    record = create_profile_revision(
        db,
        factory_id=factory_id,
        profile_family=profile_family,
        profile_code=profile_code,
        name=name,
        description=description,
        expected_family_revision=expected_family_revision,
        request_id=request_id,
        config=config,
        user=user,
        commit=False,
    )
    timestamp = _now()
    actor_name = _actor_name(user)
    record.status = "ACTIVE"
    record.lifecycle_revision += 1
    record.reviewed_by = user.id
    record.reviewed_by_name = actor_name
    record.reviewed_at = timestamp
    shadowed_records = list(
        db.scalars(
            select(InjectionSchedulingImportProfile)
            .join(
                InjectionSchedulingImportProfileFactory,
                InjectionSchedulingImportProfile.id
                == InjectionSchedulingImportProfileFactory.profile_id,
            )
            .where(
                InjectionSchedulingImportProfileFactory.factory_id == factory_id,
                InjectionSchedulingImportProfile.profile_family == profile_family,
                InjectionSchedulingImportProfile.status == "ACTIVE",
                InjectionSchedulingImportProfile.id != record.id,
            )
        ).all()
    )
    _audit(
        db,
        factory_id=factory_id,
        event_type="workbench_import_template_activated",
        entity_type="import_profile",
        entity_id=record.id,
        entity_revision=record.revision,
        request_id=request_id,
        detail={
            "reason": description,
            "definition_sha256": record.definition_sha256,
            "workflow": "SIMPLIFIED_WORKBENCH",
            "shadowed_factory_profile_ids": [
                previous.id for previous in shadowed_records
            ],
        },
        user=user,
    )
    try:
        if commit:
            db.commit()
        else:
            db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="工作台映射模板激活冲突，请重新预览",
        ) from exc
    return record


def transition_profile(
    db: Session,
    *,
    profile_id: str,
    factory_id: str,
    expected_lifecycle_revision: int,
    target_status: str,
    request_id: str,
    reason: str,
    user: AuthContext,
) -> InjectionSchedulingImportProfile:
    record = db.scalar(
        select(InjectionSchedulingImportProfile)
        .join(
            InjectionSchedulingImportProfileFactory,
            InjectionSchedulingImportProfileFactory.profile_id
            == InjectionSchedulingImportProfile.id,
        )
        .where(
            InjectionSchedulingImportProfile.id == profile_id,
            InjectionSchedulingImportProfileFactory.factory_id == factory_id,
        )
        .with_for_update()
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Profile 不存在于当前厂区")
    if record.lifecycle_revision != expected_lifecycle_revision:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Profile lifecycle revision 已变化，请重新加载",
                "expected_revision": expected_lifecycle_revision,
                "current_revision": record.lifecycle_revision,
            },
        )
    previous_status = record.status
    if target_status == "ACTIVE" and previous_status not in {
        "PROFILE_DRAFT",
        "RETIRED",
    }:
        raise HTTPException(
            status_code=409, detail="只有 PROFILE_DRAFT 或 RETIRED Profile 可以激活"
        )
    if target_status == "ACTIVE" and record.created_by == user.id:
        raise HTTPException(
            status_code=403, detail="Profile 提交人与审核激活人必须分离"
        )
    if target_status == "RETIRED" and record.status != "ACTIVE":
        raise HTTPException(status_code=409, detail="只有 ACTIVE Profile 可以停用")
    timestamp = _now()
    actor_name = _actor_name(user)
    if target_status == "ACTIVE":
        previous_records = list(
            db.scalars(
                select(InjectionSchedulingImportProfile)
                .join(
                    InjectionSchedulingImportProfileFactory,
                    InjectionSchedulingImportProfileFactory.profile_id
                    == InjectionSchedulingImportProfile.id,
                )
                .where(
                    InjectionSchedulingImportProfile.profile_family
                    == record.profile_family,
                    InjectionSchedulingImportProfile.status == "ACTIVE",
                    InjectionSchedulingImportProfile.id != record.id,
                    InjectionSchedulingImportProfileFactory.factory_id == factory_id,
                )
                .with_for_update()
            ).all()
        )
        for previous in previous_records:
            previous.status = "RETIRED"
            previous.lifecycle_revision += 1
            previous.retired_by = user.id
            previous.retired_by_name = actor_name
            previous.retired_at = timestamp
            _audit(
                db,
                factory_id=factory_id,
                event_type="import_profile_retired_by_successor",
                entity_type="import_profile",
                entity_id=previous.id,
                entity_revision=previous.revision,
                request_id=request_id,
                detail={"reason": reason, "successor_profile_id": record.id},
                user=user,
            )
        record.reviewed_by = user.id
        record.reviewed_by_name = actor_name
        record.reviewed_at = timestamp
        record.retired_by = ""
        record.retired_by_name = ""
        record.retired_at = ""
    else:
        record.retired_by = user.id
        record.retired_by_name = actor_name
        record.retired_at = timestamp
    record.status = target_status
    record.lifecycle_revision += 1
    _audit(
        db,
        factory_id=factory_id,
        event_type=(
            (
                "import_profile_reactivated"
                if previous_status == "RETIRED"
                else "import_profile_activated"
            )
            if target_status == "ACTIVE"
            else "import_profile_retired"
        ),
        entity_type="import_profile",
        entity_id=record.id,
        entity_revision=record.revision,
        request_id=request_id,
        detail={"reason": reason, "definition_sha256": record.definition_sha256},
        user=user,
    )
    db.commit()
    return record


def seed_builtin_import_profiles(db: Session) -> None:
    timestamp = _now()
    changed = False
    for profile in BUILTIN_IMPORT_PROFILES:
        digest = profile_definition_digest(profile)
        record = db.get(InjectionSchedulingImportProfile, profile.profile_id)
        if record is None:
            record = InjectionSchedulingImportProfile(
                id=profile.profile_id,
                profile_code=profile.profile_code,
                profile_family=profile.profile_family,
                revision=profile.revision,
                lifecycle_revision=1,
                name=profile.name,
                description="系统内置且经过样本契约验证的注塑排产导入 Profile",
                status="ACTIVE",
                config_json=profile_config_json(profile),
                definition_sha256=digest,
                template_signature=profile_template_signature(profile),
                header_fingerprint=profile_header_fingerprint(profile),
                renderer_code=profile.renderer_code,
                document_kind=profile.document_kind,
                source_namespace_id=profile.source_namespace_id,
                recognition_json=json.dumps(
                    profile_config(profile).get("recognition", {}),
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                created_by="system-seed",
                created_by_name="系统初始化",
                created_at=timestamp,
                reviewed_by="system-seed",
                reviewed_by_name="系统初始化",
                reviewed_at=timestamp,
                retired_by="",
                retired_by_name="",
                retired_at="",
            )
            db.add(record)
            changed = True
        elif record.definition_sha256 != digest:
            raise RuntimeError(
                f"ACTIVE Profile {profile.profile_id} 已持久化且定义发生变化；"
                "请创建新 revision，禁止原地覆盖"
            )
        for factory_id in profile.factories:
            binding_id = f"{profile.profile_id}:{factory_id}"
            if db.get(InjectionSchedulingImportProfileFactory, binding_id) is not None:
                continue
            db.add(
                InjectionSchedulingImportProfileFactory(
                    id=binding_id,
                    profile_id=profile.profile_id,
                    factory_id=factory_id,
                    created_by="system-seed",
                    created_by_name="系统初始化",
                    created_at=timestamp,
                )
            )
            db.add(
                InjectionSchedulingAuditEvent(
                    id=f"isaudit-{uuid4().hex}",
                    factory_id=factory_id,
                    event_type="import_profile_seeded",
                    entity_type="import_profile",
                    entity_id=profile.profile_id,
                    entity_revision=profile.revision,
                    request_id="system-seed",
                    detail_json=json.dumps(
                        {
                            "definition_sha256": digest,
                            "profile_family": profile.profile_family,
                            "profile_code": profile.profile_code,
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    ),
                    actor_user_id="system-seed",
                    actor_name="系统初始化",
                    created_at=timestamp,
                )
            )
            changed = True
    if changed:
        db.commit()
