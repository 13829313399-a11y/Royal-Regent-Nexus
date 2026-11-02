from app.schemas.carton_order_groups import OrderGroupCreate
from app.schemas.carton_contract_merge import ContractMerge
from typing import Literal
from datetime import date, datetime
from decimal import Decimal
from fastapi.encoders import jsonable_encoder
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from contextlib import contextmanager
from urllib.parse import quote as url_quote

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.carton_customer_assignment import CartonCustomerAssignmentSave, CartonCustomerClaim
from app.services import carton_file_jobs as file_jobs
from app.services import carton_opening_batches as opening_batches
from app.schemas.carton_order_split import SplitCreate, SplitAction, SplitReceiptPreview
from app.services import carton_order_split as order_splits
from app.schemas.carton_inventory_report import CartonInventoryReportOut
from app.services.carton_inventory_report import inventory_report
from app.schemas.carton_order_timeline import CartonOrderTimelineOut
from app.services.carton_order_timeline import order_timeline
from app.schemas.carton_stocktake import StocktakeCreate, StocktakeAction, StocktakePolicyUpdate
from app.services.carton_stocktake import create_stocktake, stocktake_detail, list_stocktakes, act_stocktake
from app.services.carton_procurement import audit_query_options, supplier_promise_changes, supplier_promise_notices, promise_notice_acks, acknowledge_promise_notice
from app.schemas.carton_procurement import (
    PromiseNoticeAck,
    CartonAuditEventListOut,
    CartonAuditEventOut,
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
    CartonOrderReturnRequest,
    CartonOrderCreate,
    CartonOrderDatesRequest,
    CartonOrderRushRequest,
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
    create_order_response,
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
    update_order_dates,
    set_order_rush,
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


@router.get("/customer-responsibilities")
def get_customer_responsibilities(factory_id: str, summary: bool = False, db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    from app.services import carton_customer_assignment as responsibilities
    factory_id = _ensure_permission(db, current_user, "carton_procurement:read", factory_id)
    return responsibilities.workspace(db, current_user, factory_id, summary=summary)


@router.put("/customers/{customer_id}/responsibilities")
def put_customer_responsibilities(customer_id: str, payload: CartonCustomerAssignmentSave,
                                  db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    from app.services import carton_customer_assignment as responsibilities
    _ensure_permission(db, current_user, "carton_procurement:read", payload.factory_id)
    return responsibilities.save(db, current_user, customer_id, payload)


@router.post("/customers/{customer_id}/claim")
def claim_customer(customer_id: str, payload: CartonCustomerClaim,
                   db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    from app.services import carton_customer_assignment as responsibilities
    _ensure_permission(db, current_user, "carton_procurement:read", payload.factory_id)
    return responsibilities.claim(db, current_user, customer_id, payload)


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
    # Warehouse deletion uses existing scoped operating permissions without granting
    # supervisor privileges or bypassing the service's customer responsibility check.
    _ensure_permission(db, user, "carton_procurement:order_write", factory_id)
    _ensure_order_adjustment_permission(db, user, factory_id)


@router.get("/orders/{order_no}/splits")
def get_order_splits(order_no: str, factory_id: str, db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    _ensure_permission(db, current_user, "carton_procurement:read", factory_id)
    order = get_order_by_no(db, factory_id, order_no)
    from app.services.carton_customer_assignment import ensure_customer_operation
    ensure_customer_operation(db, current_user, factory_id, order.customer_code)
    return order_splits.context(db, factory_id, order_no)


@router.post("/orders/{order_no}/splits", status_code=201)
def post_order_split(order_no: str, payload: SplitCreate, db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    _ensure_permission(db, current_user, "carton_procurement:order_write", payload.factory_id)
    _ensure_order_adjustment_permission(db, current_user, payload.factory_id)
    raise HTTPException(409, "旧数量归属拆单已停用，请刷新页面，通过订单拆分建立独立子订单")


@router.post("/order-splits/{split_id}/confirm")
def confirm_order_split(split_id: str, payload: SplitAction, db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    for permission in ("read", "receipt_write", "inventory_write"):
        _ensure_permission(db, current_user, f"carton_procurement:{permission}", payload.factory_id)
    raise HTTPException(409, "旧库存归属拆单不再新增过账，请核对历史记录并使用独立订单拆分")


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


@router.post("/customers/business-sync")
def sync_business_customers(factory_id: str, request: Request, db: Session = Depends(get_db),
                            current_user: AuthContext = Depends(get_current_user)):
    # Narrow derived-data operation: only server-owned names for this factory.
    # Free-form creation/edit/delete still requires customer_manage.
    from app.services.carton_special_requests import locked_actor
    from app.services.carton_business_customers import synchronize
    factory_id = _ensure_permission(db, current_user, "carton_procurement:read", factory_id)
    locked_actor(db, current_user, factory_id)
    actor = get_current_user(request, db)
    _ensure_permission(db, actor, "carton_procurement:read", factory_id)
    try:
        added = synchronize(db, factory_id, actor)
        db.commit()
    except BaseException:
        db.rollback()
        raise
    return {"factory_id": factory_id, "added": added}


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


@router.get("/dashboard/workspace")
def get_dashboard_workspace(
    factory_id: str,
    customer: str = Query("", max_length=128), search: str = Query("", max_length=128),
    status: Literal["OPEN", "ALL"] = "OPEN",
    kind: Literal["ALL", "ACTIONABLE", "TIMING", "REDUCTION", "MISSING_ORDER", "NEW_ORDER", "QUANTITY_INCREASE", "QUANTITY_DECREASE", "QUANTITY_REVIEW", "SCHEDULE_CANCELLED", "CANCELLED_AFTER_ORDER"] = "ALL",
    offset: int = Query(0, ge=0), limit: int = Query(8, ge=1, le=50),
    db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user),
):
    from app.services.carton_dashboard import workspace
    factory_id = _ensure_permission(db, current_user, "carton_procurement:read", factory_id)
    return workspace(db, factory_id, customer=customer, search=search, status=status, kind=kind, offset=offset, limit=limit)


@router.get("/dashboard/alert-context")
def get_dashboard_alert_context(
    factory_id: str, alert_id: str = Query(..., min_length=1, max_length=4096),
    db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user),
):
    from app.services.carton_dashboard import alert_context
    factory_id = _ensure_permission(db, current_user, "carton_procurement:read", factory_id)
    return alert_context(db, factory_id, alert_id)


@router.get("/orders", response_model=CartonOrderListOut)
def get_orders(
    factory_id: str,
    responsibility_scope: Literal["OWN", "ALL"] = "OWN",
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
    collaboration_filter: Literal["ALL", "NOT_ISSUED", "PENDING_CHANGE", "PENDING", "PARTIAL", "ACCEPTED", "NOT_REQUIRED", "CANCELLED", "LATE_PROMISE"] = "ALL",
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
        statistics=statistics, collaboration_filter=collaboration_filter, user=current_user if responsibility_scope == "OWN" else None,
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
    from app.services.carton_order_split_trace import schedule_split_sources
    split_sources = schedule_split_sources(db, orders)
    return {"items": [{**{key: getattr(order, key) for key in fields},
                       "split_records": splits.get(order.id, []),
                       "schedule_split_source": split_sources.get(order.id)} for order in orders], "total": total}


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


@router.post("/order-groups/convert", response_model=list[CartonOrderOut], status_code=201)
def convert_order_group(payload: OrderGroupCreate, request: Request, db: Session = Depends(get_db),
                        current_user: AuthContext = Depends(get_current_user)):
    from app.services.carton_order_groups import create
    _ensure_permission(db, current_user, "carton_procurement:order_write", payload.factory_id)
    return create(db, payload, current_user,
        refresh_user=lambda: get_current_user(request=request, db=db),
        authorize=lambda user: _ensure_permission(db, user, "carton_procurement:order_write", payload.factory_id))


@router.post("/orders/merge-contract", response_model=list[CartonOrderOut])
def merge_order_contract(payload: ContractMerge, request: Request, db: Session = Depends(get_db),
                         current_user: AuthContext = Depends(get_current_user)):
    from app.services.carton_contract_merge import merge
    _ensure_permission(db, current_user, "carton_procurement:order_write", payload.factory_id)
    return merge(db, payload, current_user,
        refresh_user=lambda: get_current_user(request=request, db=db),
        authorize=lambda user: _ensure_permission(db, user, "carton_procurement:order_write", payload.factory_id))


@router.post("/orders", response_model=CartonOrderOut, status_code=201)
def post_order(
    payload: CartonOrderCreate,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(db, current_user, "carton_procurement:order_write", payload.factory_id)
    return create_order_response(db, payload, current_user)


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


@router.post("/orders/{order_no}/dates", response_model=CartonOrderOut)
def post_order_dates(
    order_no: str,
    payload: CartonOrderDatesRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(db, current_user, "carton_procurement:order_write", payload.factory_id)
    from app.services.carton_procurement import _lock_receipt_factory
    _lock_receipt_factory(db, require_carton_factory(payload.factory_id))
    order = get_order_by_no(db, require_carton_factory(payload.factory_id), order_no)
    if order.status in {"PENDING_SUPPLIER", "PARTIALLY_RECEIVED"}:
        _ensure_order_adjustment_permission(db, current_user, payload.factory_id)
    return order_out(db, update_order_dates(db, order_no, payload, current_user))


@router.post("/orders/{order_no}/rush", response_model=CartonOrderOut)
def post_order_rush(
    order_no: str,
    payload: CartonOrderRushRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return order_out(db, set_order_rush(db, order_no, payload, current_user))


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
    payload: CartonOrderReturnRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    for permission in ("order_write", "inventory_write"):
        _ensure_permission(db, current_user, f"carton_procurement:{permission}", payload.factory_id)
    return order_out(db, return_order(db, order_no, payload, current_user))


@router.post("/orders/bulk-cancel", response_model=list[CartonOrderOut])
def post_orders_bulk_cancel(
    payload: CartonOrderBulkCancelRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(db, current_user, "carton_procurement:order_write", payload.factory_id)
    from app.services.carton_order_projection import order_page_out
    return order_page_out(db, bulk_cancel_orders(db, payload, current_user))


@router.post("/orders/bulk-submit-supplier", response_model=list[CartonOrderOut])
def post_orders_bulk_submit_supplier(
    payload: CartonOrderBulkSubmitRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(db, current_user, "carton_procurement:order_write", payload.factory_id)
    from app.services.carton_order_projection import order_page_out
    return order_page_out(db, bulk_submit_orders_to_supplier(db, payload, current_user))


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
    with _isolated_sheet_upload(db, file, factory_id, current_user, "carton_procurement:order_write") as (content, actor):
        return preview_history_orders(db,factory_id,file.filename or "history-orders.xlsx",content,actor)


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
        {"filename": f"纸箱累计对账表_{generated.strftime('%Y%m%d_%H%M%S')}.xlsx", "order_nos": payload.order_nos})


@router.get("/file-jobs/{job_id}/download")
def download_export_job(job_id: str, factory_id: str, db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    _ensure_permission(db, current_user, "carton_procurement:read", factory_id)
    job = file_jobs.get_job(job_id, current_user.id, factory_id)
    if job.operation != "combined_export":
        raise HTTPException(422, "此任务不是导出任务")
    _export_order_snapshot(db, factory_id, job.metadata.get("order_nos", []))
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
    responsibility_scope: Literal["OWN", "ALL"] = "OWN",
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
        offset=offset, user=current_user if responsibility_scope == "OWN" else None,
    )
    return CartonReceiptListOut(
        factory_id=factory_id,
        total=total,
        limit=limit,
        offset=offset,
        items=[receipt_out(db, item) for item in items],
    )


@router.get("/receipt-history")
def get_receipt_history(factory_id: str, responsibility_scope: Literal["OWN", "ALL"] = "OWN",
    business_kind: Literal["", "PURCHASE", "SAMPLE", "WORKSHOP_MISC", "SUPPLIER_GIFT", "LEGACY"] = "",
    customer_code: str = Query(default="", max_length=64), search: str = Query(default="", max_length=128),
    status_filter: Literal["", "PENDING_CONFIRMATION", "POSTED", "REVERSED"] = "",
    date_field: Literal["ACCEPTANCE", "DELIVERY"] = "ACCEPTANCE", date_from: str = "", date_to: str = "",
    sort: Literal["ASC", "DESC"] = "DESC", limit: int = Query(default=25, ge=1, le=100), offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    from app.services.carton_procurement import _receipt_lines
    factory_id = _ensure_permission(db, current_user, "carton_procurement:read", factory_id)
    total, rows = list_receipts(db, factory_id, user=current_user if responsibility_scope == "OWN" else None,
        customer_code=customer_code.strip(), search=search.strip(), status_filter=status_filter, date_field=date_field,
        date_from=date_from, date_to=date_to, sort=sort, limit=limit, offset=offset, business_kind=business_kind)
    items = []
    for row in rows:
        lines = _receipt_lines(db, row.id)
        from app.services.carton_source_links import receipt_sources
        items.append(dict(**receipt_sources(db, row, lines), id=row.id, receipt_no=row.receipt_no, delivery_note_no=row.delivery_note_no,
            delivery_date=row.delivery_date, acceptance_date=row.acceptance_date, status=row.status,
            confirmed_at=row.confirmed_at, operator=row.confirmed_by_name or row.created_by_name,
            line_count=len(lines), customers="、".join(dict.fromkeys(line.customer_name for line in lines))[:160],
            contracts="、".join(dict.fromkeys(line.contract_no for line in lines if line.contract_no))[:160]))
    return dict(items=items, total=total, limit=limit, offset=offset)


@router.get("/receipts/{receipt_id}", response_model=CartonReceiptOut)
def get_receipt_detail(receipt_id: str, factory_id: str, responsibility_scope: Literal["OWN", "ALL"] = "OWN",
    db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    factory_id = _ensure_permission(db, current_user, "carton_procurement:read", factory_id)
    _, rows = list_receipts(db, factory_id, receipt_id=receipt_id, user=current_user if responsibility_scope == "OWN" else None)
    if not rows:
        raise HTTPException(404, "收料单不存在或不在当前客户范围")
    return receipt_out(db, rows[0])


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
    scope_mode: str = Form(default="UNDECLARED", max_length=16), as_of_date: str = Form(default="", max_length=10),
    coverage_start: str = Form(default="", max_length=10), coverage_end: str = Form(default="", max_length=10),
    full_scope_confirmed: bool = Form(default=False),
    advance_days: int = Query(default=3, ge=0, le=30),
    db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_permission(db, current_user, "carton_procurement:import", factory_id)
    if import_type == "WEEKLY_SCHEDULE":
        from app.services.carton_procurement import get_active_customer
        customer_code = get_active_customer(db, factory_id, customer_code).customer_code
    content = _read_carton_upload(file)
    profile = {"customer_code": customer_code} if import_type == "WEEKLY_SCHEDULE" else {"advance_days": advance_days} if import_type == "INSPECTION_SCHEDULE" else {}
    if import_type == "WEEKLY_SCHEDULE":
        from app.services.carton_schedule_coverage import normalize_scope
        profile = normalize_scope(dict(profile, scope_mode=scope_mode, as_of_date=as_of_date,
            coverage_start=coverage_start, coverage_end=coverage_end, full_scope_confirmed=full_scope_confirmed))
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
            from app.services.carton_schedule_coverage import completed_batch
            return completed_batch(db, current_user, factory_id, job.batch_id)
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
    scope_mode: str = Form(default="UNDECLARED", max_length=16), as_of_date: str = Form(default="", max_length=10),
    coverage_start: str = Form(default="", max_length=10), coverage_end: str = Form(default="", max_length=10),
    full_scope_confirmed: bool = Form(default=False),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_permission(db, current_user, "carton_procurement:import", factory_id)
    from app.services.carton_schedule_coverage import normalize_scope
    profile = normalize_scope(dict(customer_code=customer_code, scope_mode=scope_mode, as_of_date=as_of_date,
        coverage_start=coverage_start, coverage_end=coverage_end, full_scope_confirmed=full_scope_confirmed))
    return _isolated_import(db, factory_id, "WEEKLY_SCHEDULE", file, current_user, profile)


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
        reason=payload.reason,
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
        reason=payload.reason,
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
    import_types: str = Query(default="", max_length=96),
    status: str = Query(default="", max_length=16),
    date_from: str = Query(default="", max_length=10),
    date_to: str = Query(default="", max_length=10),
    summary_only: bool = False,
    search: str = Query(default="", max_length=128),
    customer_code: str = Query(default="", max_length=64),
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
        import_types=import_types.strip(),
        status=status.strip(),
        date_from=date_from.strip(),
        date_to=date_to.strip(),
        summary_only=summary_only,
        search=search.strip(),
        customer_code=customer_code.strip(),
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
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    from app.services.carton_procurement import _lock_receipt_factory
    from app.services.identity_policy import lock_mutation
    from app.services.carton_stocktake_policy import require
    lock_mutation(db)
    _lock_receipt_factory(db, require_carton_factory(payload.factory_id))
    current_user = get_current_user(request=request, db=db)
    require(current_user, "carton_procurement:exception_manage", payload.factory_id)
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
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    from app.services.identity_policy import lock_mutation
    from app.services.carton_procurement import _lock_receipt_factory
    from app.services.carton_stocktake_policy import require
    lock_mutation(db)
    _lock_receipt_factory(db, require_carton_factory(payload.factory_id))
    current_user = get_current_user(request=request, db=db)
    require(current_user, "carton_procurement:exception_manage", payload.factory_id)
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


@router.get("/inventory/movement-history")
def get_inventory_movement_history(
    factory_id: str,
    customer_code: str = Query(default="", max_length=64),
    customer_name: str = Query(default="", max_length=255),
    search: str = Query(default="", max_length=128),
    movement_type: Literal["", "INBOUND", "OUTBOUND", "ADJUSTMENT", "REVERSAL"] = "",
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    from app.services.carton_procurement import _lock_receipt_factory
    from app.services.carton_inventory_history import inventory_movement_history
    factory_id = _ensure_permission(db, current_user, "carton_procurement:read", factory_id)
    _lock_receipt_factory(db, factory_id)
    return inventory_movement_history(db, factory_id, customer_code=customer_code.strip(),
        customer_name=customer_name.strip(), search=search.strip(), movement_type=movement_type, date_from=date_from, date_to=date_to,
        limit=limit, offset=offset)


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


@router.get("/inventory/history-imports/batches")
def opening_batches_list(factory_id: str, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
                         db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    factory = _ensure_permission(db, user, "carton_procurement:inventory_write", factory_id)
    from app.services.carton_procurement import _lock_receipt_factory
    _lock_receipt_factory(db, factory)
    return opening_batches.list_batches(db, factory, limit, offset)


@router.post("/inventory/history-imports/batches/{batch_id}/reversal-preview")
def opening_batch_reversal_preview(batch_id: str, factory_id: str, db: Session = Depends(get_db),
                                   user: AuthContext = Depends(get_current_user)):
    factory = _ensure_permission(db, user, "carton_procurement:inventory_write", factory_id)
    return opening_batches.preview_batch_reversal(db, factory, batch_id)


@router.post("/inventory/history-imports/batches/{batch_id}/reverse")
def opening_batch_reverse(batch_id: str, payload: opening_batches.OpeningBatchReversal,
                          db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    from app.services.auth import build_auth_context, get_authenticated_user
    actor = build_auth_context(db, get_authenticated_user(db, user))
    _ensure_permission(db, actor, "carton_procurement:inventory_write", payload.factory_id)
    return opening_batches.reverse_batch(db, batch_id, payload, actor)


@router.get("/stocktakes")
def stocktakes_list(factory_id: str, limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0),
                    status: Literal["", "DRAFT", "SUBMITTED", "POSTED", "CANCELLED"] = "",
                    date_from: str = "", date_to: str = "", sort: Literal["ASC", "DESC"] = "DESC",
                    db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    _ensure_permission(db, user, "carton_procurement:read", factory_id)
    return list_stocktakes(db, factory_id, limit, offset, status, date_from, date_to, sort)


@router.get("/stocktake-policy")
def stocktake_policy_get(factory_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    from app.services.carton_stocktake_policy import policy
    _ensure_permission(db, user, "carton_procurement:read", factory_id)
    return policy(db, factory_id)


@router.put("/stocktake-policy")
def stocktake_policy_put(payload: StocktakePolicyUpdate, request: Request,
                         db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    from app.services.carton_stocktake_policy import update_policy
    return update_policy(db, payload, user, refresh_user=lambda: get_current_user(request=request, db=db))


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
def stocktakes_action(identifier: str, payload: StocktakeAction, request: Request, db: Session = Depends(get_db),
                      user: AuthContext = Depends(get_current_user)):
    _ensure_permission(db, user, "carton_procurement:inventory_write", payload.factory_id)
    if payload.action in ("APPROVE", "RETURN", "CANCEL"):
        doc = stocktake_detail(db, payload.factory_id, identifier)
        if payload.action != "CANCEL" or doc["created_by"] != user.id:
            _ensure_permission(db, user, "carton_procurement:order_adjust", payload.factory_id)
    return jsonable_encoder(act_stocktake(db, identifier, payload, user,
        refresh_user=lambda: get_current_user(request=request, db=db)), custom_encoder={Decimal: str})


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
    sort: Literal["ASC", "DESC"] = "DESC",
    summary_only: bool = False,
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
        sort=sort,
        summary_only=summary_only,
    )
    return CartonAuditEventListOut(
        factory_id=factory_id,
        total=total,
        limit=limit,
        offset=offset,
        items=items,
        **audit_query_options(db, factory_id),
    )


@router.get("/audit-events/{event_id}", response_model=CartonAuditEventOut)
def get_audit_detail(event_id: str, factory_id: str, db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    from app.services.carton_procurement import get_audit_event
    factory_id = _ensure_permission(db, current_user, "carton_procurement:read", factory_id)
    return get_audit_event(db, factory_id, event_id)


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


from app.schemas.carton_material_correction import MaterialCorrectionCreate, MaterialCorrectionAction
from app.services import carton_material_correction as material_corrections

@router.get("/orders/{order_no}/material-corrections")
def material_correction_context(order_no: str, factory_id: str, db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    return material_corrections.context(db, current_user, factory_id, order_no)

@router.post("/orders/{order_no}/material-corrections", status_code=201)
def request_material_correction(order_no: str, payload: MaterialCorrectionCreate, db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    return material_corrections.create(db, current_user, order_no, payload)

@router.post("/material-corrections/{identifier}/actions")
def withdraw_material_correction(identifier: str, payload: MaterialCorrectionAction, db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    return material_corrections.act(db, current_user, identifier, payload)

@router.get("/supplier-promise-changes")
def supplier_promise_change_list(factory_id: str, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
                                 db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    from app.services.carton_procurement import _lock_receipt_factory
    factory_id = _ensure_permission(db, current_user, "carton_procurement:read", factory_id)
    _lock_receipt_factory(db, factory_id)
    return supplier_promise_notices(db, factory_id, limit, offset)


@router.post("/promise-notices/ack")
def acknowledge_promise_notice_route(payload: PromiseNoticeAck,
                                     db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    factory_id = _ensure_permission(db, current_user, "carton_procurement:read", payload.factory_id)
    payload.factory_id = factory_id
    return acknowledge_promise_notice(db, current_user, payload)

# Ordinary splits materialize immediately and reuse standard supplier changes.
from app.schemas.carton_order_division import OrderDivisionCreate
from app.services import carton_order_division as divisions


@router.get('/orders/{order_no}/independent-splits')
def independent_split_context(order_no: str, factory_id: str, db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    return divisions.context(db, current_user, factory_id, order_no)


@router.post('/orders/{order_no}/independent-splits', status_code=201)
def divide_order(order_no: str, payload: OrderDivisionCreate, db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    return divisions.create(db, order_no, payload, current_user)


# Retained proposal endpoints allow previously sent print changes to be resolved.
from app.schemas.carton_print_split import PrintSplitCreate, PrintSplitAction
from app.services import carton_print_split as print_splits


@router.get('/orders/{order_no}/print-splits')
def get_print_splits(order_no: str, factory_id: str, db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    _ensure_permission(db, current_user, 'carton_procurement:read', factory_id)
    order = get_order_by_no(db, factory_id, order_no)
    from app.services.carton_customer_assignment import ensure_customer_operation
    ensure_customer_operation(db, current_user, factory_id, order.customer_code)
    from app.services.carton_asset_access import visible
    from app.models.carton_mark import CartonMarkAsset
    from sqlalchemy import select
    files = [dict(id=file.id, revision=file.revision, file_name=file.file_name, sha256=file.sha256)
        for file in db.scalars(select(CartonMarkAsset).where(CartonMarkAsset.factory_id == factory_id,
            CartonMarkAsset.is_archived.is_(False), CartonMarkAsset.asset_purpose == 'MATERIAL'))
        if visible(db, current_user, file, view_factory=factory_id)]
    files.extend(print_splits.material_candidates(db, current_user, factory_id, order.customer_code))
    current_print = print_splits.order_info(db, order)
    return dict(revision=order.revision, files=files, inherited_original_files=print_splits.source_files(db, current_user, order), fixed_original_files=current_print["files"] if current_print and current_print["status"] == "ACTIVE" else [], plans=[p for p in print_splits.records(db, factory_id)
        if p.get('workflow') != 'ORDER' and (p['order_id'] == order.id or any(m['order_id'] == order.id for m in p['members']))])


@router.post('/orders/{order_no}/print-splits', status_code=201)
def post_print_split(order_no: str, payload: PrintSplitCreate, db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    _ensure_permission(db, current_user, 'carton_procurement:order_write', payload.factory_id)
    raise HTTPException(409, '拆单已简化为独立订单，请刷新后从订单的拆单入口确认，不再创建印刷拆单提案')


@router.post('/print-splits/{identifier}/{action}')
def act_print_split(identifier: str, action: Literal['send', 'withdraw'], payload: PrintSplitAction,
        db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    if action == 'send':
        _ensure_permission(db, current_user, 'carton_procurement:order_write', payload.factory_id)
        raise HTTPException(409, '旧拆单草稿不能继续发送，请撤销后使用独立订单拆分')
    return print_splits.act(db, identifier, action, payload, current_user)


@router.get('/print-splits/{identifier}/files/{asset_id}')
def print_split_file(identifier: str, asset_id: str, factory_id: str, db: Session = Depends(get_db), current_user: AuthContext = Depends(get_current_user)):
    asset, frozen = print_splits.download(db, current_user, factory_id, identifier, asset_id)
    return StreamingResponse(BytesIO(asset.content), media_type=frozen['content_type'],
        headers={'Content-Disposition': "attachment; filename*=UTF-8''" + url_quote(frozen['file_name'])})
