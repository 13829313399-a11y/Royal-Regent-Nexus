from __future__ import annotations

from datetime import timedelta
from hashlib import sha256
from math import ceil
from urllib.parse import quote

from fastapi import HTTPException
from sqlalchemy import case, func, or_, select, update
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
        func.nullif(func.trim(EmployeeProfile.position), ""),
        FALLBACK_POSITION,
    )
    factory = func.coalesce(
        func.nullif(func.trim(EmployeeProfile.primary_factory_id), ""),
        FALLBACK_FACTORY,
    )
    department = func.coalesce(
        func.nullif(func.trim(EmployeeProfile.primary_department), ""),
        FALLBACK_DEPARTMENT,
    )
    return presence_state, presence_rank, display_name, position, factory, department


def _base_conditions(
    *,
    q: str = "",
    factory_id: str = "",
    department: str = "",
    expressions,
):
    _, _, display_name, position, factory, profile_department = expressions
    conditions = [AuthUser.status == "active"]
    normalized_query = q.strip()
    if normalized_query:
        pattern = f"%{normalized_query}%"
        search_conditions = [
            display_name.ilike(pattern),
            position.ilike(pattern),
            factory.ilike(pattern),
            profile_department.ilike(pattern),
        ]
        matching_factories = _matching_alias_codes(
            normalized_query, FACTORY_SEARCH_ALIASES
        )
        matching_departments = _matching_alias_codes(
            normalized_query, DEPARTMENT_SEARCH_ALIASES
        )
        if matching_factories:
            search_conditions.append(
                EmployeeProfile.primary_factory_id.in_(matching_factories)
            )
        if matching_departments:
            search_conditions.append(
                EmployeeProfile.primary_department.in_(matching_departments)
            )
        conditions.append(
            or_(*search_conditions)
        )
    if factory_id.strip():
        conditions.append(EmployeeProfile.primary_factory_id == factory_id.strip())
    if department.strip():
        conditions.append(EmployeeProfile.primary_department == department.strip())
    return conditions


def _member_select(expressions):
    presence_state, presence_rank, display_name, position, factory, department = (
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
        )
        .select_from(AuthUser)
        .outerjoin(EmployeeProfile, EmployeeProfile.user_id == AuthUser.id)
        .outerjoin(AuthUserPresence, AuthUserPresence.user_id == AuthUser.id)
        .order_by(presence_rank.asc(), display_name.asc(), AuthUser.id.asc())
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
    conditions = _base_conditions(expressions=expressions)
    counts = _state_counts(db, conditions, expressions)
    rows = db.execute(
        _member_select(expressions).where(*conditions).limit(SUMMARY_PREVIEW_LIMIT)
    ).all()
    return DirectorySummaryResponse(
        total_members=counts.online + counts.away + counts.offline,
        state_counts=counts,
        preview_members=[_member_from_row(row) for row in rows],
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
) -> DirectoryMembersResponse:
    expressions = _directory_expressions()
    conditions = _base_conditions(
        q=q,
        factory_id=factory_id,
        department=department,
        expressions=expressions,
    )
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
        items=[_member_from_row(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=ceil(total / page_size) if total else 0,
        state_counts=counts,
    )


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
        )
    ).one_or_none()
    if row is None or not row.avatar_png:
        raise HTTPException(status_code=404, detail="头像不可用")

    content = bytes(row.avatar_png)
    version = str(row.avatar_version or "") or sha256(content).hexdigest()[:24]
    return content, f'"{version}"'
