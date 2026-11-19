from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session
from app.db import get_db
from app.schemas.position_review import AdminAdjustment, CommitInput, DecisionInput, SubmitReview, UpdateReview, WithdrawReview, PreviewInput
from app.schemas.position_review import Position
from app.schemas.access_studio import LegacyConfirmation, StudioCommit, StudioDraft, StudioLifecycle
from app.schemas.identity import FactoryScope
from app.services import access_studio
from app.services.auth import AuthContext, get_current_user
from app.services import position_reviews as self_service, position_workbench as workbench, position_workbench_read as reads


class PositionRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()
        async def handler(request):
            request_id = uuid4().hex
            try:
                response = await original(request)
            except HTTPException as exc:
                detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
                details = dict(detail.get("details", {}))
                if request.url.path.endswith(("/preview", "/legacy-preview", "/lifecycle-preview")):
                    details.update(allowed_to_commit=False, blocked_reasons=[detail.get("message", "当前方案无法办理")])
                response = JSONResponse(status_code=exc.status_code, content={"code": detail.get("code", "POSITION_REQUEST_FAILED"),
                    "message": detail.get("message", "请求未完成"), "details": details, "request_id": request_id}, headers=exc.headers)
            except RequestValidationError as exc:
                fields = [".".join(map(str, error["loc"][1:])) for error in exc.errors()]
                details = {"fields": fields}
                message = "请核对填写内容"
                if request.url.path.endswith(("/preview", "/legacy-preview")):
                    if any(field.endswith(".department") or field.endswith(".permission_department") for field in fields):
                        message = "请明确选择每个权限包或个人例外的作用部门"
                    details.update(allowed_to_commit=False, blocked_reasons=[message])
                response = JSONResponse(status_code=422, content={"code": "INVALID_FIELDS", "message": message,
                    "details": details, "request_id": request_id})
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Request-ID"] = request_id
            return response
        return handler


router = APIRouter(prefix="/api", route_class=PositionRoute)


@router.get("/auth/me/position-profile")
def self_profile(db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return self_service.self_profile(db, user.id)


@router.get("/auth/me/position-reviews")
def history(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
            db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return self_service.self_history(db, user.id, page, page_size)


@router.post("/auth/me/position-reviews")
def submit(payload: SubmitReview, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return self_service.submit(db, user.id, payload)


@router.patch("/auth/me/position-reviews/{review_id}")
def edit(review_id: str, payload: UpdateReview, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return self_service.mutate_self(db, user.id, review_id, payload)


@router.post("/auth/me/position-reviews/{review_id}/withdraw")
def withdraw(review_id: str, payload: WithdrawReview, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return self_service.mutate_self(db, user.id, review_id, payload, withdraw=True)


@router.get("/iam/position-workbench/queue")
def queue(page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100), q: str = Query("", max_length=128),
          status: str = "pending", kind: str = "", org_unit_id: str = "",
          db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return reads.queue(db, user, page=page, page_size=page_size, q=q, status=status, kind=kind, org_unit_id=org_unit_id)


@router.get("/iam/position-workbench/packages")
def packages(item_key: str = "", org_unit_id: str = "", department_code: str = "",
             scope_kind: str = "home", factory_ids: list[str] = Query(default=[]),
             db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    from pydantic import ValidationError
    try:
        profile = Position(org_unit_id=org_unit_id, department_code=department_code, position="范围核对") if org_unit_id else None
        scope = FactoryScope(kind=scope_kind, factory_ids=factory_ids)
    except ValidationError:
        raise HTTPException(422, {"code": "INVALID_SCOPE", "message": "请选择有效组织、部门和业务范围"})
    return workbench.packages(db, user, item_key, profile, scope)


@router.get("/iam/position-workbench/items/{item_key}")
def detail(item_key: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return reads.detail(db, user, item_key)


@router.post("/iam/position-workbench/admin-adjustments")
def admin_adjust(payload: AdminAdjustment, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return workbench.admin_adjustment(db, user.id, payload)


@router.post("/iam/position-workbench/items/{item_key}/preview")
def preview(item_key: str, payload: PreviewInput, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return workbench.preview(db, user.id, item_key, payload)


@router.post("/iam/position-workbench/items/{item_key}/commit")
def commit(item_key: str, payload: CommitInput, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return workbench.commit(db, user.id, item_key, payload)


@router.post("/iam/position-workbench/items/{item_key}/decision")
def decide(item_key: str, payload: DecisionInput, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return workbench.decide(db, user.id, item_key, payload)


@router.get("/iam/position-workbench/receipts/{command_id}")
def receipt(command_id: UUID, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return workbench.read_receipt(db, user.id, command_id)


@router.post("/iam/users/{user_id}/access-studio/preview")
def studio_preview(user_id: str, payload: StudioDraft | StudioLifecycle, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return access_studio.preview(db, user.id, user_id, payload)


@router.get("/iam/access-studio/package-abilities")
def studio_package_abilities(db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    from sqlalchemy import select
    from app.models.auth import AuthRolePermission, AuthPermission
    from app.services.iam import _ensure_iam_manager, _ensure_permission_catalog_reader
    _ensure_iam_manager(db, user)
    _ensure_permission_catalog_reader(db, user)
    rows = db.execute(select(AuthRolePermission.role_id, AuthPermission.code, AuthPermission.name)
        .join(AuthPermission, AuthPermission.id == AuthRolePermission.permission_id)
        .order_by(AuthRolePermission.role_id, AuthPermission.code))
    result = {}
    for role_id, code, name in rows:
        result.setdefault(role_id, []).append({"code": code, "name": name})
    return result


@router.post("/iam/users/{user_id}/access-studio/legacy-preview")
def studio_legacy_preview(user_id: str, payload: LegacyConfirmation, db: Session = Depends(get_db),
                          user: AuthContext = Depends(get_current_user)):
    return access_studio.preview(db, user.id, user_id, payload)


@router.post("/iam/users/{user_id}/access-studio/commit")
def studio_commit(user_id: str, payload: StudioCommit, idempotency_key: UUID = Header(),
                  db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return access_studio.commit(db, user.id, user_id, payload, idempotency_key)


@router.get("/iam/access-studio/receipts/{command_id}")
def studio_receipt(command_id: UUID, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return access_studio.read_receipt(db, user.id, command_id)
