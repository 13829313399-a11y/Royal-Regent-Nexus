"""Read-only order evidence and explicit, permission-scoped customer initialization."""
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.carton_mark import CartonMarkAsset, CartonMarkCustomer
from app.schemas.carton_mark import (
    CartonMarkCustomerInitializationCandidate,
    CartonMarkCustomerInitializationOut,
    CartonMarkCustomerOrderCandidate,
    CartonMarkCustomerRecognitionOut,
)
from app.services.auth import add_auth_audit, now_text
from app.services.carton_mark_assets import available_orders, identity
from app.services.carton_mark_customers import (
    CARTON_MARK_CUSTOMER_MANAGE_PERMISSION,
    normalize_carton_mark_customer_name,
)
from app.services.carton_mark_library import CARTON_MARK_WRITE_DEPARTMENTS, ensure_carton_mark_scope


def _managed(db, factory):
    return {c.normalized_name: c for c in db.scalars(select(CartonMarkCustomer).where(
        CartonMarkCustomer.factory_id == factory))}


def recognize_customer(db, user, factory, payload):
    for permission in ("carton_mark:read", "carton_mark:template_upload"):
        factory = ensure_carton_mark_scope(db, user, permission, factory, CARTON_MARK_WRITE_DEPARTMENTS)
    contract = identity(payload.contract_number)
    if not contract:
        return CartonMarkCustomerRecognitionOut(status="NO_MATCH", message="请填写合同号，再从本厂纸箱订单识别客名。")
    matches = [o for o in available_orders(db, factory) if identity(o.contract_no) == contract]
    # Preserve explicit source boundaries, including a source whose bound order was deleted.
    for asset_id, kind in ((payload.excel_asset_id, "excel"), (payload.pdf_asset_id, "pdf")):
        if not asset_id:
            continue
        asset = db.scalar(select(CartonMarkAsset).where(CartonMarkAsset.id == asset_id,
            CartonMarkAsset.factory_id == factory, CartonMarkAsset.is_archived.is_(False)))
        if asset is None or asset.kind != kind:
            raise HTTPException(404, "箱唛源文件不存在或不属于当前厂区")
        if asset.contract_number and identity(asset.contract_number) != contract:
            return CartonMarkCustomerRecognitionOut(status="CONFLICT", message="源文件关联的合同与填写的合同不同，请先确认资料。")
        if asset.bound_order_id or asset.recognition_source == "manual_order":
            matches = [o for o in matches if o.id == asset.bound_order_id]
    if identity(payload.item):
        matches = [o for o in matches if identity(o.item_no) == identity(payload.item)]
    if identity(payload.po):
        matches = [o for o in matches if identity(o.customer_po) == identity(payload.po)]
    if payload.order_id:
        matches = [o for o in matches if o.id == payload.order_id]
    candidates = [CartonMarkCustomerOrderCandidate(id=o.id, order_no=o.order_no,
        contract_no=o.contract_no, item_no=o.item_no, customer_code=o.customer_code,
        customer_name=o.customer_name) for o in sorted(matches, key=lambda o: (o.order_no, o.id))]
    if not matches:
        return CartonMarkCustomerRecognitionOut(status="NO_MATCH", message="没有匹配到有效的本厂纸箱订单，请核对合同号、ITEM，或手动选择客名。")
    codes = {identity(o.customer_code) for o in matches}
    names = {normalize_carton_mark_customer_name(o.customer_name) for o in matches}
    if len(codes) != 1 or "" in codes or len(names) != 1 or "" in names:
        return CartonMarkCustomerRecognitionOut(status="AMBIGUOUS", orders=candidates,
            message="订单对应多个客户或客名有差异，请明确选择一张订单。")
    name = " ".join(matches[0].customer_name.split())
    customer = _managed(db, factory).get(normalize_carton_mark_customer_name(name))
    return CartonMarkCustomerRecognitionOut(status="MATCHED", customer_name=customer.name if customer else name,
        managed_customer_id=customer.id if customer else None, orders=candidates,
        message="已根据本厂纸箱订单识别客名。" if customer else "已识别客名，尚未加入本厂箱唛客户库。")


def initialization_candidates(db, user, factory):
    factory = ensure_carton_mark_scope(db, user, CARTON_MARK_CUSTOMER_MANAGE_PERMISSION,
        factory, CARTON_MARK_WRITE_DEPARTMENTS)
    managed = _managed(db, factory)
    groups, code_names = {}, {}
    for order in available_orders(db, factory):
        name = " ".join(order.customer_name.split())
        key = normalize_carton_mark_customer_name(name)
        if not key:
            continue
        group = groups.setdefault(key, {"name": name, "orders": [], "codes": set()})
        group["orders"].append(order.id)
        group["codes"].add(identity(order.customer_code))
        code_names.setdefault(identity(order.customer_code), set()).add(key)
    result = []
    for key, group in sorted(groups.items()):
        codes = group["codes"]
        warning = ""
        if not codes or "" in codes or len(codes) > 1:
            warning = "同名订单的客户编码不唯一，请先核实客户身份。"
        elif any(len(code_names[code]) > 1 for code in codes):
            warning = "同一客户编码存在不同客名，请先在客户资料中确认名称。"
        elif len(group["name"]) > 128:
            warning = "客名超过 128 字，请手动维护。"
        existing = managed.get(key)
        result.append(CartonMarkCustomerInitializationCandidate(name=existing.name if existing else group["name"],
            order_count=len(group["orders"]), customer_codes=sorted(codes),
            existing_customer_id=existing.id if existing else None, warning=warning))
    return result


def initialize_customers(db, user, factory, payload, request=None):
    factory = ensure_carton_mark_scope(db, user, CARTON_MARK_CUSTOMER_MANAGE_PERMISSION,
        factory, CARTON_MARK_WRITE_DEPARTMENTS)
    # Recompute the evidence on write; a stale preview cannot import an arbitrary name.
    candidates = {normalize_carton_mark_customer_name(c.name): c for c in initialization_candidates(db, user, factory)}
    selected = {normalize_carton_mark_customer_name(name) for name in payload.names}
    if any(key not in candidates or candidates[key].warning for key in selected):
        raise HTTPException(409, "订单客名已变化或有歧义，请刷新候选客户；有歧义的客名需核实后通过“维护客户”处理。")
    created, existing = [], []
    for key in sorted(selected):
        candidate = candidates[key]
        if candidate.existing_customer_id:
            existing.append(candidate.name)
            continue
        timestamp = now_text()
        db.add(CartonMarkCustomer(id=f"CMC-{uuid4().hex.upper()}", factory_id=factory,
            name=candidate.name, normalized_name=key, revision=1,
            created_by=user.id, created_by_name=user.display_name, created_at=timestamp,
            updated_by=user.id, updated_by_name=user.display_name, updated_at=timestamp))
        created.append(candidate.name)
    if created:
        add_auth_audit(db, "carton_mark_customers_initialized", username=user.username,
            user_id=user.id, detail=f"从本厂纸箱订单初始化箱唛客名：{factory}/" + "、".join(created), request=request)
    try:
        db.commit()
    except IntegrityError as exception:
        db.rollback()
        raise HTTPException(409, "客户库已被其他人更新，请刷新候选客户后重试。") from exception
    return CartonMarkCustomerInitializationOut(created_names=created, existing_names=existing)
