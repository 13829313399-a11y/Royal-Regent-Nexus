from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, or_, select
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
    CartonReceipt,
    CartonReceiptLine,
    CartonSupplier,
)
from app.schemas.carton_procurement import (
    CartonClosingGenerateRequest,
    CartonClosingOut,
    CartonClosingStatusRequest,
    CartonCustomerCreate,
    CartonCustomerUpdate,
    CartonDashboardOut,
    CartonExceptionListOut,
    CartonExceptionOut,
    CartonExceptionUpdate,
    CartonImportBatchOut,
    CartonInventoryBalanceOut,
    CartonInventoryMovementCreate,
    CartonInventoryMovementOut,
    CartonInventoryReversalRequest,
    CartonOrderCancelRequest,
    CartonOrderCreate,
    CartonOrderLineOut,
    CartonOrderOut,
    CartonOrderUpdate,
    CartonReceiptConfirmRequest,
    CartonReceiptCreate,
    CartonReceiptLineOut,
    CartonReceiptOut,
)
from app.services.auth import ALLOWED_FACTORY_IDS, AuthContext
from app.services.carton_procurement_imports import parse_carton_import


CARTON_DEPARTMENTS = ("pmc-warehouse", "carton")
CARTON_DEFAULT_SUPPLIER_CODE = "HEYUAN-DONGKANG"
CARTON_DEFAULT_SUPPLIER_NAME = "河源东康纸品有限公司"
QUANTITY_QUANTUM = Decimal("0.0001")
MONEY_QUANTUM = Decimal("0.0001")
MAX_IMPORT_BYTES = 20 * 1024 * 1024
ALLOWED_IMPORT_SUFFIXES = {".xlsx", ".xls", ".pdf", ".png", ".jpg", ".jpeg"}
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
        product_name=payload.product_name,
        product_order_quantity=payload.product_order_quantity,
        order_date=payload.order_date,
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
        required_quantity = quantity(payload.product_order_quantity * line.usage_quantity)
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
        {"line_count": len(payload.lines), "contract_no": payload.contract_no},
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
    schedule_changed = payload.due_date != order.due_date or payload.note != order.note
    if not structural_changed and not schedule_changed:
        raise HTTPException(status_code=422, detail="订单内容没有发生变化")
    if structural_changed and _order_has_business_activity(db, order):
        raise HTTPException(
            status_code=409,
            detail="订单已有收料或库存流水，只能修改计划交期和备注",
        )

    before = {
        "revision": order.revision,
        "customer_code": order.customer_code,
        "contract_no": order.contract_no,
        "item_no": order.item_no,
        "product_order_quantity": order.product_order_quantity,
        "order_date": order.order_date,
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
            required_quantity = quantity(payload.product_order_quantity * input_line.usage_quantity)
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

    order.due_date = payload.due_date
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


def cancel_order(
    db: Session,
    order_no: str,
    payload: CartonOrderCancelRequest,
    user: AuthContext,
) -> CartonOrder:
    factory_id = require_carton_factory(payload.factory_id)
    order = get_order_by_no(db, factory_id, order_no)
    if order.status == "CANCELLED":
        raise HTTPException(status_code=409, detail="订单已经取消")
    if order.status == "COMPLETED":
        raise HTTPException(status_code=409, detail="已完成订单不能取消")
    if order.revision != payload.expected_revision:
        raise HTTPException(status_code=409, detail="订单已被其他人更新，请刷新后重试")
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
            "reason": payload.reason,
            "previous_status": previous_status,
            "revision": order.revision,
        },
    )
    db.commit()
    db.refresh(order)
    return order


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


def order_out(db: Session, order: CartonOrder) -> CartonOrderOut:
    lines = _order_lines(db, order.id)
    received = _posted_received_by_line(db, [line.id for line in lines])
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
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[CartonOrder]]:
    query = select(CartonOrder).where(CartonOrder.factory_id == factory_id)
    if customer_code:
        query = query.where(CartonOrder.customer_code == customer_code)
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


def create_receipt(db: Session, payload: CartonReceiptCreate, user: AuthContext) -> CartonReceipt:
    factory_id = require_carton_factory(payload.factory_id)
    supplier = get_active_supplier(db, factory_id, payload.supplier_id)
    line_ids = [line.order_line_id for line in payload.lines]
    if len(line_ids) != len(set(line_ids)):
        raise HTTPException(status_code=422, detail="同一张收料单不能重复填写同一订单明细")
    order_lines = list(
        db.scalars(
            select(CartonOrderLine).where(
                CartonOrderLine.factory_id == factory_id,
                CartonOrderLine.id.in_(line_ids),
            )
        ).all()
    )
    by_id = {line.id: line for line in order_lines}
    if len(by_id) != len(line_ids):
        raise HTTPException(status_code=422, detail="存在不属于当前厂区或不存在的纸箱订单明细")
    orders = {
        order.id: order
        for order in db.scalars(
            select(CartonOrder).where(CartonOrder.id.in_({line.order_id for line in order_lines}))
        ).all()
    }
    if any(order.status == "CANCELLED" for order in orders.values()):
        raise HTTPException(status_code=409, detail="已取消的纸箱订单不能登记收料")

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
        order_line = by_id[input_line.order_line_id]
        order = orders[order_line.order_id]
        effective = quantity(
            input_line.received_quantity
            - input_line.damaged_quantity
            - input_line.rejected_quantity
            - input_line.unusable_quantity
        )
        db.add(
            CartonReceiptLine(
                id=f"CRL-{uuid4().hex}",
                factory_id=factory_id,
                receipt_id=receipt_id,
                line_no=index,
                order_line_id=order_line.id,
                customer_code=order.customer_code,
                customer_name=order.customer_name,
                contract_no=order.contract_no,
                item_no=order.item_no,
                packaging_type=order_line.packaging_type,
                paper_quality=order_line.paper_quality,
                specification=order_line.specification,
                delivered_quantity=input_line.delivered_quantity,
                received_quantity=input_line.received_quantity,
                damaged_quantity=input_line.damaged_quantity,
                rejected_quantity=input_line.rejected_quantity,
                unusable_quantity=input_line.unusable_quantity,
                effective_quantity=effective,
                unit=order_line.unit,
                unit_price=(input_line.unit_price if input_line.unit_price is not None else order_line.unit_price),
                currency=order_line.currency,
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
        {"delivery_note_no": payload.delivery_note_no, "line_count": len(payload.lines)},
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
    order_line_ids = [line.order_line_id for line in lines]
    order_lines = {
        line.id: line
        for line in db.scalars(select(CartonOrderLine).where(CartonOrderLine.id.in_(order_line_ids))).all()
    }
    if len(order_lines) != len(order_line_ids):
        raise HTTPException(status_code=409, detail="收料单关联的订单明细已不存在")
    order_ids: set[str] = set()
    for line in lines:
        _ensure_period_open(db, factory_id, line.customer_code, timestamp)
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
                reason="人工确认收料反馈后入库",
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
        {"delivery_note_no": receipt.delivery_note_no, "movement_count": sum(1 for line in lines if line.effective_quantity > 0)},
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
    for row in rows:
        if customer_code and row.customer_code != customer_code:
            continue
        key = _movement_key(row)
        totals[key] += row.quantity
        latest[key] = row
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
            latest_location=row.location,
            latest_movement_id=row.id,
            latest_movement_at=row.occurred_at,
        )
        for key, row in latest.items()
    ]


def create_inventory_movement(
    db: Session,
    payload: CartonInventoryMovementCreate,
    user: AuthContext,
) -> CartonInventoryMovementOut:
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
        location=payload.location or (reference.location if reference is not None else ""),
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
    db.commit()
    db.refresh(movement)
    return _movement_out(movement, current + signed_quantity)


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
        raise HTTPException(status_code=422, detail="仅支持 Excel、PDF、PNG 或 JPG 文件")
    if not content:
        raise HTTPException(status_code=422, detail="导入文件不能为空")
    if len(content) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="导入文件不能超过 20 MB")
    sha256 = hashlib.sha256(content).hexdigest()
    profile_text = (
        json.dumps(import_profile, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        if import_profile
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
    parse_options = dict(import_profile or {})
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
