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
    factory_id: str
    department: str
    position: str


class RegisterResponse(BaseModel):
    status: str
    message: str


class PasswordResetRequest(BaseModel):
    username: str
    display_name: str = ""
    contact: str
    note: str = ""


class PasswordResetResponse(BaseModel):
    status: str
    message: str


class AuthGrant(BaseModel):
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
    effective_access: list[AuthEffectiveAccess] = Field(default_factory=list)
    authz_mode: Literal["legacy", "shadow", "enforce"] = "legacy"
