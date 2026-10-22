"""Simplified monthly supplier settlement with one review round and one lock.

Money still comes from the audited settlement source builder, so supplier
delivery prices, returns and refunds keep their existing evidence. The flow is
plain: the factory submits the month, the supplier confirms it, then the factory
locks it. All state is derived from immutable audit events; no new table.
"""
import json
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select

from app.models.carton_procurement import CartonAuditEvent
from app.services import carton_procurement as core
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


def workspace(db, factory: str, period: str, currency: str) -> dict:
    factory = core.require_carton_factory(factory)
    core._lock_receipt_factory(db, factory)
    supplier = core.get_active_supplier(db, factory, None)
    try:
        core._period_bounds(period)
    except (ValueError, OverflowError):
        raise HTTPException(422, "账期月份无效")
    currency = core.normalize_currency(currency)
    rows, fingerprint, issues, undated = legacy.sources(db, factory, supplier.id, period, currency)
    adopt_supplier_original_prices(db, factory, rows)
    receipts = [row for row in rows if row["kind"] == "RECEIPT"]
    returns = [row for row in rows if row["kind"] == "RETURN"]
    refunds = [row for row in rows if row["kind"] == "RETURN_REFUND"]
    inbound, return_amount, refund_amount = _sum(receipts), _sum(returns), _sum(refunds)
    net = None if inbound is None or return_amount is None else money(inbound - return_amount + (refund_amount or Decimal(0)))
    identifier = entity_id(supplier.id, period, currency)
    state = workflow_state(db, factory, identifier)
    stale = is_stale(state, fingerprint)
    status = "STALE" if stale and state["status"] in REVIEWED else state["status"]
    blockers = blocking_issues(rows, issues, undated)
    if net is None:
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
        "totals": {
            "inbound": None if inbound is None else str(inbound),
            "returns": None if return_amount is None else str(return_amount),
            "refunds": None if refund_amount is None else str(refund_amount),
            "net": None if net is None else str(net),
            "documents": len({row["document_no"] for row in receipts if row.get("document_no")}),
            "receipt_lines": len(receipts),
            "return_lines": len(returns),
            "refund_lines": len(refunds),
        },
        "blockers": blockers,
        "lines": rows,
    }


def adopt_supplier_original_prices(db, factory: str, rows) -> None:
    """A supplier's own delivery-note price settles the line; no manual correction queue.

    When the receipt price is unresolved (zero/blank pending review) but the
    supplier note recorded a price at receipt time, use that supplier price.
    Lines without any supplier price still stay unresolved and block submission.
    """
    from app.models.carton_price_review import CartonPriceReview
    reviews = {row.receipt_line_id: row for row in db.scalars(
        select(CartonPriceReview).where(CartonPriceReview.factory_id == factory))}
    for row in rows:
        if row["kind"] != "RECEIPT" or row["amount"] is not None:
            continue
        review = reviews.get(row["source_key"].removeprefix("RECEIPT:"))
        if review is None or review.original_unit_price is None:
            continue
        price = Decimal(str(review.original_unit_price))
        row["unit_price"] = str(price)
        row["amount"] = str(money(Decimal(str(row["quantity"])) * price))
        row["price_basis"] = "SUPPLIER_ORIGINAL"
        row["issues"] = [issue for issue in row["issues"]
                         if issue not in {"入库单价待核实", "送货价格待双方核实，不能完成月结确认"}]


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
    current = workspace(db, factory, payload.period, currency)
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
    current = workspace(db, factory, payload.period, currency)
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
    current = workspace(db, factory, payload.period, currency)
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
    current = workspace(db, factory, payload.period, currency)
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
    current = workspace(db, factory, payload.period, currency)
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
