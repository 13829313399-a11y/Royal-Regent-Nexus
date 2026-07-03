from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthMeResponse(BaseModel):
    id: str
    username: str
    display_name: str
    roles: list[str]
    permissions: list[str]
    factory_scopes: list[str]
    department_scopes: list[str]
    force_password_change: bool = False
