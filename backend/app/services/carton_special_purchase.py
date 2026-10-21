"""Read-only purchase document adapter over existing immutable special versions.

No new orders, issue rows or execution identities are created by viewing/exporting.
Only SEND and subsequent procurement revisions are purchase documents; receiving,
quotes, attachments and messages never become additional purchase quantities.
"""
import json
from decimal import Decimal
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import select
from app.models.carton_special_requests import SpecialRequest, SpecialVersion
from app.services import carton_special_requests as special
from app.services.carton_procurement_export import build_purchase_order_issue_workbook


def project_versions(row, events):
    result, previous = [], None
    for event in events:
        if event.action not in {"SEND", "ADJUSTED", "CANCEL"}:
            continue
        current = json.loads(event.snapshot_json)
        if previous is None and event.action != "SEND":
            continue
        if current.get("kind") not in {"SAMPLE", "WORKSHOP_MISC"}:
            continue
        before = {line["id"]: line for line in (previous or {}).get("lines", [])}
        after = {line["id"]: line for line in current.get("lines", [])}
        papers = []
        for identifier in dict.fromkeys([*after, *before]):
            old, new = before.get(identifier), after.get(identifier)
            source = new or old
            old_qty = Decimal(str(old["quantity"])) if old else Decimal(0)
            new_qty = Decimal(str(new["quantity"])) if new else Decimal(0)
            papers.append(dict(source, before_required_quantity=str(old_qty),
                               required_quantity_delta=str(new_qty - old_qty),
                               after_required_quantity=str(new_qty)))
            if old and new and any(old.get(key) != new.get(key) for key in ("packaging_type", "paper_quality", "specification", "dimension_unit", "unit")):
                papers[-1]["change_note"] = "原纸品：" + " · ".join(str(old.get(key, "")) for key in ("packaging_type", "paper_quality", "specification", "dimension_unit", "unit"))
        deltas = [Decimal(line["required_quantity_delta"]) for line in papers]
        kind = "INITIAL" if previous is None else "APPEND" if any(x > 0 for x in deltas) and all(x >= 0 for x in deltas) else "REDUCE" if any(x < 0 for x in deltas) and all(x <= 0 for x in deltas) else "ADJUSTMENT"
        cancelled = event.action == "CANCEL"
        snapshot = {"order": {"order_kind": current["kind"], "customer_name": current.get("customer_name", ""),
                              "supplier_name": "河源东康纸品有限公司", "note": current.get("purpose", "")},
                    "lines": papers, "before_due_date": (previous or {}).get("required_date", ""),
                    "after_due_date": current.get("required_date", "")}
        if cancelled:
            snapshot["cancellation"] = {"reason": current.get("reason", "")}
        if row.origin == "REPLENISHMENT":
            snapshot["special_replenishment"] = True
        issue = dict(id=event.id, factory_id=row.factory_id, order_no=row.request_no,
                     document_no=f"{row.request_no}-V{event.revision}", document_type=kind,
                     issue_sequence=len(result) + 1, source_order_revision=event.revision,
                     before_product_quantity=None, after_product_quantity=None, product_quantity_delta=None,
                     generated_by=event.actor_id, generated_by_name=event.actor_name,
                     generated_at=event.created_at, is_cancellation=cancelled,
                     is_replenishment=row.origin == "REPLENISHMENT", snapshot_json=json.dumps(snapshot, ensure_ascii=False))
        result.append(issue)
        previous = current
    return result


def issues(db, row):
    events = db.scalars(select(SpecialVersion).where(SpecialVersion.factory_id == row.factory_id,
        SpecialVersion.request_id == row.id).order_by(SpecialVersion.revision)).all()
    return project_versions(row, events)


def context(db, user, factory, identifier, *, external=False):
    row = special.access(db, user, factory, identifier, external=external)
    records = issues(db, row)
    return dict(factory_id=factory, order_no=row.request_no, order_revision=row.revision,
                pending_type="INITIAL" if not records and row.status == "SUBMITTED" else "NONE", pending_product_quantity=None,
                pending_line_count=0, can_generate=False, historical_baseline=False,
                latest_document_no=records[-1]["document_no"] if records else "",
                empty_reason="" if records else "订单尚未确认锁定，确认后可下载采购单。" if row.status == "SUBMITTED" else "此历史来源没有内部已发布采购版本；原订单、送货和收料记录继续保留。",
                issues=[{k: v for k, v in item.items() if k != "snapshot_json"} for item in reversed(records)])


def export(db, user, factory, identifier, version_id, *, external=False):
    row = special.access(db, user, factory, identifier, external=external)
    issue = next((item for item in issues(db, row) if item["id"] == version_id), None)
    if issue is None:
        raise HTTPException(404, "未找到此订单已发布采购版本")
    return build_purchase_order_issue_workbook(SimpleNamespace(**issue)), issue["document_no"] + ".xlsx"


def supplier_documents(db, user, factory):
    vendor = special.supplier(db, user, factory)
    result = []
    for row in db.scalars(select(SpecialRequest).where(SpecialRequest.factory_id == factory,
            SpecialRequest.supplier_id == vendor.id, SpecialRequest.kind.in_(["SAMPLE", "WORKSHOP_MISC"]),
            SpecialRequest.status != "SUBMITTED", ~special.deleted_predicate())):
        from app.services.carton_supplier_changes import special_confirmation
        confirmation = special_confirmation(db, row)
        records = issues(db, row)
        for issue in records:
            snap = json.loads(issue["snapshot_json"])
            business_kind = "SAMPLE" if row.kind == "SAMPLE" else "MISC"
            status = confirmation["status"] if issue["id"] == records[-1]["id"] else "HISTORICAL"
            acceptance = dict(status=status, label={"ACCEPTED": "已确认接单", "PENDING": "待确认接单",
                "DISPUTED": "有异议 · 待确认", "HISTORICAL": "历史采购版本", "CANCEL_ACKNOWLEDGED": "停止通知已回执"}.get(status, "待核实回执"),
                total_line_count=len(snap["lines"]), accepted_line_count=len(snap["lines"]) if status == "ACCEPTED" else 0,
                delivery_differences=[])
            result.append(dict(id=issue["id"], kind="PURCHASE", factory_id=factory,
                document_no=issue["document_no"], document_type=issue["document_type"], date=issue["generated_at"][:10],
                created_at=issue["generated_at"], status="已生成", replenishment=issue["is_replenishment"],
                is_cancellation=issue["is_cancellation"], special_request_id=row.id, supplier_acceptance=acceptance,
                orders=[dict(order_kind=business_kind, order_no=row.request_no, customer_name=snap["order"].get("customer_name", ""),
                             contract_no="", customer_po="", item_no="", product_name="", order_date=row.created_at[:10], planned_date=snap["after_due_date"])],
                lines=[dict(order_kind=business_kind, order_no=row.request_no, child_no=f"{row.request_no}/{line.get('line_no', index):02}",
                            packaging_type=line["packaging_type"], paper_quality=line["paper_quality"],
                            specification=f"{line['specification']} {line['dimension_unit']}", unit=line["unit"],
                            before_quantity=line["before_required_quantity"], change_quantity=line["required_quantity_delta"],
                            quantity=line["after_required_quantity"]) for index, line in enumerate(snap["lines"], 1)]))
    return result
