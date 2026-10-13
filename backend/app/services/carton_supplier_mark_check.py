"""Supplier PDF checks reuse the template workflow without internal warehouse privileges."""
import json
from fastapi import HTTPException
from sqlalchemy import select
from app.models.carton_mark import CartonMarkAsset, CartonMarkDocument, CartonMarkTemplate
from app.models.carton_procurement import CartonAuditEvent, CartonOrder
from app.schemas.carton_supplier_portal import SupplierMarkCheckOut
from app.services import carton_supplier_portal as portal
from app.services.carton_mark_library import _persist_carton_mark_template, _template_out


def check_source(db, user, factory, order_id, issue_id, asset_id, revision, *, lock=False):
    supplier = portal.supplier_access(db, user, factory, "carton_supplier:edit")
    if lock:
        # Asset binding/archive uses row updates; retain its boundary until the
        # template pair commits, including on PostgreSQL where the factory lock
        # alone does not serialize asset maintenance.
        db.scalar(select(CartonMarkAsset).where(CartonMarkAsset.id == asset_id,
            CartonMarkAsset.factory_id == factory).with_for_update())
    for asset, orders in portal._supplier_mark_assets(db, user, factory):
        if asset.id != asset_id:
            continue
        order = next((row for row in orders if row["id"] == order_id), None)
        if order is None:
            break
        if asset.kind != "excel":
            raise HTTPException(422, "请选择仓库共享的客人 Excel")
        if asset.revision != revision or order["issue_id"] != issue_id:
            raise HTTPException(409, "订单或 Excel 资料已变更，请刷新后重新选择")
        return dict(factory_id=factory, supplier_id=supplier.id, order_id=order_id,
            issue_id=issue_id, excel_asset_id=asset.id, asset_revision=asset.revision,
            excel_sha256=asset.sha256, excel_file_name=asset.file_name,
            excel_bytes=bytes(asset.content), **{key: order[key] for key in
                ("customer_name", "contract_no", "customer_po", "item_no")})
    raise HTTPException(404, "未找到此订单可用于核对的 Excel 资料")


def save_check(db, user, source, pdf_bytes, result):
    context = {key: source[key] for key in ("supplier_id", "order_id", "issue_id",
        "excel_asset_id", "asset_revision", "excel_sha256")}
    context.update({key: source[key] for key in ("pdf_asset_id", "pdf_asset_revision", "pdf_sha256") if key in source})
    record = _persist_carton_mark_template(db, user,
        factory_id=source["factory_id"], customer_name=source["customer_name"],
        po=source["customer_po"], item=source["item_no"], contract_number=source["contract_no"],
        excel_file_name=source["excel_file_name"], excel_bytes=source["excel_bytes"],
        pdf_file_name=result.pdf_file_name, pdf_bytes=pdf_bytes, check_result=result,
        supplier_context=context)
    return _check_out(record, context)


def check_pdf_source(db, user, factory, order_id, issue_id, asset_id, revision):
    portal.supplier_access(db, user, factory, "carton_supplier:edit")
    for asset, orders in portal._supplier_mark_assets(db, user, factory):
        if asset.id != asset_id or not any(order["id"] == order_id for order in orders):
            continue
        if asset.kind != "pdf":
            raise HTTPException(422, "请选择此订单的打印 PDF")
        if asset.revision != revision or not any(order["id"] == order_id and order["issue_id"] == issue_id for order in orders):
            raise HTTPException(409, "订单或 PDF 资料已变更，请刷新后重新选择")
        return dict(pdf_asset_id=asset.id, pdf_asset_revision=asset.revision, pdf_sha256=asset.sha256,
            pdf_file_name=asset.file_name, pdf_bytes=bytes(asset.content))
    raise HTTPException(404, "未找到此订单可用于核对的 PDF 资料")


def _check_out(record, context):
    # Keep internal reviewers, release reasons and employee identities private.
    return SupplierMarkCheckOut(**{key: getattr(record, key) for key in (
        "id", "factory_id", "customer_name", "po", "item", "contract_number", "version",
        "check_status", "manual_released", "qc_ready", "excel_file_name", "pdf_file_name",
        "created_at", "check_result")}, **{key: context[key] for key in
        ("order_id", "issue_id", "excel_asset_id")})


def visible_checks(db, user, factory):
    supplier = portal.supplier_access(db, user, factory)
    own_orders = {}
    for order in db.scalars(select(CartonOrder).where(CartonOrder.factory_id == factory,
            CartonOrder.supplier_id == supplier.id, CartonOrder.deleted_at.is_(None),
            CartonOrder.status.in_(portal.OPEN_STATES | {"COMPLETED"}))):
        issue = portal.latest_issue(db, order)
        header = portal._purchase_order_snapshot(issue).get("order", {}) if issue else {}
        if not isinstance(header, dict) or header.get("supplier_id") != supplier.id:
            continue
        own_orders[order.id] = portal._mark_identity(str(header.get("customer_name") or ""),
            str(header.get("customer_po") or header.get("contract_no") or ""),
            str(header.get("item_no") or ""), str(header.get("contract_no") or ""))
    if not own_orders:
        return []
    templates = {record.id: record for record in db.scalars(select(CartonMarkTemplate).where(
        CartonMarkTemplate.factory_id == factory, CartonMarkTemplate.is_archived.is_(False)))}
    result = []
    for event in db.scalars(select(CartonAuditEvent).where(CartonAuditEvent.factory_id == factory,
            CartonAuditEvent.entity_type == "carton_mark_template",
            CartonAuditEvent.event_type == "CARTON_MARK_TEMPLATE_CREATED",
            CartonAuditEvent.entity_id.in_(templates))):
        context = json.loads(event.detail_json).get("supplier_context", {})
        record = templates[event.entity_id]
        if context.get("supplier_id") != supplier.id or own_orders.get(context.get("order_id")) != portal._mark_identity(
                record.customer_name, record.po or record.contract_number, record.item, record.contract_number):
            continue
        documents = {row.kind: row for row in db.scalars(select(CartonMarkDocument).where(
            CartonMarkDocument.factory_id == factory, CartonMarkDocument.template_id == record.id))}
        if "print_pdf" in documents:
            result.append((_check_out(_template_out(record, documents), context), documents))
    return sorted(result, key=lambda row: (row[0].created_at, row[0].id), reverse=True)


def check_document(db, user, factory, identifier, kind):
    if kind not in {"source_excel", "print_pdf"}:
        raise HTTPException(422, "箱唛文档类型无效")
    for record, documents in visible_checks(db, user, factory):
        if record.id == identifier:
            if kind in documents:
                return documents[kind]
            raise HTTPException(404, "此人工审核资料没有 Excel 原稿")
    raise HTTPException(404, "未找到可查看的供应商核对资料")
