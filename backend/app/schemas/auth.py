from typing import Literal

from pydantic import BaseModel, Field, field_validator
import re


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=6, max_length=256)
    confirm_password: str = Field(min_length=6, max_length=256)
    phone: str = Field(default="", max_length=64)
    email: str = Field(default="", max_length=128)
    factory_id: str = Field(default="", max_length=64)
    org_unit_id: str = Field(default="", max_length=64)
    department: str = Field(min_length=1, max_length=64)
    position: str = Field(min_length=1, max_length=128)

    @field_validator("username", "display_name", "phone", "email", "factory_id", "org_unit_id", "department", "position", mode="before")
    @classmethod
    def trim_public_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("email")
    @classmethod
    def validate_email(cls, value):
        if value and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("请输入有效邮箱")
        return value


class RegisterResponse(BaseModel):
    status: str
    message: str
    request_id: str | None = None
    submitted_at: str | None = None


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
    can_request_reopen: bool = False
    expires_in_seconds: int = 0
    expires_at: str = ""
    message: str


class PasswordResetClaimCompleteRequest(BaseModel):
    new_password: str = Field(min_length=1, max_length=256)
    confirm_password: str = Field(min_length=1, max_length=256)


class PasswordResetClaimCompleteResponse(BaseModel):
    status: Literal["completed"]
    message: str


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1)
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
    internal_member: bool = False
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
