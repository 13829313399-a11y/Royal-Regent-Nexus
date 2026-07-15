from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.molding_sample import (
    InventoryBatchCreateRequest,
    InventoryBatchOut,
    InventoryMovementOut,
    MaterialPricesResponse,
    MaterialPricesUpdateRequest,
    MoldingSampleBoardPageResponse,
    MoldingSampleBoardStatus,
    MoldingSampleBoardSummaryResponse,
    MoldingSampleCreateRequest,
    MoldingSampleDetailResponse,
    MoldingSampleEditRequest,
    MoldingSampleItemOut,
    MoldingSampleItemsPatchRequest,
    MoldingSampleNotificationOut,
    MoldingSampleNotificationUpdateRequest,
    MoldingSampleProblemCreateRequest,
    MoldingSampleProblemOut,
    MoldingSampleProblemStatusRequest,
    MoldingSampleStatusRequest,
    MoldingSampleTrialReportOut,
    MoldingSampleTrialReportUpsertRequest,
    RequisitionCreateRequest,
    RequisitionOut,
    RequisitionStatusRequest,
    SensitiveAuditLogOut,
    TotalCostSummary,
)
from app.services.auth import AuthContext, get_current_user
from app.services.business_authz import (
    MANAGEMENT_DEPARTMENTS,
    WAREHOUSE_DEPARTMENTS,
    can_view_molding_cost,
    molding_read_access,
)
from app.services.molding_sample import (
    build_total_cost_summary,
    create_inventory_batch,
    create_order,
    create_problem,
    create_requisition,
    delete_order,
    delete_requisition,
    ensure_any_local_molding_read,
    ensure_export_permission,
    ensure_molding_create_access,
    ensure_molding_cost_read,
    ensure_permission_in_any_factory,
    get_exchange_rate,
    get_board_summary,
    get_prices,
    list_inventory_batches,
    list_inventory_movements,
    list_board_page,
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
    upsert_trial_report,
)
from app.services.molding_sample_excel import (
    XLSX_MIME,
    build_engineering_import_template,
    export_order_to_excel,
    export_orders_to_excel,
    parse_order_excel,
)

router = APIRouter()


def serialize_order(order, current_user: AuthContext) -> MoldingSampleDetailResponse:
    read_source = molding_read_access(current_user, order.factory_id) or "local"
    can_view_cost = can_view_molding_cost(current_user, order.factory_id, read_source)
    items = [MoldingSampleItemOut.model_validate(item) for item in order.items]
    if not can_view_cost:
        items = [
            item.model_copy(
                update={
                    "actual_amount_hkd": None,
                    "actual_material_cost_components": [],
                    "injection_cost": None,
                    "injection_cost_hkd": None,
                    "exchange_rate_at_save": None,
                }
            )
            for item in items
        ]
    return MoldingSampleDetailResponse(
        order=order,
        items=items,
        audit_logs=list(order.audit_logs),
        notifications=list(order.notifications),
        problems=list(order.problems),
        trial_reports=list(order.trial_reports),
        read_source=read_source,
        can_view_cost=can_view_cost,
    )


def resolve_import_factory_id(current_user: AuthContext, factory_id: str | None) -> str | None:
    if factory_id:
        return factory_id

    factory_scopes = [scope for scope in current_user.factory_scopes if scope != "*"]
    if len(factory_scopes) == 1:
        return factory_scopes[0]

    return None


@router.get("/api/injection", response_model=list[MoldingSampleDetailResponse])
def get_injection_orders(
    factory_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return [serialize_order(order, current_user) for order in list_orders(db, current_user, factory_id=factory_id)]


@router.get("/api/injection/export-excel")
def export_injection_orders_excel(
    order_ids: list[str] = Query(..., min_length=1),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    normalized_order_ids = list(dict.fromkeys(order_id for order_id in order_ids if order_id.strip()))

    if not normalized_order_ids:
        raise HTTPException(status_code=400, detail="请选择需要导出的啤办单")

    orders = [load_order(db, order_id, current_user) for order_id in normalized_order_ids]
    for order in orders:
        ensure_export_permission(db, current_user, order.factory_id)
    content = export_orders_to_excel(orders, get_prices(db))
    filename = f"molding-sample-{len(orders)}-orders.xlsx"
    return Response(
        content=content,
        media_type=XLSX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/api/injection/import-excel-template")
def download_engineering_import_template(
    factory_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    resolved_factory_id = resolve_import_factory_id(current_user, factory_id)
    ensure_molding_create_access(db, current_user, resolved_factory_id)
    return Response(
        content=build_engineering_import_template(),
        media_type=XLSX_MIME,
        headers={"Content-Disposition": 'attachment; filename="engineering-molding-sample-import-template.xlsx"'},
    )


@router.get("/api/injection/board/page", response_model=MoldingSampleBoardPageResponse)
def get_injection_board_page(
    factory_id: str = Query(..., min_length=1),
    board_status: MoldingSampleBoardStatus = Query(..., alias="status"),
    q: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    orders, total, normalized_page, page_count = list_board_page(
        db,
        current_user,
        factory_id=factory_id,
        board_status=board_status,
        keyword=q,
        page=page,
        page_size=page_size,
    )
    return MoldingSampleBoardPageResponse(
        rows=[serialize_order(order, current_user) for order in orders],
        total=total,
        page=normalized_page,
        page_size=page_size,
        page_count=page_count,
    )


@router.get("/api/injection/board/summary", response_model=MoldingSampleBoardSummaryResponse)
def get_injection_board_summary(
    factory_id: str = Query(..., min_length=1),
    q: str = "",
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return MoldingSampleBoardSummaryResponse.model_validate(
        get_board_summary(
            db,
            current_user,
            factory_id=factory_id,
            keyword=q,
        )
    )


@router.get("/api/injection/{order_id}", response_model=MoldingSampleDetailResponse)
def get_injection_order(
    order_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return serialize_order(load_order(db, order_id, current_user), current_user)


@router.post("/api/injection", response_model=MoldingSampleDetailResponse, status_code=status.HTTP_201_CREATED)
def post_injection_order(
    payload: MoldingSampleCreateRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return serialize_order(create_order(db, payload, current_user), current_user)


@router.get("/api/injection/{order_id}/export-excel")
def export_injection_order_excel(
    order_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    order = load_order(db, order_id, current_user)
    ensure_export_permission(db, current_user, order.factory_id)
    content = export_order_to_excel(order, get_prices(db))
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
    factory_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    try:
        payload = parse_order_excel(
            body,
            order_id_override=order_id,
            factory_id_override=resolve_import_factory_id(current_user, factory_id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return serialize_order(create_order(db, payload, current_user), current_user)


@router.post("/api/injection/import-excel-preview", response_model=MoldingSampleCreateRequest)
def preview_injection_order_excel(
    body: bytes = Body(..., media_type=XLSX_MIME),
    order_id: str | None = None,
    factory_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    try:
        payload = parse_order_excel(
            body,
            order_id_override=order_id,
            factory_id_override=resolve_import_factory_id(current_user, factory_id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    ensure_molding_create_access(db, current_user, payload.order.factory_id)
    return payload


@router.put("/api/injection/{order_id}", response_model=MoldingSampleDetailResponse)
def put_injection_order(
    order_id: str,
    payload: MoldingSampleEditRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return serialize_order(update_order(db, order_id, payload, current_user), current_user)


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
    return serialize_order(transition_status(db, order_id, payload, current_user), current_user)


@router.patch("/api/injection/{order_id}/items", response_model=MoldingSampleDetailResponse)
def patch_injection_items(
    order_id: str,
    payload: MoldingSampleItemsPatchRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return serialize_order(update_order_items(db, order_id, payload.items, current_user), current_user)


@router.put(
    "/api/injection/{order_id}/trial-reports/{item_id}",
    response_model=MoldingSampleTrialReportOut,
)
def put_injection_trial_report(
    order_id: str,
    item_id: str,
    payload: MoldingSampleTrialReportUpsertRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return upsert_trial_report(db, order_id, item_id, payload, current_user)


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
    factory_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    if factory_id:
        ensure_molding_cost_read(db, current_user, factory_id)
    else:
        ensure_any_local_molding_read(db, current_user)
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
    ensure_permission_in_any_factory(
        db,
        current_user,
        "molding_sample:audit_read",
        MANAGEMENT_DEPARTMENTS,
    )
    return list_sensitive_audit_logs(db)


@router.get("/api/requisitions", response_model=list[RequisitionOut])
def get_requisitions(
    order_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return list_requisitions(db, current_user, order_id=order_id)


@router.get("/api/inventory-batches", response_model=list[InventoryBatchOut])
def get_inventory_batches(
    material: str | None = None,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_permission_in_any_factory(
        db,
        current_user,
        "molding_sample:inventory_issue",
        WAREHOUSE_DEPARTMENTS,
    )
    return list_inventory_batches(db, material=material)


@router.get("/api/inventory-movements", response_model=list[InventoryMovementOut])
def get_inventory_movements(
    batch_id: str | None = None,
    material: str | None = None,
    requisition_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_permission_in_any_factory(
        db,
        current_user,
        "molding_sample:inventory_issue",
        WAREHOUSE_DEPARTMENTS,
    )
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
    factory_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    if factory_id:
        ensure_molding_cost_read(db, current_user, factory_id)
    return [
        build_total_cost_summary(order)
        for order in list_orders(db, current_user, factory_id=factory_id)
        if order.status == "已完成"
        and can_view_molding_cost(
            current_user,
            order.factory_id,
            molding_read_access(current_user, order.factory_id),
        )
    ]
