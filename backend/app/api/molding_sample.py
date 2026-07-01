from fastapi import APIRouter, Depends, Response, status
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
    MoldingSampleStatusRequest,
    PinChangeRequest,
    PinVerifyRequest,
    PinVerifyResponse,
    RequisitionCreateRequest,
    RequisitionOut,
    RequisitionStatusRequest,
    ResetSupervisorPinRequest,
    RoleEntry,
    RolesResponse,
    SensitiveAuditLogOut,
    TotalCostSummary,
)
from app.services.molding_sample import (
    build_total_cost_summary,
    create_inventory_batch,
    change_pin,
    create_order,
    create_requisition,
    delete_order,
    delete_requisition,
    get_exchange_rate,
    get_prices,
    list_auth_roles,
    list_inventory_batches,
    list_inventory_movements,
    list_orders,
    list_requisitions,
    list_sensitive_audit_logs,
    load_order,
    replace_material_prices,
    reset_supervisor_pin,
    transition_status,
    update_order,
    update_order_items,
    update_requisition_status,
    verify_pin,
)

router = APIRouter()


def serialize_order(order) -> MoldingSampleDetailResponse:
    return MoldingSampleDetailResponse(
        order=order,
        items=list(order.items),
        audit_logs=list(order.audit_logs),
    )


@router.get("/api/injection", response_model=list[MoldingSampleDetailResponse])
def get_injection_orders(db: Session = Depends(get_db)):
    return [serialize_order(order) for order in list_orders(db)]


@router.get("/api/injection/{order_id}", response_model=MoldingSampleDetailResponse)
def get_injection_order(order_id: str, db: Session = Depends(get_db)):
    return serialize_order(load_order(db, order_id))


@router.post("/api/injection", response_model=MoldingSampleDetailResponse, status_code=status.HTTP_201_CREATED)
def post_injection_order(payload: MoldingSampleCreateRequest, db: Session = Depends(get_db)):
    return serialize_order(create_order(db, payload))


@router.put("/api/injection/{order_id}", response_model=MoldingSampleDetailResponse)
def put_injection_order(order_id: str, payload: MoldingSampleEditRequest, db: Session = Depends(get_db)):
    return serialize_order(update_order(db, order_id, payload))


@router.delete("/api/injection/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_injection_order(
    order_id: str,
    actor_name: str,
    actor_role: str,
    pin: str = "",
    db: Session = Depends(get_db),
):
    delete_order(db, order_id, actor_name, actor_role, pin)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/api/injection/{order_id}/status", response_model=MoldingSampleDetailResponse)
def patch_injection_status(order_id: str, payload: MoldingSampleStatusRequest, db: Session = Depends(get_db)):
    return serialize_order(transition_status(db, order_id, payload))


@router.patch("/api/injection/{order_id}/items", response_model=MoldingSampleDetailResponse)
def patch_injection_items(order_id: str, payload: MoldingSampleItemsPatchRequest, db: Session = Depends(get_db)):
    return serialize_order(update_order_items(db, order_id, payload.items))


@router.get("/api/material-prices", response_model=MaterialPricesResponse)
def get_material_prices(db: Session = Depends(get_db)):
    return {
        "prices": get_prices(db),
        "rmb_to_hkd_rate": get_exchange_rate(db),
    }


@router.post("/api/manager-update-prices", response_model=MaterialPricesResponse)
def post_material_prices(payload: MaterialPricesUpdateRequest, db: Session = Depends(get_db)):
    return replace_material_prices(
        db,
        prices=payload.prices,
        rmb_to_hkd_rate=payload.rmb_to_hkd_rate,
        manager_name=payload.manager_name,
        manager_pin=payload.manager_pin,
    )


@router.get("/api/roles", response_model=RolesResponse)
def get_roles(db: Session = Depends(get_db)):
    return list_auth_roles(db)


@router.post("/api/verify-pin", response_model=PinVerifyResponse)
def post_verify_pin(payload: PinVerifyRequest, db: Session = Depends(get_db)):
    return verify_pin(db, payload)


@router.post("/api/change-pin", response_model=PinVerifyResponse)
def post_change_pin(payload: PinChangeRequest, db: Session = Depends(get_db)):
    return change_pin(db, payload)


@router.post("/api/reset-supervisor-pin", response_model=RoleEntry)
def post_reset_supervisor_pin(payload: ResetSupervisorPinRequest, db: Session = Depends(get_db)):
    return reset_supervisor_pin(db, payload)


@router.get("/api/sensitive-audit-logs", response_model=list[SensitiveAuditLogOut])
def get_sensitive_audit_logs(db: Session = Depends(get_db)):
    return list_sensitive_audit_logs(db)


@router.get("/api/requisitions", response_model=list[RequisitionOut])
def get_requisitions(order_id: str | None = None, db: Session = Depends(get_db)):
    return list_requisitions(db, order_id=order_id)


@router.get("/api/inventory-batches", response_model=list[InventoryBatchOut])
def get_inventory_batches(material: str | None = None, db: Session = Depends(get_db)):
    return list_inventory_batches(db, material=material)


@router.get("/api/inventory-movements", response_model=list[InventoryMovementOut])
def get_inventory_movements(
    batch_id: str | None = None,
    material: str | None = None,
    requisition_id: str | None = None,
    db: Session = Depends(get_db),
):
    return list_inventory_movements(
        db,
        batch_id=batch_id,
        material=material,
        requisition_id=requisition_id,
    )


@router.post("/api/inventory-batches", response_model=InventoryBatchOut, status_code=status.HTTP_201_CREATED)
def post_inventory_batch(payload: InventoryBatchCreateRequest, db: Session = Depends(get_db)):
    return create_inventory_batch(db, payload)


@router.post("/api/requisitions", response_model=RequisitionOut, status_code=status.HTTP_201_CREATED)
def post_requisition(payload: RequisitionCreateRequest, db: Session = Depends(get_db)):
    return create_requisition(db, payload)


@router.patch("/api/requisitions/{requisition_id}/status", response_model=RequisitionOut)
def patch_requisition_status(
    requisition_id: str,
    payload: RequisitionStatusRequest,
    db: Session = Depends(get_db),
):
    return update_requisition_status(db, requisition_id, payload)


@router.delete("/api/requisitions/{requisition_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_requisition_route(requisition_id: str, db: Session = Depends(get_db)):
    delete_requisition(db, requisition_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/api/injection-total-costs", response_model=list[TotalCostSummary])
def get_injection_total_costs(db: Session = Depends(get_db)):
    return [
        build_total_cost_summary(order)
        for order in list_orders(db)
        if order.status == "已完成"
    ]
