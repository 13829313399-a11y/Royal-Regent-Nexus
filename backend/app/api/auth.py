from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.auth import AuthMeResponse, LoginRequest, RegisterRequest, RegisterResponse
from app.services.auth import (
    SESSION_COOKIE_NAME,
    AuthContext,
    authenticate_user,
    build_auth_context,
    create_session,
    get_current_user,
    register_user,
    revoke_session,
    to_auth_response,
)

router = APIRouter(prefix="/api/auth")


@router.post("/login", response_model=AuthMeResponse)
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    user = authenticate_user(db, payload.username, payload.password, request=request)
    token = create_session(db, user, request=request)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=12 * 60 * 60,
        path="/",
    )
    return to_auth_response(build_auth_context(db, user))


@router.post("/register", response_model=RegisterResponse)
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    return register_user(db, payload, request=request)


@router.get("/me", response_model=AuthMeResponse)
def me(current_user: AuthContext = Depends(get_current_user)):
    return to_auth_response(current_user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    revoke_session(db, request.cookies.get(SESSION_COOKIE_NAME), request=request)
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return None
