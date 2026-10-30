"""Supplier-confirmed print changes. Proposals do not create additional demand.

The audit aggregate is immutable; acceptance materializes ordinary orders atomically.
Legacy allocations can be explicitly converted only before stock has moved.
"""
import hashlib
import json
from collections import defaultdict
from datetime import date
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select

from app.models.auth import AuthUser
from app.models.carton_mark import CartonMarkAsset
from app.models.carton_procurement import CartonAuditEvent, CartonOrder, CartonOrderLine
from app.models.carton_supplier_portal import SupplierCommitment
from app.schemas.carton_print_split import PrintSplitCreate
from app.services import carton_procurement as core
from app.services import carton_supplier_portal as portal
from app.services.carton_customer_assignment import ensure_customer_operation

ENTITY = "carton_print_split"
HELD = {"SENT", "DISPUTED", "WITHDRAWING"}


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def records(db, factory):
    cache = db.info.setdefault("print_split_records", {})
    if factory in cache: return cache[factory]
    result = {}
    for event in db.scalars(select(CartonAuditEvent).where(CartonAuditEvent.factory_id == factory,
            CartonAuditEvent.entity_type == ENTITY).order_by(CartonAuditEvent.sequence)):
        detail = json.loads(event.detail_json)
        if "plan" in detail:
            result[event.entity_id] = detail["plan"]
    cache[factory] = list(result.values())
    return cache[factory]


def get(db, factory, identifier):
    plan = next((p for p in records(db, factory) if p["id"] == identifier), None)
    if not plan:
        raise HTTPException(404, "印刷拆单不存在")
    return plan


def held(db, order):
    return next((p for p in records(db, order.factory_id)
                 if p["order_id"] == order.id and p["status"] in HELD), None)


def guard(db, order, *, allow_legacy_conversion=False):
    if held(db, order):
        raise HTTPException(409, "此订单有印刷拆单待供应商回应，请先处理拆单或取得撤回回执")
    if not allow_legacy_conversion:
        guard_legacy(db, order)


def guard_receipts(db, factory, line_ids):
    orders = db.scalars(select(CartonOrder).join(CartonOrderLine, CartonOrderLine.order_id == CartonOrder.id)
        .where(CartonOrder.factory_id == factory, CartonOrderLine.id.in_(line_ids))).unique()
    for order in orders:
        guard(db, order)
        guard_legacy(db, order)


def guard_legacy(db, order):
    from app.services.carton_order_split import live_plans
    if live_plans(db, order.factory_id, order.id):
        raise HTTPException(409, "此单仍是旧数量分配记录，请在订单拆分中转为独立订单后分别送货、收料，不能按原单合并执行")


def legacy_conversion(db, order, body):
    """Bind an explicit, revision checked conversion; never rewrite posted stock."""
    from app.services.carton_order_split import live_plans, norm
    plans = live_plans(db, order.factory_id, order.id)
    expected = {p["id"]: p["revision"] for p in plans}
    if expected != body.legacy_splits:
        raise HTTPException(409, "旧拆单记录已变化，请重新载入全部拆分去向后转换")
    if not plans:
        return []
    ids = [line["target_line_id"] for p in plans for t in p["targets"] for line in t["lines"]]
    from app.models.carton_procurement import CartonInventoryMovement
    if any(p["pairs"] or p["status"] != "ACTIVE" or any(line["stock"] or Decimal(line["received_quantity"]) for t in p["targets"] for line in t["lines"]) for p in plans) or db.scalar(select(CartonInventoryMovement.id).where(CartonInventoryMovement.factory_id == order.factory_id, CartonInventoryMovement.order_line_id.in_(ids)).limit(1)):
        raise HTTPException(409, "旧拆单已有库存分配或入库流水，不能自动转换。请先核对历史收料、领用及库存归属，保留原账务记录")
    def target_key(contract, po, product, amounts):
        return (norm(contract), norm(po), Decimal(str(product)) if product is not None else None, tuple(sorted(amounts.items())))
    old = {target_key(t["contract_no"], t["customer_po"], t["product_quantity"], {l["order_line_id"]: Decimal(l["pending_quantity"]) for l in t["lines"]}) for p in plans for t in p["targets"]}
    new = {target_key(t.contract_no, t.customer_po, t.product_quantity, {l.order_line_id: l.quantity for l in t.lines}) for t in body.targets}
    if old != new or len(body.targets) != sum(len(p["targets"]) for p in plans):
        raise HTTPException(409, "转换须完整保留旧拆单的合同、PO及数量；请重新载入旧记录")
    return plans


def authorize(db, user, factory):
    from app.services.carton_special_requests import locked_actor
    from app.api.carton_procurement import _ensure_permission, _ensure_order_adjustment_permission
    user = locked_actor(db, user, factory)
    _ensure_permission(db, user, "carton_procurement:order_write", factory)
    _ensure_order_adjustment_permission(db, user, factory)
    return user


def file_manifest(db, user, factory, identifiers):
    from app.services.carton_asset_access import ensure
    result = []
    if len(identifiers) != len(set(identifiers)):
        raise HTTPException(422, "印刷资料不能重复选择")
    for identifier in identifiers:
        if identifier.startswith("CMVREF|"):
            from app.services.carton_material_references import read_source
            parts = identifier.split("|")
            if len(parts) != 3: raise HTTPException(422, "印刷版本标识无效")
            entry, version, origin = read_source(db, factory, "warehouse", user, parts[1], parts[2])
            if version["role"] == "EVIDENCE" or not version.get("asset_id"):
                raise HTTPException(422, "请选择正式印刷原件或 PDF；核对照片与纯文字不能作为印刷文件")
            asset = db.get(CartonMarkAsset, version["asset_id"])
            result.append(dict(id=identifier, asset_id=asset.id, revision=version["number"], sha256=version["sha256"],
                file_name=version["file_name"], content_type=asset.content_type,
                source_context_id=parts[1], version_id=parts[2], version_event_sequence=origin["version_event_sequence"]))
            continue
        asset = db.get(CartonMarkAsset, identifier)
        if not asset or asset.factory_id != factory or asset.asset_purpose != "MATERIAL":
            raise HTTPException(404, "印刷资料不属于当前厂区")
        ensure(db, user, asset, view_factory=factory)
        result.append(dict(id=asset.id, revision=asset.revision, sha256=asset.sha256,
            file_name=asset.file_name, content_type=asset.content_type))
    return result


def source_files(db, user, order):
    """Inherit only currently associated and supplier-shared production originals."""
    from app.services import carton_mark_assets as assets, carton_mark_sharing as sharing, carton_mark_asset_workflow as lifecycle
    from app.services.carton_asset_access import visible
    orders = assets.available_orders(db, order.factory_id)
    audiences = sharing.states(db, order.factory_id)
    ids = []
    for asset in db.scalars(select(CartonMarkAsset).where(CartonMarkAsset.factory_id == order.factory_id,
            CartonMarkAsset.is_archived.is_(False), CartonMarkAsset.asset_purpose == "MATERIAL",
            CartonMarkAsset.recognition_source != "materials_folder")):
        audience = audiences.get(asset.id, {})
        if audience.get("sharing_mode") == "INTERNAL" or (audience.get("sharing_mode") == "SUPPLIER" and audience.get("shared_supplier_id") != order.supplier_id): continue
        if lifecycle.current(db, asset).status == "HISTORY" or not visible(db, user, asset, view_factory=order.factory_id): continue
        projected = assets.asset_out(asset, orders)
        if projected.binding_status == "BOUND" and any(o.id == order.id for o in projected.orders):
            ids.append(asset.id)
    return file_manifest(db, user, order.factory_id, ids)


def _validate(db, order, body, *, expected=True, allow_unissued=False):
    from app.services.carton_order_split import live_plans, norm
    from app.services.carton_quantity import requirements
    if expected and order.revision != body.expected_revision:
        raise HTTPException(409, "原订单已变化，请重新保存印刷拆单草稿")
    if not allow_unissued and (order.status not in {"PENDING_SUPPLIER", "PARTIALLY_RECEIVED"} or not portal.latest_issue(db, order)):
        raise HTTPException(409, "印刷拆单适用于已发给供应商且尚有待到数量的订单")
    if allow_unissued and order.status not in {"DRAFT", "CONFIRMED", "PENDING_SUPPLIER", "PARTIALLY_RECEIVED"}:
        raise HTTPException(409, "当前订单没有可拆的未入库需求；已完成或取消的订单只能查看拆分记录")
    legacy_conversion(db, order, body)
    papers = core.get_order_lines(db, order.id)
    ids = [p.id for p in papers]
    if any(portal.outstanding(db, ids).values()) or any(core._pending_received_by_line(db, ids).values()):
        raise HTTPException(409, "原单有在途送货或待确认收料，请先处理对应送货单或收料草稿，再拆分剩余需求")
    from app.services.carton_material_correction import guard_issue
    guard_issue(db, order)
    protected = core.protected_by_line(db, ids)
    totals = defaultdict(Decimal)
    products = Decimal(0)
    seen = {norm(order.contract_no)}
    existing = {norm(c) for c in db.scalars(select(CartonOrder.contract_no).where(
        CartonOrder.factory_id == order.factory_id, CartonOrder.customer_code == order.customer_code,
        CartonOrder.item_no == order.item_no, CartonOrder.deleted_at.is_(None)))}
    for target in body.targets:
        if norm(target.contract_no) in seen | existing:
            raise HTTPException(409, "拆分合同与原单、其他去向或已有订单重复，请核对需求")
        seen.add(norm(target.contract_no))
        core.master_data.validate_order(db, order.factory_id, order.customer_code, target.contract_no,
            order.item_no, customer_po=target.customer_po)
        if target.due_date.isoformat() < order.order_date:
            raise HTTPException(422, "拆单交期不能早于原下单日期")
        amounts = {p.order_line_id: p.quantity for p in target.lines}
        if len(amounts) != len(target.lines) or not set(amounts).issubset(ids) or (order.quantity_basis == "CALCULATED" and set(amounts) != set(ids)):
            raise HTTPException(422, "每个印刷去向须明确原单每项纸品，不能重复或漏项")
        if any(p.unit in {"张", "个", "件", "只", "箱"} and amounts.get(p.id, Decimal(0)) % 1 for p in papers):
            raise HTTPException(422, "按张、个、件、只、箱计数的拆分数量必须为整数")
        if order.quantity_basis == "CALCULATED":
            if target.product_quantity is None:
                raise HTTPException(422, "请填写拆出产品数量")
            demands = requirements(target.product_quantity, papers, manual_targets={i+1: amounts[p.id] for i, p in enumerate(papers)})
            if any(amounts[p.id] != demand for p, demand in zip(papers, demands)):
                raise HTTPException(422, "子单纸品数量必须符合原单装箱规则")
        products += target.product_quantity or Decimal(0)
        for identifier, quantity in amounts.items():
            totals[identifier] += quantity
    if order.product_order_quantity is not None and products > order.product_order_quantity:
        raise HTTPException(422, "拆出产品数量超过原单")
    remaining = {p.id: p.required_quantity - totals[p.id] for p in papers}
    if any(remaining[p.id] < protected.get(p.id, Decimal(0)) for p in papers):
        raise HTTPException(409, "拆出量超过未到货数量，已收纸箱不能直接改成另一种印刷")
    if order.quantity_basis == "CALCULATED":
        rest = order.product_order_quantity - products
        demands = requirements(rest, papers, manual_targets={i+1: remaining[p.id] for i, p in enumerate(papers)}) if rest else [Decimal(0)] * len(papers)
        if any(remaining[p.id] != demand for p, demand in zip(papers, demands)):
            raise HTTPException(422, "拆分取整后总纸箱需求变化，请另行补充采购，不能凭空增减数量")
    return papers, remaining, products


def _write(db, user, plan, event, *, replay=None, digest=None):
    db.info.pop("print_split_records", None)
    plan["revision"] += 1
    plan["updated_at"] = core.now_text()
    row = core._audit(db, user, plan["factory_id"], event, ENTITY, plan["id"],
        {"plan": plan, **({"fingerprint": digest} if digest else {})})
    if replay:
        row.id = replay
    db.flush()


def _replay(db, user, factory, request, body):
    if not request or len(request) < 8:
        raise HTTPException(422, "请提供有效提交标识以避免重复拆单")
    key = "CAE-PRINT-" + hashlib.sha256(encoded([factory, user.id, request]).encode()).hexdigest()
    digest = hashlib.sha256(encoded(body).encode()).hexdigest()
    previous = db.scalar(select(CartonAuditEvent).where(CartonAuditEvent.id == key))
    if previous:
        detail = json.loads(previous.detail_json)
        if detail.get("fingerprint") != digest:
            raise HTTPException(409, "提交标识已用于不同印刷拆单操作，请先核对原结果")
        return key, digest, get(db, factory, previous.entity_id)
    return key, digest, None


def same_files(left, right):
    # Folder activity may advance an evidence sequence without changing this immutable version.
    def identity(files):
        return sorted(encoded({k: v for k, v in file.items() if k != "version_event_sequence"}) for file in files)
    return identity(left) == identity(right)


def create(db, number, body, user):
    user = authorize(db, user, body.factory_id)
    order = core.get_order_by_no(db, body.factory_id, number)
    ensure_customer_operation(db, user, body.factory_id, order.customer_code)
    key, digest, prior = _replay(db, user, body.factory_id, body.request_id, [number, body.model_dump(mode="json")])
    if prior:
        return prior
    guard(db, order, allow_legacy_conversion=True)
    _validate(db, order, body)
    if not body.print_changed and any(t.asset_ids and sorted(t.asset_ids) != sorted(body.original_asset_ids) for t in body.targets):
        raise HTTPException(422, "沿用原印刷的子单必须继承同一份原件；更换资料请明确选择印刷不同")
    current_print = order_info(db, order)
    if current_print and current_print["status"] == "ACTIVE" and current_print["files"]:
        if sorted(body.original_asset_ids) != sorted(f["id"] for f in current_print["files"]):
            raise HTTPException(409, "已执行印刷的保留部分必须沿用固定原件；更换印刷只能拆入新的真实子单")
        for file in current_print["files"]:
            download(db, user, body.factory_id, current_print["id"], file["id"])
        original_files = current_print["files"]
    else:
        inherited = source_files(db, user, order) if not body.print_changed else []
        if inherited and body.original_asset_ids and sorted(body.original_asset_ids) != sorted(f["id"] for f in inherited):
            raise HTTPException(409, "同印刷拆单须沿用原单现有关联资料；更换印刷请明确选择印刷不同")
        original_files = inherited or file_manifest(db, user, body.factory_id, body.original_asset_ids)
    plan = dict(id="CPS-" + uuid4().hex, factory_id=body.factory_id, order_id=order.id,
        order_no=order.order_no, contract_no=order.contract_no, item_no=order.item_no,
        customer_code=order.customer_code, customer_name=order.customer_name, supplier_id=order.supplier_id,
        status="DRAFT", revision=0, created_at=core.now_text(), created_by=user.id,
        created_by_name=user.display_name, reason=body.reason, body=body.model_dump(mode="json"),
        original_files=original_files,
        print_changed=body.print_changed,
        original_evidence_added=bool(current_print and not current_print["files"] and original_files),
        targets=[{**t.model_dump(mode="json"), "files": file_manifest(db, user, body.factory_id, t.asset_ids) if body.print_changed else original_files} for t in body.targets],
        members=[], read=False, response_reason="")
    _write(db, user, plan, "PRINT_SPLIT_DRAFT", replay=key, digest=digest)
    db.commit()
    return plan


def act(db, identifier, action, body, user):
    user = authorize(db, user, body.factory_id)
    plan = get(db, body.factory_id, identifier)
    order = db.get(CartonOrder, plan["order_id"])
    ensure_customer_operation(db, user, body.factory_id, order.customer_code)
    key, digest, prior = _replay(db, user, body.factory_id, body.request_id, [identifier, action, body.model_dump(mode="json")])
    if prior:
        return prior
    if plan["revision"] != body.expected_revision:
        raise HTTPException(409, "印刷拆单已变化，请刷新")
    if action == "send":
        if plan["status"] != "DRAFT":
            raise HTTPException(409, "只能发送未发布的拆单草稿")
        guard(db, order, allow_legacy_conversion=True)
        original = PrintSplitCreate(**plan["body"])
        papers, remaining, _ = _validate(db, order, original)
        if original.print_changed and (not plan["original_files"] or any(not t["files"] for t in plan["targets"])):
            raise HTTPException(422, "请为原单和每个子单选择印刷资料；缺资料草稿请撤销后重新填写")
        current_print = order_info(db, order)
        inherited = current_print and current_print["status"] == "ACTIVE" and current_print["files"]
        if inherited:
            if not same_files(plan["original_files"], current_print["files"]):
                raise HTTPException(409, "保留部分的印刷版本已变化，请重新核对")
            for file in plan["original_files"]:
                download(db, user, body.factory_id, current_print["id"], file["id"])
        expected_files = ([] if inherited else [plan["original_files"]]) + ([t["files"] for t in plan["targets"]] if original.print_changed else [])
        for files in expected_files:
            if not same_files(file_manifest(db, user, body.factory_id, [f["id"] for f in files]), files):
                raise HTTPException(409, "所选印刷资料版本已变化，请重新保存草稿")
        plan.update(status="SENT", sent_at=core.now_text(), published_by=user.id,
            papers=[dict(id=p.id, packaging_type=p.packaging_type, paper_quality=p.paper_quality,
                specification=p.specification, unit=p.unit, before_quantity=str(p.required_quantity),
                quantity=str(remaining[p.id])) for p in papers])
    elif action == "withdraw":
        if plan["status"] not in {"DRAFT", "SENT", "DISPUTED"}:
            raise HTTPException(409, "已生效拆单不能撤销关系；请沿实际订单处理后续变更")
        plan["status"] = "CANCELLED" if plan["status"] == "DRAFT" else "WITHDRAWING"
        plan["withdraw_reason"] = body.reason
    else:
        raise HTTPException(422, "未知拆单操作")
    _write(db, user, plan, "PRINT_SPLIT_" + action.upper(), replay=key, digest=digest)
    db.commit()
    return plan


def _materialize(db, plan, user, promised, produced):
    from app.schemas.carton_procurement import CartonOrderCreate, CartonOrderLineCreate
    from app.services.auth import build_auth_context
    publisher = db.get(AuthUser, plan["published_by"])
    if not publisher or publisher.status != "active":
        raise HTTPException(409, "原发布人授权已失效，请内部撤回后由当前负责人重新发布")
    operator = authorize(db, build_auth_context(db, publisher), plan["factory_id"])
    order = db.get(CartonOrder, plan["order_id"])
    ensure_customer_operation(db, operator, plan["factory_id"], order.customer_code)
    body = PrintSplitCreate(**plan["body"])
    papers, remaining, products = _validate(db, order, body)
    if set(produced) != {p.id for p in papers}:
        raise HTTPException(422, "请逐纸品填写已按原印刷生产的累计数量（包含已送和已收）")
    protected = core.protected_by_line(db, [p.id for p in papers])
    for p in papers:
        value = Decimal(str(produced[p.id]))
        upper = remaining[p.id] if body.print_changed else p.required_quantity
        if not value.is_finite() or value < protected.get(p.id, Decimal(0)) or value > upper:
            raise HTTPException(409, "已按原印刷生产数量必须包含已收数量且不能超过原单保留量，请提出异议协商处理")
        if p.unit in {"张", "个", "件", "只", "箱"} and value % 1:
            raise HTTPException(422, "按张、个、件、只、箱计数的已生产数量必须为整数")
    # Revalidate pinned bytes before committing any supplier execution change.
    for file in plan["original_files"] + [f for t in plan["targets"] for f in t["files"]]:
        download(db, user, plan["factory_id"], plan["id"], file["id"], supplier=True)
    original = core.order_out(db, order).model_dump(mode="json")
    # Retire legacy projections in this transaction before create_order checks
    # demand collisions. A failed child/issue creation rolls everything back.
    for legacy in legacy_conversion(db, order, body):
        core._audit(db, operator, order.factory_id, "ORDER_SPLIT_CANCELLED", "carton_order_split", legacy["id"],
            {"reason": "转为独立订单", "converted_to": plan["id"], "expected_revision": legacy["revision"]})
    db.flush()
    children = []
    for target in plan["targets"]:
        amounts = {p["order_line_id"]: p["quantity"] for p in target["lines"]}
        data = {k: v for k, v in original.items() if k in CartonOrderCreate.model_fields}
        data.update(contract_no=target["contract_no"], customer_po=target["customer_po"],
            product_order_quantity=target["product_quantity"], due_date=target["due_date"], status="CONFIRMED", plan_date_manual=True,
            master_config_id="", master_config_revision=0, source_batch_id=None, source_row_key=None,
            note=f"拆单来源 {order.order_no} · {order.contract_no}；{plan['reason']}")
        data["lines"] = [{**{k: v for k, v in line.items() if k in CartonOrderLineCreate.model_fields},
            "required_quantity": amounts[line["id"]], **({"quantity_rule": {**line["quantity_rule"], "manual_quantity": amounts[line["id"]]}} if line.get("quantity_rule") and line["quantity_rule"].get("manual_quantity") is not None else {})} for line in original["lines"] if line["id"] in amounts]
        child = core.create_order(db, CartonOrderCreate(**data), operator, commit=False)
        child.status = "PENDING_SUPPLIER"
        children.append((child, target["files"]))
    for p in papers:
        p.required_quantity = remaining[p.id]
        if p.quantity_rule and p.quantity_rule.get("manual_quantity") is not None:
            p.quantity_rule_json = encoded({**p.quantity_rule, "manual_quantity": str(remaining[p.id])})
    rest = (order.product_order_quantity - products) if order.product_order_quantity is not None else None
    if rest is not None and rest > 0:
        order.product_order_quantity = rest
    if not any(remaining.values()):
        order.quantity_basis = "EXPLICIT"
        order.product_order_quantity = None
        order.status = "CANCELLED"
    elif all(remaining[p.id] == protected.get(p.id, Decimal(0)) for p in papers):
        order.status = "COMPLETED"
    order.revision += 1
    order.updated_at = core.now_text()
    order.updated_by = operator.id
    order.updated_by_name = operator.display_name
    # No partial commit: source reduction and all child issues share one transaction.
    members = []
    for member, files in [(order, plan["original_files"]), *children]:
        issue = core.create_purchase_order_issue(db, member, member.revision, operator, commit=False, already_locked=True, print_split_id=plan["id"])
        snapshot = core._purchase_order_snapshot(issue)
        print_info = dict(id=plan["id"], print_changed=body.print_changed, source_order_no=order.order_no, source_contract_no=order.contract_no,
            contract_no=member.contract_no, role="ORIGINAL" if member.id == order.id else "CHILD", files=files,
            targets=[t["contract_no"] for t in plan["targets"]], reason=plan["reason"])
        snapshot.update(print_split=print_info, change_reason="印刷拆单：" + plan["reason"])
        issue.snapshot_json = encoded(snapshot)
        members.append(dict(order_id=member.id, order_no=member.order_no, contract_no=member.contract_no,
            issue_id=issue.id, files=files, role=print_info["role"]))
        for paper in core.get_order_lines(db, member.id):
            commitment = db.get(SupplierCommitment, paper.id)
            if not commitment:
                commitment = SupplierCommitment(order_line_id=paper.id, factory_id=member.factory_id, revision=0)
                db.add(commitment)
            commitment.issue_id = issue.id
            commitment.promised_date = promised
            commitment.revision += 1
            commitment.accepted_by, commitment.accepted_at = user.id, core.now_text()
        from app.services.carton_supplier_changes import record_response
        record_response(db, user, member.factory_id, "REGULAR", issue.id,
            "CANCEL_ACKNOWLEDGED" if member.status == "CANCELLED" else "ACCEPTED", promised_date=promised,
            reason="整组确认印刷拆单 " + plan["id"])
    plan.update(status="ACTIVE", members=members, produced_quantities={k: str(v) for k, v in produced.items()})


def respond(db, user, body):
    from app.services.carton_special_requests import locked_actor
    user = locked_actor(db, user, body.factory_id)
    vendor = portal.supplier_access(db, user, body.factory_id,
        "carton_supplier:read" if body.action == "READ" else "carton_supplier:approve")
    plan = get(db, body.factory_id, body.source_id)
    if plan["supplier_id"] != vendor.id or plan["status"] == "DRAFT":
        raise HTTPException(404, "未找到当前供应商印刷拆单")
    key, digest, prior = _replay(db, user, body.factory_id, body.request_id, body.model_dump(mode="json"))
    if prior:
        return task(prior, user, internal=False)
    if plan["revision"] != body.expected_revision or plan["status"] not in HELD:
        raise HTTPException(409, "拆单状态已变化，请刷新核对")
    if body.action == "READ":
        plan["read"] = True
    elif body.action == "DISPUTE":
        if not body.reason.strip() or plan["status"] == "WITHDRAWING":
            raise HTTPException(422, "请填写拆单异议；撤回通知请确认收到")
        plan.update(status="DISPUTED", response_reason=body.reason)
    elif body.action == "ACK_CANCEL":
        if plan["status"] != "WITHDRAWING":
            raise HTTPException(409, "此拆单尚未请求撤回")
        plan["status"] = "CANCELLED"
    elif body.action == "ACCEPT":
        if plan["status"] == "WITHDRAWING" or not body.promised_date:
            raise HTTPException(422, "请确认有效拆单并填写承诺交期")
        _materialize(db, plan, user, body.promised_date.isoformat(), body.produced_quantities)
    else:
        raise HTTPException(422, "不支持的拆单回应")
    if body.action != "READ":
        plan.update(responded_by=user.display_name, responded_at=core.now_text())
    _write(db, user, plan, "PRINT_SPLIT_RESPONSE", replay=key, digest=digest)
    db.commit()
    return task(plan, user, internal=False)


def task(plan, user, *, internal):
    pending = plan["status"] in HELD
    age_days = max(0, (core.business_now().date() - date.fromisoformat(plan["created_at"][:10])).days)
    status = {"SENT": "PENDING", "ACTIVE": "ACCEPTED", "CANCELLED": "CANCEL_ACKNOWLEDGED",
        "WITHDRAWING": "PENDING"}.get(plan["status"], plan["status"])
    return dict(source_kind="PRINT", source_id=plan["id"], factory_id=plan["factory_id"],
        order_id=plan["order_id"], order_no=plan["order_no"], document_no="订单拆分 · " + plan["order_no"],
        expected_revision=plan["revision"], status=status, is_cancellation=plan["status"] == "WITHDRAWING",
        read=plan["read"], read_at="", reason=plan.get("response_reason", ""),
        responded_by=plan.get("responded_by", ""), responded_at=plan.get("responded_at", ""),
        promised_date="", planned_date=max(t["due_date"] for t in plan["targets"]), before_date="",
        change_reason=plan["reason"], created_at=plan["created_at"], age_days=age_days, overdue=pending and age_days >= 1,
        action="PRINT_SPLIT", responsibility="", lines=plan.get("papers", []), material_changed=True,
        pending=pending, can_respond=pending and not internal and portal.supplier_permission(user,
            "carton_supplier:approve", plan["factory_id"]), print_split=plan)


def order_info(db, order):
    for plan in reversed(records(db, order.factory_id)):
        if plan.get("workflow") == "ORDER":
            continue
        if plan["status"] in HELD and plan["order_id"] == order.id:
            return dict(id=plan["id"], print_changed=plan.get("print_changed", True), role="ORIGINAL", status=plan["status"], source_order_no=order.order_no,
                source_contract_no=order.contract_no, targets=[t["contract_no"] for t in plan["targets"]], files=plan["original_files"])
        for member in plan["members"]:
            if member["order_id"] == order.id:
                return dict(id=plan["id"], print_changed=plan.get("print_changed", True), role=member["role"], status=plan["status"], source_order_no=plan["order_no"],
                    source_contract_no=plan["contract_no"], targets=[t["contract_no"] for t in plan["targets"]], files=member["files"])
    return None


def download(db, user, factory, identifier, asset_id, *, supplier=False):
    plan = get(db, factory, identifier)
    if plan.get("workflow") == "ORDER":
        raise HTTPException(404, "普通拆单资料请从订单资料库查看")
    if supplier:
        vendor = portal.supplier_access(db, user, factory)
        if vendor.id != plan["supplier_id"] or plan["status"] == "DRAFT":
            raise HTTPException(404, "没有此印刷资料的访问权限")
    else:
        portal.internal_permission(user, factory, "carton_procurement:read")
        ensure_customer_operation(db, user, factory, plan["customer_code"])
    files = plan["original_files"] + [f for t in plan["targets"] for f in t["files"]]
    frozen = next((f for f in files if f["id"] == asset_id), None)
    asset = db.get(CartonMarkAsset, frozen.get("asset_id", asset_id)) if frozen else None
    if not frozen or not asset or asset.factory_id != factory or hashlib.sha256(asset.content).hexdigest() != frozen["sha256"]:
        raise HTTPException(409, "固定印刷原件不可用，请联系内部核对，不能自动替换为最新版本")
    return asset, frozen


def material_candidates(db, user, factory, customer_code):
    """Expose accessible immutable file versions, including adopted references."""
    from app.services import carton_materials as materials
    from app.services.carton_material_references import hydrate
    result = []
    for state in materials.folders(db, factory).values():
        if state.get("customer_code") != customer_code or state.get("is_archived") or state.get("hidden"):
            continue
        try:
            materials.authorize(db, user, factory, "warehouse", state)
            current = hydrate(db, factory, "warehouse", user, state)
            for version in current.get("versions", []):
                if version.get("role") == "EVIDENCE": continue
                identifier = f"CMVREF|{state['id']}|{version['id']}"
                try:
                    result.extend(file_manifest(db, user, factory, [identifier]))
                except HTTPException as exc:
                    if exc.status_code not in {403, 404, 409, 422}: raise
        except HTTPException as exc:
            if exc.status_code not in {403, 404}: raise
    return result
