"""Current, read-only evidence for PO-less regular purchases.

This evidence is never a schedule link, a material grant or a write credential.
All requests solve against the whole factory, before response pagination.
"""
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
import re

from sqlalchemy import select

from app.models.carton_procurement import CartonOrder, CartonOrderLine
from app.services.carton_schedule_tracking import identity, normalized, effective_po

BASIS = "CONTRACT_ITEM_QUANTITY_PACKING"
REVIEW_REASON = "合同、货号、产品数量及装箱相同的采购或排期不唯一，请核对原订单，勿重复下单"


def positive(value):
    try:
        number = Decimal(str(value))
        return number if number.is_finite() and number > 0 else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def number(value):
    return format(value.normalize(), "f")


def packing(value):
    text = re.sub(r"\s+", "", normalized(value))
    if not re.fullmatch(r"\d+(?:\.\d+)?(?:/\d+(?:\.\d+)?)?", text):
        return None
    parts = [Decimal(part) for part in text.split("/")]
    inner, outer = (Decimal(0), parts[0]) if len(parts) == 1 else parts
    return (inner, outer) if outer > 0 and 0 <= inner <= outer else None


def packing_key(value):
    parsed = packing(value)
    return "/".join(number(part) for part in parsed) if parsed else ""


def order_packing(order):
    values = {}
    for line in order.get("lines", []):
        kind = line.get("packaging_type")
        rule = line.get("quantity_rule") or {}
        if rule.get("manual_quantity") is not None:
            return None
        # These are the existing carton-master outer-box names, not inferred custom types.
        kind = "外箱" if kind in {"外箱", "普通箱", "半翼箱"} else kind
        if kind not in {"内箱", "外箱"}:
            continue
        if rule and rule.get("mode") != "PACKING":
            return None
        amount = positive(line.get("usage_quantity"))
        if amount is None or kind in values:
            return None
        values[kind] = amount
    if "外箱" not in values:
        return None
    result = values.get("内箱", Decimal(0)), values["外箱"]
    return result if result[0] <= result[1] else None


def scope(row, *, source=False):
    return (normalized(row.get("schedule_customer_code") if source else row.get("customer_code")),
            normalized(row.get("contract_no") or row.get("reference")), normalized(row.get("item_no")))


def solve(rows, orders, *, factory_id):
    """Blocked demands compete too; another PO cannot silently steal their purchase."""
    by_scope = defaultdict(list)
    for order in orders:
        if (order.get("status") != "CANCELLED" and not order.get("deleted_at")
                and (factory_id is None or order.get("factory_id") == factory_id)):
            by_scope[scope(order)].append(order)
    reserved = {identifier for row in rows for identifier in row.get("explicit_order_ids", [])}
    blank_source_orders = set()
    for row in rows:
        for order in by_scope[scope(row, source=True)]:
            if not effective_po(row) and row.get("schedule_section") == "PENDING":
                blank_source_orders.add(order["id"])
            elif effective_po(row) and effective_po(row) == normalized(order.get("customer_po")):
                reserved.add(order["id"])
    counts = Counter(identity(row) for row in rows)
    edges = []
    for row in rows:
        if (row.get("template") != "unified-item" or not all(scope(row, source=True))
                or row.get("schedule_section") != "PENDING"
                or row.get("order_type") not in {"正单", "加单", "改单", "正式PO"}
                or factory_id is not None and row.get("factory_id", factory_id) != factory_id
                or not effective_po(row) or positive(row.get("quantity")) is None or packing(row.get("carton_rule")) is None):
            continue
        scoped = by_scope[scope(row, source=True)]
        if row.get("explicit_order_ids") or row.get("has_split") or any(
                normalized(order.get("customer_po")) == effective_po(row) for order in scoped):
            continue
        for order in scoped:
            if (normalized(order.get("customer_po")) or order["id"] in reserved
                    or order.get("quantity_basis") != "CALCULATED" or order.get("has_split")
                    or row.get("factory_id") and order.get("factory_id") != row["factory_id"]
                    or positive(order.get("product_order_quantity")) != positive(row.get("quantity"))
                    or order_packing(order) != packing(row.get("carton_rule"))):
                continue
            edges.append((row, order))
    source_counts = Counter(identity(row) for row, _ in edges)
    order_counts = Counter(order["id"] for _, order in edges)
    result = defaultdict(list)
    for row, order in edges:
        ambiguous = (counts[identity(row)] != 1 or source_counts[identity(row)] != 1
                     or order_counts[order["id"]] != 1 or bool(row.get("schedule_identity_duplicate"))
                     or order["id"] in blank_source_orders
                     or row.get("can_operate_source") is False)
        result[order["id"]].append(dict(version=1, basis=BASIS,
            factory_id=order.get("factory_id") or factory_id,
            customer_code=scope(row, source=True)[0], contract_no=scope(row, source=True)[1], item_no=scope(row, source=True)[2],
            schedule_identity=row.get("schedule_identity") or identity(row), source_identity=identity(row),
            source_batch_id=row.get("_batch_id", ""), source_sheet=row.get("source_sheet", ""), source_row=row.get("source_row"),
            quantity=number(positive(row["quantity"])), carton_rule=packing_key(row["carton_rule"]), ambiguous=ambiguous,
            reason=("最新全量排期缺行尚未核实，相关采购须人工核对" if row.get("can_operate_source") is False else REVIEW_REASON) if ambiguous
                else "手动订单未填客户 PO；合同、货号、产品数量及装箱一致且双方唯一"))
    return dict(result)


def proof_matches(row, proof):
    return (proof.get("version") == 1 and proof.get("basis") == BASIS
            and proof.get("schedule_identity") == (row.get("schedule_identity") or identity(row))
            and proof.get("source_identity") == identity(row)
            and (proof.get("customer_code"), proof.get("contract_no"), proof.get("item_no")) == scope(row, source=True)
            and positive(proof.get("quantity")) == positive(row.get("quantity"))
            and bool(packing_key(row.get("carton_rule"))) and proof.get("carton_rule") == packing_key(row.get("carton_rule")))


def candidates(row, orders, *, ambiguous=False):
    return [order for order in orders if order.get("status") != "CANCELLED" and not normalized(order.get("customer_po"))
        and scope(order) == scope(row, source=True) and positive(order.get("product_order_quantity")) == positive(row.get("quantity"))
        and any(proof_matches(row, proof) and proof.get("factory_id") == order.get("factory_id")
                and proof.get("ambiguous") == ambiguous for proof in order.get("schedule_quantity_matches", []))]


def read_matches(db, factory, incoming_rows=None):
    from app.services import carton_procurement as core, carton_schedule_coverage as coverage
    from app.services.carton_order_split import live_plans
    from app.services.carton_print_split import records, HELD
    fields = ("id", "factory_id", "customer_code", "contract_no", "item_no", "customer_po", "status", "quantity_basis", "product_order_quantity")
    orders = [dict(row) for row in db.execute(select(*(getattr(CartonOrder, key) for key in fields)).where(
        CartonOrder.factory_id == factory, CartonOrder.deleted_at.is_(None), CartonOrder.status != "CANCELLED")).mappings()]
    eligible = {order["id"] for order in orders if not normalized(order.get("customer_po")) and order.get("quantity_basis") == "CALCULATED"}
    if not eligible:
        return {}
    # No dashboard dependency: imports, read projections and write guards share this service.
    entries = coverage.batches(db, factory)
    reviews = coverage.source_reviews(db, factory)
    sources = []
    if incoming_rows is not None:
        sources.append(("", [dict(row) for row in incoming_rows]))
    sources.extend((entry["batch"].id, core.import_batch_out(entry["batch"]).parse_summary.get("rows", []))
                   for entry in entries if entry["batch"].status != "REJECTED")
    latest, seen = [], set()
    for batch_id, rows in sources:
        grouped = defaultdict(list)
        for source in rows:
            if isinstance(source, dict) and source.get("schedule_customer_code") and identity(source):
                grouped[identity(source)].append(source)
        for key, group in grouped.items():
            if key in seen:
                continue
            seen.add(key)
            if batch_id and reviews.get(key, {}).get("status") == "NO_LONGER_REQUIRED":
                continue
            for source in group:
                row = dict(source, _batch_id=batch_id, factory_id=factory)
                if batch_id and key in reviews:
                    row["can_operate_source"] = coverage.source_allowed(reviews[key], row, batch_id)
                latest.append(row)
    links = core._schedule_order_links(db, factory)
    plans = live_plans(db, factory)
    split_ids = {plan["order_id"] for plan in plans}
    for plan in records(db, factory):
        if plan.get("status") in {"ACTIVE", *HELD}:
            split_ids.add(plan["order_id"])
            split_ids.update(member["order_id"] for member in plan.get("members", []))
    split_scopes = {(normalized(plan.get("customer_code")), normalized(target.get("contract_no")), normalized(plan.get("item_no")),
                     normalized(target.get("customer_po"))) for plan in plans for target in plan["targets"]}
    for row in latest:
        row["explicit_order_ids"] = links.get(row.get("schedule_identity") or identity(row), [])
        row["has_split"] = (*scope(row, source=True), effective_po(row)) in split_scopes
    lines = defaultdict(list)
    for line in db.scalars(select(CartonOrderLine).join(CartonOrder, CartonOrder.id == CartonOrderLine.order_id).where(
            CartonOrderLine.factory_id == factory, CartonOrder.factory_id == factory,
            CartonOrder.deleted_at.is_(None), CartonOrder.status != "CANCELLED",
            CartonOrder.quantity_basis == "CALCULATED", CartonOrderLine.order_id.in_(eligible))):
        if line.order_id not in eligible:
            continue
        lines[line.order_id].append(dict(packaging_type=line.packaging_type, usage_quantity=line.usage_quantity, quantity_rule=line.quantity_rule))
    for order in orders:
        order.update(lines=lines[order["id"]], has_split=order["id"] in split_ids)
    return solve(latest, orders, factory_id=factory)


def refresh_snapshot_matches(db, result, *, matches=None):
    """A saved import fallback is historical comparison, never a durable order link."""
    if result.import_type != "WEEKLY_SCHEDULE" or not result.detail_loaded:
        return result
    rows = [row for row in result.parse_summary.get("rows", []) if isinstance(row, dict) and row.get("match_basis") == BASIS]
    if not rows:
        return result
    matches = read_matches(db, result.factory_id) if matches is None else matches
    proofs = [(identifier, proof) for identifier, values in matches.items() for proof in values]
    orders = {order.id: order for order in db.scalars(select(CartonOrder).where(CartonOrder.factory_id == result.factory_id,
        CartonOrder.status != "CANCELLED", CartonOrder.deleted_at.is_(None)))}
    by_scope = defaultdict(list)
    for order in orders.values():
        by_scope[(normalized(order.customer_code), normalized(order.contract_no), normalized(order.item_no))].append(order)
    from app.services import carton_procurement as core
    from app.services.carton_order_split import live_plans, annotate_schedule
    links = core._schedule_order_links(db, result.factory_id)
    plans = live_plans(db, result.factory_id)
    for row in rows:
        current = [(identifier, proof) for identifier, proof in proofs if proof_matches(row, proof)]
        for key in ("order_id", "order_no", "order_status"):
            row.pop(key, None)
        scoped = [order for order in by_scope[scope(row, source=True)] if not effective_po(row)
                  or normalized(order.customer_po) == effective_po(row)]
        explicit = [order for order in scoped if order.id in links.get(row.get("schedule_identity"), [])]
        if not explicit and not row.get("schedule_identity_duplicate") and annotate_schedule(db, result.factory_id, row, plans):
            # Retain the comparison provenance marker, even when a current split now wins.
            row["match_basis"] = BASIS
            continue
        exact = explicit or ([] if row.get("schedule_identity_duplicate") else scoped)
        if exact:
            if len(exact) > 1:
                row.update(match_status="AMBIGUOUS", procurement_state="REVIEW", suggestion="当前匹配多个正式订单，请按客户 PO 核对")
            else:
                order = exact[0]
                mismatch = positive(order.product_order_quantity) != positive(row.get("quantity"))
                row.update(order_id=order.id, order_no=order.order_no, order_status=order.status,
                    match_status="QUANTITY_MISMATCH" if mismatch else "DATE_MISMATCH" if row.get("match_status") == "DATE_MISMATCH" else "MATCHED",
                    procurement_state="REVIEW" if mismatch else "NEEDS_ORDER" if order.status in {"DRAFT", "CONFIRMED"}
                        else "COMPLETED" if order.status == "COMPLETED" else "ORDERED",
                    suggestion="已按当前明确来源或客户 PO 匹配正式订单" + ("；产品数量不同，请核对原订单" if mismatch else ""))
            continue
        if any(proof["ambiguous"] for _, proof in current):
            row.update(match_status="AMBIGUOUS", procurement_state="REVIEW", suggestion=REVIEW_REASON)
        elif current:
            order = orders[current[0][0]]
            row.update(order_id=order.id, order_no=order.order_no, order_status=order.status,
                       suggestion=current[0][1]["reason"],
                       procurement_state="NEEDS_ORDER" if order.status in {"DRAFT", "CONFIRMED"}
                           else "COMPLETED" if order.status == "COMPLETED" else "ORDERED")
            if row.get("match_status") != "DATE_MISMATCH":
                row["match_status"] = "MATCHED"
        else:
            row.update(match_status="MISSING_ORDER", procurement_state="NEEDS_ORDER",
                       suggestion="原数量及装箱匹配已失效，请核对当前订单和最新排期")
    all_rows = [row for row in result.parse_summary.get("rows", []) if isinstance(row, dict)]
    matched = sum(row.get("match_status") == "MATCHED" for row in all_rows)
    result.parse_summary.update(matched_count=matched, issue_count=len(all_rows) - matched,
        review_count=sum(row.get("match_status") == "REVIEW_REQUIRED" or bool(row.get("date_review_required")) for row in all_rows))
    return result
