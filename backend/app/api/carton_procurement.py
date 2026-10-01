from typing import Literal
from datetime import datetime
from decimal import Decimal
from fastapi.encoders import jsonable_encoder
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from contextlib import contextmanager
from urllib.parse import quote as url_quote

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.services import carton_file_jobs as file_jobs
from app.schemas.carton_order_split import SplitCreate, SplitAction, SplitReceiptPreview
from app.services import carton_order_split as order_splits
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
    CartonExceptionBulkUpdate,
    CartonReplenishmentCreate,
    CartonReplenishmentOut,
    CartonImportBatchOut,
    CartonImportBatchUndoRequest,
    CartonScheduleOrderMarkRequest,
    CartonScheduleOrderMarkBulkRequest,
    CartonHistoryOrderBulkDeleteRequest,
    CartonOrderBulkDeleteRequest,
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
    closing_outputs,
    create_customer,
    create_import_batch,
    schedule_order_state,
    set_schedule_order_mark,
    set_schedule_order_marks,
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
from app.services.carton_procurement_history_import import import_history_orders, preview_history_orders
from app.services.carton_procurement_history_inventory import import_history_inventory, preview_history_inventory
from app.core.time import business_now
from app.services.carton_purchase_batches import load_purchase_batch


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
    if permission == "carton_procurement:customer_manage" and any(
        has_permission_in_scope(user, "carton_procurement:master_manage", factory_id, department)
        for department in CARTON_DEPARTMENTS
    ):
        return factory_id
    if any(
        has_permission_in_scope(user, permission, factory_id, department)
        for department in CARTON_DEPARTMENTS
    ):
        return factory_id
    ensure_permission_in_scope(db, user, permission, factory_id, CARTON_DEPARTMENTS[0])
    return factory_id


def _ensure_order_adjustment_permission(db: Session, user: AuthContext, factory_id: str) -> None:
    factory_id = require_carton_factory(factory_id)
    if any(
        has_permission_in_scope(user, "carton_procurement:order_adjust", factory_id, department)
        for department in CARTON_DEPARTMENTS
    ):
        return
    # Warehouse order adjustments do not grant supervisor-only stocktake/closing rights.
    for permission in ("order_write", "inventory_write"):
        _ensure_permission(db, user, f"carton_procurement:{permission}", factory_id)


def _ensure_order_deletion_permission(db: Session, user: AuthContext, factory_id: str) -> None:
    # Deletion requires the supervisor adjustment entitlement itself. The warehouse
    # order_write + inventory_write fallback used by append/reduce does not apply.
    for permission in ("order_write", "order_adjust"):
        _ensure_permission(db, user, f"carton_procurement:{permission}", factory_id)


@router.get("/orders/{order_no}/splits")
def get_order_splits(order_no: str, factory_id: str, db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    _ensure_permission(db, current_user, "carton_procurement:read", factory_id)
    return order_splits.context(db, factory_id, order_no)


@router.post("/orders/{order_no}/splits", status_code=201)
def post_order_split(order_no: str, payload: SplitCreate, db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    _ensure_permission(db, current_user, "carton_procurement:order_write", payload.factory_id)
    _ensure_order_adjustment_permission(db, current_user, payload.factory_id)
    return order_splits.create(db, order_no, payload, current_user)


@router.post("/order-splits/{split_id}/confirm")
def confirm_order_split(split_id: str, payload: SplitAction, db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    for permission in ("read", "receipt_write", "inventory_write"):
        _ensure_permission(db, current_user, f"carton_procurement:{permission}", payload.factory_id)
    return order_splits.act(db, split_id, payload, current_user)


@router.post("/order-splits/{split_id}/cancel")
def cancel_order_split(split_id: str, payload: SplitAction, db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    _ensure_permission(db, current_user, "carton_procurement:order_write", payload.factory_id)
    _ensure_order_adjustment_permission(db, current_user, payload.factory_id)
    from app.services.carton_procurement import _lock_receipt_factory
    _lock_receipt_factory(db, payload.factory_id)
    plan = next((row for row in order_splits.plans(db, payload.factory_id) if row["id"] == split_id), None)
    if plan and plan["pairs"]:
        _ensure_permission(db, current_user, "carton_procurement:inventory_write", payload.factory_id)
    return order_splits.act(db, split_id, payload, current_user, cancel=True)


@router.post("/order-splits/receipt-preview")
def preview_receipt_split(payload: SplitReceiptPreview, db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    _ensure_permission(db, current_user, "carton_procurement:read", payload.factory_id)
    from app.services.carton_procurement import _lock_receipt_factory
    _lock_receipt_factory(db, payload.factory_id)
    return order_splits.receipt_preview(db, payload.factory_id, [line.model_dump() for line in payload.lines])


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
    customer_name: str = Query(default="", max_length=128),
    order_from: str = Query(default="", pattern=r"^$|^\d{4}-\d{2}-\d{2}$"),
    order_to: str = Query(default="", pattern=r"^$|^\d{4}-\d{2}-\d{2}$"),
    due_filter: Literal["ALL", "OVERDUE", "TODAY", "DUE_SOON", "UPCOMING"] = "ALL",
    sort: Literal["ORDER_DESC", "DUE_ASC", "DUE_DESC"] = "ORDER_DESC",
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(db, current_user, "carton_procurement:read", factory_id)
    statistics = {}
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
        customer_name=customer_name, order_from=order_from, order_to=order_to, due_filter=due_filter, sort=sort,
        statistics=statistics,
    )
    from app.services.carton_order_projection import order_page_out
    return CartonOrderListOut(factory_id=factory_id, total=total, limit=limit,
        offset=offset, items=order_page_out(db, items), statistics=statistics)


@router.get("/schedule-orders")
def get_schedule_orders(factory_id: str, offset: int = Query(0, ge=0), limit: int = Query(500, ge=1, le=500),
                        db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    from sqlalchemy import select, func
    from app.models.carton_procurement import CartonOrder
    factory_id = _ensure_permission(db, user, "carton_procurement:read", factory_id)
    query = select(CartonOrder).where(CartonOrder.factory_id == factory_id, CartonOrder.deleted_at.is_(None))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    orders = list(db.scalars(query.order_by(CartonOrder.id).offset(offset).limit(limit)))
    fields = ("id", "factory_id", "order_no", "customer_code", "customer_name", "contract_no", "item_no",
              "customer_po", "status", "product_order_quantity", "product_name", "customer_due_date")
    identifiers = {order.id for order in orders}
    splits = {}
    for plan in order_splits.plans(db, factory_id):
        if plan["order_id"] in identifiers:
            splits.setdefault(plan["order_id"], []).append(plan)
    return {"items": [{**{key: getattr(order, key) for key in fields},
                       "split_records": splits.get(order.id, [])} for order in orders], "total": total}


@router.post("/orders/selection")
def read_selected_orders(payload: CartonOrderSelectionRequest, db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    from sqlalchemy import select
    from app.models.carton_procurement import CartonOrder
    from app.services.carton_order_projection import order_page_out
    factory = _ensure_permission(db, current_user, "carton_procurement:read", payload.factory_id)
    orders = list(db.scalars(select(CartonOrder).where(CartonOrder.factory_id == factory,
        CartonOrder.deleted_at.is_(None), CartonOrder.order_no.in_(payload.order_nos))))
    return {"items": order_page_out(db, orders)}


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
        _ensure_order_adjustment_permission(db, current_user, payload.factory_id)
    return order_out(db, append_order(db, order_no, payload, current_user))


@router.post("/orders/{order_no}/replenish", response_model=CartonReplenishmentOut, status_code=201)
def post_order_replenish(
    order_no: str,
    payload: CartonReplenishmentCreate,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    from app.services.carton_replenishment import replenish_order
    for permission in ("order_write", "inventory_write"):
        _ensure_permission(db, current_user, f"carton_procurement:{permission}", payload.factory_id)
    return replenish_order(db, order_no, payload, current_user)


@router.post("/orders/{order_no}/reduce", response_model=CartonOrderOut)
def post_order_reduce(
    order_no: str,
    payload: CartonOrderReduceRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_order_adjustment_permission(db, current_user, payload.factory_id)
    return order_out(db, reduce_order(db, order_no, payload, current_user))


@router.post("/orders/bulk-delete", status_code=204)
def post_orders_bulk_delete(
    payload: CartonOrderBulkDeleteRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    from app.services.carton_procurement import bulk_delete_orders
    _ensure_order_deletion_permission(db, current_user, payload.factory_id)
    bulk_delete_orders(db, payload, current_user)


@router.post("/orders/{order_no}/delete", status_code=204)
def post_order_delete(
    order_no: str,
    payload: CartonOrderCancelRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    from app.services.carton_procurement import delete_order
    _ensure_order_deletion_permission(db, current_user, payload.factory_id)
    delete_order(db, order_no, payload, current_user)


@router.post("/orders/bulk-delete-history", status_code=204)
def post_orders_bulk_delete_history(
    payload: CartonHistoryOrderBulkDeleteRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    from app.services.carton_procurement import bulk_delete_history_orders
    _ensure_order_deletion_permission(db, current_user, payload.factory_id)
    bulk_delete_history_orders(db, payload, current_user)


@router.post("/orders/{order_no}/delete-history", status_code=204)
def post_order_delete_history(
    order_no: str,
    payload: CartonOrderCancelRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    from app.services.carton_procurement import delete_history_order
    _ensure_order_deletion_permission(db, current_user, payload.factory_id)
    delete_history_order(db, order_no, payload, current_user)


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
def post_history_order_import(
    factory_id: str,
    file: UploadFile = File(...),
    expected_preview_fingerprint: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(
        db, current_user, "carton_procurement:order_write", factory_id
    )
    with _isolated_sheet_upload(db, file, factory_id, current_user, "carton_procurement:order_write") as (content, current_user):
        return import_history_orders(db, factory_id, file.filename or "history-orders.xlsx", content,
            current_user, expected_preview_fingerprint=expected_preview_fingerprint)


@router.post("/history-orders/preview")
def post_history_order_preview(
    factory_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(db,current_user,"carton_procurement:order_write",factory_id)
    with _isolated_sheet_upload(db, file, factory_id, current_user, "carton_procurement:order_write") as (content, _):
        return preview_history_orders(db,factory_id,file.filename or "history-orders.xlsx",content)


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
    issue = create_purchase_order_issue(db, order, payload.expected_revision, current_user, reuse_initial=True)
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
    orders = _export_order_snapshot(db, factory_id, payload.order_nos)
    db.rollback()
    content = file_jobs.run_file_job("combined_export", orders, generated_at)
    file_name = f"纸箱累计对账表_{generated_at.strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(
        BytesIO(content),
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{url_quote(file_name)}"},
    )


def _export_order_snapshot(db, factory, numbers):
    from collections import defaultdict
    from sqlalchemy import select
    from app.models.carton_procurement import CartonOrder, CartonOrderLine
    orders = {order.order_no: order for order in db.scalars(select(CartonOrder).where(
        CartonOrder.factory_id == factory, CartonOrder.deleted_at.is_(None), CartonOrder.order_no.in_(numbers)))}
    if any(number not in orders for number in numbers):
        raise HTTPException(404, "部分订单不存在或不属于当前厂区，请刷新后重试")
    lines = defaultdict(list)
    def snapshot(record):
        return SimpleNamespace(**{column.name: getattr(record, column.name) for column in record.__table__.columns})
    for line in db.scalars(select(CartonOrderLine).where(CartonOrderLine.order_id.in_([order.id for order in orders.values()])).order_by(CartonOrderLine.line_no)):
        lines[line.order_id].append(snapshot(line))
    return [(snapshot(orders[number]), lines[orders[number].id]) for number in numbers]


@router.post("/file-jobs/exports", status_code=202)
def start_export_job(payload: CartonOrderSelectionRequest, db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    factory = _ensure_permission(db, current_user, "carton_procurement:read", payload.factory_id)
    snapshot = _export_order_snapshot(db, factory, payload.order_nos)
    generated = business_now()
    db.rollback()
    return file_jobs.start_job(current_user.id, factory, "combined_export", (snapshot, generated),
        {"filename": f"纸箱累计对账表_{generated.strftime('%Y%m%d_%H%M%S')}.xlsx"})


@router.get("/file-jobs/{job_id}/download")
def download_export_job(job_id: str, factory_id: str, db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    _ensure_permission(db, current_user, "carton_procurement:read", factory_id)
    job = file_jobs.get_job(job_id, current_user.id, factory_id)
    if job.operation != "combined_export":
        raise HTTPException(422, "此任务不是导出任务")
    with file_jobs.result(job) as (content, _):
        job.status = "COMPLETED"
        return StreamingResponse(BytesIO(content), media_type=XLSX_MEDIA_TYPE,
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{url_quote(job.metadata['filename'])}"})


@router.get("/purchase-order-batches/{batch_id}.xlsx")
def get_purchase_order_batch_workbook(
    batch_id: str,
    factory_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(db, current_user, "carton_procurement:read", factory_id)
    batch, issues = load_purchase_batch(db, factory_id, batch_id)
    content = build_purchase_order_issue_batch_workbook(
        issues, generated_at=datetime.fromisoformat(batch["generated_at"]),
        batch_document_no=batch["document_no"],
    )
    return StreamingResponse(BytesIO(content), media_type=XLSX_MEDIA_TYPE, headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{url_quote(batch['document_no'] + '_合并采购单.xlsx')}",
        "X-Purchase-Order-Document-No": batch["document_no"],
    })


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


def _read_carton_upload(file):
    from app.services.carton_procurement import MAX_IMPORT_BYTES, ALLOWED_IMPORT_SUFFIXES
    if Path(file.filename or "").suffix.lower() not in ALLOWED_IMPORT_SUFFIXES | {".xlsm"}:
        raise HTTPException(422, "仅支持 Excel、PDF、PNG、JPG 或 HEIC 文件")
    content = file.file.read(MAX_IMPORT_BYTES + 1)
    if not content:
        raise HTTPException(422, "导入文件不能为空")
    if len(content) > MAX_IMPORT_BYTES:
        raise HTTPException(413, "导入文件不能超过 20 MB")
    return content


@contextmanager
def _isolated_sheet_upload(db, file, factory, user, permission):
    from app.services.carton_procurement_imports import prepared_sheets
    from app.services.auth import build_auth_context, get_authenticated_user
    content = _read_carton_upload(file)
    db.rollback()
    sheets = file_jobs.run_file_job("sheets", file.filename or "", content)
    user = build_auth_context(db, get_authenticated_user(db, user))
    _ensure_permission(db, user, permission, factory)
    with prepared_sheets(Path(file.filename or "").name, content, sheets):
        yield content, user


def _isolated_import(db, factory, kind, file, user, profile=None):
    content = _read_carton_upload(file)
    db.rollback()  # Release the read-only authorization connection before CPU work.
    parsed = file_jobs.run_file_job("parse", kind, file.filename or "", content)
    # Permission is checked again after a possibly long file operation.
    from app.services.auth import build_auth_context, get_authenticated_user
    user = build_auth_context(db, get_authenticated_user(db, user))
    _ensure_permission(db, user, "carton_procurement:import", factory)
    return create_import_batch(db, factory, kind, file, content, user,
        import_profile=profile, parsed_source=parsed)


@router.post("/file-jobs/imports", status_code=202)
def start_import_job(
    factory_id: str,
    import_type: Literal["WEEKLY_SCHEDULE", "INSPECTION_SCHEDULE", "DELIVERY_NOTE"],
    file: UploadFile = File(...), customer_code: str = Form(default="", max_length=64),
    advance_days: int = Query(default=3, ge=0, le=30),
    db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(db, current_user, "carton_procurement:import", factory_id)
    if import_type == "WEEKLY_SCHEDULE":
        from app.services.carton_procurement import get_active_customer
        customer_code = get_active_customer(db, factory_id, customer_code).customer_code
    content = _read_carton_upload(file)
    profile = {"customer_code": customer_code} if import_type == "WEEKLY_SCHEDULE" else {"advance_days": advance_days} if import_type == "INSPECTION_SCHEDULE" else {}
    metadata = {"filename": file.filename, "content_type": file.content_type, "profile": profile}
    db.rollback()
    return file_jobs.start_job(current_user.id, factory_id, "parse",
        (import_type, file.filename or "", content), metadata)


@router.get("/file-jobs/{job_id}")
def read_file_job(job_id: str, factory_id: str, db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    _ensure_permission(db, current_user, "carton_procurement:read", factory_id)
    return file_jobs.job_status(file_jobs.get_job(job_id, current_user.id, factory_id))


@router.post("/file-jobs/{job_id}/complete", response_model=CartonImportBatchOut)
def complete_import_job(job_id: str, factory_id: str, db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    _ensure_permission(db, current_user, "carton_procurement:import", factory_id)
    job = file_jobs.get_job(job_id, current_user.id, factory_id)
    if job.operation != "parse":
        raise HTTPException(422, "此任务不是导入任务")
    with file_jobs.result(job) as (parsed, args):
        if job.batch_id:
            return get_import_batch(db, factory_id, job.batch_id)
        kind, filename, content = args
        upload = SimpleNamespace(filename=filename, content_type=job.metadata["content_type"])
        batch = create_import_batch(db, factory_id, kind, upload, content, current_user,
            import_profile=job.metadata["profile"], parsed_source=parsed)
        job.batch_id, job.status = batch.id, "COMPLETED"
        return batch


@router.post("/receipt-imports", response_model=CartonImportBatchOut, status_code=201)
def post_receipt_import(
    factory_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(db, current_user, "carton_procurement:import", factory_id)
    return _isolated_import(db, factory_id, "DELIVERY_NOTE", file, current_user)


@router.post("/weekly-imports", response_model=CartonImportBatchOut, status_code=201)
def post_weekly_import(
    factory_id: str,
    customer_code: str = Form(..., min_length=1, max_length=64),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(db, current_user, "carton_procurement:import", factory_id)
    return _isolated_import(db, factory_id, "WEEKLY_SCHEDULE", file, current_user, {"customer_code": customer_code})


@router.get("/schedule-order-marks")
def get_schedule_order_marks(
    factory_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(db, current_user, "carton_procurement:read", factory_id)
    return schedule_order_state(db, factory_id)


@router.post("/schedule-order-marks")
def post_schedule_order_mark(
    payload: CartonScheduleOrderMarkRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(db, current_user, "carton_procurement:import", payload.factory_id)
    return set_schedule_order_mark(
        db, factory_id, payload.batch_id, payload.source_sheet,
        payload.source_row, payload.marked, current_user,
    )


@router.post("/schedule-order-marks/bulk")
def post_schedule_order_marks_bulk(
    payload: CartonScheduleOrderMarkBulkRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(db, current_user, "carton_procurement:import", payload.factory_id)
    return set_schedule_order_marks(
        db, factory_id, payload.batch_id,
        [(row.source_sheet, row.source_row) for row in payload.rows],
        payload.marked, current_user,
    )


@router.post("/inspection-imports", response_model=CartonImportBatchOut, status_code=201)
def post_inspection_import(
    factory_id: str,
    advance_days: int = Query(default=3, ge=0, le=30),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(db, current_user, "carton_procurement:import", factory_id)
    return _isolated_import(db, factory_id, "INSPECTION_SCHEDULE", file, current_user, {"advance_days": advance_days})


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


@router.post("/imports/{batch_id}/undo", response_model=CartonImportBatchOut)
def post_import_undo(
    batch_id: str,
    payload: CartonImportBatchUndoRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    from app.services.carton_procurement import undo_schedule_import
    _ensure_permission(db, current_user, "carton_procurement:import", payload.factory_id)
    return undo_schedule_import(db, batch_id, payload, current_user)


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


@router.post("/exceptions/bulk-update", response_model=list[CartonExceptionOut])
def post_exceptions_bulk_update(
    payload: "CartonExceptionBulkUpdate",
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    from app.services.carton_procurement import _lock_receipt_factory
    _ensure_permission(db, current_user, "carton_procurement:exception_manage", payload.factory_id)
    _lock_receipt_factory(db, require_carton_factory(payload.factory_id))
    if len({item.id for item in payload.items}) != len(payload.items):
        raise HTTPException(422, "异常选择不能重复")
    rows = [update_exception(db, item.id, CartonExceptionUpdate(
        factory_id=payload.factory_id, expected_revision=item.expected_revision,
        status=payload.status, resolution_note=payload.resolution_note,
    ), current_user, commit=False) for item in payload.items]
    db.commit()
    return rows


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
    from app.services.carton_procurement import _lock_receipt_factory
    from app.services.carton_inventory_money import annotate_movements
    _lock_receipt_factory(db, factory_id)
    total, items = list_movements(
        db,
        factory_id,
        customer_code=customer_code.strip(),
        search=search.strip(),
        limit=limit,
        offset=offset,
    )
    items = annotate_movements(db, factory_id, items)
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
def post_history_inventory_import(
    factory_id: str,
    file: UploadFile = File(...),
    options: str | None = Form(default=None),
    expected_preview_fingerprint: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(
        db, current_user, "carton_procurement:inventory_write", factory_id
    )
    with _isolated_sheet_upload(db, file, factory_id, current_user, "carton_procurement:inventory_write") as (content, current_user):
        return import_history_inventory(db, factory_id, file.filename or "history-inventory.xlsx", content,
            current_user, options=options, expected_preview_fingerprint=expected_preview_fingerprint)


@router.post("/inventory/history-imports/preview")
def post_history_inventory_preview(
    factory_id: str,
    file: UploadFile = File(...),
    options: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id=_ensure_permission(db,current_user,"carton_procurement:inventory_write",factory_id)
    with _isolated_sheet_upload(db, file, factory_id, current_user, "carton_procurement:inventory_write") as (content, _):
        return preview_history_inventory(db,factory_id,file.filename or "history-inventory.xlsx",content,options=options)


@router.get("/stocktakes")
def stocktakes_list(factory_id: str, limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0),
                    status: Literal["", "DRAFT", "SUBMITTED", "POSTED", "CANCELLED"] = "",
                    db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    _ensure_permission(db, user, "carton_procurement:read", factory_id)
    return list_stocktakes(db, factory_id, limit, offset, status)


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
    from app.services.carton_procurement import _lock_receipt_factory
    from app.services.carton_inventory_money import annotate_balances
    _lock_receipt_factory(db, factory_id)
    rows = annotate_balances(db, factory_id, inventory_balances(db, factory_id))
    return [row for row in rows if not customer_code.strip() or row.customer_code == customer_code.strip()]


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
    return closing_outputs(db, rows)


@router.post("/closings/generate", response_model=list[CartonClosingOut])
def post_closing_generation(
    payload: CartonClosingGenerateRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(db, current_user, "carton_procurement:closing_manage", payload.factory_id)
    return closing_outputs(db, generate_closings(db, payload, current_user))


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


from app.schemas.carton_positions import LocationCreate, PositionTransfer
from app.services import carton_positions as position_service

@router.get("/inventory/locations")
def get_carton_locations(factory_id: str, db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    factory_id = _ensure_permission(db, current_user, "carton_procurement:read", factory_id)
    return position_service.locations(db, factory_id)

@router.post("/inventory/locations", status_code=201)
def post_carton_location(payload: LocationCreate, db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    payload.factory_id = _ensure_permission(db, current_user, "carton_procurement:read", payload.factory_id)
    from app.services.carton_master import require_manage
    from app.services.carton_procurement import _lock_receipt_factory, _audit
    _lock_receipt_factory(db, payload.factory_id)
    require_manage(db, current_user, payload.factory_id, payload.warehouse)
    row = position_service.create_location(db, payload.factory_id, payload.warehouse, payload.bin_code)
    _audit(db, current_user, payload.factory_id, "INVENTORY_LOCATION_CREATED", "carton_location", row.id, {**position_service.location_out(row), "reason": payload.reason})
    db.commit()
    return position_service.location_out(row)

@router.get("/inventory/positions", response_model=list[CartonInventoryBalanceOut])
def get_carton_positions(factory_id: str, customer_code: str = "", db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    factory_id = _ensure_permission(db, current_user, "carton_procurement:read", factory_id)
    from app.services.carton_procurement import _lock_receipt_factory
    from app.services.carton_inventory_money import annotate_balances
    _lock_receipt_factory(db, factory_id)
    rows = annotate_balances(db, factory_id, position_service.position_balances(db, factory_id))
    return [row for row in rows if not customer_code.strip() or row.customer_code == customer_code.strip()]

@router.post("/inventory/transfers")
def post_carton_transfer(payload: PositionTransfer, db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    payload.factory_id = _ensure_permission(db, current_user, "carton_procurement:inventory_write", payload.factory_id)
    return position_service.transfer(db, payload, current_user)


from app.services import carton_master as master_service
from app.schemas.carton_master import MasterSave, MasterImportResult, LocationUpdate, WarehouseCreate, WarehouseRename, WarehouseDelete
from app.services import carton_master_import as master_import_service


@router.get("/master-data/import/{kind}/template")
def get_master_import_template(kind: Literal["paper-options", "configurations", "locations"], factory_id: str,
                               db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    factory_id = _ensure_permission(db, current_user, "carton_procurement:read", factory_id)
    master_service.require_manage(db, current_user, factory_id)
    filename = {"paper-options": "纸品选项导入模板.xlsx", "configurations": "货号与包装导入模板.xlsx", "locations": "仓库仓位导入模板.xlsx"}[kind]
    return StreamingResponse(BytesIO(master_import_service.template(kind)),
                             media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f"attachment; filename=master-template.xlsx; filename*=UTF-8''{url_quote(filename)}"})


@router.post("/master-data/import/{kind}/{action}", response_model=MasterImportResult)
def post_master_import(kind: Literal["paper-options", "configurations", "locations"], action: Literal["preview", "apply"],
                             factory_id: str = Form(...), file: UploadFile = File(...), preview_token: str = Form(""),
                             db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    factory_id = _ensure_permission(db, current_user, "carton_procurement:read", factory_id)
    master_service.require_manage(db, current_user, factory_id)
    content = file.file.read(master_import_service.MAX_BYTES + 1)
    if action == "apply" and not preview_token:
        raise HTTPException(422, "请先预览并确认导入")
    db.rollback()
    parsed = file_jobs.run_file_job("master_parse", content, file.filename or "", kind)
    from app.services.auth import build_auth_context, get_authenticated_user
    current_user = build_auth_context(db, get_authenticated_user(db, current_user))
    _ensure_permission(db, current_user, "carton_procurement:read", factory_id)
    return master_import_service.run(db, current_user, factory_id, kind, content, file.filename or "",
                                     expected=preview_token if action == "apply" else None, parsed=parsed)

@router.get("/master-data")
def get_master_data(factory_id: str, db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    factory_id = _ensure_permission(db, current_user, "carton_procurement:read", factory_id)
    return master_service.workspace(db, factory_id, current_user)

@router.post("/master-data", status_code=201)
def post_master_data(payload: MasterSave, db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    payload.factory_id = _ensure_permission(db, current_user, "carton_procurement:read", payload.factory_id)
    return master_service.save_record(db, current_user, payload)

@router.patch("/master-data/{record_id}")
def patch_master_data(record_id: str, payload: MasterSave, db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    payload.factory_id = _ensure_permission(db, current_user, "carton_procurement:read", payload.factory_id)
    return master_service.save_record(db, current_user, payload, record_id)

@router.patch("/inventory/locations/{location_id}")
def patch_master_location(location_id: str, payload: LocationUpdate, db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    payload.factory_id = _ensure_permission(db, current_user, "carton_procurement:read", payload.factory_id)
    return master_service.update_location(db, current_user, location_id, payload)


@router.post("/inventory/warehouses", status_code=201)
def post_carton_warehouse(payload: WarehouseCreate, db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    payload.factory_id = _ensure_permission(db, current_user, "carton_procurement:read", payload.factory_id)
    return master_service.save_warehouse(db, current_user, payload)


@router.patch("/inventory/warehouses")
def rename_carton_warehouse(payload: WarehouseRename, db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    payload.factory_id = _ensure_permission(db, current_user, "carton_procurement:read", payload.factory_id)
    return master_service.save_warehouse(db, current_user, payload, rename=True)


@router.post("/inventory/warehouses/delete")
def delete_carton_warehouse(payload: WarehouseDelete, db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    payload.factory_id = _ensure_permission(db, current_user, "carton_procurement:read", payload.factory_id)
    return master_service.delete_warehouse(db, current_user, payload)
