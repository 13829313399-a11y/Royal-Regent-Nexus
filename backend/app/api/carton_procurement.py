from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.carton_procurement import (
    CartonClosingGenerateRequest,
    CartonClosingOut,
    CartonClosingStatusRequest,
    CartonDashboardOut,
    CartonExceptionListOut,
    CartonExceptionOut,
    CartonExceptionUpdate,
    CartonImportBatchOut,
    CartonInventoryBalanceOut,
    CartonInventoryMovementCreate,
    CartonInventoryMovementListOut,
    CartonInventoryMovementOut,
    CartonInventoryReversalRequest,
    CartonOrderCreate,
    CartonOrderListOut,
    CartonOrderOut,
    CartonReceiptConfirmRequest,
    CartonReceiptCreate,
    CartonReceiptListOut,
    CartonReceiptOut,
)
from app.services.auth import (
    AuthContext,
    ensure_permission_in_scope,
    get_current_user,
    has_permission_in_scope,
)
from app.services.carton_procurement import (
    CARTON_DEPARTMENTS,
    confirm_receipt,
    create_import_batch,
    create_inventory_movement,
    create_order,
    create_receipt,
    dashboard,
    generate_closings,
    get_import_batch,
    inventory_balances,
    list_closings,
    list_exceptions,
    list_movements,
    list_orders,
    list_receipts,
    order_out,
    receipt_out,
    require_carton_factory,
    reverse_inventory_movement,
    update_closing_status,
    update_exception,
)


router = APIRouter(
    prefix="/api/carton-procurement",
    tags=["carton-procurement"],
)


def _ensure_permission(
    db: Session,
    user: AuthContext,
    permission: str,
    factory_id: str,
) -> str:
    factory_id = require_carton_factory(factory_id)
    if any(
        has_permission_in_scope(user, permission, factory_id, department)
        for department in CARTON_DEPARTMENTS
    ):
        return factory_id
    ensure_permission_in_scope(db, user, permission, factory_id, CARTON_DEPARTMENTS[0])
    return factory_id


@router.get("/dashboard", response_model=CartonDashboardOut)
def get_dashboard(
    factory_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(db, current_user, "carton_procurement:read", factory_id)
    return dashboard(db, factory_id)


@router.get("/orders", response_model=CartonOrderListOut)
def get_orders(
    factory_id: str,
    customer_code: str = Query(default="", max_length=64),
    search: str = Query(default="", max_length=128),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(db, current_user, "carton_procurement:read", factory_id)
    total, items = list_orders(
        db,
        factory_id,
        customer_code=customer_code.strip(),
        search=search.strip(),
        limit=limit,
        offset=offset,
    )
    return CartonOrderListOut(
        factory_id=factory_id,
        total=total,
        limit=limit,
        offset=offset,
        items=[order_out(db, item) for item in items],
    )


@router.post("/orders", response_model=CartonOrderOut, status_code=201)
def post_order(
    payload: CartonOrderCreate,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(db, current_user, "carton_procurement:order_write", payload.factory_id)
    return order_out(db, create_order(db, payload, current_user))


@router.get("/receipts", response_model=CartonReceiptListOut)
def get_receipts(
    factory_id: str,
    customer_code: str = Query(default="", max_length=64),
    search: str = Query(default="", max_length=128),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(db, current_user, "carton_procurement:read", factory_id)
    total, items = list_receipts(
        db,
        factory_id,
        customer_code=customer_code.strip(),
        search=search.strip(),
        limit=limit,
        offset=offset,
    )
    return CartonReceiptListOut(
        factory_id=factory_id,
        total=total,
        limit=limit,
        offset=offset,
        items=[receipt_out(db, item) for item in items],
    )


@router.post("/receipts", response_model=CartonReceiptOut, status_code=201)
def post_receipt(
    payload: CartonReceiptCreate,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(db, current_user, "carton_procurement:receipt_write", payload.factory_id)
    return receipt_out(db, create_receipt(db, payload, current_user))


@router.post("/receipts/{receipt_id}/confirm", response_model=CartonReceiptOut)
def post_receipt_confirmation(
    receipt_id: str,
    payload: CartonReceiptConfirmRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(db, current_user, "carton_procurement:receipt_write", payload.factory_id)
    return receipt_out(db, confirm_receipt(db, receipt_id, payload, current_user))


@router.post("/receipt-imports", response_model=CartonImportBatchOut, status_code=201)
async def post_receipt_import(
    factory_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(db, current_user, "carton_procurement:import", factory_id)
    content = await file.read()
    return create_import_batch(db, factory_id, "DELIVERY_NOTE", file, content, current_user)


@router.post("/weekly-imports", response_model=CartonImportBatchOut, status_code=201)
async def post_weekly_import(
    factory_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(db, current_user, "carton_procurement:import", factory_id)
    content = await file.read()
    return create_import_batch(db, factory_id, "WEEKLY_SCHEDULE", file, content, current_user)


@router.get("/imports/{batch_id}", response_model=CartonImportBatchOut)
def get_import_preview(
    batch_id: str,
    factory_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(db, current_user, "carton_procurement:read", factory_id)
    return get_import_batch(db, factory_id, batch_id)


@router.get("/exceptions", response_model=CartonExceptionListOut)
def get_exceptions(
    factory_id: str,
    status_filter: str = Query(default="", max_length=24),
    search: str = Query(default="", max_length=128),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(db, current_user, "carton_procurement:read", factory_id)
    total, items = list_exceptions(
        db,
        factory_id,
        status_filter=status_filter.strip(),
        search=search.strip(),
        limit=limit,
        offset=offset,
    )
    return CartonExceptionListOut(
        factory_id=factory_id,
        total=total,
        limit=limit,
        offset=offset,
        items=[CartonExceptionOut.model_validate(item) for item in items],
    )


@router.patch("/exceptions/{exception_id}", response_model=CartonExceptionOut)
def patch_exception(
    exception_id: str,
    payload: CartonExceptionUpdate,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(db, current_user, "carton_procurement:exception_manage", payload.factory_id)
    return update_exception(db, exception_id, payload, current_user)


@router.get("/inventory/movements", response_model=CartonInventoryMovementListOut)
def get_inventory_movements(
    factory_id: str,
    customer_code: str = Query(default="", max_length=64),
    search: str = Query(default="", max_length=128),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(db, current_user, "carton_procurement:read", factory_id)
    total, items = list_movements(
        db,
        factory_id,
        customer_code=customer_code.strip(),
        search=search.strip(),
        limit=limit,
        offset=offset,
    )
    return CartonInventoryMovementListOut(
        factory_id=factory_id,
        total=total,
        limit=limit,
        offset=offset,
        items=items,
    )


@router.get("/inventory/balances", response_model=list[CartonInventoryBalanceOut])
def get_inventory_balances(
    factory_id: str,
    customer_code: str = Query(default="", max_length=64),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(db, current_user, "carton_procurement:read", factory_id)
    return inventory_balances(db, factory_id, customer_code=customer_code.strip())


@router.post("/inventory/movements", response_model=CartonInventoryMovementOut, status_code=201)
def post_inventory_movement(
    payload: CartonInventoryMovementCreate,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(db, current_user, "carton_procurement:inventory_write", payload.factory_id)
    return create_inventory_movement(db, payload, current_user)


@router.post(
    "/inventory/movements/{movement_id}/reverse",
    response_model=CartonInventoryMovementOut,
    status_code=201,
)
def post_inventory_reversal(
    movement_id: str,
    payload: CartonInventoryReversalRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(db, current_user, "carton_procurement:inventory_write", payload.factory_id)
    return reverse_inventory_movement(db, movement_id, payload, current_user)


@router.get("/closings", response_model=list[CartonClosingOut])
def get_closings(
    factory_id: str,
    period: str = Query(default="", max_length=7),
    customer_code: str = Query(default="", max_length=64),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(db, current_user, "carton_procurement:read", factory_id)
    return list_closings(
        db,
        factory_id,
        period=period.strip(),
        customer_code=customer_code.strip(),
    )


@router.post("/closings/generate", response_model=list[CartonClosingOut])
def post_closing_generation(
    payload: CartonClosingGenerateRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(db, current_user, "carton_procurement:closing_manage", payload.factory_id)
    return generate_closings(db, payload, current_user)


@router.post("/closings/{closing_id}/status", response_model=CartonClosingOut)
def post_closing_status(
    closing_id: str,
    payload: CartonClosingStatusRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(db, current_user, "carton_procurement:closing_manage", payload.factory_id)
    return update_closing_status(db, closing_id, payload, current_user)
