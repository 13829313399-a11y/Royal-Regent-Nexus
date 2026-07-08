from pydantic import BaseModel


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


class AuthMeResponse(BaseModel):
    id: str
    username: str
    display_name: str
    roles: list[str]
    permissions: list[str]
    factory_scopes: list[str]
    department_scopes: list[str]
    force_password_change: bool = False
