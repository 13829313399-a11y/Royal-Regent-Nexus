"""Supplier return evidence, independent of immutable stock and bank chronology.

Only new, explicitly enrolled Dongkang sources acquire this workflow. Financial
sources contain approved immutable facts, never the changing workspace revision.
"""
import hashlib
import json
from decimal import Decimal, DecimalException
from pydantic import ValidationError
from fastapi import HTTPException
from sqlalchemy import select, or_, and_
from app.models.carton_procurement import CartonAuditEvent, CartonInventoryMovement, CartonSupplier
from app.services import carton_procurement as core, carton_return_dates as dates

ENTITY = "carton_return_collaboration"
EVENT = "RETURN_COLLABORATION_ACTION"
OPEN = "RETURN_COLLABORATION_OPENED"
ZERO = Decimal(0)
SUPPLIER_ACTIONS = {"RECEIVE", "DISPUTE", "PROPOSE_CREDIT", "DECLARE_REFUND", "RECONFIRM_DATE", "VOID"}
INTERNAL_ACTIONS = {"ENROLL", "CONFIRM_CREDIT", "CONFIRM_REFUND", "CONFIRM_DATE", "VOID"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def events(db, factory, identifier=None):
    query = select(CartonAuditEvent).where(CartonAuditEvent.factory_id == factory,
        CartonAuditEvent.entity_type == ENTITY, CartonAuditEvent.event_type.in_([EVENT, OPEN]))
    if identifier: query = query.where(CartonAuditEvent.entity_id == identifier)
    return list(db.scalars(query.order_by(CartonAuditEvent.sequence)))


def ledger(records):
    result = dict(enabled=False, revision=0, supplier_id=None, receipts=[], credits=[], refunds=[], history=[], supplier_date=None, internal_date=None)
    for event in records:
        detail = json.loads(event.detail_json)
        action = "OPEN" if event.event_type == OPEN else detail["action"]
        data = dict(detail.get("data") or {})
        result["revision"] = detail["revision"]
        info = dict(data, id=event.id, actor_name=event.actor_name, created_at=event.created_at)
        result["history"].append(dict(id=event.id, action=action, reason=data.get("reason", ""),
            actor_name=event.actor_name, created_at=event.created_at, target_event_id=data.get("target_event_id", "")))
        if action in {"OPEN", "ENROLL"}:
            result.update(enabled=True, supplier_id=data["supplier_id"])
        elif action in {"RECEIVE", "DISPUTE"}:
            result["receipts"].append(dict(info, decision=action, status="ACTIVE"))
        elif action == "PROPOSE_CREDIT":
            for old in result["credits"]:
                if old["status"] == "PROPOSED": old["status"] = "SUPERSEDED"
            result["credits"].append(dict(info, status="PROPOSED"))
        elif action == "CONFIRM_CREDIT":
            for item in result["credits"]:
                if item["status"] == "CONFIRMED": item["status"] = "SUPERSEDED"
                if item["id"] == data["target_event_id"]:
                    item.update(status="CONFIRMED", confirmation_id=event.id, confirmed_by=event.actor_name,
                        confirmed_at=event.created_at, confirmed_date_fingerprint=data["date_fingerprint"])
        elif action == "DECLARE_REFUND":
            result["refunds"].append(dict(info, status="PROPOSED"))
        elif action == "CONFIRM_REFUND":
            for item in result["refunds"]:
                if item["id"] == data["target_event_id"]:
                    item.update(status="CONFIRMED", confirmation_id=event.id, confirmed_by=event.actor_name,
                        confirmed_at=event.created_at, confirmation_reference=data["confirmation_reference"])
        elif action == "VOID":
            for name in ("receipts", "credits", "refunds"):
                for item in result[name]:
                    if item["id"] == data["target_event_id"]:
                        item.update(status="VOID", voided_by=event.actor_name, voided_at=event.created_at, void_reason=data["reason"])
        elif action == "RECONFIRM_DATE":
            result["supplier_date"] = dict(info, fingerprint=data["date_fingerprint"])
        elif action == "CONFIRM_DATE":
            result["internal_date"] = dict(info, fingerprint=data["date_fingerprint"])
    return result


def approved_credit(state):
    return next((row for row in reversed(state["credits"]) if row["status"] == "CONFIRMED"), None)


def amounts(state):
    return {kind: sum((Decimal(row["amount"]) for row in state["refunds"]
        if row["kind"] == kind and row["status"] == "CONFIRMED"), ZERO) for kind in ("CASH", "OFFSET")}


def quantities(state):
    return {kind: sum((Decimal(row["quantity"]) for row in state["receipts"]
        if row["decision"] == kind and row["status"] == "ACTIVE"), ZERO) for kind in ("RECEIVE", "DISPUTE")}


def date_review(state, current):
    active = [row for row in state["receipts"] if row["status"] == "ACTIVE"]
    supplier_ok = not any(row["date_fingerprint"] != current["fingerprint"] for row in active) or bool(
        state["supplier_date"] and state["supplier_date"]["fingerprint"] == current["fingerprint"])
    credit = approved_credit(state)
    internal_ok = not credit or credit["confirmed_date_fingerprint"] == current["fingerprint"] or bool(
        state["internal_date"] and state["internal_date"]["fingerprint"] == current["fingerprint"]
        and state["internal_date"].get("credit_event_id") == credit["confirmation_id"])
    return supplier_ok, internal_ok


def _date_pending_periods(state, current, history):
    """Keep every unresolved date month visible until both parties recheck it."""
    anchors = []
    if state["supplier_date"]:
        anchors.append(state["supplier_date"]["fingerprint"])
    else:
        anchors.extend(row["date_fingerprint"] for row in state["receipts"] if row["status"] == "ACTIVE")
    credit = approved_credit(state)
    if credit:
        confirmed = state["internal_date"]
        anchors.append(confirmed["fingerprint"] if confirmed and confirmed.get("credit_event_id") == credit["confirmation_id"]
            else credit["confirmed_date_fingerprint"])
    fingerprints = [history[index + 1].get("before_fingerprint") if index + 1 < len(history)
        else current["fingerprint"] for index in range(len(history))]
    unresolved = [value for value in anchors if value != current["fingerprint"]]
    # A legacy posting-date acknowledgement predates the first actual-date
    # record. Unknown anchors retain the complete chain rather than lose a month.
    start = min((fingerprints.index(value) if value in fingerprints else 0 for value in unresolved), default=len(history))
    affected = {(current["return_date"] or current["posting_date"])[:7]}
    unknown = any(value not in fingerprints for value in unresolved)
    for index, row in enumerate(history[start:], start):
        for field in (("before_date", "return_date") if index > start or unknown else ("return_date",)):
            if row.get(field): affected.add(row[field][:7])
    if unresolved and unknown:
        affected.add(current["posting_date"][:7])
    return affected


def _source(db, factory, identifier):
    movement = db.get(CartonInventoryMovement, identifier)
    if not movement or movement.factory_id != factory or not dates.is_return(movement) or movement.quantity >= 0:
        raise HTTPException(404, "未找到此厂真实退货纸品")
    from app.services.carton_supplier_settlement import return_supplier
    supplier = return_supplier(db, movement)
    active = not bool(db.scalar(select(CartonInventoryMovement.id).where(
        CartonInventoryMovement.factory_id == factory, CartonInventoryMovement.reversal_of_movement_id == movement.id)))
    return movement, supplier, active


def _financial(user, factory):
    from app.services.carton_special_requests import allowed
    return all(allowed(user, factory, permission) for permission in ("closing_manage", "order_adjust"))


def authorize(db, user, factory, movement, supplier, *, external=False, write=False):
    from app.services import carton_supplier_portal as portal, carton_special_requests as special
    core.require_carton_factory(factory)
    if external:
        if not portal.supplier_permission(user, "carton_supplier:read", factory) or (
            write and not portal.supplier_permission(user, "carton_supplier:approve", factory)):
            raise HTTPException(403, "没有本厂供应商退货回执权限")
        if portal.fixed_supplier(db, factory).id != supplier: raise HTTPException(404, "未找到可访问的退货纸品")
    else:
        if not special.allowed(user, factory, "read") or (write and not _financial(user, factory)):
            raise HTTPException(403, "退货财务核对须具备本厂月结及调整权限")
        if movement: special.ensure_customer_operation(db, user, factory, movement.customer_code)


def source_fingerprint(movement, supplier, active, current):
    return digest({"id": movement.id, "factory": movement.factory_id, "supplier": supplier, "active": active,
        "quantity": str(movement.quantity), "currency": core.normalize_currency(movement.currency),
        "date_fingerprint": current["fingerprint"], "identity": [getattr(movement, key) for key in
            ("contract_no", "item_no", "packaging_type", "paper_quality", "specification", "unit")]})


def _date(value, label):
    if value is None: raise HTTPException(422, f"请填写{label}")
    text = value.isoformat()
    from app.services.carton_supplier_settlement import _posting_date
    if text > _posting_date(core.now_text()): raise HTTPException(422, f"{label}不能晚于今天")
    return text


def _document(value):
    value = " ".join(value.split())
    if not value: raise HTTPException(422, "请填写真实凭证号")
    return value


def _reason(value):
    if len(value.strip()) < 4: raise HTTPException(422, "请填写至少四字核对或更正依据")
    return value.strip()


def _statement_values(**values):
    """Reject evidence which cannot be represented in the monthly statement."""
    from app.schemas.carton_supplier_settlement import StatementLine
    try:
        return StatementLine(id="return-evidence", **values)
    except (ValidationError, DecimalException, ValueError) as exc:
        raise HTTPException(422, "贷项或现金金额超过月结凭证允许的位数或精度，请核实真实凭证") from exc


def _period_open(db, movement, supplier, day=None):
    from app.services.carton_supplier_settlement import ensure_open
    current = dates.state(db, movement)
    period = (day or current["return_date"] or current["posting_date"])[:7]
    ensure_open(db, movement.factory_id, supplier, period)


def open_return(db, user, movement):
    """Called only for newly posted real returns, in the same stock transaction."""
    from app.services.carton_supplier_settlement import return_supplier
    supplier = db.get(CartonSupplier, return_supplier(db, movement))
    if not supplier or supplier.supplier_code != "HEYUAN-DONGKANG": return
    if events(db, movement.factory_id, movement.id): return
    core._audit(db, user, movement.factory_id, OPEN, ENTITY, movement.id,
        {"revision": 1, "data": {"supplier_id": supplier.id, "reason": "新退货进入供应商签收与贷项核对"}})
    db.flush()


def detail(db, user, factory, identifier, *, external=False):
    movement, supplier, active = _source(db, factory, identifier)
    authorize(db, user, factory, movement, supplier, external=external)
    state = ledger(events(db, factory, identifier)); current = dates.state(db, movement)
    if state["supplier_id"] and state["supplier_id"] != supplier: active = False
    counts, totals = quantities(state), amounts(state)
    credit = approved_credit(state)
    proposed = next((row for row in reversed(state["credits"]) if row["status"] == "PROPOSED"), None)
    shown_credit = proposed or credit
    supplier_ok, internal_ok = date_review(state, current)
    required = not (supplier_ok and internal_ok)
    quantity = -movement.quantity
    supplier_row = db.get(CartonSupplier, supplier) if supplier else None
    supported = bool(supplier_row and supplier_row.supplier_code == "HEYUAN-DONGKANG")
    actions = []
    voidable = []
    active_credits = any(row["status"] in {"PROPOSED", "CONFIRMED"} for row in state["credits"])
    pending_refunds = any(row["status"] == "PROPOSED" for row in state["refunds"])
    fully_received = counts["RECEIVE"] == quantity and not counts["DISPUTE"]
    refund_allocated = sum((Decimal(row["amount"]) for row in state["refunds"]
        if row["status"] in {"PROPOSED", "CONFIRMED"}), ZERO)
    if active and supported and current["return_date"]:
        if external:
            from app.services.carton_supplier_portal import supplier_permission
            if state["enabled"] and supplier_permission(user, "carton_supplier:approve", factory):
                if not credit and counts["RECEIVE"] + counts["DISPUTE"] < quantity:
                    actions += ["RECEIVE", "DISPUTE"]
                if fully_received and supplier_ok: actions.append("PROPOSE_CREDIT")
                if credit and supplier_ok and internal_ok and not proposed and refund_allocated < Decimal(credit["amount"]):
                    actions.append("DECLARE_REFUND")
                if not supplier_ok: actions.append("RECONFIRM_DATE")
        elif _financial(user, factory):
            if not state["enabled"]: actions = ["ENROLL"]
            else:
                if proposed and fully_received and supplier_ok and proposed["date_fingerprint"] == current["fingerprint"] and not pending_refunds:
                    actions.append("CONFIRM_CREDIT")
                if credit and supplier_ok and internal_ok and any(row["status"] == "PROPOSED"
                        and row["credit_event_id"] == credit["confirmation_id"] for row in state["refunds"]):
                    actions.append("CONFIRM_REFUND")
                if supplier_ok and not internal_ok and credit: actions.append("CONFIRM_DATE")
        can_void = state["enabled"] and (supplier_permission(user, "carton_supplier:approve", factory) if external else _financial(user, factory))
        if can_void:
            for category in ("receipts", "credits", "refunds"):
                for row in state[category]:
                    if row["status"] not in {"ACTIVE", "PROPOSED", "CONFIRMED"}: continue
                    if external and row["status"] == "CONFIRMED": continue
                    if category == "receipts" and active_credits: continue
                    if category == "credits" and any(item["status"] in {"PROPOSED", "CONFIRMED"}
                            and item["credit_event_id"] == row.get("confirmation_id") for item in state["refunds"]): continue
                    voidable.append(row["id"])
            if voidable: actions.append("VOID")
    if not external and active and current["return_date"] and _financial(user, factory): actions.append("CORRECT_DATE")
    pending = bool(state["enabled"] and active and (counts["RECEIVE"] != quantity or counts["DISPUTE"] or not credit
        or proposed or required or any(row["status"] == "PROPOSED" for row in state["refunds"])))
    status = "LEGACY" if not state["enabled"] else "SOURCE_REVERSED" if not active else "RECONFIRM_REQUIRED" if required else (
        "DISPUTED" if counts["DISPUTE"] else "RECEIVED" if counts["RECEIVE"] == quantity else "PARTIAL" if counts["RECEIVE"] else "PENDING")
    result = {key: getattr(movement, key) for key in ("document_no", "customer_name", "contract_no", "item_no", "packaging_type", "paper_quality", "specification", "unit")}
    result.update(movement_id=movement.id, factory_id=factory, quantity=str(quantity), currency=core.normalize_currency(movement.currency),
        return_date=current["return_date"] or current["posting_date"], posting_date=current["posting_date"], date_evidence=current,
        revision=state["revision"], source_fingerprint=source_fingerprint(movement, supplier, active, current),
        enabled=state["enabled"], legacy=not state["enabled"], source_active=active, pending=pending, receipt_status=status,
        received_quantity=str(counts["RECEIVE"]), disputed_quantity=str(counts["DISPUTE"]),
        remaining_quantity=str(max(ZERO, quantity - counts["RECEIVE"] - counts["DISPUTE"])),
        credit_status="RECONFIRM_REQUIRED" if required and credit else shown_credit["status"] if shown_credit else "NOT_PROPOSED",
        credit=shown_credit, cash_confirmed_amount=str(totals["CASH"]), offset_confirmed_amount=str(totals["OFFSET"]),
        deduction_amount=str(Decimal(credit["amount"]) - totals["CASH"]) if credit else None,
        receipts=state["receipts"], credits=state["credits"], refunds=state["refunds"], history=state["history"],
        date_reconfirmation_required=required, supplier_date_confirmed=supplier_ok, internal_date_confirmed=internal_ok,
        allowed_actions=sorted(actions), voidable_event_ids=voidable,
        void_confirmation_required_event_ids=[row["id"] for row in state["refunds"]
            if row["id"] in voidable and row["status"] == "CONFIRMED"], date_history=dates.history(db, movement))
    return result


def workspace(db, user, factory, *, external=False, status=None, keyword="", limit=50, offset=0):
    from app.services.carton_supplier_portal import fixed_supplier
    authorize(db, user, factory, None, fixed_supplier(db, factory).id if external else None, external=external)
    if status not in (None, "ALL", "PENDING"): raise HTTPException(422, "退货筛选状态无效")
    rows = list(db.scalars(select(CartonInventoryMovement).where(CartonInventoryMovement.factory_id == factory,
        or_(CartonInventoryMovement.source_type == "ORDER_RETURN", and_(CartonInventoryMovement.movement_type == "OUTBOUND", CartonInventoryMovement.issue_kind == "RETURN")))
        .order_by(CartonInventoryMovement.occurred_at.desc(), CartonInventoryMovement.id)))
    result = []
    for row in rows:
        try: item = detail(db, user, factory, row.id, external=external)
        except HTTPException as exc:
            if exc.status_code not in (403, 404): raise
            continue
        result.append(item)
    pending_count = sum(item["pending"] for item in result)
    legacy_count = sum(item["legacy"] for item in result)
    if status == "PENDING": result = [item for item in result if item["pending"]]
    if keyword:
        word = keyword.casefold()
        result = [item for item in result if word in " ".join(str(item[key]) for key in
            ("document_no", "customer_name", "contract_no", "item_no", "packaging_type", "paper_quality", "specification")).casefold()]
    return dict(items=result[offset:offset+limit], total=len(result), limit=limit, offset=offset,
        pending_count=pending_count, legacy_count=legacy_count)


def act(db, user, identifier, payload, *, external=False):
    from app.services.carton_special_requests import locked_actor
    user = locked_actor(db, user, payload.factory_id)
    movement, supplier, active = _source(db, payload.factory_id, identifier)
    authorize(db, user, payload.factory_id, movement, supplier, external=external, write=True)
    if payload.action not in (SUPPLIER_ACTIONS if external else INTERNAL_ACTIONS): raise HTTPException(403, "当前身份不能执行此退货回执动作")
    request_id = "CAE-RC-" + digest([payload.factory_id, user.id, payload.request_id])
    fingerprint = digest([identifier, payload.model_dump(mode="json")])
    previous = db.scalar(select(CartonAuditEvent).where(CartonAuditEvent.id == request_id))
    if previous:
        if json.loads(previous.detail_json).get("fingerprint") != fingerprint: raise HTTPException(409, "此提交标识已用于其他退货回执内容")
        return dict(detail(db, user, payload.factory_id, identifier, external=external), replayed=True)
    records = events(db, payload.factory_id, identifier); state = ledger(records)
    current = dates.state(db, movement)
    if not active or state["supplier_id"] and state["supplier_id"] != supplier: raise HTTPException(409, "原退货已冲销或来源归属已变更，不可新增回执")
    if payload.expected_revision != state["revision"] or payload.source_fingerprint != source_fingerprint(movement, supplier, active, current):
        raise HTTPException(409, "退货来源、日期或回执版本已变更，请刷新核对")
    vendor = db.get(CartonSupplier, supplier) if supplier else None
    if not vendor or vendor.supplier_code != "HEYUAN-DONGKANG": raise HTTPException(409, "仅东康供应商支持退货协同，其他供应商保留原手工贷项核对")
    if not current["return_date"]: raise HTTPException(409, "请先核实实际退货日期，再启用供应商回执")
    if not state["enabled"] and payload.action != "ENROLL": raise HTTPException(409, "历史退货尚未启用协同，请由内部明确接入；不会自动追溯新增待办")
    counts = quantities(state); credit = approved_credit(state); totals = amounts(state)
    supplier_ok, internal_ok = date_review(state, current)
    quantity = -movement.quantity
    data = {"reason": payload.reason.strip(), "date_fingerprint": current["fingerprint"], "supplier_id": supplier}
    name = payload.action
    target = next((row for category in ("receipts", "credits", "refunds") for row in state[category] if row["id"] == payload.target_event_id), None)
    if name in {"ENROLL", "RECEIVE", "DISPUTE", "PROPOSE_CREDIT", "CONFIRM_CREDIT", "RECONFIRM_DATE", "CONFIRM_DATE"}:
        _period_open(db, movement, supplier)
    if name == "ENROLL":
        if state["enabled"]: raise HTTPException(409, "该退货已启用协同，无需重复启用")
        data["reason"] = _reason(payload.reason)
    elif name in {"RECEIVE", "DISPUTE"}:
        if payload.quantity is None or payload.quantity > quantity - counts["RECEIVE"] - counts["DISPUTE"]:
            raise HTTPException(422, "回执数量超过尚未签收或提出异议的真实退货余量")
        if credit: raise HTTPException(409, "已有已确认贷项，修改签收须先处理对应贷项证据")
        if name == "DISPUTE": data["reason"] = _reason(payload.reason)
        data.update(quantity=str(payload.quantity), receipt_date=_date(payload.receipt_date, "供应商回执日期"), document_no=_document(payload.document_no))
    elif name == "PROPOSE_CREDIT":
        if counts["RECEIVE"] != quantity or counts["DISPUTE"] or not supplier_ok:
            raise HTTPException(409, "尚有未签收、异议或日期版本待确认，不能核定整笔退货贷项")
        if payload.unit_price is None: raise HTTPException(422, "请填写独立贷项单价，不能使用库存成本代替")
        from app.services.carton_supplier_settlement import money
        try:
            amount = money(quantity * payload.unit_price)
        except DecimalException as exc:
            raise HTTPException(422, "贷项总金额超过月结凭证允许的位数或精度，请核实真实凭证") from exc
        _statement_values(quantity=quantity, unit_price=payload.unit_price, amount=amount)
        if totals["CASH"] + totals["OFFSET"] > amount:
            raise HTTPException(409, "已确认现金或抵扣分配超过新贷项；不能覆盖已有资金事实，请核实原凭证")
        data.update(unit_price=str(payload.unit_price), amount=str(amount), document_no=_document(payload.document_no),
            credit_date=_date(payload.credit_date, "贷项凭证日期"), reason=_reason(payload.reason))
    elif name == "CONFIRM_CREDIT":
        if not target or target not in state["credits"] or target["status"] != "PROPOSED": raise HTTPException(409, "贷项提议已变化")
        if counts["RECEIVE"] != quantity or counts["DISPUTE"] or not supplier_ok or target["date_fingerprint"] != current["fingerprint"]:
            raise HTTPException(409, "贷项所依据的签收或日期版本已变化，请供应商重新提议贷项")
        if any(row["status"] == "PROPOSED" for row in state["refunds"]): raise HTTPException(409, "仍有退款声明待核对，请先处理再更正贷项")
        if totals["CASH"] + totals["OFFSET"] > Decimal(target["amount"]): raise HTTPException(409, "新贷项不足以覆盖已有现金及抵扣分配")
        data.update(target_event_id=target["id"], reason=_reason(payload.reason))
    elif name == "DECLARE_REFUND":
        if not credit or not supplier_ok or not internal_ok: raise HTTPException(409, "须先确认当前日期版本的退货贷项，再登记退款或抵扣回执")
        if any(row["status"] == "PROPOSED" for row in state["credits"]): raise HTTPException(409, "贷项更正尚未完成")
        allocated = sum((Decimal(row["amount"]) for row in state["refunds"] if row["status"] in {"PROPOSED", "CONFIRMED"}), ZERO)
        if payload.amount is None or not payload.kind or payload.amount > Decimal(credit["amount"]) - allocated:
            raise HTTPException(422, "现金与月结抵扣分配合计不可超过已认可贷项，不能重复抵账")
        day = _date(payload.refund_date, "实际退款或抵扣日期")
        document = _document(payload.document_no)
        if payload.kind == "CASH":
            from app.services.carton_supplier_payables import ensure_inflow_unused
            ensure_inflow_unused(db, payload.factory_id, supplier, core.normalize_currency(movement.currency), [document])
            if any(row["kind"] == "CASH" and row["status"] in {"PROPOSED", "CONFIRMED"}
                    and " ".join(row["document_no"].split()) == document for row in state["refunds"]):
                raise HTTPException(409, "此退货已有相同现金退款凭证号，请核对原回执；不能换提交标识重复登记")
            _statement_values(quantity=Decimal(1), unit_price=payload.amount, amount=payload.amount)
            _period_open(db, movement, supplier, day)
        data.update(kind=payload.kind, amount=str(payload.amount), refund_date=day, document_no=document,
            credit_event_id=credit["confirmation_id"], currency=core.normalize_currency(movement.currency))
    elif name == "CONFIRM_REFUND":
        if not target or target not in state["refunds"] or target["status"] != "PROPOSED": raise HTTPException(409, "退款回执已变化")
        if not credit or target["credit_event_id"] != credit["confirmation_id"] or not supplier_ok or not internal_ok:
            raise HTTPException(409, "退款所依据的贷项或日期版本已变化，请先完成重核")
        reference = _document(payload.confirmation_reference)
        if target["kind"] == "CASH":
            from app.services.carton_supplier_payables import ensure_inflow_unused
            ensure_inflow_unused(db, payload.factory_id, supplier, core.normalize_currency(movement.currency), [reference, target["document_no"]])
            if any(row["kind"] == "CASH" and row["status"] == "CONFIRMED"
                    and " ".join(row["confirmation_reference"].split()) == reference for row in state["refunds"]):
                raise HTTPException(409, "此退货已有相同银行核对凭证，请核实是否重复现金回款")
            _period_open(db, movement, supplier, target["refund_date"])
        data.update(target_event_id=target["id"], confirmation_reference=reference, reason=_reason(payload.reason))
    elif name == "VOID":
        if not target or target["status"] not in {"ACTIVE", "PROPOSED", "CONFIRMED"}: raise HTTPException(409, "原回执已撤销或被新版本替代")
        if external and target["status"] == "CONFIRMED": raise HTTPException(403, "已核对资金或贷项须由内部凭据更正，供应商不能自行撤销")
        if target in state["receipts"] and any(row["status"] in {"PROPOSED", "CONFIRMED"} for row in state["credits"]):
            raise HTTPException(409, "签收已关联贷项，请先有依据处理对应贷项及退款证据")
        if target in state["credits"] and any(row["status"] in {"PROPOSED", "CONFIRMED"}
                and row["credit_event_id"] == target.get("confirmation_id") for row in state["refunds"]):
            raise HTTPException(409, "贷项已关联现金或抵扣事实，请先核实对应回执，不能清除真实资金")
        if target in state["refunds"]:
            if target["kind"] == "CASH": _period_open(db, movement, supplier, target["refund_date"])
            if target["status"] == "CONFIRMED": data["confirmation_reference"] = _document(payload.confirmation_reference)
        else: _period_open(db, movement, supplier)
        data.update(target_event_id=target["id"], reason=_reason(payload.reason))
    elif name == "RECONFIRM_DATE":
        if supplier_ok: raise HTTPException(409, "当前退货日期版本无需重复签收确认")
        data["reason"] = _reason(payload.reason)
    elif name == "CONFIRM_DATE":
        if not supplier_ok or internal_ok or not credit: raise HTTPException(409, "请先由供应商重确认新日期版本，再核对已有贷项")
        data.update(credit_event_id=credit["confirmation_id"], reason=_reason(payload.reason))
    event = core._audit(db, user, payload.factory_id, EVENT, ENTITY, identifier,
        {"action": name, "revision": state["revision"] + 1, "request_id": payload.request_id,
         "fingerprint": fingerprint, "data": data})
    event.id = request_id
    db.flush()
    result = detail(db, user, payload.factory_id, identifier, external=external)
    db.commit()
    return result


def reversal_guard(db, movement):
    if not dates.is_return(movement): return
    state = ledger(events(db, movement.factory_id, movement.id))
    if any(row["status"] in {"ACTIVE", "PROPOSED", "CONFIRMED"} for key in ("receipts", "credits", "refunds") for row in state[key]):
        raise HTTPException(409, "原退货仍有有效签收、贷项或退款证据；须先凭依据处理对应回执，不能通过库存冲销隐藏双方或真实资金事实")


def financial_sources(db, factory, supplier, period, currency, rows, issues):
    """Enrich opted-in returns and append cash in its own actual refund month.

    Later refund declarations never enter the original return's fingerprint.
    Each cash source contains only that immutable confirmed receipt's facts.
    """
    grouped = {}
    for event in events(db, factory): grouped.setdefault(event.entity_id, []).append(event)
    by_key = {row["source_key"]: row for row in rows}
    for identifier, records in grouped.items():
        state = ledger(records)
        if not state["enabled"] or state["supplier_id"] != supplier: continue
        movement, actual_supplier, active = _source(db, factory, identifier)
        if core.normalize_currency(movement.currency) != currency: continue
        current = dates.state(db, movement)
        counts, credit = quantities(state), approved_credit(state)
        supplier_ok, internal_ok = date_review(state, current)
        proposed = next((row for row in reversed(state["credits"]) if row["status"] == "PROPOSED"), None)
        row = by_key.get("RETURN:" + identifier)
        if row:
            row["return_movement_id"] = identifier
            row["return_agreement"] = {
                "receipt_event_ids": [item["id"] for item in state["receipts"] if item["status"] == "ACTIVE"],
                "credit_event_id": credit["confirmation_id"] if credit else None,
                "credit_document_no": credit["document_no"] if credit else "",
                "credit_date": credit["credit_date"] if credit else None,
                "pending_credit_id": proposed["id"] if proposed else None,
                "supplier_date_confirmation": state["supplier_date"]["id"] if state["supplier_date"] else None,
                "internal_date_confirmation": state["internal_date"]["id"] if state["internal_date"] else None,
            }
            row["unit_price"] = credit["unit_price"] if credit else None
            row["amount"] = credit["amount"] if credit else None
            if counts["RECEIVE"] != -movement.quantity or counts["DISPUTE"]:
                row["issues"].append("退货尚有未签收或异议数量，不能核定整笔贷项")
            if not credit or proposed: row["issues"].append("退货独立贷项尚未由内部核定或有待核对更正")
            if not supplier_ok or not internal_ok: row["issues"].append("退货日期新版本待供应商和内部重新确认，原签收及资金事实保留")
        if active and (not supplier_ok or not internal_ok):
            history = dates.history(db, movement)
            if period in _date_pending_periods(state, current, history):
                issues.append(f"退货 {movement.document_no} 日期版本待双方重新确认；不能沿用旧日期审批")
        for refund in state["refunds"]:
            if refund["kind"] != "CASH" or refund["status"] != "CONFIRMED" or refund["refund_date"][:7] != period: continue
            warning = [] if active and actual_supplier == supplier else ["原退货已冲销或归属异常；真实现金回款仍保留，须凭证重核"]
            rows.append({"source_key": "RETURN_REFUND:" + refund["confirmation_id"], "kind": "RETURN_REFUND",
                "return_movement_id": identifier, "receipt_id": None, "document_no": refund["document_no"],
                "acceptance_date": refund["refund_date"], "refund_date": refund["refund_date"], "date_basis": "REFUND_ACTUAL",
                **{key: getattr(movement, key) for key in ("customer_name", "contract_no", "item_no", "packaging_type", "paper_quality", "specification")},
                "unit": "笔", "quantity": "1", "unit_price": refund["amount"], "amount": refund["amount"], "currency": currency,
                "refund_evidence": {"id": refund["id"], "confirmation_id": refund["confirmation_id"],
                    "credit_event_id": refund["credit_event_id"], "confirmation_reference": refund["confirmation_reference"]},
                "issues": warning, "reason": "内部已凭证核对现金退款；作为本期正项，避免退货贷项再次抵扣"})
