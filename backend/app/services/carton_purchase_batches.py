"""Warehouse confirmation batches carried by immutable first-issue snapshots."""
from __future__ import annotations

import json
import re
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select

from app.models.carton_procurement import CartonPurchaseOrderIssue


def new_purchase_batch(orders, timestamp):
    token = uuid4().hex
    issue_ids = [f"CPOI-{token}", *[f"CPOI-{uuid4().hex}" for _ in orders[1:]]]
    return {
        "id": f"CPB-{token}",
        "document_no": f"CG-{timestamp[:10].replace('-', '')[2:]}-{token[:10].upper()}",
        "factory_id": orders[0].factory_id,
        "supplier_id": orders[0].supplier_id,
        "generated_at": timestamp,
        "issue_ids": issue_ids,
    }


def purchase_batch(issue):
    batch = json.loads(issue.snapshot_json).get("purchase_batch")
    if batch is None:
        return None
    if (not isinstance(batch, dict)
            or not re.fullmatch(r"CPB-[a-f0-9]{32}", str(batch.get("id", "")))
            or batch.get("factory_id") != issue.factory_id
            or not batch.get("supplier_id")
            or not isinstance(batch.get("document_no"), str)
            or not batch["document_no"]
            or not isinstance(batch.get("generated_at"), str)):
        raise HTTPException(409, "合并采购单记录不完整，请核对原采购单")
    members = batch.get("issue_ids")
    if (not isinstance(members, list) or not 2 <= len(members) <= 100
            or any(not isinstance(member, str) for member in members)
            or len(set(members)) != len(members) or issue.id not in members
            or members[0] != "CPOI-" + batch["id"][4:]
            or issue.document_type != "INITIAL"):
        raise HTTPException(409, "合并采购单明细不完整，请核对原采购单")
    return batch


def purchase_batch_out(issue):
    batch = purchase_batch(issue)
    return {key: batch[key] for key in ("id", "document_no", "generated_at")} | {
        "order_count": len(batch["issue_ids"]),
    } if batch else None


def load_purchase_batch(db, factory_id, batch_id):
    if not re.fullmatch(r"CPB-[a-f0-9]{32}", batch_id):
        raise HTTPException(404, "合并采购单不存在")
    anchor = db.get(CartonPurchaseOrderIssue, "CPOI-" + batch_id[4:])
    if anchor is None or anchor.factory_id != factory_id:
        raise HTTPException(404, "合并采购单不存在")
    batch = purchase_batch(anchor)
    if batch is None or batch["id"] != batch_id:
        raise HTTPException(404, "合并采购单不存在")
    issues = {issue.id: issue for issue in db.scalars(select(CartonPurchaseOrderIssue).where(
        CartonPurchaseOrderIssue.factory_id == factory_id,
        CartonPurchaseOrderIssue.id.in_(batch["issue_ids"]),
    )).all()}
    if (set(issues) != set(batch["issue_ids"])
            or any(purchase_batch(issue) != batch for issue in issues.values())
            or len({issue.order_id for issue in issues.values()}) != len(issues)):
        raise HTTPException(409, "合并采购单明细不完整，请核对原采购单")
    return batch, [issues[issue_id] for issue_id in batch["issue_ids"]]


def group_purchase_documents(rows, batches):
    """Only an explicitly recorded batch can combine supplier-visible snapshots."""
    by_id = {row["id"]: row for row in rows}
    grouped = []
    consumed = set()
    for row in rows:
        if row["id"] in consumed:
            continue
        batch = batches.get(row["id"])
        if not batch or not all(
            member in by_id and batches.get(member) == batch
            for member in batch["issue_ids"]
        ):
            grouped.append(row)
            continue
        sources = [by_id[member] for member in batch["issue_ids"]]
        grouped.append({
            **row, "id": batch["id"], "document_no": batch["document_no"],
            "created_at": batch["generated_at"], "date": batch["generated_at"][:10],
            "is_batch": True,
            "source_documents": [{"id": source["id"], "document_no": source["document_no"],
                                  "order_no": source["orders"][0]["order_no"]} for source in sources],
            "orders": [order for source in sources for order in source["orders"]],
            "lines": [{**line, "source_document_no": source["document_no"]}
                      for source in sources for line in source["lines"]],
        })
        consumed.update(batch["issue_ids"])
    return grouped
