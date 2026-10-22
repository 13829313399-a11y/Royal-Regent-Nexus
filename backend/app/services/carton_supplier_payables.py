"""Append-only supplier subledger, separate from stock and goods statements."""
import csv
import hashlib
import io
import json
import unicodedata
from collections import defaultdict
from datetime import date
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select

from app.models.carton_procurement import CartonAuditEvent, CartonReceipt, CartonReceiptLine, CartonInventoryMovement
from app.models.carton_supplier_settlement import CartonSupplierSettlement
from app.services import carton_procurement as core, carton_supplier_settlement as settlement

ENTITY = "carton_supplier_payables"
EVENT = "SUPPLIER_PAYABLES_ACTION"
ZERO = Decimal(0)
INTERNAL = {"PROPOSE_OPENING", "CONFIRM_OPENING", "PROPOSE_FEE", "REVISE_FEE", "VOID_FEE", "CONFIRM_FEE", "RECORD_PAYMENT",
    "CONFIRM_PAYMENT_RETURN", "REQUEST_VOID", "CONFIRM_VOID", "ALLOCATE", "DEALLOCATE"}
EXTERNAL = {"REVIEW_OPENING", "REVIEW_FEE", "RECEIVE_PAYMENT", "DECLARE_PAYMENT_RETURN", "REVIEW_VOID"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str).encode()).hexdigest()


def money(value):
    return format(settlement.money(value), ".2f")


def text(value):
    return " ".join(str(value or "").split())


def identity(value):
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).split()).casefold()


def required(value, label):
    value = text(value)
    if not value: raise HTTPException(422, f"请填写{label}")
    return value


def day(value, label):
    if value is None: raise HTTPException(422, f"请填写{label}")
    result = value.isoformat() if isinstance(value, date) else str(value)
    try:
        if date.fromisoformat(result).isoformat() != result: raise ValueError()
    except ValueError as exc: raise HTTPException(422, f"{label}格式无效") from exc
    if result > settlement._posting_date(core.now_text()): raise HTTPException(422, f"{label}不能晚于上海今天")
    return result


def authorize(db, user, factory, supplier_id=None, *, external=False, write=False):
    from app.services import carton_special_requests as special, carton_supplier_portal as portal
    core.require_carton_factory(factory)
    currency_permissions = ("read", "closing_manage", "order_adjust") if write else ("read",)
    if external:
        if not portal.supplier_permission(user, "carton_supplier:read", factory) or write and not portal.supplier_permission(user, "carton_supplier:approve", factory):
            raise HTTPException(403, "没有本厂供应商往来读取或审批权限")
        supplier = portal.supplier_access(db, user, factory)
        if supplier_id and supplier_id != supplier.id: raise HTTPException(404, "未找到可访问的供应商往来")
    else:
        if not all(special.allowed(user, factory, item) for item in currency_permissions): raise HTTPException(403, "供应商往来办理须具备本厂读取、月结及调整权限")
        supplier = core.get_active_supplier(db, factory, supplier_id)
    if supplier.supplier_code != "HEYUAN-DONGKANG": raise HTTPException(409, "当前在线双方往来仅支持东康，其他供应商保留原手工月结")
    return supplier


def account_id(factory, supplier, currency):
    return "APAC-" + digest([factory, supplier, currency])


def events(db, factory, supplier, currency):
    return list(db.scalars(select(CartonAuditEvent).where(CartonAuditEvent.factory_id == factory,
        CartonAuditEvent.entity_type == ENTITY, CartonAuditEvent.entity_id == account_id(factory, supplier, currency),
        CartonAuditEvent.event_type == EVENT).order_by(CartonAuditEvent.sequence)))


def fold(records):
    state = dict(revision=0, opening=None, fees={}, payments={}, returns={}, allocations=[], history=[])
    for event in records:
        detail = json.loads(event.detail_json); name, data = detail["action"], detail["data"]
        state["revision"] = detail["revision"]
        info = dict(id=event.id, action=name, actor_name=event.actor_name, created_at=event.created_at,
            reason=data["reason"], target_id=data.get("record_id", ""), data=data)
        state["history"].append(info)
        identifier = data.get("record_id")
        if name in {"PROPOSE_OPENING", "PROPOSE_FEE", "REVISE_FEE", "VOID_FEE"}:
            row = state["opening"] if name == "PROPOSE_OPENING" else state["fees"].get(identifier)
            if row is None:
                row = dict(id=identifier, kind="OPENING" if name == "PROPOSE_OPENING" else "FEE", active=None, proposal=None, versions=[])
                if name == "PROPOSE_OPENING": state["opening"] = row
                else: state["fees"][identifier] = row
            if row["proposal"]: row["proposal"]["status"] = "SUPERSEDED"
            version = dict(data, event_id=event.id, version=len(row["versions"]) + 1, status="PENDING_SUPPLIER", created_at=event.created_at, created_by=event.actor_name)
            row["versions"].append(version); row["proposal"] = version
        elif name in {"REVIEW_OPENING", "REVIEW_FEE"}:
            row = state["opening"] if name == "REVIEW_OPENING" else state["fees"][identifier]
            row["proposal"]["supplier_review"] = dict(decision=data["decision"], by=event.actor_name, at=event.created_at, reason=data["reason"])
            row["proposal"]["status"] = "SUPPLIER_CONFIRMED" if data["decision"] == "CONFIRMED" else "DISPUTED"
        elif name in {"CONFIRM_OPENING", "CONFIRM_FEE"}:
            row = state["opening"] if name == "CONFIRM_OPENING" else state["fees"][identifier]
            if row["active"]: row["active"]["status"] = "SUPERSEDED"
            row["active"] = row["proposal"]; row["proposal"] = None
            row["active"].update(status="VOID" if row["active"].get("voids") else "EFFECTIVE", confirmation_id=event.id,
                confirmed_by=event.actor_name, confirmed_at=event.created_at)
        elif name == "RECORD_PAYMENT":
            state["payments"][identifier] = dict(data, id=identifier, kind="PAYMENT", status="RECORDED", receipt_status="PENDING",
                created_at=event.created_at, created_by=event.actor_name, event_id=event.id, void_request=None)
        elif name == "RECEIVE_PAYMENT":
            row = state["payments"][identifier]
            row.update(receipt_status=data["decision"], status="RECEIVED" if data["decision"] == "CONFIRMED" else "DISPUTED",
                receipt_review=dict(decision=data["decision"], by=event.actor_name, at=event.created_at, reason=data["reason"]))
        elif name == "DECLARE_PAYMENT_RETURN":
            state["returns"][identifier] = dict(data, id=identifier, kind="PAYMENT_RETURN", status="DECLARED", confirmed=False,
                created_at=event.created_at, created_by=event.actor_name, event_id=event.id, void_request=None)
        elif name == "CONFIRM_PAYMENT_RETURN":
            state["returns"][identifier].update(status="CONFIRMED", confirmed=True, confirmation_id=event.id,
                confirmation_reference=data["confirmation_reference"], confirmed_at=event.created_at, confirmed_by=event.actor_name)
        elif name in {"REQUEST_VOID", "REVIEW_VOID", "CONFIRM_VOID"}:
            row = state["payments"].get(identifier) or state["returns"][identifier]
            if name == "REQUEST_VOID": row["void_request"] = dict(data, status="PENDING_SUPPLIER", event_id=event.id)
            elif name == "REVIEW_VOID": row["void_request"].update(status="SUPPLIER_CONFIRMED" if data["decision"] == "CONFIRMED" else "DISPUTED", supplier_review=info)
            else: row.update(status="VOID", voided_at=event.created_at, voided_by=event.actor_name)
        elif name == "ALLOCATE":
            for allocation in data["allocations"]:
                state["allocations"].append(dict(allocation, status="ACTIVE", actor_name=event.actor_name, created_at=event.created_at, reason=data["reason"]))
        elif name == "DEALLOCATE":
            for allocation in state["allocations"]:
                if allocation["id"] in data["allocation_ids"]: allocation.update(status="RELEASED", released_at=event.created_at, released_by=event.actor_name)
    return state


def bills(db, factory, supplier, currency):
    rows = list(db.scalars(select(CartonSupplierSettlement).where(CartonSupplierSettlement.factory_id == factory,
        CartonSupplierSettlement.supplier_id == supplier, CartonSupplierSettlement.currency == currency)
        .order_by(CartonSupplierSettlement.period.desc(), CartonSupplierSettlement.version.desc())))
    latest, confirmed = {}, {}
    for row in rows:
        latest.setdefault(row.period, row)
        if row.confirmed_at: confirmed.setdefault(row.period, row)
    return latest, confirmed


def baseline(db, factory, supplier, currency, cutoff, previous_periods=()):
    """Economic evidence only: later bank/assignment events never stale opening."""
    from app.services import carton_return_dates, carton_return_collaboration
    periods = set(previous_periods)
    unknown = []
    receipts = list(db.scalars(select(CartonReceipt).where(CartonReceipt.factory_id == factory, CartonReceipt.supplier_id == supplier, CartonReceipt.status == "POSTED")))
    for receipt in receipts:
        lines = [line for line in db.scalars(select(CartonReceiptLine).where(CartonReceiptLine.receipt_id == receipt.id,
            CartonReceiptLine.factory_id == factory).order_by(CartonReceiptLine.id)) if core.normalize_currency(line.currency) == currency and line.effective_quantity > 0]
        if not lines: continue
        if receipt.acceptance_date and receipt.acceptance_date < cutoff: periods.add(receipt.acceptance_date[:7])
        elif receipt.status == "POSTED" and not receipt.acceptance_date:
            month = settlement._posting_date(receipt.confirmed_at)[:7] if receipt.confirmed_at else cutoff[:7]
            economic_rows, source_fp, _, _ = settlement.sources(db, factory, supplier, month, currency)
            from app.services.carton_settlement_collaboration import build
            vendor_rows = build(db, factory, supplier, month, currency, economic_rows, source_fp)["sources"]
            keys = {"RECEIPT:" + line.id for line in lines}
            unknown.append(dict(receipt_id=receipt.id, document_no=receipt.delivery_note_no,
                lines=[dict(id=line.id, quantity=str(line.effective_quantity), price=str(line.unit_price)) for line in lines],
                financial_evidence=[{key: value for key, value in row.items() if key != "delivery_id"} for row in vendor_rows if row["source_key"] in keys]))
    date_records = carton_return_dates.dates(db, factory)
    movements = list(db.scalars(select(CartonInventoryMovement).where(CartonInventoryMovement.factory_id == factory)))
    reversed_ids = {movement.reversal_of_movement_id for movement in movements if movement.reversal_of_movement_id}
    for movement in movements:
        if not carton_return_dates.is_return(movement) or movement.quantity >= 0 or movement.id in reversed_ids: continue
        if settlement.return_supplier(db, movement) != supplier or core.normalize_currency(movement.currency) != currency: continue
        actual = date_records.get(movement.id) or settlement._posting_date(movement.occurred_at)
        if actual < cutoff: periods.add(actual[:7])
    return_events = defaultdict(list)
    for event in carton_return_collaboration.events(db, factory): return_events[event.entity_id].append(event)
    for records in return_events.values():
        state = carton_return_collaboration.ledger(records)
        if state["supplier_id"] != supplier: continue
        for data in state["refunds"]:
            if (data["kind"] == "CASH" and data["status"] == "CONFIRMED"
                    and core.normalize_currency(data.get("currency")) == currency and data["refund_date"] < cutoff): periods.add(data["refund_date"][:7])
    _, confirmed = bills(db, factory, supplier, currency)
    periods.update(period for period in confirmed if period < cutoff[:7])
    economic = []
    for period in sorted(period for period in periods if period < cutoff[:7]):
        rows, _, _, _ = settlement.sources(db, factory, supplier, period, currency)
        economic.append(dict(period=period, rows=[{key: value for key, value in row.items() if key != "delivery_id"} for row in rows]))
    approved = [dict(id=row.id, period=period, version=row.version, source_fingerprint=row.source_fingerprint,
        statement=json.loads(row.statement_json), net_amount=json.loads(row.result_json).get("net_amount")) for period, row in sorted(confirmed.items()) if period < cutoff[:7]]
    unknown.sort(key=lambda row: row["receipt_id"])
    return dict(fingerprint=digest([economic, approved, unknown]), periods=sorted(periods), unknown_sources=unknown)


def active_allocations(state):
    return [row for row in state["allocations"] if row["status"] == "ACTIVE"]


def allocated_to(state, identifier):
    return sum((Decimal(row["amount"]) for row in active_allocations(state) if row["target_id"] == identifier or row["source_id"] == identifier), ZERO)


def require_unallocated(state, identifier):
    if allocated_to(state, identifier): raise HTTPException(409, "此确认版本已有核销，请先明确解除分配；实际付款和原凭证会保留")


def return_reserved(state, payment):
    return sum((Decimal(row["amount"]) for row in state["returns"].values() if row["status"] != "VOID" and row["parent_payment_id"] == payment), ZERO)


def is_voiding(row):
    return row.get("void_request") and row["void_request"]["status"] != "DISPUTED" and row["status"] != "VOID"


def context(db, factory, supplier, currency):
    state = fold(events(db, factory, supplier, currency))
    opening = state["opening"]; active = opening["active"] if opening else None
    cutoff = active["cutoff_date"] if active else None
    proof = baseline(db, factory, supplier, currency, cutoff, active.get("baseline_periods", [])) if active else None
    stale = bool(active and proof["fingerprint"] != active["baseline_fingerprint"])
    latest, confirmed = bills(db, factory, supplier, currency)
    obligations = []
    def add(identifier, kind, record, version, amount, when, document, status="CURRENT", fingerprint=""):
        used = allocated_to(state, identifier)
        obligations.append(dict(id=identifier, kind=kind, record_id=record, version=version, currency=currency,
            signed_amount=money(amount), direction="CREDIT" if amount < 0 else "DEBIT", date=when, document_no=document,
            allocated_amount=money(used), remaining_amount=money(max(ZERO, abs(amount)-used)),
            can_allocate=bool(active and not stale and status == "CURRENT" and abs(amount) > used), status=status, source_fingerprint=fingerprint))
    if active:
        add("OPENING:" + active["confirmation_id"], "OPENING", opening["id"], active["version"], Decimal(active["signed_amount"]), cutoff, active["document_no"], "STALE" if stale else "REOPENED_HOLD" if opening["proposal"] else "CURRENT", active["baseline_fingerprint"])
    confirmed_total = ZERO
    bill_heads = []
    for period, row in confirmed.items():
        if not cutoff or period < cutoff[:7]: continue
        amount = Decimal(json.loads(row.result_json)["net_amount"])
        hold = latest[period].id != row.id or row.status != "CONFIRMED"
        confirmed_total += amount
        bill_heads.append([row.id, row.revision, row.status, latest[period].id, latest[period].revision, row.source_fingerprint])
        add("SETTLEMENT:" + row.id, "SETTLEMENT", row.id, row.version, amount, period + "-01", json.loads(row.statement_json).get("statement_no", ""), "REOPENED_HOLD" if hold else "CURRENT", row.source_fingerprint)
        obligations[-1]["period"] = period
    fees_total = ZERO
    for row in state["fees"].values():
        version = row["active"]
        if not version: continue
        amount = Decimal(version["signed_amount"]); fees_total += amount
        if amount:
            add("FEE:" + version["confirmation_id"], "FEE", row["id"], version["version"], amount, version["date"], version["document_no"], "REOPENED_HOLD" if row["proposal"] else "CURRENT", fingerprint=version["event_id"])
    paid = sum((Decimal(row["amount"]) for row in state["payments"].values() if row["status"] != "VOID"), ZERO)
    received = sum((Decimal(row["amount"]) for row in state["payments"].values() if row["status"] != "VOID" and row["receipt_status"] == "CONFIRMED"), ZERO)
    returned = sum((Decimal(row["amount"]) for row in state["returns"].values() if row["status"] != "VOID" and row["confirmed"]), ZERO)
    sources = []
    for row in state["payments"].values():
        if row["status"] == "VOID": continue
        amount, used, reserved = Decimal(row["amount"]), allocated_to(state, row["id"]), return_reserved(state, row["id"])
        available = max(ZERO, amount-used-reserved)
        sources.append(dict(id=row["id"], source_kind="PAYMENT", record_id=row["id"], document_no=row["document_no"], date=row["date"], currency=currency,
            amount=row["amount"], allocated_amount=money(used), reserved_return_amount=money(reserved), available_amount=money(available), returnable_amount=money(available),
            can_allocate=bool(active and not stale and row["receipt_status"] == "CONFIRMED" and not is_voiding(row) and available),
            can_declare_payment_return=bool(active and not is_voiding(row) and available)))
    for row in obligations:
        if row["direction"] == "CREDIT":
            sources.append(dict(id=row["id"], source_kind="CREDIT", record_id=row["record_id"], document_no=row["document_no"], date=row["date"], currency=currency,
                amount=money(abs(Decimal(row["signed_amount"]))), allocated_amount=row["allocated_amount"], reserved_return_amount="0.00",
                available_amount=row["remaining_amount"], returnable_amount="0.00", can_declare_payment_return=False, can_allocate=row["can_allocate"]))
    opening_amount = Decimal(active["signed_amount"]) if active else ZERO
    summary = dict(opening_signed=money(opening_amount), confirmed_settlements=money(confirmed_total), fees_signed=money(fees_total), internal_paid=money(paid),
        supplier_received=money(received), paid_awaiting_receipt=money(paid-received), payment_returns_confirmed=money(returned),
        allocated=money(sum((Decimal(row["amount"]) for row in active_allocations(state)), ZERO)),
        unapplied_payment=money(sum((Decimal(row["available_amount"]) for row in sources if row["source_kind"] == "PAYMENT"), ZERO)),
        unapplied_credit=money(sum((Decimal(row["available_amount"]) for row in sources if row["source_kind"] == "CREDIT"), ZERO)),
        balance_due_signed=money(opening_amount+confirmed_total+fees_total-paid+returned), needs_reconfirmation=stale)
    return dict(state=state, cutoff=cutoff, proof=proof, latest=latest, confirmed=confirmed, obligations=obligations, allocation_sources=sources, summary=summary,
        fingerprint=digest([state["revision"], proof["fingerprint"] if proof else None, bill_heads]))


def _record_actions(row, current, external):
    state, active = current["state"], bool(current["cutoff"])
    if row["kind"] in {"OPENING", "FEE"}:
        proposal = row["proposal"]
        if external: return ["REVIEW_" + row["kind"]] if proposal else []
        result = []
        if row["kind"] == "OPENING": result.append("PROPOSE_OPENING")
        elif active:
            result.append("REVISE_FEE")
            if row["proposal"] or row["active"] and row["active"]["status"] != "VOID": result.append("VOID_FEE")
        if proposal and proposal["status"] == "SUPPLIER_CONFIRMED": result.append("CONFIRM_" + row["kind"])
        return result
    if row["status"] == "VOID": return []
    if external:
        result = ["RECEIVE_PAYMENT"] if row["kind"] == "PAYMENT" else []
        if row.get("void_request"): result.append("REVIEW_VOID")
        return result
    result = []
    if row["kind"] == "PAYMENT_RETURN" and not row["confirmed"] and not is_voiding(row): result.append("CONFIRM_PAYMENT_RETURN")
    if not allocated_to(state, row["id"]):
        if not (row["kind"] == "PAYMENT" and return_reserved(state, row["id"])): result.append("REQUEST_VOID")
        if (row.get("void_request") or {}).get("status") == "SUPPLIER_CONFIRMED": result.append("CONFIRM_VOID")
    return result


def records_out(current, currency, external, writable):
    state = current["state"]
    result = []
    for row in ([state["opening"]] if state["opening"] else []) + list(state["fees"].values()) + list(state["payments"].values()) + list(state["returns"].values()):
        history = [event for event in state["history"] if event["target_id"] == row["id"]]
        base = dict(id=row["id"], kind=row["kind"], currency=currency, revision=len(history), history=history,
            allowed_actions=_record_actions(row, current, external) if writable else [])
        if row["kind"] in {"OPENING", "FEE"}:
            shown = row["proposal"] or row["active"]
            base.update({key: shown.get(key) for key in ("date", "amount", "signed_amount", "direction", "category", "document_no", "reason", "related_settlement_id")})
            base.update(active=row["active"], proposal=row["proposal"], versions=row["versions"], status=shown["status"])
            if row["kind"] == "OPENING":
                base.update(needs_reconfirmation=current["summary"]["needs_reconfirmation"],
                    unknown_sources=current["proof"]["unknown_sources"] if current["proof"] else shown.get("unknown_sources", []), cutoff_date=shown["cutoff_date"])
        else:
            base.update({key: value for key, value in row.items() if key not in {"id", "kind"}})
            base.update(active=None, proposal=None)
            if is_voiding(row): base["status"] = "VOID_PENDING_INTERNAL" if row["void_request"]["status"] == "SUPPLIER_CONFIRMED" else "VOID_PENDING_SUPPLIER"
        result.append(base)
    return sorted(result, key=lambda row: (row["history"][-1]["created_at"], row["id"]), reverse=True)


def workspace(db, user, factory, supplier_id=None, currency="CNY", *, external=False, kind="ALL", status="ALL", keyword="", limit=50, offset=0):
    from app.services.carton_special_requests import allowed
    from app.services.carton_supplier_portal import supplier_permission
    supplier = authorize(db, user, factory, supplier_id, external=external)
    core._lock_receipt_factory(db, factory)
    if kind not in {"ALL", "OPENING", "FEE", "PAYMENT", "PAYMENT_RETURN"}: raise HTTPException(422, "往来凭证类型无效")
    if status not in {"ALL", "PENDING", "PENDING_SUPPLIER", "SUPPLIER_CONFIRMED", "DISPUTED", "EFFECTIVE", "VOID", "RECORDED", "RECEIVED", "DECLARED", "CONFIRMED", "VOID_PENDING_SUPPLIER", "VOID_PENDING_INTERNAL"}: raise HTTPException(422, "往来凭证状态无效")
    currency = core.normalize_currency(currency)
    writable = (all(allowed(user, factory, permission) for permission in ("read", "closing_manage", "order_adjust")) if not external else
        supplier_permission(user, "carton_supplier:approve", factory))
    current = context(db, factory, supplier.id, currency)
    state = current["state"]
    all_rows = records_out(current, currency, external, writable)
    items = all_rows
    if kind != "ALL": items = [row for row in items if row["kind"] == kind]
    if status == "PENDING": items = [row for row in items if row.get("proposal") or row["status"] in {"PENDING_SUPPLIER", "SUPPLIER_CONFIRMED", "DISPUTED", "RECORDED", "DECLARED", "VOID_PENDING_SUPPLIER", "VOID_PENDING_INTERNAL"} or row.get("needs_reconfirmation")]
    elif status != "ALL": items = [row for row in items if row["status"] == status]
    if text(keyword): items = [row for row in items if text(keyword).casefold() in " ".join(str(row.get(key) or "") for key in ("id", "document_no", "reason", "bank_reference")).casefold()]
    actions = set()
    if writable:
        actions.update(action for row in all_rows for action in row["allowed_actions"])
        if not external:
            actions.add("PROPOSE_OPENING")
            if current["cutoff"]: actions.update({"PROPOSE_FEE", "RECORD_PAYMENT"})
            if any(row["can_allocate"] for row in current["allocation_sources"]) and any(row["direction"] == "DEBIT" and row["can_allocate"] for row in current["obligations"]): actions.add("ALLOCATE")
            if active_allocations(state): actions.add("DEALLOCATE")
        elif any(row["can_declare_payment_return"] for row in current["allocation_sources"]): actions.add("DECLARE_PAYMENT_RETURN")
    issues = []
    if not current["cutoff"]: issues.append("账户尚未启用双方确认的期初，当前余额不代表已结清；请先完成切账及期初确认")
    if current["summary"]["needs_reconfirmation"]: issues.append("切账前来源或历史确认依据已变化，原期初暂计；请双方重新确认期初，期间禁止新增核销，实际付款仍可登记")
    if state["opening"] and state["opening"]["proposal"]: issues.append("期初新版本待双方核对，原生效金额暂计且该版本暂停新增核销")
    return dict(factory_id=factory, supplier_id=supplier.id, supplier_name=supplier.supplier_name, currency=currency,
        revision=state["revision"], source_fingerprint=current["fingerprint"], allowed_actions=sorted(actions),
        opening=next((row for row in all_rows if row["kind"] == "OPENING"), None), records=dict(items=items[offset:offset+limit], total=len(items), limit=limit, offset=offset),
        obligations=current["obligations"], allocation_sources=current["allocation_sources"], allocations=state["allocations"], summary=current["summary"], issues=issues)


def detail(db, user, factory, identifier, supplier_id=None, currency="CNY", *, external=False):
    supplier = authorize(db, user, factory, supplier_id, external=external)
    core._lock_receipt_factory(db, factory)
    currency = core.normalize_currency(currency)
    current = context(db, factory, supplier.id, currency)
    from app.services.carton_special_requests import allowed
    from app.services.carton_supplier_portal import supplier_permission
    writable = supplier_permission(user, "carton_supplier:approve", factory) if external else all(allowed(user, factory, key) for key in ("read", "closing_manage", "order_adjust"))
    row = next((row for row in records_out(current, currency, external, writable) if row["id"] == identifier), None)
    if not row: raise HTTPException(404, "未找到本账户往来凭证")
    return dict(row, account_revision=current["state"]["revision"], source_fingerprint=current["fingerprint"])


def _positive(payload):
    if payload.amount is None or payload.amount <= 0: raise HTTPException(422, "请填写大于零的实际金额")
    return money(payload.amount)


def _dated(current, value, label):
    result = day(value, label)
    if not current["cutoff"] or result < current["cutoff"]: raise HTTPException(409, "此日期早于已启用切账日，请在期初依据中核对；不能重复登记切账前资金或费用")
    return result


def _proposal_current(db, factory, supplier, currency, row):
    proposal = row and row["proposal"]
    if not proposal: raise HTTPException(409, "当前没有待核对的新版本")
    if row["kind"] == "OPENING":
        proof = baseline(db, factory, supplier, currency, proposal["cutoff_date"], proposal["baseline_periods"])
        if proof["fingerprint"] != proposal["baseline_fingerprint"]: raise HTTPException(409, "期初提议依据已变化，请内部重新提议后再由供应商确认")
    return proposal


def _fee_document(state, document, identifier=""):
    for row in state["fees"].values():
        if row["id"] == identifier: continue
        if any(version and version["status"] != "VOID" and identity(version["document_no"]) == identity(document) for version in (row["active"], row["proposal"])):
            raise HTTPException(409, "此账户已有相同费用凭证号，跨费用类别也不能换提交标识重复登记；请打开原凭证更正")


def _bank_keys(*values):
    return {identity(value) for value in values if identity(value)}


def ensure_inflow_unused(db, factory, supplier, currency, references, *, exclude_payment_return=""):
    """Shared by both cash workflows; pending claims also reserve bank identity."""
    keys = _bank_keys(*references)
    if not keys: return
    current = fold(events(db, factory, supplier, currency))
    for row in current["returns"].values():
        if row["id"] != exclude_payment_return and row["status"] != "VOID" and keys & _bank_keys(row["document_no"], row["bank_reference"], row.get("confirmation_reference")):
            raise HTTPException(409, "此银行入款凭证已用于预付款退回，不能重复登记资金；请核对原回执")


def _material_inflow_unused(db, factory, supplier, currency, references):
    from app.services import carton_return_collaboration as returns
    grouped = defaultdict(list)
    for event in returns.events(db, factory): grouped[event.entity_id].append(event)
    keys = _bank_keys(*references)
    for records in grouped.values():
        state = returns.ledger(records)
        if state["supplier_id"] != supplier: continue
        for row in state["refunds"]:
            if row["kind"] == "CASH" and row["status"] in {"PROPOSED", "CONFIRMED"} and core.normalize_currency(row["currency"]) == currency:
                if keys & _bank_keys(row["document_no"], row.get("confirmation_reference")):
                    raise HTTPException(409, "此银行入款凭证已用于材料退货现金退款，不能再记为预付款退回；两条资金链必须分清")


def reopen_guard(db, row):
    """Called inside the common IAM/factory transaction before bill supersession."""
    state = fold(events(db, row.factory_id, row.supplier_id, row.currency))
    require_unallocated(state, "SETTLEMENT:" + row.id)


def _bill_current(db, current, obligation, factory, supplier, currency):
    if obligation["kind"] != "SETTLEMENT": return
    bill = db.get(CartonSupplierSettlement, obligation["record_id"])
    evidence = settlement.workspace(db, factory, supplier, bill.period, currency)
    evidence = settlement.comparison_context(evidence, json.loads(bill.statement_json).get("origin", "MANUAL"))
    if evidence["source_fingerprint"] != bill.source_fingerprint: raise HTTPException(409, "月结实际来源已变化，不能沿旧确认版本新增核销，请先重核")


def act(db, user, payload, *, external=False):
    from app.services.carton_special_requests import locked_actor
    user = locked_actor(db, user, payload.factory_id)
    supplier = authorize(db, user, payload.factory_id, payload.supplier_id, external=external, write=True)
    factory, currency = payload.factory_id, core.normalize_currency(payload.currency)
    name = payload.action
    if name not in (EXTERNAL if external else INTERNAL): raise HTTPException(403, "当前身份不能执行此往来动作")
    request = payload.model_dump(mode="json")
    request["currency"] = currency; request["supplier_id"] = supplier.id
    if payload.amount is not None: request["amount"] = money(payload.amount)
    for target in request["targets"]: target["amount"] = money(target["amount"])
    request_hash = digest(request)
    event_id = "CAE-AP-" + digest([factory, supplier.id, currency, user.id, payload.request_id])
    previous = db.scalar(select(CartonAuditEvent).where(CartonAuditEvent.id == event_id))
    if previous:
        record = json.loads(previous.detail_json)
        if record["fingerprint"] != request_hash: raise HTTPException(409, "此提交标识已用于其他往来内容，请按原请求重试")
        result = workspace(db, user, factory, supplier.id, currency, external=external)
        return dict(result, changed_record_id=record["data"].get("record_id"), replayed=True)
    current = context(db, factory, supplier.id, currency); state = current["state"]
    if payload.expected_revision != state["revision"] or payload.source_fingerprint != current["fingerprint"]: raise HTTPException(409, "往来账户、期初依据或月结版本已变化，请刷新核对")
    reason = text(payload.reason)
    if len(reason) < 4: raise HTTPException(422, "请填写至少四字的凭据或办理原因")
    if not current["cutoff"] and name not in {"PROPOSE_OPENING", "REVIEW_OPENING", "CONFIRM_OPENING"}: raise HTTPException(409, "请先完成双方期初确认并启用固定切账日，再登记付款及费用")
    data = dict(reason=reason)
    opening, fee = state["opening"], state["fees"].get(payload.target_id)
    payment = state["payments"].get(payload.target_id)
    returned = state["returns"].get(payload.target_id)
    if name == "PROPOSE_OPENING":
        cutoff = day(payload.cutoff_date, "月首切账日期")
        if cutoff[-2:] != "01": raise HTTPException(422, "切账日必须是月首，避免同一月账单与期初重复")
        if opening and opening["active"]:
            if cutoff != opening["active"]["cutoff_date"]: raise HTTPException(409, "已启用切账日期永久固定，不能移动后覆盖既有资金及账单")
            require_unallocated(state, "OPENING:" + opening["active"]["confirmation_id"])
        if payload.direction not in {"PAYABLE", "CREDIT"} or payload.amount is None: raise HTTPException(422, "请填写期初方向与金额，明确零余额也须双方确认")
        proof = baseline(db, factory, supplier.id, currency, cutoff)
        if proof["unknown_sources"] and not payload.acknowledge_unknown_sources: raise HTTPException(409, "存在未知实际日期历史来源，请先核实日期或明确确认外部期初证据已覆盖这些未知来源")
        data.update(record_id=opening["id"] if opening else "APO-" + uuid4().hex, date=cutoff, cutoff_date=cutoff, direction=payload.direction,
            amount=money(payload.amount), signed_amount=money(payload.amount if payload.direction == "PAYABLE" else -payload.amount),
            document_no=required(payload.document_no, "双方期初凭证号"), baseline_fingerprint=proof["fingerprint"], baseline_periods=proof["periods"],
            unknown_sources=proof["unknown_sources"], acknowledge_unknown_sources=payload.acknowledge_unknown_sources)
    elif name in {"REVIEW_OPENING", "CONFIRM_OPENING", "REVIEW_FEE", "CONFIRM_FEE"}:
        row = opening if name.endswith("OPENING") else fee
        if not row or row["id"] != payload.target_id: raise HTTPException(404, "未找到本账户对应凭证")
        proposal = _proposal_current(db, factory, supplier.id, currency, row)
        data["record_id"] = row["id"]
        if name.startswith("REVIEW"):
            if payload.decision is None: raise HTTPException(422, "请明确同意或提出异议")
            data["decision"] = payload.decision
        else:
            if proposal["status"] != "SUPPLIER_CONFIRMED": raise HTTPException(409, "须先由供应商同意当前提议版本，再完成内部确认")
            if row["active"]: require_unallocated(state, row["kind"] + ":" + row["active"]["confirmation_id"])
    elif name in {"PROPOSE_FEE", "REVISE_FEE", "VOID_FEE"}:
        if name != "PROPOSE_FEE" and not fee: raise HTTPException(404, "未找到本账户独立费用")
        if fee and fee["active"]: require_unallocated(state, "FEE:" + fee["active"]["confirmation_id"])
        if name == "VOID_FEE":
            previous_fee = fee["proposal"] or fee["active"]
            if previous_fee["status"] == "VOID": raise HTTPException(409, "此费用已完成作废")
            data.update({key: previous_fee[key] for key in ("date", "direction", "category", "document_no", "related_settlement_id")})
            data.update(amount="0.00", signed_amount="0.00", voids=True)
        else:
            amount = _positive(payload)
            if payload.direction not in {"ADD_PAYABLE", "DEDUCT_PAYABLE"} or not payload.category: raise HTTPException(422, "请明确费用方向及类别")
            document = required(payload.document_no, "独立费用凭证号")
            _fee_document(state, document, fee["id"] if fee else "")
            if payload.related_settlement_id:
                bill = db.get(CartonSupplierSettlement, payload.related_settlement_id)
                if not bill or (bill.factory_id, bill.supplier_id, bill.currency) != (factory, supplier.id, currency): raise HTTPException(404, "关联货款月结不属于此账户")
            data.update(date=_dated(current, payload.fee_date, "费用凭证日期"), amount=amount, direction=payload.direction, category=payload.category,
                signed_amount=money(Decimal(amount) if payload.direction == "ADD_PAYABLE" else -Decimal(amount)), document_no=document, related_settlement_id=payload.related_settlement_id)
        data["record_id"] = fee["id"] if fee else "APF-" + uuid4().hex
    elif name == "RECORD_PAYMENT":
        document, reference = required(payload.document_no, "付款凭证号"), required(payload.bank_reference, "实际银行付款凭证")
        keys = _bank_keys(document, reference)
        if any(row["status"] != "VOID" and keys & _bank_keys(row["document_no"], row["bank_reference"]) for row in state["payments"].values()): raise HTTPException(409, "此账户已有相同付款凭证，请核对原记录，不能重复扣账")
        data.update(record_id="APP-" + uuid4().hex, amount=_positive(payload), date=_dated(current, payload.payment_date, "实际付款日期"), document_no=document, bank_reference=reference)
    elif name == "RECEIVE_PAYMENT":
        if not payment or payment["status"] == "VOID" or is_voiding(payment): raise HTTPException(409, "原付款已变更或正在更正作废")
        if not payload.decision: raise HTTPException(422, "请明确实际收款确认或异议")
        if allocated_to(state, payment["id"]) and payload.decision != "CONFIRMED": raise HTTPException(409, "此付款已核销，须先解除分配再更正收款回执")
        data.update(record_id=payment["id"], decision=payload.decision)
    elif name == "DECLARE_PAYMENT_RETURN":
        parent = state["payments"].get(payload.parent_payment_id)
        if not parent or parent["status"] == "VOID" or is_voiding(parent): raise HTTPException(409, "原付款不可退回，请核实当前付款证据")
        amount = _positive(payload)
        if Decimal(amount) > Decimal(parent["amount"])-allocated_to(state, parent["id"])-return_reserved(state, parent["id"]): raise HTTPException(409, "预付款退回超过未分配余款；待核实退回已预留额度，请先解除核销或核对原回执")
        document, reference = required(payload.document_no, "预付款退回凭证号"), required(payload.bank_reference, "实际银行退回凭证")
        ensure_inflow_unused(db, factory, supplier.id, currency, [document, reference]); _material_inflow_unused(db, factory, supplier.id, currency, [document, reference])
        return_date = _dated(current, payload.return_date, "实际预付款退回日期")
        if return_date < parent["date"]: raise HTTPException(422, "实际预付款退回日期不能早于原付款日期")
        data.update(record_id="APR-" + uuid4().hex, parent_payment_id=parent["id"], parent_payment_document_no=parent["document_no"], amount=amount, date=return_date, document_no=document, bank_reference=reference)
    elif name == "CONFIRM_PAYMENT_RETURN":
        if not returned or returned["status"] != "DECLARED" or is_voiding(returned): raise HTTPException(409, "预付款退回已变化，请核对当前回执")
        parent = state["payments"][returned["parent_payment_id"]]
        if parent["status"] == "VOID" or is_voiding(parent) or return_reserved(state, parent["id"])+allocated_to(state, parent["id"]) > Decimal(parent["amount"]): raise HTTPException(409, "原付款可退额度已变化，不能超额确认退回")
        reference = required(payload.confirmation_reference, "内部银行入款核对凭证")
        ensure_inflow_unused(db, factory, supplier.id, currency, [reference], exclude_payment_return=returned["id"])
        _material_inflow_unused(db, factory, supplier.id, currency, [reference, returned["document_no"], returned["bank_reference"]])
        data.update(record_id=returned["id"], confirmation_reference=reference)
    elif name in {"REQUEST_VOID", "REVIEW_VOID", "CONFIRM_VOID"}:
        row = payment or returned
        if not row or row["status"] == "VOID": raise HTTPException(409, "原资金凭证已不存在或已完成更正作废")
        require_unallocated(state, row["id"])
        if payment and return_reserved(state, payment["id"]): raise HTTPException(409, "原付款有关联预付款退回证据，不能单独作废隐藏资金来源")
        data["record_id"] = row["id"]
        if name == "REQUEST_VOID": data["correction_reference"] = required(payload.correction_reference, "错误登记更正凭证（不能以作废代替真实退汇）")
        else:
            if not row.get("void_request"): raise HTTPException(409, "请先内部说明错误登记依据并提议作废")
            if name == "REVIEW_VOID":
                if not payload.decision: raise HTTPException(422, "请明确同意更正或提出异议")
                data["decision"] = payload.decision
            else:
                if row["void_request"]["status"] != "SUPPLIER_CONFIRMED": raise HTTPException(409, "供应商尚未同意当前错误登记更正版本")
                data["correction_reference"] = required(payload.correction_reference, "内部错误登记最终核对凭证")
    elif name == "ALLOCATE":
        if not payload.targets or len({row.target_id for row in payload.targets}) != len(payload.targets): raise HTTPException(422, "请选择不重复的核销目标及金额")
        source = next((row for row in current["allocation_sources"] if row["id"] == payload.source_id and row["source_kind"] == payload.source_kind), None)
        if not source or not source["can_allocate"]: raise HTTPException(409, "资金或贷方版本当前不可核销，请核对收款回执、期初及版本状态")
        total = sum((row.amount for row in payload.targets), ZERO)
        if total > Decimal(source["available_amount"]): raise HTTPException(409, "本次核销总额超过来源可用金额")
        if source["source_kind"] == "CREDIT": _bill_current(db, current, next(row for row in current["obligations"] if row["id"] == source["id"]), factory, supplier.id, currency)
        allocations = []
        for target in payload.targets:
            obligation = next((row for row in current["obligations"] if row["id"] == target.target_id and row["kind"] == target.target_kind), None)
            if not obligation or obligation["direction"] != "DEBIT" or not obligation["can_allocate"] or target.amount > Decimal(obligation["remaining_amount"]): raise HTTPException(409, "目标确认版本不可核销或超过该版本未结余量")
            _bill_current(db, current, obligation, factory, supplier.id, currency)
            allocations.append(dict(id="APA-" + uuid4().hex, source_kind=source["source_kind"], source_id=source["id"], target_kind=target.target_kind,
                target_id=target.target_id, amount=money(target.amount), source_document_no=source["document_no"], target_document_no=obligation["document_no"], target_version=obligation["version"],
                source_date=source["date"], target_date=obligation["date"], target_period=obligation.get("period")))
        data["allocations"] = allocations
    elif name == "DEALLOCATE":
        identifiers = set(payload.allocation_ids)
        if not identifiers or len(identifiers) != len(payload.allocation_ids) or not identifiers <= {row["id"] for row in active_allocations(state)}: raise HTTPException(409, "核销分配已变更或不属于本账户，请刷新核对")
        data["allocation_ids"] = sorted(identifiers)
    event = core._audit(db, user, factory, EVENT, ENTITY, account_id(factory, supplier.id, currency),
        dict(action=name, data=data, revision=state["revision"]+1, fingerprint=request_hash, request_id=payload.request_id))
    event.id = event_id
    db.flush()
    result = workspace(db, user, factory, supplier.id, currency, external=external)
    db.commit()
    return dict(result, changed_record_id=data.get("record_id"), replayed=False)


def export_csv(db, user, factory, supplier_id=None, currency="CNY", *, external=False):
    value = workspace(db, user, factory, supplier_id, currency, external=external, limit=1000000)
    output = io.StringIO(); writer = csv.writer(output)
    def safe(value):
        value = str(value or "")
        return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")) else value
    writer.writerow(["供应商往来（独立费用不在原货款月结内；核销只分配不二次抵账）", safe(value["supplier_name"]), safe(value["currency"])])
    writer.writerow(["已确认期初", "切账后货款净额（含材料退款正项）", "独立费用净额", "本厂实际付款", "预付款退回", "往来余额"])
    writer.writerow([value["summary"][key] for key in ("opening_signed", "confirmed_settlements", "fees_signed", "internal_paid", "payment_returns_confirmed", "balance_due_signed")])
    writer.writerow(["状态提示", safe("；".join(value["issues"]))])
    writer.writerow(["记录ID", "类型", "状态", "日期", "凭证号", "金额", "有向金额", "收款回执", "原付款ID", "依据", "生效版本", "生效有向额", "提议版本", "提议有向额", "实际银行凭证", "内部入款核对凭证"])
    for row in value["records"]["items"]:
        writer.writerow([safe(row.get(key)) if key not in {"amount", "signed_amount"} else row.get(key, "") for key in ("id", "kind", "status", "date", "document_no", "amount", "signed_amount", "receipt_status", "parent_payment_id", "reason")] +
            [(row.get("active") or {}).get("version", ""), (row.get("active") or {}).get("signed_amount", ""), (row.get("proposal") or {}).get("version", ""), (row.get("proposal") or {}).get("signed_amount", ""), safe(row.get("bank_reference")), safe(row.get("confirmation_reference"))])
    writer.writerow(["确认义务ID", "类型", "原凭证ID", "单号", "确认版本", "账期", "日期", "有向金额", "已核销", "可分配余款", "状态", "可新增核销"])
    for row in value["obligations"]: writer.writerow([row.get(key, "") if key in {"version", "signed_amount", "allocated_amount", "remaining_amount", "can_allocate"} else safe(row.get(key)) for key in
        ("id", "kind", "record_id", "document_no", "version", "period", "date", "signed_amount", "allocated_amount", "remaining_amount", "status", "can_allocate")])
    writer.writerow(["核销ID", "状态", "来源ID", "来源凭证", "来源日期", "目标ID", "目标凭证", "目标版本", "目标账期", "目标日期", "分配金额", "办理依据"])
    for row in value["allocations"]: writer.writerow([row.get(key, "") if key in {"target_version", "amount"} else safe(row.get(key)) for key in ("id", "status", "source_id", "source_document_no", "source_date", "target_id", "target_document_no", "target_version", "target_period", "target_date", "amount", "reason")])
    return "\ufeff" + output.getvalue()
