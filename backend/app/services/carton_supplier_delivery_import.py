"""Preview Dongkang delivery notes and dispatch confirmed notes to factory receipt queues."""
import hashlib
from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select

from app.models.carton_procurement import CartonReceipt
from app.models.carton_supplier_portal import SupplierShipment
from app.schemas.carton_supplier_portal import ShipmentCreate
from app.services import carton_supplier_portal as portal
from app.services import carton_supplier_receipt_link as receipt_link
from app.services.carton_material_identity import material_conflicts
from app.services.carton_procurement_imports import _dongkang_identity, _parse_delivery_spreadsheet

MAX_IMPORT_ROWS = 500


def _source(filename, content):
    if not filename or len(filename) > 255 or any(char in filename for char in ('/', '\\', '\r', '\n', '\x00')):
        raise HTTPException(422, "送货单文件名无效")
    if Path(filename).suffix.lower() not in {".xls", ".xlsx"}:
        raise HTTPException(422, "请上传东康系统导出的 Excel 送货单（.xls 或 .xlsx）")
    if not content or len(content) > portal.MAX_FILE:
        raise HTTPException(422, "送货单文件不能为空且不能超过 10 MB")
    return hashlib.sha256(content).hexdigest()


def _same_text(left, right):
    return _dongkang_identity(left) == _dongkang_identity(right)


def _request_id(digest, factory_id, note_no):
    return "SUP-IMPORT-" + hashlib.sha256(f"{digest}|{factory_id}|{note_no}".encode()).hexdigest()


def preview(db, user, filename, content):
    digest = _source(filename, content)
    factories = {supplier.factory_id for supplier in portal.supplier_factories(db, user)
        if portal.supplier_permission(user, "carton_supplier:edit", supplier.factory_id)}
    if not factories:
        raise HTTPException(403, "没有可导入送货单的厂区权限")
    parsed = _parse_delivery_spreadsheet(filename, content, strict_rows=True)
    rows = parsed["rows"]
    if len(rows) > MAX_IMPORT_ROWS or parsed["warnings"]:
        raise HTTPException(422, "送货单超过单次 500 行上限，请拆分原文件后重新导入")
    if any(row.get("template") != "dongkang-delivery" for row in rows):
        raise HTTPException(422, "送货单表头不是东康系统格式，请上传原系统导出的送货明细表")
    workspaces = {factory: portal.workspace(db, user, factory) for factory in factories}
    groups = {}
    for source_row in rows:
        factory = source_row.get("destination_factory_id") or ""
        note_no = source_row.get("delivery_note_no") or ""
        key = (factory, note_no)
        group = groups.setdefault(key, {"factory_id": factory, "destination": source_row.get("destination") or "",
            "delivery_note_no": note_no, "delivery_date": source_row.get("delivery_date") or "",
            "ready": False, "issues": [], "rows": []})
        item = {field: source_row.get(field) for field in ("source_sheet", "source_row", "contract_no", "item_no",
            "packaging_type", "packaging_type_explicit", "paper_quality", "specification", "delivered_quantity")}
        item["unit"] = "个"
        item["unit_price"] = source_row.get("unit_price") or 0
        item.update(order_no="", child_no="", order_line_id="", issue_id="", status="BLOCKED", reason="")
        group["rows"].append(item)
        if factory not in factories:
            item["reason"] = "送货厂区无法识别或不在当前账号服务范围"
            continue
        if not note_no or not source_row.get("delivery_date"):
            item["reason"] = "送货单号或送货日期为空"
            continue
        if source_row["delivery_date"] != group["delivery_date"]:
            item["reason"] = "同一送货单存在不同送货日期"
            continue
        try:
            date.fromisoformat(source_row["delivery_date"])
            quantity = Decimal(str(source_row.get("delivered_quantity")))
            if not quantity.is_finite() or quantity <= 0 or quantity.as_tuple().exponent < -4:
                raise ValueError()
        except (ValueError, TypeError, InvalidOperation):
            item["reason"] = "发货数量或送货日期无效"
            continue
        if not source_row.get("item_no"):
            item["reason"] = "客户料号为空，不能安全核实纸品"
            continue
        orders = [order for order in workspaces[factory]["orders"]
            if _same_text(order["contract_no"], source_row["contract_no"])
            and _same_text(order["item_no"], source_row["item_no"])] if source_row.get("contract_no") else []
        if not orders:
            if all(source_row.get(key) not in (None, "", "待复核")
                   for key in ("packaging_type", "paper_quality", "specification")):
                item.update(status="AD_HOC_REVIEW", reason="未找到正式订单；仓库必须核实是否为确需入库的样板箱或送错货")
            else:
                item["reason"] = "未匹配订单且纸品类型、纸质或规格缺失，请核对原单"
            continue
        candidates = [(order, line) for order in orders for line in order["lines"]
            if Decimal(line["required_quantity"]) > 0]
        candidates = [(order, line) for order, line in candidates if not material_conflicts(source_row, line)]
        if len(candidates) != 1:
            item["reason"] = "合同与货号存在订单，但纸品类型/规格/材质或尺寸单位不符，请核对原单" if not candidates else "匹配到多条纸品，请核对规格与材质"
            continue
        order, line = candidates[0]
        item.update(order_no=order["order_no"], child_no=line["child_no"],
            order_line_id=line["id"], issue_id=order["issue_id"])
        item["receipt_link_eligible"] = bool(order["issue_id"] and order["status"] != "CANCELLED"
            and not order["awaiting_issue"] and not line["shipping_blocked_reason"])
        if order["status"] not in portal.OPEN_STATES or order["awaiting_issue"]:
            item["reason"] = "订单已结束或采购版本有待生成变更"
        elif any(Decimal(paper["required_quantity"]) > 0 and not paper["accepted"] for paper in order["lines"]):
            item["reason"] = "此订单尚未整单确认接单"
        elif line["shipping_blocked_reason"]:
            item["reason"] = line["shipping_blocked_reason"]
        elif quantity > Decimal(line["remaining_to_ship"]):
            item["reason"] = f"发货数量超过剩余未送 {line['remaining_to_ship']} {line['unit']}"
        else:
            item.update(status="READY", reason="已匹配")
    for group in groups.values():
        factory = group["factory_id"]
        note_no = group["delivery_note_no"]
        shipment_exists = False
        receipt_exists = False
        if factory in factories and note_no:
            shipment_exists = bool(db.scalar(select(SupplierShipment.id).where(SupplierShipment.factory_id == factory,
                SupplierShipment.delivery_note_no == note_no).limit(1)))
            receipt_exists = bool(db.scalar(select(CartonReceipt.id).where(CartonReceipt.factory_id == factory,
                CartonReceipt.delivery_note_no == note_no).limit(1)))
            if shipment_exists:
                group["issues"].append("此厂区的供应商送货单号已经登记")
        duplicates = {line_id for line_id, count in Counter(row["order_line_id"] for row in group["rows"]
            if row["order_line_id"]).items() if count > 1}
        if duplicates:
            group["issues"].append("同一送货单内重复出现同一纸品，请先在原系统合并明细")
        if len(group["rows"]) > 200:
            group["issues"].append("一张送货单最多 200 条纸品")
        group["existing_receipt_count"] = 0
        if factory in factories and note_no and not group["issues"] and all(row.get("receipt_link_eligible") for row in group["rows"]):
            by_id = {line["id"]: line | {"contract_no": order["contract_no"], "item_no": order["item_no"],
                "currency": db.get(portal.CartonOrderLine, line["id"]).currency}
                for order in workspaces[factory]["orders"] for line in order["lines"]}
            papers = [by_id[row["order_line_id"]] | {"order_line_id": row["order_line_id"], "quantity": row["delivered_quantity"]} for row in group["rows"]]
            supplier = portal.supplier_access(db, user, factory, "carton_supplier:edit")
            group["existing_receipt_count"] = len(receipt_link.matching_receipts(db, factory, supplier.id, papers, note_no=note_no))
        group["receipt_link_ready"] = group["existing_receipt_count"] > 0
        group["ready"] = bool(factory in factories and note_no and group["rows"] and not receipt_exists
            and not group["issues"] and all(row["status"] in {"READY", "AD_HOC_REVIEW"} for row in group["rows"]))
        if receipt_exists:
            group["issues"].append("此单号已有收料；后补原文件请选择仅关联已有入库")
    return {"filename": filename, "sha256": digest, "row_count": len(rows), "groups": list(groups.values())}


def confirm(db, user, filename, content, expected_sha256, selections):
    if _source(filename, content) != expected_sha256:
        raise HTTPException(409, "送货单文件与预览时不同，请重新预览")
    selections = [(item[0], item[1], item[2] if len(item) == 3 else "SHIPMENT") for item in selections]
    keys = [(factory, note) for factory, note, _ in selections]
    if not selections or len(selections) > 100 or len(keys) != len(set(keys)) or any(mode not in {"SHIPMENT", "EXISTING_RECEIPT"} for _, _, mode in selections):
        raise HTTPException(422, "请选择 1 至 100 张不重复的送货单")
    result = preview(db, user, filename, content)
    groups = {(group["factory_id"], group["delivery_note_no"]): group for group in result["groups"]}
    if any(key not in groups for key in keys):
        raise HTTPException(422, "所选送货单不在上传文件中")
    sent = []
    try:
        for factory, note_no, mode in sorted(selections):
            group = groups[(factory, note_no)]
            request_id = _request_id(expected_sha256, factory, note_no)
            existing = db.scalar(select(SupplierShipment).where(SupplierShipment.factory_id == factory,
                SupplierShipment.created_by == user.id, SupplierShipment.request_id == request_id))
            if existing:
                supplier = portal.supplier_access(db, user, factory, "carton_supplier:edit")
                if existing.supplier_id != supplier.id:
                    raise HTTPException(403, "账号无权访问此供应商的原送货单")
                import json
                evidence = db.scalar(select(portal.CartonAuditEvent).where(portal.CartonAuditEvent.entity_id == existing.id,
                    portal.CartonAuditEvent.event_type == "SUPPLIER_SHIPMENT_CREATED", portal.CartonAuditEvent.factory_id == factory))
                old_mode = json.loads(evidence.detail_json).get("registration_mode", "SHIPMENT") if evidence else "SHIPMENT"
                if old_mode != mode:
                    raise HTTPException(409, "此原文件已按另一种提交方式登记，不可改为再次发货")
                sent.append(portal.shipment_out(db, existing))
                continue
            if not group["receipt_link_ready" if mode == "EXISTING_RECEIPT" else "ready"]:
                problem = next((row["reason"] for row in group["rows"] if row["status"] == "BLOCKED"), "")
                raise HTTPException(409, f"送货单 {note_no} 无法确认：{problem or '；'.join(group['issues'])}")
            payload = ShipmentCreate(factory_id=factory, request_id=request_id, delivery_note_no=note_no,
                registration_mode=mode,
                delivery_date=date.fromisoformat(group["delivery_date"]), lines=[{
                    "order_line_id": row["order_line_id"], "issue_id": row["issue_id"],
                    "quantity": row["delivered_quantity"]} for row in group["rows"] if row["status"] == "READY" or mode == "EXISTING_RECEIPT"],
                unmatched_lines=[{"source_sheet": row["source_sheet"], "source_row": row["source_row"],
                    "contract_no": row["contract_no"] or "", "item_no": row["item_no"],
                    "packaging_type": row["packaging_type"], "paper_quality": row["paper_quality"],
                    "specification": row["specification"], "quantity": row["delivered_quantity"], "unit": row["unit"],
                    "unit_price": row["unit_price"]}
                    for row in group["rows"] if row["status"] == "AD_HOC_REVIEW"])
            sent.append(portal.create_shipment(db, user, payload, commit=False,
                source={"filename": filename, "sha256": expected_sha256,
                    "rows": [row["source_row"] for row in group["rows"]],
                    "delivery_materials": {row["order_line_id"]: {key: row.get(key) for key in (
                        "packaging_type", "packaging_type_explicit", "paper_quality", "specification", "source_sheet", "source_row")}
                        for row in group["rows"] if row["order_line_id"]},
                    "delivery_unit_prices": {row["order_line_id"]: row["unit_price"]
                        for row in group["rows"] if row["order_line_id"]}}))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"shipments": sent}
