from __future__ import annotations
from app.services import carton_master as master_data
from app.services.carton_replenishment import fulfilled_by_line, replenished_by_line, protected_by_line

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

from app.services.transaction_lock import lock_transaction
from app.core.time import business_now, business_today
from app.models.carton_supplier_settlement import CartonSupplierSettlement  # noqa: F401 - register additive schema
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
    CartonClosingUnitQuantities,
    CartonPricingIssueOut,
    CartonClosingStatusRequest,
    CartonClosingUnlockRequest,
    CartonInventoryPriceConfirmRequest,
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
    CartonReceiptReverseRequest,
    CartonReceiptCreate,
    CartonReceiptLineOut,
    CartonReceiptOut,
    DEFAULT_CARTON_SAFETY_LEAD_DAYS,
    derive_carton_plan_due_date,
)
from app.services.auth import ALLOWED_FACTORY_IDS, AuthContext
from app.schemas.carton_procurement import CartonLocationAllocation
from app.services import carton_positions as positions
from app.services.carton_inventory_valuation import cost_key, load_valuation, value_movements, Valuation
from app.services.carton_ledger_time import ledger_rows, ledger_time, ordered_ledger_rows
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
) -> CartonAuditEvent:
    event = CartonAuditEvent(
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
    db.add(event)
    return event


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


def _input_required(payload, line, *, allow_zero=False):
    if payload.quantity_basis == "EXPLICIT":
        if line.required_quantity is None or line.required_quantity < 0 or (line.required_quantity == 0 and not allow_zero):
            raise HTTPException(422, "直接填写需求时，每行纸品需求数量必须大于 0")
        return quantity(line.required_quantity)
    if payload.product_order_quantity is None or line.usage_quantity is None:
        raise HTTPException(422, "按装箱数计算需求必须填写产品订单数量和每箱个数")
    if not line.paper_quality or not line.specification:
        raise HTTPException(422, "请补全纸质和规格")
    return required_carton_quantity(payload.product_order_quantity, line.usage_quantity)


def _require_receipt_material(line):
    if not line.paper_quality.strip() or not line.specification.strip() or not line.unit.strip():
        raise HTTPException(422, f"{line.contract_no} / {line.packaging_type}：入库前请补齐纸质、规格和单位")


def _require_order_complete(db, order):
    lines = _order_lines(db, order.id)
    if not lines or any(not line.paper_quality.strip() or not line.specification.strip() or not line.unit.strip() for line in lines):
        raise HTTPException(422, "订单纸质、规格或单位尚未完善，请先修改订单")
    if not any(line.required_quantity > 0 for line in lines):
        raise HTTPException(422, "订单没有可执行的纸品需求")
    if order.quantity_basis == "CALCULATED" and (order.product_order_quantity is None or any(line.usage_quantity is None for line in lines)):
        raise HTTPException(422, "按装箱数计算的订单缺少数量依据")


def _explicit_targets(order, lines, targets, *, append):
    target = {item.order_line_id: quantity(item.required_quantity) for item in targets}
    if len(target) != len(targets) or set(target) != {line.id for line in lines}:
        raise HTTPException(422, "直接填写需求的订单必须逐行提供全部纸品的目标需求，不能重复或遗漏")
    deltas = [target[line.id] - line.required_quantity for line in lines]
    if append and (any(delta < 0 for delta in deltas) or not any(delta > 0 for delta in deltas)):
        raise HTTPException(422, "追加须至少增加一种纸品，其他纸品需求不得减少")
    if not append and (any(delta > 0 for delta in deltas) or not any(delta < 0 for delta in deltas)):
        raise HTTPException(422, "减单须至少减少一种纸品，其他纸品需求不得增加")
    return target


def _validate_customer_po_identity(db, factory, customer, contract, item, customer_po, exclude_id=""):
    # Legacy blank-PO orders remain valid. A supplied PO disambiguates otherwise identical demand.
    if not customer_po:
        return
    candidates = db.scalars(select(CartonOrder).where(CartonOrder.factory_id == factory,
        CartonOrder.customer_code == customer, CartonOrder.status != "CANCELLED",
        CartonOrder.id != exclude_id)).all()
    key = tuple(value.strip().casefold() for value in (contract, item, customer_po))
    if any(tuple(value.strip().casefold() for value in (o.contract_no, o.item_no, o.customer_po)) == key for o in candidates):
        raise HTTPException(409, "同客户、合同号、货号及客户 PO 的订单已存在，请核对或在原单追加")


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
    _lock_receipt_factory(db, factory_id)
    rules = master_data.validate_order(db, factory_id, payload.customer_code, payload.contract_no, payload.item_no, customer_po=payload.customer_po, config_id=payload.master_config_id, config_revision=payload.master_config_revision)
    _validate_customer_po_identity(db, factory_id, payload.customer_code, payload.contract_no, payload.item_no, payload.customer_po)
    planned = derive_carton_plan_due_date(payload.order_date, payload.customer_due_date, rules["lead_days"]) if payload.customer_due_date and payload.quantity_basis == "CALCULATED" else payload.due_date
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
                CartonOrder.customer_code == customer.customer_code,
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
        customer_po=payload.customer_po,
        contract_no=payload.contract_no,
        item_no=payload.item_no,
        product_name=product_name,
        quantity_basis=payload.quantity_basis,
        product_order_quantity=payload.product_order_quantity,
        order_date=payload.order_date,
        customer_due_date=payload.customer_due_date,
        safety_lead_days=rules["lead_days"],
        master_config_id=payload.master_config_id,
        master_config_revision=payload.master_config_revision,
        due_date=planned,
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
        required_quantity = _input_required(payload, line)
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
            "customer_po": payload.customer_po,
            "customer_code": order.customer_code,
            "customer_name": order.customer_name,
            "item_no": order.item_no,
            "product_name": order.product_name,
            "product_order_quantity": order.product_order_quantity,
            "quantity_basis": order.quantity_basis,
            "paper_demand": [{"packaging_type": line.packaging_type, "paper_quality": line.paper_quality, "specification": line.specification, "unit": line.unit, "required_quantity": str(_input_required(payload, line)), "usage_quantity": str(line.usage_quantity) if line.usage_quantity is not None else None} for line in payload.lines],
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
        is_replenishment=bool(_purchase_order_snapshot(issue).get("replenishment")),
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
    before_product_quantity = quantity(Decimal(str(previous.get("after_product_quantity") or 0)))
    before_due_date = str(previous.get("after_due_date", ""))
    previous_lines = {
        str(item.get("id", "")): item
        for item in previous.get("lines", [])
        if isinstance(item, dict)
    }
    product_delta = quantity(order.product_order_quantity - before_product_quantity) if order.product_order_quantity is not None else Decimal(0)
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
                "usage_quantity": str(line.usage_quantity) if line.usage_quantity is not None else None,
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
    paper_delta = sum((Decimal(item["required_quantity_delta"]) for item in line_snapshots), Decimal(0))
    if latest_issue is None:
        pending_type = "INITIAL"
    elif product_delta > 0 or (order.quantity_basis == "EXPLICIT" and paper_delta > 0):
        pending_type = "APPEND"
    elif product_delta < 0 or (order.quantity_basis == "EXPLICIT" and paper_delta < 0):
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
            "customer_po": order.customer_po,
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
        "before_product_quantity": str(before_product_quantity) if order.quantity_basis == "CALCULATED" or previous.get("after_product_quantity") is not None else None,
        "after_product_quantity": str(quantity(order.product_order_quantity)) if order.product_order_quantity is not None else None,
        "quantity_basis": order.quantity_basis,
        "product_quantity_delta": str(product_delta) if order.quantity_basis == "CALCULATED" else None,
        "before_due_date": before_due_date,
        "after_due_date": order.due_date,
        "lines": line_snapshots,
    }
    return pending_type, product_delta, changed_line_count, snapshot


def register_history_order_placed(db: Session, order: CartonOrder, user: AuthContext):
    """Record already placed demand without issuing a supplier purchase document."""
    if _purchase_order_issues(db, order.id):
        return
    if order.status != "CONFIRMED" or _order_has_business_activity(db, order):
        raise HTTPException(409, "仅未收料的历史待下单订单可以转为历史已下单")
    if not db.scalar(select(CartonAuditEvent.id).where(
        CartonAuditEvent.factory_id == order.factory_id,
        CartonAuditEvent.entity_id == order.id,
        CartonAuditEvent.event_type == "HISTORY_ORDER_IMPORTED",
    ).limit(1)):
        raise HTTPException(409, "订单没有历史导入来源，不允许跳过正常下单流程")
    previous_status = order.status
    order.status = "PENDING_SUPPLIER"
    order.revision += 1
    order.updated_by = user.id
    order.updated_by_name = user.display_name
    order.updated_at = now_text()
    _, _, _, snapshot = _purchase_order_pending_change(order, _order_lines(db, order.id), None)
    db.add(CartonPurchaseOrderIssue(
        id=f"CPOI-{uuid4().hex}", factory_id=order.factory_id, order_id=order.id,
        order_no=order.order_no, document_no=f"{order.order_no}-HISTORY",
        document_type="LEGACY_BASELINE", issue_sequence=0, source_order_revision=order.revision,
        before_product_quantity=order.product_order_quantity, after_product_quantity=order.product_order_quantity,
        product_quantity_delta=Decimal(0) if order.product_order_quantity is not None else None,
        snapshot_json=json.dumps(snapshot, ensure_ascii=False, sort_keys=True),
        generated_by=user.id, generated_by_name=user.display_name, generated_at=now_text(),
    ))
    _audit(db, user, order.factory_id, "HISTORY_ORDER_PLACED", "carton_order", order.id,
           {"order_no": order.order_no, "previous_status": previous_status, "status": order.status,
            "reason": "历史订单已在系统外下单，直接待收料，不重复发行采购单"})
    db.flush()


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
        pending_product_quantity=product_delta if order.quantity_basis == "CALCULATED" else None,
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
    _lock_receipt_factory(db, order.factory_id)
    if order.revision != expected_revision:
        raise HTTPException(status_code=409, detail="订单已被其他人更新，请刷新后重试")
    if order.status not in {"PENDING_SUPPLIER", "PARTIALLY_RECEIVED", "COMPLETED"}:
        raise HTTPException(status_code=409, detail="只有已确认并锁定的订单可以发行供应商采购单")

    _require_order_complete(db, order)
    issues = _purchase_order_issues(db, order.id)
    latest_issue = issues[0] if issues else None
    pending_type, product_delta, _, snapshot = _purchase_order_pending_change(
        order, _order_lines(db, order.id), latest_issue
    )
    if pending_type == "NONE":
        raise HTTPException(status_code=409, detail="当前订单没有尚未生成采购单的数量或交期变化")

    next_issue_sequence = (latest_issue.issue_sequence if latest_issue else 0) + 1
    type_sequence = 1 + sum(issue.document_type == pending_type and not _purchase_order_snapshot(issue).get("replenishment") for issue in issues)
    if pending_type == "INITIAL":
        document_no = f"{order.order_no}-P00"
    else:
        prefix = {"APPEND": "A", "REDUCE": "R", "ADJUSTMENT": "C"}[pending_type]
        document_no = f"{order.order_no}-{prefix}{type_sequence:02d}"
    before_quantity = quantity(Decimal(str(snapshot["before_product_quantity"]))) if snapshot["before_product_quantity"] is not None else None
    after_quantity = quantity(Decimal(str(snapshot["after_product_quantity"]))) if snapshot["after_product_quantity"] is not None else None
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
        product_quantity_delta=product_delta if order.quantity_basis == "CALCULATED" else None,
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


def can_delete_history_order(db: Session, order: CartonOrder) -> bool:
    imported = db.scalar(select(CartonAuditEvent.id).where(
        CartonAuditEvent.factory_id == order.factory_id,
        CartonAuditEvent.entity_id == order.id,
        CartonAuditEvent.event_type == "HISTORY_ORDER_IMPORTED",
    ).limit(1))
    return bool(imported) and not _order_has_business_activity(db, order)


def delete_history_order(db: Session, order_no: str, payload: CartonOrderCancelRequest, user: AuthContext) -> None:
    factory_id = require_carton_factory(payload.factory_id)
    _lock_receipt_factory(db, factory_id)
    order = get_order_by_no(db, factory_id, order_no)
    if order.revision != payload.expected_revision:
        raise HTTPException(409, "订单已更新，请刷新后重试")
    if not can_delete_history_order(db, order):
        raise HTTPException(409, "仅无收料或库存记录的历史导入订单可以删除；入库后即使冲销也不能删除")
    snapshot = order_out(db, order).model_dump(mode="json")
    issues = _purchase_order_issues(db, order.id)
    _audit(db, user, factory_id, "HISTORY_ORDER_DELETED", "carton_order", order.id,
           {"order_no": order.order_no, "reason": payload.reason, "order": snapshot,
            "purchase_issues": [{"document_no": issue.document_no, "snapshot": json.loads(issue.snapshot_json)} for issue in issues]})
    for issue in issues:
        db.delete(issue)
    for line in _order_lines(db, order.id):
        db.delete(line)
    db.flush()
    db.delete(order)
    db.commit()


def _order_line_signature(line: CartonOrderLine | object) -> tuple[str, ...]:
    return (
        str(line.packaging_type),
        str(line.paper_quality),
        str(line.specification),
        str(line.dimension_unit),
        str(Decimal(line.usage_quantity).normalize()) if line.usage_quantity is not None else "",
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
    _lock_receipt_factory(db, factory_id)
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

    if "customer_po" not in payload.model_fields_set:
        payload.customer_po = order.customer_po
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
            str(Decimal(line.usage_quantity).normalize()) if line.usage_quantity is not None else "",
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
            payload.customer_po != order.customer_po,
            payload.item_no != order.item_no,
            payload.product_name != order.product_name,
            payload.product_order_quantity != order.product_order_quantity,
            payload.quantity_basis != order.quantity_basis,
            payload.quantity_basis == "EXPLICIT" and [line.required_quantity for line in payload.lines] != [line.required_quantity for line in existing_lines],
            payload.order_date != order.order_date,
            target_line_signatures != [_order_line_signature(line) for line in existing_lines],
        )
    )
    if order.quantity_basis == "CALCULATED" and order.customer_due_date is not None and payload.customer_due_date is None:
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
    if target_customer_due_date and payload.quantity_basis == "CALCULATED":
        target_due_date = derive_carton_plan_due_date(payload.order_date, target_customer_due_date, order.safety_lead_days)
    # Existing orders retain their snapshot: changing a date/note must not reapply
    # newly introduced master rules or invalidate a previously selected configuration.
    if structural_changed:
        master_data.validate_order(db, factory_id, target_customer_code, payload.contract_no, payload.item_no, customer_po=payload.customer_po, config_id=payload.master_config_id, config_revision=payload.master_config_revision)
    if structural_changed:
        _validate_customer_po_identity(db, factory_id, target_customer_code, payload.contract_no, payload.item_no, payload.customer_po, order.id)
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
        "customer_po": order.customer_po,
        "item_no": order.item_no,
        "product_order_quantity": order.product_order_quantity,
        "order_date": order.order_date,
        "customer_due_date": order.customer_due_date,
        "safety_lead_days": order.safety_lead_days,
        "due_date": order.due_date,
        "note": order.note,
        "lines": [_order_line_signature(line) for line in existing_lines],
        "quantity_basis": order.quantity_basis,
        "required_quantities": [str(line.required_quantity) for line in existing_lines],
    }
    if structural_changed:
        order.customer_code = target_customer_code
        order.customer_name = target_customer_name
        order.supplier_id = target_supplier_id
        order.supplier_name_snapshot = target_supplier_name
        order.customer_po = payload.customer_po
        order.contract_no = payload.contract_no
        order.item_no = payload.item_no
        order.product_name = payload.product_name
        order.quantity_basis = payload.quantity_basis
        order.product_order_quantity = payload.product_order_quantity
        order.order_date = payload.order_date
        for index, input_line in enumerate(payload.lines, start=1):
            required_quantity = _input_required(payload, input_line, allow_zero=(index <= len(existing_lines) and existing_lines[index - 1].required_quantity == 0))
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
    if structural_changed:
        order.master_config_id = payload.master_config_id
        order.master_config_revision = payload.master_config_revision
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
                "customer_po": order.customer_po,
                "item_no": order.item_no,
                "product_order_quantity": order.product_order_quantity,
                "quantity_basis": order.quantity_basis,
                "required_quantities": [str(line.required_quantity) for line in _order_lines(db, order.id)],
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
    _lock_receipt_factory(db, factory_id)
    order = get_order_by_no(db, factory_id, order_no)
    if order.revision != payload.expected_revision:
        raise HTTPException(status_code=409, detail="订单已被其他人更新，请刷新后重试")
    if order.status == "PENDING_SUPPLIER":
        raise HTTPException(status_code=409, detail="订单已经确认并锁定")
    if order.status not in {"CONFIRMED", "DRAFT"}:
        raise HTTPException(status_code=409, detail="只有待下单且尚未确认锁定的订单可以确认")
    _require_order_complete(db, order)

    master_data.validate_order(db, factory_id, order.customer_code, order.contract_no, order.item_no, customer_po=order.customer_po)
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
    master_data.sync_history(db, factory_id)
    db.commit()
    db.refresh(order)
    return order


def bulk_submit_orders_to_supplier(
    db: Session,
    payload: CartonOrderBulkSubmitRequest,
    user: AuthContext,
) -> list[CartonOrder]:
    factory_id = require_carton_factory(payload.factory_id)
    _lock_receipt_factory(db, factory_id)
    orders: list[CartonOrder] = []
    for item in payload.items:
        order = get_order_by_no(db, factory_id, item.order_no)
        if order.status not in {"CONFIRMED", "DRAFT"}:
            continue
        _require_order_complete(db, order)
        if order.revision != item.expected_revision:
            raise HTTPException(status_code=409, detail=f"订单 {item.order_no} 已更新，请刷新后重试")
        orders.append(order)

    timestamp = now_text()
    for order in orders:
        master_data.validate_order(db, factory_id, order.customer_code, order.contract_no, order.item_no, customer_po=order.customer_po)
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

    master_data.sync_history(db, factory_id)
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
    _lock_receipt_factory(db, factory_id)
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
    _lock_receipt_factory(db, factory_id)
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
    if payload.customer_due_date and order.quantity_basis == "CALCULATED":
        try:
            target_due_date = derive_carton_plan_due_date(
                order.order_date,
                payload.customer_due_date,
                order.safety_lead_days,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        target_customer_due_date = payload.customer_due_date
    else:
        if order.quantity_basis == "CALCULATED" and order.customer_due_date is not None and payload.due_date and payload.due_date != order.due_date:
            raise HTTPException(
                status_code=422,
                detail="已有客户交期的订单必须通过客户交期自动计算计划交期",
            )
        target_customer_due_date = payload.customer_due_date or order.customer_due_date
        target_due_date = payload.due_date or order.due_date
    if target_due_date < order.order_date:
        raise HTTPException(status_code=422, detail="计划交期不能早于下单日期")

    previous_status = order.status
    before_quantity = quantity(order.product_order_quantity) if order.product_order_quantity is not None else None
    before_customer_due_date = order.customer_due_date
    before_due_date = order.due_date
    lines = _order_lines(db, order.id)
    before_required = {line.id: quantity(line.required_quantity) for line in lines}
    if order.quantity_basis == "EXPLICIT":
        if payload.additional_quantity is not None:
            raise HTTPException(422, "直接填写需求的订单请逐纸品追加，不能以产品数量换算")
        target = _explicit_targets(order, lines, payload.line_quantities, append=True)
        after_quantity = before_quantity
        for line in lines:
            line.required_quantity = target[line.id]
    else:
        if payload.additional_quantity is None or payload.line_quantities:
            raise HTTPException(422, "按装箱数计算的订单必须填写产品追加数量")
        after_quantity = quantity(before_quantity + payload.additional_quantity)
        for line in lines:
            line.required_quantity = required_carton_quantity(after_quantity, line.usage_quantity)
    order.product_order_quantity = after_quantity
    if previous_status == "COMPLETED":
        received = fulfilled_by_line(db, [line.id for line in lines])
        order.status = "COMPLETED" if all(
            received.get(line.id, Decimal(0)) >= line.required_quantity for line in lines
        ) else "PARTIALLY_RECEIVED"
    order.customer_due_date = target_customer_due_date
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
            "quantity_basis": order.quantity_basis,
            "line_labels": {line.id: {"packaging_type": line.packaging_type, "paper_quality": line.paper_quality, "specification": line.specification, "unit": line.unit} for line in lines},
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
                (f"纸品需求由 {before_required} 调整至 {target}；" if order.quantity_basis == "EXPLICIT" else f"产品订单数量由 {before_quantity} 追加 {payload.additional_quantity} 至 {after_quantity}；") +
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
    _lock_receipt_factory(db, factory_id)
    order = get_order_by_no(db, factory_id, order_no)
    if order.revision != payload.expected_revision:
        raise HTTPException(status_code=409, detail="订单已被其他人更新，请刷新后重试")
    if order.status not in {"PENDING_SUPPLIER", "PARTIALLY_RECEIVED"}:
        raise HTTPException(status_code=409, detail="减单仅适用于已确认锁定或部分到货的订单")

    before_quantity = quantity(order.product_order_quantity) if order.product_order_quantity is not None else None
    if order.quantity_basis == "EXPLICIT":
        if payload.reduction_quantity is not None:
            raise HTTPException(422, "直接填写需求的订单请逐纸品减单，不能以产品数量换算")
        reduction_quantity = None
        after_quantity = before_quantity
    else:
        if payload.reduction_quantity is None or payload.line_quantities:
            raise HTTPException(422, "按装箱数计算的订单必须填写产品减单数量")
        reduction_quantity = quantity(payload.reduction_quantity)
        if reduction_quantity > before_quantity:
            raise HTTPException(status_code=422, detail="减单数量不能超过当前订单数量")
        after_quantity = quantity(before_quantity - reduction_quantity)
    lines = _order_lines(db, order.id)
    line_ids = [line.id for line in lines]
    posted_received = protected_by_line(db, line_ids)
    fulfilled = fulfilled_by_line(db, line_ids)
    pending_received = _pending_received_by_line(db, line_ids)
    # Pending replacements restore the protected baseline; they do not add original demand.
    pending_received = {key: max(Decimal(0), value - (posted_received.get(key, Decimal(0)) - fulfilled.get(key, Decimal(0)))) for key, value in pending_received.items()}
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
    after_required = _explicit_targets(order, lines, payload.line_quantities, append=False) if order.quantity_basis == "EXPLICIT" else {
        line.id: (
            Decimal("0")
            if full_return
            else required_carton_quantity(after_quantity, line.usage_quantity)
        )
        for line in lines
    }
    if order.quantity_basis == "EXPLICIT":
        full_return = not any(after_required.values())
    protected_violations = [
        line
        for line in lines
        if after_required[line.id] < protected_quantity[line.id]
    ]
    if (protected_product_quantity is not None and after_quantity < protected_product_quantity) or protected_violations:
        details = "；".join(
            f"{line.packaging_type}调整后需求 {after_required[line.id]}，"
            f"已入库及待确认 {protected_quantity[line.id]}"
            for line in protected_violations
        )
        maximum_reduction = max(
            Decimal(0), quantity(before_quantity - protected_product_quantity)
        ) if protected_product_quantity is not None else "请按各纸品已入库及待确认数量核对"
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
            fulfilled.get(line.id, Decimal(0)) >= after_required[line.id]
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
            "quantity_basis": order.quantity_basis,
            "line_labels": {line.id: {"packaging_type": line.packaging_type, "paper_quality": line.paper_quality, "specification": line.specification, "unit": line.unit} for line in lines},
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
    _lock_receipt_factory(db, factory_id)
    order = get_order_by_no(db, factory_id, order_no)
    if order.revision != payload.expected_revision:
        raise HTTPException(status_code=409, detail="订单已被其他人更新，请刷新后重试")
    if order.status not in {"PARTIALLY_RECEIVED", "COMPLETED"}:
        raise HTTPException(status_code=409, detail="退单仅用于已发生入库的订单；未确认锁定的订单请取消，已确认锁定但未入库的订单不可取消")

    from app.services.carton_supplier_settlement import ensure_open
    ensure_open(db, factory_id, order.supplier_id, now_text()[:7])
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
        movement = CartonInventoryMovement(
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
        movement.unit_price = _issue_cost_price(db, movement)
        movement.issue_kind = "RETURN"
        positions.seed_unallocated(db, factory_id)
        allocations = [{"location_id": row.location_id, "quantity": str(-row.balance)}
                       for row in positions.position_balances(db, factory_id)
                       if row.inventory_key == line.id and row.balance > 0]
        positions.post(db, movement, allocations=allocations)
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
    _lock_receipt_factory(db, factory_id)
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
    if order.quantity_basis == "EXPLICIT":
        return None
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


def order_out(db: Session, order: CartonOrder, *, usage=None) -> CartonOrderOut:
    lines = _order_lines(db, order.id)
    line_ids = [line.id for line in lines]
    from app.services.carton_replenishment_receipts import options_by_line, legacy_review_lines
    replenishment_options = options_by_line(db, order.factory_id, line_ids)
    replenishment_review = legacy_review_lines(db, order.factory_id, line_ids)
    posted_received = protected_by_line(db, line_ids)
    received = fulfilled_by_line(db, line_ids)
    replenished = replenished_by_line(db, line_ids)
    pending_received = _pending_received_by_line(db, line_ids)
    protected_product_quantity = _protected_product_quantity(
        db,
        order,
        lines,
        posted_received,
        {key: max(Decimal(0), value - (posted_received.get(key, Decimal(0)) - received.get(key, Decimal(0)))) for key, value in pending_received.items()},
    )
    from app.services.carton_usage import usage_by_key, aggregate_status, LABELS
    if usage is None:
        usage = usage_by_key(db, order.factory_id)
    usage_status = aggregate_status((usage.get(line.id, {}).get("status", "NOT_RECEIVED") for line in lines),
        sum((usage.get(line.id, {}).get("usage", Decimal(0)) for line in lines), Decimal(0)))
    return CartonOrderOut(
        can_delete_history=can_delete_history_order(db, order),
        usage_status=usage_status, usage_status_label=LABELS[usage_status],
        id=order.id,
        factory_id=order.factory_id,
        order_no=order.order_no,
        customer_code=order.customer_code,
        customer_name=order.customer_name,
        supplier_id=order.supplier_id,
        supplier_name=order.supplier_name_snapshot,
        customer_po=order.customer_po,
        contract_no=order.contract_no,
        item_no=order.item_no,
        product_name=order.product_name,
        quantity_basis=order.quantity_basis,
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
        maximum_reducible_quantity=(max(Decimal(0), quantity(order.product_order_quantity - protected_product_quantity))
                                    if protected_product_quantity is not None else None),
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
                pending_received_quantity=pending_received.get(line.id, Decimal(0)),
                maximum_reducible_quantity=max(Decimal(0), line.required_quantity - max(posted_received.get(line.id, Decimal(0)), received.get(line.id, Decimal(0)) + pending_received.get(line.id, Decimal(0)))),
                received_quantity=received.get(line.id, Decimal(0)),
                replenished_quantity=replenished.get(line.id, Decimal(0)),
                replenishment_options=replenishment_options.get(line.id, []),
                replenishment_review_required=line.id in replenishment_review,
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
        if order.product_order_quantity is None or any(line.usage_quantity is None or line.required_quantity <= 0 or not line.paper_quality or not line.specification for line in _order_lines(db, order.id)):
            continue
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


def _ensure_receipt_capacity(
    db: Session,
    order_lines: dict[str, CartonOrderLine],
    additional: dict[str, Decimal],
) -> None:
    # Call only under the factory lock. Pending documents reserve effective quantities;
    # at confirmation the current document is already included in pending, not added twice.
    line_ids = list(order_lines)
    posted = fulfilled_by_line(db, line_ids)
    pending = _pending_received_by_line(db, line_ids)
    for line_id, line in order_lines.items():
        received = posted.get(line_id, Decimal(0))
        reserved = pending.get(line_id, Decimal(0))
        incoming = additional.get(line_id, Decimal(0))
        if received + reserved + incoming > line.required_quantity:
            order = db.get(CartonOrder, line.order_id)
            label = f"{order.contract_no} / {order.item_no}" if order else "订单"
            raise HTTPException(status_code=409, detail=(
                f"{label} · {line.packaging_type} {line.paper_quality}：累计收料超过订单需求。"
                f"需求 {line.required_quantity}，已入库 {received}，待确认 {reserved}，"
                f"本次新增 {incoming} {line.unit}。请先核对或作废多余的待确认收料单。"
            ))


def create_receipt(db: Session, payload: CartonReceiptCreate, user: AuthContext) -> CartonReceipt:
    if not payload.post_immediately:
        return _create_receipt(db, payload, user)
    factory_id = require_carton_factory(payload.factory_id)
    _lock_receipt_factory(db, factory_id)
    scope = json.dumps([factory_id, user.id, payload.request_id], separators=(",", ":"))
    event_id = f"CAE-RCP-{hashlib.sha256(scope.encode()).hexdigest()}"
    fingerprint = hashlib.sha256(json.dumps(payload.model_dump(mode="json", exclude={"request_id"}),
        sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    previous = db.scalar(select(CartonAuditEvent).where(CartonAuditEvent.id == event_id))
    if previous is not None:
        if json.loads(previous.detail_json).get("request", {}).get("fingerprint") != fingerprint:
            raise HTTPException(status_code=409, detail="本次提交标识已用于不同的收料内容，请核对原入库结果")
        return db.get(CartonReceipt, previous.entity_id)
    try:
        receipt = _create_receipt(db, payload, user, commit=False)
        confirm_receipt(db, receipt.id, CartonReceiptConfirmRequest(
            factory_id=factory_id, expected_revision=receipt.revision), user, commit=False)
        event = db.scalar(select(CartonAuditEvent).where(
            CartonAuditEvent.entity_id == receipt.id, CartonAuditEvent.event_type == "RECEIPT_CONFIRMED"))
        event.id = event_id
        detail = json.loads(event.detail_json)
        detail["request"] = {"fingerprint": fingerprint}
        event.detail_json = json.dumps(detail, ensure_ascii=False, sort_keys=True)
        db.commit()
        db.refresh(receipt)
        return receipt
    except Exception:
        db.rollback()
        raise


def _create_receipt(db: Session, payload: CartonReceiptCreate, user: AuthContext, *, commit: bool = True) -> CartonReceipt:
    factory_id = require_carton_factory(payload.factory_id)
    _lock_receipt_factory(db, factory_id)
    supplier = get_active_supplier(db, factory_id, payload.supplier_id)
    from app.services.carton_supplier_settlement import date_check, ensure_open
    if payload.acceptance_date:
        date_check(payload.acceptance_date)
        ensure_open(db, factory_id, supplier.id, payload.acceptance_date[:7])
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
    if any(order.supplier_id != supplier.id for order in orders.values()):
        raise HTTPException(status_code=422, detail="收料供应商必须与关联订单的供应商一致，请分供应商登记")
    if ineligible_orders:
        raise HTTPException(
            status_code=409,
            detail=f"订单 {', '.join(sorted(ineligible_orders))} 必须先确认并锁定，且保持待收料状态，才能登记收料",
        )
    for input_line in formal_inputs:
        line = by_id[input_line.order_line_id]
        if not line.paper_quality.strip() or not line.specification.strip():
            order = orders[line.order_id]
            if not any(issue.document_type == "LEGACY_BASELINE" for issue in _purchase_order_issues(db, order.id)):
                _require_receipt_material(line)
            before = {"paper_quality": line.paper_quality, "specification": line.specification}
            line.paper_quality = line.paper_quality or input_line.paper_quality.strip()
            line.specification = line.specification or input_line.specification.strip()
            _require_receipt_material(line)
            _audit(db, user, factory_id, "HISTORY_ORDER_MATERIAL_COMPLETED", "carton_order", order.id,
                   {"order_no": order.order_no, "line_id": line.id, "before": before,
                    "after": {"paper_quality": line.paper_quality, "specification": line.specification}})
            order.revision += 1
            order.updated_at = now_text()
            order.updated_by = user.id
            order.updated_by_name = user.display_name
        _require_receipt_material(line)
    _ensure_receipt_capacity(db, by_id, {
        line.order_line_id: quantity(line.received_quantity - line.damaged_quantity
                                     - line.rejected_quantity - line.unusable_quantity)
        for line in formal_inputs
    })
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
        acceptance_date=payload.acceptance_date,
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
        replacement_link = None
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
            from app.services.carton_replenishment_receipts import select_link
            replacement_link = select_link(db, factory_id, order_line, effective, input_line.replenishment_issue_id)
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
        if replacement_link:
            if replacement_link["responsibility"] == "SUPPLIER":
                snapshot["unit_price"] = Decimal(replacement_link["inventory_unit_price"])
            else:
                replacement_link["settlement_unit_price"] = str(snapshot["unit_price"])
            replacement_link["inventory_unit_price"] = str(snapshot["unit_price"])
        receipt_line_id = f"CRL-{uuid4().hex}"
        db.add(
            CartonReceiptLine(
                id=receipt_line_id,
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
                location_allocations_json=json.dumps(positions.validate_allocations(db, factory_id,
                    [a.model_dump(mode="json") for a in input_line.location_allocations], effective)),
                feedback_note=input_line.feedback_note,
            )
        )
        if replacement_link:
            from app.services.carton_replenishment_receipts import EVENT
            _audit(db, user, factory_id, EVENT, "carton_receipt_line", receipt_line_id,
                   {**replacement_link, "receipt_id": receipt_id, "order_line_id": input_line.order_line_id})
        elif input_line.source_type == "FORMAL_ORDER":
            from app.services.carton_replenishment_receipts import NORMAL_EVENT
            _audit(db, user, factory_id, NORMAL_EVENT, "carton_receipt_line", receipt_line_id,
                   {"receipt_id": receipt_id, "order_line_id": input_line.order_line_id, "quantity": str(effective)})
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
        db.commit() if commit else db.flush()
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
    from app.services.carton_replenishment_receipts import receipt_links, public_link
    links = receipt_links(db, receipt.factory_id)
    return CartonReceiptOut(
        id=receipt.id,
        factory_id=receipt.factory_id,
        receipt_no=receipt.receipt_no,
        delivery_note_no=receipt.delivery_note_no,
        delivery_date=receipt.delivery_date,
        acceptance_date=receipt.acceptance_date,
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
        lines=[CartonReceiptLineOut.model_validate(line).model_copy(update={**public_link(links.get(line.id)), "location_allocations": [CartonLocationAllocation.model_validate(a) for a in json.loads(line.location_allocations_json or "[]")]}) for line in _receipt_lines(db, receipt.id)],
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
    db.execute(update(CartonSupplier).where(CartonSupplier.factory_id == factory_id)
               .values(updated_at=CartonSupplier.updated_at))
    period = ledger_time(occurred_at).strftime("%Y-%m")
    locked = db.scalar(
        select(CartonClosing.period).where(
            CartonClosing.factory_id == factory_id,
            CartonClosing.customer_code == customer_code,
            CartonClosing.period >= period,
            CartonClosing.status == "LOCKED",
        ).order_by(CartonClosing.period.desc()).limit(1)
    )
    if locked:
        raise HTTPException(status_code=409, detail=f"{locked} 已锁账，不能新增或冲销影响该月结存的库存流水；请先由主管从最新锁账月份解锁重核")


def _lock_receipt_factory(db: Session, factory_id: str) -> None:
    # Receipt confirmation, correction and dependent order edits share this lock.
    lock_transaction(db, "carton-inventory", factory_id)
    db.execute(update(CartonSupplier).where(CartonSupplier.factory_id == factory_id)
               .values(updated_at=CartonSupplier.updated_at))
    db.expire_all()


def _refresh_order_statuses(db: Session, order_ids: set[str], user: AuthContext) -> None:
    for order_id in order_ids:
        order = db.get(CartonOrder, order_id)
        if order is None or order.status == "CANCELLED":
            continue
        lines = _order_lines(db, order.id)
        received = fulfilled_by_line(db, [line.id for line in lines])
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
    *, commit: bool = True,
) -> CartonReceipt:
    factory_id = require_carton_factory(payload.factory_id)
    _lock_receipt_factory(db, factory_id)
    receipt = db.get(CartonReceipt, receipt_id)
    if receipt is None or receipt.factory_id != factory_id:
        raise HTTPException(status_code=404, detail="收料单不存在")
    if receipt.status == "POSTED":
        return receipt
    if receipt.status != "PENDING_CONFIRMATION":
        raise HTTPException(status_code=409, detail="当前收料单状态不能确认")
    if receipt.revision != payload.expected_revision:
        raise HTTPException(status_code=409, detail="收料单已被其他人更新，请刷新后重试")
    from app.services.carton_supplier_settlement import date_check, ensure_open
    if receipt.acceptance_date:
        date_check(receipt.acceptance_date)
    ensure_open(db, factory_id, receipt.supplier_id, (receipt.acceptance_date or now_text()[:10])[:7])
    lines = _receipt_lines(db, receipt.id)
    if not lines:
        raise HTTPException(status_code=409, detail="收料单没有可确认的明细")
    from app.services.carton_replenishment_receipts import receipt_links, select_link, EVENT
    replacement_links = receipt_links(db, factory_id)
    # Validate the whole receipt before posting any line, including legacy drafts.
    missing_prices = [line for line in lines if line.effective_quantity > 0 and (
        line.unit_price is None or line.unit_price <= 0
    ) and replacement_links.get(line.id, {}).get("responsibility") != "SUPPLIER"]
    if missing_prices:
        labels = "、".join(
            f"{line.contract_no} / {line.item_no} · {line.packaging_type}"
            for line in missing_prices
        )
        raise HTTPException(status_code=422, detail=f"入库必须填写大于 0 的单价：{labels}。请补齐后再确认入库。")
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
    if any(order.supplier_id != receipt.supplier_id for order in receipt_orders.values()):
        raise HTTPException(status_code=409, detail="原收料供应商与关联订单不一致，请先更正收料单")
    if ineligible_orders:
        raise HTTPException(
            status_code=409,
            detail=f"订单 {', '.join(sorted(ineligible_orders))} 当前未处于已确认锁定的待收料状态，不能确认入库",
        )
    for order_line in order_lines.values():
        _require_receipt_material(order_line)
    _ensure_receipt_capacity(db, order_lines, {})
    for line in formal_lines:
        existing = replacement_links.get(line.id)
        checked = select_link(db, factory_id, order_lines[line.order_line_id], line.effective_quantity,
                              existing["replenishment_issue_id"] if existing else None, exclude_receipt=receipt.id)
        if checked and not existing:
            # Legacy unlinked drafts must be reviewed again; never silently change their payable basis.
            raise HTTPException(409, "收料草稿未关联补单，请作废后按具体补单重新登记")
    order_ids: set[str] = set()
    for line in lines:
        _ensure_period_open(db, factory_id, line.customer_code, timestamp)
        if line.source_type == "FORMAL_ORDER":
            order_line = order_lines[line.order_line_id]
            order_ids.add(order_line.order_id)
        if line.effective_quantity <= 0:
            continue
        movement = CartonInventoryMovement(
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
        positions.post(db, movement, allocations=json.loads(line.location_allocations_json or "[]"), legacy_location=line.location)
        if line.unit_price == 0 and replacement_links.get(line.id, {}).get("responsibility") == "SUPPLIER":
            _audit(db, user, factory_id, "INVENTORY_PRICE_CONFIRMED", "carton_inventory_movement", movement.id,
                   {"unit_price": "0", "reason": "供应商责任免费换补，原出库库存成本为零", "zero_price_confirmed": True})
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
        db.commit() if commit else db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="该收料单已确认或库存流水已生成") from exc
    db.refresh(receipt)
    return receipt


def _movement_key(movement: CartonInventoryMovement) -> str:
    return positions.inventory_key(movement)


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
            if column not in {"balance", "cost_status", "cost_currency", "cost_amount", "cost_unit_price"}
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
    all_rows = ordered_ledger_rows(db, factory_id)
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
        reference = db.get(CartonInventoryMovement, detail.get("reference_movement_id", ""))
        key = _movement_key(reference) if reference is not None and reference.factory_id == factory_id else detail.get("inventory_key")
        if key:
            locations[key] = (detail["to_location"], event.sequence)
    return locations


def inventory_balances(
    db: Session,
    factory_id: str,
    *,
    customer_code: str = "",
) -> list[CartonInventoryBalanceOut]:
    rows = ordered_ledger_rows(db, factory_id)
    totals: dict[str, Decimal] = defaultdict(Decimal)
    latest: dict[str, CartonInventoryMovement] = {}
    latest_inbound: dict[str, str] = {}
    locations = _inventory_locations(db, factory_id)
    physical_locations = defaultdict(list)
    for position in positions.position_balances(db, factory_id):
        if position.balance > 0:
            physical_locations[position.inventory_key].append(position.latest_location)
    for key, labels in physical_locations.items():
        summary = labels[0] if len(labels) == 1 else f"{len(labels)} 个仓位（详见分仓明细）"
        locations[key] = (summary, locations.get(key, ("", 0))[1])
    for row in rows:
        if customer_code and row.customer_code != customer_code:
            continue
        key = _movement_key(row)
        totals[key] += row.quantity
        latest[key] = row
        if row.movement_type == "INBOUND" or (row.source_type == "HISTORY_INVENTORY" and row.movement_type == "ADJUSTMENT" and row.quantity > 0):
            latest_inbound[key] = row.occurred_at
    return [
        CartonInventoryBalanceOut(
            inventory_key=key,
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


def relocate_inventory(db: Session, payload: CartonInventoryRelocateRequest, user: AuthContext) -> CartonInventoryBalanceOut:
    # Compatibility for older clients: only an unambiguous whole-position move.
    from app.schemas.carton_positions import PositionTransfer
    _lock_receipt_factory(db, payload.factory_id)
    reference = db.get(CartonInventoryMovement, payload.reference_movement_id)
    if reference is None or reference.factory_id != payload.factory_id:
        raise HTTPException(404, "库存结存记录不存在")
    positions.seed_unallocated(db, payload.factory_id)
    matches = [row for row in positions.position_balances(db, payload.factory_id)
               if row.inventory_key == _movement_key(reference) and row.balance > 0]
    if len(matches) != 1:
        raise HTTPException(409, "该库存已分仓，请刷新页面后按具体仓位调仓")
    source = matches[0]
    legacy_revision = _inventory_locations(db, payload.factory_id).get(source.inventory_key, ("", 0))[1]
    if legacy_revision != payload.expected_location_revision:
        raise HTTPException(409, "仓位已更新，请刷新后操作")
    from app.models.carton_positions import CartonLocation
    target = db.scalar(select(CartonLocation).where(CartonLocation.factory_id == payload.factory_id,
        CartonLocation.warehouse == "默认仓", CartonLocation.bin_code == payload.location.strip().upper()))
    if target is None:
        master_data.require_manage(db, user, payload.factory_id, "默认仓")
        target = positions.create_location(db, payload.factory_id, "默认仓", payload.location)
    positions.transfer(db, PositionTransfer(factory_id=payload.factory_id, request_id=uuid4().hex,
        position_key=source.position_key, expected_position_revision=source.position_revision,
        location_id=target.id, quantity=source.balance, note=payload.note), user)
    # Transfer commits its own transaction. Read the resulting balance and cost
    # together under the same lock used by the normal balance endpoint.
    from app.services.carton_inventory_money import annotate_balances
    _lock_receipt_factory(db, payload.factory_id)
    balances = annotate_balances(db, payload.factory_id, inventory_balances(db, payload.factory_id))
    return next(row for row in balances if row.inventory_key == source.inventory_key)


def _prepare_inventory_movement(
    db: Session,
    payload: CartonInventoryMovementCreate,
    user: AuthContext,
) -> tuple[CartonInventoryMovement, Decimal, CartonAuditEvent]:
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
        order_line_id=order_line.id if order_line is not None else reference.order_line_id,
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
        issue_kind=payload.issue_kind if payload.movement_type == "OUTBOUND" else "OTHER",
        workshop_id=payload.workshop_id if payload.movement_type == "OUTBOUND" else "",
        workshop_name=master_data.workshop_snapshot(db, factory_id, payload.workshop_id) if payload.movement_type == "OUTBOUND" else "",
        actor_user_id=user.id,
        actor_name=user.display_name,
        occurred_at=timestamp,
    )
    if signed_quantity < 0:
        movement.unit_price = _issue_cost_price(db, movement)
    from app.services.carton_supplier_settlement import movement_guard, return_supplier
    if movement.movement_type == "OUTBOUND" and movement.issue_kind == "RETURN" and not return_supplier(db, movement):
        raise HTTPException(status_code=409, detail="该库存无法确定供应商，暂不能登记退供应商；请先核实原收料来源。库存尚未扣减。")
    movement_guard(db, movement)
    positions.post(db, movement, location_id=payload.location_id, legacy_location=movement.location)
    event = _audit(db, user, factory_id, "INVENTORY_MOVEMENT_CREATED", "carton_inventory_movement", movement.id, {"movement_type": movement.movement_type, "quantity": movement.quantity})
    return movement, quantity(current + signed_quantity), event


def _issue_cost_price(db: Session, movement: CartonInventoryMovement) -> Decimal:
    valuation = load_valuation(db, movement.factory_id)
    key = cost_key(movement)
    balance = valuation.balances.get(key)
    if not balance or balance.quantity < abs(movement.quantity):
        raise HTTPException(status_code=409, detail="当前物料、单位和币种的计价库存不足")
    if any(cost_key(row) == key for row, _ in valuation.errors):
        raise HTTPException(status_code=409, detail="该物料历史计价异常，请先核对后再出库或调整")
    return (balance.amount / balance.quantity).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def _inventory_request(
    db: Session,
    payload: CartonInventoryMovementCreate | CartonInventoryBulkCreate,
    user: AuthContext,
    kind: str,
) -> tuple[str, str, list[CartonInventoryMovementOut] | None]:
    factory_id = require_carton_factory(payload.factory_id)
    # Serialize lookup and write together, including retries after timeout/restart.
    _lock_receipt_factory(db, factory_id)
    scope = json.dumps([factory_id, user.id, payload.request_id], separators=(",", ":"))
    event_id = f"CAE-REQ-{hashlib.sha256(scope.encode()).hexdigest()}"

    def canonical(value):
        if isinstance(value, Decimal):
            return format(value.quantize(QUANTITY_QUANTUM), "f")
        if isinstance(value, dict):
            return {key: canonical(item) for key, item in value.items()}
        if isinstance(value, list):
            return [canonical(item) for item in value]
        return value

    body = canonical(payload.model_dump(exclude={"request_id"}))
    fingerprint = hashlib.sha256(json.dumps([kind, body], sort_keys=True, separators=(",", ":"),
                                            ensure_ascii=False).encode()).hexdigest()
    previous = db.scalar(select(CartonAuditEvent).where(CartonAuditEvent.id == event_id))
    if previous is None:
        return event_id, fingerprint, None
    evidence = json.loads(previous.detail_json).get("request", {})
    if evidence.get("fingerprint") != fingerprint:
        raise HTTPException(status_code=409, detail="本次提交标识已用于不同的库存操作，请核对原操作结果")
    return event_id, fingerprint, [CartonInventoryMovementOut.model_validate(row) for row in evidence["result"]]


def _record_inventory_request(
    event: CartonAuditEvent,
    event_id: str,
    fingerprint: str,
    result: list[CartonInventoryMovementOut],
) -> None:
    # Add retry evidence to the existing business audit, atomically with its movements.
    # The audit's unique ID is the durable request receipt; no extra visible log entry.
    event.id = event_id
    detail = json.loads(event.detail_json)
    detail["request"] = {"fingerprint": fingerprint, "result": [row.model_dump(mode="json") for row in result]}
    event.detail_json = json.dumps(detail, ensure_ascii=False, sort_keys=True)


def create_inventory_movement(
    db: Session,
    payload: CartonInventoryMovementCreate,
    user: AuthContext,
) -> CartonInventoryMovementOut:
    event_id, fingerprint, replay = _inventory_request(db, payload, user, "single")
    if replay is not None:
        db.commit()
        return replay[0]
    movement, balance, event = _prepare_inventory_movement(db, payload, user)
    result = _movement_out(movement, balance)
    _record_inventory_request(event, event_id, fingerprint, [result])
    db.commit()
    return result


def create_inventory_movements_bulk(
    db: Session,
    payload: CartonInventoryBulkCreate,
    user: AuthContext,
) -> list[CartonInventoryMovementOut]:
    factory_id = require_carton_factory(payload.factory_id)
    event_id, fingerprint, replay = _inventory_request(db, payload, user, "bulk")
    if replay is not None:
        db.commit()
        return replay
    prepared: list[tuple[CartonInventoryMovement, Decimal, CartonAuditEvent]] = []
    for item in payload.items:
        prepared.append(
            _prepare_inventory_movement(
                db,
                CartonInventoryMovementCreate(
                    request_id=payload.request_id,
                    factory_id=factory_id,
                    order_line_id=item.order_line_id,
                    reference_movement_id=item.reference_movement_id,
                    movement_type="OUTBOUND",
                    quantity=item.quantity,
                    location=item.location,
                    location_id=item.location_id,
                    issue_kind=payload.issue_kind,
                    workshop_id=item.workshop_id or payload.workshop_id,
                    document_no=payload.document_no,
                    reason=payload.reason,
                ),
                user,
            )
        )
        db.flush()
    event = _audit(
        db,
        user,
        factory_id,
        "INVENTORY_BULK_OUTBOUND_CREATED",
        "carton_inventory_batch",
        payload.document_no,
        {
            "reason": payload.reason,
            "movement_ids": [movement.id for movement, _, _ in prepared],
            "line_count": len(prepared),
        },
    )
    result = [_movement_out(movement, balance) for movement, balance, _ in prepared]
    _record_inventory_request(event, event_id, fingerprint, result)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="批量出库流水冲突，请刷新库存后重试") from exc
    return result


def list_inventory_flow_summary(
    db: Session,
    factory_id: str,
    *,
    customer_code: str = "",
    date_from: str = "",
    date_to: str = "",
) -> list[CartonInventoryFlowSummaryOut]:
    reversed_receipts = set(db.scalars(select(CartonReceipt.id).where(
        CartonReceipt.factory_id == factory_id, CartonReceipt.status == "REVERSED")))
    groups = {}
    for row in ordered_ledger_rows(db, factory_id):
        day = ledger_time(row.occurred_at).date().isoformat()
        if row.movement_type not in {"INBOUND", "OUTBOUND"}:
            continue
        if row.source_type == "RECEIPT" and row.source_id in reversed_receipts:
            continue
        if (customer_code and row.customer_code != customer_code) or (date_from and day < date_from) or (date_to and day > date_to):
            continue
        key = (day, row.customer_code, row.customer_name, row.movement_type)
        group = groups.setdefault(key, {"documents": set(), "lines": 0, "quantity": Decimal(0)})
        group["documents"].add(row.document_no)
        group["lines"] += 1
        group["quantity"] += row.quantity
    return [CartonInventoryFlowSummaryOut(business_date=key[0], customer_code=key[1], customer_name=key[2],
        movement_type=key[3], document_count=len(value["documents"]), line_count=value["lines"],
        quantity=quantity(abs(value["quantity"])))
        for key, value in sorted(groups.items(), key=lambda pair: (-date.fromisoformat(pair[0][0]).toordinal(), pair[0][2], pair[0][3]))]



def reverse_receipt(
    db: Session, receipt_id: str, payload: CartonReceiptReverseRequest, user: AuthContext,
) -> CartonReceipt:
    factory_id = require_carton_factory(payload.factory_id)
    _lock_receipt_factory(db, factory_id)
    receipt = db.get(CartonReceipt, receipt_id)
    if receipt is None or receipt.factory_id != factory_id:
        raise HTTPException(status_code=404, detail="收料单不存在")
    if receipt.revision != payload.expected_revision or receipt.status not in {"PENDING_CONFIRMATION", "POSTED"}:
        raise HTTPException(status_code=409, detail="收料单状态或版本已变化，请刷新后重试")
    from app.services.carton_supplier_settlement import receipt_guard
    receipt_guard(db, receipt)
    previous_status = receipt.status
    lines = _receipt_lines(db, receipt.id)
    timestamp = now_text()
    reversals = []
    if previous_status == "POSTED":
        movements = list(db.scalars(select(CartonInventoryMovement).where(
            CartonInventoryMovement.factory_id == factory_id,
            CartonInventoryMovement.source_type == "RECEIPT",
            CartonInventoryMovement.source_id == receipt.id,
            CartonInventoryMovement.movement_type == "INBOUND",
        )))
        expected = {line.id: line for line in lines if line.effective_quantity > 0}
        if len(movements) != len(expected) or {row.source_line_id for row in movements} != set(expected):
            raise HTTPException(status_code=409, detail="原收料明细与入库流水不一致，请先核对数据")
        balances = {}
        for original in movements:
            if original.quantity != expected[original.source_line_id].effective_quantity:
                raise HTTPException(status_code=409, detail="原收料数量与入库流水不一致，请先核对数据")
            _ensure_period_open(db, factory_id, original.customer_code, original.occurred_at)
            _ensure_period_open(db, factory_id, original.customer_code, timestamp)
            if db.scalar(select(CartonInventoryMovement.id).where(
                CartonInventoryMovement.reversal_of_movement_id == original.id,
            )):
                raise HTTPException(status_code=409, detail="原入库流水已冲销，请刷新后重试")
            key = _movement_key(original)
            if key not in balances:
                balances[key] = _inventory_balance_for_key(db, factory_id, key)
            balances[key] -= original.quantity
            if balances[key] < 0:
                raise HTTPException(status_code=409, detail="冲销后库存不足，请先核对后续出库；本次整单未作任何更改")
            reversal_id = f"CIM-{uuid4().hex}"
            snapshot = {name: getattr(original, name) for name in (
                "factory_id", "order_line_id", "customer_code", "customer_name", "contract_no",
                "item_no", "packaging_type", "paper_quality", "specification", "unit", "unit_price", "currency", "location",
            )}
            reversal = CartonInventoryMovement(
                **snapshot, id=reversal_id, movement_type="REVERSAL", quantity=-original.quantity,
                document_no=f"REV-{receipt.receipt_no}", source_type="REVERSAL", source_id=original.id,
                source_line_id=reversal_id, reversal_of_movement_id=original.id, reason=payload.reason,
                actor_user_id=user.id, actor_name=user.display_name, occurred_at=timestamp,
            )
            reversal.workshop_id = original.workshop_id
            reversal.workshop_name = original.workshop_name
            reversal.issue_kind = original.issue_kind
            positions.post(db, reversal, reverse=original)
            reversals.append(reversal)
            _audit(db, user, factory_id, "INVENTORY_MOVEMENT_REVERSED", "carton_inventory_movement", original.id,
                   {"reversal_id": reversal_id, "receipt_id": receipt.id, "reason": payload.reason})
    # The original header/lines and confirmed timestamps remain available as evidence.
    receipt.status = "REVERSED"
    receipt.revision += 1
    receipt.updated_at = timestamp
    db.flush()
    order_line_ids = [line.order_line_id for line in lines if line.order_line_id]
    order_ids = set(db.scalars(select(CartonOrderLine.order_id).where(
        CartonOrderLine.factory_id == factory_id, CartonOrderLine.id.in_(order_line_ids),
    )))
    if previous_status == "POSTED":
        for order_id in order_ids:
            order = db.get(CartonOrder, order_id)
            if order and order.status in {"COMPLETED", "PARTIALLY_RECEIVED", "PENDING_SUPPLIER"}:
                before_revision = order.revision
                order_lines = _order_lines(db, order.id)
                received = fulfilled_by_line(db, [line.id for line in order_lines])
                if not any(received.values()):
                    order.status = "PENDING_SUPPLIER"
                else:
                    _refresh_order_statuses(db, {order.id}, user)
                if order.revision == before_revision:
                    order.revision += 1
                order.updated_by, order.updated_by_name, order.updated_at = user.id, user.display_name, timestamp
        valuation = load_valuation(db, factory_id)
        affected = {cost_key(row) for row in reversals}
        if any(cost_key(row) in affected for row, _ in valuation.errors):
            raise HTTPException(status_code=409, detail="冲销后库存金额无法对平，请先核对后续出库；本次整单未作任何更改")
    _audit(db, user, factory_id, "RECEIPT_REVERSED", "carton_receipt", receipt.id, {
        "receipt_no": receipt.receipt_no, "delivery_note_no": receipt.delivery_note_no,
        "previous_status": previous_status, "reason": payload.reason,
        "reversal_ids": [row.id for row in reversals], "order_ids": sorted(order_ids),
    })
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="收料单已被处理，请刷新后重试") from exc
    db.refresh(receipt)
    return receipt


def reverse_inventory_movement(
    db: Session,
    movement_id: str,
    payload: CartonInventoryReversalRequest,
    user: AuthContext,
) -> CartonInventoryMovementOut:
    factory_id = require_carton_factory(payload.factory_id)
    lock_transaction(db, "carton-inventory", factory_id)
    original = db.get(CartonInventoryMovement, movement_id)
    if original is None or original.factory_id != factory_id:
        raise HTTPException(status_code=404, detail="库存流水不存在")
    if original.source_type == "ORDER_REPLENISHMENT":
        raise HTTPException(409, "补单出库已关联供应商补单，不能通过普通库存冲销取消")
    from app.services.carton_supplier_settlement import movement_guard
    movement_guard(db, original)
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
    reversal.workshop_id = original.workshop_id
    reversal.workshop_name = original.workshop_name
    reversal.issue_kind = original.issue_kind
    positions.post(db, reversal, reverse=original)
    _audit(db, user, factory_id, "INVENTORY_MOVEMENT_REVERSED", "carton_inventory_movement", original.id, {"reversal_id": reversal_id, "reason": payload.reason})
    db.flush()
    valuation = load_valuation(db, factory_id)
    if any(cost_key(row) == cost_key(reversal) for row, _ in valuation.errors):
        raise HTTPException(status_code=409, detail="冲销后库存金额无法对平，请先核对或冲销后续出库记录")
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
    effective_profile["matching_version"] = "customer-po-v1"
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
    *, commit: bool = True,
) -> CartonException:
    factory_id = require_carton_factory(payload.factory_id)
    _lock_receipt_factory(db, factory_id)
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
    db.flush()
    if commit:
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
        if row.id.startswith("CAE-REQ-") and isinstance(detail, dict):
            detail.pop("request", None)  # Transport retry evidence is not a business log field.
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


def _pricing_issues(valuation: Valuation, customer_code: str, currency: str) -> list[dict]:
    issues = [(row, "入库单价待核实（原单价为 0）", True) for row in valuation.missing]
    issues += [(row, message, False) for row, message in valuation.errors]
    result = []
    seen = set()
    for row, message, can_price in issues:
        if row.customer_code != customer_code or normalize_currency(row.currency) != currency:
            continue
        if (row.id, message) in seen:
            continue
        seen.add((row.id, message))
        result.append(dict(movement_id=row.id, document_no=row.document_no, item_no=row.item_no,
                           packaging_type=row.packaging_type, occurred_at=row.occurred_at,
                           unit=row.unit, currency=currency, message=message, can_price=can_price))
    return result


_CLOSING_FIELDS = ("opening_quantity", "inbound_quantity", "outbound_quantity", "adjustment_quantity", "ending_quantity", "ending_amount")


def _closing_unit_quantities(rows, period):
    start, end = (ledger_time(day) for day in _period_bounds(period))
    units = defaultdict(lambda: {field: Decimal(0) for field in _CLOSING_FIELDS[:-1]})
    for row in rows:
        timestamp = ledger_time(row.occurred_at)
        if timestamp >= end:
            continue
        values = units[row.unit]
        field = ("opening_quantity" if timestamp < start else
                 "inbound_quantity" if row.movement_type == "INBOUND" else
                 "outbound_quantity" if row.movement_type == "OUTBOUND" else "adjustment_quantity")
        values[field] += -row.quantity if field == "outbound_quantity" else row.quantity
        values["ending_quantity"] += row.quantity
    return [{"unit": unit, **{field: format(quantity(value), "f") for field, value in values.items()}}
            for unit, values in sorted(units.items())]


def _saved_closing_units(db, closing, context=None):
    if context is not None:
        return context["units"].get(closing.id)
    # Extend existing immutable generation/price evidence; never rewrite a locked row.
    events = db.scalars(select(CartonAuditEvent).where(
        CartonAuditEvent.factory_id == closing.factory_id,
        CartonAuditEvent.event_type.in_(["CLOSING_GENERATED", "INVENTORY_PRICE_CONFIRMED"]),
        CartonAuditEvent.detail_json.contains(f'"{closing.id}"'),
    ).order_by(CartonAuditEvent.sequence.desc()))
    for event in events:
        snapshots = json.loads(event.detail_json or "{}").get("closing_unit_snapshots", {})
        if closing.id in snapshots:
            return snapshots[closing.id]
    return None


def _closing_current_snapshot(db: Session, closing: CartonClosing, valuation: Valuation, context=None) -> dict[str, Decimal]:
    start, end = _period_bounds(closing.period)
    rows = (ledger_rows(db, closing.factory_id, before=end, customer=closing.customer_code) if context is None else
            [row for row in context["rows"] if row.customer_code == closing.customer_code and ledger_time(row.occurred_at) < ledger_time(end)])
    result = {field: Decimal(0) for field in _CLOSING_FIELDS}
    for row in rows:
        if normalize_currency(row.currency) != normalize_currency(closing.currency):
            continue
        if ledger_time(row.occurred_at) < ledger_time(start):
            result["opening_quantity"] += row.quantity
        elif row.movement_type == "INBOUND":
            result["inbound_quantity"] += row.quantity
        elif row.movement_type == "OUTBOUND":
            result["outbound_quantity"] -= row.quantity
        else:
            result["adjustment_quantity"] += row.quantity
        result["ending_quantity"] += row.quantity
        result["ending_amount"] += valuation.amounts[row.id]
    result["ending_amount"] = result["ending_amount"].quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    return result


def _closing_snapshot_stale(db: Session, closing: CartonClosing, valuation: Valuation, context=None) -> bool:
    if any(getattr(closing, field) != value for field, value in _closing_current_snapshot(db, closing, valuation, context).items()):
        return True
    saved = _saved_closing_units(db, closing, context)
    if saved is None:
        return False  # Missing legacy evidence is disclosed separately, never invented.
    rows = [row for row in (context["rows"] if context is not None else ledger_rows(db, closing.factory_id))
            if row.customer_code == closing.customer_code and normalize_currency(row.currency) == normalize_currency(closing.currency)]
    return saved != _closing_unit_quantities(rows, closing.period)


def _closing_audit_snapshot(closing: CartonClosing) -> dict:
    return {name: getattr(closing, name) for name in (*_CLOSING_FIELDS, "period", "customer_code", "currency",
        "status", "revision", "confirmed_by", "confirmed_at", "locked_by", "locked_at", "generated_at")}


def closing_out(db: Session, closing: CartonClosing, context=None) -> CartonClosingOut:
    if context is None:
        context = _closing_read_context(db, closing.factory_id)
    result = CartonClosingOut.model_validate(closing)
    saved = _saved_closing_units(db, closing, context)
    result.quantities_by_unit = [CartonClosingUnitQuantities(**item) for item in saved or []]
    result.quantity_snapshot_missing = saved is None
    _, end = _period_bounds(closing.period)
    if context is None:
        valuation = load_valuation(db, closing.factory_id, before=end)
    else:
        if end not in context["valuations"]:
            context["valuations"][end] = value_movements(
                [row for row in context["rows"] if ledger_time(row.occurred_at) < ledger_time(end)], context["events"])
        valuation = context["valuations"][end]
    result.snapshot_stale = _closing_snapshot_stale(db, closing, valuation, context)
    if closing.status != "LOCKED":
        result.pricing_issues = [CartonPricingIssueOut(**issue) for issue in
                                 _pricing_issues(valuation, closing.customer_code, closing.currency)]
        result.pricing_issues.extend(_prior_locked_price_issues(db, closing, context))
    return result


def _closing_read_context(db, factory):
    # Serialize header/evidence/ledger reads with all inventory writers. Acquiring
    # the lock expires any ORM header loaded before a concurrent regeneration.
    lock_transaction(db, "carton-inventory", factory)
    events = list(db.scalars(select(CartonAuditEvent).where(
        CartonAuditEvent.factory_id == factory).order_by(CartonAuditEvent.sequence.desc())))
    units = {}
    for event in events:
        if event.event_type in {"CLOSING_GENERATED", "INVENTORY_PRICE_CONFIRMED"}:
            for identifier, values in json.loads(event.detail_json or "{}").get("closing_unit_snapshots", {}).items():
                units.setdefault(identifier, values)
    return {"rows": ledger_rows(db, factory), "events": events, "units": units, "valuations": {}}


def closing_outputs(db, closings):
    contexts = {factory: _closing_read_context(db, factory) for factory in sorted({row.factory_id for row in closings})}
    return [closing_out(db, closing, contexts[closing.factory_id]) for closing in closings]


def _prior_locked_price_issues(db: Session, closing: CartonClosing, context=None) -> list[CartonPricingIssueOut]:
    previous = db.scalar(select(CartonClosing).where(
        CartonClosing.factory_id == closing.factory_id,
        CartonClosing.customer_code == closing.customer_code,
        CartonClosing.currency == closing.currency,
        CartonClosing.period < closing.period,
        CartonClosing.status == "LOCKED",
    ).order_by(CartonClosing.period.desc()).limit(1))
    if previous is None:
        return []
    _, end = _period_bounds(previous.period)
    if context is None:
        valuation = load_valuation(db, closing.factory_id, before=end)
    else:
        if end not in context["valuations"]:
            context["valuations"][end] = value_movements(
                [row for row in context["rows"] if ledger_time(row.occurred_at) < ledger_time(end)], context["events"])
        valuation = context["valuations"][end]
    amount = sum((b.amount for key, b in valuation.balances.items()
                  if key[1] == closing.customer_code and key[-1] == closing.currency), Decimal(0))
    if amount.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP) == previous.ending_amount and not _closing_snapshot_stale(db, previous, valuation, context):
        return []
    return [CartonPricingIssueOut(
        movement_id=previous.id, document_no=f"{previous.period} 已锁账月结", item_no="", packaging_type="",
        occurred_at=f"{previous.period}-01", unit="", currency=closing.currency,
        message="历史锁账数量或金额与当前库存计价不一致，须先单独核对历史账务；系统不会改写已锁账快照",
    )]


def confirm_inventory_price(db: Session, movement_id: str, payload: CartonInventoryPriceConfirmRequest, user: AuthContext) -> None:
    factory_id = require_carton_factory(payload.factory_id)
    lock_transaction(db, "carton-inventory", factory_id)
    # Serialize price decisions with one another; original quantity/price evidence
    # is never overwritten. The existing closing permission guards this action.
    db.execute(update(CartonSupplier).where(CartonSupplier.factory_id == factory_id)
               .values(updated_at=CartonSupplier.updated_at))
    row = db.get(CartonInventoryMovement, movement_id)
    if row is None or row.factory_id != factory_id:
        raise HTTPException(status_code=404, detail="库存流水不存在")
    from app.services.carton_supplier_settlement import movement_guard
    movement_guard(db, row)
    if row.quantity <= 0 or row.movement_type == "REVERSAL" or row.unit_price != 0:
        raise HTTPException(status_code=409, detail="仅可核实缺价的入库或期初正调整记录")
    existing = db.scalar(select(CartonAuditEvent.id).where(
        CartonAuditEvent.factory_id == factory_id,
        CartonAuditEvent.event_type == "INVENTORY_PRICE_CONFIRMED",
        CartonAuditEvent.entity_id == row.id,
    ))
    if existing:
        raise HTTPException(status_code=409, detail="该单价已核实，请刷新月结")
    affected = list(db.scalars(select(CartonClosing).where(
        CartonClosing.factory_id == factory_id, CartonClosing.customer_code == row.customer_code,
        CartonClosing.currency == normalize_currency(row.currency),
        CartonClosing.period >= ledger_time(row.occurred_at).strftime("%Y-%m"),
    )).all())
    if any(c.status == "LOCKED" for c in affected):
        raise HTTPException(status_code=409, detail="补价会影响已锁账月份，须先由主管单独核对历史账务")
    price_event = _audit(db, user, factory_id, "INVENTORY_PRICE_CONFIRMED", "carton_inventory_movement", row.id,
           {"unit_price": payload.unit_price, "zero_price_confirmed": payload.zero_price_confirmed,
            "reason": payload.reason, "document_no": row.document_no, "item_no": row.item_no,
            "currency": row.currency, "unit": row.unit})
    # Price evidence changes require another review of affected unlocked snapshots.
    for closing in affected:
        closing.status = "DRAFT"
        closing.revision += 1
        closing.confirmed_by = closing.confirmed_at = ""
    db.flush()
    unit_snapshots = {}
    for closing in affected:
        start, end = _period_bounds(closing.period)
        valuation = load_valuation(db, factory_id, before=f"{end}T")
        rows = ledger_rows(db, factory_id, before=end, customer=closing.customer_code)
        rows = [row for row in rows if normalize_currency(row.currency) == closing.currency]
        closing.opening_quantity = quantity(sum((row.quantity for row in rows if ledger_time(row.occurred_at) < ledger_time(start)), Decimal(0)))
        current = [row for row in rows if ledger_time(row.occurred_at) >= ledger_time(start)]
        closing.inbound_quantity = quantity(sum((row.quantity for row in current if row.movement_type == "INBOUND"), Decimal(0)))
        closing.outbound_quantity = quantity(-sum((row.quantity for row in current if row.movement_type == "OUTBOUND"), Decimal(0)))
        closing.adjustment_quantity = quantity(sum((row.quantity for row in current if row.movement_type not in {"INBOUND", "OUTBOUND"}), Decimal(0)))
        closing.ending_quantity = quantity(sum((row.quantity for row in rows), Decimal(0)))
        closing.ending_amount = sum((valuation.amounts[row.id] for row in rows), Decimal(0)).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
        closing.generated_by = user.id
        closing.generated_by_name = user.display_name
        closing.generated_at = now_text()
        unit_snapshots[closing.id] = _closing_unit_quantities(rows, closing.period)
    price_detail = json.loads(price_event.detail_json)
    price_detail["closing_unit_snapshots"] = unit_snapshots
    price_event.detail_json = json.dumps(price_detail, ensure_ascii=False, sort_keys=True)
    db.commit()


def generate_closings(
    db: Session,
    payload: CartonClosingGenerateRequest,
    user: AuthContext,
) -> list[CartonClosing]:
    factory_id = require_carton_factory(payload.factory_id)
    _lock_receipt_factory(db, factory_id)
    start, end = _period_bounds(payload.period)
    movements = ledger_rows(db, factory_id, before=end)
    if payload.customer_code:
        movements = [row for row in movements if row.customer_code == payload.customer_code]
    valuation = load_valuation(db, factory_id, before=f"{end}T")
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
        if ledger_time(movement.occurred_at) < ledger_time(start):
            values["opening"] += movement.quantity
        else:
            if movement.movement_type == "INBOUND":
                values["inbound"] += movement.quantity
            elif movement.movement_type == "OUTBOUND":
                values["outbound"] += -movement.quantity
            else:
                values["adjustment"] += movement.quantity
        values["ending"] += movement.quantity
        values["amount"] += valuation.amounts[movement.id]

    timestamp = now_text()
    closings: list[CartonClosing] = []
    previous_snapshots = []
    unit_snapshots = {}
    for (customer_code, currency), values in sorted(aggregates.items()):
        existing = db.scalar(
            select(CartonClosing).where(
                CartonClosing.factory_id == factory_id,
                CartonClosing.period == payload.period,
                CartonClosing.customer_code == customer_code,
                CartonClosing.currency == currency,
            )
        )
        if existing is not None and existing.status == "LOCKED":
            closings.append(existing)
            continue
        if existing is not None:
            previous_snapshots.append({"id": existing.id, **_closing_audit_snapshot(existing)})
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
            closing.confirmed_by = closing.confirmed_at = ""
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
        unit_snapshots[closing.id] = _closing_unit_quantities(
            [row for row in movements if row.customer_code == customer_code and normalize_currency(row.currency) == currency],
            closing.period,
        )
    _audit(
        db,
        user,
        factory_id,
        "CLOSING_GENERATED",
        "carton_closing_period",
        payload.period,
        {
            "closing_count": len(closings),
            "previous_snapshots": previous_snapshots,
            "closing_unit_snapshots": unit_snapshots,
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
    lock_transaction(db, "carton-inventory", factory_id)
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


def unlock_closing(db: Session, closing_id: str, payload: CartonClosingUnlockRequest, user: AuthContext) -> CartonClosing:
    factory_id = require_carton_factory(payload.factory_id)
    _lock_receipt_factory(db, factory_id)
    closing = db.get(CartonClosing, closing_id)
    if closing is None or closing.factory_id != factory_id:
        raise HTTPException(status_code=404, detail="月结记录不存在")
    if closing.status != "LOCKED" or closing.revision != payload.expected_revision:
        raise HTTPException(status_code=409, detail="月结状态或版本已变化，请刷新后重试")
    later = db.scalar(select(CartonClosing).where(
        CartonClosing.factory_id == factory_id, CartonClosing.customer_code == closing.customer_code,
        CartonClosing.currency == closing.currency, CartonClosing.period > closing.period,
        CartonClosing.status == "LOCKED",
    ).order_by(CartonClosing.period.desc()).limit(1))
    if later:
        raise HTTPException(status_code=409, detail=f"{later.period} 已最终锁账，请先从最新月份依次解锁，避免后续账目失去核对依据")
    before = _closing_audit_snapshot(closing)
    closing.status = "DRAFT"
    closing.revision += 1
    closing.confirmed_by = closing.confirmed_at = ""
    closing.locked_by = closing.locked_at = ""
    _audit(db, user, factory_id, "CLOSING_UNLOCKED", "carton_closing", closing.id,
           {"reason": payload.reason, "before": before, "after_status": "DRAFT", "period": closing.period,
            "customer_code": closing.customer_code, "currency": closing.currency})
    db.commit()
    db.refresh(closing)
    return closing


def update_closing_status(
    db: Session,
    closing_id: str,
    payload: CartonClosingStatusRequest,
    user: AuthContext,
) -> CartonClosing:
    factory_id = require_carton_factory(payload.factory_id)
    _lock_receipt_factory(db, factory_id)
    closing = db.get(CartonClosing, closing_id)
    if closing is None or closing.factory_id != factory_id:
        raise HTTPException(status_code=404, detail="月结记录不存在")
    if closing.revision != payload.expected_revision:
        raise HTTPException(status_code=409, detail="月结记录已更新，请刷新后重试")
    transitions = {"DRAFT": "PENDING", "PENDING": "CONFIRMED", "CONFIRMED": "LOCKED"}
    if transitions.get(closing.status) != payload.status:
        raise HTTPException(status_code=409, detail="月结状态必须依次经过待核对、已确认和锁账")
    if payload.status == "LOCKED" and closing.period >= business_now().strftime("%Y-%m"):
        raise HTTPException(status_code=409, detail="该月份尚未结束，只能核对确认，不能最终锁账；不影响正常收发货")
    if payload.status in {"CONFIRMED", "LOCKED"}:
        _, end = _period_bounds(closing.period)
        valuation = load_valuation(db, factory_id, before=f"{end}T")
        issues = _pricing_issues(valuation, closing.customer_code, closing.currency)
        if issues:
            summary = "；".join(f"{item['document_no']} / {item['item_no']}：{item['message']}" for item in issues[:5])
            raise HTTPException(status_code=409, detail=f"存在 {len(issues)} 项计价问题，不能确认或锁账。{summary}")
        historical_issues = _prior_locked_price_issues(db, closing)
        if historical_issues:
            raise HTTPException(status_code=409, detail=historical_issues[0].message)
        if _saved_closing_units(db, closing) is None:
            raise HTTPException(status_code=409, detail="旧月结尚未保存分单位数量，请重新生成草稿后核对")
        if _closing_snapshot_stale(db, closing, valuation):
            raise HTTPException(status_code=409, detail="核对快照的数量或金额已变化，请重新生成草稿并核对确认后再操作")
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
