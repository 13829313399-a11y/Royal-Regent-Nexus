"""Contact reuse checks run inside the shared IAM mutation transaction."""
import re
import unicodedata

from sqlalchemy import exists, or_, select

from app.models.auth import AuthRegistrationRequest, AuthUser, EmployeeProfile
from app.services.auth_problem import auth_problem


def contact_key(value: str | None, field: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").strip().casefold()
    if field == "email":
        return value
    value = re.sub(r"[\s()\-]", "", value)
    if value.startswith("00"):
        value = "+" + value[2:]
    if re.fullmatch(r"\+861\d{10}", value):
        value = value[3:]
    return value


def ensure_registration_contacts_available(db, phone, email, *, exclude_user_id=None):
    # A pending reapplication may have an older profile. Its pending request is
    # authoritative until approval; active/frozen accounts use current profiles.
    pending = exists(select(AuthRegistrationRequest.id).where(
        AuthRegistrationRequest.user_id == AuthUser.id,
        AuthRegistrationRequest.status == "pending"))
    profiles = select(EmployeeProfile.phone, EmployeeProfile.email).join(
        AuthUser, AuthUser.id == EmployeeProfile.user_id).where(
        AuthUser.status.in_(("active", "suspended", "pending")),
        or_(AuthUser.status != "pending", ~pending))
    requests = select(AuthRegistrationRequest.phone, AuthRegistrationRequest.email).join(
        AuthUser, AuthUser.id == AuthRegistrationRequest.user_id).where(
        AuthUser.status == "pending", AuthRegistrationRequest.status == "pending")
    if exclude_user_id:
        profiles = profiles.where(AuthUser.id != exclude_user_id)
        requests = requests.where(AuthUser.id != exclude_user_id)
    keys = {"phone": contact_key(phone, "phone"), "email": contact_key(email, "email")}
    for stored_phone, stored_email in db.execute(profiles.union_all(requests)):
        for field, stored in (("phone", stored_phone), ("email", stored_email)):
            if keys[field] and keys[field] == contact_key(stored, field):
                label = "手机号" if field == "phone" else "邮箱"
                auth_problem(409, "AUTH_REGISTRATION_CONTACT_CONFLICT",
                    f"{label}已用于其他账号或待审核申请，请使用原账号登录、找回密码或联系管理员核对", field=field)
