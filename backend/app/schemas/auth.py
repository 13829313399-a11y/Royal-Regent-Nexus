from typing import Literal

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    display_name: str
    password: str
    confirm_password: str
    phone: str = ""
    email: str = ""
    factory_id: str = ""
    org_unit_id: str = ""
    department: str
    position: str


class RegisterResponse(BaseModel):
    status: str
    message: str


class PasswordResetRequest(BaseModel):
    username: str = Field(max_length=64)
    display_name: str = Field(max_length=128)
    contact: str = Field(max_length=128)
    note: str = Field(default="", max_length=500)


class PasswordResetResponse(BaseModel):
    status: str
    message: str
    request_id: str | None = None


class PasswordResetClaimResponse(BaseModel):
    status: Literal[
        "none",
        "pending",
        "approved",
        "completed",
        "rejected",
        "expired",
        "legacy_invalid",
    ]
    request_id: str = ""
    can_complete: bool = False
    expires_at: str = ""
    message: str


class PasswordResetClaimCompleteRequest(BaseModel):
    new_password: str = Field(min_length=1, max_length=256)
    confirm_password: str = Field(min_length=1, max_length=256)


class PasswordResetClaimCompleteResponse(BaseModel):
    status: Literal["completed"]
    message: str


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)
    confirm_password: str = Field(min_length=1, max_length=256)


class AuthGrant(BaseModel):
    factory_ceiling: list[str] | None = None
    assignment_id: str = ""
    role_id: str
    role_name: str
    factory_id: str
    department: str
    permissions: list[str]
    data_scope: str = "department"
    scope_mode: Literal[
        "own_factory",
        "cross_factory_read",
        "cross_factory_operate",
    ] = "own_factory"
    read_permission_codes: list[str] = Field(default_factory=list)
    unrestricted_department: bool = False


class AuthProfile(BaseModel):
    primary_factory_id: str = ""
    primary_department: str = ""
    position: str = ""
    phone: str = ""
    email: str = ""
    confirmation_status: str = "needs_review"


class AuthEffectiveAccess(BaseModel):
    permission_code: str
    factory_id: str
    department: str
    effect: str
    allowed: bool
    source_type: str
    source_ids: list[str] = Field(default_factory=list)
    source_name: str = ""


class AuthMeResponse(BaseModel):
    id: str
    username: str
    display_name: str
    roles: list[str]
    permissions: list[str]
    factory_scopes: list[str]
    department_scopes: list[str]
    grants: list[AuthGrant] = Field(default_factory=list)
    force_password_change: bool = False
    avatar_url: str = ""
    profile: AuthProfile | None = None
    authorization_version: int = 0
    identity: dict | None = None
    effective_access: list[AuthEffectiveAccess] = Field(default_factory=list)
    authz_mode: Literal["legacy", "shadow", "enforce"] = "legacy"
