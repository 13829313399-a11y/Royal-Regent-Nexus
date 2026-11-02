"""Shared new-order import coordinator; source domains keep their own create rules."""
import hashlib
import json
from collections import OrderedDict

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select

from app.models.carton_procurement import CartonAuditEvent, CartonOrder, CartonSupplier
from app.schemas.carton_procurement import CartonOrderCreate, CartonOrderLineCreate
from app.schemas.carton_special_requests import Create
from app.services import carton_procurement as core, carton_special_requests as special, carton_demand_import as demand
from app.services.carton_customer_assignment import ensure_customer_operation
from app.services.carton_order_import_file import fields


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


def authorize(db, user, factory, mode):
    core.require_carton_factory(factory)
    if mode == "SPECIAL":
        demand.authorize(db, user, factory)
    elif not special.allowed(user, factory, "order_write"):
        raise HTTPException(403, "没有本厂正单下单权限")


def norm(value):
    return " ".join(value.split()).casefold()


def group_key(row, mode):
    data = row.data if hasattr(row, "data") else row["data"]
    if mode == "SPECIAL":
        return ("special", data.get("group", "").strip()) if data.get("group", "").strip() else ("missing", row.source_row if hasattr(row, "source_row") else row["source_row"])
    # A supplied grouping label holds incomplete/conflicting identity rows together.
    if data.get("group", "").strip():
        return ("group", data["group"].strip())
    identity = tuple(norm(data.get(key, "")) for key in ("customer", "contract_no", "item_no", "customer_po"))
    return ("regular", *identity) if any(identity) else ("missing", row.source_row if hasattr(row, "source_row") else row["source_row"])


def group_rows(rows, mode):
    groups = OrderedDict()
    for row in rows:
        groups.setdefault(group_key(row, mode), []).append(row)
    if len(groups) > 100:
        raise HTTPException(422, "每次最多 100 张订单，请缩小文件批次")
    return groups


def ambiguous_rows(rows, mode, customers=None):
    """An incomplete identity must never strand a sibling paper outside a ready order.

    A special-demand group is its identity. For regular orders a grouping label
    cannot replace missing business identity, so hold compatible candidates.
    A blank PO alongside a populated PO for the same base identity is ambiguous too.
    """
    blocked = set()
    def identity_value(data, key):
        value = norm(data.get(key, ""))
        return ((customers or {}).get(value) or value) if key == "customer" else value
    for row in rows:
        d = row.data
        if mode == "SPECIAL" and d.get("group"):
            continue
        incomplete = mode == "SPECIAL" or any(not d.get(k) for k in ("customer", "contract_no", "item_no"))
        keys = ("customer", "contract_no", "item_no", "customer_po")
        compatible = [other for other in rows if all(not d.get(k) or not other.data.get(k) or identity_value(d, k) == identity_value(other.data, k) for k in keys)]
        blank_po_mixed = mode == "REGULAR" and not d.get("customer_po") and any(other.data.get("customer_po") for other in compatible)
        if incomplete or blank_po_mixed:
            blocked.update(other.source_row for other in compatible)
    return blocked


def validate_source(payload, original):
    if payload.fingerprint != original["fingerprint"]:
        raise HTTPException(409, "文件已变化，请重新读取")
    source_ids = [r["source_row"] for r in original["rows"]]
    submitted = [r.source_row for r in payload.rows]
    if len(set(submitted)) != len(submitted) or set(source_ids) != set(submitted):
        raise HTTPException(422, "必须保留所选工作表全部原始行；请按整单选择，不能遗漏纸品行")
    allowed = {k for k, _, _ in fields(payload.mode)}
    if any(set(r.data) - allowed for r in payload.rows):
        raise HTTPException(422, "导入包含不适用于此订单类型的字段")


def claim_id(factory, fingerprint, sheet, row):
    # Preserve old demand-import claims so a different endpoint cannot duplicate them.
    if sheet == "新建需求":
        return "CAE-DI-" + hashlib.sha256(f"{factory}:{fingerprint}:{row}".encode()).hexdigest()
    return "CAE-OI-" + digest([factory, fingerprint, sheet, row])


def require_fields(data, keys):
    labels = {key: label for key, label, _ in fields("REGULAR") + fields("SPECIAL")}
    missing = [labels[k] for k in keys if not data.get(k, "").strip()]
    if missing:
        raise HTTPException(422, "缺少：" + "、".join(missing))


def customer_for(db, factory, value):
    matches = [c for c in core.list_customers(db, factory) if norm(value) in {norm(c.customer_code), norm(c.customer_name)}]
    if len(matches) != 1:
        raise HTTPException(422, "客户不存在、未启用或名称不唯一，请填写本厂已维护的准确名称或编码")
    return matches[0]


def regular_customer_codes(db, factory, rows):
    customers = {}
    for row in rows:
        value = norm(row.data.get("customer", ""))
        if value and value not in customers:
            try:
                customers[value] = customer_for(db, factory, row.data["customer"]).customer_code
            except HTTPException:
                customers[value] = None
    return customers


def repeated_regular_groups(grouped, customers):
    """Resolve business identities before paper validation can reject a sibling group."""
    identities = {}
    for key, rows in grouped.items():
        for row in rows:
            data = row.data
            if any(not data.get(k) for k in ("customer", "contract_no", "item_no")):
                continue
            customer = norm(data["customer"])
            if not customers.get(customer):
                continue
            identity = (customers[customer], *[norm(data.get(k, "")) for k in ("contract_no", "item_no", "customer_po")])
            identities.setdefault(identity, set()).add(key)
    return {key for owners in identities.values() if len(owners) > 1 for key in owners}


def regular_body(db, user, factory, rows):
    first = rows[0].data
    headers = ("customer", "contract_no", "item_no", "customer_po", "product_name", "product_quantity", "order_date", "customer_due_date", "due_date")
    for row in rows:
        require_fields(row.data, ("customer", "contract_no", "item_no", "order_date", "customer_due_date", "packaging_type", "paper_quality", "specification", "unit"))
        if any(norm(row.data.get(k, "")) != norm(first.get(k, "")) for k in headers):
            raise HTTPException(422, "同一订单的客户、合同、货号、PO、产品数量及日期须一致，请核对每行订单信息")
    customer = customer_for(db, factory, first["customer"])
    ensure_customer_operation(db, user, factory, customer.customer_code)
    rules = core.master_data.validate_order(db, factory, customer.customer_code, first["contract_no"], first["item_no"], customer_po=first.get("customer_po", ""))
    vendors = list(db.scalars(select(CartonSupplier).where(CartonSupplier.factory_id == factory, CartonSupplier.status == "ACTIVE")))
    if len(vendors) != 1:
        raise HTTPException(422, "当前厂区须有唯一有效纸箱供应商，请先核对基础资料")
    explicit = all(r.data.get("quantity") for r in rows) and not any(r.data.get("usage_quantity") or r.data.get("carton_source_row") or r.data.get("per_carton_quantity") for r in rows)
    if not explicit and not first.get("product_quantity"):
        raise HTTPException(422, "缺少产品订单数量；或为每行明确填写采购数量")
    indices = {row.source_row: i for i, row in enumerate(rows, 1)}
    papers = []
    warnings = []
    for row in rows:
        d = row.data
        dimension = {"厘米": "cm", "英寸": "in", "inch": "in", "毫米": "mm"}.get(d.get("dimension_unit", "").lower(), d.get("dimension_unit", "").lower()) or "cm"
        if dimension not in {"cm", "in", "mm"}:
            raise HTTPException(422, f"第 {row.source_row} 行尺寸单位须为 cm、inch 或 mm")
        from app.services.carton_material_identity import dimension_unit
        embedded = dimension_unit(d["specification"])
        if embedded and embedded != dimension:
            raise HTTPException(422, f"第 {row.source_row} 行规格与尺寸单位冲突")
        if not d.get("dimension_unit"):
            warnings.append(f"第 {row.source_row} 行尺寸单位按 cm")
        rule = None
        if not explicit:
            if d.get("carton_source_row") or d.get("per_carton_quantity"):
                try:
                    reference = indices[int(d.get("carton_source_row", ""))]
                except (ValueError, KeyError) as exc:
                    raise HTTPException(422, f"第 {row.source_row} 行须引用同一订单内的纸箱原表行号") from exc
                rule = {"mode": "PER_CARTON", "carton_line_no": reference, "per_carton_quantity": d.get("per_carton_quantity") or None}
            else:
                if not d.get("usage_quantity"):
                    raise HTTPException(422, f"第 {row.source_row} 行缺少每箱个数")
                rule = {"mode": "PACKING"}
            if d.get("quantity"):
                rule["manual_quantity"] = d["quantity"]
        papers.append(CartonOrderLineCreate(packaging_type=d["packaging_type"], paper_quality=d["paper_quality"], specification=d["specification"],
            dimension_unit=dimension, unit=d["unit"], usage_quantity=d.get("usage_quantity") or None,
            required_quantity=d.get("quantity") or None, quantity_rule=rule,
            net_weight_kg=d.get("net_weight_kg") or None, gross_weight_kg=d.get("gross_weight_kg") or None, note=d.get("note", "")))
    suggested_due = core.derive_carton_plan_due_date(first["order_date"], first["customer_due_date"], rules["lead_days"])
    due = first.get("due_date") or suggested_due
    body = CartonOrderCreate(factory_id=factory, customer_code=customer.customer_code, customer_name=customer.customer_name,
        contract_no=first["contract_no"], item_no=first["item_no"], customer_po=first.get("customer_po", ""), product_name=first.get("product_name", ""),
        product_order_quantity=first.get("product_quantity") or None, quantity_basis="EXPLICIT" if explicit else "CALCULATED",
        supplier_id=vendors[0].id, order_date=first["order_date"], customer_due_date=first["customer_due_date"], due_date=due,
        plan_date_manual=bool(first.get("due_date")), lines=papers)
    # Schema defaults are compatibility-only; canonical current factory/customer lead wins.
    body.due_date = due
    quantities = [str(core._input_required(body, paper)) for paper in papers]
    identity = tuple(norm(x) for x in (body.contract_no, body.item_no, body.customer_po))
    existing = db.scalars(select(CartonOrder).where(CartonOrder.factory_id == factory, CartonOrder.customer_code == customer.customer_code))
    if any(tuple(norm(x) for x in (o.contract_no, o.item_no, o.customer_po)) == identity for o in existing):
        raise HTTPException(409, "相同客户、合同、货号及 PO 已有订单记录，请核对原单；导入不会覆盖或追加")
    if not first.get("due_date"):
        warnings.append(f"计划到料日期按当前提前 {rules['lead_days']} 天计算：{due}")
    warnings.extend(w["message"] for w in core.master_data.number_warnings(rules, body.contract_no, body.item_no, body.customer_po) if not w["blocking"])
    basis = {"rules": rules, "customer_revision": customer.revision, "supplier": [vendors[0].id, vendors[0].supplier_name]}
    return body, quantities, warnings, basis


def special_body(db, factory, rows):
    inputs = []
    warnings = []
    for row in rows:
        d = row.data
        require_fields(d, ("group", "kind", "required_date", "packaging_type", "paper_quality", "specification", "quantity", "unit"))
        if not d.get("dimension_unit"):
            warnings.append(f"第 {row.source_row} 行尺寸单位按 cm")
        inputs.append(demand.ImportRow(source_row=row.source_row, **{key: d.get(key, "") for key in demand.KEYS if key != "dimension_unit"}, dimension_unit=d.get("dimension_unit") or "cm"))
    grouped = demand.grouped(inputs)
    if len(grouped) != 1:
        raise HTTPException(422, "同一订单分组不一致")
    item = next(iter(grouped.values()))
    body = Create(factory_id=factory, request_id="preview-order-import", kind=item["kind"], required_date=item["required_date"], purpose="\n".join(item["notes"]), lines=item["lines"])
    vendor = special.portal.fixed_supplier(db, factory)
    return body, [str(line.quantity) for line in body.lines], warnings, {"supplier": [vendor.id, vendor.supplier_code, vendor.supplier_name, vendor.status]}


def assessment(db, user, payload, original):
    validate_source(payload, original)
    grouped = group_rows(sorted(payload.rows, key=lambda r: r.source_row), payload.mode)
    results, bodies = [], {}
    original_groups = group_rows(original["rows"], payload.mode)
    owners = {row.source_row: key for key, rows in grouped.items() for row in rows}
    split_sources = {r["source_row"] for rows in original_groups.values() if len({owners[r["source_row"]] for r in rows}) > 1 for r in rows}
    customers = regular_customer_codes(db, payload.factory_id, payload.rows) if payload.mode == "REGULAR" else {}
    ambiguous = ambiguous_rows(payload.rows, payload.mode, customers)
    repeated = repeated_regular_groups(grouped, customers) if payload.mode == "REGULAR" else set()
    for key, rows in grouped.items():
        ids = [row.source_row for row in rows]
        identifier = "G-" + "-".join(map(str, ids))
        entry = {"id": identifier, "source_rows": ids, "label": rows[0].data.get("group") or " / ".join(rows[0].data.get(k, "") for k in ("customer", "contract_no", "item_no", "customer_po")),
                 "errors": [], "warnings": [], "quantities": [], "due_date": "", "status": "INVALID"}
        try:
            if len(rows) > 50:
                raise HTTPException(422, "一张订单最多 50 项纸品")
            if set(ids) & split_sources:
                raise HTTPException(422, "原表同一订单的纸品不能拆开导入，请保持原分组一致")
            if set(ids) & ambiguous:
                message = "有纸品行缺少明确订单归属，可能属于本单；请补齐这些行的客户／合同／货号／PO 后重新校验，分组编号不能代替订单信息" if payload.mode == "REGULAR" else "有纸品行缺少分组编号，请为全部纸品明确订单归属后重新校验"
                raise HTTPException(422, message)
            if key in repeated:
                raise HTTPException(422, "文件内同一客户、合同、货号、PO 出现在多个分组，请合并核对")
            claims = [claim_id(payload.factory_id, payload.fingerprint, original["sheet"], n) for n in ids]
            if db.scalar(select(CartonAuditEvent.id).where(CartonAuditEvent.id.in_(claims)).limit(1)):
                entry["status"] = "IMPORTED"
                raise HTTPException(409, "本组原表行已有导入记录，请核对台账")
            body, quantities, warnings, basis = regular_body(db, user, payload.factory_id, rows) if payload.mode == "REGULAR" else special_body(db, payload.factory_id, rows)
            entry.update(status="READY", quantities=quantities, warnings=warnings, due_date=body.due_date if payload.mode == "REGULAR" else body.required_date.isoformat())
            bodies[identifier] = (body, basis)
        except HTTPException as exc:
            entry["errors"].append(str(exc.detail))
        except ValidationError as exc:
            entry["errors"].extend(" / ".join(map(str, e["loc"])) + "：" + e["msg"] for e in exc.errors(include_url=False))
        except ValueError:
            entry["errors"].append("请核对日期（YYYY-MM-DD）及数量格式")
        results.append(entry)
    signature = digest({"input": payload.model_dump(exclude={"request_id", "selected_groups", "preview_fingerprint"}), "groups": results,
                        "bodies": {key: [body.model_dump(mode="json"), basis] for key, (body, basis) in bodies.items()}})
    return {"groups": results, "preview_fingerprint": signature}, bodies


def confirm(db, user, payload, original, filename, *, refresh_actor):
    validate_source(payload, original)
    try:
        special.locked_actor(db, user, payload.factory_id)
        current = refresh_actor()
        if current.id != user.id:
            raise HTTPException(401, "账号已变化，请重新登录核对")
        user = current
        authorize(db, user, payload.factory_id, payload.mode)
        fingerprint, saved = special.replay(db, user, payload, "NEW_ORDER_IMPORT")
        if saved:
            for item in saved["orders"]:
                if payload.mode == "REGULAR":
                    order = db.get(CartonOrder, item["id"])
                    if order is None or order.deleted_at is not None or order.factory_id != payload.factory_id:
                        raise HTTPException(409, "原导入订单已删除，请核对历史记录")
                    ensure_customer_operation(db, user, payload.factory_id, order.customer_code)
                else:
                    special.access(db, user, payload.factory_id, item["id"])
            db.commit()
            return saved
        preview, bodies = assessment(db, user, payload, original)
        if preview["preview_fingerprint"] != payload.preview_fingerprint:
            raise HTTPException(409, "订单资料、规则或导入记录已变化，请重新校验预览")
        chosen = set(payload.selected_groups)
        if len(chosen) != len(payload.selected_groups) or chosen - {g["id"] for g in preview["groups"]}:
            raise HTTPException(422, "选择的订单分组无效")
        orders = []
        for group in preview["groups"]:
            if group["id"] not in chosen:
                continue
            if group["status"] != "READY":
                raise HTTPException(422, "所选订单还有缺项、冲突或导入记录，请先处理或取消选择该整单")
            body, basis = bodies[group["id"]]
            if payload.mode == "REGULAR":
                created = core.create_order(db, body, user, commit=False)
                core._require_order_complete(db, created)
                identifier, number, kind = created.id, created.order_no, "PURCHASE"
            else:
                body.request_id = "OI-" + digest([payload.request_id, group["id"]])
                created = special.create(db, user, body, commit=False)
                identifier, number, kind = created["id"], created["request_no"], created["kind"]
            orders.append({"id": identifier, "number": number, "kind": kind, "source_rows": group["source_rows"]})
            for n in group["source_rows"]:
                event = core._audit(db, user, payload.factory_id, "NEW_ORDER_IMPORTED", "carton_order" if payload.mode == "REGULAR" else "carton_special_request", identifier,
                    {"batch_id": payload.request_id, "filename": filename, "sha256": payload.fingerprint, "sheet": original["sheet"], "source_row": n,
                     "mapping": original["mapping"], "header_row": original["header_row"], "mode": payload.mode, "basis": basis,
                     "original": next(r for r in original["rows"] if r["source_row"] == n), "confirmed": next(r.model_dump() for r in payload.rows if r.source_row == n)})
                event.id = claim_id(payload.factory_id, payload.fingerprint, original["sheet"], n)
            db.flush()
        result = {"batch_id": payload.request_id, "count": len(orders), "orders": orders}
        event = core._audit(db, user, payload.factory_id, "NEW_ORDER_IMPORT", "carton_unified_order_batch", payload.request_id,
                            {"fingerprint": fingerprint, "response": result, "filename": filename})
        event.id = special.replay_id(user, payload)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
