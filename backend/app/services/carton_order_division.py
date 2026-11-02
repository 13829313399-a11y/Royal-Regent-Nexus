"""Ordinary independent orders; supplier acknowledgement uses REGULAR changes."""
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select

from app.models.carton_procurement import CartonOrder
from app.schemas.carton_print_split import PrintSplitCreate
from app.services import carton_print_split as history, carton_procurement as core
from app.services import carton_supplier_portal as portal
from app.services.carton_customer_assignment import ensure_customer_operation


def order_info(db, order):
    origin, children = None, []
    for record in history.records(db, order.factory_id):
        if record.get("workflow") != "ORDER":
            continue
        if record["order_id"] == order.id:
            children.extend({k: m[k] for k in ("order_id", "order_no", "contract_no")} for m in record["members"] if m["role"] == "CHILD")
        if any(m["order_id"] == order.id and m["role"] == "CHILD" for m in record["members"]):
            origin = dict(source_order_no=record["order_no"], source_contract_no=record["contract_no"])
    return {**(origin or {}), "children": children} if origin or children else None


def context(db, user, factory, number):
    from app.api.carton_procurement import _ensure_permission
    from app.services import carton_order_split as legacy
    _ensure_permission(db, user, "carton_procurement:read", factory)
    order = core.get_order_by_no(db, factory, number)
    ensure_customer_operation(db, user, factory, order.customer_code)
    result = legacy.context(db, factory, number)
    old = [p for p in history.records(db, factory) if p.get("workflow") != "ORDER" and p["order_id"] == order.id]
    reason = ""
    if order.status not in {"DRAFT", "CONFIRMED", "PENDING_SUPPLIER", "PARTIALLY_RECEIVED"}:
        reason = "当前订单没有可拆的未入库需求，仅可查看拆分记录。"
    elif history.held(db, order):
        reason = "此前的拆单方案仍待供应商回应，请先在下方请求撤回并取得回执，再使用简化拆单。"
    else:
        ids = [line.id for line in core.get_order_lines(db, order.id)]
        if any(portal.outstanding(db, ids).values()) or any(core._pending_received_by_line(db, ids).values()):
            reason = "原单有在途送货或待确认收料，请先处理对应送货单或收料草稿，再拆分剩余需求。"
    return {**result, "supplier_notified": bool(portal.latest_issue(db, order)),
            "can_split": not reason, "block_reason": reason, "order_split": order_info(db, order),
            "previous_proposals": [p for p in old if p["status"] in {"DRAFT", *history.HELD}]}


def _inherit_materials(db, user, order, children, sources):
    """Copy authorized current associations once; later edits use the normal library."""
    from app.models.carton_mark import CartonMarkAssetOrderBinding
    from app.services import carton_asset_targets as targets
    for asset, matches in sources:
        saved = targets.current(db, asset)
        # Preserve source and unrelated existing associations, including schedules.
        rows = list(saved)
        known = {r["id"] for r in rows if r["kind"] == "REGULAR"}
        for member in [*matches, *children]:
            if member.id not in known:
                row = dict(kind="REGULAR", id=member.id, sheet="", row=0,
                    customer_code=member.customer_code, customer_name=member.customer_name,
                    contract_no=member.contract_no, item_no=member.item_no, customer_po=member.customer_po,
                    supplier_id=member.supplier_id, revision=member.revision)
                row["identity"] = targets.identity(row)
                row["fingerprint"] = targets.digest(row)
                rows.append(row)
                known.add(member.id)
        existing = {link.order_id for link in asset.order_bindings}
        for member in [*matches, *children]:
            if member.id not in existing:
                asset.order_bindings.append(CartonMarkAssetOrderBinding(factory_id=order.factory_id, order_id=member.id))
                existing.add(member.id)
        asset.recognition_source = "manual_orders"
        asset.revision += 1
        asset.updated_at = core.now_text()
        core._audit(db, user, order.factory_id, targets.EVENT, "carton_mark_asset", asset.id,
                    {"targets": rows, "reason": "独立拆单自动沿用关联资料", "source_order_id": order.id})
    db.flush()


def _material_sources(db, user, order):
    from app.models.carton_mark import CartonMarkAsset
    from app.services import carton_mark_assets as assets, carton_mark_asset_workflow as lifecycle
    from app.services.carton_asset_access import visible
    orders = assets.available_orders(db, order.factory_id)
    result = []
    for asset in db.scalars(select(CartonMarkAsset).where(CartonMarkAsset.factory_id == order.factory_id,
            CartonMarkAsset.is_archived.is_(False), CartonMarkAsset.asset_purpose == "MATERIAL",
            CartonMarkAsset.recognition_source != "materials_folder")):
        if lifecycle.current(db, asset).status == "HISTORY" or not visible(db, user, asset, view_factory=order.factory_id):
            continue
        matches = assets.matching_asset_orders(asset, orders)
        if any(member.id == order.id for member in matches):
            result.append((asset, matches))
    return result


def create(db, number, payload, user):
    from app.schemas.carton_procurement import CartonOrderCreate, CartonOrderLineCreate
    from app.services.carton_special_requests import locked_actor
    from app.api.carton_procurement import _ensure_permission, _ensure_order_adjustment_permission
    user = locked_actor(db, user, payload.factory_id)
    _ensure_permission(db, user, "carton_procurement:order_write", payload.factory_id)
    order = core.get_order_by_no(db, payload.factory_id, number)
    if portal.latest_issue(db, order):
        _ensure_order_adjustment_permission(db, user, payload.factory_id)
    ensure_customer_operation(db, user, payload.factory_id, order.customer_code)
    key, digest, prior = history._replay(db, user, payload.factory_id, payload.request_id,
                                       ["ORDER", number, payload.model_dump(mode="json")])
    if prior:
        return prior
    history.guard(db, order, allow_legacy_conversion=True)
    body = PrintSplitCreate(**payload.model_dump(), print_changed=False)
    papers, remaining, products = history._validate(db, order, body, allow_unissued=True)
    issued = portal.latest_issue(db, order)
    if issued and core._purchase_order_pending_change(order, papers, issued)[0] != "NONE":
        raise HTTPException(409, "原单还有未发送的订单变更，请先完成原变更发送，再进行拆单")
    original = core.order_out(db, order).model_dump(mode="json")
    sources = _material_sources(db, user, order)
    plan = dict(id="COS-" + uuid4().hex, workflow="ORDER", factory_id=order.factory_id,
        order_id=order.id, order_no=order.order_no, contract_no=order.contract_no,
        customer_code=order.customer_code, customer_name=order.customer_name, item_no=order.item_no,
        supplier_id=order.supplier_id, supplier_notified=bool(issued), status="ACTIVE", revision=0,
        created_at=core.now_text(), created_by=user.id, created_by_name=user.display_name,
        reason=payload.reason, members=[], targets=[t.model_dump(mode="json") for t in payload.targets],
        before=original, original_files=[], response_reason="")
    for legacy in history.legacy_conversion(db, order, body):
        core._audit(db, user, order.factory_id, "ORDER_SPLIT_CANCELLED", "carton_order_split", legacy["id"],
            {"reason": "转为独立订单", "converted_to": plan["id"], "expected_revision": legacy["revision"]})
    db.flush()
    children = []
    for target in payload.targets:
        amounts = {line.order_line_id: line.quantity for line in target.lines}
        data = {k: v for k, v in original.items() if k in CartonOrderCreate.model_fields}
        data.update(contract_no=target.contract_no, customer_po=target.customer_po,
            product_order_quantity=target.product_quantity, due_date=target.due_date.isoformat(),
            status="CONFIRMED", plan_date_manual=True, master_config_id="", master_config_revision=0,
            source_batch_id=None, source_row_key=None,
            note=f"拆单来源 {order.order_no} · {order.contract_no}；{payload.reason}")
        data["lines"] = [{**{k: v for k, v in line.items() if k in CartonOrderLineCreate.model_fields},
            "required_quantity": amounts[line["id"]],
            **({"quantity_rule": {**line["quantity_rule"], "manual_quantity": amounts[line["id"]]}}
               if (line.get("quantity_rule") or {}).get("manual_quantity") is not None else {})}
            for line in original["lines"] if line["id"] in amounts]
        child = core.create_order(db, CartonOrderCreate(**data), user, commit=False)
        child.status = "PENDING_SUPPLIER" if issued else "CONFIRMED"
        children.append(child)
    for paper in papers:
        paper.required_quantity = remaining[paper.id]
        if paper.quantity_rule and paper.quantity_rule.get("manual_quantity") is not None:
            paper.quantity_rule_json = history.encoded({**paper.quantity_rule, "manual_quantity": str(remaining[paper.id])})
    rest = order.product_order_quantity - products if order.product_order_quantity is not None else None
    order.product_order_quantity = rest if rest and all(t.product_quantity is not None for t in payload.targets) else None
    if not any(remaining.values()):
        order.quantity_basis, order.status = "EXPLICIT", "CANCELLED"
    # Keep a submitted source executable for its reduction acknowledgement even
    # when only already received demand remains. Standard acceptance closes it later.
    order.revision += 1
    order.updated_at, order.updated_by, order.updated_by_name = core.now_text(), user.id, user.display_name
    core._audit(db, user, order.factory_id, "ORDER_REDUCED", "carton_order", order.id,
        {"revision": order.revision, "reason": f"拆单至 { '、'.join(t.contract_no for t in payload.targets) }；{payload.reason}",
         "split_id": plan["id"], "before": original})
    _inherit_materials(db, user, order, children, sources)
    for member in [order, *children]:
        issue = None
        if issued:
            issue = core.create_purchase_order_issue(db, member, member.revision, user, commit=False,
                                                    already_locked=True, print_split_id=plan["id"])
            snapshot = core._purchase_order_snapshot(issue)
            snapshot["order_division_id"] = plan["id"]
            snapshot["change_reason"] = (f"拆单来源 {order.order_no} · {order.contract_no}；" if member != order else
                f"拆单减量，拆出至 {'、'.join(t.contract_no for t in payload.targets)}；") + payload.reason
            issue.snapshot_json = history.encoded(snapshot)
        plan["members"].append(dict(order_id=member.id, order_no=member.order_no, contract_no=member.contract_no,
            role="ORIGINAL" if member == order else "CHILD", issue_id=issue.id if issue else ""))
    history._write(db, user, plan, "ORDER_DIVIDED", replay=key, digest=digest)
    db.commit()
    return plan
