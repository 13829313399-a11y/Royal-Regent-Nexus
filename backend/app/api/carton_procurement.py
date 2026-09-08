from decimal import Decimal
from fastapi.encoders import jsonable_encoder
from io import BytesIO
from urllib.parse import quote as url_quote

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.carton_inventory_report import CartonInventoryReportOut
from app.services.carton_inventory_report import inventory_report
from app.schemas.carton_order_timeline import CartonOrderTimelineOut
from app.services.carton_order_timeline import order_timeline
from app.schemas.carton_stocktake import StocktakeCreate, StocktakeAction
from app.services.carton_stocktake import create_stocktake, stocktake_detail, list_stocktakes, act_stocktake
from app.schemas.carton_procurement import (
    CartonAuditEventListOut,
    CartonClosingGenerateRequest,
    CartonClosingOut,
    CartonClosingStatusRequest,
    CartonClosingUnlockRequest,
    CartonInventoryPriceConfirmRequest,
    CartonCustomerCreate,
    CartonCustomerListOut,
    CartonCustomerOut,
    CartonCustomerUpdate,
    CartonDashboardOut,
    CartonExceptionListOut,
    CartonExceptionOut,
    CartonExceptionUpdate,
    CartonImportBatchOut,
    CartonImportBatchListOut,
    CartonHistoryOrderImportOut,
    CartonHistoryInventoryImportOut,
    CartonInventoryBalanceOut,
    CartonInventoryBulkCreate,
    CartonInventoryFlowSummaryOut,
    CartonInventoryMovementCreate,
    CartonInventoryMovementListOut,
    CartonInventoryMovementOut,
    CartonInventoryReversalRequest,
    CartonInventoryRelocateRequest,
    CartonOrderAppendRequest,
    CartonOrderBulkCancelRequest,
    CartonOrderBulkSubmitRequest,
    CartonOrderCancelRequest,
    CartonOrderCreate,
    CartonOrderHistorySuggestionListOut,
    CartonOrderListOut,
    CartonOrderOut,
    CartonPurchaseOrderContextOut,
    CartonPurchaseOrderIssueCreate,
    CartonOrderReduceRequest,
    CartonOrderSelectionRequest,
    CartonOrderSubmitRequest,
    CartonOrderUpdate,
    CartonReceiptConfirmRequest,
    CartonReceiptReverseRequest,
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
    append_order,
    bulk_cancel_orders,
    bulk_submit_orders_to_supplier,
    cancel_order,
    confirm_receipt,
    confirm_inventory_price,
    closing_out,
    create_customer,
    create_import_batch,
    create_inventory_movement,
    create_inventory_movements_bulk,
    create_order,
    create_purchase_order_issue,
    create_purchase_order_issues_batch,
    create_receipt,
    delete_customer,
    delete_unmatched_delivery_import,
    dashboard,
    generate_closings,
    get_import_batch,
    get_latest_import_batch,
    get_order_by_no,
    get_order_lines,
    get_purchase_order_issue,
    inventory_balances,
    list_customers,
    list_closings,
    list_exceptions,
    list_import_batches,
    list_inventory_flow_summary,
    list_audit_events,
    list_movements,
    list_orders,
    list_receipts,
    order_out,
    purchase_order_context,
    reduce_order,
    receipt_out,
    require_carton_factory,
    reverse_inventory_movement,
    reverse_receipt,
    relocate_inventory,
    return_order,
    search_order_history_items,
    submit_order_to_supplier,
    update_order,
    update_closing_status,
    unlock_closing,
    update_customer,
    update_exception,
)
from app.services.carton_procurement_export import (
    XLSX_MEDIA_TYPE,
    build_combined_purchase_order_workbook,
    build_purchase_order_issue_batch_workbook,
    build_purchase_order_issue_workbook,
    build_purchase_order_workbook,
)
from app.services.carton_procurement_history_import import import_history_orders
from app.services.carton_procurement_history_inventory import import_history_inventory
from app.core.time import business_now


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


@router.get("/customers", response_model=CartonCustomerListOut)
def get_customers(
    factory_id: str,
    include_inactive: bool = False,
    search: str = Query(default="", max_length=128),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(db, current_user, "carton_procurement:read", factory_id)
    items = list_customers(
        db,
        factory_id,
        include_inactive=include_inactive,
        search=search.strip(),
    )
    return CartonCustomerListOut(factory_id=factory_id, total=len(items), items=items)


@router.post("/customers", response_model=CartonCustomerOut, status_code=201)
def post_customer(
    payload: CartonCustomerCreate,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(db, current_user, "carton_procurement:customer_manage", payload.factory_id)
    return create_customer(db, payload, current_user)


@router.patch("/customers/{customer_id}", response_model=CartonCustomerOut)
def patch_customer(
    customer_id: str,
    payload: CartonCustomerUpdate,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(db, current_user, "carton_procurement:customer_manage", payload.factory_id)
    return update_customer(db, customer_id, payload, current_user)


@router.delete("/customers/{customer_id}", status_code=204)
def remove_customer(
    customer_id: str,
    factory_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(db, current_user, "carton_procurement:customer_manage", factory_id)
    delete_customer(db, factory_id, customer_id, current_user)


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
    status_filter: str = Query(default="", max_length=32),
    due_from: str = Query(default="", pattern=r"^$|^\d{4}-\d{2}-\d{2}$"),
    due_to: str = Query(default="", pattern=r"^$|^\d{4}-\d{2}-\d{2}$"),
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
        status_filter=status_filter.strip(),
        due_from=due_from.strip(),
        due_to=due_to.strip(),
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


@router.get("/order-history/item-suggestions", response_model=CartonOrderHistorySuggestionListOut)
def get_order_history_item_suggestions(
    factory_id: str,
    item_no: str = Query(min_length=1, max_length=128),
    customer_code: str = Query(default="", max_length=64),
    limit: int = Query(default=8, ge=1, le=20),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(
        db, current_user, "carton_procurement:read", factory_id
    )
    items = search_order_history_items(
        db,
        factory_id,
        item_no,
        customer_code=customer_code,
        limit=limit,
    )
    return CartonOrderHistorySuggestionListOut(
        factory_id=factory_id,
        query=item_no.strip(),
        total=len(items),
        items=items,
    )


@router.post("/orders", response_model=CartonOrderOut, status_code=201)
def post_order(
    payload: CartonOrderCreate,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(db, current_user, "carton_procurement:order_write", payload.factory_id)
    return order_out(db, create_order(db, payload, current_user))


@router.patch("/orders/{order_no}", response_model=CartonOrderOut)
def patch_order(
    order_no: str,
    payload: CartonOrderUpdate,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(db, current_user, "carton_procurement:order_write", payload.factory_id)
    return order_out(db, update_order(db, order_no, payload, current_user))


@router.post("/orders/{order_no}/submit-supplier", response_model=CartonOrderOut)
def post_order_submit_supplier(
    order_no: str,
    payload: CartonOrderSubmitRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(db, current_user, "carton_procurement:order_write", payload.factory_id)
    return order_out(db, submit_order_to_supplier(db, order_no, payload, current_user))


@router.post("/orders/{order_no}/append", response_model=CartonOrderOut)
def post_order_append(
    order_no: str,
    payload: CartonOrderAppendRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(db, current_user, "carton_procurement:order_write", payload.factory_id)
    order = get_order_by_no(db, require_carton_factory(payload.factory_id), order_no)
    if order.status in {"PENDING_SUPPLIER", "PARTIALLY_RECEIVED", "COMPLETED"}:
        _ensure_permission(db, current_user, "carton_procurement:order_adjust", payload.factory_id)
    return order_out(db, append_order(db, order_no, payload, current_user))


@router.post("/orders/{order_no}/reduce", response_model=CartonOrderOut)
def post_order_reduce(
    order_no: str,
    payload: CartonOrderReduceRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(db, current_user, "carton_procurement:order_adjust", payload.factory_id)
    return order_out(db, reduce_order(db, order_no, payload, current_user))


@router.post("/orders/{order_no}/cancel", response_model=CartonOrderOut)
def post_order_cancel(
    order_no: str,
    payload: CartonOrderCancelRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(db, current_user, "carton_procurement:order_write", payload.factory_id)
    return order_out(db, cancel_order(db, order_no, payload, current_user))


@router.post("/orders/{order_no}/return", response_model=CartonOrderOut)
def post_order_return(
    order_no: str,
    payload: CartonOrderCancelRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(db, current_user, "carton_procurement:order_write", payload.factory_id)
    return order_out(db, return_order(db, order_no, payload, current_user))


@router.post("/orders/bulk-cancel", response_model=list[CartonOrderOut])
def post_orders_bulk_cancel(
    payload: CartonOrderBulkCancelRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(db, current_user, "carton_procurement:order_write", payload.factory_id)
    return [order_out(db, order) for order in bulk_cancel_orders(db, payload, current_user)]


@router.post("/orders/bulk-submit-supplier", response_model=list[CartonOrderOut])
def post_orders_bulk_submit_supplier(
    payload: CartonOrderBulkSubmitRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(db, current_user, "carton_procurement:order_write", payload.factory_id)
    return [order_out(db, order) for order in bulk_submit_orders_to_supplier(db, payload, current_user)]


@router.post(
    "/orders/history-imports",
    response_model=CartonHistoryOrderImportOut,
    status_code=201,
)
async def post_history_order_import(
    factory_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(
        db, current_user, "carton_procurement:order_write", factory_id
    )
    content = await file.read()
    return import_history_orders(
        db,
        factory_id,
        file.filename or "history-orders.xlsx",
        content,
        current_user,
    )


@router.get("/orders/{order_no}/purchase-order.xlsx")
def get_purchase_order_workbook(
    order_no: str,
    factory_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(db, current_user, "carton_procurement:read", factory_id)
    order = get_order_by_no(db, factory_id, order_no)
    content = build_purchase_order_workbook(
        order,
        get_order_lines(db, order.id),
        generated_at=business_now(),
    )
    file_name = f"{order.order_no}_纸箱采购单.xlsx"
    return StreamingResponse(
        BytesIO(content),
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{url_quote(file_name)}"},
    )


@router.get(
    "/orders/{order_no}/purchase-order-context",
    response_model=CartonPurchaseOrderContextOut,
)
def get_purchase_order_context(
    order_no: str,
    factory_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(db, current_user, "carton_procurement:read", factory_id)
    order = get_order_by_no(db, factory_id, order_no)
    return purchase_order_context(db, order)


@router.post("/orders/{order_no}/purchase-order-issues.xlsx")
def post_purchase_order_issue_workbook(
    order_no: str,
    payload: CartonPurchaseOrderIssueCreate,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(
        db, current_user, "carton_procurement:order_write", payload.factory_id
    )
    order = get_order_by_no(db, factory_id, order_no)
    issue = create_purchase_order_issue(db, order, payload.expected_revision, current_user)
    content = build_purchase_order_issue_workbook(issue)
    file_name = f"{issue.document_no}_{issue.document_type}.xlsx"
    return StreamingResponse(
        BytesIO(content),
        media_type=XLSX_MEDIA_TYPE,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{url_quote(file_name)}",
            "X-Purchase-Order-Issue-Id": issue.id,
            "X-Purchase-Order-Document-No": issue.document_no,
        },
    )


@router.get("/orders/{order_no}/purchase-order-issues/{issue_id}.xlsx")
def get_purchase_order_issue_workbook(
    order_no: str,
    issue_id: str,
    factory_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(db, current_user, "carton_procurement:read", factory_id)
    order = get_order_by_no(db, factory_id, order_no)
    issue = get_purchase_order_issue(db, factory_id, order, issue_id)
    content = build_purchase_order_issue_workbook(issue)
    file_name = f"{issue.document_no}_{issue.document_type}.xlsx"
    return StreamingResponse(
        BytesIO(content),
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{url_quote(file_name)}"},
    )


@router.post("/orders/purchase-orders.xlsx")
def post_combined_purchase_order_workbook(
    payload: CartonOrderSelectionRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(db, current_user, "carton_procurement:read", payload.factory_id)
    generated_at = business_now()
    orders = []
    for order_no in payload.order_nos:
        order = get_order_by_no(db, factory_id, order_no)
        orders.append((order, get_order_lines(db, order.id)))
    content = build_combined_purchase_order_workbook(orders, generated_at=generated_at)
    file_name = f"纸箱累计对账表_{generated_at.strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(
        BytesIO(content),
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{url_quote(file_name)}"},
    )


@router.post("/orders/purchase-order-issues.xlsx")
def post_purchase_order_issue_batch_workbook(
    payload: CartonOrderBulkSubmitRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(db, current_user, "carton_procurement:order_write", payload.factory_id)
    generated_at = business_now()
    issues = create_purchase_order_issues_batch(db, payload, current_user)
    content = build_purchase_order_issue_batch_workbook(issues, generated_at=generated_at)
    file_name = f"供应商采购单批次_{generated_at.strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(
        BytesIO(content),
        media_type=XLSX_MEDIA_TYPE,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{url_quote(file_name)}",
            "X-Purchase-Order-Issue-Count": str(len(issues)),
        },
    )


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


@router.post("/receipts/{receipt_id}/reverse", response_model=CartonReceiptOut)
def post_receipt_reversal(
    receipt_id: str, payload: CartonReceiptReverseRequest,
    db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(db, current_user, "carton_procurement:receipt_write", payload.factory_id)
    _ensure_permission(db, current_user, "carton_procurement:inventory_write", payload.factory_id)
    return receipt_out(db, reverse_receipt(db, receipt_id, payload, current_user))


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


@router.post("/inspection-imports", response_model=CartonImportBatchOut, status_code=201)
async def post_inspection_import(
    factory_id: str,
    advance_days: int = Query(default=3, ge=0, le=30),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(db, current_user, "carton_procurement:import", factory_id)
    content = await file.read()
    return create_import_batch(
        db,
        factory_id,
        "INSPECTION_SCHEDULE",
        file,
        content,
        current_user,
        import_profile={"advance_days": advance_days},
    )


@router.get("/receipt-imports/latest", response_model=CartonImportBatchOut | None)
def get_latest_receipt_import(
    factory_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(db, current_user, "carton_procurement:read", factory_id)
    return get_latest_import_batch(db, factory_id, "DELIVERY_NOTE")


@router.delete("/receipt-imports/{batch_id}", status_code=204)
def remove_unmatched_receipt_import(
    batch_id: str,
    factory_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(db, current_user, "carton_procurement:import", factory_id)
    delete_unmatched_delivery_import(db, factory_id, batch_id, current_user)


@router.get("/imports", response_model=CartonImportBatchListOut)
def get_imports(
    factory_id: str,
    import_type: str = Query(default="", max_length=32),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(db, current_user, "carton_procurement:read", factory_id)
    total, items = list_import_batches(
        db,
        factory_id,
        import_type=import_type.strip(),
        limit=limit,
        offset=offset,
    )
    return CartonImportBatchListOut(
        factory_id=factory_id,
        total=total,
        limit=limit,
        offset=offset,
        items=items,
    )


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


@router.post(
    "/inventory/history-imports",
    response_model=CartonHistoryInventoryImportOut,
    status_code=201,
)
async def post_history_inventory_import(
    factory_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(
        db, current_user, "carton_procurement:inventory_write", factory_id
    )
    content = await file.read()
    return import_history_inventory(
        db,
        factory_id,
        file.filename or "history-inventory.xlsx",
        content,
        current_user,
    )


@router.get("/stocktakes")
def stocktakes_list(factory_id: str, limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0),
                    db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    _ensure_permission(db, user, "carton_procurement:read", factory_id)
    return list_stocktakes(db, factory_id, limit, offset)


@router.get("/stocktakes/{identifier}")
def stocktakes_detail(identifier: str, factory_id: str, db: Session = Depends(get_db),
                      user: AuthContext = Depends(get_current_user)):
    _ensure_permission(db, user, "carton_procurement:read", factory_id)
    return jsonable_encoder(stocktake_detail(db, factory_id, identifier), custom_encoder={Decimal: str})


@router.post("/stocktakes", status_code=201)
def stocktakes_create(payload: StocktakeCreate, db: Session = Depends(get_db),
                      user: AuthContext = Depends(get_current_user)):
    _ensure_permission(db, user, "carton_procurement:inventory_write", payload.factory_id)
    return jsonable_encoder(create_stocktake(db, payload, user), custom_encoder={Decimal: str})


@router.post("/stocktakes/{identifier}/actions")
def stocktakes_action(identifier: str, payload: StocktakeAction, db: Session = Depends(get_db),
                      user: AuthContext = Depends(get_current_user)):
    _ensure_permission(db, user, "carton_procurement:inventory_write", payload.factory_id)
    if payload.action in ("APPROVE", "RETURN", "CANCEL"):
        doc = stocktake_detail(db, payload.factory_id, identifier)
        if payload.action != "CANCEL" or doc["created_by"] != user.id:
            _ensure_permission(db, user, "carton_procurement:order_adjust", payload.factory_id)
    return jsonable_encoder(act_stocktake(db, identifier, payload, user), custom_encoder={Decimal: str})


@router.get("/inventory/balances", response_model=list[CartonInventoryBalanceOut])
def get_inventory_balances(
    factory_id: str,
    customer_code: str = Query(default="", max_length=64),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(db, current_user, "carton_procurement:read", factory_id)
    return inventory_balances(db, factory_id, customer_code=customer_code.strip())


@router.get("/inventory/report", response_model=CartonInventoryReportOut)
def get_inventory_report(
    factory_id: str,
    customer_code: str = Query(default="", max_length=64),
    date_from: str = Query(default="", pattern=r"^$|^\d{4}-\d{2}-\d{2}$"),
    date_to: str = Query(default="", pattern=r"^$|^\d{4}-\d{2}-\d{2}$"),
    search: str = Query(default="", max_length=255),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(db, current_user, "carton_procurement:read", factory_id)
    return inventory_report(db, factory_id, customer_code=customer_code.strip(),
                            date_from=date_from.strip(), date_to=date_to.strip(), search=search.strip())


@router.get("/inventory/order-timeline", response_model=CartonOrderTimelineOut)
def get_order_timeline(
    factory_id: str,
    customer_code: str = Query(default="", max_length=64),
    date_from: str = Query(default="", pattern=r"^$|^\d{4}-\d{2}-\d{2}$"),
    date_to: str = Query(default="", pattern=r"^$|^\d{4}-\d{2}-\d{2}$"),
    search: str = Query(default="", max_length=255),
    order_id: str = Query(default="", max_length=96),
    inventory_key: str = Query(default="", max_length=2048),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(db, current_user, "carton_procurement:read", factory_id)
    return order_timeline(db, factory_id, customer_code=customer_code.strip(), date_from=date_from,
                          date_to=date_to, search=search.strip(), order_id=order_id.strip(),
                          inventory_key=inventory_key.strip())


@router.get("/inventory/summary", response_model=list[CartonInventoryFlowSummaryOut])
def get_inventory_summary(
    factory_id: str,
    customer_code: str = Query(default="", max_length=64),
    date_from: str = Query(default="", pattern=r"^$|^\d{4}-\d{2}-\d{2}$"),
    date_to: str = Query(default="", pattern=r"^$|^\d{4}-\d{2}-\d{2}$"),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(db, current_user, "carton_procurement:read", factory_id)
    return list_inventory_flow_summary(
        db,
        factory_id,
        customer_code=customer_code.strip(),
        date_from=date_from.strip(),
        date_to=date_to.strip(),
    )


@router.post("/inventory/movements", response_model=CartonInventoryMovementOut, status_code=201)
def post_inventory_movement(
    payload: CartonInventoryMovementCreate,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(db, current_user, "carton_procurement:inventory_write", payload.factory_id)
    return create_inventory_movement(db, payload, current_user)


@router.post("/inventory/relocations", response_model=CartonInventoryBalanceOut)
def post_inventory_relocation(
    payload: CartonInventoryRelocateRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(db, current_user, "carton_procurement:inventory_write", payload.factory_id)
    return relocate_inventory(db, payload, current_user)


@router.post(
    "/inventory/movements/bulk",
    response_model=list[CartonInventoryMovementOut],
    status_code=201,
)
def post_inventory_movements_bulk(
    payload: CartonInventoryBulkCreate,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(db, current_user, "carton_procurement:inventory_write", payload.factory_id)
    return create_inventory_movements_bulk(db, payload, current_user)


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


@router.get("/audit-events", response_model=CartonAuditEventListOut)
def get_audit_events(
    factory_id: str,
    search: str = Query(default="", max_length=128),
    event_type: str = Query(default="", max_length=64),
    actor_user_id: str = Query(default="", max_length=64),
    date_from: str = Query(default="", pattern=r"^$|^\d{4}-\d{2}-\d{2}$"),
    date_to: str = Query(default="", pattern=r"^$|^\d{4}-\d{2}-\d{2}$"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(db, current_user, "carton_procurement:read", factory_id)
    total, items = list_audit_events(
        db,
        factory_id,
        search=search.strip(),
        event_type=event_type.strip(),
        actor_user_id=actor_user_id.strip(),
        date_from=date_from.strip(),
        date_to=date_to.strip(),
        limit=limit,
        offset=offset,
    )
    return CartonAuditEventListOut(
        factory_id=factory_id,
        total=total,
        limit=limit,
        offset=offset,
        items=items,
    )


@router.get("/closings", response_model=list[CartonClosingOut])
def get_closings(
    factory_id: str,
    period: str = Query(default="", max_length=7),
    customer_code: str = Query(default="", max_length=64),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(db, current_user, "carton_procurement:read", factory_id)
    rows = list_closings(
        db,
        factory_id,
        period=period.strip(),
        customer_code=customer_code.strip(),
    )
    return [closing_out(db, row) for row in rows]


@router.post("/closings/generate", response_model=list[CartonClosingOut])
def post_closing_generation(
    payload: CartonClosingGenerateRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(db, current_user, "carton_procurement:closing_manage", payload.factory_id)
    return [closing_out(db, row) for row in generate_closings(db, payload, current_user)]


@router.post("/closings/{closing_id}/status", response_model=CartonClosingOut)
def post_closing_status(
    closing_id: str,
    payload: CartonClosingStatusRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(db, current_user, "carton_procurement:closing_manage", payload.factory_id)
    if payload.status == "LOCKED":
        _ensure_permission(db, current_user, "carton_procurement:order_adjust", payload.factory_id)
    return closing_out(db, update_closing_status(db, closing_id, payload, current_user))


@router.post("/closings/{closing_id}/unlock", response_model=CartonClosingOut)
def post_closing_unlock(
    closing_id: str, payload: CartonClosingUnlockRequest,
    db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(db, current_user, "carton_procurement:closing_manage", payload.factory_id)
    _ensure_permission(db, current_user, "carton_procurement:order_adjust", payload.factory_id)
    return closing_out(db, unlock_closing(db, closing_id, payload, current_user))


@router.post("/inventory/movements/{movement_id}/price-confirmation", status_code=204)
def post_inventory_price_confirmation(
    movement_id: str,
    payload: CartonInventoryPriceConfirmRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(db, current_user, "carton_procurement:closing_manage", payload.factory_id)
    confirm_inventory_price(db, movement_id, payload, current_user)
