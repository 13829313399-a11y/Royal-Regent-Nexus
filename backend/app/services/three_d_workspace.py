"""Bounded, permission-scoped queries for the modular workspace."""

from fastapi import HTTPException
from sqlalchemy import func, or_, select

from app.models import three_d_printing as m
from app.services import three_d_printing as business


def page(
    db,
    kind,
    *,
    page=1,
    page_size=50,
    q="",
    machine_no=0,
    state="",
    source="",
    date_from="",
    date_to="",
    quality="",
    customer="",
    material="",
    product_id="",
):
    kinds = {
        "products": (m.ThreeDPrintingProduct, business.product_out),
        "records": (m.ThreeDPrintingProductionRecord, business.production_record_out),
        "movements": (
            m.ThreeDPrintingInventoryMovement,
            business.inventory_movement_out,
        ),
        "schedules": (m.ThreeDPrintingSchedule, business.schedule_out),
        "maintenance": (m.ThreeDPrintingMaintenance, business.maintenance_out),
        "commands": (m.ThreeDPrintingPrinterCommand, business.command_out),
    }
    if kind not in kinds:
        raise HTTPException(404, {"code": "unknown_collection"})
    model, serialize = kinds[kind]
    filters = [model.factory_id == "huakang-a"]
    if kind == "products":
        filters.append(model.is_active.is_(True))
        image_exists = (
            select(m.ThreeDPrintingProductImage.id)
            .where(
                m.ThreeDPrintingProductImage.product_id == model.id,
                m.ThreeDPrintingProductImage.is_current.is_(True),
            )
            .exists()
        )
        if quality == "missing_image":
            filters.append(~image_exists)
        if quality == "incomplete":
            filters.append(
                or_(
                    model.weight_g <= 0,
                    model.material_name == "",
                    model.quoted_price <= 0,
                )
            )
        if quality == "duplicate":
            filters.append(
                model.name.in_(
                    select(m.ThreeDPrintingProduct.name)
                    .where(
                        m.ThreeDPrintingProduct.factory_id == "huakang-a",
                        m.ThreeDPrintingProduct.is_active.is_(True),
                    )
                    .group_by(m.ThreeDPrintingProduct.name)
                    .having(func.count() > 1)
                )
            )
    if kind == "records":
        filters.append(model.deleted_at == "")
        if quality == "pending":
            filters.append(model.reconciliation_status == "pending")
        elif quality:
            filters.append(model.data_quality_flags_json != "[]")
        if state:
            filters.append(model.run_status == state)
        if source:
            filters.append(model.source_system == source)
    fields = [
        getattr(model, name)
        for name in (
            "id",
            "name",
            "product_name",
            "current_file",
            "gcode_file",
            "customer",
            "material_name",
        )
        if hasattr(model, name)
    ]
    if q and fields:
        filters.append(or_(*(field.contains(q, autoescape=True) for field in fields)))
    for key, value in (("customer", customer), ("material_name", material)):
        if value and hasattr(model, key):
            filters.append(getattr(model, key).contains(value, autoescape=True))
    if machine_no and hasattr(model, "machine_no"):
        filters.append(model.machine_no == machine_no)
    if product_id and hasattr(model, "product_id"):
        filters.append(model.product_id == product_id)
    if hasattr(model, "business_date"):
        if date_from:
            filters.append(model.business_date >= date_from)
        if date_to:
            filters.append(model.business_date <= date_to)
    total = db.scalar(select(func.count()).select_from(model).where(*filters))
    sort = (
        model.name
        if kind == "products"
        else getattr(model, "created_at", model.id).desc()
    )
    rows = list(
        db.scalars(
            select(model)
            .where(*filters)
            .order_by(sort, model.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    if kind == "products":
        images = {
            image.product_id: image
            for image in db.scalars(
                select(m.ThreeDPrintingProductImage).where(
                    m.ThreeDPrintingProductImage.product_id.in_([r.id for r in rows]),
                    m.ThreeDPrintingProductImage.is_current.is_(True),
                )
            )
        }
        items = [serialize(row, images.get(row.id)) for row in rows]
    else:
        items = [serialize(row) for row in rows]
    if kind == "records":
        product_ids = {row.product_id for row in rows if row.product_id}
        images = {image.product_id: image for image in db.scalars(select(m.ThreeDPrintingProductImage).where(
            m.ThreeDPrintingProductImage.factory_id == "huakang-a",
            m.ThreeDPrintingProductImage.product_id.in_(product_ids),
            m.ThreeDPrintingProductImage.is_current.is_(True),
        ))}
        for item in items:
            image = images.get(item["product_id"])
            item["product_image_url"] = f"/api/three-d-printing/products/{image.product_id}/image?factory_id=huakang-a&v={image.sha256}" if image else ""
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def printer_detail(db, printer_id):
    printer = db.get(m.ThreeDPrintingPrinter, printer_id)
    if not printer or printer.factory_id != "huakang-a":
        raise HTTPException(404, {"code": "printer_not_found"})
    events = db.scalars(
        select(m.ThreeDPrintingPrinterStateEvent)
        .where(
            m.ThreeDPrintingPrinterStateEvent.printer_id == printer_id,
            m.ThreeDPrintingPrinterStateEvent.factory_id == "huakang-a",
        )
        .order_by(m.ThreeDPrintingPrinterStateEvent.received_at.desc())
        .limit(100)
    )
    commands = db.scalars(
        select(m.ThreeDPrintingPrinterCommand)
        .where(
            m.ThreeDPrintingPrinterCommand.printer_id == printer_id,
            m.ThreeDPrintingPrinterCommand.factory_id == "huakang-a",
        )
        .order_by(m.ThreeDPrintingPrinterCommand.requested_at.desc())
        .limit(50)
    )
    return {
        "printer": business.printer_out(printer),
        "events": [
            {
                "id": e.id,
                "state": e.state,
                "progress": e.progress,
                "observed_at": e.observed_at,
                "received_at": e.received_at,
            }
            for e in events
        ],
        "commands": [business.command_out(c) for c in commands],
    }
