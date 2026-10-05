"""Read-only dashboard projection. No business decisions or writes are cached here.

Source matching is indexed once per request; filtering and counts precede paging.
Full immutable import evidence and order details stay behind the context endpoint.
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select, func

from app.models.carton_procurement import CartonOrder, CartonCustomer, CartonImportBatch, CartonException, CartonAuditEvent
from app.models.carton_master import CartonMasterRecord
from app.schemas.carton_procurement import CartonExceptionOut
from app.services import carton_procurement as core, carton_order_split


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def norm(value):
    return unicodedata.normalize("NFKC", str(value or "")).strip().lower()


def business_identity(value):
    return re.sub(r"[\s\-_/\\.]", "", str(value or "").strip().lower())


class SourceIndex:
    def __init__(self, rows):
        self.rows = rows
        self.entries = []
        self.indexes = [defaultdict(list) for _ in range(4)]
        self.cache = {}
        for row in rows:
            values = (business_identity(row.get("contract_no") if row.get("contract_no") is not None else row.get("reference")),
                      business_identity(row.get("item_no")), business_identity(row.get("customer_name")),
                      (row.get("source_sheet"), row.get("source_row"), row.get("source_reference") or "未填"))
            entry = (row, values)
            self.entries.append(entry)
            for index, value in zip(self.indexes, values):
                index[value].append(entry)

    def find(self, exception):
        location = re.search(r"\n来源：(.+) · 第 (\d+) 行 · SO：(.*)$", exception.get("description", ""))
        keys = (business_identity(exception.get("contract_no")) or None,
                business_identity(exception.get("item_no")) or None,
                business_identity(exception.get("customer_name")) if exception.get("customer_name") else None,
                (location[1], int(location[2]), location[3]) if location else None)
        cancelled = exception.get("category") in ("SCHEDULE_CANCELLED", "SCHEDULE_CANCELLED_AFTER_ORDER")
        key = (*keys, cancelled)
        if key in self.cache:
            return self.cache[key]
        candidates = min([self.entries] + [index.get(value, []) for index, value in zip(self.indexes, keys) if value is not None], key=len)
        found = None
        for row, values in candidates:
            if any(k is not None and k != v for k, v in zip(keys, values)) or (cancelled and row.get("schedule_section") != "CANCELLED"):
                continue
            if found is not None:
                self.cache[key] = None
                return None
            found = row
        self.cache[key] = found
        return found


def complete_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def reminder(source, *, today, lead_days, production_days, marked=False, orders=()):
    if source.get("schedule_section") and source["schedule_section"] != "PENDING":
        return None
    if source.get("template") == "unified-item" and (source.get("order_type") or "").strip() not in ("正单", "加单", "正式PO"):
        return None
    def result(state, label, tone, detail):
        return dict(state=state, label=label, tone=tone, detail=detail, attention=state not in ("WAIT", "ORDERED"), deadline="", arrivalDate="", days=None)
    status = orders[0]["status"] if orders else ""
    if len(orders) > 1 or source.get("match_status") == "AMBIGUOUS":
        return result("REVIEW", "待人工确认", "amber", "订单身份或关联不唯一，请核实后判断是否已下单。")
    if not (source.get("item_no") or "").strip() or not (source.get("contract_no") or source.get("reference") or "").strip() or float(source.get("quantity") or 0) <= 0:
        return result("REVIEW", "待人工确认", "amber", "合同、货号或数量不完整，请核实后计算下单时限。")
    if source.get("schedule_identity_duplicate"):
        return result("REVIEW", "待人工确认", "amber", "合同、货号和 SO#/Reference 相同，请核实是否重复或分批；仍可标记已下单或按此下单。")
    if source.get("schedule_change") == "REVIEW_REQUIRED":
        return result("REVIEW", "待人工确认", "amber", "订单身份或关联不唯一，请核实后判断是否已下单。")
    if marked or status in ("PENDING_SUPPLIER", "PARTIALLY_RECEIVED", "COMPLETED"):
        return result("ORDERED", "人工已下单" if marked else "已完单" if status == "COMPLETED" else "已下单", "green", "已下单，停止下单时限提醒；排期退单和数量变化继续核对。")
    dates = [complete_date(source[key]) for key in ("inspection_window", "customer_due_date") if source.get(key)]
    if source.get("date_review_required") or not dates or None in dates:
        return result("DATE_REVIEW", "交期待确认", "amber", "缺少完整交期或日期原文需要确认，暂不判定漏单。")
    if any(not isinstance(n, int) or isinstance(n, bool) or n < 0 for n in (lead_days, production_days)):
        return result("RULE_REVIEW", "交期规则待确认", "amber", "请先加载或设置供应商生产送货周期和安全提前量。")
    arrival = min(dates) - timedelta(days=lead_days)
    deadline = arrival - timedelta(days=production_days)
    days = (deadline - today).days
    state = "OVERDUE" if days < 0 else "DUE_TODAY" if days == 0 else "DUE_SOON" if days <= 3 else "WAIT"
    created = status in ("DRAFT", "CONFIRMED")
    label = f"疑似漏单 · 超时 {-days} 天" if days < 0 else "今天必须下单" if days == 0 else f"即将到期 · 剩 {days} 天" if days <= 3 else "待下单"
    return dict(state=state, label=label + (" · 待确认下单" if created else ""), tone="red" if days <= 0 else "amber" if days <= 3 else "blue",
                attention=state != "WAIT", deadline=str(deadline), arrivalDate=str(arrival), days=days,
                detail=f"最迟下单 {deadline}；纸箱需到仓 {arrival}（验货/走货较早日期 {min(dates)}－安全提前 {lead_days} 天）；生产送货 {production_days} 天。" + ("已建单但未确认锁定，仍需完成下单。" if created else ""))


class Context:
    def __init__(self, factory, orders, customers, marks, rules, today):
        self.factory, self.marks, self.rules, self.today = factory, marks, rules, today
        self.latest_rows = []
        self.orders = {o["id"]: o for o in orders if o["factory_id"] == factory and o["status"] != "CANCELLED"}
        self.customers = [c for c in customers if c["factory_id"] == factory and c["status"] == "ACTIVE"]
        self.by_code, self.by_name = defaultdict(list), defaultdict(list)
        for customer in self.customers:
            self.by_code[customer["customer_code"]].append(customer)
            self.by_name[norm(customer["customer_name"])].append(customer)
        self.index, self.splits = defaultdict(list), defaultdict(list)
        for o in self.orders.values():
            self.index[(o["customer_code"], norm(o["contract_no"]), norm(o["item_no"]))].append(o)
            for plan in o.get("split_records", []):
                if plan["status"] == "CANCELLED":
                    continue
                for target in plan["targets"]:
                    self.splits[(o["customer_code"], norm(plan["item_no"]), norm(target["contract_no"]))].append((o, target))

    def customer(self, row):
        matches = self.by_code.get(row["customer_code"], []) if row.get("customer_code") else self.by_name.get(norm(row.get("customer_name") or row.get("source_customer_name")), [])
        return matches[0] if len(matches) == 1 else None

    def marked(self, row):
        return bool(self.marks.get(row.get("schedule_identity"), {}).get("marked", row.get("manual_ordered", False))) if row.get("schedule_identity") else False

    def matching(self, row):
        linked_ids = list(dict.fromkeys(self.marks.get(row.get("schedule_identity"), {}).get("order_ids", []) + ([row["order_id"]] if row.get("order_id") else [])))
        linked = [self.orders[i] for i in linked_ids if i in self.orders and (not row.get("schedule_customer_code") or self.orders[i]["customer_code"] == row["schedule_customer_code"])
                  and norm(self.orders[i]["contract_no"]) == norm(row.get("contract_no") or row.get("reference")) and norm(self.orders[i]["item_no"]) == norm(row.get("item_no"))]
        if linked:
            return linked
        if row.get("schedule_identity_duplicate"):
            return []
        po = row.get("source_reference") or row.get("customer_po")
        split = {o["id"]: o for o, target in self.splits.get((row.get("schedule_customer_code"), norm(row.get("item_no")), norm(row.get("contract_no"))), [])
                 if not po or norm(target.get("customer_po")) == norm(po)}
        if split:
            return list(split.values())
        customer = self.customer(row)
        if not customer:
            return []
        return [o for o in self.index.get((customer["customer_code"], norm(row.get("contract_no") or row.get("reference")), norm(row.get("item_no"))), []) if not po or norm(o.get("customer_po")) == norm(po)]

    def reminder(self, row):
        customer = row.get("schedule_customer_code") or (self.customer(row) or {}).get("customer_code", "")
        rules = {"lead_days": 3, "production_days": 7}
        for code in dict.fromkeys(["", customer]):
            rules.update({k: v for k, v in self.rules.get(code, {}).items() if k in rules and v is not None})
        return reminder(row, today=self.today, **rules, marked=self.marked(row), orders=self.matching(row))


def source_key(row):
    return row.get("schedule_identity") or compact([row.get("schedule_customer_code") or row.get("customer_code") or norm(row.get("customer_name")),
        norm(row.get("contract_no") or row.get("reference")), norm(row.get("item_no")), norm(row.get("source_reference"))])


def build_alerts(context, batches, exceptions):
    by_batch = defaultdict(list)
    for e in exceptions:
        if e["factory_id"] == context.factory and e["source_type"] == "WEEKLY_SCHEDULE":
            by_batch[e["source_id"]].append(e)
    changes, timing, seen = {}, {}, set()
    for batch in batches:
        if batch["status"] == "REJECTED" or batch["factory_id"] != context.factory:
            continue
        rows = batch["parse_summary"].get("rows", [])
        lookup, timing_exceptions = SourceIndex(rows), {}
        for e in by_batch[batch["id"]]:
            row = lookup.find(e)
            if e["category"] in ("MISSING_ORDER", "SCHEDULE_NEW_ORDER"):
                if row is not None:
                    timing_exceptions.setdefault(id(row), e)
                continue
            if e["category"] not in ("QUANTITY_MISMATCH", "SCHEDULE_CANCELLED", "SCHEDULE_CANCELLED_AFTER_ORDER"):
                continue
            if row and row.get("legacy_match_stale") and e["category"] == "QUANTITY_MISMATCH":
                continue
            merged = dict(row or {})
            for key in ("contract_no", "item_no", "customer_code", "customer_name"):
                merged[key] = e.get(key) or merged.get(key) or (merged.get("reference") if key == "contract_no" else None)
            orders = context.matching(merged)
            order = orders[0] if len(orders) == 1 else None
            qty, oqty = float((row or {}).get("quantity") or 0), float((order or {}).get("product_order_quantity") or 0)
            kind = "CANCELLED_AFTER_ORDER" if e["category"] == "SCHEDULE_CANCELLED_AFTER_ORDER" else "SCHEDULE_CANCELLED" if e["category"] == "SCHEDULE_CANCELLED" else "QUANTITY_REVIEW" if row is None else "QUANTITY_INCREASE" if qty > oqty else "QUANTITY_DECREASE" if qty < oqty else "QUANTITY_REVIEW"
            key = source_key(row) if row else compact([e.get("customer_code") or e.get("customer_name"), e.get("contract_no"), e.get("item_no")])
            if key not in changes:
                changes[key] = dict(id=e["id"], alertNo=e["exception_no"], kind=kind,
                    customerCode=e.get("customer_code") or (row or {}).get("schedule_customer_code") or (order or {}).get("customer_code", ""),
                    customerName=(row or {}).get("schedule_customer_name") or e.get("customer_name") or (order or {}).get("customer_name") or "待识别客户",
                    contractNo=e.get("contract_no") or (row or {}).get("contract_no") or (row or {}).get("reference") or "",
                    itemNo=e.get("item_no") or (row or {}).get("item_no") or "", productName=(row or {}).get("product_name") or (order or {}).get("product_name") or "",
                    scheduleQuantity=qty, orderQuantity=oqty, differenceQuantity=qty-oqty, orderNo=(order or {}).get("order_no") or (row or {}).get("order_no") or "",
                    orderStatus=(order or {}).get("status", ""), sourceFilename=batch["original_filename"], sourceOperatorName=batch.get("imported_by_name") or "业务接单员",
                    sourceCreatedAt=batch["created_at"], suggestion=(row or {}).get("suggestion") or e["description"], exception=e,
                    batchId=batch["id"], status=e["status"], reminder=None, sourceRow=row, order=order)
        for row in rows:
            key = source_key(row)
            if key in seen:
                continue
            seen.add(key)
            r = context.reminder(row)
            if not r or r["state"] in ("ORDERED", "REVIEW"):
                continue
            e = timing_exceptions.get(id(row))
            orders = context.matching(row)
            order = orders[0] if len(orders) == 1 else None
            timing[key] = dict(id=f"TIMING:{batch['id']}:{key}", alertNo=e["exception_no"] if e else f"排期-{row.get('source_sheet') or 'ITEM'}-{row.get('source_row') or 1}",
                kind="NEW_ORDER" if row.get("schedule_change") == "NEW" else "MISSING_ORDER",
                customerCode=row.get("schedule_customer_code") or row.get("customer_code") or "", customerName=row.get("schedule_customer_name") or row.get("customer_name") or "未绑定客户",
                contractNo=row.get("contract_no") or row.get("reference") or "", itemNo=row.get("item_no") or "", productName=row.get("product_name") or "",
                scheduleQuantity=float(row.get("quantity") or 0), orderQuantity=float((order or {}).get("product_order_quantity") or 0), differenceQuantity=0,
                orderNo=(order or {}).get("order_no", ""), orderStatus=(order or {}).get("status", ""), sourceFilename=batch["original_filename"],
                sourceOperatorName=batch.get("imported_by_name") or "业务接单员", sourceCreatedAt=batch["created_at"], suggestion=r["detail"],
                exception=e, batchId=batch["id"], status="OPEN", reminder=r, sourceRow=row, order=order)
    def rank(a):
        return (0 if a["kind"] == "CANCELLED_AFTER_ORDER" else {"OVERDUE": 1, "DUE_TODAY": 2, "DUE_SOON": 3, "WAIT": 6}.get((a["reminder"] or {}).get("state"), 4), (a["reminder"] or {}).get("deadline", ""))
    return sorted([*changes.values(), *timing.values()], key=rank)


ORDER_FIELDS = ("id", "factory_id", "order_no", "customer_code", "customer_name", "contract_no", "customer_po", "item_no", "status", "product_order_quantity", "product_name", "customer_due_date", "due_date", "order_date")


def read_context(db, factory):
    fields = [getattr(CartonOrder, k) for k in ORDER_FIELDS]
    orders = [dict(row) for row in db.execute(select(*fields).where(CartonOrder.factory_id == factory, CartonOrder.deleted_at.is_(None))).mappings()]
    splits = defaultdict(list)
    for plan in carton_order_split.plans(db, factory):
        splits[plan["order_id"]].append(plan)
    for o in orders:
        o["split_records"] = splits[o["id"]]
    customers = [dict(row) for row in db.execute(select(CartonCustomer.factory_id, CartonCustomer.customer_code, CartonCustomer.customer_name, CartonCustomer.status).where(CartonCustomer.factory_id == factory)).mappings()]
    rules = {row.customer_code: json.loads(row.data_json) for row in db.scalars(select(CartonMasterRecord).where(CartonMasterRecord.factory_id == factory, CartonMasterRecord.kind == "RULE", CartonMasterRecord.status == "ACTIVE"))}
    return Context(factory, orders, customers, core.schedule_order_state(db, factory), rules, core.business_now().date()), orders


def active_batches(db, factory):
    # Stream immutable evidence in deterministic business-import order; never silently cut at 50 batches.
    sequence = select(func.max(CartonAuditEvent.sequence)).where(CartonAuditEvent.factory_id == factory,
        CartonAuditEvent.entity_id == CartonImportBatch.id, CartonAuditEvent.entity_type == "carton_import_batch",
        CartonAuditEvent.event_type == "IMPORT_BATCH_CREATED").correlate(CartonImportBatch).scalar_subquery()
    query = select(CartonImportBatch).where(CartonImportBatch.factory_id == factory, CartonImportBatch.import_type == "WEEKLY_SCHEDULE",
        CartonImportBatch.status != "REJECTED").order_by(sequence.desc().nulls_last(), CartonImportBatch.created_at.desc(), CartonImportBatch.id.desc()).execution_options(yield_per=10)
    for batch in db.scalars(query):
        yield core.import_batch_out(batch).model_dump(mode="json")


def read_alerts(db, factory):
    context, orders = read_context(db, factory)
    query = select(CartonException).where(CartonException.factory_id == factory, core._visible_exception()).order_by(CartonException.created_at.desc(), CartonException.id.desc())
    exceptions = [CartonExceptionOut.model_validate(e).model_dump(mode="json") for e in db.scalars(query)]
    def batches():
        for index, batch in enumerate(active_batches(db, factory)):
            if index == 0:
                context.latest_rows = batch["parse_summary"].get("rows", [])
            yield batch
    return context, orders, exceptions, build_alerts(context, batches(), exceptions)


def text_matches(values, search):
    value = " ".join(str(v or "") for v in values).lower()
    return search.strip().lower() in value


def alert_page(alerts, *, customer="", search="", status="OPEN", kind="ALL", offset=0, limit=8):
    items = [a for a in alerts if (not customer or a["customerName"] == customer)
        and (status == "ALL" or a["status"] in ("OPEN", "IN_PROGRESS")) and (kind == "ALL" or a["kind"] == kind)
        and text_matches([a[k] for k in ("alertNo", "customerName", "contractNo", "itemNo", "productName", "orderNo", "sourceFilename", "sourceOperatorName")], search)]
    actionable = [a for a in items if a["status"] in ("OPEN", "IN_PROGRESS") and (not a["reminder"] or a["reminder"]["attention"])]
    summary = dict(total=len(actionable), missing=sum(bool(a["reminder"] and a["reminder"]["attention"]) for a in actionable),
                   increase=sum(a["kind"] == "QUANTITY_INCREASE" for a in actionable),
                   decrease=sum(a["kind"] in ("QUANTITY_DECREASE", "SCHEDULE_CANCELLED", "CANCELLED_AFTER_ORDER") for a in actionable))
    return dict(items=items[offset:offset+limit], total=len(items), summary=summary, reminders=actionable[:3], offset=offset, limit=limit)


def alert_context(db, factory, identifier):
    context, _, _, alerts = read_alerts(db, factory)
    alert = next((a for a in alerts if a["id"] == identifier), None)
    if not alert:
        raise HTTPException(409, "提醒已变化，请刷新看板后重新核对")
    batch = db.get(CartonImportBatch, alert["batchId"])
    if not batch or batch.factory_id != factory or batch.status == "REJECTED":
        raise HTTPException(409, "来源排期已撤销，请刷新看板")
    # Only one action's source evidence and full current orders; nothing is written.
    row = alert["sourceRow"]
    matches = context.matching(row) if row else ([alert["order"]] if alert["order"] else [])
    from app.services.carton_order_projection import order_page_out
    models = list(db.scalars(select(CartonOrder).where(CartonOrder.factory_id == factory, CartonOrder.deleted_at.is_(None), CartonOrder.id.in_([o["id"] for o in matches])))) if len(matches) == 1 else []
    batch_out = core.import_batch_out(batch).model_dump(mode="json")
    batch_out["parse_summary"] = {"rows": [row] if row else []}
    identity = (row or {}).get("schedule_identity")
    return dict(alert=alert, batch=batch_out, orders=[o.model_dump(mode="json") for o in order_page_out(db, models)], matching_orders=matches[:2],
                marks={identity: context.marks[identity]} if identity in context.marks else {})


def weekly_attention(db, context, customer, search):
    total = 0
    match_labels = {"MATCHED": "已匹配", "MISSING_ORDER": "未匹配订单", "QUANTITY_MISMATCH": "数量差异", "AMBIGUOUS": "待人工选择", "REVIEW_REQUIRED": "待人工确认", "DATE_MISMATCH": "交期差异"}
    for row in context.latest_rows:
        name = row.get("schedule_customer_name") or (row.get("customer_name") if row.get("schedule_customer_code") else "未绑定客户") or "未绑定客户"
        r = context.reminder(row)
        preserve = not row.get("schedule_identity_duplicate") and (row.get("match_status") in ("QUANTITY_MISMATCH", "DATE_MISMATCH", "AMBIGUOUS")
            or (row.get("match_status") == "REVIEW_REQUIRED" and r and r["state"] == "ORDERED"))
        result = match_labels.get(row.get("match_status"), "待核对") if preserve or not r else r["label"]
        attention = bool((r and r["attention"]) or row.get("date_review_required") or row.get("schedule_change") in ("CANCELLED", "CANCELLED_AFTER_ORDER", "REOPENED")
            or result in ("数量差异", "交期差异", "待人工选择", "待人工确认") or (not r and not context.marked(row) and row.get("match_status") != "MATCHED"))
        state = {"NEEDS_ORDER": "需要下单", "ORDERED": "已下单", "COMPLETED": "已完单", "REVIEW": "待确认"}.get(row.get("procurement_state"), "待确认" if row.get("template") else "")
        if attention and (not customer or name == customer) and text_matches([row.get("reference", row.get("contract_no")), row.get("po_numbers"), row.get("source_reference"), name, row.get("item_no"), row.get("product_name"), result, state, row.get("source_customer_name")], search):
            total += 1
    batch = db.scalar(select(CartonImportBatch).where(CartonImportBatch.factory_id == context.factory, CartonImportBatch.import_type == "INSPECTION_SCHEDULE", CartonImportBatch.status != "REJECTED").order_by(CartonImportBatch.created_at.desc(), CartonImportBatch.id.desc()).limit(1))
    labels = {"READY": "纸箱已备齐", "UPCOMING": "待提前交货", "DUE_SOON": "交货临近", "OVERDUE": "交货已逾期", "MISSING_ORDER": "未匹配订单", "AMBIGUOUS": "待人工关联", "INVALID_DATE": "送货日期待补充", "REVIEW_REQUIRED": "待人工确认"}
    for row in (core.import_batch_out(batch).parse_summary.get("rows", []) if batch else []):
        name = row.get("schedule_customer_name") or (row.get("customer_name") if row.get("schedule_customer_code") else "未绑定客户") or "未绑定客户"
        if row.get("reminder_status") != "READY" and (not customer or name == customer) and text_matches([row.get("reference", row.get("contract_no")), row.get("po_numbers"), name, row.get("item_no"), row.get("product_name"), labels.get(row.get("reminder_status"), "待核对"), row.get("required_delivery_date")], search):
            total += 1
    return total


def workspace(db, factory, *, customer="", search="", status="OPEN", kind="ALL", offset=0, limit=8):
    context, orders, exceptions, alerts = read_alerts(db, factory)
    page = alert_page(alerts, customer=customer, search=search, status=status, kind=kind, offset=offset, limit=limit)
    # An alert preview must not embed the entire split/order document.
    for key in ("items", "reminders"):
        page[key] = [{**a, "order": {k: a["order"].get(k) for k in ORDER_FIELDS} if a["order"] else None} for a in page[key]]
    order_rows = [o for o in orders if (not customer or o["customer_name"] == customer) and text_matches([o[k] for k in ("order_no", "contract_no", "item_no", "customer_name")], search)]
    pending = sum(o["status"] not in ("COMPLETED", "CANCELLED") for o in order_rows)
    recent = sorted(order_rows, key=lambda o: (o["order_date"], o["order_no"]), reverse=True)[:3]
    open_exceptions = [e for e in exceptions if e["status"] in ("OPEN", "IN_PROGRESS") and (not customer or e["customer_name"] == customer)
                       and text_matches([e[k] for k in ("exception_no", "customer_name", "category", "title", "description")], search)]
    # Reuse authoritative location/identity/reversal semantics; transmit only totals grouped by unit.
    from app.services.carton_positions import position_balances
    inventory = defaultdict(Decimal)
    for b in position_balances(db, factory):
        if b.balance <= 0 or (customer and b.customer_name != customer):
            continue
        if not text_matches([b.latest_movement_at.replace("T", " ")[:16], b.latest_document_no, b.customer_name, b.contract_no, b.item_no, b.packaging_type, b.paper_quality, b.specification, b.latest_location], search):
            continue
        inventory[(b.unit or "").strip() or "单位未注明"] += b.balance
    pending_splits = [o for o in order_rows if any(p["status"] == "PENDING_WAREHOUSE" for p in o.get("split_records", []))]
    return dict(factory_id=factory, business_date=str(context.today), generated_at=core.now_text(), **page,
        pending_order_count=pending, open_exception_count=len(open_exceptions), weekly_attention_count=weekly_attention(db, context, customer, search), inventory_by_unit=[dict(unit=k, quantity=str(v)) for k, v in inventory.items()],
        recent_orders=[{k: o[k] for k in ORDER_FIELDS} for o in recent], priority_exceptions=open_exceptions[:3],
        pending_splits=[{k: o[k] for k in ORDER_FIELDS} for o in pending_splits[:3]], pending_split_count=len(pending_splits))
