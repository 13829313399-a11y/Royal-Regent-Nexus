from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db
from app.schemas.auth import (
    AuthMeResponse,
    LoginRequest,
    PasswordResetRequest,
    PasswordResetResponse,
    RegisterRequest,
    RegisterResponse,
)
from app.services.auth import (
    AVATAR_MAX_UPLOAD_BYTES,
    SESSION_COOKIE_NAME,
    AuthContext,
    authenticate_user,
    build_auth_context,
    create_session,
    get_current_user,
    read_auth_user_avatar,
    register_user,
    remove_auth_user_avatar,
    revoke_session,
    save_auth_user_avatar,
    submit_password_reset_request,
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
        secure=settings.effective_session_cookie_secure,
        samesite="lax",
        max_age=12 * 60 * 60,
        path="/",
    )
    return to_auth_response(build_auth_context(db, user))


@router.post("/register", response_model=RegisterResponse)
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    return register_user(db, payload, request=request)


@router.post("/password-reset-requests", response_model=PasswordResetResponse)
def request_password_reset(payload: PasswordResetRequest, request: Request, db: Session = Depends(get_db)):
    return submit_password_reset_request(db, payload, request=request)


@router.get("/me", response_model=AuthMeResponse)
def me(current_user: AuthContext = Depends(get_current_user)):
    return to_auth_response(current_user)


@router.post("/me/avatar", response_model=AuthMeResponse)
async def upload_avatar(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    try:
        image_bytes = await file.read(AVATAR_MAX_UPLOAD_BYTES + 1)
    finally:
        await file.close()

    if len(image_bytes) > AVATAR_MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="头像文件不能超过 2 MB")

    return save_auth_user_avatar(db, current_user, image_bytes, request=request)


@router.get("/me/avatar")
def get_avatar(
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return Response(
        content=read_auth_user_avatar(db, current_user),
        media_type="image/png",
        headers={"Cache-Control": "private, no-store"},
    )


@router.delete("/me/avatar", response_model=AuthMeResponse)
def delete_avatar(
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return remove_auth_user_avatar(db, current_user, request=request)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    revoke_session(db, request.cookies.get(SESSION_COOKIE_NAME), request=request)
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
        secure=settings.effective_session_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    return None
