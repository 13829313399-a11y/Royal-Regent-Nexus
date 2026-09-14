"""Versioned handover checks; actual PMC receipt is outside this domain."""
from datetime import date
from typing import Annotated
from pydantic import Field
from sqlalchemy import select
from app.models.uv_handover import UvHandover
from app.models import uv_printing as core_models
from app.schemas.uv_printing import Command, Id, Qty, COMMAND_SCHEMAS
from app.services import uv_printing as core


class HandoverInput(Command):
    id: Id | None = None
    business_date: date
    report_id: Id | None = None
    product_id: Id
    received_qty: Qty
    receiver: Annotated[str, Field(max_length=128)] = ""
    note: Annotated[str, Field(max_length=4000)] = ""


def output(db, factory, row):
    value = core.serial(row, ("created_by",))
    if row.report_id:
        report = core.find(db, core_models.UvReport, factory, row.report_id)
        if report.status not in core.ACTIVE:
            value["state"] = "pending"
            value["source_stale"] = True
            value["source_warning"] = "关联报工已修订或作废，请关联有效报工重新核数；原比较数量保留"
    return value


def save(db, factory, actor, payload):
    row = core.find(db, UvHandover, factory, payload["id"]) if payload.get("id") else None
    core.version(row, payload["expected_version"])
    if row:
        core.guard_open(db, factory, row.business_date)
    core.guard_open(db, factory, payload["business_date"])
    product = core.find(db, core_models.UvProduct, factory, payload["product_id"])
    report = core.find(db, core_models.UvReport, factory, payload["report_id"]) if payload.get("report_id") else None
    if report:
        if report.product_id != product.id or report.business_date != payload["business_date"]:
            core.fail("关联报工必须与核数的产品和业务日期一致")
        if report.status not in core.ACTIVE:
            core.fail("只能核数已确认的有效报工；草稿、作废或被修订报工不可核数", 409)
    reported = report.reported_qty if report else 0
    difference = payload["received_qty"] - reported
    state = "pending" if report is None or not payload["receiver"].strip() else "difference" if difference else "reconciled"
    values = dict(business_date=payload["business_date"], product_id=product.id, report_id=report.id if report else None,
        product_no=report.product_no if report else product.product_no, product_name=report.product_name if report else product.name,
        reported_qty=reported, received_qty=payload["received_qty"], difference_qty=difference,
        state=state, receiver=payload["receiver"].strip(), note=payload["note"])
    if row:
        for key, value in values.items():
            setattr(row, key, value)
        core.bump(row)
    else:
        row = UvHandover(factory_id=factory, created_by=actor, **values)
        db.add(row)
    db.flush()
    return output(db, factory, row)


def list_rows(db, factory, scope):
    query = select(UvHandover).where(UvHandover.factory_id == factory)
    for key, expression in (("business_date", UvHandover.business_date == scope.get("business_date")),
            ("date_from", UvHandover.business_date >= (scope.get("date_from") or "")),
            ("date_to", UvHandover.business_date <= (scope.get("date_to") or "9999-12-31")),
            ("product_id", UvHandover.product_id == scope.get("product_id"))):
        if scope.get(key):
            query = query.where(expression)
    if scope.get("machine_id") or scope.get("shift"):
        query = query.join(core_models.UvReport, core_models.UvReport.id == UvHandover.report_id)
        if scope.get("machine_id"):
            query = query.where(core_models.UvReport.machine_id == scope["machine_id"])
        if scope.get("shift"):
            query = query.where(core_models.UvReport.shift == scope["shift"])
    if scope.get("q"):
        from sqlalchemy import or_
        query = query.where(or_(UvHandover.product_no.contains(scope["q"], autoescape=True), UvHandover.product_name.contains(scope["q"], autoescape=True), UvHandover.receiver.contains(scope["q"], autoescape=True)))
    rows = [output(db, factory, row) for row in db.scalars(query.order_by(UvHandover.business_date.desc(), UvHandover.created_at.desc(), UvHandover.id))]
    if scope.get("status"):
        rows = [row for row in rows if row["state"] == scope["status"]]
    return rows


def summary_counts(db, factory, scope):
    return {"handover_differences": sum(row["state"] == "difference" or row.get("source_stale", False) for row in list_rows(db, factory, {k: v for k, v in scope.items() if k != "status"}))}


COMMAND_SCHEMAS["handover-save"] = HandoverInput
core.ACTIONS["handover-save"] = save
