"""Versioned assistant evidence identity; never depends on Python hash order."""
from dataclasses import fields, is_dataclass
from hashlib import sha256
import json


def canonical(value):
    if is_dataclass(value):
        return {field.name: canonical(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, dict):
        return {key: canonical(item) for key, item in value.items()}
    if isinstance(value, (set, frozenset)):
        return sorted((canonical(item) for item in value), key=lambda item: json.dumps(item, sort_keys=True))
    if isinstance(value, (tuple, list)):
        return [canonical(item) for item in value]
    return value


def digest(user, employment_epoch, authz_mode):
    identity = user.identity or {}
    snapshot = {key: getattr(user, key) for key in (
        "id", "authorization_version", "grants", "overrides", "effective_access",
        "roles", "role_codes", "permissions", "factory_scopes", "department_scopes",
        "active_permission_codes", "permission_catalog_loaded", "account_available",
    )}
    snapshot.update(employment_epoch=employment_epoch, authz_mode=authz_mode,
                    identity_mode=identity.get("identity_mode"),
                    effective_context_key=identity.get("effective_context_key"))
    encoded = json.dumps(canonical(snapshot), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "auth3:" + sha256(encoded.encode()).hexdigest()


def fingerprint(db, user):
    from app.core.config import settings
    from app.models.auth import EmployeeProfile
    profile = db.get(EmployeeProfile, user.id)
    return digest(user, profile.employment_epoch if profile else 1, settings.authz_mode)


def matches(db, user, stored):
    if not isinstance(stored, str):
        return False
    if stored.startswith("auth3:"):
        return stored == fingerprint(db, user)
    # Legacy evidence has no canonical snapshot to prove an equivalent grant
    # set after a process restart. Retain its exact check; never reinterpret a
    # mismatching old digest as authorized or overwrite historical evidence.
    from app.services.work_center.service import context
    return stored == context(db, user)[1]
