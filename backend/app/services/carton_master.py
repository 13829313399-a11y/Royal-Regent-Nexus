"""Factory-isolated master data with immutable historical provenance."""
import hashlib
import json
from decimal import Decimal
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select
from app.models.carton_master import CartonMasterRecord as Record, CartonMasterSource as Source
from app.models.carton_procurement import CartonOrder, CartonOrderLine, CartonCustomer, CartonAuditEvent
from app.models.auth import AuthUser
from app.schemas.carton_master import MasterSave
from app.services.auth import has_permission_in_scope, build_auth_context

PERMISSION = "carton_procurement:master_manage"


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def can_manage(user, factory):
    return any(has_permission_in_scope(user, PERMISSION, factory, d) for d in ("carton", "pmc-warehouse"))


def inventory_allowed(user, factory):
    return any(has_permission_in_scope(user, "carton_procurement:inventory_write", factory, d) for d in ("carton", "pmc-warehouse"))


def warehouse_access(db, user, factory):
    # Legacy ACCESS records remain historical evidence, never an authorization fallback.
    return []


def require_manage(db, user, factory, warehouse=None):
    if can_manage(user, factory):
        return
    raise HTTPException(403, "修改基础资料需要本厂纸箱／仓管主管或仓管岗位的资料维护权限")


def canonical_lines(lines):
    result = []
    for line in lines:
        get = line.get if isinstance(line, dict) else lambda k, default="": getattr(line, k, default)
        result.append({**{k: str(get(k, "") or "").strip() for k in ("packaging_type", "paper_quality", "specification", "dimension_unit", "unit")},
                       "usage_quantity": format(Decimal(str((get("usage_quantity", 0) or 0))).normalize(), "f")})
    return sorted(result, key=encoded)


def packing_name(data, baseline):
    if baseline is None:
        return "标准装"
    def outer(config):
        lines = config.get("lines", [])
        boxes = [line for line in lines if line["packaging_type"] == "外箱"]
        return boxes[0] if len(boxes) == 1 else None
    first, current = outer(baseline), outer(data)
    composition = lambda config: sorted((l["packaging_type"], l["unit"]) for l in config.get("lines", []))
    if first and current and first["unit"] == current["unit"] and data.get("product_name") == baseline.get("product_name") and composition(data) == composition(baseline):
        a, b = Decimal(str(first["usage_quantity"])), Decimal(str(current["usage_quantity"]))
        if a != b:
            return ("大包装" if b > a else "小包装") + f"（{format(b.normalize(), 'f')}个装）"
    return "其他包装"


def ensure_packing_names(db, factory):
    first_source = {}
    for source in db.scalars(select(Source).where(Source.factory_id == factory)):
        first_source[source.record_id] = min(first_source.get(source.record_id, source.occurred_at), source.occurred_at)
    groups = {}
    rows = list(db.scalars(select(Record).where(Record.factory_id == factory, Record.kind == "CONFIG")))
    for row in sorted(rows, key=lambda r: (first_source.get(r.id, r.updated_at), r.id)):
        groups.setdefault(row.code, []).append(row)
    for rows in groups.values():
        standard = next((r for r in rows if json.loads(r.data_json).get("packing_name") == "标准装"), rows[0])
        base = json.loads(standard.data_json)
        for row in rows:
            data = json.loads(row.data_json)
            name = packing_name(data, None if row.id == standard.id else base)
            if data.get("packing_name") != name:
                data["packing_name"] = name
                row.data_json = encoded(data)
                row.revision += 1


def record_out(row, sources=()):
    return {"id": row.id, "kind": row.kind, "customer_code": row.customer_code, "code": row.code,
            "data": json.loads(row.data_json), "status": row.status, "preferred": bool(row.preferred),
            "revision": row.revision, "maintained": bool(row.maintained), "updated_at": row.updated_at,
            "sources": [json.loads(s.snapshot_json) for s in sources]}


def sync_history(db, factory):
    """Caller holds the factory lock. No pagination limit and no business-row mutation."""
    from app.services.carton_procurement import now_text
    db.flush()
    records = {(r.kind, r.identity): r for r in db.scalars(select(Record).where(Record.factory_id == factory))}
    source_rows = list(db.scalars(select(Source).where(Source.factory_id == factory)))
    sources = {(s.record_id, s.order_id, s.signature) for s in source_rows}
    by_id = {r.id: r for r in records.values()}
    # Both original and corrected configurations identify the same maintained item.
    # Provenance also retains intermediate configurations encountered in formal orders.
    for row in sorted(by_id.values(), key=lambda r: (r.maintained, r.updated_at)):
        if row.kind == "CONFIG":
            data = json.loads(row.data_json)
            semantic = {"product_name": data.get("product_name", ""), "lines": canonical_lines(data.get("lines", []))}
            records[("CONFIG", digest([row.code, semantic]))] = row
    for source in source_rows:
        row = by_id.get(source.record_id)
        if row and row.kind == "CONFIG":
            data = json.loads(source.snapshot_json)["configuration"]
            records.setdefault(("CONFIG", digest([row.code, data])), row)
    # Confirmed supplier orders plus explicitly accepted historical imports; OCR/drafts are excluded.
    imported = set(db.scalars(select(CartonAuditEvent.entity_id).where(CartonAuditEvent.factory_id == factory,
        CartonAuditEvent.event_type.in_(["HISTORY_ORDER_IMPORTED", "ORDER_SUBMITTED_SUPPLIER"]))))
    orders = [o for o in db.scalars(select(CartonOrder).where(CartonOrder.factory_id == factory))
              if o.status in {"PENDING_SUPPLIER", "PARTIALLY_RECEIVED", "COMPLETED"} or o.id in imported]
    lines = {}
    for line in db.scalars(select(CartonOrderLine).where(CartonOrderLine.factory_id == factory)):
        lines.setdefault(line.order_id, []).append(line)
    added = 0
    for order in orders:
        config = {"product_name": order.product_name, "lines": canonical_lines(lines.get(order.id, []))}
        for kind, code, data, identity in (
            ("CONFIG", order.item_no, config, digest([order.item_no, config])),
            ("CONTRACT", order.contract_no, {"item_nos": [order.item_no]}, digest([order.customer_code, order.contract_no])),
        ):
            if kind == "CONFIG" and (not lines.get(order.id) or any(line.usage_quantity is None or line.required_quantity <= 0 or not line.paper_quality or not line.specification for line in lines[order.id])):
                continue
            key = (kind, identity)
            row = records.get(key)
            if row is None:
                row = Record(id="CMD-" + uuid4().hex, factory_id=factory, kind=kind, identity=identity,
                             customer_code=order.customer_code if kind == "CONTRACT" else "", code=code, data_json=encoded(data), updated_at=now_text())
                db.add(row); db.flush(); records[key] = row; added += 1
            # The immutable identity remains the original signature even after privileged edits.
            # Never replace edited content, status or preferred choices during a scan.
            if kind == "CONTRACT" and not row.maintained:
                old = json.loads(row.data_json)
                old["item_nos"] = sorted(set(old.get("item_nos", [])) | {order.item_no})
                if encoded(old) != row.data_json:
                    row.data_json = encoded(old); row.revision += 1
            signature = digest([data, order.customer_po]) if order.customer_po else digest(data)
            if (row.id, order.id, signature) not in sources:
                evidence = {"order_no": order.order_no, "order_date": order.order_date,
                            "contract_no": order.contract_no, "customer_po": order.customer_po, "item_no": order.item_no, "customer_code": order.customer_code, "configuration": data}
                db.add(Source(id="CMS-" + uuid4().hex, factory_id=factory, record_id=row.id, order_id=order.id,
                              signature=signature, snapshot_json=encoded(evidence), occurred_at=order.updated_at))
                sources.add((row.id, order.id, signature))
    db.flush()
    ensure_packing_names(db, factory)
    db.flush()
    return added


def workspace(db, factory, user):
    from app.services.carton_procurement import _lock_receipt_factory
    from app.services.carton_positions import locations
    _lock_receipt_factory(db, factory)
    sync_history(db, factory)
    db.commit()
    provenance = {}
    for source in db.scalars(select(Source).where(Source.factory_id == factory).order_by(Source.occurred_at.desc())):
        provenance.setdefault(source.record_id, []).append(source)
    rows = list(db.scalars(select(Record).where(Record.factory_id == factory).order_by(Record.preferred.desc(), Record.updated_at.desc())))
    admin = can_manage(user, factory)
    users = []
    if admin:
        for candidate in db.scalars(select(AuthUser).where(AuthUser.status == "active")):
            if inventory_allowed(build_auth_context(db, candidate), factory):
                users.append({"id": candidate.id, "name": candidate.display_name or candidate.username})
    # Saved pending orders contribute scalar suggestions without enrolling configurations.
    paper_history = {}
    for field in ("packaging_type", "paper_quality", "specification"):
        column = getattr(CartonOrderLine, field)
        values = db.scalars(select(column).join(CartonOrder, CartonOrder.id == CartonOrderLine.order_id)
                            .where(CartonOrder.factory_id == factory, CartonOrderLine.factory_id == factory,
                                   CartonOrder.status != "CANCELLED").distinct().order_by(column))
        paper_history[field] = list(dict.fromkeys(value.strip() for value in values if value and value.strip()))
    return {"can_manage": admin, "warehouses": warehouse_access(db, user, factory),
            "records": [record_out(r, provenance.get(r.id, [])) for r in rows if r.kind != "ACCESS" or admin],
            "paper_history": paper_history, "locations": locations(db, factory),
            "users": users}


def save_record(db, user, payload: MasterSave, identifier=""):
    from app.services.carton_procurement import _lock_receipt_factory, _audit, now_text
    factory = payload.factory_id
    _lock_receipt_factory(db, factory)
    require_manage(db, user, factory)
    if payload.kind == "ACCESS":
        raise HTTPException(422, "已取消单独仓库授权，请按仓管或主管岗位维护本厂资料")
    data = payload.data.model_dump(mode="json")
    if payload.kind == "CONTRACT" and not payload.customer_code:
        raise HTTPException(422, "请选择客户")
    if payload.customer_code and not db.scalar(select(CartonCustomer.id).where(CartonCustomer.factory_id == factory, CartonCustomer.customer_code == payload.customer_code)):
        raise HTTPException(422, "客户不属于当前工厂")
    if payload.kind != "RULE" and not payload.code:
        raise HTTPException(422, "请填写编号或名称")
    if payload.kind == "CONFIG":
        if not data["lines"]:
            raise HTTPException(422, "货号资料至少需要一行纸品")
        data["lines"] = canonical_lines(data["lines"])
    if payload.kind == "CONTRACT":
        if any(not x.strip() or len(x) > 128 for x in data["item_nos"]):
            raise HTTPException(422, "合同货号不能为空且不能超过 128 字")
        data["item_nos"] = sorted(set(x.strip() for x in data["item_nos"]))
    if payload.kind == "ACCESS":
        user_row = db.get(AuthUser, payload.code)
        if not user_row or user_row.status != "active":
            raise HTTPException(422, "请选择有效人员")
        if not inventory_allowed(build_auth_context(db, user_row), factory):
            raise HTTPException(422, "该人员没有本厂库存业务权限，不能授予仓库维护范围")
        if any(not x.strip() or len(x.strip()) > 64 for x in data["warehouses"]):
            raise HTTPException(422, "仓库名称不能为空且不能超过 64 字")
        data["warehouses"] = sorted(set(x.strip().upper() for x in data["warehouses"]))
    semantic = {"product_name": data["product_name"], "lines": data["lines"]}
    identity = digest([payload.code, semantic]) if payload.kind == "CONFIG" else digest([payload.customer_code, payload.code if payload.kind != "RULE" else ""])
    row = db.get(Record, identifier) if identifier else None
    if identifier and (not row or row.factory_id != factory):
        raise HTTPException(404, "基础资料不存在")
    if payload.kind == "CONFIG":
        old_data = json.loads(row.data_json) if row else {}
        data["packing_name"] = old_data.get("packing_name", "")
        old_semantic = {"product_name": old_data.get("product_name", ""), "lines": canonical_lines(old_data.get("lines", []))}
        for existing in db.scalars(select(Record).where(Record.factory_id == factory, Record.kind == "CONFIG",
                Record.code == payload.code)):
            previous = json.loads(existing.data_json)
            current = {"product_name": previous.get("product_name", ""), "lines": canonical_lines(previous.get("lines", []))}
            if existing.id != identifier and current == semantic and (not row or old_semantic != semantic):
                raise HTTPException(409, "相同包装配置已经存在，请维护原记录；停用配置不会自动重建")
    if row:
        if row.revision != payload.expected_revision:
            raise HTTPException(409, "资料已更新，请刷新后重试")
        if row.kind != payload.kind or (row.kind != "CONFIG" and row.customer_code != payload.customer_code) or (row.code != payload.code and row.kind != "WORKSHOP"):
            raise HTTPException(422, "客户及编号是资料身份；请新建资料并停用旧项，不能覆盖归属")
        before = record_out(row)
        if row.kind == "WORKSHOP" and row.code != payload.code:
            if db.scalar(select(Record.id).where(Record.factory_id == factory, Record.kind == "WORKSHOP", Record.code == payload.code, Record.id != row.id)):
                raise HTTPException(409, "本厂已有同名车间")
            row.code = payload.code
            row.identity = identity
    else:
        if db.scalar(select(Record.id).where(Record.factory_id == factory, Record.kind == payload.kind, Record.identity == identity)):
            raise HTTPException(409, "该资料已存在，请修改现有记录")
        before = None
        row = Record(id="CMD-" + uuid4().hex, factory_id=factory, kind=payload.kind, identity=identity,
                     customer_code="" if payload.kind == "CONFIG" else payload.customer_code, code=payload.code, revision=0)
        db.add(row)
    row.data_json = encoded(data); row.status = payload.status; row.preferred = int(payload.preferred)
    row.maintained = 1; row.revision += 1; row.updated_at = now_text()
    if row.preferred and row.kind == "CONFIG" and row.status == "ACTIVE":
        for other in db.scalars(select(Record).where(Record.factory_id == factory, Record.kind == "CONFIG",
                Record.code == row.code, Record.id != row.id, Record.preferred == 1)):
            other.preferred = 0; other.revision += 1
    db.flush()
    ensure_packing_names(db, factory)
    db.flush()
    _audit(db, user, factory, "MASTER_DATA_SAVED", "carton_master", row.id,
           {"reason": payload.reason, "before": before, "after": record_out(row)})
    db.commit()
    return record_out(row)


def due_rules(db, factory, customer):
    rows = list(db.scalars(select(Record).where(Record.factory_id == factory, Record.kind == "RULE", Record.status == "ACTIVE",
                                               Record.customer_code.in_(["", customer]))))
    result = {"lead_days": 3, "customer_days": None, "contract_rule": {}, "item_rule": {}, "customer_po_rule": {}, "revision": ""}
    for row in sorted(rows, key=lambda r: bool(r.customer_code)):
        data = json.loads(row.data_json)
        for key in ("lead_days", "customer_days"):
            if data.get(key) is not None:
                result[key] = data[key]
        if data.get("customer_days_disabled"):
            result["customer_days"] = None
        if row.customer_code:
            result.update({key: data.get(key, {}) for key in ("contract_rule", "item_rule", "customer_po_rule")})
        result["revision"] += f"{row.id}:{row.revision};"
    return result


def number_warnings(rules, contract, item, customer_po=""):
    from app.services.carton_number_templates import matches_template
    warnings = []
    for key, name, value in (("contract_rule", "合同号", contract), ("item_rule", "货号", item), ("customer_po_rule", "客户 PO", customer_po)):
        if key == "customer_po_rule" and not value:
            continue
        rule = rules.get(key, {})
        if rule.get("mode", "OFF") == "OFF":
            continue
        if rule.get("frozen") and rule.get("templates"):
            if not any(matches_template(t, value) for t in rule["templates"]):
                warnings.append({"message": f"{name}与已保存的客户格式不同，请核对", "blocking": rule.get("mode") == "BLOCK"})
            continue
        # Legacy automatic rules have no approved snapshot and must not learn while ordering.
        if rule.get("mode") == "AUTO":
            continue
        invalid = not value.startswith(rule.get("prefix", "")) or not rule.get("min_length", 0) <= len(value) <= rule.get("max_length", 128)
        if rule.get("characters") == "DIGITS":
            invalid |= not value.isascii() or not value.isdigit()
        if rule.get("characters") == "ALNUM_DASH":
            invalid |= any(not (c.isascii() and c.isalnum()) and c not in "-_" for c in value)
        if invalid:
            warnings.append({"message": f"{name}与客户编号格式不同，请核对前缀、长度及字符", "blocking": rule.get("mode") == "BLOCK"})
    return warnings


def validate_order(db, factory, customer, contract, item, *, customer_po="", config_id="", config_revision=0):
    stopped_contract = db.scalar(select(Record.id).where(Record.factory_id == factory, Record.kind == "CONTRACT",
        Record.customer_code == customer, Record.code == contract, Record.status == "INACTIVE"))
    if stopped_contract:
        raise HTTPException(422, "该合同已停用，请核对合同号或联系主管")
    rules = due_rules(db, factory, customer)
    errors = [w["message"] for w in number_warnings(rules, contract, item, customer_po) if w["blocking"]]
    if errors:
        raise HTTPException(422, "；".join(errors))
    if config_id:
        row = db.get(Record, config_id)
        if not row or row.factory_id != factory or row.kind != "CONFIG" or row.code != item:
            raise HTTPException(422, "所选货号资料与工厂或货号不对应")
        if row.status != "ACTIVE" or row.revision != config_revision:
            raise HTTPException(409, "所选基础资料已修改或停用，请重新核对并选择")
    return rules


def update_location(db, user, identifier, payload):
    from app.services.carton_positions import get_location, location_out, unknown_id
    from app.services.carton_procurement import _lock_receipt_factory, _audit
    from app.models.carton_positions import CartonLocation
    _lock_receipt_factory(db, payload.factory_id)
    row = get_location(db, payload.factory_id, identifier)
    if row.id == unknown_id(payload.factory_id):
        raise HTTPException(422, "系统待核仓位不可修改，请使用调仓")
    require_manage(db, user, payload.factory_id, row.warehouse)
    require_manage(db, user, payload.factory_id, payload.warehouse)
    if row.revision != payload.expected_revision:
        raise HTTPException(409, "仓位资料已修改，请刷新后重试")
    warehouse, bin_code = payload.warehouse.upper(), payload.bin_code.upper()
    if not bin_code and row.bin_code:
        raise HTTPException(422, "请填写仓位编号")
    duplicate = db.scalar(select(CartonLocation.id).where(CartonLocation.factory_id == payload.factory_id,
        CartonLocation.warehouse == warehouse, CartonLocation.bin_code == bin_code, CartonLocation.id != identifier))
    if duplicate:
        raise HTTPException(409, "本仓库已存在相同仓位")
    before = location_out(row)
    row.warehouse = warehouse; row.bin_code = bin_code; row.status = payload.status; row.revision += 1
    _audit(db, user, payload.factory_id, "MASTER_LOCATION_UPDATED", "carton_location", row.id,
           {"reason": payload.reason, "before": before, "after": location_out(row)})
    db.commit()
    return location_out(row)


def workshop_snapshot(db, factory, identifier):
    if not identifier:
        return ""
    row = db.get(Record, identifier)
    if not row or row.factory_id != factory or row.kind != "WORKSHOP" or row.status != "ACTIVE":
        raise HTTPException(422, "领用车间已停用或不属于当前工厂")
    return row.code


def save_warehouse(db, user, payload, *, rename=False):
    from app.models.carton_positions import CartonLocation
    from app.services.carton_positions import create_location, location_out, unknown_id
    from app.services.carton_procurement import _lock_receipt_factory, _audit, now_text
    factory = payload.factory_id
    _lock_receipt_factory(db, factory)
    require_manage(db, user, factory)  # Whole warehouse changes require master permission.
    old = payload.warehouse.upper()
    name = payload.new_name.upper() if rename else old
    if "待核仓位" in {old, name}:
        raise HTTPException(422, "待核仓位由系统保留，请调仓后使用正式仓库")
    rows = list(db.scalars(select(CartonLocation).where(CartonLocation.factory_id == factory, CartonLocation.warehouse == old)))
    if any(row.id == unknown_id(factory) for row in rows):
        raise HTTPException(422, "系统待核仓位不可修改，请使用调仓")
    if not rename:
        if rows:
            raise HTTPException(409, "该仓库已存在，请在仓库旁添加仓位")
        row = create_location(db, factory, name, payload.bin_code)
        _audit(db, user, factory, "INVENTORY_LOCATION_CREATED", "carton_location", row.id,
               {**location_out(row), "reason": payload.reason})
        db.commit()
        return [location_out(row)]
    if not rows:
        raise HTTPException(404, "仓库不存在，请刷新资料")
    if {r.id: r.revision for r in rows} != payload.expected_locations:
        raise HTTPException(409, "仓库或仓位资料已变化，请刷新后重新修改")
    if name != old and db.scalar(select(CartonLocation.id).where(CartonLocation.factory_id == factory, CartonLocation.warehouse == name)):
        raise HTTPException(409, "目标仓库名称已存在，不能通过更名合并仓库")
    grants = list(db.scalars(select(Record).where(Record.factory_id == factory, Record.kind == "ACCESS")))
    if name != old:
        for row in rows:
            before = location_out(row)
            row.warehouse = name
            row.revision += 1
            _audit(db, user, factory, "MASTER_LOCATION_UPDATED", "carton_location", row.id,
                   {"reason": payload.reason, "before": before, "after": location_out(row)})
        # Grants follow the same physical warehouse; no new warehouse access is added.
        for grant in grants:
            before = json.loads(grant.data_json)
            if old not in before.get("warehouses", []):
                continue
            after = {**before, "warehouses": sorted({name if w == old else w for w in before["warehouses"]})}
            grant.data_json = encoded(after); grant.revision += 1; grant.updated_at = now_text()
            _audit(db, user, factory, "MASTER_DATA_SAVED", "carton_master", grant.id,
                   {"reason": payload.reason, "before": before, "after": after, "warehouse_rename": True})
    db.commit()
    return [location_out(row) for row in rows]


def _warehouse_has_history(db, factory, rows):
    """Check immutable use, not net stock; legacy labels survive catalog renames."""
    from app.models.carton_positions import CartonPositionEntry
    from app.models.carton_procurement import CartonReceiptLine, CartonInventoryMovement
    from app.models.carton_stocktake import CartonStocktakeLine
    from app.services.carton_positions import location_out
    identifiers = {row.id for row in rows}
    if db.scalar(select(CartonPositionEntry.id).where(CartonPositionEntry.factory_id == factory,
            CartonPositionEntry.location_id.in_(identifiers)).limit(1)) is not None:
        return "已有库存流水或调仓历史"

    def normalized(value):
        return "/".join(part.strip() for part in str(value or "").strip().upper().replace("／", "/").split("/"))

    labels, warehouses = set(), set()

    def remember(snapshot):
        if isinstance(snapshot, dict) and snapshot.get("id") in identifiers:
            warehouses.add(normalized(snapshot.get("warehouse")))
            labels.add(normalized(snapshot.get("label")))
            if snapshot.get("warehouse") and snapshot.get("bin_code"):
                labels.add(normalized(snapshot["warehouse"] + "/" + snapshot["bin_code"]))

    for row in rows:
        remember(location_out(row))
    events = list(db.scalars(select(CartonAuditEvent).where(CartonAuditEvent.factory_id == factory)))
    for event in events:
        if event.entity_type == "carton_location" and event.entity_id in identifiers:
            detail = json.loads(event.detail_json)
            remember(detail)
            remember(detail.get("before"))
            remember(detail.get("after"))
    labels.discard(""); warehouses.discard("")

    def refers(value):
        if isinstance(value, list):
            return any(refers(item) for item in value)
        if not isinstance(value, dict):
            return False
        for key, item in value.items():
            if key in {"location_id", "from_location_id", "to_location_id"} and isinstance(item, str) and item in identifiers:
                return True
            if key in {"location", "latest_location", "from_location", "to_location", "label"} and normalized(item) in labels | warehouses:
                return True
            if key == "warehouse" and normalized(item) in warehouses:
                return True
            if key == "position_key" and isinstance(item, str):
                try:
                    position = json.loads(item)
                except (TypeError, ValueError):
                    position = None
                if isinstance(position, list) and len(position) == 2 and isinstance(position[1], str) and position[1] in identifiers:
                    return True
            if isinstance(item, (dict, list)) and refers(item):
                return True
        return False

    # Draft, voided and posted receipt lines all remain business evidence.
    for row in db.scalars(select(CartonReceiptLine).where(CartonReceiptLine.factory_id == factory)):
        if refers({"location": row.location, "allocations": json.loads(row.location_allocations_json or "[]")}):
            return "已被收料单引用（包括未入库或已作废单据）"
    for row in db.scalars(select(CartonInventoryMovement).where(CartonInventoryMovement.factory_id == factory)):
        if refers({"location": row.location}):
            return "已有历史库存流水"
    for row in db.scalars(select(CartonStocktakeLine).where(CartonStocktakeLine.factory_id == factory)):
        if refers(json.loads(row.snapshot_json)) or refers({"position_key": row.inventory_key}):
            return "已有盘点记录（包括已取消盘点）"
    for event in events:
        # Catalog editing and grant changes do not count as business use.
        if event.entity_type in {"carton_location", "carton_warehouse", "carton_master"}:
            continue
        if refers(json.loads(event.detail_json)):
            return "已有业务操作历史引用"
    return ""


def delete_warehouse(db, user, payload):
    from app.models.carton_positions import CartonLocation
    from app.services.carton_positions import location_out, unknown_id
    from app.services.carton_procurement import _lock_receipt_factory, _audit, now_text
    factory, warehouse = payload.factory_id, payload.warehouse.upper()
    _lock_receipt_factory(db, factory)
    require_manage(db, user, factory)
    rows = list(db.scalars(select(CartonLocation).where(CartonLocation.factory_id == factory,
        CartonLocation.warehouse == warehouse)))
    if warehouse == "待核仓位" or any(row.id == unknown_id(factory) for row in rows):
        raise HTTPException(422, "系统待核仓位不可删除，请使用调仓")
    if not rows:
        raise HTTPException(404, "仓库不存在，请刷新资料")
    if {row.id: row.revision for row in rows} != payload.expected_locations:
        raise HTTPException(409, "仓库或仓位资料已变化，请刷新后重新核对删除范围")
    reason = _warehouse_has_history(db, factory, rows)
    if reason:
        raise HTTPException(409, f"该仓库{reason}，不能删除；请保留并停用仓位")
    before = [location_out(row) for row in rows]
    # Name-based permissions must not be inherited if a new warehouse reuses this name.
    for grant in db.scalars(select(Record).where(Record.factory_id == factory, Record.kind == "ACCESS")):
        data = json.loads(grant.data_json)
        if warehouse not in data.get("warehouses", []):
            continue
        previous = record_out(grant)
        grant.data_json = encoded({**data, "warehouses": [name for name in data["warehouses"] if name != warehouse]})
        grant.revision += 1
        grant.updated_at = now_text()
        _audit(db, user, factory, "MASTER_DATA_SAVED", "carton_master", grant.id,
               {"reason": payload.reason, "before": previous, "after": record_out(grant), "warehouse_deleted": warehouse})
    for row in rows:
        db.delete(row)
    _audit(db, user, factory, "MASTER_WAREHOUSE_DELETED", "carton_warehouse", "CWH-" + digest([factory, warehouse]),
           {"reason": payload.reason, "warehouse": warehouse, "before": before, "after": [], "deleted_location_count": len(rows)})
    db.commit()
    return {"deleted": True}
