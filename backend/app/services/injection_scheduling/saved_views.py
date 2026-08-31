from __future__ import annotations

import json
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.time import business_now
from app.models.injection_schedule import InjectionScheduleSavedView
from app.services.auth import AuthContext
from app.services.injection_scheduling.audit import write_audit_event


def _out(item: InjectionScheduleSavedView) -> dict[str, object]:
    return {
        "id": item.id,
        "factory_id": item.factory_id,
        "user_id": item.user_id,
        "name": item.name,
        "scope": item.scope,
        "config": json.loads(item.config_json),
        "is_default": item.is_default,
        "version": item.version,
    }


def _validate(name: str, scope: str, config: dict[str, object]) -> None:
    if not name.strip() or len(name.strip()) > 128:
        raise HTTPException(status_code=422, detail="视图名称必须为 1 到 128 个字符")
    if scope not in {"PERSONAL", "FACTORY_SHARED"}:
        raise HTTPException(status_code=422, detail="视图范围不受支持")
    columns = config.get("columns", [])
    if not isinstance(columns, list) or len(columns) > 60:
        raise HTTPException(status_code=422, detail="视图最多保存 60 个字段")


def list_saved_views(
    db: Session, factory_id: str, actor: AuthContext
) -> list[dict[str, object]]:
    items = db.scalars(
        select(InjectionScheduleSavedView)
        .where(
            InjectionScheduleSavedView.factory_id == factory_id,
            InjectionScheduleSavedView.status == "ACTIVE",
            or_(
                InjectionScheduleSavedView.user_id == actor.id,
                InjectionScheduleSavedView.scope == "FACTORY_SHARED",
            ),
        )
        .order_by(
            InjectionScheduleSavedView.is_default.desc(),
            InjectionScheduleSavedView.name,
        )
    ).all()
    return [_out(item) for item in items]


def create_saved_view(
    db: Session,
    *,
    factory_id: str,
    name: str,
    scope: str,
    config: dict[str, object],
    is_default: bool,
    actor: AuthContext,
) -> dict[str, object]:
    _validate(name, scope, config)
    if is_default:
        for existing in db.scalars(
            select(InjectionScheduleSavedView).where(
                InjectionScheduleSavedView.factory_id == factory_id,
                InjectionScheduleSavedView.user_id == actor.id,
                InjectionScheduleSavedView.is_default.is_(True),
            )
        ).all():
            existing.is_default = False
            existing.version += 1
    now = business_now().isoformat(timespec="seconds")
    item = InjectionScheduleSavedView(
        id=f"is-view-{uuid4().hex}",
        factory_id=factory_id,
        user_id=actor.id,
        name=name.strip(),
        scope=scope,
        config_json=json.dumps(config, ensure_ascii=False, separators=(",", ":")),
        is_default=is_default,
        status="ACTIVE",
        created_by=actor.id,
        created_by_name=actor.display_name,
        created_at=now,
        updated_at=now,
    )
    db.add(item)
    write_audit_event(
        db,
        factory_id=factory_id,
        event_type="SAVED_VIEW_CREATED",
        entity_type="SAVED_VIEW",
        entity_id=item.id,
        entity_version=1,
        actor=actor,
        after={"name": item.name, "scope": scope},
    )
    db.commit()
    return _out(item)


def patch_saved_view(
    db: Session,
    *,
    factory_id: str,
    view_id: str,
    version: int,
    name: str,
    config: dict[str, object],
    is_default: bool,
    actor: AuthContext,
) -> dict[str, object]:
    item = db.scalar(
        select(InjectionScheduleSavedView).where(
            InjectionScheduleSavedView.id == view_id,
            InjectionScheduleSavedView.factory_id == factory_id,
            InjectionScheduleSavedView.status == "ACTIVE",
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="保存视图不存在")
    if item.user_id != actor.id:
        raise HTTPException(status_code=403, detail="只能修改自己创建的视图")
    if item.version != version:
        raise HTTPException(
            status_code=409, detail={"message": "保存视图已更新", "latest": _out(item)}
        )
    _validate(name, item.scope, config)
    before = {
        "name": item.name,
        "config": json.loads(item.config_json),
        "version": item.version,
    }
    if is_default:
        for existing in db.scalars(
            select(InjectionScheduleSavedView).where(
                InjectionScheduleSavedView.factory_id == factory_id,
                InjectionScheduleSavedView.user_id == actor.id,
                InjectionScheduleSavedView.is_default.is_(True),
                InjectionScheduleSavedView.id != item.id,
            )
        ).all():
            existing.is_default = False
            existing.version += 1
    item.name = name.strip()
    item.config_json = json.dumps(config, ensure_ascii=False, separators=(",", ":"))
    item.is_default = is_default
    item.version += 1
    item.updated_at = business_now().isoformat(timespec="seconds")
    write_audit_event(
        db,
        factory_id=factory_id,
        event_type="SAVED_VIEW_UPDATED",
        entity_type="SAVED_VIEW",
        entity_id=item.id,
        entity_version=item.version,
        actor=actor,
        before=before,
        after={"name": item.name, "config": config, "version": item.version},
    )
    db.commit()
    return _out(item)


def archive_saved_view(
    db: Session, *, factory_id: str, view_id: str, version: int, actor: AuthContext
) -> dict[str, object]:
    item = db.scalar(
        select(InjectionScheduleSavedView).where(
            InjectionScheduleSavedView.id == view_id,
            InjectionScheduleSavedView.factory_id == factory_id,
            InjectionScheduleSavedView.status == "ACTIVE",
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="保存视图不存在")
    if item.user_id != actor.id:
        raise HTTPException(status_code=403, detail="只能删除自己创建的视图")
    if item.version != version:
        raise HTTPException(
            status_code=409, detail={"message": "保存视图已更新", "latest": _out(item)}
        )
    item.status = "ARCHIVED"
    item.version += 1
    item.updated_at = business_now().isoformat(timespec="seconds")
    write_audit_event(
        db,
        factory_id=factory_id,
        event_type="SAVED_VIEW_ARCHIVED",
        entity_type="SAVED_VIEW",
        entity_id=item.id,
        entity_version=item.version,
        actor=actor,
        before={"status": "ACTIVE"},
        after={"status": "ARCHIVED"},
    )
    db.commit()
    return {"archived": True, "id": item.id}
