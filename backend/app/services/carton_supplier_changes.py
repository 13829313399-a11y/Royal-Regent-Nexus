"""Durable supplier work derived from immutable procurement versions and audit receipts.

No GET writes, notification delivery assumptions, or inventory/price side effects.
"""
import hashlib
import json
from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select

from app.models.carton_procurement import CartonAuditEvent, CartonOrder, CartonPurchaseOrderIssue
from app.models.carton_special_requests import SpecialRequest, SpecialVersion
from app.schemas.carton_supplier_portal import BatchCommitmentSave, CancellationAcknowledge
from app.services import carton_procurement as core, carton_supplier_portal as portal


def response_state(db, factory, source_kind, source_id):
    return response_states(db, factory, source_kind, [source_id])[source_id]


def response_states(db, factory, source_kind, source_ids):
    result = {identifier: {"status": "PENDING", "reason": "", "promised_date": "", "read": False,
              "responded_at": "", "responded_by": "", "read_at": "", "history": []} for identifier in source_ids}
    if not result:
        return result
    events = db.scalars(select(CartonAuditEvent).where(CartonAuditEvent.factory_id == factory,
        CartonAuditEvent.entity_type == "carton_supplier_change", CartonAuditEvent.entity_id.in_(source_ids),
        CartonAuditEvent.event_type.in_(["SUPPLIER_CHANGE_READ", "SUPPLIER_CHANGE_RESPONSE"]))
        .order_by(CartonAuditEvent.sequence)).all()
    for event in events:
        saved = json.loads(event.detail_json)
        if saved.get("source_kind") != source_kind:
            continue
        state = result[event.entity_id]
        state["history"].append({"status": "READ" if event.event_type == "SUPPLIER_CHANGE_READ" else saved["status"],
            "reason": saved.get("reason", ""), "promised_date": saved.get("promised_date", ""),
            "actor_name": event.actor_name, "created_at": event.created_at})
        if event.event_type == "SUPPLIER_CHANGE_READ":
            state.update(read=True, read_at=event.created_at)
        else:
            state.update(status=saved["status"], reason=saved.get("reason", ""),
                promised_date=saved.get("promised_date", ""), responded_at=event.created_at,
                responded_by=event.actor_name)
    return result


def record_response(db, user, factory, source_kind, source_id, status, *, reason="", promised_date=""):
    return core._audit(db, user, factory, "SUPPLIER_CHANGE_RESPONSE", "carton_supplier_change", source_id,
        {"source_kind": source_kind, "status": status, "reason": reason, "promised_date": promised_date})


def special_confirmation(db, row):
    state = response_state(db, row.factory_id, "SPECIAL", row.current_version_id)
    state["version_id"] = row.current_version_id
    # Supplier-authored extra goods do not pretend to have an internal acceptance.
    if row.status != "CANCELLED" and (row.origin == "SUPPLIER_EXTRA" or row.kind == "SUPPLIER_GIFT"):
        state["status"] = "SUPPLIER_ORIGIN"
        return state
    if state["status"] == "PENDING" and row.quote_version_id:
        quoted = db.get(SpecialVersion, row.quote_version_id)
        latest_requirement = db.scalar(select(SpecialVersion).where(SpecialVersion.factory_id == row.factory_id,
            SpecialVersion.request_id == row.id,
            SpecialVersion.action.in_(["SEND", "ADJUSTED", "MATERIAL_CHANGED", "CANCEL"]))
            .order_by(SpecialVersion.revision.desc()).limit(1))
        if quoted and quoted.action == "QUOTE" and (not latest_requirement or quoted.revision > latest_requirement.revision):
            state.update(status="ACCEPTED", promised_date=row.promised_date,
                responded_by=quoted.actor_name, responded_at=quoted.created_at)
    return state


def _special_deleted(db, row):
    return bool(db.scalar(select(SpecialVersion.id).where(SpecialVersion.factory_id == row.factory_id,
        SpecialVersion.request_id == row.id, SpecialVersion.action == "DELETED").limit(1)))


def _source(db, user, factory, kind, identifier, *, internal=False):
    from app.services import carton_special_requests as special
    if internal:
        portal.internal_permission(user, factory, "carton_procurement:read")
        vendor = portal.fixed_supplier(db, factory)
    else:
        vendor = portal.supplier_access(db, user, factory)
    if kind == "SPECIAL":
        version = db.get(SpecialVersion, identifier)
        row = db.get(SpecialRequest, version.request_id) if version and version.factory_id == factory else None
        if (not row or row.factory_id != factory or row.supplier_id != vendor.id
                or row.status == "SUBMITTED" or not special.is_published(db, row)
                or row.current_version_id != identifier or _special_deleted(db, row)):
            raise HTTPException(409, "特殊订单版本已变化或已归档，请刷新变更待办")
        if internal:
            special.access(db, user, factory, row.id)
        return row, version
    issue = db.get(CartonPurchaseOrderIssue, identifier)
    row = db.get(CartonOrder, issue.order_id) if issue and issue.factory_id == factory else None
    if (not row or row.factory_id != factory or row.supplier_id != vendor.id or row.deleted_at
            or row.status not in portal.VISIBLE_STATES):
        raise HTTPException(404, "未找到可访问的采购版本")
    snapshot = core._purchase_order_snapshot(issue)
    if bool(snapshot.get("replenishment")) != (kind == "REPLENISHMENT"):
        raise HTTPException(409, "采购版本类型不一致")
    if kind == "REGULAR" and (not portal.latest_issue(db, row) or portal.latest_issue(db, row).id != identifier):
        raise HTTPException(409, "采购版本已更新，请刷新后核对最新版本")
    if internal:
        core.ensure_customer_operation(db, user, factory, row.customer_code)
    return row, issue


def _publication_history(db, row, current, kind):
    """Superseded publication is not evidence that either party agreed to it."""
    if kind == "SPECIAL":
        versions = list(db.scalars(select(SpecialVersion).where(SpecialVersion.factory_id == row.factory_id,
            SpecialVersion.request_id == row.id, SpecialVersion.revision <= current.revision,
            SpecialVersion.action.in_(["SEND", "ADJUSTED", "MATERIAL_CHANGED", "CANCEL", "QUOTE", "APPROVE"]))
            .order_by(SpecialVersion.revision)))
        first_send = next((version.revision for version in versions if version.action == "SEND"), None)
        versions = [version for version in versions if first_send is not None and version.revision >= first_send]
        states = response_states(db, row.factory_id, kind, [version.id for version in versions])
        result, last_quote = [], None
        for version in versions:
            frozen = json.loads(version.snapshot_json)
            state = states[version.id]
            if version.action in {"SEND", "ADJUSTED", "MATERIAL_CHANGED", "CANCEL"}:
                last_quote = None
            if version.action == "QUOTE":
                last_quote = version
            if state["status"] == "PENDING" and last_quote and version.action in {"QUOTE", "APPROVE"}:
                state.update(status="ACCEPTED", responded_by=last_quote.actor_name, responded_at=last_quote.created_at)
            result.append({"source_id": version.id, "document_no": f"{row.request_no} / 版本 {version.revision}",
                "created_at": version.created_at, "action": version.action, "status": state["status"],
                "read": state["read"], "responded_by": state["responded_by"], "responded_at": state["responded_at"],
                "response_history": state["history"],
                "planned_date": frozen.get("required_date", ""), "reason": state["reason"],
                "superseded": version.id != current.id,
                "lines": [{"id": paper["id"], "packaging_type": paper.get("packaging_type", ""),
                    "paper_quality": paper.get("paper_quality", ""), "specification": paper.get("specification", ""),
                    "unit": paper.get("unit", ""), "quantity": "0" if frozen.get("status") == "CANCELLED" else str(paper.get("quantity", "0"))}
                    for paper in frozen.get("lines", [])]})
        return result
    versions = [issue for issue in reversed(core._purchase_order_issues(db, row.id))
        if issue.issue_sequence <= current.issue_sequence
        and bool(core._purchase_order_snapshot(issue).get("replenishment")) == (kind == "REPLENISHMENT")
        and (kind != "REPLENISHMENT" or issue.id == current.id)]
    states = response_states(db, row.factory_id, kind, [version.id for version in versions])
    accepted, cancel_acks, last_at = {}, set(), {}
    identifiers = [version.id for version in versions] if kind == "REPLENISHMENT" else [row.id]
    events = db.scalars(select(CartonAuditEvent).where(CartonAuditEvent.factory_id == row.factory_id,
        CartonAuditEvent.entity_id.in_(identifiers),
        CartonAuditEvent.entity_type == ("carton_purchase_order_issue" if kind == "REPLENISHMENT" else "carton_order"),
        CartonAuditEvent.event_type.in_(["SUPPLIER_PAPER_ACCEPTED", "SUPPLIER_CANCELLATION_ACKNOWLEDGED", "SUPPLIER_REPLENISHMENT_ACCEPTED"]))
        .order_by(CartonAuditEvent.sequence))
    for event in events:
        saved = json.loads(event.detail_json)
        identifier = saved.get("issue_id")
        if event.event_type == "SUPPLIER_CANCELLATION_ACKNOWLEDGED":
            cancel_acks.add(identifier)
        elif saved.get("line_id"):
            accepted.setdefault(identifier, set()).add(saved["line_id"])
            last_at[identifier] = (event.actor_name, event.created_at)
    result = []
    for version in versions:
        frozen = core._purchase_order_snapshot(version)
        state = states[version.id]
        papers = frozen.get("lines", [])
        positive = {str(paper["id"]) for paper in papers if Decimal(str(paper.get("required_quantity_delta" if kind == "REPLENISHMENT" else "after_required_quantity", "0"))) > 0}
        if frozen.get("cancellation") and version.id in cancel_acks:
            state["status"] = "CANCEL_ACKNOWLEDGED"
        elif state["status"] == "PENDING" and positive and positive <= accepted.get(version.id, set()):
            state.update(status="ACCEPTED", responded_by=last_at[version.id][0], responded_at=last_at[version.id][1])
        elif state["status"] == "PENDING" and positive & accepted.get(version.id, set()):
            state.update(status="PARTIAL", responded_by=last_at[version.id][0], responded_at=last_at[version.id][1])
        result.append({"source_id": version.id, "document_no": version.document_no, "created_at": version.generated_at,
            "action": version.document_type, "status": state["status"], "read": state["read"],
            "responded_by": state["responded_by"], "responded_at": state["responded_at"], "reason": state["reason"],
            "response_history": state["history"],
            "planned_date": frozen.get("after_due_date", ""), "superseded": version.id != current.id,
            "lines": [{"id": paper["id"], "packaging_type": paper.get("packaging_type", ""),
                "paper_quality": paper.get("paper_quality", ""), "specification": paper.get("specification", ""),
                "unit": paper.get("unit", ""), "quantity": str(paper.get("required_quantity_delta", "0") if kind == "REPLENISHMENT" else paper.get("after_required_quantity", "0"))}
                for paper in papers]})
    return result


def _task(db, user, row, version, kind, *, internal=False):
    state = special_confirmation(db, row) if kind == "SPECIAL" else response_state(db, row.factory_id, kind, version.id)
    cancelled = row.status == "CANCELLED" and kind != "REPLENISHMENT"
    if kind == "SPECIAL":
        after = json.loads(version.snapshot_json)
        previous = db.scalar(select(SpecialVersion).where(SpecialVersion.request_id == row.id,
            SpecialVersion.factory_id == row.factory_id, SpecialVersion.revision < version.revision,
            SpecialVersion.action.in_(["SEND", "ADJUSTED", "MATERIAL_CHANGED", "CANCEL", "QUOTE", "APPROVE"]))
            .order_by(SpecialVersion.revision.desc()).limit(1))
        before = json.loads(previous.snapshot_json) if previous else {}
        old_lines = {str(item["id"]): item for item in before.get("lines", [])}
        papers = [{**item, "before_quantity": str(old_lines.get(str(item["id"]), {}).get("quantity", "0")),
            "quantity": "0" if cancelled else str(item["quantity"]),
            "before_material": {key: old_lines.get(str(item["id"]), {}).get(key, "") for key in ("packaging_type", "paper_quality", "specification", "dimension_unit")}}
            for item in after.get("lines", [])]
        current_ids = {str(item["id"]) for item in after.get("lines", [])}
        papers.extend({**item, "before_quantity": str(item["quantity"]), "quantity": "0"}
            for identifier, item in old_lines.items() if identifier not in current_ids)
        number, plan, created = row.request_no, row.required_date, version.created_at
        before_date = before.get("required_date", "")
        before_manifest, after_manifest = before.get("material_manifest", []), after.get("material_manifest", [])
        customer_date, before_customer_date = "", ""
    else:
        after = core._purchase_order_snapshot(version)
        previous = db.scalar(select(CartonPurchaseOrderIssue).where(CartonPurchaseOrderIssue.order_id == row.id,
            CartonPurchaseOrderIssue.factory_id == row.factory_id,
            CartonPurchaseOrderIssue.issue_sequence < version.issue_sequence)
            .order_by(CartonPurchaseOrderIssue.issue_sequence.desc()).limit(1))
        old_lines = {str(item["id"]): item for item in core._purchase_order_snapshot(previous).get("lines", [])}
        papers = [{**item, "order_line_id": item["id"], "before_quantity": str(item.get("before_required_quantity", "0")),
            "quantity": str(item.get("required_quantity_delta", "0") if kind == "REPLENISHMENT" else item.get("after_required_quantity", "0")),
            "before_material": {key: old_lines.get(str(item["id"]), {}).get(key, "") for key in ("packaging_type", "paper_quality", "specification", "dimension_unit")}}
            for item in after.get("lines", [])]
        number, plan, created = version.document_no, str(after.get("after_due_date", "")), version.generated_at
        before_date = str(after.get("before_due_date", ""))
        before_manifest, after_manifest = [], []
        customer_date = str(after.get("order", {}).get("customer_due_date") or "")
        before_customer_date = str(core._purchase_order_snapshot(previous).get("order", {}).get("customer_due_date") or "")
        if kind == "REGULAR":
            accepted = portal.acceptance_summary(db, row, core.get_order_lines(db, row.id))
            if cancelled:
                notice = portal.cancellation_notice(db, row, version)
                if notice and notice["acknowledged"]:
                    state["status"] = "CANCEL_ACKNOWLEDGED"
            elif accepted["status"] == "PENDING_CHANGE":
                state["status"] = "PENDING_ISSUE"
            elif state["status"] != "DISPUTED" and accepted["status"] == "ACCEPTED":
                state["status"] = "ACCEPTED"
            elif state["status"] != "DISPUTED" and accepted["status"] == "PARTIAL":
                state["status"] = "PARTIAL"
        else:
            from app.services import carton_replenishment_supplier as replacements
            source = next((item for item in replacements.sources(db, row) if item["issue_id"] == version.id), None)
            if source and state["status"] != "DISPUTED" and all(paper["accepted"] for paper in source["lines"]):
                state["status"] = "ACCEPTED"
            if source:
                papers = [{**item, "before_quantity": "0", "quantity": str(item["required_quantity"])} for item in source["lines"]]
    if kind == "REPLENISHMENT" and row.status == "CANCELLED":
        state["status"] = "CLOSED_BY_CANCELLATION"
    closed_without_acceptance = row.status == "COMPLETED" and kind != "REPLENISHMENT"
    if kind == "REPLENISHMENT" and row.status == "COMPLETED":
        closed_without_acceptance = bool(papers) and all(Decimal(str(paper.get("remaining_to_ship", "0"))) <= 0 for paper in papers)
    if closed_without_acceptance and state["status"] not in {"ACCEPTED", "CANCEL_ACKNOWLEDGED"}:
        state["status"] = "CLOSED_WITHOUT_ACCEPTANCE"
    pending = state["status"] not in {"ACCEPTED", "CANCEL_ACKNOWLEDGED", "SUPPLIER_ORIGIN", "CLOSED_WITHOUT_ACCEPTANCE", "CLOSED_BY_CANCELLATION"}
    try:
        age_days = (date.fromisoformat(core.now_text()[:10]) - date.fromisoformat(created[:10])).days
    except ValueError:
        age_days = 0
    return {"source_kind": kind, "source_id": version.id, "factory_id": row.factory_id,
        "order_id": row.id, "order_no": row.request_no if kind == "SPECIAL" else row.order_no,
        "document_no": number, "expected_revision": row.revision, "status": state["status"],
        "is_cancellation": cancelled, "read": state["read"], "read_at": state["read_at"],
        "reason": state["reason"], "responded_by": state["responded_by"], "responded_at": state["responded_at"],
        "promised_date": state["promised_date"], "planned_date": plan, "before_date": before_date,
        "customer_due_date": customer_date, "before_customer_due_date": before_customer_date,
        "change_reason": str(after.get("change_reason") or after.get("reason") or ""),
        "created_at": created, "age_days": max(0, age_days), "overdue": pending and age_days >= 1,
        "action": "CANCEL" if cancelled else version.action if kind == "SPECIAL" else version.document_type,
        "responsibility": after.get("replenishment", {}).get("responsibility", ""), "lines": papers,
        "material_changed": before_manifest != after_manifest, "pending": pending,
        "publication_history": _publication_history(db, row, version, kind),
        "can_respond": pending and state["status"] != "PENDING_ISSUE" and not internal and portal.supplier_permission(user, "carton_supplier:approve", row.factory_id)}


def workspace(db, user, factory, *, internal=False):
    if internal:
        portal.internal_permission(user, factory, "carton_procurement:read")
        vendor = portal.fixed_supplier(db, factory)
    else:
        vendor = portal.supplier_access(db, user, factory)
    items = []
    orders = db.scalars(select(CartonOrder).where(CartonOrder.factory_id == factory,
        CartonOrder.supplier_id == vendor.id, CartonOrder.deleted_at.is_(None), CartonOrder.status.in_(portal.VISIBLE_STATES))).all()
    for row in orders:
        ordinary = portal.latest_issue(db, row)
        versions = core._purchase_order_issues(db, row.id)
        for version in versions:
            replacement = bool(core._purchase_order_snapshot(version).get("replenishment"))
            if not replacement and (not ordinary or ordinary.id != version.id):
                continue
            try:
                owner, source = _source(db, user, factory, "REPLENISHMENT" if replacement else "REGULAR", version.id, internal=internal)
                items.append(_task(db, user, owner, source, "REPLENISHMENT" if replacement else "REGULAR", internal=internal))
            except HTTPException as exc:
                if exc.status_code not in {403, 404, 409}:
                    raise
    for row in db.scalars(select(SpecialRequest).where(SpecialRequest.factory_id == factory,
            SpecialRequest.supplier_id == vendor.id, SpecialRequest.status != "SUBMITTED")):
        if row.status != "CANCELLED" and (row.origin == "SUPPLIER_EXTRA" or row.kind == "SUPPLIER_GIFT"):
            continue
        try:
            owner, source = _source(db, user, factory, "SPECIAL", row.current_version_id, internal=internal)
            items.append(_task(db, user, owner, source, "SPECIAL", internal=internal))
        except HTTPException as exc:
            if exc.status_code not in {403, 404, 409}:
                raise
    from app.services import carton_print_split as prints
    for plan in prints.records(db, factory):
        if plan.get("workflow") == "ORDER" or plan["supplier_id"] != vendor.id or plan["status"] == "DRAFT":
            continue
        if internal:
            from app.services.carton_customer_assignment import ensure_customer_operation
            try:
                ensure_customer_operation(db, user, factory, plan["customer_code"])
            except HTTPException as exc:
                if exc.status_code in {403, 404}: continue
                raise
        items.append(prints.task(plan, user, internal=internal))
    items.sort(key=lambda item: (not item["pending"], not item["is_cancellation"], item["created_at"], item["source_id"]))
    return {"items": items, "pending_count": sum(item["pending"] for item in items),
        "overdue_count": sum(item["overdue"] for item in items),
        "disputed_count": sum(item["status"] == "DISPUTED" for item in items)}


def respond(db, user, payload):
    if payload.source_kind == "PRINT":
        from app.services.carton_print_split import respond as print_response
        return print_response(db, user, payload)
    from app.services import carton_special_requests as special
    user = special.locked_actor(db, user, payload.factory_id)
    row, version = _source(db, user, payload.factory_id, payload.source_kind, payload.source_id)
    if payload.action != "READ" and not portal.supplier_permission(user, "carton_supplier:approve", payload.factory_id):
        raise HTTPException(403, "此操作需要供应商接单确认权限")
    data = payload.model_dump(mode="json")
    digest = hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    replay_id = "CAE-CHANGE-" + hashlib.sha256(f"{payload.factory_id}:{user.id}:{payload.request_id}".encode()).hexdigest() if payload.request_id else ""
    saved = db.scalar(select(CartonAuditEvent).where(CartonAuditEvent.id == replay_id)) if replay_id else None
    if saved:
        evidence = json.loads(saved.detail_json)
        if evidence.get("fingerprint") != digest:
            raise HTTPException(409, "提交标识已用于其他变更回应")
        return evidence["result"]
    if row.revision != payload.expected_revision:
        raise HTTPException(409, "订单修订已变化，请刷新后重新核对")
    if payload.action != "READ" and row.status == "COMPLETED" and payload.source_kind != "REPLENISHMENT":
        raise HTTPException(409, "此订单已收料完成，仅保留历史回执，不补造供应商接单")
    cancelled = row.status == "CANCELLED" and payload.source_kind != "REPLENISHMENT"
    if payload.action == "READ":
        if not response_state(db, payload.factory_id, payload.source_kind, version.id)["read"]:
            core._audit(db, user, payload.factory_id, "SUPPLIER_CHANGE_READ", "carton_supplier_change", version.id,
                {"source_kind": payload.source_kind})
    elif payload.action == "DISPUTE":
        if not payload.reason.strip():
            raise HTTPException(422, "请填写具体异议，便于双方核实")
        record_response(db, user, payload.factory_id, payload.source_kind, version.id, "DISPUTED", reason=payload.reason)
    elif payload.action == "ACK_CANCEL":
        if not cancelled:
            raise HTTPException(409, "此版本不是当前取消通知")
        if payload.source_kind == "REGULAR":
            portal.acknowledge_cancellation(db, user, row.id, CancellationAcknowledge(factory_id=payload.factory_id,
                issue_id=version.id, expected_order_revision=row.revision), commit=False)
        record_response(db, user, payload.factory_id, payload.source_kind, version.id, "CANCEL_ACKNOWLEDGED")
    else:
        if cancelled:
            raise HTTPException(409, "已取消订单只能确认收到停止通知，不能继续接单")
        if payload.promised_date is None:
            raise HTTPException(422, "确认接单须填写承诺交期")
        promise = payload.promised_date.isoformat()
        if payload.source_kind == "SPECIAL":
            row.promised_date = promise
            # Keep the executable requirement version stable; acknowledgement is its own evidence.
        else:
            if payload.source_kind == "REPLENISHMENT":
                from app.services import carton_replenishment_supplier as replacements
                source = next((item for item in replacements.sources(db, row) if item["issue_id"] == version.id), None)
                papers = source["lines"] if source else []
            else:
                projected = portal.order_out(db, row)
                papers = projected["lines"]
            selected = [{"order_line_id": paper["id"], "issue_id": version.id,
                "expected_revision": paper["commitment_revision"], "promised_date": promise}
                for paper in papers if Decimal(str(paper["required_quantity"])) > 0]
            if not selected:
                raise HTTPException(409, "当前版本没有待执行纸品")
            portal.accept_lines(db, user, BatchCommitmentSave(factory_id=payload.factory_id, lines=selected),
                commit=False, resolve_dispute=True)
        record_response(db, user, payload.factory_id, payload.source_kind, version.id, "ACCEPTED", promised_date=promise)
        if payload.source_kind == "REGULAR" and core._purchase_order_snapshot(version).get("order_division_id"):
            core._refresh_order_statuses(db, {row.id}, user)
    db.flush()
    result = _task(db, user, row, version, payload.source_kind)
    if replay_id:
        event = core._audit(db, user, payload.factory_id, "SUPPLIER_CHANGE_REQUEST", "carton_supplier_change", version.id,
            {"fingerprint": digest, "result": result})
        event.id = replay_id
    db.commit()
    return result
