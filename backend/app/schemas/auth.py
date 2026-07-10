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
