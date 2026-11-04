"""Atomic independent orders; all business identities/quantities come from live sources."""
import hashlib
import json
from datetime import date

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from app.models.carton_procurement import CartonAuditEvent, CartonImportBatch, CartonOrder
from app.schemas.carton_procurement import CartonOrderCreate, CartonOrderLineCreate
from app.schemas.carton_quantity import PaperQuantityRule
from app.services import carton_procurement as core
from app.services.carton_customer_assignment import ensure_customer_operation
from app.services.carton_order_projection import order_page_out
from app.services.carton_schedule_quantity_matching import packing
from app.services.carton_schedule_tracking import normalized
from app.services.carton_supplier_portal import fixed_supplier
from app.services.identity_policy import lock_mutation


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def request_content(payload):
    # Keep legacy default-only requests replayable. Nested omission and explicit
    # null are different weight operations and must never share a fingerprint.
    body = payload.model_dump(mode="json", exclude={"note", "rush", "rush_reason", "order_overrides"})
    explicit_nulls = [{"line_no": index, "fields": [field for field in
        ("net_weight_kg", "gross_weight_kg", "quantity_rule")
        if field in line.model_fields_set and getattr(line, field) is None]}
        for index, line in enumerate(payload.lines, 1)]
    explicit_nulls = [value for value in explicit_nulls if value["fields"]]
    if explicit_nulls:
        body["common_line_explicit_nulls"] = explicit_nulls
    for field in ("note", "rush", "rush_reason"):
        if getattr(payload, field):
            body[field] = getattr(payload, field)
    if payload.order_overrides:
        body["order_overrides"] = [value.model_dump(mode="json", exclude_unset=True) for value in payload.order_overrides]
    return body


def source_row(db, factory, source):
    batch = db.get(CartonImportBatch, source.batch_id)
    if not batch or batch.factory_id != factory or batch.import_type != "WEEKLY_SCHEDULE" or batch.status == "REJECTED":
        raise HTTPException(404, "有效的业务排期批次不存在，请刷新")
    rows = [r for r in core.import_batch_out(batch).parse_summary.get("rows", [])
            if isinstance(r, dict) and r.get("source_sheet") == source.source_sheet and r.get("source_row") == source.source_row]
    if len(rows) != 1:
        raise HTTPException(404, "排期明细不存在，请刷新")
    row = rows[0]
    code = str(row.get("schedule_customer_code") or "").strip().upper()
    if not code:
        name = " ".join(str(row.get("source_customer_name") or row.get("customer_name") or "").split()).casefold()
        customers = [c for c in core.list_customers(db, factory)
                     if " ".join(c.customer_name.split()).casefold() == name]
        code = customers[0].customer_code if len(customers) == 1 else ""
    if not code:
        raise HTTPException(422, "排期未绑定唯一基础客户，请先核对客户")
    return row, code, batch.original_filename


def paper_lines(lines, row):
    amounts = packing(row.get("carton_rule"))
    if amounts is None:
        raise HTTPException(422, "排期装箱数不完整或无效，请先核对内外箱装箱数")
    result, kinds = [], set()
    for original in lines:
        line = original.model_copy(deep=True)
        line.required_quantity = None
        if line.quantity_rule and line.quantity_rule.mode == "PER_CARTON":
            line.usage_quantity = None
        else:
            kind = "外箱" if line.packaging_type in {"外箱", "普通箱", "半翼箱"} else line.packaging_type
            if kind in {"内箱", "外箱"}:
                if kind in kinds:
                    raise HTTPException(422, "内箱／外箱各保留一条，不能重复装箱纸品")
                kinds.add(kind)
                amount = amounts[0 if kind == "内箱" else 1]
                if amount <= 0:
                    raise HTTPException(422, "所选排期没有内箱装箱数，不能套用含内箱的纸品资料")
                line.usage_quantity = amount
            elif not line.quantity_rule or line.quantity_rule.mode != "PACKING" or not line.usage_quantity:
                raise HTTPException(422, "其他纸品须明确按装箱数计算并填写每箱装产品数，或选择每箱配套规则")
        if not line.paper_quality or not line.specification or not line.dimension_unit:
            raise HTTPException(422, "请统一补齐纸质、规格及尺寸单位")
        result.append(line)
    if "外箱" not in kinds or (amounts[0] > 0 and "内箱" not in kinds):
        raise HTTPException(422, "纸品资料必须包含排期要求的内外箱，不能遗漏")
    return result


def apply_overrides(lines, override):
    if override is not None:
        for change in override.lines:
            line = lines[change.line_no - 1]
            if "manual_quantity" in change.model_fields_set:
                if line.quantity_rule or change.manual_quantity is not None:
                    value = line.quantity_rule.model_copy(deep=True) if line.quantity_rule else PaperQuantityRule()
                    value.manual_quantity = change.manual_quantity
                    line.quantity_rule = value
            for field in ("net_weight_kg", "gross_weight_kg"):
                if field in change.model_fields_set:
                    setattr(line, field, getattr(change, field))
    # Revalidate combined weights, retaining field-presence evidence for the
    # existing master-data inheritance in core.create_order.
    return [CartonOrderLineCreate.model_validate(line.model_dump(exclude_unset=True)) for line in lines]


def create(db, payload, user, *, refresh_user, authorize):
    try:
        factory = core.require_carton_factory(payload.factory_id)
        lock_mutation(db)
        core._lock_receipt_factory(db, factory)
        current = refresh_user()
        if current.id != user.id:
            raise HTTPException(401, "账号身份已变化，请重新核对")
        user = current
        authorize(user)
        fingerprint = digest(request_content(payload))
        event_id = "CAE-SBC-" + digest([factory, user.id, payload.request_id])
        prior = db.scalar(select(CartonAuditEvent).where(CartonAuditEvent.id == event_id))
        if prior:
            detail = json.loads(prior.detail_json)
            if detail["fingerprint"] != fingerprint:
                raise HTTPException(409, "该批量下单请求已有订单记录，当前内容或校验版本与原提交不一致（可能是旧版提交）；请核对原订单，勿重复下单")
            for result in detail["orders"]:
                order = db.get(CartonOrder, result["id"])
                if not order or order.factory_id != factory or order.deleted_at is not None:
                    raise HTTPException(409, "该批原订单已删除或不可访问，请核对历史记录，勿重复下单")
                ensure_customer_operation(db, user, factory, order.customer_code)
            db.commit()
            return detail["orders"]

        supplier = fixed_supplier(db, factory)
        today = core.now_text()[:10]
        overrides = {(value.batch_id, value.source_sheet, value.source_row): value for value in payload.order_overrides}
        selected, bodies, scope = [], [], None
        for index, source in enumerate(payload.sources, 1):
            try:
                row, code, filename = source_row(db, factory, source)
                ensure_customer_operation(db, user, factory, code)
                if row.get("schedule_identity_duplicate"):
                    raise HTTPException(409, "此排期的 SO / PO 身份重复，请先逐行核对，不能批量下单")
                customer = core.get_active_customer(db, factory, code)
                key = (code, normalized(row.get("item_no")))
                if scope is not None and scope != key:
                    raise HTTPException(422, "只能批量选择同厂区、同客户、同货号的排期")
                scope = key
                due = str(row.get("customer_due_date") or "").strip()
                if not due or date.fromisoformat(due).isoformat() != due:
                    raise HTTPException(422, "排期缺少完整客户交期，请先核对")
                body = CartonOrderCreate(factory_id=factory, customer_code=code, customer_name=customer.customer_name,
                    supplier_id=supplier.id, schedule_source=source,
                    contract_no=str(row.get("contract_no") or ""), item_no=str(row.get("item_no") or ""),
                    customer_po=str(row.get("customer_po") or ""),
                    product_name=str(row.get("product_name") or ""), product_order_quantity=row.get("quantity"),
                    order_date=today, customer_due_date=due, due_date=payload.planned_due_date, plan_date_manual=True,
                    master_config_id=payload.master_config_id, master_config_revision=payload.master_config_revision,
                    rush=payload.rush, rush_reason=payload.rush_reason,
                    note=((payload.note.strip() + "\n") if payload.note.strip() else "") +
                         (f"来源排期：{filename} / {source.source_sheet} 第 {source.source_row} 行；"
                          f"类型：{row.get('order_type') or '未填写'}；原装箱：{row.get('carton_rule') or ''}；"
                          f"业务 SO：{row.get('source_reference') or ''}；客户 PO：{row.get('customer_po') or ''}；客户交期：{due}"),
                    lines=apply_overrides(paper_lines(payload.lines, row),
                        overrides.get((source.batch_id, source.source_sheet, source.source_row))))
                core._schedule_source_for_order(db, factory, body)
                bodies.append(body)
                selected.append(source.model_dump())
            except (ValueError, ValidationError) as exc:
                raise HTTPException(422, f"第 {index} 条排期资料不完整或日期无效：{exc}") from exc
            except HTTPException as exc:
                raise HTTPException(exc.status_code, f"第 {index} 条排期：{exc.detail}；本批均未下单") from exc
        orders = []
        for index, body in enumerate(bodies, 1):
            try:
                order = core.create_order(db, body, user, commit=False)
                db.flush()
                core._require_order_complete(db, order)
                orders.append(order)
            except HTTPException as exc:
                raise HTTPException(exc.status_code, f"第 {index} 条排期：{exc.detail}；本批均未下单") from exc
        result = [r.model_dump(mode="json") for r in order_page_out(db, orders)]
        event = core._audit(db, user, factory, "SCHEDULE_BATCH_ORDERS_CREATED", "carton_schedule_batch",
            payload.request_id, {"fingerprint": fingerprint, "sources": selected, "orders": result})
        event.id = event_id
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
