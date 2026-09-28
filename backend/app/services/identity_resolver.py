"""The server clock resolves identity. No worker updates authorization state."""
from __future__ import annotations
from datetime import datetime, timezone
from hashlib import sha256
from sqlalchemy import case, select
from sqlalchemy.orm import Session
from app.models.auth import EmployeeProfile
from app.models.identity import EmployeeAssignment, IamOrgUnit, IamOrgDepartment


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def instant(value: str | datetime | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    # Auth timestamps historically used process local wall-clock time.
    return parsed.astimezone(timezone.utc)


def stamp(value: datetime | None = None) -> str:
    return (value or utc_now()).astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def assignment_active(item: EmployeeAssignment, profile: EmployeeProfile, at: datetime) -> bool:
    return (item.lifecycle_state == "approved" and item.employment_epoch == profile.employment_epoch
            and profile.employment_status != "left"
            and instant(item.valid_from) <= at
            and (not item.valid_until or at < instant(item.valid_until)))


def assignment_dict(item: EmployeeAssignment, org: IamOrgUnit | None, at: datetime) -> dict:
    state = ("revoked" if item.lifecycle_state == "revoked" else "scheduled" if instant(item.valid_from) > at
             else "ended" if item.valid_until and at >= instant(item.valid_until) else "current")
    return {"id": item.id, "org_unit_id": item.org_unit_id, "org_name": org.name if org else item.org_unit_id,
            "factory_id": org.legacy_factory_id if org else "", "department_code": item.department_code,
            "official_position_title": item.official_position_title, "assignment_type": item.assignment_type,
            "is_primary": item.is_primary, "valid_from": item.valid_from, "valid_until": item.valid_until,
            "state": state, "revision": item.revision, "employment_epoch": item.employment_epoch,
            "source_request_id": item.source_request_id, "ended_reason": item.ended_reason}


def resolve_identity_at(db: Session, user_id: str, at: datetime | None = None) -> dict:
    at = instant(at) if at else utc_now()
    profile = db.get(EmployeeProfile, user_id)
    rows = db.execute(select(EmployeeAssignment, IamOrgUnit).select_from(EmployeeAssignment).join(IamOrgUnit)
                      .where(EmployeeAssignment.user_id == user_id).order_by(EmployeeAssignment.valid_from, EmployeeAssignment.id)).all()
    departments = {(d.org_unit_id, d.department_code) for d in db.scalars(select(IamOrgDepartment).where(IamOrgDepartment.status == "active"))}
    active = [assignment_dict(a, org, at) for a, org in rows
              if profile and assignment_active(a, profile, at) and org.status == "active" and (a.org_unit_id, a.department_code) in departments]
    primary = next((a for a in active if a["is_primary"]), None)
    v2 = profile is not None and profile.identity_mode == "v2"
    boundaries = sorted({instant(t) for a, _ in rows if profile and a.employment_epoch == profile.employment_epoch
                         and a.lifecycle_state == "approved" for t in (a.valid_from, a.valid_until) if t and instant(t) > at})
    version = profile.identity_version if profile else 0
    return {"identity_mode": "v2" if v2 else "legacy", "identity_version": version,
            "confirmation_status": profile.confirmation_status if profile else "unconfirmed",
            "employment_epoch": profile.employment_epoch if profile else 1,
            "employment_status": profile.employment_status if profile else "unconfirmed",
            "primary_assignment": primary, "active_assignments_summary": active,
            "assignments": [assignment_dict(a, org, at) for a, org in rows],
            "primary_factory_id": (primary["factory_id"] if primary else "") if v2 else (profile.primary_factory_id if profile else ""),
            "primary_department": (primary["department_code"] if primary else "") if v2 else (profile.primary_department if profile else ""),
            "position": (primary["official_position_title"] if primary else "") if v2 else (profile.position if profile else ""),
            "server_now": stamp(at), "next_transition_at": stamp(boundaries[0]) if boundaries else None,
            "effective_context_key": sha256(f"{user_id}:{version}:{','.join(sorted(a['id'] for a in active))}".encode()).hexdigest()[:24]}


def identity_columns(at: datetime | None = None, *, include_org=False):
    """Correlated expressions for directory/list filters; no per-person auth N+1."""
    now = stamp(at)
    def column(field):
        return (select(field).select_from(EmployeeAssignment).join(IamOrgUnit)
                .join(IamOrgDepartment, (IamOrgDepartment.org_unit_id == EmployeeAssignment.org_unit_id) &
                      (IamOrgDepartment.department_code == EmployeeAssignment.department_code))
                .where(EmployeeAssignment.user_id == EmployeeProfile.user_id,
                       EmployeeAssignment.employment_epoch == EmployeeProfile.employment_epoch,
                       EmployeeAssignment.is_primary.is_(True), EmployeeAssignment.lifecycle_state == "approved",
                       EmployeeAssignment.valid_from <= now,
                       (EmployeeAssignment.valid_until.is_(None) | (EmployeeAssignment.valid_until > now)),
                       IamOrgUnit.status == "active", IamOrgDepartment.status == "active", EmployeeProfile.employment_status != "left")
                .correlate(EmployeeProfile).scalar_subquery())
    fields = [(IamOrgUnit.legacy_factory_id, EmployeeProfile.primary_factory_id),
              (EmployeeAssignment.department_code, EmployeeProfile.primary_department),
              (EmployeeAssignment.official_position_title, EmployeeProfile.position)]
    if include_org:
        fields.append((EmployeeAssignment.org_unit_id, EmployeeProfile.primary_factory_id))
    return tuple(case((EmployeeProfile.identity_mode == "v2", column(field)), else_=legacy) for field, legacy in fields)
