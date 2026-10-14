from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session
from app.db import get_db
from app.schemas.position_review import AdminAdjustment, CommitInput, DecisionInput, SubmitReview, UpdateReview, WithdrawReview, PreviewInput
from app.schemas.position_review import Position
from app.schemas.identity import FactoryScope
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
                response = JSONResponse(status_code=exc.status_code, content={"code": detail.get("code", "POSITION_REQUEST_FAILED"),
                    "message": detail.get("message", "请求未完成"), "details": detail.get("details", {}), "request_id": request_id}, headers=exc.headers)
            except RequestValidationError as exc:
                response = JSONResponse(status_code=422, content={"code": "INVALID_FIELDS", "message": "请核对填写内容",
                    "details": {"fields": [".".join(map(str, error["loc"][1:])) for error in exc.errors()]}, "request_id": request_id})
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
