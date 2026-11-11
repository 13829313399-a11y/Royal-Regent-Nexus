"""Read-only monthly reconciliation for both portals and legacy audit projection."""
from collections import defaultdict
import json
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select, text

from app.models.carton_procurement import CartonAuditEvent, CartonInventoryMovement, CartonReceiptLine
from app.models.carton_price_review import CartonPriceReview
from app.models.carton_special_requests import SpecialShipment, UnifiedDelivery
from app.models.carton_supplier_portal import SupplierShipment
from app.services import carton_procurement as core
from app.services import carton_source_links
from app.services import carton_supplier_portal as portal
from app.services import carton_supplier_settlement as legacy

ENTITY = "carton_monthly_settlement"
SUBMIT_EVENT = "MONTHLY_SETTLEMENT_SUBMITTED"
CONFIRM_EVENT = "MONTHLY_SETTLEMENT_SUPPLIER_CONFIRMED"
DISPUTE_EVENT = "MONTHLY_SETTLEMENT_SUPPLIER_DISPUTED"
LOCK_EVENT = "MONTHLY_SETTLEMENT_LOCKED"
UNLOCK_EVENT = "MONTHLY_SETTLEMENT_UNLOCKED"
REVIEWED = {"SUBMITTED", "CONFIRMED", "DISPUTED"}


def money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def entity_id(supplier_id: str, period: str, currency: str) -> str:
    return f"{supplier_id}:{period}:{currency}"


def _events(db, factory: str, identifier: str):
    return list(db.scalars(select(CartonAuditEvent).where(
        CartonAuditEvent.factory_id == factory,
        CartonAuditEvent.entity_type == ENTITY,
        CartonAuditEvent.entity_id == identifier,
    ).order_by(CartonAuditEvent.sequence)))


def _detail(event) -> dict:
    try:
        value = json.loads(event.detail_json or "{}")
        return value if isinstance(value, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def derive_state(events) -> dict:
    """Pure reducer over normalized events, so the workflow is unit-testable."""
    state = {"status": "OPEN", "fingerprint": "", "totals": {}, "submitted_at": None, "submitted_by": None,
             "confirmed_at": None, "confirmed_by": None, "disputed_reason": "",
             "locked_at": None, "locked_by": None, "unlocked_reason": ""}
    for event in events:
        kind, detail = event["type"], event["detail"]
        if kind == SUBMIT_EVENT:
            state.update(status="SUBMITTED", fingerprint=detail.get("fingerprint") or "",
                         totals=detail.get("totals") or {}, submitted_at=event["at"],
                         submitted_by=event["actor"], confirmed_at=None, confirmed_by=None, disputed_reason="")
        elif kind == CONFIRM_EVENT:
            state.update(status="CONFIRMED", confirmed_at=event["at"], confirmed_by=event["actor"], disputed_reason="")
        elif kind == DISPUTE_EVENT:
            state.update(status="DISPUTED", disputed_reason=detail.get("reason") or "",
                         confirmed_at=None, confirmed_by=None)
        elif kind == LOCK_EVENT:
            state.update(status="LOCKED", locked_at=event["at"], locked_by=event["actor"],
                         fingerprint=state["fingerprint"] or detail.get("fingerprint") or "",
                         totals=detail.get("totals") or state["totals"])
        elif kind == UNLOCK_EVENT:
            state.update(status="OPEN", fingerprint="", totals={}, submitted_at=None, submitted_by=None,
                         confirmed_at=None, confirmed_by=None, disputed_reason="",
                         locked_at=None, locked_by=None, unlocked_reason=detail.get("reason") or "")
    return state


def workflow_state(db, factory: str, identifier: str) -> dict:
    return derive_state([{"type": event.event_type, "detail": _detail(event),
                          "at": event.created_at, "actor": event.actor_name}
                         for event in _events(db, factory, identifier)])


def is_stale(state: dict, fingerprint: str) -> bool:
    return bool(state["fingerprint"] and state["fingerprint"] != fingerprint)


def _amount(row) -> Decimal | None:
    return None if row["amount"] is None else Decimal(str(row["amount"]))


def _sum(rows) -> Decimal | None:
    amounts = [_amount(row) for row in rows]
    return None if any(value is None for value in amounts) else money(sum(amounts, Decimal(0)))


def blocking_issues(rows, issues, undated) -> list[str]:
    result = [str(issue) for issue in issues]
    if undated:
        result.append(f"有 {len(undated)} 张收料单未核实实际验收日期：{('、'.join(str(row.get('document_no') or '无单号') for row in undated))}")
    unpriced = [row for row in rows if row["kind"] == "RECEIPT" and row["amount"] is None]
    if unpriced:
        names = "、".join(f"{row.get('document_no') or '无单号'} {row.get('item_no') or ''}".strip() for row in unpriced[:6])
        result.append(f"{len(unpriced)} 行送货单缺价，不能计入应付：{names}")
    unpriced_returns = [row for row in rows if row["kind"] == "RETURN" and row["amount"] is None]
    if unpriced_returns:
        names = "、".join(str(row.get("document_no") or "无单号") for row in unpriced_returns[:6])
        result.append(f"{len(unpriced_returns)} 笔退货还没有供应商贷项价格：{names}")
    row_issues = [row for row in rows if row.get("issues")]
    for row in row_issues:
        detail = "；".join(str(issue) for issue in row["issues"])
        result.append(f"{row.get('document_no') or '无单号'} · {row.get('item_no') or '货号待补'}：{detail}")
    seen, unique = set(), []
    for issue in result:
        if issue not in seen:
            seen.add(issue)
            unique.append(issue)
    return unique


def _totals(rows):
    receipts = [row for row in rows if row["kind"] == "RECEIPT"]
    returns = [row for row in rows if row["kind"] == "RETURN"]
    refunds = [row for row in rows if row["kind"] == "RETURN_REFUND"]
    inbound, return_amount, refund_amount = _sum(receipts), _sum(returns), _sum(refunds)
    verified_net = Decimal(0)
    pending_price_lines = 0
    for row in rows:
        amount = _amount(row)
        if amount is None:
            pending_price_lines += 1
        else:
            verified_net += -amount if row["kind"] == "RETURN" else amount
    verified_net_text = str(money(verified_net))
    return {
        "inbound": None if inbound is None else str(inbound),
        "returns": None if return_amount is None else str(return_amount),
        "refunds": None if refund_amount is None else str(refund_amount),
        "net": None if pending_price_lines else verified_net_text,
        "verified_net": verified_net_text, "pending_price_lines": pending_price_lines,
        "documents": len({row["document_no"] for row in receipts if row.get("document_no")}),
        "receipt_lines": len(receipts), "return_lines": len(returns), "refund_lines": len(refunds),
    }


def _return_id(row):
    return row.get("return_movement_id") or (row["source_key"].removeprefix("RETURN:") if row["kind"] == "RETURN" else "")


def _delivery_links(db, factory, supplier_id, receipts):
    if not receipts:
        return {}
    linked = carton_source_links.line_sources(db, factory, list(receipts))
    links = {key: value["delivery_id"] for key, value in linked.items()}
    remaining = {receipt_id for key, receipt_id in receipts.items() if key not in links}
    if remaining:
        groups = carton_source_links.delivery_ids(db, factory)
        direct = defaultdict(set)
        for shipment in db.scalars(select(SupplierShipment).where(SupplierShipment.factory_id == factory,
                SupplierShipment.supplier_id == supplier_id, SupplierShipment.receipt_id.in_(remaining))):
            direct[shipment.receipt_id].add(groups.get(shipment.id, "FORMAL:" + shipment.id))
        links.update({key: next(iter(direct[receipt_id])) for key, receipt_id in receipts.items()
                      if key not in links and len(direct[receipt_id]) == 1})

    # Only offer supplier-owned links. The original detail endpoint rechecks authorization.
    permitted = set()
    for model, prefix in ((UnifiedDelivery, ""), (SupplierShipment, "FORMAL:"), (SpecialShipment, "SPECIAL:")):
        ids = {identifier.removeprefix(prefix) for identifier in links.values()
               if (identifier.startswith(prefix) if prefix else ":" not in identifier)}
        if ids:
            permitted.update(prefix + identifier for identifier in db.scalars(select(model.id).where(
                model.factory_id == factory, model.supplier_id == supplier_id, model.id.in_(ids))))
    return {key: identifier for key, identifier in links.items() if identifier in permitted}


def _customer(code, name):
    return (f"code:{code}" if code else f"name:{name}" if name else "unassigned", name or code or "未填写客户")


def _reconciliation_details(db, factory, supplier_id, rows):
    receipts = {row["source_key"].removeprefix("RECEIPT:"): row["receipt_id"] for row in rows if row["kind"] == "RECEIPT"}
    receipt_codes = dict(db.execute(select(CartonReceiptLine.id, CartonReceiptLine.customer_code).where(
        CartonReceiptLine.factory_id == factory, CartonReceiptLine.id.in_(receipts))).all()) if receipts else {}
    return_ids = {_return_id(row) for row in rows} - {""}
    return_codes = dict(db.execute(select(CartonInventoryMovement.id, CartonInventoryMovement.customer_code).where(
        CartonInventoryMovement.factory_id == factory, CartonInventoryMovement.id.in_(return_ids))).all()) if return_ids else {}
    delivery_links = _delivery_links(db, factory, supplier_id, receipts)
    customer_rows = defaultdict(list)
    names = {}
    for row in rows:
        if row["kind"] == "RECEIPT":
            line_id = row["source_key"].removeprefix("RECEIPT:")
            code = receipt_codes.get(line_id)
            row["reference"] = {"kind": "RECEIPT", "id": row["receipt_id"]}
            if line_id in delivery_links:
                row["supplier_reference"] = {"kind": "DELIVERY", "id": delivery_links[line_id]}
        else:
            movement_id = _return_id(row)
            code = return_codes.get(movement_id)
            if movement_id in return_codes:
                row["reference"] = {"kind": "RETURN", "id": movement_id}
                if row["kind"] == "RETURN_REFUND":
                    row["reference"]["refund_id"] = row["refund_evidence"]["id"]
                # An anomalous historical refund can survive a change in source ownership.
                if row["kind"] == "RETURN" or not row["issues"]:
                    row["supplier_reference"] = row["reference"]
        key, label = _customer(code, row.get("customer_name"))
        row["customer_key"] = key
        names.setdefault(key, label)
        customer_rows[key].append(row)
    return [{"key": key, "name": names[key], "totals": _totals(customer_rows[key])}
            for key in sorted(customer_rows, key=lambda key: (names[key], key))]


def supplier_line(row):
    keys = ("source_key", "kind", "document_no", "acceptance_date", "date_basis", "customer_key", "customer_name", "contract_no",
            "item_no", "packaging_type", "paper_quality", "specification", "unit", "quantity", "unit_price", "amount", "currency",
            "supplier_original_unit_price", "supplier_original_amount")
    safe = {key: row.get(key) for key in keys}
    safe["issues"] = []
    if row["kind"] == "RECEIPT":
        if row["amount"] is None:
            safe["issues"].append("送货单价待核实")
        if not row["acceptance_date"]:
            safe["issues"].append("实际验收日期待核实")
        if row["issues"] and not safe["issues"]:
            safe["issues"].append("原送货与验收资料有差异，请与仓库核对")
    elif row["kind"] == "RETURN":
        if row["issues"]:
            safe["issues"].append("退货签收、日期或贷项待核对")
        elif row["amount"] is None:
            safe["issues"].append("退货贷项金额待核实")
    elif row["issues"]:
        safe["issues"].append("退款与原退货的关联待核实")
    safe["reference"] = row.get("supplier_reference")
    return safe


def workspace(db, factory: str, period: str, currency: str) -> dict:
    """Read the authorized month in one snapshot after request authentication."""
    # Release the authentication transaction before configuring the snapshot.
    db.rollback()
    try:
        dialect = db.get_bind().dialect.name
        if dialect == "postgresql":
            db.connection(execution_options={"isolation_level": "REPEATABLE READ"})
            db.execute(text("SET TRANSACTION READ ONLY"))
        elif dialect == "sqlite":
            connection = db.connection()
            if not connection.connection.driver_connection.in_transaction:
                connection.exec_driver_sql("BEGIN")
        else:
            raise RuntimeError("Carton monthly reconciliation requires PostgreSQL or SQLite")
        return _workspace(db, factory, period, currency)
    finally:
        db.rollback()


def _workspace(db, factory: str, period: str, currency: str) -> dict:
    factory = core.require_carton_factory(factory)
    supplier = portal.fixed_supplier(db, factory)
    try:
        core._period_bounds(period)
    except (ValueError, OverflowError):
        raise HTTPException(422, "账期月份无效")
    currency = core.normalize_currency(currency)
    rows, fingerprint, issues, undated = legacy.sources(db, factory, supplier.id, period, currency)
    _attach_supplier_original_prices(db, factory, supplier.id, rows)
    totals = _totals(rows)
    customers = _reconciliation_details(db, factory, supplier.id, rows)
    receipt_groups = defaultdict(list)
    for row in rows:
        if row["kind"] == "RECEIPT":
            receipt_groups[row.get("packaging_type") or "纸品类型待补"].append(row)
    packaging = [{"name": name, "amount": None if (amount := _sum(group)) is None else str(amount)}
                 for name, group in receipt_groups.items()]
    identifier = entity_id(supplier.id, period, currency)
    state = workflow_state(db, factory, identifier)
    stale = is_stale(state, fingerprint)
    status = "STALE" if stale and state["status"] in REVIEWED else state["status"]
    blockers = blocking_issues(rows, issues, undated)
    if totals["net"] is None:
        blockers = blockers or ["本月金额仍有未核实价格，不能提交核对"]
    return {
        "factory_id": factory, "supplier_id": supplier.id, "supplier_name": supplier.supplier_name,
        "period": period, "currency": currency, "source_fingerprint": fingerprint,
        "read_only": True,
        "status": status,
        "stale": stale,
        "submitted_at": state["submitted_at"], "submitted_by": state["submitted_by"],
        "supplier_confirmed_at": state["confirmed_at"], "supplier_confirmed_by": state["confirmed_by"],
        "disputed_reason": state["disputed_reason"], "unlocked_reason": state["unlocked_reason"],
        "locked_at": state["locked_at"], "locked_by": state["locked_by"],
        "locked_totals": state["totals"] if status == "LOCKED" else None,
        "can_submit": False,
        "can_lock": False,
        "totals": totals,
        "customers": customers,
        "packaging": packaging,
        "global_issues": blocking_issues([], issues, undated),
        "blockers": blockers,
        "lines": rows,
    }


def _attach_supplier_original_prices(db, factory: str, supplier_id: str, rows) -> None:
    pending = {row["source_key"].removeprefix("RECEIPT:"): row for row in rows
               if row["kind"] == "RECEIPT" and row["amount"] is None}
    if not pending:
        return
    original_prices = db.execute(select(CartonPriceReview.receipt_line_id, CartonPriceReview.original_unit_price).where(
        CartonPriceReview.factory_id == factory, CartonPriceReview.supplier_id == supplier_id,
        CartonPriceReview.receipt_line_id.in_(pending), CartonPriceReview.original_unit_price > 0))
    for line_id, price in original_prices:
        row = pending[line_id]
        row["supplier_original_unit_price"] = str(price)
        row["supplier_original_amount"] = str(legacy.money(Decimal(str(row["quantity"])) * price))


def _locked_workspace(db, factory: str, period: str, currency: str) -> dict:
    core._lock_receipt_factory(db, factory)
    return _workspace(db, factory, period, currency)


def _permissions(db, user, factory: str) -> None:
    core.require_carton_factory(factory)
    from app.api.carton_procurement import _ensure_permission
    _ensure_permission(db, user, "carton_procurement:closing_manage", factory)
    _ensure_permission(db, user, "carton_procurement:order_adjust", factory)


def submit(db, user, payload) -> dict:
    factory = core.require_carton_factory(payload.factory_id)
    _permissions(db, user, factory)
    supplier = core.get_active_supplier(db, factory, None)
    currency = core.normalize_currency(payload.currency)
    identifier = entity_id(supplier.id, payload.period, currency)
    current = _locked_workspace(db, factory, payload.period, currency)
    status = current["status"]
    if status == "LOCKED":
        raise HTTPException(409, "本月已锁定；如需重新核对请先解锁")
    if status == "CONFIRMED":
        raise HTTPException(409, "供应商已确认，可直接完成月结；如需重新核对请先解锁")
    if status == "SUBMITTED" and not current["stale"]:
        return current
    if current["blockers"]:
        raise HTTPException(422, "本月还有待处理事项，不能提交核对：" + "；".join(current["blockers"][:6]))
    core._audit(db, user, factory, SUBMIT_EVENT, ENTITY, identifier, {
        "totals": current["totals"], "fingerprint": current["source_fingerprint"],
        "period": payload.period, "currency": currency,
    })
    db.commit()
    return workspace(db, factory, payload.period, currency)


def lock(db, user, payload) -> dict:
    factory = core.require_carton_factory(payload.factory_id)
    _permissions(db, user, factory)
    supplier = core.get_active_supplier(db, factory, None)
    currency = core.normalize_currency(payload.currency)
    identifier = entity_id(supplier.id, payload.period, currency)
    current = _locked_workspace(db, factory, payload.period, currency)
    status = current["status"]
    if status == "LOCKED":
        raise HTTPException(409, "本月已锁定；如需修改请先解锁")
    if status == "STALE":
        raise HTTPException(409, "本月来源已变化，请重新提交供应商核对")
    if status == "DISPUTED":
        raise HTTPException(409, "供应商已提出异议：" + (current["disputed_reason"] or "请先处理") + "；处理后再提交核对")
    if status == "SUBMITTED":
        raise HTTPException(409, "供应商尚未确认本月金额，不能锁定")
    if status != "CONFIRMED":
        raise HTTPException(409, "请先提交供应商核对，由供应商确认后再锁定")
    core._audit(db, user, factory, LOCK_EVENT, ENTITY, identifier, {
        "totals": current["totals"], "fingerprint": current["source_fingerprint"],
        "period": payload.period, "currency": currency,
    })
    db.commit()
    return workspace(db, factory, payload.period, currency)


def unlock(db, user, payload) -> dict:
    factory = core.require_carton_factory(payload.factory_id)
    _permissions(db, user, factory)
    supplier = core.get_active_supplier(db, factory, None)
    currency = core.normalize_currency(payload.currency)
    identifier = entity_id(supplier.id, payload.period, currency)
    current = _locked_workspace(db, factory, payload.period, currency)
    if current["status"] != "LOCKED":
        raise HTTPException(409, "本月尚未锁定，无需解锁")
    reason = (payload.reason or "").strip()
    if len(reason) < 4:
        raise HTTPException(422, "请填写至少四个字的解锁原因")
    core._audit(db, user, factory, UNLOCK_EVENT, ENTITY, identifier,
                {"reason": reason, "fingerprint": current["source_fingerprint"]})
    db.commit()
    return workspace(db, factory, payload.period, currency)


def _supplier_permission(user, factory: str, write: bool = False) -> None:
    from app.services import carton_supplier_portal as portal
    permission = "carton_supplier:approve" if write else "carton_supplier:read"
    if not portal.supplier_permission(user, permission, factory):
        raise HTTPException(403, "没有本厂供应商月结" + ("确认" if write else "查看") + "权限")


def supplier_confirm(db, user, payload) -> dict:
    factory = core.require_carton_factory(payload.factory_id)
    _supplier_permission(user, factory, write=True)
    supplier = core.get_active_supplier(db, factory, None)
    currency = core.normalize_currency(payload.currency)
    identifier = entity_id(supplier.id, payload.period, currency)
    current = _locked_workspace(db, factory, payload.period, currency)
    if current["status"] == "CONFIRMED" and not current["stale"]:
        return current
    if current["status"] == "LOCKED":
        raise HTTPException(409, "本月已被本厂锁定，不能再修改确认")
    if current["status"] == "STALE":
        raise HTTPException(409, "本月金额已变化，请等本厂重新提交后再确认")
    if current["status"] != "SUBMITTED":
        raise HTTPException(409, "本厂尚未提交本月核对，暂不能确认")
    core._audit(db, user, factory, CONFIRM_EVENT, ENTITY, identifier, {
        "fingerprint": current["source_fingerprint"], "totals": current["totals"],
    })
    db.commit()
    return workspace(db, factory, payload.period, currency)


def supplier_dispute(db, user, payload) -> dict:
    factory = core.require_carton_factory(payload.factory_id)
    _supplier_permission(user, factory, write=True)
    supplier = core.get_active_supplier(db, factory, None)
    currency = core.normalize_currency(payload.currency)
    identifier = entity_id(supplier.id, payload.period, currency)
    current = _locked_workspace(db, factory, payload.period, currency)
    if current["status"] == "LOCKED":
        raise HTTPException(409, "本月已被本厂锁定，不能再提出异议")
    if current["status"] not in {"SUBMITTED", "CONFIRMED"}:
        raise HTTPException(409, "本厂尚未提交本月核对，暂不能提出异议")
    reason = (payload.reason or "").strip()
    if len(reason) < 4:
        raise HTTPException(422, "请填写至少四个字的异议原因")
    core._audit(db, user, factory, DISPUTE_EVENT, ENTITY, identifier,
                {"reason": reason, "fingerprint": current["source_fingerprint"]})
    db.commit()
    return workspace(db, factory, payload.period, currency)
