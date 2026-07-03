from fastapi import APIRouter, Body, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.molding_sample import (
    InventoryBatchCreateRequest,
    InventoryBatchOut,
    InventoryMovementOut,
    MaterialPricesResponse,
    MaterialPricesUpdateRequest,
    MoldingSampleCreateRequest,
    MoldingSampleDetailResponse,
    MoldingSampleEditRequest,
    MoldingSampleItemsPatchRequest,
    MoldingSampleNotificationOut,
    MoldingSampleNotificationUpdateRequest,
    MoldingSampleProblemCreateRequest,
    MoldingSampleProblemOut,
    MoldingSampleProblemStatusRequest,
    MoldingSampleStatusRequest,
    RequisitionCreateRequest,
    RequisitionOut,
    RequisitionStatusRequest,
    SensitiveAuditLogOut,
    TotalCostSummary,
)
from app.services.auth import AuthContext, ensure_permission, get_current_user
from app.services.molding_sample import (
    build_total_cost_summary,
    create_inventory_batch,
    create_order,
    create_problem,
    create_requisition,
    delete_order,
    delete_requisition,
    get_exchange_rate,
    get_prices,
    list_inventory_batches,
    list_inventory_movements,
    list_notifications,
    list_orders,
    list_problems,
    list_requisitions,
    list_sensitive_audit_logs,
    load_order,
    replace_material_prices,
    transition_status,
    update_notification,
    update_order,
    update_order_items,
    update_problem_status,
    update_requisition_status,
)
from app.services.molding_sample_excel import XLSX_MIME, export_order_to_excel, parse_order_excel

router = APIRouter()


def serialize_order(order) -> MoldingSampleDetailResponse:
    return MoldingSampleDetailResponse(
        order=order,
        items=list(order.items),
        audit_logs=list(order.audit_logs),
        notifications=list(order.notifications),
        problems=list(order.problems),
    )


@router.get("/api/injection", response_model=list[MoldingSampleDetailResponse])
def get_injection_orders(
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return [serialize_order(order) for order in list_orders(db, current_user)]


@router.get("/api/injection/{order_id}", response_model=MoldingSampleDetailResponse)
def get_injection_order(
    order_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_permission(db, current_user, "molding_sample:read")
    return serialize_order(load_order(db, order_id, current_user))


@router.post("/api/injection", response_model=MoldingSampleDetailResponse, status_code=status.HTTP_201_CREATED)
def post_injection_order(
    payload: MoldingSampleCreateRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return serialize_order(create_order(db, payload, current_user))


@router.get("/api/injection/{order_id}/export-excel")
def export_injection_order_excel(
    order_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_permission(db, current_user, "molding_sample:read")
    order = load_order(db, order_id, current_user)
    content = export_order_to_excel(order)
    filename = f"{order.id}-molding-sample.xlsx"
    return Response(
        content=content,
        media_type=XLSX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/api/injection/import-excel", response_model=MoldingSampleDetailResponse, status_code=status.HTTP_201_CREATED)
def import_injection_order_excel(
    body: bytes = Body(..., media_type=XLSX_MIME),
    order_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    try:
        payload = parse_order_excel(body, order_id_override=order_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return serialize_order(create_order(db, payload, current_user))


@router.put("/api/injection/{order_id}", response_model=MoldingSampleDetailResponse)
def put_injection_order(
    order_id: str,
    payload: MoldingSampleEditRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return serialize_order(update_order(db, order_id, payload, current_user))


@router.delete("/api/injection/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_injection_order(
    order_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    delete_order(db, order_id, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/api/injection/{order_id}/status", response_model=MoldingSampleDetailResponse)
def patch_injection_status(
    order_id: str,
    payload: MoldingSampleStatusRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return serialize_order(transition_status(db, order_id, payload, current_user))


@router.patch("/api/injection/{order_id}/items", response_model=MoldingSampleDetailResponse)
def patch_injection_items(
    order_id: str,
    payload: MoldingSampleItemsPatchRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return serialize_order(update_order_items(db, order_id, payload.items, current_user))


@router.get("/api/molding-sample-notifications", response_model=list[MoldingSampleNotificationOut])
def get_molding_sample_notifications(
    target_module: str | None = None,
    target_role: str | None = None,
    factory_id: str | None = None,
    order_id: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return list_notifications(
        db,
        current_user=current_user,
        target_module=target_module,
        target_role=target_role,
        factory_id=factory_id,
        order_id=order_id,
        status=status,
    )


@router.patch("/api/molding-sample-notifications/{notification_id}", response_model=MoldingSampleNotificationOut)
def patch_molding_sample_notification(
    notification_id: str,
    payload: MoldingSampleNotificationUpdateRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return update_notification(db, notification_id, payload, current_user)


@router.get("/api/problems", response_model=list[MoldingSampleProblemOut])
def get_molding_sample_problems(
    order_id: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return list_problems(db, current_user=current_user, order_id=order_id, status=status)


@router.post("/api/problems", response_model=MoldingSampleProblemOut, status_code=status.HTTP_201_CREATED)
def post_molding_sample_problem(
    payload: MoldingSampleProblemCreateRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return create_problem(db, payload, current_user)


@router.patch("/api/problems/{problem_id}", response_model=MoldingSampleProblemOut)
def patch_molding_sample_problem(
    problem_id: str,
    payload: MoldingSampleProblemStatusRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return update_problem_status(db, problem_id, payload, current_user)


@router.get("/api/material-prices", response_model=MaterialPricesResponse)
def get_material_prices(
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_permission(db, current_user, "molding_sample:read")
    return {
        "prices": get_prices(db),
        "rmb_to_hkd_rate": get_exchange_rate(db),
    }


@router.post("/api/manager-update-prices", response_model=MaterialPricesResponse)
def post_material_prices(
    payload: MaterialPricesUpdateRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return replace_material_prices(
        db,
        prices=payload.prices,
        rmb_to_hkd_rate=payload.rmb_to_hkd_rate,
        current_user=current_user,
    )


@router.get("/api/sensitive-audit-logs", response_model=list[SensitiveAuditLogOut])
def get_sensitive_audit_logs(
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_permission(db, current_user, "molding_sample:audit_read")
    return list_sensitive_audit_logs(db)


@router.get("/api/requisitions", response_model=list[RequisitionOut])
def get_requisitions(
    order_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_permission(db, current_user, "molding_sample:read")
    return list_requisitions(db, order_id=order_id)


@router.get("/api/inventory-batches", response_model=list[InventoryBatchOut])
def get_inventory_batches(
    material: str | None = None,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_permission(db, current_user, "molding_sample:read")
    return list_inventory_batches(db, material=material)


@router.get("/api/inventory-movements", response_model=list[InventoryMovementOut])
def get_inventory_movements(
    batch_id: str | None = None,
    material: str | None = None,
    requisition_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_permission(db, current_user, "molding_sample:read")
    return list_inventory_movements(
        db,
        batch_id=batch_id,
        material=material,
        requisition_id=requisition_id,
    )


@router.post("/api/inventory-batches", response_model=InventoryBatchOut, status_code=status.HTTP_201_CREATED)
def post_inventory_batch(
    payload: InventoryBatchCreateRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return create_inventory_batch(db, payload, current_user)


@router.post("/api/requisitions", response_model=RequisitionOut, status_code=status.HTTP_201_CREATED)
def post_requisition(
    payload: RequisitionCreateRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return create_requisition(db, payload, current_user)


@router.patch("/api/requisitions/{requisition_id}/status", response_model=RequisitionOut)
def patch_requisition_status(
    requisition_id: str,
    payload: RequisitionStatusRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return update_requisition_status(db, requisition_id, payload, current_user)


@router.delete("/api/requisitions/{requisition_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_requisition_route(
    requisition_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    delete_requisition(db, requisition_id, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/api/injection-total-costs", response_model=list[TotalCostSummary])
def get_injection_total_costs(
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_permission(db, current_user, "molding_sample:read")
    return [
        build_total_cost_summary(order)
        for order in list_orders(db, current_user)
        if order.status == "已完成"
    ]
