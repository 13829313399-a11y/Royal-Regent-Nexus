"""Read-only vendor evidence matched through the existing shipment/receipt link."""
import hashlib
import json
from decimal import Decimal, DecimalException
from pydantic import ValidationError

from sqlalchemy import select
from app.models.carton_procurement import CartonReceipt, CartonReceiptLine
from app.models.carton_supplier_portal import SupplierShipment


def vendor_values(raw_price, quantity, currency):
    from app.schemas.carton_supplier_settlement import StatementLine
    from app.services.carton_supplier_settlement import money
    try:
        price = Decimal(str(raw_price)) if raw_price is not None else None
        if price is None or not price.is_finite() or price <= 0:
            return None, None, "供应商原送货单价缺失或无效，请按凭证核实"
        # Validate before quantizing: arbitrary Excel exponents must not crash a
        # read, and unsupported precision must never be silently rounded.
        StatementLine(id="validation", unit_price=price)
        amount = money(Decimal(quantity) * price)
        StatementLine(id="validation", amount=amount)
        if currency != "CNY":
            return None, None, "原送货价为 CNY，请核实本期币种及价格"
        return str(price), str(amount), ""
    except (DecimalException, ValidationError, ValueError, TypeError):
        return None, None, "原送货价超出支持范围或六位小数精度，请按凭证核实"


def build(db, factory, supplier, period, currency, rows, base_fingerprint):
    from app.services.carton_supplier_portal import _shipment_sources
    from app.services.carton_supplier_settlement import dump, _posting_date

    shipments = list(db.scalars(select(SupplierShipment).where(
        SupplierShipment.factory_id == factory, SupplierShipment.supplier_id == supplier
    ).order_by(SupplierShipment.id)))
    receipt_ids = {row["receipt_id"] for row in rows if row["kind"] == "RECEIPT"}
    receipts = {r.id: r for r in db.scalars(select(CartonReceipt).where(
        CartonReceipt.factory_id == factory, CartonReceipt.supplier_id == supplier))}
    receipt_lines = {line.id: line for line in db.scalars(select(CartonReceiptLine).where(
        CartonReceiptLine.factory_id == factory, CartonReceiptLine.receipt_id.in_(receipt_ids)))} if receipt_ids else {}
    by_receipt, evidence, unsettled = {}, [], []
    for shipment in shipments:
        receipt = receipts.get(shipment.receipt_id)
        accepted = json.loads(shipment.acceptance_json or "{}")
        acceptance_date = ((receipt.acceptance_date or accepted.get("acceptance_date")
            or (_posting_date(receipt.confirmed_at) if receipt.confirmed_at else None))
            if receipt else accepted.get("acceptance_date"))
        if not (shipment.delivery_date[:7] == period or (acceptance_date or "")[:7] == period):
            continue
        formal, unmatched = _shipment_sources(db, shipment)
        vendor_lines = []
        for line in [*formal, *unmatched]:
            snapshot = json.loads(line.snapshot_json)
            raw_price = snapshot.get("delivery_unit_price") if hasattr(line, "order_line_id") else snapshot.get("unit_price")
            # Imported Dongkang prices are explicitly CNY. Never substitute an
            # internal order/receipt price for missing vendor price evidence.
            price, amount, warning = vendor_values(raw_price, line.quantity, currency)
            vendor_lines.append({"id": line.id, "order_line_id": getattr(line, "order_line_id", None),
                "quantity": str(line.quantity), "unit_price": price, "amount": amount,
                "original_unit_price": str(raw_price) if raw_price is not None else None,
                "price_warning": warning, "currency": "CNY", "snapshot": snapshot})
        item = {"shipment_id": shipment.id, "revision": shipment.revision, "receipt_id": shipment.receipt_id,
                "document_no": shipment.delivery_note_no, "delivery_date": shipment.delivery_date,
                "acceptance_date": acceptance_date, "status": shipment.status,
                "lines": vendor_lines, "acceptance": accepted}
        evidence.append(item)
        if shipment.receipt_id:
            by_receipt.setdefault(shipment.receipt_id, []).append(item)
    enriched, suggested, matched = [], [], set()
    for source in rows:
        row = dict(source)
        vendor = None
        receipt_line = receipt_lines.get(source["source_key"].removeprefix("RECEIPT:"))
        linked = by_receipt.get(source.get("receipt_id"), [])
        if receipt_line and len(linked) == 1:
            shipment = linked[0]
            candidates = []
            for line in shipment["lines"]:
                if receipt_line.order_line_id:
                    matches = line["order_line_id"] == receipt_line.order_line_id and line["snapshot"].get("unit") == receipt_line.unit
                else:
                    snapshot = line["snapshot"]
                    matches = line["order_line_id"] is None and all(
                        str(snapshot.get(key) or (shipment["document_no"] if key == "contract_no" else "")) == getattr(receipt_line, key)
                        for key in ("contract_no", "item_no", "packaging_type", "paper_quality", "specification", "unit"))
                if matches:
                    candidates.append(line)
            if len(candidates) == 1:
                line = candidates[0]
                price = line["unit_price"]
                accepted_line = next((entry for entry in shipment["acceptance"].get("lines", [])
                    if entry["shipment_line_id"] in {line["id"], line["snapshot"].get("original_unmatched_line_id")}), {})
                matched.add((shipment["shipment_id"], line["id"]))
                vendor = {"shipment_id": shipment["shipment_id"], "line_id": line["id"],
                    "document_no": shipment["document_no"], "delivery_date": shipment["delivery_date"],
                    "quantity": line["quantity"], "unit_price": price, "currency": "CNY",
                    "amount": line["amount"], "original_unit_price": line["original_unit_price"], "price_warning": line["price_warning"],
                    "received_quantity": str(receipt_line.received_quantity), "damaged_quantity": str(receipt_line.damaged_quantity),
                    "rejected_quantity": str(receipt_line.rejected_quantity), "unusable_quantity": str(receipt_line.unusable_quantity),
                    "difference_reason": accepted_line.get("difference_reason", ""),
                    "quantity_difference": str(Decimal(line["quantity"]) - Decimal(row["quantity"])),
                    "price_difference": str(Decimal(price) - Decimal(row["unit_price"])) if price is not None and row["unit_price"] is not None else None}
        row["supplier_delivery"] = vendor
        enriched.append(row)
        suggested.append({"id": "AUTO-" + row["source_key"], "source_key": row["source_key"], "document_no": row["document_no"],
            "quantity": vendor["quantity"] if vendor else None, "unit_price": vendor["unit_price"] if vendor else None,
            "amount": vendor["amount"] if vendor else None, "approved_return_unit_price": None,
            "credit_document_no": "", "credit_date": None, "note": ""})
    # Every omitted vendor line remains visible, including an entirely rejected
    # paper on a document whose other papers produced a valid posted receipt.
    for shipment in evidence:
        receipt = receipts.get(shipment["receipt_id"])
        for line in shipment["lines"]:
            if (shipment["shipment_id"], line["id"]) in matched:
                continue
            accepted_line = next((entry for entry in shipment["acceptance"].get("lines", [])
                if entry["shipment_line_id"] in {line["id"], line["snapshot"].get("original_unmatched_line_id")}), {})
            reason = "待仓库验收" if shipment["status"] == "SENT" else "未收到或未形成有效入库"
            if shipment["acceptance"].get("registration_mode") == "EXISTING_RECEIPT" and not shipment["receipt_id"]:
                reason = "后补凭证待关联原入库，不新增应结"
            if receipt and receipt.status == "REVERSED":
                reason = "收料已冲销，待更正"
            elif receipt and receipt.status == "POSTED" and shipment["acceptance_date"] and shipment["acceptance_date"][:7] != period:
                reason = f"按验收日期计入 {shipment['acceptance_date'][:7]}"
            elif accepted_line:
                effective = Decimal(str(accepted_line.get("received_quantity") or 0)) - sum(
                    Decimal(str(accepted_line.get(key) or 0)) for key in ("damaged_quantity", "rejected_quantity", "unusable_quantity"))
                reason = "有效验收为零，不计应结" if effective <= 0 else "未关联本期有效结算来源，请核实币种及来源"
            unsettled.append({key: shipment[key] for key in ("shipment_id", "document_no", "delivery_date", "acceptance_date", "status")} | {
                "line_id": line["id"], "item_no": line["snapshot"].get("item_no", ""),
                "specification": line["snapshot"].get("specification", ""), "unit": line["snapshot"].get("unit", ""),
                "quantity": line["quantity"], "original_unit_price": line["original_unit_price"],
                "difference_reason": accepted_line.get("difference_reason", ""), "reason": reason})
    fingerprint = hashlib.sha256(dump({"base": base_fingerprint, "sources": enriched, "vendor_evidence": evidence}).encode()).hexdigest()
    return {"sources": enriched, "lines": suggested, "source_fingerprint": fingerprint, "unsettled_shipments": unsettled}
