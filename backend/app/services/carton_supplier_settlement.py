"""Supplier reconciliation uses receipt prices, never inventory carrying costs.

Confirmed versions are immutable. Reopening creates a new draft and retains the
prior statement and all comparison evidence. All writes share the carton lock.
"""
from __future__ import annotations
import hashlib
import json
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select
from app.models.carton_procurement import CartonReceipt, CartonReceiptLine, CartonInventoryMovement, CartonOrder, CartonOrderLine, CartonAuditEvent
from app.models.carton_supplier_settlement import CartonSupplierSettlement
from app.services import carton_procurement as core
from app.services.carton_ledger_time import ledger_time


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def money(value):
    return Decimal(value).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)


def _posting_date(value):
    """Legacy UTC/offset timestamps belong to the Shanghai business date."""
    return ledger_time(value).date().isoformat()


def date_check(value):
    if value > _posting_date(core.now_text()):
        raise HTTPException(422, "实际验收日期不能晚于今天")


def ensure_open(db, factory, supplier, period):
    if db.scalar(select(CartonSupplierSettlement.id).where(
        CartonSupplierSettlement.factory_id == factory,
        CartonSupplierSettlement.supplier_id == supplier,
        CartonSupplierSettlement.period == period,
        CartonSupplierSettlement.status == "CONFIRMED",
    )):
        raise HTTPException(409, "该供应商月份已确认对账，请先说明原因并重新核对，再更正来源单据")


def receipt_guard(db, receipt):
    if receipt.status != "POSTED":
        return
    day = receipt.acceptance_date or (_posting_date(receipt.confirmed_at) if receipt.confirmed_at else "")
    if day:
        ensure_open(db, receipt.factory_id, receipt.supplier_id, day[:7])


def movement_guard(db, movement, *, return_date=None):
    if movement.source_type == "RECEIPT":
        receipt = db.get(CartonReceipt, movement.source_id)
        if receipt:
            receipt_guard(db, receipt)
    elif movement.source_type == "ORDER_RETURN" or (movement.movement_type == "OUTBOUND" and movement.issue_kind == "RETURN"):
        supplier = return_supplier(db, movement)
        from app.services.carton_return_dates import dates
        period = (return_date or dates(db, movement.factory_id).get(movement.id) or _posting_date(movement.occurred_at))[:7]
        if supplier:
            ensure_open(db, movement.factory_id, supplier, period)
        elif db.scalar(select(CartonSupplierSettlement.id).where(
            CartonSupplierSettlement.factory_id == movement.factory_id,
            CartonSupplierSettlement.period == period,
            CartonSupplierSettlement.status == "CONFIRMED")):
            raise HTTPException(409, "退货尚未明确供应商，且本月已有供应商确认对账，请先核实来源")


def return_supplier(db, movement):
    if movement.source_type == "SPECIAL_RETURN":
        event = db.scalar(select(CartonAuditEvent).where(CartonAuditEvent.factory_id == movement.factory_id,
            CartonAuditEvent.event_type == "SPECIAL_STOCK_SOURCE_LINKED", CartonAuditEvent.entity_id == movement.id))
        if not event: return None
        data = json.loads(event.detail_json)
        line = db.get(CartonReceiptLine, data.get("receipt_line_id"))
        receipt = db.get(CartonReceipt, line.receipt_id) if line and line.factory_id == movement.factory_id else None
        return receipt.supplier_id if receipt and receipt.factory_id == movement.factory_id and receipt.supplier_id == data.get("supplier_id") else None
    from app.services.carton_order_split import target_origin
    split = target_origin(db, movement.factory_id, movement.order_line_id)
    if split:
        return split[0]["supplier_id"]
    if movement.order_line_id:
        line = db.get(CartonOrderLine, movement.order_line_id)
        order = db.get(CartonOrder, line.order_id) if line and line.factory_id == movement.factory_id else None
        if order is None or order.factory_id != movement.factory_id:
            return None
        receipt_suppliers = set(db.scalars(select(CartonReceipt.supplier_id).join(CartonReceiptLine,
            (CartonReceiptLine.receipt_id == CartonReceipt.id) & (CartonReceiptLine.factory_id == CartonReceipt.factory_id)).where(
            CartonReceipt.factory_id == movement.factory_id, CartonReceipt.status == "POSTED",
            CartonReceiptLine.order_line_id == movement.order_line_id)))
        return order.supplier_id if not receipt_suppliers or receipt_suppliers == {order.supplier_id} else None
    candidates = set(db.scalars(select(CartonReceipt.supplier_id).join(CartonReceiptLine,
        (CartonReceiptLine.receipt_id == CartonReceipt.id) & (CartonReceiptLine.factory_id == CartonReceipt.factory_id)).where(
        CartonReceipt.factory_id == movement.factory_id, CartonReceipt.status == "POSTED",
        *[getattr(CartonReceiptLine, key) == getattr(movement, key) for key in (
            "customer_code", "contract_no", "item_no", "packaging_type", "paper_quality", "specification", "unit")])))
    return next(iter(candidates)) if len(candidates) == 1 else None


def sources(db, factory, supplier, period, currency):
    from app.services import carton_return_dates
    return_evidence = carton_return_dates.evidence(db, factory)
    return_dates = {key: value["return_date"] for key, value in return_evidence.items()}
    from app.services.carton_replenishment_receipts import receipt_links, legacy_review_lines
    replacements = receipt_links(db, factory)
    receipts = list(db.scalars(select(CartonReceipt).where(
        CartonReceipt.factory_id == factory, CartonReceipt.supplier_id == supplier,
        CartonReceipt.status.in_(["POSTED", "REVERSED"]))))
    receipt_by_id = {r.id: r for r in receipts}
    movements = list(db.scalars(select(CartonInventoryMovement).where(CartonInventoryMovement.factory_id == factory)))
    reversed_ids = {m.reversal_of_movement_id for m in movements if m.reversal_of_movement_id}
    incoming = {m.source_line_id: m for m in movements if m.source_type == "RECEIPT"}
    prices = {}
    for event in db.scalars(select(CartonAuditEvent).where(CartonAuditEvent.factory_id == factory,
                                                         CartonAuditEvent.event_type.in_(["INVENTORY_PRICE_CONFIRMED", "INVENTORY_PRICE_CORRECTED"]))
            .order_by(CartonAuditEvent.sequence)):
        prices[event.entity_id] = Decimal(str(json.loads(event.detail_json)["unit_price"]))
    lines = list(db.scalars(select(CartonReceiptLine).where(CartonReceiptLine.factory_id == factory,
                    CartonReceiptLine.receipt_id.in_(list(receipt_by_id))))) if receipt_by_id else []
    legacy_replacements = legacy_review_lines(db, factory, [line.order_line_id for line in lines if line.order_line_id])
    result, undated, issues = [], [], []
    for receipt in receipts:
        if receipt.status != "POSTED":
            continue  # Whole-receipt reversal corrects the original, it is not a supplier return.
        if not receipt.acceptance_date and any(line.receipt_id == receipt.id and line.effective_quantity > 0
                and replacements.get(line.id, {}).get("responsibility") != "SUPPLIER" for line in lines):
            undated.append({"receipt_id": receipt.id, "revision": receipt.revision,
                            "document_no": receipt.delivery_note_no, "confirmed_at": receipt.confirmed_at,
                            "acceptance_date": None})
    for line in lines:
        if replacements.get(line.id, {}).get("responsibility") == "SUPPLIER":
            continue  # Free replacement restores inventory cost but creates no supplier payable.
        receipt = receipt_by_id[line.receipt_id]
        day = receipt.acceptance_date or (_posting_date(receipt.confirmed_at) if receipt.confirmed_at else "")
        if receipt.status != "POSTED" or day[:7] != period or core.normalize_currency(line.currency) != currency or line.effective_quantity <= 0:
            continue
        movement = incoming.get(line.id)
        row_issues = []
        if line.order_line_id in legacy_replacements:
            row_issues.append("该纸品有未关联补单的历史收料，请先核对责任及计费来源")
        if line.order_line_id:
            order_line = db.get(CartonOrderLine, line.order_line_id)
            order = db.get(CartonOrder, order_line.order_id) if order_line and order_line.factory_id == factory else None
            if order is None or order.factory_id != factory or order.supplier_id != receipt.supplier_id:
                row_issues.append("历史收料供应商与关联订单不一致，须核实来源")
        if not receipt.acceptance_date:
            row_issues.append("历史记录仅有确认日期，请核实实际验收日期")
        if movement is None or movement.id in reversed_ids or movement.quantity != line.effective_quantity:
            row_issues.append("收料与有效入库流水不一致")
        elif Decimal(movement.unit_price) != Decimal(line.unit_price):
            row_issues.append("收料单价与原入库单价不一致，请核实历史凭据")
        price = prices.get(movement.id, Decimal(line.unit_price)) if movement else Decimal(line.unit_price)
        if price == 0 and (movement is None or movement.id not in prices):
            row_issues.append("入库单价待核实")
            price = None
        result.append({"source_key": "RECEIPT:" + line.id, "kind": "RECEIPT", "receipt_id": receipt.id,
            "receipt_revision": receipt.revision, "document_no": receipt.delivery_note_no,
            "acceptance_date": receipt.acceptance_date, "legacy_confirmation_date": None if receipt.acceptance_date else day,
            "date_basis": "ACCEPTANCE" if receipt.acceptance_date else "LEGACY_CONFIRMATION",
            **{key: getattr(line, key) for key in ("customer_name", "contract_no", "item_no", "packaging_type", "paper_quality", "specification", "unit")},
            "quantity": str(line.effective_quantity), "unit_price": str(price) if price is not None else None,
            "amount": str(money(line.effective_quantity * price)) if price is not None else None,
            "currency": currency, "issues": row_issues})
    for movement in movements:
        if not (movement.source_type == "ORDER_RETURN" or (movement.movement_type == "OUTBOUND" and movement.issue_kind == "RETURN")) or movement.id in reversed_ids:
            continue
        posting_date = _posting_date(movement.occurred_at)
        actual_date = return_dates.get(movement.id)
        return_day = actual_date or posting_date
        if return_day[:7] != period or core.normalize_currency(movement.currency) != currency:
            continue
        matched_supplier = return_supplier(db, movement)
        if matched_supplier is None:
            issues.append(f"退货 {movement.document_no} 无法确定唯一供应商，请核实原收料及订单归属")
            continue
        if matched_supplier != supplier:
            continue
        result.append({"source_key": "RETURN:" + movement.id, "kind": "RETURN", "receipt_id": None,
            "document_no": movement.document_no, "acceptance_date": return_day, "date_basis": "RETURN_ACTUAL" if actual_date else "RETURN_POSTING",
            **({"return_date": actual_date, "posting_date": posting_date} if actual_date else {}),
            **({"return_date_revision": return_evidence[movement.id]["revision"],
                "return_date_evidence_fingerprint": return_evidence[movement.id]["fingerprint"]}
                if return_evidence.get(movement.id, {}).get("revision", 0) >= 2 else {}),
            **{key: getattr(movement, key) for key in ("customer_name", "contract_no", "item_no", "packaging_type", "paper_quality", "specification", "unit")},
            "quantity": str(-movement.quantity), "unit_price": None, "amount": None, "currency": currency,
            "issues": [], "reason": movement.reason})
    from app.services.carton_return_collaboration import financial_sources
    financial_sources(db, factory, supplier, period, currency, result, issues)
    # Unknown dates can belong to any month. Do not silently omit historical debt.
    if undated:
        issues.append(f"有 {len(undated)} 张历史收料单未核实实际验收日期，请先补齐日期")
    from app.services.carton_special_requests import settlement_evidence
    special_sources, _ = settlement_evidence(db, factory, supplier, period)
    from app.services.carton_source_links import delivery_ids
    group_ids = delivery_ids(db, factory)
    for row in result:
        vendor = special_sources.get(row["source_key"].removeprefix("RECEIPT:")) if row["kind"] == "RECEIPT" else None
        if vendor:
            row.update(document_no=vendor["document_no"], supplier_delivery=vendor, special_request_kind=vendor["request_kind"],
                special_request_no=vendor["request_no"], special_request_id=vendor["request_id"],
                delivery_id=group_ids.get(vendor["shipment_id"], "SPECIAL:" + vendor["shipment_id"]))
    from app.services.carton_price_review import apply_sources
    apply_sources(db, factory, result)
    result.sort(key=lambda row: (row["acceptance_date"] or "", row["document_no"], row["source_key"]))
    # Navigation metadata must not invalidate a previously reconciled month.
    fingerprint_sources = [{key: value for key, value in row.items() if key != "delivery_id"} for row in result]
    fingerprint = hashlib.sha256(dump({"sources": fingerprint_sources, "issues": issues, "undated": sorted(undated, key=lambda row: row["receipt_id"])}).encode()).hexdigest()
    return result, fingerprint, issues, undated


def compare(rows, statement, source_issues):
    issues = list(source_issues)
    if any(row["kind"] not in {"RECEIPT", "RETURN", "RETURN_REFUND"} for row in rows):
        issues.append("存在未知结算来源类型，请核实；不能默认作为退货扣款")
    if not statement.get("statement_no", "").strip():
        issues.append("请填写供应商账单编号")
    if not statement.get("same_price_basis"):
        issues.append("请核实双方币种、计量单位及含税口径一致，账单没有未列明费用")
    by_key = {row["source_key"]: row for row in rows}
    seen, ids, results = set(), set(), []
    inbound = sum((Decimal(row["amount"]) for row in rows if row["kind"] == "RECEIPT" and row["amount"] is not None), Decimal(0))
    returns, supplier_total = Decimal(0), Decimal(0)
    cash = sum((Decimal(row["amount"]) for row in rows if row["kind"] == "RETURN_REFUND" and row["amount"] is not None), Decimal(0))
    inbound_unknown = any(row["kind"] == "RECEIPT" and row["amount"] is None for row in rows)
    return_unknown = False
    statement_unknown = False
    for line in statement.get("lines", []):
        key, line_issues = line.get("source_key", ""), []
        if line["id"] in ids:
            line_issues.append("账单行标识重复")
        ids.add(line["id"])
        row = by_key.get(key)
        if key in seen and key:
            line_issues.append("同一收货／退货行被重复匹配")
            statement_unknown = True
            return_unknown = return_unknown or (row is not None and row["kind"] == "RETURN")
        seen.add(key)
        diffs = {"quantity_difference": None, "price_difference": None, "amount_difference": None}
        if not row:
            line_issues.append("账单有此行，但本期没有对应有效收货或退货")
            statement_unknown = True
        else:
            line_issues.extend(row["issues"])
            vendor = row.get("supplier_delivery")
            if statement.get("origin") == "COLLABORATION" and vendor:
                changed = any(line.get(key) is not None and vendor.get(key) is not None
                              and Decimal(str(line[key])) != Decimal(str(vendor[key]))
                              for key in ("quantity", "unit_price", "amount"))
                if changed and len(line.get("note", "").strip()) < 4:
                    line_issues.append("调整供应商原送货数量或价格须填写至少四字核对依据，并由供应商确认")
            if line.get("document_no", "").strip() != row["document_no"]:
                line_issues.append("供应商单据号与本厂单据号不一致")
            local_price = Decimal(row["unit_price"]) if row["unit_price"] is not None else None
            if row["kind"] == "RETURN":
                agreement = row.get("return_agreement")
                local_price = (Decimal(row["unit_price"]) if row["unit_price"] is not None else None) if agreement else (
                    Decimal(str(line["approved_return_unit_price"])) if line.get("approved_return_unit_price") is not None else None)
                if agreement and (line.get("approved_return_unit_price") is None or local_price is None
                    or Decimal(str(line["approved_return_unit_price"])) != local_price
                    or line.get("credit_document_no") != agreement["credit_document_no"]
                    or line.get("credit_date") != agreement["credit_date"]):
                    line_issues.append("退货协同须沿已认可的独立贷项价格及凭证，修改请先在退货协同重核")
                if local_price is None or not line.get("credit_document_no", "").strip() or not line.get("note", "").strip() or not line.get("credit_date"):
                    line_issues.append("退货需本厂认可单价、贷项凭证号、日期及依据说明")
                    return_unknown = True
                if line.get("credit_date") and line["credit_date"] > _posting_date(core.now_text()):
                    line_issues.append("贷项凭证日期不能晚于今天")
            if local_price is None:
                line_issues.append("本厂金额尚未核实")
                if row["kind"] == "RETURN":
                    return_unknown = True
            else:
                local_amount = money(Decimal(row["quantity"]) * local_price)
                if row["kind"] == "RETURN":
                    returns += local_amount
                if line.get("amount") is not None:
                    diffs["amount_difference"] = str(Decimal(str(line["amount"])) - local_amount)
                if line.get("unit_price") is not None:
                    diffs["price_difference"] = str(Decimal(str(line["unit_price"])) - local_price)
            if line.get("quantity") is not None:
                diffs["quantity_difference"] = str(Decimal(str(line["quantity"])) - Decimal(row["quantity"]))
        if any(line.get(field) is None for field in ("quantity", "unit_price", "amount")):
            line_issues.append("供应商数量、单价和金额尚未填齐")
            statement_unknown = True
        else:
            qty, price, amount = (Decimal(str(line[field])) for field in ("quantity", "unit_price", "amount"))
            if money(qty * price) != amount:
                line_issues.append("供应商行金额不等于数量乘单价，请核实舍入或额外费用")
            sign = {"RECEIPT": 1, "RETURN": -1, "RETURN_REFUND": 1}.get(row["kind"]) if row else None
            if sign is None:
                statement_unknown = True
                line_issues.append("未知结算来源不可计入应结金额")
            else:
                supplier_total += amount * sign
        if any(value is not None and Decimal(value) != 0 for value in diffs.values()):
            line_issues.append("数量、单价或金额存在差异")
        results.append({"id": line["id"], "source_key": key, **diffs, "issues": line_issues})
        issues.extend(f"第 {len(results)} 行：{msg}" for msg in line_issues)
    missing = set(by_key) - seen
    if missing:
        issues.append(f"有 {len(missing)} 条本厂收货／退货未匹配供应商账单")
        return_unknown = return_unknown or any(by_key[key]["kind"] == "RETURN" for key in missing)
    if not rows and not statement.get("lines"):
        issues.append("本期无有效供货或退货，不生成空对账确认")
    return {"issues": issues, "line_results": results, "inbound_amount": None if inbound_unknown else str(inbound),
            "return_amount": None if return_unknown else str(returns), "net_amount": None if inbound_unknown or return_unknown else str(inbound - returns + cash),
            "statement_amount": None if statement_unknown or missing else str(supplier_total),
            **({"cash_refund_amount": str(cash), "return_deduction_amount": None if return_unknown else str(returns - cash)}
                if cash or any(row.get("return_agreement") or row["kind"] == "RETURN_REFUND" for row in rows) else {})}


def document_out(row, current_fingerprint=None):
    return {key: getattr(row, key) for key in ("id", "factory_id", "supplier_id", "period", "currency", "version", "revision", "status", "source_fingerprint", "created_at", "updated_at", "confirmed_at", "confirmed_by", "reopen_reason")} | {
        "sources": json.loads(row.sources_json), "statement": json.loads(row.statement_json),
        "result": json.loads(row.result_json), "stale": current_fingerprint is not None and current_fingerprint != row.source_fingerprint}


def workspace(db, factory, supplier_id, period, currency):
    factory = core.require_carton_factory(factory)
    core._lock_receipt_factory(db, factory)
    supplier = core.get_active_supplier(db, factory, supplier_id)
    try:
        core._period_bounds(period)
    except (ValueError, OverflowError):
        raise HTTPException(422, "账期月份无效")
    currency = core.normalize_currency(currency)
    rows, fingerprint, issues, undated = sources(db, factory, supplier.id, period, currency)
    from app.services.carton_settlement_collaboration import build
    collaboration = build(db, factory, supplier.id, period, currency, rows, fingerprint) if supplier.supplier_code == "HEYUAN-DONGKANG" else None
    documents = list(db.scalars(select(CartonSupplierSettlement).where(CartonSupplierSettlement.factory_id == factory,
        CartonSupplierSettlement.supplier_id == supplier.id, CartonSupplierSettlement.period == period,
        CartonSupplierSettlement.currency == currency).order_by(CartonSupplierSettlement.version.desc())))
    return {"factory_id": factory, "supplier_id": supplier.id, "supplier_name": supplier.supplier_name,
            "period": period, "currency": currency, "source_fingerprint": fingerprint, "sources": rows,
            "issues": issues, "undated_receipts": undated,
            "collaboration": collaboration,
            "documents": [document_out(row, collaboration["source_fingerprint"]
                          if collaboration and json.loads(row.statement_json).get("origin") == "COLLABORATION" else fingerprint) for row in documents]}


def comparison_context(current, origin):
    if origin == "COLLABORATION":
        if not current.get("collaboration"):
            raise HTTPException(409, "当前供应商尚未接入协同月结，请使用手工对账")
        return {**current, **{key: current["collaboration"][key] for key in ("sources", "source_fingerprint")}}
    return current


def calculate(current, statement):
    result = compare(current["sources"], statement, current["issues"])
    # A real prior confirmed liability can become zero after source correction.
    # This is a new bilateral reconciliation, never a fresh empty-month bill.
    zero_reopen = (not current["sources"] and not statement.get("lines")
        and statement.get("origin") == "COLLABORATION"
        and any(doc["confirmed_at"] for doc in current["documents"])
        and any(doc["status"] == "DRAFT" and len(doc["reopen_reason"].strip()) >= 4 for doc in current["documents"]))
    if zero_reopen:
        result["issues"] = [issue for issue in result["issues"] if issue != "本期无有效供货或退货，不生成空对账确认"]
        result["historical_zero_reconciliation"] = True
    if statement.get("origin") == "COLLABORATION":
        result["unsettled_shipments"] = current["collaboration"]["unsettled_shipments"]
    return result


def review_fingerprint(row):
    return hashlib.sha256(dump({"sources": row.source_fingerprint, "statement": json.loads(row.statement_json)}).encode()).hexdigest()


def save(db, payload, user):
    from app.services.carton_special_requests import locked_actor, allowed
    user = locked_actor(db, user, core.require_carton_factory(payload.factory_id))
    if not all(allowed(user, payload.factory_id, key) for key in ("read", "closing_manage")):
        raise HTTPException(403, "没有本厂读取及供应商月结管理权限")
    current = workspace(db, payload.factory_id, payload.supplier_id, payload.period, payload.currency)
    if not payload.id and payload.origin != "COLLABORATION" and current.get("collaboration") and any(row.get("supplier_delivery") for row in current["collaboration"]["sources"]):
        raise HTTPException(409, "本期已有供应商协同送货记录，请使用协同对账并保留双方确认")
    current = comparison_context(current, payload.origin)
    if payload.source_fingerprint != current["source_fingerprint"]:
        raise HTTPException(409, "收货、退货或价格来源已变化，请刷新后重新核对")
    if payload.id:
        row = db.get(CartonSupplierSettlement, payload.id)
        if row is None or any(getattr(row, key) != current[key] for key in ("factory_id", "supplier_id", "period", "currency")):
            raise HTTPException(404, "对账单不存在")
        if row.status != "DRAFT" or row.revision != payload.expected_revision:
            raise HTTPException(409, "对账单状态或版本已变化")
        if json.loads(row.statement_json).get("origin") == "COLLABORATION" and payload.origin != "COLLABORATION":
            raise HTTPException(409, "协同对账须保留双方确认流程，不能改为手工单绕过确认")
        row.revision += 1
    else:
        if current["documents"]:
            raise HTTPException(409, "本期对账已存在，请打开现有草稿或重核已确认版本")
        row = CartonSupplierSettlement(id="CSS-" + uuid4().hex, factory_id=current["factory_id"],
            supplier_id=current["supplier_id"], period=current["period"], currency=current["currency"],
            version=1, revision=1, status="DRAFT", created_at=core.now_text(), created_by=user.id,
            confirmed_at="", confirmed_by="", reopen_reason="")
        db.add(row)
    row.source_fingerprint = current["source_fingerprint"]
    row.sources_json = dump(current["sources"])
    statement = payload.model_dump(mode="json", include={"origin", "statement_no", "tax_basis", "same_price_basis", "lines"})
    row.statement_json = dump(statement)
    row.result_json = dump(calculate(current, statement))
    row.updated_at = core.now_text()
    core._audit(db, user, row.factory_id, "SUPPLIER_SETTLEMENT_SAVED", "carton_supplier_settlement", row.id,
                {"revision": row.revision, "version": row.version, "statement": statement, "source_fingerprint": row.source_fingerprint})
    db.commit()
    return document_out(row)


def act(db, identifier, payload, user, reopen=False):
    factory = core.require_carton_factory(payload.factory_id)
    from app.services.carton_special_requests import locked_actor, allowed
    user = locked_actor(db, user, factory)
    if not all(allowed(user, factory, key) for key in ("read", "closing_manage", "order_adjust")):
        raise HTTPException(403, "没有本厂读取、月结及调整权限")
    row = db.get(CartonSupplierSettlement, identifier)
    if row is None or row.factory_id != factory:
        raise HTTPException(404, "对账单不存在")
    if row.revision != payload.expected_revision:
        raise HTTPException(409, "对账单已更新，请刷新")
    if reopen:
        if row.status != "CONFIRMED" or len(payload.reason.strip()) < 4:
            raise HTTPException(409, "只有已确认对账可重核，并须填写至少四字原因")
        from app.services.carton_supplier_payables import reopen_guard
        reopen_guard(db, row)
        row.status = "SUPERSEDED"
        row.revision += 1
        new = CartonSupplierSettlement(id="CSS-" + uuid4().hex, factory_id=factory, supplier_id=row.supplier_id,
            period=row.period, currency=row.currency, version=row.version + 1, revision=1, status="DRAFT",
            source_fingerprint=row.source_fingerprint, sources_json=row.sources_json, statement_json=row.statement_json,
            result_json=row.result_json, created_at=core.now_text(), updated_at=core.now_text(), created_by=user.id,
            confirmed_at="", confirmed_by="", reopen_reason=payload.reason.strip())
        reopened_result = json.loads(new.result_json)
        reopened_result.pop("supplier_review", None)
        new.result_json = dump(reopened_result)
        db.add(new)
        core._audit(db, user, factory, "SUPPLIER_SETTLEMENT_REOPENED", "carton_supplier_settlement", row.id,
                    {"reason": payload.reason.strip(), "new_id": new.id, "version": new.version})
        db.commit()
        return document_out(new)
    if row.status != "DRAFT":
        raise HTTPException(409, "仅草稿可确认")
    if row.period >= _posting_date(core.now_text())[:7]:
        raise HTTPException(409, "本月尚未结束，可保存核对草稿，月末结束后再确认")
    current = workspace(db, factory, row.supplier_id, row.period, row.currency)
    statement = json.loads(row.statement_json)
    current = comparison_context(current, statement.get("origin", "MANUAL"))
    if current["source_fingerprint"] != row.source_fingerprint:
        raise HTTPException(409, "来源已变化，请刷新并重新保存核对结果")
    result = calculate(current, statement)
    if result["issues"]:
        raise HTTPException(409, "仍有未处理差异：" + "；".join(result["issues"][:5]))
    if statement.get("origin") == "COLLABORATION":
        review = json.loads(row.result_json).get("supplier_review", {})
        if review.get("decision") != "CONFIRMED" or review.get("fingerprint") != review_fingerprint(row):
            raise HTTPException(409, "请先由供应商确认当前版本月结明细，再完成本厂确认")
        result["supplier_review"] = review
    row.result_json = dump(result)
    row.status = "CONFIRMED"
    row.revision += 1
    row.confirmed_by = user.id
    row.confirmed_at = row.updated_at = core.now_text()
    core._audit(db, user, factory, "SUPPLIER_SETTLEMENT_CONFIRMED", "carton_supplier_settlement", row.id,
                {"version": row.version, "result": result, "source_fingerprint": row.source_fingerprint})
    db.commit()
    return document_out(row)


def supplier_document(document):
    # Warehouse's previous manual proposal and audit delta are internal notices.
    return {**document, "sources": [{key: value for key, value in source.items() if key != "supplier_price_update"}
        for source in document["sources"]]}


def supplier_workspace(db, user, factory, period, currency):
    from app.services.carton_supplier_portal import supplier_access
    supplier = supplier_access(db, user, factory)
    current = workspace(db, factory, supplier.id, period, currency)
    # Publish saved collaborative versions only. Unsaved internal forms and
    # legacy independently entered statements are not vendor acknowledgements.
    return {"factory_id": factory, "supplier_name": supplier.supplier_name,
            "period": current["period"], "currency": current["currency"],
            "documents": [supplier_document(doc) for doc in current["documents"] if doc["statement"].get("origin") == "COLLABORATION"]}


def supplier_review(db, identifier, payload, user):
    from app.services.carton_supplier_portal import supplier_access
    factory = core.require_carton_factory(payload.factory_id)
    from app.services.carton_special_requests import locked_actor
    from app.services.carton_supplier_portal import supplier_permission
    user = locked_actor(db, user, factory)
    if not supplier_permission(user, "carton_supplier:read", factory): raise HTTPException(403, "没有本厂供应商月结读取权限")
    supplier = supplier_access(db, user, factory, "carton_supplier:approve")
    row = db.get(CartonSupplierSettlement, identifier)
    if row is None or row.factory_id != factory or row.supplier_id != supplier.id:
        raise HTTPException(404, "未找到可核对的供应商月结")
    statement = json.loads(row.statement_json)
    if row.status != "DRAFT" or statement.get("origin") != "COLLABORATION" or row.revision != payload.expected_revision:
        raise HTTPException(409, "月结状态或版本已变化，请刷新后重新核对")
    current = comparison_context(workspace(db, factory, supplier.id, row.period, row.currency), "COLLABORATION")
    if current["source_fingerprint"] != row.source_fingerprint:
        raise HTTPException(409, "送货或验收来源已变化，请本厂更新草稿后再核对")
    result = calculate(current, statement)
    if payload.decision == "CONFIRMED":
        if row.period >= _posting_date(core.now_text())[:7]:
            raise HTTPException(409, "本月尚未结束，可先核对明细，月份结束后再确认")
        if result["issues"]:
            raise HTTPException(409, "仍有未处理差异，暂不能确认月结")
    elif len(payload.reason.strip()) < 4:
        raise HTTPException(422, "请填写至少四字的异议说明")
    result["supplier_review"] = {"decision": payload.decision, "reason": payload.reason.strip(),
        "by": user.id, "at": core.now_text(), "fingerprint": review_fingerprint(row)}
    row.result_json = dump(result)
    row.revision += 1
    row.updated_at = core.now_text()
    core._audit(db, user, factory, "SUPPLIER_SETTLEMENT_REVIEWED", "carton_supplier_settlement", row.id,
                {"revision": row.revision, "version": row.version, "review": result["supplier_review"]})
    db.commit()
    return supplier_document(document_out(row))


def set_return_date(db, movement_id, payload, user):
    """Verify a historical date once, protecting both supplier month snapshots."""
    from app.services import carton_return_dates
    from app.services.carton_special_requests import locked_actor, allowed
    factory = core.require_carton_factory(payload.factory_id)
    user = locked_actor(db, user, factory)  # IAM lock precedes the shared factory lock.
    if not all(allowed(user, factory, permission) for permission in ("closing_manage", "order_adjust")):
        raise HTTPException(403, "核实退货日期须具备本厂主管月结与调整权限")
    movement = db.get(CartonInventoryMovement, movement_id)
    if movement is None or movement.factory_id != factory or not carton_return_dates.is_return(movement):
        raise HTTPException(404, "退货库存流水不存在")
    core.ensure_customer_operation(db, user, factory, movement.customer_code)
    posting_date = _posting_date(movement.occurred_at)
    if (posting_date != payload.expected_posting_date or movement.id in carton_return_dates.dates(db, factory)
        or db.scalar(select(CartonInventoryMovement.id).where(CartonInventoryMovement.factory_id == factory,
            CartonInventoryMovement.reversal_of_movement_id == movement.id))):
        raise HTTPException(409, "退货日期依据或状态已变化；已有实际日期不能在此覆盖，请刷新核对")
    if len(payload.reason.strip()) < 4:
        raise HTTPException(422, "请填写实际退货日期核实依据，至少四字")
    day = carton_return_dates.require_date(payload.return_date)
    supplier = return_supplier(db, movement)
    if not supplier:
        raise HTTPException(409, "无法确定退货供应商，请先核实原收料来源")
    ensure_open(db, factory, supplier, posting_date[:7])
    ensure_open(db, factory, supplier, day[:7])
    carton_return_dates.record(db, user, movement, day, reason=payload.reason.strip(), verified=True)
    db.commit()
    return {"movement_id": movement.id, "return_date": day, "posting_date": posting_date, "date_basis": "RETURN_ACTUAL"}


def set_acceptance_date(db, receipt_id, payload, user):
    factory = core.require_carton_factory(payload.factory_id)
    core._lock_receipt_factory(db, factory)
    receipt = db.get(CartonReceipt, receipt_id)
    if receipt is None or receipt.factory_id != factory:
        raise HTTPException(404, "收料单不存在")
    if receipt.revision != payload.expected_revision or receipt.status == "REVERSED":
        raise HTTPException(409, "收料单状态或版本已变化")
    if len(payload.reason.strip()) < 4:
        raise HTTPException(422, "请填写验收日期核实依据，至少四字")
    date_check(payload.acceptance_date)
    receipt_guard(db, receipt)
    ensure_open(db, factory, receipt.supplier_id, payload.acceptance_date[:7])
    before = receipt.acceptance_date
    receipt.acceptance_date = payload.acceptance_date
    receipt.revision += 1
    receipt.updated_at = core.now_text()
    core._audit(db, user, factory, "RECEIPT_ACCEPTANCE_DATE_VERIFIED", "carton_receipt", receipt.id,
                {"before": before, "acceptance_date": receipt.acceptance_date, "reason": payload.reason.strip(), "revision": receipt.revision})
    db.commit()
    return core.receipt_out(db, receipt)
