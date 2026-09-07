from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from difflib import SequenceMatcher
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time import business_now, business_today
from app.models.carton_procurement import (
    CartonAuditEvent,
    CartonClosing,
    CartonCustomer,
    CartonException,
    CartonImportBatch,
    CartonInventoryMovement,
    CartonOrder,
    CartonOrderLine,
    CartonPurchaseOrderIssue,
    CartonReceipt,
    CartonReceiptLine,
    CartonSupplier,
)
from app.schemas.carton_procurement import (
    CartonClosingGenerateRequest,
    CartonClosingOut,
    CartonClosingStatusRequest,
    CartonAuditEventOut,
    CartonCustomerCreate,
    CartonCustomerUpdate,
    CartonDashboardOut,
    CartonExceptionListOut,
    CartonExceptionOut,
    CartonExceptionUpdate,
    CartonImportBatchOut,
    CartonInventoryBalanceOut,
    CartonInventoryBulkCreate,
    CartonInventoryFlowSummaryOut,
    CartonInventoryMovementCreate,
    CartonInventoryMovementOut,
    CartonInventoryReversalRequest,
    CartonInventoryRelocateRequest,
    CartonOrderAppendRequest,
    CartonOrderBulkCancelRequest,
    CartonOrderBulkSubmitRequest,
    CartonOrderCancelRequest,
    CartonOrderCreate,
    CartonOrderLineOut,
    CartonOrderHistoryLineOut,
    CartonOrderHistorySuggestionOut,
    CartonOrderOut,
    CartonPurchaseOrderContextOut,
    CartonPurchaseOrderIssueOut,
    CartonOrderReduceRequest,
    CartonOrderSubmitRequest,
    CartonOrderUpdate,
    CartonReceiptConfirmRequest,
    CartonReceiptCreate,
    CartonReceiptLineOut,
    CartonReceiptOut,
    DEFAULT_CARTON_SAFETY_LEAD_DAYS,
    derive_carton_plan_due_date,
)
from app.services.auth import ALLOWED_FACTORY_IDS, AuthContext
from app.services.carton_procurement_imports import (
    DELIVERY_IMPORT_PARSER_VERSION,
    parse_carton_import,
)


CARTON_DEPARTMENTS = ("pmc-warehouse", "carton")
CARTON_DEFAULT_SUPPLIER_CODE = "HEYUAN-DONGKANG"
CARTON_DEFAULT_SUPPLIER_NAME = "河源东康纸品有限公司"
QUANTITY_QUANTUM = Decimal("0.0001")
MONEY_QUANTUM = Decimal("0.0001")
MAX_IMPORT_BYTES = 20 * 1024 * 1024
ALLOWED_IMPORT_SUFFIXES = {".xlsx", ".xls", ".pdf", ".png", ".jpg", ".jpeg", ".heic", ".heif"}
CURRENCY_ALIASES = {
    "RMB": "CNY",
    "人民币": "CNY",
    "人民币元": "CNY",
    "¥": "CNY",
    "￥": "CNY",
    "港币": "HKD",
    "港元": "HKD",
    "HK$": "HKD",
}


def now_text() -> str:
    return business_now().isoformat(timespec="seconds")


def quantity(value: Decimal | int | str) -> Decimal:
    return Decimal(value).quantize(QUANTITY_QUANTUM, rounding=ROUND_HALF_UP)


def required_carton_quantity(
    product_order_quantity: Decimal | int | str,
    units_per_carton: Decimal | int | str,
) -> Decimal:
    normalized_units_per_carton = Decimal(units_per_carton)
    if normalized_units_per_carton <= 0:
        raise ValueError("每箱个数必须大于 0")
    cartons = (Decimal(product_order_quantity) / normalized_units_per_carton).to_integral_value(
        rounding=ROUND_CEILING
    )
    return quantity(cartons)


def normalize_currency(value: str) -> str:
    normalized = value.strip().upper()
    return CURRENCY_ALIASES.get(normalized, normalized or "CNY")


def require_carton_factory(factory_id: str) -> str:
    normalized = factory_id.strip()
    if normalized not in ALLOWED_FACTORY_IDS:
        raise HTTPException(status_code=422, detail="纸箱采购厂区无效")
    return normalized


def _audit(
    db: Session,
    user: AuthContext,
    factory_id: str,
    event_type: str,
    entity_type: str,
    entity_id: str,
    detail: dict[str, object] | None = None,
) -> None:
    db.add(
        CartonAuditEvent(
            id=f"CAE-{uuid4().hex}",
            factory_id=factory_id,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            detail_json=json.dumps(detail or {}, ensure_ascii=False, sort_keys=True, default=str),
            actor_user_id=user.id,
            actor_name=user.display_name,
            created_at=now_text(),
        )
    )


def seed_carton_supplier_defaults(db: Session) -> int:
    created = 0
    timestamp = now_text()
    for factory_id in sorted(ALLOWED_FACTORY_IDS):
        supplier_id = f"CSP-{factory_id}-{CARTON_DEFAULT_SUPPLIER_CODE}"
        if db.get(CartonSupplier, supplier_id) is not None:
            continue
        db.add(
            CartonSupplier(
                id=supplier_id,
                factory_id=factory_id,
                supplier_code=CARTON_DEFAULT_SUPPLIER_CODE,
                supplier_name=CARTON_DEFAULT_SUPPLIER_NAME,
                status="ACTIVE",
                created_at=timestamp,
                updated_at=timestamp,
            )
        )
        created += 1
    db.commit()
    return created


def get_active_supplier(db: Session, factory_id: str, supplier_id: str | None) -> CartonSupplier:
    if supplier_id:
        supplier = db.get(CartonSupplier, supplier_id)
        if supplier is None or supplier.factory_id != factory_id or supplier.status != "ACTIVE":
            raise HTTPException(status_code=422, detail="纸箱供应商不存在、已停用或不属于当前厂区")
        return supplier
    supplier = db.scalar(
        select(CartonSupplier).where(
            CartonSupplier.factory_id == factory_id,
            CartonSupplier.status == "ACTIVE",
        )
    )
    if supplier is None:
        raise HTTPException(status_code=409, detail="当前厂区尚未配置有效纸箱供应商")
    return supplier


def list_customers(
    db: Session,
    factory_id: str,
    *,
    include_inactive: bool = False,
    search: str = "",
) -> list[CartonCustomer]:
    statement = select(CartonCustomer).where(CartonCustomer.factory_id == factory_id)
    if not include_inactive:
        statement = statement.where(CartonCustomer.status == "ACTIVE")
    if search:
        term = f"%{search}%"
        statement = statement.where(
            or_(
                CartonCustomer.customer_code.ilike(term),
                CartonCustomer.customer_name.ilike(term),
                CartonCustomer.country_region.ilike(term),
                CartonCustomer.contact_name.ilike(term),
            )
        )
    return list(
        db.scalars(
            statement.order_by(CartonCustomer.status, CartonCustomer.customer_name, CartonCustomer.customer_code)
        ).all()
    )


def get_active_customer(db: Session, factory_id: str, customer_code: str) -> CartonCustomer:
    customer = db.scalar(
        select(CartonCustomer).where(
            CartonCustomer.factory_id == factory_id,
            CartonCustomer.customer_code == customer_code.strip().upper(),
        )
    )
    if customer is None:
        raise HTTPException(status_code=422, detail="客户不存在或不属于当前厂区，请先由纸箱部主管维护客户资料")
    if customer.status != "ACTIVE":
        raise HTTPException(status_code=422, detail="客户已停用，不能用于新建纸箱订单")
    return customer


def get_active_customer_by_name(
    db: Session,
    factory_id: str,
    customer_name: str,
) -> CartonCustomer:
    normalized_name = " ".join(customer_name.strip().split()).casefold()
    matches = [
        customer
        for customer in db.scalars(
            select(CartonCustomer).where(
                CartonCustomer.factory_id == factory_id,
                CartonCustomer.status == "ACTIVE",
            )
        ).all()
        if " ".join(customer.customer_name.strip().split()).casefold() == normalized_name
    ]
    if not matches:
        raise HTTPException(
            status_code=422,
            detail=f"客户名称“{customer_name.strip()}”不存在或未启用，请先由纸箱部主管维护客户资料",
        )
    if len(matches) > 1:
        raise HTTPException(
            status_code=422,
            detail=f"客户名称“{customer_name.strip()}”对应多个客户，请先合并或更正客户资料",
        )
    return matches[0]


def create_customer(db: Session, payload: CartonCustomerCreate, user: AuthContext) -> CartonCustomer:
    factory_id = require_carton_factory(payload.factory_id)
    timestamp = now_text()
    duplicate_name = next(
        (
            item
            for item in db.scalars(
                select(CartonCustomer).where(CartonCustomer.factory_id == factory_id)
            ).all()
            if " ".join(item.customer_name.strip().split()).casefold()
            == " ".join(payload.customer_name.strip().split()).casefold()
        ),
        None,
    )
    if duplicate_name is not None:
        raise HTTPException(status_code=409, detail="当前厂区已存在相同客户名称")
    internal_code = payload.customer_code.upper() or (
        "CUST-" + hashlib.sha256(payload.customer_name.casefold().encode("utf-8")).hexdigest()[:12].upper()
    )
    customer = CartonCustomer(
        id=f"CCU-{uuid4().hex}",
        factory_id=factory_id,
        customer_code=internal_code,
        customer_name=payload.customer_name,
        country_region=payload.country_region,
        contact_name=payload.contact_name,
        contact_phone=payload.contact_phone,
        note=payload.note,
        status=payload.status,
        revision=1,
        created_by=user.id,
        created_by_name=user.display_name,
        updated_by=user.id,
        updated_by_name=user.display_name,
        created_at=timestamp,
        updated_at=timestamp,
    )
    db.add(customer)
    _audit(db, user, factory_id, "CUSTOMER_CREATED", "carton_customer", customer.id, {
        "customer_code": customer.customer_code,
        "customer_name": customer.customer_name,
    })
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="当前厂区已存在相同客户名称或内部编号") from exc
    db.refresh(customer)
    return customer


def _get_customer(db: Session, factory_id: str, customer_id: str) -> CartonCustomer:
    customer = db.get(CartonCustomer, customer_id)
    if customer is None or customer.factory_id != factory_id:
        raise HTTPException(status_code=404, detail="客户资料不存在")
    return customer


def update_customer(
    db: Session,
    customer_id: str,
    payload: CartonCustomerUpdate,
    user: AuthContext,
) -> CartonCustomer:
    factory_id = require_carton_factory(payload.factory_id)
    customer = _get_customer(db, factory_id, customer_id)
    if customer.revision != payload.expected_revision:
        raise HTTPException(status_code=409, detail="客户资料已被其他人更新，请刷新后重试")
    changes = payload.model_dump(exclude={"factory_id", "expected_revision"}, exclude_none=True)
    if "customer_name" in changes:
        normalized_name = " ".join(changes["customer_name"].strip().split()).casefold()
        duplicate_name = next(
            (
                item
                for item in db.scalars(
                    select(CartonCustomer).where(
                        CartonCustomer.factory_id == factory_id,
                        CartonCustomer.id != customer.id,
                    )
                ).all()
                if " ".join(item.customer_name.strip().split()).casefold() == normalized_name
            ),
            None,
        )
        if duplicate_name is not None:
            raise HTTPException(status_code=409, detail="当前厂区已存在相同客户名称")
    if "customer_code" in changes:
        changes["customer_code"] = changes["customer_code"].upper()
    previous = {field: getattr(customer, field) for field in changes}
    for field, value in changes.items():
        setattr(customer, field, value)
    customer.revision += 1
    customer.updated_by = user.id
    customer.updated_by_name = user.display_name
    customer.updated_at = now_text()
    _audit(db, user, factory_id, "CUSTOMER_UPDATED", "carton_customer", customer.id, {
        "before": previous,
        "after": changes,
    })
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="当前厂区已存在相同客户名称或内部编号") from exc
    db.refresh(customer)
    return customer


def delete_customer(db: Session, factory_id: str, customer_id: str, user: AuthContext) -> None:
    factory_id = require_carton_factory(factory_id)
    customer = _get_customer(db, factory_id, customer_id)
    order_count = db.scalar(
        select(func.count(CartonOrder.id)).where(
            CartonOrder.factory_id == factory_id,
            CartonOrder.customer_code == customer.customer_code,
        )
    ) or 0
    if order_count:
        raise HTTPException(status_code=409, detail="客户已有纸箱订单，不能删除；如不再使用请改为停用")
    _audit(db, user, factory_id, "CUSTOMER_DELETED", "carton_customer", customer.id, {
        "customer_code": customer.customer_code,
        "customer_name": customer.customer_name,
    })
    db.delete(customer)
    db.commit()


def _new_number(prefix: str) -> str:
    return f"{prefix}-{business_now().strftime('%y%m%d')}-{uuid4().hex[:6].upper()}"


def create_order(
    db: Session,
    payload: CartonOrderCreate,
    user: AuthContext,
    *,
    order_no: str | None = None,
    commit: bool = True,
    audit_event: str = "ORDER_CREATED",
) -> CartonOrder:
    factory_id = require_carton_factory(payload.factory_id)
    customer = get_active_customer(db, factory_id, payload.customer_code)
    supplier = get_active_supplier(db, factory_id, payload.supplier_id)
    product_name = payload.product_name
    product_name_source = "submitted"
    if not product_name:
        historical_product_name = db.scalar(
            select(CartonOrder.product_name)
            .where(
                CartonOrder.factory_id == factory_id,
                CartonOrder.item_no == payload.item_no,
                CartonOrder.product_name != "",
            )
            .order_by(CartonOrder.created_at.desc())
            .limit(1)
        )
        if historical_product_name:
            product_name = historical_product_name
            product_name_source = "item_history"
    timestamp = now_text()
    order_id = f"CTO-{uuid4().hex}"
    order = CartonOrder(
        id=order_id,
        factory_id=factory_id,
        order_no=order_no or _new_number("CT"),
        customer_code=customer.customer_code,
        customer_name=customer.customer_name,
        supplier_id=supplier.id,
        supplier_name_snapshot=supplier.supplier_name,
        contract_no=payload.contract_no,
        item_no=payload.item_no,
        product_name=product_name,
        product_order_quantity=payload.product_order_quantity,
        order_date=payload.order_date,
        customer_due_date=payload.customer_due_date,
        safety_lead_days=DEFAULT_CARTON_SAFETY_LEAD_DAYS,
        due_date=payload.due_date,
        status="CONFIRMED",
        note=payload.note,
        revision=1,
        created_by=user.id,
        created_by_name=user.display_name,
        updated_by=user.id,
        updated_by_name=user.display_name,
        created_at=timestamp,
        updated_at=timestamp,
    )
    db.add(order)
    for index, line in enumerate(payload.lines, start=1):
        required_quantity = required_carton_quantity(
            payload.product_order_quantity,
            line.usage_quantity,
        )
        if required_quantity <= 0:
            raise HTTPException(status_code=422, detail=f"第 {index} 行计算后的需求数量必须大于 0")
        db.add(
            CartonOrderLine(
                id=f"CTL-{uuid4().hex}",
                factory_id=factory_id,
                order_id=order_id,
                line_no=index,
                customer_code=customer.customer_code,
                contract_no=payload.contract_no,
                item_no=payload.item_no,
                packaging_type=line.packaging_type,
                paper_quality=line.paper_quality,
                specification=line.specification,
                dimension_unit=line.dimension_unit,
                usage_quantity=line.usage_quantity,
                required_quantity=required_quantity,
                unit=line.unit,
                unit_price=line.unit_price,
                currency=normalize_currency(line.currency),
                price_source=line.price_source,
                note=line.note,
            )
        )
    _audit(
        db,
        user,
        factory_id,
        audit_event,
        "carton_order",
        order_id,
        {
            "order_no": order.order_no,
            "line_count": len(payload.lines),
            "contract_no": payload.contract_no,
            "status": "CONFIRMED",
            "product_name_source": product_name_source,
        },
    )
    try:
        if commit:
            db.commit()
        else:
            db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="纸箱订单编号冲突，请重试") from exc
    if commit:
        db.refresh(order)
    return order


def get_order_by_no(db: Session, factory_id: str, order_no: str) -> CartonOrder:
    order = db.scalar(
        select(CartonOrder).where(
            CartonOrder.factory_id == factory_id,
            CartonOrder.order_no == order_no,
        )
    )
    if order is None:
        raise HTTPException(status_code=404, detail="纸箱订单不存在")
    return order


def _order_lines(db: Session, order_id: str) -> list[CartonOrderLine]:
    return list(
        db.scalars(
            select(CartonOrderLine)
            .where(CartonOrderLine.order_id == order_id)
            .order_by(CartonOrderLine.line_no)
        ).all()
    )


def get_order_lines(db: Session, order_id: str) -> list[CartonOrderLine]:
    return _order_lines(db, order_id)


def _purchase_order_issue_out(issue: CartonPurchaseOrderIssue) -> CartonPurchaseOrderIssueOut:
    return CartonPurchaseOrderIssueOut(
        id=issue.id,
        factory_id=issue.factory_id,
        order_no=issue.order_no,
        document_no=issue.document_no,
        document_type=issue.document_type,
        issue_sequence=issue.issue_sequence,
        source_order_revision=issue.source_order_revision,
        before_product_quantity=issue.before_product_quantity,
        after_product_quantity=issue.after_product_quantity,
        product_quantity_delta=issue.product_quantity_delta,
        generated_by=issue.generated_by,
        generated_by_name=issue.generated_by_name,
        generated_at=issue.generated_at,
    )


def _purchase_order_issues(db: Session, order_id: str) -> list[CartonPurchaseOrderIssue]:
    return list(
        db.scalars(
            select(CartonPurchaseOrderIssue)
            .where(CartonPurchaseOrderIssue.order_id == order_id)
            .order_by(CartonPurchaseOrderIssue.issue_sequence.desc())
        ).all()
    )


def _purchase_order_snapshot(issue: CartonPurchaseOrderIssue | None) -> dict[str, object]:
    if issue is None:
        return {}
    try:
        snapshot = json.loads(issue.snapshot_json or "{}")
    except (TypeError, ValueError):
        return {}
    return snapshot if isinstance(snapshot, dict) else {}


def _purchase_order_pending_change(
    order: CartonOrder,
    lines: list[CartonOrderLine],
    latest_issue: CartonPurchaseOrderIssue | None,
) -> tuple[str, Decimal, int, dict[str, object]]:
    previous = _purchase_order_snapshot(latest_issue)
    before_product_quantity = quantity(
        Decimal(str(previous.get("after_product_quantity", 0)))
    )
    before_due_date = str(previous.get("after_due_date", ""))
    previous_lines = {
        str(item.get("id", "")): item
        for item in previous.get("lines", [])
        if isinstance(item, dict)
    }
    product_delta = quantity(order.product_order_quantity - before_product_quantity)
    line_snapshots: list[dict[str, object]] = []
    for line in lines:
        previous_line = previous_lines.get(line.id, {})
        before_required = quantity(
            Decimal(str(previous_line.get("after_required_quantity", 0)))
        )
        after_required = quantity(line.required_quantity)
        line_snapshots.append(
            {
                "id": line.id,
                "line_no": line.line_no,
                "packaging_type": line.packaging_type,
                "paper_quality": line.paper_quality,
                "specification": line.specification,
                "dimension_unit": line.dimension_unit,
                "usage_quantity": str(line.usage_quantity),
                "unit": line.unit,
                "unit_price": str(line.unit_price),
                "currency": line.currency,
                "price_source": line.price_source,
                "note": line.note,
                "before_required_quantity": str(before_required),
                "after_required_quantity": str(after_required),
                "required_quantity_delta": str(quantity(after_required - before_required)),
            }
        )

    changed_line_count = sum(
        Decimal(str(item["required_quantity_delta"])) != 0 for item in line_snapshots
    )
    due_date_changed = bool(before_due_date and before_due_date != order.due_date)
    if latest_issue is None:
        pending_type = "INITIAL"
    elif product_delta > 0:
        pending_type = "APPEND"
    elif product_delta < 0:
        pending_type = "REDUCE"
    elif changed_line_count or due_date_changed:
        pending_type = "ADJUSTMENT"
    else:
        pending_type = "NONE"

    snapshot: dict[str, object] = {
        "order": {
            "id": order.id,
            "factory_id": order.factory_id,
            "order_no": order.order_no,
            "customer_code": order.customer_code,
            "customer_name": order.customer_name,
            "supplier_id": order.supplier_id,
            "supplier_name": order.supplier_name_snapshot,
            "contract_no": order.contract_no,
            "item_no": order.item_no,
            "product_name": order.product_name,
            "order_date": order.order_date,
            "customer_due_date": order.customer_due_date,
            "safety_lead_days": order.safety_lead_days,
            "due_date": order.due_date,
            "status": order.status,
            "note": order.note,
            "revision": order.revision,
        },
        "before_product_quantity": str(before_product_quantity),
        "after_product_quantity": str(quantity(order.product_order_quantity)),
        "product_quantity_delta": str(product_delta),
        "before_due_date": before_due_date,
        "after_due_date": order.due_date,
        "lines": line_snapshots,
    }
    return pending_type, product_delta, changed_line_count, snapshot


def purchase_order_context(
    db: Session,
    order: CartonOrder,
) -> CartonPurchaseOrderContextOut:
    issues = _purchase_order_issues(db, order.id)
    latest_issue = issues[0] if issues else None
    lines = _order_lines(db, order.id)
    pending_type, product_delta, changed_line_count, _ = _purchase_order_pending_change(
        order, lines, latest_issue
    )
    eligible_status = order.status in {"PENDING_SUPPLIER", "PARTIALLY_RECEIVED", "COMPLETED"}
    visible_issues = [issue for issue in issues if issue.document_type != "LEGACY_BASELINE"]
    return CartonPurchaseOrderContextOut(
        factory_id=order.factory_id,
        order_no=order.order_no,
        order_revision=order.revision,
        pending_type=pending_type,
        pending_product_quantity=product_delta,
        pending_line_count=changed_line_count,
        can_generate=eligible_status and pending_type != "NONE",
        latest_document_no=visible_issues[0].document_no if visible_issues else "",
        historical_baseline=any(issue.document_type == "LEGACY_BASELINE" for issue in issues),
        issues=[_purchase_order_issue_out(issue) for issue in visible_issues],
    )


def create_purchase_order_issue(
    db: Session,
    order: CartonOrder,
    expected_revision: int,
    user: AuthContext,
    *,
    commit: bool = True,
) -> CartonPurchaseOrderIssue:
    if order.revision != expected_revision:
        raise HTTPException(status_code=409, detail="订单已被其他人更新，请刷新后重试")
    if order.status not in {"PENDING_SUPPLIER", "PARTIALLY_RECEIVED", "COMPLETED"}:
        raise HTTPException(status_code=409, detail="只有已确认并锁定的订单可以发行供应商采购单")

    issues = _purchase_order_issues(db, order.id)
    latest_issue = issues[0] if issues else None
    pending_type, product_delta, _, snapshot = _purchase_order_pending_change(
        order, _order_lines(db, order.id), latest_issue
    )
    if pending_type == "NONE":
        raise HTTPException(status_code=409, detail="当前订单没有尚未生成采购单的数量或交期变化")

    next_issue_sequence = (latest_issue.issue_sequence if latest_issue else 0) + 1
    type_sequence = 1 + sum(issue.document_type == pending_type for issue in issues)
    if pending_type == "INITIAL":
        document_no = f"{order.order_no}-P00"
    else:
        prefix = {"APPEND": "A", "REDUCE": "R", "ADJUSTMENT": "C"}[pending_type]
        document_no = f"{order.order_no}-{prefix}{type_sequence:02d}"
    before_quantity = quantity(Decimal(str(snapshot["before_product_quantity"])))
    after_quantity = quantity(Decimal(str(snapshot["after_product_quantity"])))
    timestamp = now_text()
    issue = CartonPurchaseOrderIssue(
        id=f"CPOI-{uuid4().hex}",
        factory_id=order.factory_id,
        order_id=order.id,
        order_no=order.order_no,
        document_no=document_no,
        document_type=pending_type,
        issue_sequence=next_issue_sequence,
        source_order_revision=order.revision,
        before_product_quantity=before_quantity,
        after_product_quantity=after_quantity,
        product_quantity_delta=product_delta,
        snapshot_json=json.dumps(snapshot, ensure_ascii=False, sort_keys=True),
        generated_by=user.id,
        generated_by_name=user.display_name,
        generated_at=timestamp,
    )
    db.add(issue)
    _audit(
        db,
        user,
        order.factory_id,
        "PURCHASE_ORDER_ISSUED",
        "carton_purchase_order_issue",
        issue.id,
        {
            "order_no": order.order_no,
            "document_no": document_no,
            "document_type": pending_type,
            "source_order_revision": order.revision,
            "before_product_quantity": before_quantity,
            "after_product_quantity": after_quantity,
            "product_quantity_delta": product_delta,
            "line_deltas": {
                str(item["id"]): item["required_quantity_delta"]
                for item in snapshot["lines"]
                if isinstance(item, dict)
            },
        },
    )
    try:
        if commit:
            db.commit()
        else:
            db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="采购单已由其他操作生成，请刷新后查看记录") from exc
    if commit:
        db.refresh(issue)
    return issue


def create_purchase_order_issues_batch(
    db: Session,
    payload: CartonOrderBulkSubmitRequest,
    user: AuthContext,
) -> list[CartonPurchaseOrderIssue]:
    factory_id = require_carton_factory(payload.factory_id)
    pending_orders: list[tuple[CartonOrder, int]] = []
    reusable_issues: dict[str, CartonPurchaseOrderIssue] = {}
    selected_order_nos: list[str] = []
    for item in payload.items:
        order = get_order_by_no(db, factory_id, item.order_no)
        selected_order_nos.append(order.order_no)
        if order.revision != item.expected_revision:
            db.rollback()
            raise HTTPException(status_code=409, detail=f"订单 {item.order_no} 已更新，请刷新后重试")
        issues = _purchase_order_issues(db, order.id)
        pending_type, _, _, _ = _purchase_order_pending_change(
            order,
            _order_lines(db, order.id),
            issues[0] if issues else None,
        )
        if (
            order.status in {"PENDING_SUPPLIER", "PARTIALLY_RECEIVED", "COMPLETED"}
            and pending_type != "NONE"
        ):
            pending_orders.append((order, item.expected_revision))
            continue
        latest_visible_issue = next(
            (issue for issue in issues if issue.document_type != "LEGACY_BASELINE"),
            None,
        )
        if latest_visible_issue is not None:
            reusable_issues[order.order_no] = latest_visible_issue

    if not pending_orders and not reusable_issues:
        raise HTTPException(status_code=409, detail="所选订单没有待发行变化或可重新下载的历史采购单")

    created_by_order: dict[str, CartonPurchaseOrderIssue] = {}
    try:
        for order, expected_revision in pending_orders:
            created_by_order[order.order_no] = create_purchase_order_issue(
                db,
                order,
                expected_revision,
                user,
                commit=False,
            )
        if created_by_order:
            db.commit()
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="采购单批次与其他操作冲突，请刷新后重试") from exc
    for issue in created_by_order.values():
        db.refresh(issue)
    return [
        issue
        for order_no in selected_order_nos
        if (issue := created_by_order.get(order_no) or reusable_issues.get(order_no)) is not None
    ]


def get_purchase_order_issue(
    db: Session,
    factory_id: str,
    order: CartonOrder,
    issue_id: str,
) -> CartonPurchaseOrderIssue:
    issue = db.scalar(
        select(CartonPurchaseOrderIssue).where(
            CartonPurchaseOrderIssue.id == issue_id,
            CartonPurchaseOrderIssue.factory_id == factory_id,
            CartonPurchaseOrderIssue.order_id == order.id,
            CartonPurchaseOrderIssue.document_type != "LEGACY_BASELINE",
        )
    )
    if issue is None:
        raise HTTPException(status_code=404, detail="采购单记录不存在")
    return issue


def _order_has_business_activity(db: Session, order: CartonOrder) -> bool:
    line_ids = [line.id for line in _order_lines(db, order.id)]
    if not line_ids:
        return False
    receipt_line_count = db.scalar(
        select(func.count(CartonReceiptLine.id)).where(
            CartonReceiptLine.order_line_id.in_(line_ids)
        )
    ) or 0
    if receipt_line_count:
        return True
    movement_count = db.scalar(
        select(func.count(CartonInventoryMovement.id)).where(
            CartonInventoryMovement.order_line_id.in_(line_ids)
        )
    ) or 0
    return bool(movement_count)


def _order_line_signature(line: CartonOrderLine | object) -> tuple[str, ...]:
    return (
        str(line.packaging_type),
        str(line.paper_quality),
        str(line.specification),
        str(line.dimension_unit),
        str(Decimal(line.usage_quantity).normalize()),
        str(line.unit),
        str(Decimal(line.unit_price).normalize()),
        normalize_currency(str(line.currency)),
        str(line.price_source),
        str(line.note),
    )


def update_order(
    db: Session,
    order_no: str,
    payload: CartonOrderUpdate,
    user: AuthContext,
) -> CartonOrder:
    factory_id = require_carton_factory(payload.factory_id)
    order = get_order_by_no(db, factory_id, order_no)
    if order.status == "CANCELLED":
        raise HTTPException(status_code=409, detail="已取消订单不能修改")
    if order.status == "COMPLETED":
        raise HTTPException(status_code=409, detail="已完成订单不能修改；如有差异请通过库存调整处理")
    if order.revision != payload.expected_revision:
        raise HTTPException(status_code=409, detail="订单已被其他人更新，请刷新后重试")
    if order.status in {"PENDING_SUPPLIER", "PARTIALLY_RECEIVED"}:
        raise HTTPException(
            status_code=409,
            detail="订单已确认并锁定，不能再修改；收料差异请通过收料或库存流水处理",
        )

    existing_lines = _order_lines(db, order.id)
    customer = (
        get_active_customer(db, factory_id, payload.customer_code)
        if payload.customer_code != order.customer_code
        else None
    )
    supplier = (
        get_active_supplier(db, factory_id, payload.supplier_id)
        if payload.supplier_id and payload.supplier_id != order.supplier_id
        else None
    )
    target_customer_code = customer.customer_code if customer else order.customer_code
    target_customer_name = customer.customer_name if customer else order.customer_name
    target_supplier_id = supplier.id if supplier else order.supplier_id
    target_supplier_name = supplier.supplier_name if supplier else order.supplier_name_snapshot
    target_line_signatures = [
        (
            line.packaging_type,
            line.paper_quality,
            line.specification,
            line.dimension_unit,
            str(Decimal(line.usage_quantity).normalize()),
            line.unit,
            str(Decimal(line.unit_price).normalize()),
            normalize_currency(line.currency),
            line.price_source,
            line.note,
        )
        for line in payload.lines
    ]
    structural_changed = any(
        (
            target_customer_code != order.customer_code,
            target_supplier_id != order.supplier_id,
            payload.contract_no != order.contract_no,
            payload.item_no != order.item_no,
            payload.product_name != order.product_name,
            Decimal(payload.product_order_quantity) != Decimal(order.product_order_quantity),
            payload.order_date != order.order_date,
            target_line_signatures != [_order_line_signature(line) for line in existing_lines],
        )
    )
    if order.customer_due_date is not None and payload.customer_due_date is None:
        if payload.due_date != order.due_date:
            raise HTTPException(
                status_code=422,
                detail="已有客户交期的订单必须通过客户交期自动计算计划交期",
            )
        target_customer_due_date = order.customer_due_date
        target_due_date = order.due_date
    else:
        target_customer_due_date = payload.customer_due_date
        target_due_date = payload.due_date
    schedule_changed = (
        target_customer_due_date != order.customer_due_date
        or target_due_date != order.due_date
        or payload.note != order.note
    )
    if not structural_changed and not schedule_changed:
        raise HTTPException(status_code=422, detail="订单内容没有发生变化")
    if structural_changed and _order_has_business_activity(db, order):
        raise HTTPException(
            status_code=409,
            detail="订单已有收料或库存流水，只能修改客户交期、自动计划交期和备注",
        )

    before = {
        "revision": order.revision,
        "customer_code": order.customer_code,
        "contract_no": order.contract_no,
        "item_no": order.item_no,
        "product_order_quantity": order.product_order_quantity,
        "order_date": order.order_date,
        "customer_due_date": order.customer_due_date,
        "safety_lead_days": order.safety_lead_days,
        "due_date": order.due_date,
        "note": order.note,
        "lines": [_order_line_signature(line) for line in existing_lines],
    }
    if structural_changed:
        order.customer_code = target_customer_code
        order.customer_name = target_customer_name
        order.supplier_id = target_supplier_id
        order.supplier_name_snapshot = target_supplier_name
        order.contract_no = payload.contract_no
        order.item_no = payload.item_no
        order.product_name = payload.product_name
        order.product_order_quantity = payload.product_order_quantity
        order.order_date = payload.order_date
        for index, input_line in enumerate(payload.lines, start=1):
            required_quantity = required_carton_quantity(
                payload.product_order_quantity,
                input_line.usage_quantity,
            )
            if required_quantity <= 0:
                raise HTTPException(status_code=422, detail=f"第 {index} 行计算后的需求数量必须大于 0")
            line = existing_lines[index - 1] if index <= len(existing_lines) else CartonOrderLine(
                id=f"CTL-{uuid4().hex}",
                factory_id=factory_id,
                order_id=order.id,
                line_no=index,
            )
            line.line_no = index
            line.customer_code = target_customer_code
            line.contract_no = payload.contract_no
            line.item_no = payload.item_no
            line.packaging_type = input_line.packaging_type
            line.paper_quality = input_line.paper_quality
            line.specification = input_line.specification
            line.dimension_unit = input_line.dimension_unit
            line.usage_quantity = input_line.usage_quantity
            line.required_quantity = required_quantity
            line.unit = input_line.unit
            line.unit_price = input_line.unit_price
            line.currency = normalize_currency(input_line.currency)
            line.price_source = input_line.price_source
            line.note = input_line.note
            if index > len(existing_lines):
                db.add(line)
        for line in existing_lines[len(payload.lines):]:
            db.delete(line)

    order.customer_due_date = target_customer_due_date
    order.safety_lead_days = DEFAULT_CARTON_SAFETY_LEAD_DAYS
    order.due_date = target_due_date
    order.note = payload.note
    order.revision += 1
    order.updated_by = user.id
    order.updated_by_name = user.display_name
    order.updated_at = now_text()
    _audit(
        db,
        user,
        factory_id,
        "ORDER_UPDATED",
        "carton_order",
        order.id,
        {
            "order_no": order.order_no,
            "reason": payload.reason,
            "structural_changed": structural_changed,
            "before": before,
            "after": {
                "revision": order.revision,
                "customer_code": order.customer_code,
                "contract_no": order.contract_no,
                "item_no": order.item_no,
                "product_order_quantity": order.product_order_quantity,
                "order_date": order.order_date,
                "customer_due_date": order.customer_due_date,
                "safety_lead_days": order.safety_lead_days,
                "due_date": order.due_date,
                "note": order.note,
                "lines": target_line_signatures,
            },
        },
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="订单修改与现有业务数据冲突，请刷新后重试") from exc
    db.refresh(order)
    return order


def submit_order_to_supplier(
    db: Session,
    order_no: str,
    payload: CartonOrderSubmitRequest,
    user: AuthContext,
) -> CartonOrder:
    factory_id = require_carton_factory(payload.factory_id)
    order = get_order_by_no(db, factory_id, order_no)
    if order.revision != payload.expected_revision:
        raise HTTPException(status_code=409, detail="订单已被其他人更新，请刷新后重试")
    if order.status == "PENDING_SUPPLIER":
        raise HTTPException(status_code=409, detail="订单已经确认并锁定")
    if order.status != "CONFIRMED":
        raise HTTPException(status_code=409, detail="只有待下单且尚未确认锁定的订单可以确认")

    previous_status = order.status
    order.status = "PENDING_SUPPLIER"
    order.revision += 1
    order.updated_by = user.id
    order.updated_by_name = user.display_name
    order.updated_at = now_text()
    _audit(
        db,
        user,
        factory_id,
        "ORDER_SUBMITTED_SUPPLIER",
        "carton_order",
        order.id,
        {
            "order_no": order.order_no,
            "previous_status": previous_status,
            "status": order.status,
            "supplier_id": order.supplier_id,
            "supplier_name": order.supplier_name_snapshot,
            "revision": order.revision,
        },
    )
    db.commit()
    db.refresh(order)
    return order


def bulk_submit_orders_to_supplier(
    db: Session,
    payload: CartonOrderBulkSubmitRequest,
    user: AuthContext,
) -> list[CartonOrder]:
    factory_id = require_carton_factory(payload.factory_id)
    orders: list[CartonOrder] = []
    for item in payload.items:
        order = get_order_by_no(db, factory_id, item.order_no)
        if order.status != "CONFIRMED":
            continue
        if order.revision != item.expected_revision:
            raise HTTPException(status_code=409, detail=f"订单 {item.order_no} 已更新，请刷新后重试")
        orders.append(order)

    timestamp = now_text()
    for order in orders:
        previous_status = order.status
        order.status = "PENDING_SUPPLIER"
        order.revision += 1
        order.updated_by = user.id
        order.updated_by_name = user.display_name
        order.updated_at = timestamp
        _audit(
            db,
            user,
            factory_id,
            "ORDER_SUBMITTED_SUPPLIER",
            "carton_order",
            order.id,
            {
                "order_no": order.order_no,
                "previous_status": previous_status,
                "status": order.status,
                "supplier_id": order.supplier_id,
                "supplier_name": order.supplier_name_snapshot,
                "revision": order.revision,
                "bulk": True,
            },
        )

    db.commit()
    for order in orders:
        db.refresh(order)
    return orders


def cancel_order(
    db: Session,
    order_no: str,
    payload: CartonOrderCancelRequest,
    user: AuthContext,
) -> CartonOrder:
    factory_id = require_carton_factory(payload.factory_id)
    order = get_order_by_no(db, factory_id, order_no)
    if order.revision != payload.expected_revision:
        raise HTTPException(status_code=409, detail="订单已被其他人更新，请刷新后重试")
    if order.status not in {"DRAFT", "CONFIRMED"}:
        raise HTTPException(status_code=409, detail="订单已确认锁定或已结束，不能取消")
    if _order_has_business_activity(db, order):
        raise HTTPException(status_code=409, detail="订单已有收料或库存流水，不能取消")

    previous_status = order.status
    order.status = "CANCELLED"
    order.revision += 1
    order.updated_by = user.id
    order.updated_by_name = user.display_name
    order.updated_at = now_text()
    _audit(
        db,
        user,
        factory_id,
        "ORDER_CANCELLED",
        "carton_order",
        order.id,
        {
            "order_no": order.order_no,
            "reason": payload.reason,
            "previous_status": previous_status,
            "revision": order.revision,
        },
    )
    db.commit()
    db.refresh(order)
    return order


def append_order(
    db: Session,
    order_no: str,
    payload: CartonOrderAppendRequest,
    user: AuthContext,
) -> CartonOrder:
    factory_id = require_carton_factory(payload.factory_id)
    order = get_order_by_no(db, factory_id, order_no)
    if order.revision != payload.expected_revision:
        raise HTTPException(status_code=409, detail="订单已被其他人更新，请刷新后重试")
    if order.status not in {
        "CONFIRMED",
        "PENDING_SUPPLIER",
        "PARTIALLY_RECEIVED",
        "COMPLETED",
    }:
        raise HTTPException(status_code=409, detail="当前订单状态不能追加")
    if payload.customer_due_date:
        try:
            target_due_date = derive_carton_plan_due_date(
                order.order_date,
                payload.customer_due_date,
                DEFAULT_CARTON_SAFETY_LEAD_DAYS,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        target_customer_due_date = payload.customer_due_date
    else:
        if order.customer_due_date is not None and payload.due_date and payload.due_date != order.due_date:
            raise HTTPException(
                status_code=422,
                detail="已有客户交期的订单必须通过客户交期自动计算计划交期",
            )
        target_customer_due_date = order.customer_due_date
        target_due_date = payload.due_date or order.due_date
    if target_due_date < order.order_date:
        raise HTTPException(status_code=422, detail="计划交期不能早于下单日期")

    previous_status = order.status
    before_quantity = quantity(order.product_order_quantity)
    before_customer_due_date = order.customer_due_date
    before_due_date = order.due_date
    after_quantity = quantity(before_quantity + payload.additional_quantity)
    lines = _order_lines(db, order.id)
    before_required = {line.id: quantity(line.required_quantity) for line in lines}
    for line in lines:
        line.required_quantity = required_carton_quantity(after_quantity, line.usage_quantity)
    order.product_order_quantity = after_quantity
    if previous_status == "COMPLETED":
        order.status = "PARTIALLY_RECEIVED"
    order.customer_due_date = target_customer_due_date
    order.safety_lead_days = DEFAULT_CARTON_SAFETY_LEAD_DAYS
    order.due_date = target_due_date
    order.revision += 1
    order.updated_by = user.id
    order.updated_by_name = user.display_name
    order.updated_at = now_text()
    _audit(
        db,
        user,
        factory_id,
        "ORDER_APPENDED",
        "carton_order",
        order.id,
        {
            "order_no": order.order_no,
            "reason": payload.reason,
            "additional_quantity": payload.additional_quantity,
            "before_quantity": before_quantity,
            "after_quantity": after_quantity,
            "before_customer_due_date": before_customer_due_date,
            "after_customer_due_date": order.customer_due_date,
            "safety_lead_days": order.safety_lead_days,
            "before_due_date": before_due_date,
            "after_due_date": order.due_date,
            "before_required": before_required,
            "after_required": {line.id: quantity(line.required_quantity) for line in lines},
            "previous_status": previous_status,
            "status": order.status,
            "revision": order.revision,
        },
    )
    timestamp = now_text()
    db.add(
        CartonException(
            id=f"CEX-{uuid4().hex}",
            factory_id=factory_id,
            exception_no=_new_number("EX"),
            source_type="ORDER",
            source_id=order.id,
            category="ORDER_APPENDED",
            severity="MEDIUM",
            customer_code=order.customer_code,
            customer_name=order.customer_name,
            contract_no=order.contract_no,
            item_no=order.item_no,
            title=f"追加订单 {order.order_no} 待仓库复核",
            description=(
                f"产品订单数量由 {before_quantity} 追加 {payload.additional_quantity} 至 {after_quantity}；"
                f"原因：{payload.reason}"
            ),
            owner_department="纸箱仓",
            status="OPEN",
            resolution_note="",
            revision=1,
            created_by=user.id,
            created_by_name=user.display_name,
            updated_by=user.id,
            updated_by_name=user.display_name,
            created_at=timestamp,
            updated_at=timestamp,
            resolved_by="",
            resolved_by_name="",
            resolved_at="",
        )
    )
    db.commit()
    db.refresh(order)
    return order


def reduce_order(
    db: Session,
    order_no: str,
    payload: CartonOrderReduceRequest,
    user: AuthContext,
) -> CartonOrder:
    factory_id = require_carton_factory(payload.factory_id)
    order = get_order_by_no(db, factory_id, order_no)
    if order.revision != payload.expected_revision:
        raise HTTPException(status_code=409, detail="订单已被其他人更新，请刷新后重试")
    if order.status not in {"PENDING_SUPPLIER", "PARTIALLY_RECEIVED"}:
        raise HTTPException(status_code=409, detail="减单仅适用于已确认锁定或部分到货的订单")

    before_quantity = quantity(order.product_order_quantity)
    reduction_quantity = quantity(payload.reduction_quantity)
    if reduction_quantity > before_quantity:
        raise HTTPException(status_code=422, detail="减单数量不能超过当前订单数量")

    after_quantity = quantity(before_quantity - reduction_quantity)
    lines = _order_lines(db, order.id)
    line_ids = [line.id for line in lines]
    posted_received = _posted_received_by_line(db, line_ids)
    pending_received = _pending_received_by_line(db, line_ids)
    protected_quantity = {
        line.id: quantity(
            posted_received.get(line.id, Decimal(0))
            + pending_received.get(line.id, Decimal(0))
        )
        for line in lines
    }
    protected_product_quantity = _protected_product_quantity(
        db,
        order,
        lines,
        posted_received,
        pending_received,
    )
    before_required = {line.id: quantity(line.required_quantity) for line in lines}
    full_return = after_quantity == 0
    after_required = {
        line.id: (
            Decimal("0")
            if full_return
            else required_carton_quantity(after_quantity, line.usage_quantity)
        )
        for line in lines
    }
    protected_violations = [
        line
        for line in lines
        if after_required[line.id] < protected_quantity[line.id]
    ]
    if after_quantity < protected_product_quantity or protected_violations:
        details = "；".join(
            f"{line.packaging_type}调整后需求 {after_required[line.id]}，"
            f"已入库及待确认 {protected_quantity[line.id]}"
            for line in protected_violations
        )
        maximum_reduction = max(
            Decimal(0), quantity(before_quantity - protected_product_quantity)
        )
        raise HTTPException(
            status_code=409,
            detail=(
                f"减单数量超过尚未入库的可退范围，当前最大可减 {maximum_reduction}"
                + (f"：{details}" if details else "")
            ),
        )
    if not full_return:
        for line in lines:
            line.required_quantity = after_required[line.id]

    previous_status = order.status
    if full_return:
        # Cancelled orders retain their original contracted quantities as immutable
        # history. The zero operational balance is recorded in the audit event.
        order.status = "CANCELLED"
    else:
        order.product_order_quantity = after_quantity
        complete = bool(lines) and all(
            posted_received.get(line.id, Decimal(0)) >= after_required[line.id]
            for line in lines
        )
        order.status = "COMPLETED" if complete else (
            "PARTIALLY_RECEIVED"
            if sum(posted_received.values(), Decimal(0)) > 0
            else "PENDING_SUPPLIER"
        )
    order.revision += 1
    order.updated_by = user.id
    order.updated_by_name = user.display_name
    order.updated_at = now_text()
    _audit(
        db,
        user,
        factory_id,
        "ORDER_REDUCED",
        "carton_order",
        order.id,
        {
            "order_no": order.order_no,
            "reason": payload.reason,
            "reduction_quantity": reduction_quantity,
            "before_quantity": before_quantity,
            "after_quantity": after_quantity,
            "before_required": before_required,
            "after_required": after_required,
            "posted_received": posted_received,
            "pending_received": pending_received,
            "protected_quantity": protected_quantity,
            "protected_product_quantity": protected_product_quantity,
            "previous_status": previous_status,
            "status": order.status,
            "full_return": full_return,
            "revision": order.revision,
        },
    )
    db.commit()
    db.refresh(order)
    return order


def return_order(
    db: Session,
    order_no: str,
    payload: CartonOrderCancelRequest,
    user: AuthContext,
) -> CartonOrder:
    factory_id = require_carton_factory(payload.factory_id)
    order = get_order_by_no(db, factory_id, order_no)
    if order.revision != payload.expected_revision:
        raise HTTPException(status_code=409, detail="订单已被其他人更新，请刷新后重试")
    if order.status not in {"PARTIALLY_RECEIVED", "COMPLETED"}:
        raise HTTPException(status_code=409, detail="退单仅用于已发生入库的订单；未确认锁定的订单请取消，已确认锁定但未入库的订单不可取消")

    lines = _order_lines(db, order.id)
    line_ids = [line.id for line in lines]
    pending_receipts = list(
        db.scalars(
            select(CartonReceipt)
            .join(CartonReceiptLine, CartonReceiptLine.receipt_id == CartonReceipt.id)
            .where(
                CartonReceipt.factory_id == factory_id,
                CartonReceipt.status == "PENDING_CONFIRMATION",
                CartonReceiptLine.order_line_id.in_(line_ids),
            )
            .distinct()
        ).all()
    ) if line_ids else []
    if pending_receipts:
        pending_receipt_ids = [receipt.id for receipt in pending_receipts]
        cross_order_line = db.scalar(
            select(CartonReceiptLine.id)
            .where(
                CartonReceiptLine.receipt_id.in_(pending_receipt_ids),
                or_(
                    CartonReceiptLine.order_line_id.is_(None),
                    CartonReceiptLine.order_line_id.not_in(line_ids),
                ),
            )
            .limit(1)
        )
        if cross_order_line:
            raise HTTPException(
                status_code=409,
                detail="该订单存在与其他订单或非正式收料共用的待确认收料单；请先确认该收料单后再退单",
            )
    timestamp = now_text()
    for receipt in pending_receipts:
        receipt.status = "REVERSED"
        receipt.revision += 1
        receipt.updated_at = timestamp

    returned_quantities: dict[str, Decimal] = {}
    movement_ids: list[str] = []
    for line in lines:
        current = _inventory_balance_for_key(db, factory_id, line.id)
        if current <= 0:
            continue
        _ensure_period_open(db, factory_id, order.customer_code, timestamp)
        movement_id = f"CIM-{uuid4().hex}"
        db.add(
            CartonInventoryMovement(
                id=movement_id,
                factory_id=factory_id,
                order_line_id=line.id,
                customer_code=order.customer_code,
                customer_name=order.customer_name,
                contract_no=order.contract_no,
                item_no=order.item_no,
                packaging_type=line.packaging_type,
                paper_quality=line.paper_quality,
                specification=line.specification,
                movement_type="OUTBOUND",
                quantity=quantity(-current),
                unit=line.unit,
                unit_price=line.unit_price,
                currency=line.currency,
                location="",
                document_no=f"RET-{order.order_no}",
                source_type="ORDER_RETURN",
                source_id=order.id,
                source_line_id=f"{order.id}:{line.id}:{order.revision + 1}",
                reversal_of_movement_id=None,
                reason=payload.reason,
                actor_user_id=user.id,
                actor_name=user.display_name,
                occurred_at=timestamp,
            )
        )
        returned_quantities[line.id] = quantity(current)
        movement_ids.append(movement_id)

    previous_status = order.status
    order.status = "CANCELLED"
    order.revision += 1
    order.updated_by = user.id
    order.updated_by_name = user.display_name
    order.updated_at = timestamp
    _audit(
        db,
        user,
        factory_id,
        "ORDER_RETURNED",
        "carton_order",
        order.id,
        {
            "order_no": order.order_no,
            "reason": payload.reason,
            "previous_status": previous_status,
            "voided_pending_receipt_count": len(pending_receipts),
            "returned_quantities": returned_quantities,
            "movement_ids": movement_ids,
            "revision": order.revision,
        },
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="退单库存流水冲突，请刷新后重试") from exc
    db.refresh(order)
    return order


def bulk_cancel_orders(
    db: Session,
    payload: CartonOrderBulkCancelRequest,
    user: AuthContext,
) -> list[CartonOrder]:
    factory_id = require_carton_factory(payload.factory_id)
    orders: list[CartonOrder] = []
    for item in payload.items:
        order = get_order_by_no(db, factory_id, item.order_no)
        if order.revision != item.expected_revision:
            raise HTTPException(status_code=409, detail=f"订单 {item.order_no} 已更新，请刷新后重试")
        if order.status not in {"DRAFT", "CONFIRMED"}:
            raise HTTPException(status_code=409, detail=f"订单 {item.order_no} 已确认锁定或已结束，不能批量取消")
        if _order_has_business_activity(db, order):
            raise HTTPException(status_code=409, detail=f"订单 {item.order_no} 已有收料或库存流水，不能批量取消")
        orders.append(order)

    timestamp = now_text()
    for order in orders:
        previous_status = order.status
        order.status = "CANCELLED"
        order.revision += 1
        order.updated_by = user.id
        order.updated_by_name = user.display_name
        order.updated_at = timestamp
        _audit(
            db,
            user,
            factory_id,
            "ORDER_CANCELLED",
            "carton_order",
            order.id,
            {
                "reason": payload.reason,
                "previous_status": previous_status,
                "revision": order.revision,
                "bulk": True,
            },
        )
    db.commit()
    for order in orders:
        db.refresh(order)
    return orders


def _pending_received_by_line(db: Session, line_ids: list[str]) -> dict[str, Decimal]:
    if not line_ids:
        return {}
    rows = db.execute(
        select(
            CartonReceiptLine.order_line_id,
            func.coalesce(func.sum(CartonReceiptLine.effective_quantity), 0),
        )
        .join(CartonReceipt, CartonReceipt.id == CartonReceiptLine.receipt_id)
        .where(
            CartonReceipt.status == "PENDING_CONFIRMATION",
            CartonReceiptLine.order_line_id.in_(line_ids),
        )
        .group_by(CartonReceiptLine.order_line_id)
    ).all()
    return {line_id: quantity(total) for line_id, total in rows}


def _posted_received_by_line(db: Session, line_ids: list[str]) -> dict[str, Decimal]:
    if not line_ids:
        return {}
    rows = db.execute(
        select(
            CartonReceiptLine.order_line_id,
            func.coalesce(func.sum(CartonReceiptLine.effective_quantity), 0),
        )
        .join(CartonReceipt, CartonReceipt.id == CartonReceiptLine.receipt_id)
        .where(
            CartonReceipt.status == "POSTED",
            CartonReceiptLine.order_line_id.in_(line_ids),
        )
        .group_by(CartonReceiptLine.order_line_id)
    ).all()
    return {line_id: quantity(total) for line_id, total in rows}


def _latest_completed_append_baseline(
    db: Session,
    order_id: str,
) -> tuple[Decimal, dict[str, Decimal]] | None:
    detail_rows = db.scalars(
        select(CartonAuditEvent.detail_json)
        .where(
            CartonAuditEvent.entity_type == "carton_order",
            CartonAuditEvent.entity_id == order_id,
            CartonAuditEvent.event_type == "ORDER_APPENDED",
        )
        .order_by(CartonAuditEvent.sequence.desc())
    ).all()
    for detail_json in detail_rows:
        try:
            detail = json.loads(detail_json or "{}")
        except (TypeError, ValueError):
            continue
        if detail.get("previous_status") != "COMPLETED":
            continue
        try:
            baseline_quantity = quantity(Decimal(str(detail["before_quantity"])))
            before_required = {
                str(line_id): quantity(Decimal(str(value)))
                for line_id, value in (detail.get("before_required") or {}).items()
            }
        except (KeyError, TypeError, ValueError):
            continue
        return baseline_quantity, before_required
    return None


def _protected_product_quantity(
    db: Session,
    order: CartonOrder,
    lines: list[CartonOrderLine],
    posted_received: dict[str, Decimal],
    pending_received: dict[str, Decimal],
) -> Decimal:
    current_quantity = quantity(order.product_order_quantity)
    protected_cartons = {
        line.id: quantity(
            posted_received.get(line.id, Decimal(0))
            + pending_received.get(line.id, Decimal(0))
        )
        for line in lines
    }
    if not any(amount > 0 for amount in protected_cartons.values()):
        return Decimal(0)

    completed_append_baseline = _latest_completed_append_baseline(db, order.id)
    protected_candidates: list[Decimal] = []
    for line in lines:
        received_cartons = protected_cartons[line.id]
        if received_cartons <= 0:
            continue
        units_per_carton = quantity(line.usage_quantity)
        if completed_append_baseline is None:
            protected_candidates.append(quantity(received_cartons * units_per_carton))
            continue

        baseline_quantity, baseline_required = completed_append_baseline
        original_cartons = baseline_required.get(
            line.id,
            required_carton_quantity(baseline_quantity, units_per_carton),
        )
        if received_cartons >= original_cartons:
            extra_received_cartons = received_cartons - original_cartons
            protected_candidates.append(
                quantity(baseline_quantity + extra_received_cartons * units_per_carton)
            )
        else:
            # A later receipt reversal can make part of the old completed balance
            # unprotected again; in that case only the cartons still posted count.
            protected_candidates.append(quantity(received_cartons * units_per_carton))

    if not protected_candidates:
        return Decimal(0)
    return min(current_quantity, max(protected_candidates))


def order_out(db: Session, order: CartonOrder) -> CartonOrderOut:
    lines = _order_lines(db, order.id)
    line_ids = [line.id for line in lines]
    received = _posted_received_by_line(db, line_ids)
    pending_received = _pending_received_by_line(db, line_ids)
    protected_product_quantity = _protected_product_quantity(
        db,
        order,
        lines,
        received,
        pending_received,
    )
    return CartonOrderOut(
        id=order.id,
        factory_id=order.factory_id,
        order_no=order.order_no,
        customer_code=order.customer_code,
        customer_name=order.customer_name,
        supplier_id=order.supplier_id,
        supplier_name=order.supplier_name_snapshot,
        contract_no=order.contract_no,
        item_no=order.item_no,
        product_name=order.product_name,
        product_order_quantity=order.product_order_quantity,
        order_date=order.order_date,
        customer_due_date=order.customer_due_date,
        safety_lead_days=order.safety_lead_days,
        due_date=order.due_date,
        status=order.status,
        note=order.note,
        revision=order.revision,
        created_by=order.created_by,
        created_by_name=order.created_by_name,
        updated_by=order.updated_by,
        updated_by_name=order.updated_by_name,
        created_at=order.created_at,
        updated_at=order.updated_at,
        maximum_reducible_quantity=max(
            Decimal(0),
            quantity(order.product_order_quantity - protected_product_quantity),
        ),
        lines=[
            CartonOrderLineOut(
                id=line.id,
                line_no=line.line_no,
                packaging_type=line.packaging_type,
                paper_quality=line.paper_quality,
                specification=line.specification,
                dimension_unit=line.dimension_unit,
                usage_quantity=line.usage_quantity,
                required_quantity=line.required_quantity,
                received_quantity=received.get(line.id, Decimal(0)),
                remaining_quantity=max(
                    Decimal(0), quantity(line.required_quantity - received.get(line.id, Decimal(0)))
                ),
                unit=line.unit,
                unit_price=line.unit_price,
                currency=line.currency,
                price_source=line.price_source,
                note=line.note,
            )
            for line in lines
        ],
    )


def list_orders(
    db: Session,
    factory_id: str,
    *,
    customer_code: str = "",
    search: str = "",
    status_filter: str = "",
    due_from: str = "",
    due_to: str = "",
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[CartonOrder]]:
    query = select(CartonOrder).where(CartonOrder.factory_id == factory_id)
    if customer_code:
        query = query.where(CartonOrder.customer_code == customer_code)
    if status_filter:
        query = query.where(CartonOrder.status == status_filter)
    if due_from:
        query = query.where(CartonOrder.due_date >= due_from)
    if due_to:
        query = query.where(CartonOrder.due_date <= due_to)
    if search:
        pattern = f"%{search}%"
        query = query.where(
            or_(
                CartonOrder.order_no.ilike(pattern),
                CartonOrder.customer_name.ilike(pattern),
                CartonOrder.contract_no.ilike(pattern),
                CartonOrder.item_no.ilike(pattern),
                CartonOrder.product_name.ilike(pattern),
            )
        )
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = list(
        db.scalars(
            query.order_by(CartonOrder.order_date.desc(), CartonOrder.created_at.desc())
            .limit(limit)
            .offset(offset)
        ).all()
    )
    return int(total), rows


def _normalized_item_no(value: str) -> str:
    return re.sub(r"[\s._/#()（）+&-]+", "", value).casefold()


def _history_item_match(query: str, candidate: str) -> tuple[str, int] | None:
    if candidate == query:
        return "EXACT", 1000
    length_penalty = min(abs(len(candidate) - len(query)), 25)
    if candidate.startswith(query):
        return "PREFIX", 900 - length_penalty
    if query in candidate:
        return "CONTAINS", 800 - length_penalty
    ratio = SequenceMatcher(None, query, candidate).ratio()
    if ratio < 0.5:
        return None
    return "SIMILAR", int(ratio * 700) - length_penalty


def search_order_history_items(
    db: Session,
    factory_id: str,
    item_no: str,
    *,
    customer_code: str = "",
    limit: int = 8,
) -> list[CartonOrderHistorySuggestionOut]:
    factory_id = require_carton_factory(factory_id)
    raw_query = item_no.strip()
    normalized_query = _normalized_item_no(raw_query)
    if not normalized_query:
        raise HTTPException(status_code=422, detail="请输入要查找的历史货号")

    active_customers = dict(
        db.execute(
            select(CartonCustomer.customer_code, CartonCustomer.customer_name).where(
                CartonCustomer.factory_id == factory_id,
                CartonCustomer.status == "ACTIVE",
            )
        ).all()
    )
    if not active_customers:
        return []

    recent_orders = list(
        db.scalars(
            select(CartonOrder)
            .where(
                CartonOrder.factory_id == factory_id,
                CartonOrder.status != "CANCELLED",
                CartonOrder.customer_code.in_(list(active_customers)),
            )
            .order_by(CartonOrder.order_date.desc(), CartonOrder.created_at.desc())
            .limit(5000)
        ).all()
    )
    grouped: dict[tuple[str, str], dict[str, object]] = {}
    for order in recent_orders:
        key = (order.customer_code, order.item_no)
        if key not in grouped:
            grouped[key] = {"order": order, "order_count": 0}
        grouped[key]["order_count"] = int(grouped[key]["order_count"]) + 1

    preferred_customer = customer_code.strip()
    ranked: list[tuple[int, str, str, CartonOrder, int]] = []
    for (candidate_customer, candidate_item_no), group in grouped.items():
        matched = _history_item_match(
            normalized_query,
            _normalized_item_no(candidate_item_no),
        )
        if matched is None:
            continue
        match_type, score = matched
        if preferred_customer and candidate_customer == preferred_customer:
            score += 25
        order = group["order"]
        assert isinstance(order, CartonOrder)
        ranked.append(
            (
                score,
                order.order_date,
                order.created_at,
                order,
                int(group["order_count"]),
            )
        )
    ranked.sort(key=lambda row: (row[0], row[1], row[2]), reverse=True)
    selected = ranked[:limit]
    selected_order_ids = [row[3].id for row in selected]
    lines_by_order: dict[str, list[CartonOrderLine]] = defaultdict(list)
    if selected_order_ids:
        for line in db.scalars(
            select(CartonOrderLine)
            .where(CartonOrderLine.order_id.in_(selected_order_ids))
            .order_by(CartonOrderLine.order_id, CartonOrderLine.line_no)
        ).all():
            lines_by_order[line.order_id].append(line)

    suggestions: list[CartonOrderHistorySuggestionOut] = []
    for score, _order_date, _created_at, order, order_count in selected:
        matched = _history_item_match(normalized_query, _normalized_item_no(order.item_no))
        assert matched is not None
        match_type, _ = matched
        suggestions.append(
            CartonOrderHistorySuggestionOut(
                item_no=order.item_no,
                customer_code=order.customer_code,
                customer_name=active_customers[order.customer_code],
                product_name=order.product_name,
                latest_order_no=order.order_no,
                latest_contract_no=order.contract_no,
                latest_order_date=order.order_date,
                latest_product_order_quantity=order.product_order_quantity,
                order_count=order_count,
                match_type=match_type,
                match_score=score,
                lines=[
                    CartonOrderHistoryLineOut(
                        line_no=line.line_no,
                        packaging_type=line.packaging_type,
                        paper_quality=line.paper_quality,
                        specification=line.specification,
                        dimension_unit=line.dimension_unit,
                        usage_quantity=line.usage_quantity,
                        unit=line.unit,
                        unit_price=line.unit_price,
                        currency=line.currency,
                        price_source=line.price_source,
                        note=line.note,
                    )
                    for line in lines_by_order[order.id]
                ],
            )
        )
    return suggestions


def create_receipt(db: Session, payload: CartonReceiptCreate, user: AuthContext) -> CartonReceipt:
    factory_id = require_carton_factory(payload.factory_id)
    supplier = get_active_supplier(db, factory_id, payload.supplier_id)
    formal_inputs = [line for line in payload.lines if line.source_type == "FORMAL_ORDER"]
    line_ids = [line.order_line_id for line in formal_inputs if line.order_line_id]
    if len(line_ids) != len(set(line_ids)):
        raise HTTPException(status_code=422, detail="同一张收料单不能重复填写同一订单明细")
    order_lines = list(db.scalars(
        select(CartonOrderLine).where(
            CartonOrderLine.factory_id == factory_id,
            CartonOrderLine.id.in_(line_ids),
        )
    ).all()) if line_ids else []
    by_id = {line.id: line for line in order_lines}
    if len(by_id) != len(line_ids):
        raise HTTPException(status_code=422, detail="存在不属于当前厂区或不存在的纸箱订单明细")
    orders = {
        order.id: order
        for order in db.scalars(
            select(CartonOrder).where(CartonOrder.id.in_({line.order_id for line in order_lines}))
        ).all()
    }
    ineligible_orders = [
        order.order_no
        for order in orders.values()
        if order.status not in {"PENDING_SUPPLIER", "PARTIALLY_RECEIVED"}
    ]
    if ineligible_orders:
        raise HTTPException(
            status_code=409,
            detail=f"订单 {', '.join(sorted(ineligible_orders))} 必须先确认并锁定，且保持待收料状态，才能登记收料",
        )
    ad_hoc_customers = {
        customer_code: get_active_customer(db, factory_id, customer_code)
        for customer_code in {
            line.customer_code
            for line in payload.lines
            if line.source_type == "AD_HOC"
        }
    }

    receipt_id = f"CTR-{uuid4().hex}"
    timestamp = now_text()
    receipt = CartonReceipt(
        id=receipt_id,
        factory_id=factory_id,
        receipt_no=_new_number("RC"),
        delivery_note_no=payload.delivery_note_no,
        delivery_date=payload.delivery_date,
        supplier_id=supplier.id,
        supplier_name_snapshot=supplier.supplier_name,
        import_batch_id=payload.import_batch_id,
        status="PENDING_CONFIRMATION",
        note=payload.note,
        revision=1,
        created_by=user.id,
        created_by_name=user.display_name,
        confirmed_by="",
        confirmed_by_name="",
        created_at=timestamp,
        updated_at=timestamp,
        confirmed_at="",
    )
    db.add(receipt)
    for index, input_line in enumerate(payload.lines, start=1):
        effective = quantity(
            input_line.received_quantity
            - input_line.damaged_quantity
            - input_line.rejected_quantity
            - input_line.unusable_quantity
        )
        if input_line.source_type == "FORMAL_ORDER":
            if input_line.order_line_id is None:
                raise HTTPException(status_code=422, detail="正式订单收料必须关联订单明细")
            order_line = by_id[input_line.order_line_id]
            order = orders[order_line.order_id]
            snapshot = {
                "order_line_id": order_line.id,
                "customer_code": order.customer_code,
                "customer_name": order.customer_name,
                "contract_no": order.contract_no,
                "item_no": order.item_no,
                "packaging_type": order_line.packaging_type,
                "paper_quality": order_line.paper_quality,
                "specification": order_line.specification,
                "unit": order_line.unit,
                "unit_price": (
                    input_line.unit_price
                    if input_line.unit_price is not None
                    else order_line.unit_price
                ),
                "currency": order_line.currency,
            }
        else:
            customer = ad_hoc_customers[input_line.customer_code]
            snapshot = {
                "order_line_id": None,
                "customer_code": customer.customer_code,
                "customer_name": customer.customer_name,
                "contract_no": input_line.contract_no or payload.delivery_note_no,
                "item_no": input_line.item_no,
                "packaging_type": input_line.packaging_type,
                "paper_quality": input_line.paper_quality,
                "specification": input_line.specification,
                "unit": input_line.unit,
                "unit_price": input_line.unit_price or Decimal(0),
                "currency": normalize_currency(input_line.currency),
            }
        db.add(
            CartonReceiptLine(
                id=f"CRL-{uuid4().hex}",
                factory_id=factory_id,
                receipt_id=receipt_id,
                line_no=index,
                source_type=input_line.source_type,
                order_line_id=snapshot["order_line_id"],
                customer_code=snapshot["customer_code"],
                customer_name=snapshot["customer_name"],
                contract_no=snapshot["contract_no"],
                item_no=snapshot["item_no"],
                packaging_type=snapshot["packaging_type"],
                paper_quality=snapshot["paper_quality"],
                specification=snapshot["specification"],
                delivered_quantity=input_line.delivered_quantity,
                received_quantity=input_line.received_quantity,
                damaged_quantity=input_line.damaged_quantity,
                rejected_quantity=input_line.rejected_quantity,
                unusable_quantity=input_line.unusable_quantity,
                effective_quantity=effective,
                unit=snapshot["unit"],
                unit_price=snapshot["unit_price"],
                currency=snapshot["currency"],
                location=input_line.location,
                feedback_note=input_line.feedback_note,
            )
        )
    _audit(
        db,
        user,
        factory_id,
        "RECEIPT_DRAFT_CREATED",
        "carton_receipt",
        receipt_id,
        {
            "delivery_note_no": payload.delivery_note_no,
            "line_count": len(payload.lines),
            "formal_order_line_count": len(formal_inputs),
            "ad_hoc_line_count": len(payload.lines) - len(formal_inputs),
            "inventory_posted": False,
        },
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="该供应商送货单号已经登记") from exc
    db.refresh(receipt)
    return receipt


def _receipt_lines(db: Session, receipt_id: str) -> list[CartonReceiptLine]:
    return list(
        db.scalars(
            select(CartonReceiptLine)
            .where(CartonReceiptLine.receipt_id == receipt_id)
            .order_by(CartonReceiptLine.line_no)
        ).all()
    )


def receipt_out(db: Session, receipt: CartonReceipt) -> CartonReceiptOut:
    return CartonReceiptOut(
        id=receipt.id,
        factory_id=receipt.factory_id,
        receipt_no=receipt.receipt_no,
        delivery_note_no=receipt.delivery_note_no,
        delivery_date=receipt.delivery_date,
        supplier_id=receipt.supplier_id,
        supplier_name=receipt.supplier_name_snapshot,
        import_batch_id=receipt.import_batch_id,
        status=receipt.status,
        note=receipt.note,
        revision=receipt.revision,
        created_by=receipt.created_by,
        created_by_name=receipt.created_by_name,
        confirmed_by=receipt.confirmed_by,
        confirmed_by_name=receipt.confirmed_by_name,
        created_at=receipt.created_at,
        updated_at=receipt.updated_at,
        confirmed_at=receipt.confirmed_at,
        lines=[CartonReceiptLineOut.model_validate(line) for line in _receipt_lines(db, receipt.id)],
    )


def list_receipts(
    db: Session,
    factory_id: str,
    *,
    customer_code: str = "",
    search: str = "",
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[CartonReceipt]]:
    query = select(CartonReceipt).where(CartonReceipt.factory_id == factory_id)
    if customer_code or search:
        line_query = select(CartonReceiptLine.receipt_id).where(CartonReceiptLine.factory_id == factory_id)
        if customer_code:
            line_query = line_query.where(CartonReceiptLine.customer_code == customer_code)
        if search:
            pattern = f"%{search}%"
            line_query = line_query.where(
                or_(
                    CartonReceiptLine.customer_name.ilike(pattern),
                    CartonReceiptLine.contract_no.ilike(pattern),
                    CartonReceiptLine.item_no.ilike(pattern),
                    CartonReceiptLine.packaging_type.ilike(pattern),
                )
            )
        if search:
            pattern = f"%{search}%"
            query = query.where(
                or_(
                    CartonReceipt.id.in_(line_query),
                    CartonReceipt.receipt_no.ilike(pattern),
                    CartonReceipt.delivery_note_no.ilike(pattern),
                )
            )
        else:
            query = query.where(CartonReceipt.id.in_(line_query))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = list(
        db.scalars(
            query.order_by(CartonReceipt.delivery_date.desc(), CartonReceipt.created_at.desc())
            .limit(limit)
            .offset(offset)
        ).all()
    )
    return int(total), rows


def _ensure_period_open(db: Session, factory_id: str, customer_code: str, occurred_at: str) -> None:
    period = occurred_at[:7]
    locked = db.scalar(
        select(CartonClosing.id).where(
            CartonClosing.factory_id == factory_id,
            CartonClosing.customer_code == customer_code,
            CartonClosing.period == period,
            CartonClosing.status == "LOCKED",
        )
    )
    if locked:
        raise HTTPException(status_code=409, detail=f"{period} 已锁账，不能新增或冲销库存流水")


def _refresh_order_statuses(db: Session, order_ids: set[str], user: AuthContext) -> None:
    for order_id in order_ids:
        order = db.get(CartonOrder, order_id)
        if order is None or order.status == "CANCELLED":
            continue
        lines = _order_lines(db, order.id)
        received = _posted_received_by_line(db, [line.id for line in lines])
        total_received = sum(received.values(), Decimal(0))
        complete = bool(lines) and all(received.get(line.id, Decimal(0)) >= line.required_quantity for line in lines)
        new_status = "COMPLETED" if complete else "PARTIALLY_RECEIVED" if total_received > 0 else order.status
        if new_status != order.status:
            order.status = new_status
            order.revision += 1
            order.updated_by = user.id
            order.updated_by_name = user.display_name
            order.updated_at = now_text()


def confirm_receipt(
    db: Session,
    receipt_id: str,
    payload: CartonReceiptConfirmRequest,
    user: AuthContext,
) -> CartonReceipt:
    factory_id = require_carton_factory(payload.factory_id)
    receipt = db.get(CartonReceipt, receipt_id)
    if receipt is None or receipt.factory_id != factory_id:
        raise HTTPException(status_code=404, detail="收料单不存在")
    if receipt.status == "POSTED":
        return receipt
    if receipt.status != "PENDING_CONFIRMATION":
        raise HTTPException(status_code=409, detail="当前收料单状态不能确认")
    if receipt.revision != payload.expected_revision:
        raise HTTPException(status_code=409, detail="收料单已被其他人更新，请刷新后重试")
    lines = _receipt_lines(db, receipt.id)
    if not lines:
        raise HTTPException(status_code=409, detail="收料单没有可确认的明细")
    timestamp = now_text()
    formal_lines = [line for line in lines if line.source_type == "FORMAL_ORDER"]
    order_line_ids = [line.order_line_id for line in formal_lines if line.order_line_id]
    if len(order_line_ids) != len(formal_lines):
        raise HTTPException(status_code=409, detail="正式收料明细缺少订单关联，请联系管理员修复数据")
    order_lines = {
        line.id: line
        for line in db.scalars(
            select(CartonOrderLine).where(
                CartonOrderLine.factory_id == factory_id,
                CartonOrderLine.id.in_(order_line_ids),
            )
        ).all()
    } if order_line_ids else {}
    if len(order_lines) != len(order_line_ids):
        raise HTTPException(status_code=409, detail="收料单关联的订单明细已不存在")
    receipt_orders = {
        order.id: order
        for order in db.scalars(
            select(CartonOrder).where(CartonOrder.id.in_({line.order_id for line in order_lines.values()}))
        ).all()
    }
    ineligible_orders = [
        order.order_no
        for order in receipt_orders.values()
        if order.status not in {"PENDING_SUPPLIER", "PARTIALLY_RECEIVED"}
    ]
    if ineligible_orders:
        raise HTTPException(
            status_code=409,
            detail=f"订单 {', '.join(sorted(ineligible_orders))} 当前未处于已确认锁定的待收料状态，不能确认入库",
        )
    order_ids: set[str] = set()
    for line in lines:
        _ensure_period_open(db, factory_id, line.customer_code, timestamp)
        if line.source_type == "FORMAL_ORDER":
            order_line = order_lines[line.order_line_id]
            order_ids.add(order_line.order_id)
        if line.effective_quantity <= 0:
            continue
        db.add(
            CartonInventoryMovement(
                id=f"CIM-{uuid4().hex}",
                factory_id=factory_id,
                order_line_id=line.order_line_id,
                customer_code=line.customer_code,
                customer_name=line.customer_name,
                contract_no=line.contract_no,
                item_no=line.item_no,
                packaging_type=line.packaging_type,
                paper_quality=line.paper_quality,
                specification=line.specification,
                movement_type="INBOUND",
                quantity=line.effective_quantity,
                unit=line.unit,
                unit_price=line.unit_price,
                currency=line.currency,
                location=line.location,
                document_no=receipt.delivery_note_no,
                source_type="RECEIPT",
                source_id=receipt.id,
                source_line_id=line.id,
                reversal_of_movement_id=None,
                reason=(
                    "非正式/打板收料经人工确认后入库"
                    if line.source_type == "AD_HOC"
                    else "正式订单收料经人工确认后入库"
                ),
                actor_user_id=user.id,
                actor_name=user.display_name,
                occurred_at=timestamp,
            )
        )
    receipt.status = "POSTED"
    receipt.revision += 1
    receipt.confirmed_by = user.id
    receipt.confirmed_by_name = user.display_name
    receipt.confirmed_at = timestamp
    receipt.updated_at = timestamp
    if receipt.import_batch_id:
        import_batch = db.get(CartonImportBatch, receipt.import_batch_id)
        if import_batch is not None and import_batch.factory_id == factory_id:
            import_batch.status = "CONFIRMED"
    db.flush()
    _refresh_order_statuses(db, order_ids, user)
    _audit(
        db,
        user,
        factory_id,
        "RECEIPT_CONFIRMED",
        "carton_receipt",
        receipt.id,
        {
            "delivery_note_no": receipt.delivery_note_no,
            "movement_count": sum(1 for line in lines if line.effective_quantity > 0),
            "formal_order_line_count": len(formal_lines),
            "ad_hoc_line_count": len(lines) - len(formal_lines),
            "included_in_month_end": True,
        },
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="该收料单已确认或库存流水已生成") from exc
    db.refresh(receipt)
    return receipt


def _movement_key(movement: CartonInventoryMovement) -> str:
    return movement.order_line_id or "|".join(
        (
            movement.customer_code,
            movement.contract_no,
            movement.item_no,
            movement.packaging_type,
            movement.paper_quality,
            movement.specification,
            movement.unit,
        )
    )


def _inventory_balance_for_key(
    db: Session,
    factory_id: str,
    movement_key: str,
) -> Decimal:
    return sum(
        (
            row.quantity
            for row in db.scalars(
                select(CartonInventoryMovement).where(
                    CartonInventoryMovement.factory_id == factory_id
                )
            ).all()
            if _movement_key(row) == movement_key
        ),
        Decimal(0),
    )


def _movement_out(movement: CartonInventoryMovement, balance: Decimal) -> CartonInventoryMovementOut:
    return CartonInventoryMovementOut(
        **{
            column: getattr(movement, column)
            for column in CartonInventoryMovementOut.model_fields
            if column != "balance"
        },
        balance=quantity(balance),
    )


def list_movements(
    db: Session,
    factory_id: str,
    *,
    customer_code: str = "",
    search: str = "",
    limit: int = 100,
    offset: int = 0,
) -> tuple[int, list[CartonInventoryMovementOut]]:
    all_rows = list(
        db.scalars(
            select(CartonInventoryMovement)
            .where(CartonInventoryMovement.factory_id == factory_id)
            .order_by(CartonInventoryMovement.occurred_at, CartonInventoryMovement.id)
        ).all()
    )
    balances: dict[str, Decimal] = defaultdict(Decimal)
    with_balances: list[CartonInventoryMovementOut] = []
    normalized_search = search.lower()
    for row in all_rows:
        key = _movement_key(row)
        balances[key] += row.quantity
        if customer_code and row.customer_code != customer_code:
            continue
        if normalized_search and normalized_search not in " ".join(
            (
                row.document_no,
                row.customer_name,
                row.contract_no,
                row.item_no,
                row.packaging_type,
                row.paper_quality,
                row.specification,
                row.location,
            )
        ).lower():
            continue
        with_balances.append(_movement_out(row, balances[key]))
    with_balances.reverse()
    return len(with_balances), with_balances[offset : offset + limit]


def _inventory_locations(db: Session, factory_id: str) -> dict[str, tuple[str, int]]:
    locations: dict[str, tuple[str, int]] = {}
    for event in db.scalars(
        select(CartonAuditEvent).where(
            CartonAuditEvent.factory_id == factory_id,
            CartonAuditEvent.event_type == "INVENTORY_LOCATION_CHANGED",
        ).order_by(CartonAuditEvent.sequence)
    ):
        detail = json.loads(event.detail_json)
        locations[detail["inventory_key"]] = (detail["to_location"], event.sequence)
    return locations


def inventory_balances(
    db: Session,
    factory_id: str,
    *,
    customer_code: str = "",
) -> list[CartonInventoryBalanceOut]:
    rows = list(
        db.scalars(
            select(CartonInventoryMovement)
            .where(CartonInventoryMovement.factory_id == factory_id)
            .order_by(CartonInventoryMovement.occurred_at, CartonInventoryMovement.id)
        ).all()
    )
    totals: dict[str, Decimal] = defaultdict(Decimal)
    latest: dict[str, CartonInventoryMovement] = {}
    latest_inbound: dict[str, str] = {}
    locations = _inventory_locations(db, factory_id)
    for row in rows:
        if customer_code and row.customer_code != customer_code:
            continue
        key = _movement_key(row)
        totals[key] += row.quantity
        latest[key] = row
        if row.movement_type == "INBOUND":
            latest_inbound[key] = row.occurred_at
    return [
        CartonInventoryBalanceOut(
            factory_id=row.factory_id,
            customer_code=row.customer_code,
            customer_name=row.customer_name,
            contract_no=row.contract_no,
            item_no=row.item_no,
            order_line_id=row.order_line_id,
            packaging_type=row.packaging_type,
            paper_quality=row.paper_quality,
            specification=row.specification,
            unit=row.unit,
            balance=quantity(totals[key]),
            latest_location=locations.get(key, (row.location, 0))[0],
            location_revision=locations.get(key, (row.location, 0))[1],
            latest_movement_id=row.id,
            latest_document_no=row.document_no,
            latest_movement_at=row.occurred_at,
            latest_inbound_at=latest_inbound.get(key),
        )
        for key, row in latest.items()
    ]


def relocate_inventory(
    db: Session, payload: CartonInventoryRelocateRequest, user: AuthContext,
) -> CartonInventoryBalanceOut:
    factory_id = require_carton_factory(payload.factory_id)
    # Serialize location revisions per factory on both SQLite and PostgreSQL.
    locked = db.execute(
        update(CartonSupplier).where(CartonSupplier.factory_id == factory_id)
        .values(updated_at=CartonSupplier.updated_at)
    )
    if not locked.rowcount:
        raise HTTPException(status_code=409, detail="当前厂区尚未初始化库存服务")
    reference = db.get(CartonInventoryMovement, payload.reference_movement_id)
    if reference is None or reference.factory_id != factory_id:
        raise HTTPException(status_code=404, detail="库存结存记录不存在")
    balance = next((row for row in inventory_balances(db, factory_id)
                    if row.latest_movement_id == reference.id), None)
    if balance is None or balance.location_revision != payload.expected_location_revision:
        raise HTTPException(status_code=409, detail="库存或仓位已更新，请刷新后重新调仓")
    if balance.balance <= 0:
        raise HTTPException(status_code=409, detail="当前没有可调仓的库存")
    if payload.location == balance.latest_location:
        raise HTTPException(status_code=422, detail="目标仓位与当前仓位相同")
    key = _movement_key(reference)
    _audit(db, user, factory_id, "INVENTORY_LOCATION_CHANGED", "carton_inventory_location",
           f"INV-{hashlib.sha256(key.encode()).hexdigest()}", {
               "inventory_key": key, "reference_movement_id": reference.id,
               "customer_name": balance.customer_name, "contract_no": balance.contract_no,
               "item_no": balance.item_no, "quantity": balance.balance, "unit": balance.unit,
               "from_location": balance.latest_location, "to_location": payload.location,
               "reason": payload.note or "整条库存调仓",
           })
    db.flush()
    result = balance.model_copy(update={
        "latest_location": payload.location,
        "location_revision": _inventory_locations(db, factory_id)[key][1],
    })
    db.commit()
    return result


def _prepare_inventory_movement(
    db: Session,
    payload: CartonInventoryMovementCreate,
    user: AuthContext,
) -> tuple[CartonInventoryMovement, Decimal]:
    factory_id = require_carton_factory(payload.factory_id)
    order_line: CartonOrderLine | None = None
    reference: CartonInventoryMovement | None = None
    if payload.order_line_id:
        order_line = db.get(CartonOrderLine, payload.order_line_id)
        if order_line is None or order_line.factory_id != factory_id:
            raise HTTPException(status_code=404, detail="纸箱订单明细不存在")
        order = db.get(CartonOrder, order_line.order_id)
        if order is None:
            raise HTTPException(status_code=409, detail="纸箱订单主记录不存在")
        movement_key = order_line.id
        customer_code = order.customer_code
        customer_name = order.customer_name
        contract_no = order.contract_no
        item_no = order.item_no
        packaging_type = order_line.packaging_type
        paper_quality = order_line.paper_quality
        specification = order_line.specification
        unit = order_line.unit
        unit_price = order_line.unit_price
        currency = order_line.currency
    else:
        reference = db.get(CartonInventoryMovement, payload.reference_movement_id)
        if reference is None or reference.factory_id != factory_id:
            raise HTTPException(status_code=404, detail="库存结存引用流水不存在")
        movement_key = _movement_key(reference)
        customer_code = reference.customer_code
        customer_name = reference.customer_name
        contract_no = reference.contract_no
        item_no = reference.item_no
        packaging_type = reference.packaging_type
        paper_quality = reference.paper_quality
        specification = reference.specification
        unit = reference.unit
        unit_price = reference.unit_price
        currency = reference.currency
    timestamp = now_text()
    _ensure_period_open(db, factory_id, customer_code, timestamp)
    current = _inventory_balance_for_key(db, factory_id, movement_key)
    current_location = _inventory_locations(db, factory_id).get(movement_key)
    signed_quantity = -payload.quantity if payload.movement_type == "OUTBOUND" else payload.quantity
    if payload.movement_type == "OUTBOUND" and current < payload.quantity:
        raise HTTPException(status_code=409, detail="库存不足，不能出库")
    if current + signed_quantity < 0:
        raise HTTPException(status_code=409, detail="调整后库存不能小于 0")
    movement_id = f"CIM-{uuid4().hex}"
    movement = CartonInventoryMovement(
        id=movement_id,
        factory_id=factory_id,
        order_line_id=order_line.id if order_line is not None else None,
        customer_code=customer_code,
        customer_name=customer_name,
        contract_no=contract_no,
        item_no=item_no,
        packaging_type=packaging_type,
        paper_quality=paper_quality,
        specification=specification,
        movement_type=payload.movement_type,
        quantity=quantity(signed_quantity),
        unit=unit,
        unit_price=unit_price,
        currency=currency,
        location=current_location[0] if current_location else payload.location or (reference.location if reference is not None else ""),
        document_no=payload.document_no,
        source_type="MANUAL",
        source_id=movement_id,
        source_line_id=movement_id,
        reversal_of_movement_id=None,
        reason=payload.reason,
        actor_user_id=user.id,
        actor_name=user.display_name,
        occurred_at=timestamp,
    )
    db.add(movement)
    _audit(db, user, factory_id, "INVENTORY_MOVEMENT_CREATED", "carton_inventory_movement", movement.id, {"movement_type": movement.movement_type, "quantity": movement.quantity})
    return movement, quantity(current + signed_quantity)


def create_inventory_movement(
    db: Session,
    payload: CartonInventoryMovementCreate,
    user: AuthContext,
) -> CartonInventoryMovementOut:
    movement, balance = _prepare_inventory_movement(db, payload, user)
    db.commit()
    db.refresh(movement)
    return _movement_out(movement, balance)


def create_inventory_movements_bulk(
    db: Session,
    payload: CartonInventoryBulkCreate,
    user: AuthContext,
) -> list[CartonInventoryMovementOut]:
    factory_id = require_carton_factory(payload.factory_id)
    prepared: list[tuple[CartonInventoryMovement, Decimal]] = []
    for item in payload.items:
        prepared.append(
            _prepare_inventory_movement(
                db,
                CartonInventoryMovementCreate(
                    factory_id=factory_id,
                    order_line_id=item.order_line_id,
                    reference_movement_id=item.reference_movement_id,
                    movement_type="OUTBOUND",
                    quantity=item.quantity,
                    location=item.location,
                    document_no=payload.document_no,
                    reason=payload.reason,
                ),
                user,
            )
        )
        db.flush()
    _audit(
        db,
        user,
        factory_id,
        "INVENTORY_BULK_OUTBOUND_CREATED",
        "carton_inventory_batch",
        payload.document_no,
        {
            "reason": payload.reason,
            "movement_ids": [movement.id for movement, _ in prepared],
            "line_count": len(prepared),
        },
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="批量出库流水冲突，请刷新库存后重试") from exc
    for movement, _ in prepared:
        db.refresh(movement)
    return [_movement_out(movement, balance) for movement, balance in prepared]


def list_inventory_flow_summary(
    db: Session,
    factory_id: str,
    *,
    customer_code: str = "",
    date_from: str = "",
    date_to: str = "",
) -> list[CartonInventoryFlowSummaryOut]:
    business_date = func.substr(CartonInventoryMovement.occurred_at, 1, 10)
    query = select(
        business_date.label("business_date"),
        CartonInventoryMovement.customer_code,
        CartonInventoryMovement.customer_name,
        CartonInventoryMovement.movement_type,
        func.count(func.distinct(CartonInventoryMovement.document_no)).label("document_count"),
        func.count(CartonInventoryMovement.id).label("line_count"),
        func.sum(CartonInventoryMovement.quantity).label("quantity"),
    ).where(
        CartonInventoryMovement.factory_id == factory_id,
        CartonInventoryMovement.movement_type.in_(("INBOUND", "OUTBOUND")),
    )
    if customer_code:
        query = query.where(CartonInventoryMovement.customer_code == customer_code)
    if date_from:
        query = query.where(CartonInventoryMovement.occurred_at >= f"{date_from}T00:00:00")
    if date_to:
        query = query.where(CartonInventoryMovement.occurred_at <= f"{date_to}T23:59:59")
    rows = db.execute(
        query.group_by(
            business_date,
            CartonInventoryMovement.customer_code,
            CartonInventoryMovement.customer_name,
            CartonInventoryMovement.movement_type,
        ).order_by(business_date.desc(), CartonInventoryMovement.customer_name)
    ).all()
    return [
        CartonInventoryFlowSummaryOut(
            business_date=row.business_date,
            customer_code=row.customer_code,
            customer_name=row.customer_name,
            movement_type=row.movement_type,
            document_count=int(row.document_count),
            line_count=int(row.line_count),
            quantity=quantity(abs(Decimal(row.quantity or 0))),
        )
        for row in rows
    ]


def reverse_inventory_movement(
    db: Session,
    movement_id: str,
    payload: CartonInventoryReversalRequest,
    user: AuthContext,
) -> CartonInventoryMovementOut:
    factory_id = require_carton_factory(payload.factory_id)
    original = db.get(CartonInventoryMovement, movement_id)
    if original is None or original.factory_id != factory_id:
        raise HTTPException(status_code=404, detail="库存流水不存在")
    if original.movement_type in {"INBOUND", "REVERSAL"}:
        raise HTTPException(status_code=409, detail="收料入库须通过收料冲销流程处理，当前流水不能直接冲销")
    if db.scalar(
        select(CartonInventoryMovement.id).where(
            CartonInventoryMovement.reversal_of_movement_id == original.id
        )
    ):
        raise HTTPException(status_code=409, detail="该库存流水已经冲销")
    timestamp = now_text()
    _ensure_period_open(db, factory_id, original.customer_code, timestamp)
    current = _inventory_balance_for_key(db, factory_id, _movement_key(original))
    if current - original.quantity < 0:
        raise HTTPException(status_code=409, detail="冲销后库存将小于 0，请先冲销后续出库或补做调整")
    reversal_id = f"CIM-{uuid4().hex}"
    reversal = CartonInventoryMovement(
        id=reversal_id,
        factory_id=factory_id,
        order_line_id=original.order_line_id,
        customer_code=original.customer_code,
        customer_name=original.customer_name,
        contract_no=original.contract_no,
        item_no=original.item_no,
        packaging_type=original.packaging_type,
        paper_quality=original.paper_quality,
        specification=original.specification,
        movement_type="REVERSAL",
        quantity=-original.quantity,
        unit=original.unit,
        unit_price=original.unit_price,
        currency=original.currency,
        location=original.location,
        document_no=f"REV-{original.document_no}",
        source_type="REVERSAL",
        source_id=original.id,
        source_line_id=reversal_id,
        reversal_of_movement_id=original.id,
        reason=payload.reason,
        actor_user_id=user.id,
        actor_name=user.display_name,
        occurred_at=timestamp,
    )
    db.add(reversal)
    _audit(db, user, factory_id, "INVENTORY_MOVEMENT_REVERSED", "carton_inventory_movement", original.id, {"reversal_id": reversal_id, "reason": payload.reason})
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="该库存流水已经冲销") from exc
    db.refresh(reversal)
    return _movement_out(reversal, current - original.quantity)


def import_batch_out(batch: CartonImportBatch, *, duplicate: bool = False) -> CartonImportBatchOut:
    try:
        parse_summary = json.loads(batch.parse_summary_json or "{}")
    except (TypeError, json.JSONDecodeError):
        parse_summary = {"message": "历史导入批次的解析摘要无法读取，请重新导入原文件"}
    return CartonImportBatchOut.model_validate(batch).model_copy(
        update={"parse_summary": parse_summary, "duplicate": duplicate}
    )


def _create_import_exceptions(
    db: Session,
    batch: CartonImportBatch,
    parse_summary: dict[str, object],
    user: AuthContext,
) -> int:
    created = 0
    timestamp = now_text()
    for row in parse_summary.get("rows", []):
        if not isinstance(row, dict):
            continue
        match_status = str(row.get("match_status") or "")
        if batch.import_type == "INSPECTION_SCHEDULE":
            reminder_status = str(row.get("reminder_status") or "")
            inspection_exception = {
                "MISSING_ORDER": ("INSPECTION_ORDER_MISSING", "HIGH", "下周查货合同未找到纸箱订单"),
                "AMBIGUOUS": ("INSPECTION_ORDER_AMBIGUOUS", "HIGH", "下周查货合同存在多个候选订单"),
                "INVALID_DATE": ("INSPECTION_DATE_INVALID", "MEDIUM", "查货合同的验货日期无法识别"),
                "OVERDUE": ("INSPECTION_DELIVERY_OVERDUE", "HIGH", "纸箱最迟交货日已逾期"),
                "DUE_SOON": ("INSPECTION_DELIVERY_DUE", "HIGH", "纸箱最迟交货日临近"),
                "UPCOMING": ("INSPECTION_DELIVERY_REMINDER", "MEDIUM", "下周查货纸箱交货提醒"),
            }.get(reminder_status)
            if inspection_exception is None:
                continue
            category, severity, title = inspection_exception
        else:
            if match_status == "MATCHED":
                continue
            if match_status == "MISSING_ORDER":
                category = "MISSING_ORDER" if batch.import_type == "WEEKLY_SCHEDULE" else "RECEIPT_UNMATCHED"
                severity = "HIGH"
                title = "周排期未找到正式纸箱订单" if batch.import_type == "WEEKLY_SCHEDULE" else "送货明细未找到订单纸品"
            elif match_status == "QUANTITY_MISMATCH":
                category = "QUANTITY_MISMATCH"
                severity = "MEDIUM"
                title = "排期数量与纸箱订单数量不一致"
            else:
                category = "AMBIGUOUS_MATCH"
                severity = "MEDIUM"
                title = "导入明细存在多个候选订单"
        exception = CartonException(
            id=f"CEX-{uuid4().hex}",
            factory_id=batch.factory_id,
            exception_no=_new_number("EX"),
            source_type=batch.import_type,
            source_id=batch.id,
            category=category,
            severity=severity,
            customer_code=str(row.get("customer_code") or ""),
            customer_name=str(row.get("customer_name") or ""),
            contract_no=str(row.get("contract_no") or row.get("reference") or ""),
            item_no=str(row.get("item_no") or ""),
            title=title,
            description=str(row.get("suggestion") or "请人工复核导入内容并关联正式纸箱订单"),
            owner_department=(
                "纸箱部"
                if batch.import_type == "INSPECTION_SCHEDULE"
                else "纸箱下单" if batch.import_type == "WEEKLY_SCHEDULE" else "纸箱仓管"
            ),
            status="OPEN",
            resolution_note="",
            revision=1,
            created_by=user.id,
            created_by_name=user.display_name,
            updated_by=user.id,
            updated_by_name=user.display_name,
            created_at=timestamp,
            updated_at=timestamp,
            resolved_by="",
            resolved_by_name="",
            resolved_at="",
        )
        db.add(exception)
        created += 1
    return created


def create_import_batch(
    db: Session,
    factory_id: str,
    import_type: str,
    upload: UploadFile,
    content: bytes,
    user: AuthContext,
    import_profile: dict[str, object] | None = None,
) -> CartonImportBatchOut:
    factory_id = require_carton_factory(factory_id)
    filename = Path(upload.filename or "未命名文件").name
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_IMPORT_SUFFIXES:
        raise HTTPException(status_code=422, detail="仅支持 Excel、PDF、PNG、JPG 或 HEIC 文件")
    if not content:
        raise HTTPException(status_code=422, detail="导入文件不能为空")
    if len(content) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="导入文件不能超过 20 MB")
    sha256 = hashlib.sha256(content).hexdigest()
    effective_profile = dict(import_profile or {})
    if import_type == "DELIVERY_NOTE":
        effective_profile["parser_version"] = DELIVERY_IMPORT_PARSER_VERSION
    profile_text = (
        json.dumps(effective_profile, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        if effective_profile
        else ""
    )
    existing = db.scalar(
        select(CartonImportBatch).where(
            CartonImportBatch.factory_id == factory_id,
            CartonImportBatch.import_type == import_type,
            CartonImportBatch.source_sha256 == sha256,
            CartonImportBatch.import_profile == profile_text,
        )
    )
    if existing is not None:
        return import_batch_out(existing, duplicate=True)
    parse_options = dict(effective_profile)
    parse_options["reference_date"] = business_now().date().isoformat()
    parse_summary = parse_carton_import(
        db,
        factory_id,
        import_type,
        filename,
        content,
        options=parse_options,
    )
    batch = CartonImportBatch(
        id=f"CIB-{uuid4().hex}",
        factory_id=factory_id,
        import_type=import_type,
        original_filename=filename,
        source_sha256=sha256,
        import_profile=profile_text,
        content_type=upload.content_type or "",
        source_size_bytes=len(content),
        status="REQUIRES_REVIEW",
        parse_summary_json=json.dumps(parse_summary, ensure_ascii=False, default=str),
        imported_by=user.id,
        imported_by_name=user.display_name,
        created_at=now_text(),
    )
    db.add(batch)
    exception_count = _create_import_exceptions(db, batch, parse_summary, user)
    _audit(
        db,
        user,
        factory_id,
        "IMPORT_BATCH_CREATED",
        "carton_import_batch",
        batch.id,
        {
            "import_type": import_type,
            "filename": filename,
            "sha256": sha256,
            "row_count": parse_summary.get("row_count", 0),
            "matched_count": parse_summary.get("matched_count", 0),
            "exception_count": exception_count,
        },
    )
    db.commit()
    db.refresh(batch)
    return import_batch_out(batch)


def get_import_batch(
    db: Session,
    factory_id: str,
    batch_id: str,
) -> CartonImportBatchOut:
    batch = db.get(CartonImportBatch, batch_id)
    if batch is None or batch.factory_id != require_carton_factory(factory_id):
        raise HTTPException(status_code=404, detail="导入批次不存在")
    return import_batch_out(batch)


def delete_unmatched_delivery_import(
    db: Session,
    factory_id: str,
    batch_id: str,
    user: AuthContext,
) -> None:
    factory_id = require_carton_factory(factory_id)
    batch = db.scalar(
        select(CartonImportBatch)
        .where(
            CartonImportBatch.id == batch_id,
            CartonImportBatch.factory_id == factory_id,
        )
        .with_for_update()
    )
    if batch is None:
        raise HTTPException(status_code=404, detail="导入批次不存在")
    if batch.import_type != "DELIVERY_NOTE":
        raise HTTPException(status_code=409, detail="只有送货单导入批次可以在收料平台删除")
    if batch.status != "REQUIRES_REVIEW":
        raise HTTPException(status_code=409, detail="已确认或已拒绝的送货单导入批次不能删除")

    receipt_count = db.scalar(
        select(func.count(CartonReceipt.id)).where(
            CartonReceipt.factory_id == factory_id,
            CartonReceipt.import_batch_id == batch.id,
        )
    ) or 0
    if receipt_count:
        raise HTTPException(status_code=409, detail="该导入批次已经生成收料单，不能删除")

    parse_summary = import_batch_out(batch).parse_summary
    rows = parse_summary.get("rows", [])
    matched_count = sum(
        1
        for row in rows
        if isinstance(row, dict) and row.get("match_status") == "MATCHED"
    )
    try:
        matched_count = max(matched_count, int(parse_summary.get("matched_count", 0) or 0))
    except (TypeError, ValueError):
        pass
    if matched_count:
        raise HTTPException(status_code=409, detail="该送货单已有明细匹配正式订单，不能删除")

    exceptions = list(
        db.scalars(
            select(CartonException).where(
                CartonException.factory_id == factory_id,
                CartonException.source_type == "DELIVERY_NOTE",
                CartonException.source_id == batch.id,
            )
        ).all()
    )
    _audit(
        db,
        user,
        factory_id,
        "UNMATCHED_DELIVERY_IMPORT_DELETED",
        "carton_import_batch",
        batch.id,
        {
            "filename": batch.original_filename,
            "sha256": batch.source_sha256,
            "row_count": parse_summary.get("row_count", 0),
            "exception_count": len(exceptions),
        },
    )
    for exception in exceptions:
        db.delete(exception)
    db.delete(batch)
    db.commit()


def get_latest_import_batch(
    db: Session,
    factory_id: str,
    import_type: str,
) -> CartonImportBatchOut | None:
    batch = db.scalar(
        select(CartonImportBatch)
        .where(
            CartonImportBatch.factory_id == require_carton_factory(factory_id),
            CartonImportBatch.import_type == import_type,
        )
        .order_by(CartonImportBatch.created_at.desc(), CartonImportBatch.id.desc())
        .limit(1)
    )
    return import_batch_out(batch) if batch is not None else None


def list_import_batches(
    db: Session,
    factory_id: str,
    *,
    import_type: str = "",
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[CartonImportBatchOut]]:
    factory_id = require_carton_factory(factory_id)
    allowed_types = {"DELIVERY_NOTE", "WEEKLY_SCHEDULE", "INSPECTION_SCHEDULE"}
    if import_type and import_type not in allowed_types:
        raise HTTPException(status_code=422, detail="导入批次类型无效")
    query = select(CartonImportBatch).where(CartonImportBatch.factory_id == factory_id)
    if import_type:
        query = query.where(CartonImportBatch.import_type == import_type)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = list(
        db.scalars(
            query.order_by(CartonImportBatch.created_at.desc(), CartonImportBatch.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()
    )
    return int(total), [import_batch_out(row) for row in rows]


def list_exceptions(
    db: Session,
    factory_id: str,
    *,
    status_filter: str = "",
    search: str = "",
    limit: int = 100,
    offset: int = 0,
) -> tuple[int, list[CartonException]]:
    query = select(CartonException).where(CartonException.factory_id == factory_id)
    if status_filter:
        query = query.where(CartonException.status == status_filter)
    if search:
        pattern = f"%{search}%"
        query = query.where(
            or_(
                CartonException.exception_no.ilike(pattern),
                CartonException.customer_name.ilike(pattern),
                CartonException.contract_no.ilike(pattern),
                CartonException.item_no.ilike(pattern),
                CartonException.title.ilike(pattern),
                CartonException.description.ilike(pattern),
            )
        )
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = list(
        db.scalars(
            query.order_by(CartonException.created_at.desc()).limit(limit).offset(offset)
        ).all()
    )
    return int(total), rows


def update_exception(
    db: Session,
    exception_id: str,
    payload: CartonExceptionUpdate,
    user: AuthContext,
) -> CartonException:
    factory_id = require_carton_factory(payload.factory_id)
    exception = db.get(CartonException, exception_id)
    if exception is None or exception.factory_id != factory_id:
        raise HTTPException(status_code=404, detail="异常记录不存在")
    if exception.revision != payload.expected_revision:
        raise HTTPException(status_code=409, detail="异常记录已更新，请刷新后重试")
    if exception.status == "CLOSED" and payload.status != "OPEN":
        raise HTTPException(status_code=409, detail="已关闭异常只能重新打开")
    timestamp = now_text()
    exception.status = payload.status
    if payload.owner_department:
        exception.owner_department = payload.owner_department
    exception.resolution_note = payload.resolution_note
    exception.revision += 1
    exception.updated_by = user.id
    exception.updated_by_name = user.display_name
    exception.updated_at = timestamp
    if payload.status in {"RESOLVED", "CLOSED"}:
        exception.resolved_by = user.id
        exception.resolved_by_name = user.display_name
        exception.resolved_at = timestamp
    else:
        exception.resolved_by = ""
        exception.resolved_by_name = ""
        exception.resolved_at = ""
    _audit(
        db,
        user,
        factory_id,
        "EXCEPTION_STATUS_UPDATED",
        "carton_exception",
        exception.id,
        {"status": payload.status, "resolution_note": payload.resolution_note},
    )
    db.commit()
    db.refresh(exception)
    return exception


def list_audit_events(
    db: Session,
    factory_id: str,
    *,
    search: str = "",
    event_type: str = "",
    actor_user_id: str = "",
    date_from: str = "",
    date_to: str = "",
    limit: int = 100,
    offset: int = 0,
) -> tuple[int, list[CartonAuditEventOut]]:
    query = select(CartonAuditEvent).where(CartonAuditEvent.factory_id == factory_id)
    if event_type:
        query = query.where(CartonAuditEvent.event_type == event_type)
    if actor_user_id:
        query = query.where(CartonAuditEvent.actor_user_id == actor_user_id)
    if date_from:
        query = query.where(CartonAuditEvent.created_at >= f"{date_from}T00:00:00")
    if date_to:
        query = query.where(CartonAuditEvent.created_at <= f"{date_to}T23:59:59")
    if search:
        pattern = f"%{search}%"
        query = query.where(
            or_(
                CartonAuditEvent.event_type.ilike(pattern),
                CartonAuditEvent.entity_type.ilike(pattern),
                CartonAuditEvent.entity_id.ilike(pattern),
                CartonAuditEvent.actor_name.ilike(pattern),
                CartonAuditEvent.detail_json.ilike(pattern),
            )
        )
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = list(
        db.scalars(
            query.order_by(CartonAuditEvent.sequence.desc()).limit(limit).offset(offset)
        ).all()
    )
    items: list[CartonAuditEventOut] = []
    for row in rows:
        try:
            detail = json.loads(row.detail_json or "{}")
        except (TypeError, json.JSONDecodeError):
            detail = {"message": "历史操作详情无法解析"}
        items.append(
            CartonAuditEventOut(
                sequence=row.sequence,
                id=row.id,
                factory_id=row.factory_id,
                event_type=row.event_type,
                entity_type=row.entity_type,
                entity_id=row.entity_id,
                detail=detail if isinstance(detail, dict) else {"value": detail},
                actor_user_id=row.actor_user_id,
                actor_name=row.actor_name,
                created_at=row.created_at,
            )
        )
    return int(total), items


def _period_bounds(period: str) -> tuple[str, str]:
    year, month = (int(part) for part in period.split("-"))
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start.isoformat(), end.isoformat()


def generate_closings(
    db: Session,
    payload: CartonClosingGenerateRequest,
    user: AuthContext,
) -> list[CartonClosing]:
    factory_id = require_carton_factory(payload.factory_id)
    start, end = _period_bounds(payload.period)
    movements = list(
        db.scalars(
            select(CartonInventoryMovement).where(
                CartonInventoryMovement.factory_id == factory_id,
                CartonInventoryMovement.occurred_at < f"{end}T",
            )
        ).all()
    )
    if payload.customer_code:
        movements = [row for row in movements if row.customer_code == payload.customer_code]
    customer_names: dict[str, str] = {}
    aggregates: dict[tuple[str, str], dict[str, Decimal]] = defaultdict(
        lambda: {
            "opening": Decimal(0),
            "inbound": Decimal(0),
            "outbound": Decimal(0),
            "adjustment": Decimal(0),
            "ending": Decimal(0),
            "amount": Decimal(0),
        }
    )
    for movement in movements:
        customer_names[movement.customer_code] = movement.customer_name
        currency = normalize_currency(movement.currency)
        values = aggregates[(movement.customer_code, currency)]
        if movement.occurred_at < f"{start}T":
            values["opening"] += movement.quantity
        else:
            if movement.movement_type == "INBOUND":
                values["inbound"] += movement.quantity
            elif movement.movement_type == "OUTBOUND":
                values["outbound"] += -movement.quantity
            else:
                values["adjustment"] += movement.quantity
        values["ending"] += movement.quantity
        values["amount"] += movement.quantity * movement.unit_price

    timestamp = now_text()
    closings: list[CartonClosing] = []
    for (customer_code, currency), values in sorted(aggregates.items()):
        existing = db.scalar(
            select(CartonClosing).where(
                CartonClosing.factory_id == factory_id,
                CartonClosing.period == payload.period,
                CartonClosing.customer_code == customer_code,
                CartonClosing.currency == currency,
            )
        )
        if existing is not None and existing.status in {"CONFIRMED", "LOCKED"}:
            raise HTTPException(
                status_code=409,
                detail=f"{customer_names[customer_code]} 的 {payload.period} {currency} 月结已确认或锁账",
            )
        closing = existing or CartonClosing(
            id=f"CCL-{uuid4().hex}",
            factory_id=factory_id,
            period=payload.period,
            customer_code=customer_code,
            customer_name=customer_names[customer_code],
            opening_quantity=Decimal(0),
            inbound_quantity=Decimal(0),
            outbound_quantity=Decimal(0),
            adjustment_quantity=Decimal(0),
            ending_quantity=Decimal(0),
            ending_amount=Decimal(0),
            currency=currency,
            status="DRAFT",
            revision=1,
            generated_by=user.id,
            generated_by_name=user.display_name,
            generated_at=timestamp,
            confirmed_by="",
            confirmed_at="",
            locked_by="",
            locked_at="",
        )
        if existing is not None:
            closing.revision += 1
        closing.customer_name = customer_names[customer_code]
        closing.currency = currency
        closing.opening_quantity = quantity(values["opening"])
        closing.inbound_quantity = quantity(values["inbound"])
        closing.outbound_quantity = quantity(values["outbound"])
        closing.adjustment_quantity = quantity(values["adjustment"])
        closing.ending_quantity = quantity(values["ending"])
        closing.ending_amount = values["amount"].quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
        closing.status = "DRAFT"
        closing.generated_by = user.id
        closing.generated_by_name = user.display_name
        closing.generated_at = timestamp
        if existing is None:
            db.add(closing)
        closings.append(closing)
    _audit(
        db,
        user,
        factory_id,
        "CLOSING_GENERATED",
        "carton_closing_period",
        payload.period,
        {
            "closing_count": len(closings),
            "customer_code": payload.customer_code or "",
            "currencies": sorted({closing.currency for closing in closings}),
        },
    )
    db.commit()
    return closings


def list_closings(
    db: Session,
    factory_id: str,
    *,
    period: str = "",
    customer_code: str = "",
) -> list[CartonClosing]:
    query = select(CartonClosing).where(CartonClosing.factory_id == factory_id)
    if period:
        query = query.where(CartonClosing.period == period)
    if customer_code:
        query = query.where(CartonClosing.customer_code == customer_code)
    return list(
        db.scalars(
            query.order_by(
                CartonClosing.period.desc(),
                CartonClosing.customer_name,
                CartonClosing.currency,
            )
        ).all()
    )


def update_closing_status(
    db: Session,
    closing_id: str,
    payload: CartonClosingStatusRequest,
    user: AuthContext,
) -> CartonClosing:
    factory_id = require_carton_factory(payload.factory_id)
    closing = db.get(CartonClosing, closing_id)
    if closing is None or closing.factory_id != factory_id:
        raise HTTPException(status_code=404, detail="月结记录不存在")
    if closing.revision != payload.expected_revision:
        raise HTTPException(status_code=409, detail="月结记录已更新，请刷新后重试")
    transitions = {"DRAFT": "PENDING", "PENDING": "CONFIRMED", "CONFIRMED": "LOCKED"}
    if transitions.get(closing.status) != payload.status:
        raise HTTPException(status_code=409, detail="月结状态必须依次经过待核对、已确认和锁账")
    timestamp = now_text()
    closing.status = payload.status
    closing.revision += 1
    if payload.status == "CONFIRMED":
        closing.confirmed_by = user.id
        closing.confirmed_at = timestamp
    elif payload.status == "LOCKED":
        closing.locked_by = user.id
        closing.locked_at = timestamp
    _audit(
        db,
        user,
        factory_id,
        f"CLOSING_{payload.status}",
        "carton_closing",
        closing.id,
        {
            "period": closing.period,
            "customer_code": closing.customer_code,
            "currency": closing.currency,
        },
    )
    db.commit()
    db.refresh(closing)
    return closing


def dashboard(db: Session, factory_id: str) -> CartonDashboardOut:
    open_order_count = db.scalar(
        select(func.count()).select_from(CartonOrder).where(
            CartonOrder.factory_id == factory_id,
            CartonOrder.status.not_in(("COMPLETED", "CANCELLED")),
        )
    ) or 0
    partial_order_count = db.scalar(
        select(func.count()).select_from(CartonOrder).where(
            CartonOrder.factory_id == factory_id,
            CartonOrder.status == "PARTIALLY_RECEIVED",
        )
    ) or 0
    pending_receipt_count = db.scalar(
        select(func.count()).select_from(CartonReceipt).where(
            CartonReceipt.factory_id == factory_id,
            CartonReceipt.status == "PENDING_CONFIRMATION",
        )
    ) or 0
    inventory_balance = db.scalar(
        select(func.coalesce(func.sum(CartonInventoryMovement.quantity), 0)).where(
            CartonInventoryMovement.factory_id == factory_id
        )
    ) or Decimal(0)
    unlocked_closing_count = db.scalar(
        select(func.count()).select_from(CartonClosing).where(
            CartonClosing.factory_id == factory_id,
            CartonClosing.status != "LOCKED",
        )
    ) or 0
    open_exception_count = db.scalar(
        select(func.count()).select_from(CartonException).where(
            CartonException.factory_id == factory_id,
            CartonException.status.in_(("OPEN", "IN_PROGRESS")),
        )
    ) or 0
    return CartonDashboardOut(
        factory_id=factory_id,
        open_order_count=int(open_order_count),
        partial_order_count=int(partial_order_count),
        pending_receipt_count=int(pending_receipt_count),
        inventory_balance=quantity(inventory_balance),
        unlocked_closing_count=int(unlocked_closing_count),
        open_exception_count=int(open_exception_count),
    )
