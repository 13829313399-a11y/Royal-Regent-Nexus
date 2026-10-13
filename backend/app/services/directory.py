from __future__ import annotations

from datetime import timedelta
from hashlib import sha256
from math import ceil
from urllib.parse import quote

from fastapi import HTTPException
from sqlalchemy import String, case, cast, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time import business_now
from app.models.auth import AuthUser, AuthUserPresence, EmployeeProfile
from app.schemas.directory import (
    DirectoryHeartbeatResponse,
    DirectoryMemberOut,
    DirectoryMembersResponse,
    DirectoryStateCounts,
    DirectorySummaryResponse,
)
from app.services.auth import AuthContext
from app.core.config import settings
from app.models.identity import IamOrgUnit, IamOrgDepartment
from app.models.collaboration import MemberProfile, MemberContact
from app.services.internal_members import eligible_member_ids
from app.services.identity_resolver import stamp

ONLINE_WINDOW_SECONDS = 120
AWAY_WINDOW_SECONDS = 15 * 60
HEARTBEAT_WRITE_COALESCE_SECONDS = 45
SUMMARY_PREVIEW_LIMIT = 6

FALLBACK_NAME = "未命名成员"
FALLBACK_POSITION = "职位待完善"
FALLBACK_FACTORY = "未确认厂区"
FALLBACK_DEPARTMENT = "未确认部门"

FACTORY_SEARCH_ALIASES = {
    "huakang-a": ("华康A", "华康A厂"),
    "huakang-b": ("华康B", "华康B厂"),
    "huakang-c": ("华康C", "华康C厂"),
    "huakang-d": ("华康D", "华康D厂"),
    "huadeng": ("华登", "华登厂"),
    "huaxing": ("华兴", "华兴厂"),
}

DEPARTMENT_SEARCH_ALIASES = {
    "assembly": ("装配部", "装配"),
    "carton": ("纸箱部", "纸箱"),
    "electronic": ("电子部", "电子"),
    "engineering": ("工程部", "工程"),
    "hair": ("植发部", "植发"),
    "management": ("总务", "综合管理"),
    "molding": ("啤机部", "啤机"),
    "painting": ("喷油部", "喷油"),
    "pmc-warehouse": ("PMC仓库", "PMC/仓库", "仓库"),
    "production": ("生产部", "啤喷装", "生产部啤喷装"),
    "qa": ("QA部", "品质部"),
    "qc": ("QC部", "品检部"),
    "sales-business": ("业务部", "营业部", "业务"),
    "sewing": ("车缝部", "车缝"),
    "slush": ("搪胶部", "搪胶"),
    "system": ("系统管理",),
    "three-d-printing": ("3D打印部", "3D打印"),
    "warehouse": ("仓管部", "仓管"),
}


def _normalized_search_label(value: str) -> str:
    return "".join(value.casefold().split()).replace("/", "")


def _matching_alias_codes(query: str, aliases: dict[str, tuple[str, ...]]) -> list[str]:
    normalized_query = _normalized_search_label(query)
    return [
        code
        for code, labels in aliases.items()
        if any(normalized_query in _normalized_search_label(label) for label in labels)
    ]


def _timestamp(value) -> str:
    return value.isoformat(timespec="seconds")


def _directory_expressions(now=None):
    checked_at = now or business_now()
    from app.services.identity_resolver import identity_columns
    identity_factory, identity_department, identity_position, identity_org = identity_columns(checked_at, include_org=True)
    online_cutoff = _timestamp(checked_at - timedelta(seconds=ONLINE_WINDOW_SECONDS))
    away_cutoff = _timestamp(checked_at - timedelta(seconds=AWAY_WINDOW_SECONDS))

    presence_state = case(
        (AuthUserPresence.last_seen_at >= online_cutoff, "online"),
        (AuthUserPresence.last_seen_at >= away_cutoff, "away"),
        else_="offline",
    )
    presence_rank = case(
        (AuthUserPresence.last_seen_at >= online_cutoff, 0),
        (AuthUserPresence.last_seen_at >= away_cutoff, 1),
        else_=2,
    )
    display_name = func.coalesce(
        func.nullif(func.trim(AuthUser.display_name), ""),
        FALLBACK_NAME,
    )
    position = func.coalesce(
        func.nullif(func.trim(identity_position), ""),
        FALLBACK_POSITION,
    )
    factory = func.coalesce(
        func.nullif(func.trim(identity_factory), ""),
        FALLBACK_FACTORY,
    )
    department = func.coalesce(
        func.nullif(func.trim(identity_department), ""),
        FALLBACK_DEPARTMENT,
    )
    return presence_state, presence_rank, display_name, position, factory, department, func.coalesce(identity_org, "")


def _base_conditions(
    *,
    q: str = "",
    factory_id: str = "",
    department: str = "",
    org_unit_id: str = "",
    eligible_ids=(),
    expressions,
):
    _, _, display_name, position, factory, profile_department, org = expressions
    conditions = [AuthUser.status == "active", AuthUser.id.in_(eligible_ids)]
    normalized_query = q.strip()
    if normalized_query:
        pattern = f"%{normalized_query}%"
        search_conditions = [
            display_name.ilike(pattern),
            position.ilike(pattern),
            factory.ilike(pattern),
            profile_department.ilike(pattern),
            org.in_(select(IamOrgUnit.id).where(IamOrgUnit.name.ilike(pattern))),
        ]
        if settings.collaboration_enabled:
            search_conditions.append(AuthUser.id.in_(select(MemberProfile.user_id).join(EmployeeProfile,
                (EmployeeProfile.user_id == MemberProfile.user_id) & (EmployeeProfile.employment_epoch == MemberProfile.epoch))
                .where(or_(MemberProfile.help_topics.ilike(pattern), MemberProfile.bio.ilike(pattern),
                           cast(MemberProfile.skill_tags, String).ilike(pattern)))))
        matching_factories = _matching_alias_codes(
            normalized_query, FACTORY_SEARCH_ALIASES
        )
        matching_departments = _matching_alias_codes(
            normalized_query, DEPARTMENT_SEARCH_ALIASES
        )
        if matching_factories:
            search_conditions.append(
                factory.in_(matching_factories)
            )
        if matching_departments:
            search_conditions.append(
                profile_department.in_(matching_departments)
            )
        conditions.append(
            or_(*search_conditions)
        )
    if factory_id.strip() and factory_id != "group":
        conditions.append(factory == factory_id.strip())
    if org_unit_id.strip() and org_unit_id != "group":
        conditions.append(org == org_unit_id.strip())
    if department.strip():
        conditions.append(profile_department == department.strip())
    return conditions


def _member_select(expressions):
    presence_state, presence_rank, display_name, position, factory, department, org = (
        expressions
    )
    return (
        select(
            AuthUser.id.label("id"),
            display_name.label("display_name"),
            position.label("position"),
            factory.label("primary_factory_id"),
            department.label("primary_department"),
            AuthUser.avatar_version.label("avatar_version"),
            AuthUser.avatar_png.is_not(None).label("has_avatar"),
            presence_state.label("presence_state"),
            org.label("org_unit_id"),
            select(IamOrgUnit.name).where(IamOrgUnit.id == org).scalar_subquery().label("org_name"),
            select(IamOrgUnit.kind).where(IamOrgUnit.id == org).scalar_subquery().label("org_kind"),
            func.coalesce(EmployeeProfile.employment_epoch, 1).label("epoch"),
        )
        .select_from(AuthUser)
        .outerjoin(EmployeeProfile, EmployeeProfile.user_id == AuthUser.id)
        .outerjoin(AuthUserPresence, AuthUserPresence.user_id == AuthUser.id)
        .order_by(org.asc(), display_name.asc(), AuthUser.id.asc())
    )


def _member_from_row(row) -> DirectoryMemberOut:
    avatar_version = str(row.avatar_version or "")
    avatar_url = ""
    if bool(row.has_avatar):
        cache_version = avatar_version or "legacy"
        avatar_url = (
            f"/api/directory/members/{quote(str(row.id), safe='')}/avatar"
            f"?v={quote(cache_version, safe='')}"
        )
    return DirectoryMemberOut(
        id=str(row.id),
        display_name=str(row.display_name or FALLBACK_NAME),
        position=str(row.position or FALLBACK_POSITION),
        primary_factory_id=str(row.primary_factory_id or FALLBACK_FACTORY),
        primary_department=str(row.primary_department or FALLBACK_DEPARTMENT),
        avatar_url=avatar_url,
        avatar_version=avatar_version,
        presence_state=str(row.presence_state),
        org_unit_id=str(row.org_unit_id or ""),
        org_name=str(row.org_name or "未登记组织"),
        org_kind=str(row.org_kind or "unknown"),
    )


def _state_counts(db: Session, conditions, expressions) -> DirectoryStateCounts:
    presence_state = expressions[0]
    row = db.execute(
        select(
            func.sum(case((presence_state == "online", 1), else_=0)).label("online"),
            func.sum(case((presence_state == "away", 1), else_=0)).label("away"),
            func.sum(case((presence_state == "offline", 1), else_=0)).label("offline"),
        )
        .select_from(AuthUser)
        .outerjoin(EmployeeProfile, EmployeeProfile.user_id == AuthUser.id)
        .outerjoin(AuthUserPresence, AuthUserPresence.user_id == AuthUser.id)
        .where(*conditions)
    ).one()
    return DirectoryStateCounts(
        online=int(row.online or 0),
        away=int(row.away or 0),
        offline=int(row.offline or 0),
    )


def get_directory_summary(db: Session) -> DirectorySummaryResponse:
    expressions = _directory_expressions()
    conditions = _base_conditions(expressions=expressions, eligible_ids=eligible_member_ids(db))
    counts = _state_counts(db, conditions, expressions)
    rows = db.execute(
        _member_select(expressions).where(*conditions, expressions[0] == "online").limit(SUMMARY_PREVIEW_LIMIT)
    ).all()
    return DirectorySummaryResponse(
        total_members=counts.online + counts.away + counts.offline,
        state_counts=counts,
        preview_members=[_member_from_row(row) for row in rows],
        server_now=stamp(), snapshot_at=stamp(),
    )


def list_directory_members(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 36,
    q: str = "",
    presence: str = "all",
    factory_id: str = "",
    department: str = "",
    org_unit_id: str = "",
    contacts_only: bool = False,
    viewer: AuthContext | None = None,
) -> DirectoryMembersResponse:
    expressions = _directory_expressions()
    conditions = _base_conditions(
        q=q,
        factory_id=factory_id,
        department=department,
        org_unit_id=org_unit_id,
        eligible_ids=eligible_member_ids(db),
        expressions=expressions,
    )
    if contacts_only:
        if not settings.collaboration_enabled or viewer is None:
            conditions.append(AuthUser.id == "")
        else:
            epoch = int((viewer.identity or {}).get("employment_epoch", 1))
            conditions.append(AuthUser.id.in_(select(MemberContact.target_id).join(EmployeeProfile,
                (EmployeeProfile.user_id == MemberContact.target_id) & (EmployeeProfile.employment_epoch == MemberContact.target_epoch))
                .where(MemberContact.user_id == viewer.id, MemberContact.epoch == epoch)))
    counts = _state_counts(db, conditions, expressions)
    page_conditions = list(conditions)
    if presence != "all":
        page_conditions.append(expressions[0] == presence)

    total = int(
        db.scalar(
            select(func.count(AuthUser.id))
            .select_from(AuthUser)
            .outerjoin(EmployeeProfile, EmployeeProfile.user_id == AuthUser.id)
            .outerjoin(AuthUserPresence, AuthUserPresence.user_id == AuthUser.id)
            .where(*page_conditions)
        )
        or 0
    )
    rows = db.execute(
        _member_select(expressions)
        .where(*page_conditions)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return DirectoryMembersResponse(
        items=_enrich_members(db, rows, viewer),
        total=total,
        page=page,
        page_size=page_size,
        total_pages=ceil(total / page_size) if total else 0,
        state_counts=counts,
        server_now=stamp(), snapshot_at=stamp(),
    )


def _enrich_members(db, rows, viewer=None):
    profiles, contacts = {}, set()
    if settings.collaboration_enabled and rows:
        from app.services.collaboration.core import profile_out
        ids = [row.id for row in rows]
        profiles = {(p.user_id, p.epoch): profile_out(p) for p in db.scalars(select(MemberProfile).where(MemberProfile.user_id.in_(ids)))}
        if viewer:
            epoch = int((viewer.identity or {}).get("employment_epoch", 1))
            contacts = {(c.target_id, c.target_epoch) for c in db.scalars(select(MemberContact).where(MemberContact.user_id == viewer.id, MemberContact.epoch == epoch, MemberContact.target_id.in_(ids)))}
    result = []
    for row in rows:
        item = _member_from_row(row)
        item.self_profile = profiles.get((row.id, row.epoch), {})
        item.is_contact = (row.id, row.epoch) in contacts
        can_contact = settings.collaboration_enabled and viewer is not None and row.id != viewer.id
        item.actions = {"can_message": can_contact, "can_appreciate": can_contact}
        result.append(item)
    return result


def directory_member(db, viewer, user_id):
    expressions = _directory_expressions()
    row = db.execute(_member_select(expressions).where(AuthUser.id == user_id,
        *_base_conditions(expressions=expressions, eligible_ids=eligible_member_ids(db)))).one_or_none()
    if row is None:
        raise HTTPException(404, "成员不存在或不可查看")
    item = _enrich_members(db, [row], viewer)[0].model_dump()
    from app.services.identity_resolver import resolve_identity_at
    resolved = resolve_identity_at(db, user_id)
    item["additional_assignments"] = [{"org_name": a["org_name"], "department": a["department_code"],
        "position": a["official_position_title"]} for a in resolved["active_assignments_summary"] if not a["is_primary"]]
    return item


def directory_catalog(db):
    expressions = _directory_expressions()
    conditions = _base_conditions(expressions=expressions, eligible_ids=eligible_member_ids(db))
    rows = db.execute(select(expressions[6].label("org"), func.count(AuthUser.id).label("total"),
        func.sum(case((expressions[0] == "online", 1), else_=0)).label("online"))
        .select_from(AuthUser).outerjoin(EmployeeProfile, EmployeeProfile.user_id == AuthUser.id)
        .outerjoin(AuthUserPresence, AuthUserPresence.user_id == AuthUser.id).where(*conditions).group_by(expressions[6])).all()
    counts = {r.org: (r.total, int(r.online or 0)) for r in rows}
    from app.services.identity_catalog import DEPARTMENTS
    departments = list(db.scalars(select(IamOrgDepartment).where(IamOrgDepartment.status == "active")))
    return {"organizations": [dict(id=o.id, name=o.name, kind=o.kind, factory_id=o.legacy_factory_id,
        parent_id=o.parent_id, total=counts.get(o.id, (0, 0))[0], online=counts.get(o.id, (0, 0))[1],
        departments=[dict(id=d.department_code, name=DEPARTMENTS.get(d.department_code, d.department_code)) for d in departments if d.org_unit_id == o.id])
        for o in db.scalars(select(IamOrgUnit).where(IamOrgUnit.status == "active", IamOrgUnit.kind != "group").order_by(IamOrgUnit.id))], "server_now": stamp()}


def record_presence_heartbeat(
    db: Session,
    current_user: AuthContext,
) -> DirectoryHeartbeatResponse:
    now = business_now()
    timestamp = _timestamp(now)
    write_cutoff = _timestamp(now - timedelta(seconds=HEARTBEAT_WRITE_COALESCE_SECONDS))

    result = db.execute(
        update(AuthUserPresence)
        .where(
            AuthUserPresence.user_id == current_user.id,
            or_(
                AuthUserPresence.last_seen_at == "",
                AuthUserPresence.last_seen_at < write_cutoff,
            ),
        )
        .values(last_seen_at=timestamp, updated_at=timestamp)
    )
    if result.rowcount:
        db.commit()
        return DirectoryHeartbeatResponse(written=True)

    if db.get(AuthUserPresence, current_user.id) is not None:
        db.rollback()
        return DirectoryHeartbeatResponse(written=False)

    created = AuthUserPresence(
        user_id=current_user.id,
        last_seen_at=timestamp,
        created_at=timestamp,
        updated_at=timestamp,
    )
    try:
        with db.begin_nested():
            db.add(created)
            db.flush()
    except IntegrityError:
        db.rollback()
        return DirectoryHeartbeatResponse(written=False)

    db.commit()
    return DirectoryHeartbeatResponse(written=True)


def read_directory_avatar(db: Session, user_id: str) -> tuple[bytes, str]:
    row = db.execute(
        select(AuthUser.avatar_png, AuthUser.avatar_version).where(
            AuthUser.id == user_id,
            AuthUser.status == "active",
            AuthUser.id.in_(eligible_member_ids(db)),
        )
    ).one_or_none()
    if row is None or not row.avatar_png:
        raise HTTPException(status_code=404, detail="头像不可用")

    content = bytes(row.avatar_png)
    version = str(row.avatar_version or "") or sha256(content).hexdigest()[:24]
    return content, f'"{version}"'
