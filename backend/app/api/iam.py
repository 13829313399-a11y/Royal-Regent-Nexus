from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.iam import (
    AccessCommitRequest,
    AccessCommitResponse,
    AccessPreviewResponse,
    AccessRequestCreate,
    AccessRequestDecision,
    AccessRequestOut,
    AuditEventOut,
    ManageableScopesResponse,
    PermissionOut,
    RoleAccessCommitResponse,
    RoleAccessOut,
    RoleAccessPreviewRequest,
    RoleAccessPreviewResponse,
    RoleSummaryOut,
    UserAccessOut,
    UserAccessPreviewRequest,
    UserSearchOut,
)
from app.services.auth import AuthContext, get_current_user
from app.services.iam import (
    approve_access_request,
    commit_role_access,
    commit_user_access,
    create_access_request,
    get_manageable_scopes,
    get_role_access,
    get_user_access,
    list_access_requests,
    list_audit_events,
    list_permissions,
    list_roles,
    preview_role_access,
    preview_user_access,
    reject_access_request,
    search_users,
)

router = APIRouter(prefix="/api/iam")


@router.get("/permissions", response_model=list[PermissionOut])
def permissions(
    status: str = "active",
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return list_permissions(db, current_user, status=status)


@router.get("/manageable-scopes", response_model=ManageableScopesResponse)
def manageable_scopes(
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return get_manageable_scopes(db, current_user)


@router.get("/users/search", response_model=list[UserSearchOut])
def users_search(
    query: str = "",
    status: str = "",
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return search_users(db, current_user, query_text=query, status=status, limit=limit)


@router.get("/users/{user_id}/access", response_model=UserAccessOut)
def user_access(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return get_user_access(db, current_user, user_id)


@router.post("/users/{user_id}/access/preview", response_model=AccessPreviewResponse)
def user_access_preview(
    user_id: str,
    payload: UserAccessPreviewRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return preview_user_access(db, current_user, user_id, payload)


@router.post("/users/{user_id}/access/commit", response_model=AccessCommitResponse)
def user_access_commit(
    user_id: str,
    payload: AccessCommitRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return commit_user_access(db, current_user, user_id, payload, request=request)


@router.get("/roles", response_model=list[RoleSummaryOut])
def roles(
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return list_roles(db, current_user)


@router.get("/roles/{role_id}/access", response_model=RoleAccessOut)
def role_access(
    role_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return get_role_access(db, current_user, role_id)


@router.post("/roles/{role_id}/access/preview", response_model=RoleAccessPreviewResponse)
def role_access_preview(
    role_id: str,
    payload: RoleAccessPreviewRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return preview_role_access(db, current_user, role_id, payload)


@router.post("/roles/{role_id}/access/commit", response_model=RoleAccessCommitResponse)
def role_access_commit(
    role_id: str,
    payload: AccessCommitRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return commit_role_access(db, current_user, role_id, payload, request=request)


@router.get("/access-requests", response_model=list[AccessRequestOut])
def access_requests(
    status: str = "pending",
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return list_access_requests(db, current_user, status=status)


@router.post("/access-requests", response_model=AccessRequestOut)
def submit_access_request(
    payload: AccessRequestCreate,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return create_access_request(db, current_user, payload)


@router.post("/access-requests/{request_id}/approve", response_model=AccessRequestOut)
def approve_request(
    request_id: str,
    payload: AccessRequestDecision,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return approve_access_request(db, current_user, request_id, payload, request=request)


@router.post("/access-requests/{request_id}/reject", response_model=AccessRequestOut)
def reject_request(
    request_id: str,
    payload: AccessRequestDecision,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return reject_access_request(db, current_user, request_id, payload, request=request)


@router.get("/audit-events", response_model=list[AuditEventOut])
def audit_events(
    actor_user_id: str = "",
    target_user_id: str = "",
    module_code: str = "",
    factory_id: str = "",
    department: str = "",
    date_from: str = Query(default="", alias="from"),
    date_to: str = Query(default="", alias="to"),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return list_audit_events(
        db,
        current_user,
        actor_user_id=actor_user_id,
        target_user_id=target_user_id,
        module_code=module_code,
        factory_id=factory_id,
        department=department,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )
