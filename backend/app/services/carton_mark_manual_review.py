"""Original-only review: explicit order, immutable reference and internal release."""
import hashlib
import zlib
from io import BytesIO

from fastapi import HTTPException
from PIL import Image, ImageOps
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject, NumberObject, StreamObject
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from app.models.carton_mark import CartonMarkAsset
from app.schemas.carton_mark import CartonMarkDocumentCheckResponse
from app.services import carton_mark_assets as assets
from app.services.auth import authorization_decision, get_current_user
from app.services.carton_mark import validate_carton_mark_document_file
from app.services.carton_mark_library import (
    CARTON_MARK_READ_DEPARTMENTS, CARTON_MARK_WRITE_DEPARTMENTS,
    CartonMarkDocumentDownload, _persist_carton_mark_template,
)
from app.services.carton_procurement import _lock_receipt_factory, require_carton_factory

def scope(user, factory, permission="carton_mark:template_upload"):
    factory = require_carton_factory(factory)
    departments = CARTON_MARK_READ_DEPARTMENTS if permission == "carton_mark:read" else CARTON_MARK_WRITE_DEPARTMENTS
    if not any(authorization_decision(user, permission, factory, dep)[0] for dep in departments):
        raise HTTPException(403, "没有当前厂区箱唛资料审核权限")
    return factory


def source(db, user, payload, supplier=False):
    factory = require_carton_factory(payload.factory_id)
    if payload.approve:
        if supplier:
            raise HTTPException(403, "供应商只能提交资料，审核通过需由有权限的内部人员操作")
        scope(user, factory, "carton_mark:template_release")
    if len({row.id for row in payload.assets}) != len(payload.assets):
        raise HTTPException(422, "同一原文件不能重复选择")
    if supplier:
        from app.services import carton_supplier_portal as portal
        owner = portal.supplier_access(db, user, factory, "carton_supplier:edit")
        visible = {asset.id: (asset, orders) for asset, orders in portal._supplier_mark_assets(db, user, factory)}
        context = dict(supplier_id=owner.id, order_id=payload.order_id, issue_id=payload.issue_id, excel_asset_id="")
    else:
        scope(user, factory)
        scope(user, factory, "carton_mark:read")
        orders = assets.available_orders(db, factory)
        visible = {ref.id: (asset, assets.asset_out(asset, orders).orders if assets.asset_out(asset, orders).binding_status == "BOUND" else [])
                   for ref in payload.assets for asset in [assets.active_asset(db, factory, ref.id)]}
        context = None
    selected, identity = [], None
    for ref in payload.assets:
        candidate = visible.get(ref.id)
        if not candidate:
            raise HTTPException(404, "未找到当前订单可审核的原文件")
        asset, orders = candidate
        order = next((row for row in orders if (row["id"] if isinstance(row, dict) else row.id) == payload.order_id), None)
        if order is None:
            raise HTTPException(422, "每个原文件必须明确关联本次审核的同一订单")
        if asset.revision != ref.revision:
            raise HTTPException(409, "原文件或关联订单已变化，请刷新后重新选择")
        if asset.kind not in {"pdf", "image"}:
            raise HTTPException(422, "人工审核请选择一个 PDF 或一组图片；Excel / PDF 请使用内容核对")
        content = bytes(asset.content)
        if hashlib.sha256(content).hexdigest() != asset.sha256:
            raise HTTPException(409, "原文件完整性校验失败")
        if supplier:
            if order["issue_id"] != payload.issue_id:
                raise HTTPException(409, "采购订单版本已变化，请重新选择")
            current = {key: order[key] for key in ("customer_name", "customer_po", "contract_no", "item_no")}
        else:
            current_order = next(row for row in orders_all(db, factory) if row.id == payload.order_id)
            current = {key: getattr(current_order, key) for key in ("customer_name", "customer_po", "contract_no", "item_no")}
        if identity is not None and identity != current:
            raise HTTPException(409, "资料的订单归属发生变化")
        identity = current
        selected.append(dict(id=asset.id, revision=asset.revision, kind=asset.kind,
            file_name=asset.file_name, sha256=asset.sha256, content_type=asset.content_type, content=content))
    if any(row["kind"] == "pdf" for row in selected) and (len(selected) != 1 or selected[0]["kind"] != "pdf"):
        raise HTTPException(422, "单 PDF 请单独提交；多张图片可按选择顺序一起提交")
    if sum(len(row["content"]) for row in selected) > 100 * 1024 * 1024:
        raise HTTPException(413, "本次审核原文件合计不能超过 100 MB")
    return dict(factory=factory, identity=identity, selected=selected, context=context, order_id=payload.order_id)


def orders_all(db, factory):
    return assets.available_orders(db, factory)


def reference_pdf(selected):
    if selected[0]["kind"] == "pdf":
        row = selected[0]
        validate_carton_mark_document_file(row["file_name"], row["content"], kind="pdf")
        reader = PdfReader(BytesIO(row["content"]), strict=False)
        if reader.is_encrypted or not 1 <= len(reader.pages) <= 100:
            raise HTTPException(422, "请使用可读取的 1–100 页 PDF")
        return row["file_name"], row["content"]
    writer = PdfWriter()
    for row in selected:
        assets.validate_asset_image(row["file_name"], row["content"])
        with Image.open(BytesIO(row["content"])) as original:
            image = ImageOps.exif_transpose(original).convert("RGBA")
            white = Image.new("RGB", image.size, "white")
            white.paste(image, mask=image.getchannel("A"))
            # Preserve pixels and aspect ratio. These page sizes are references,
            # never a physical-size production or 1:1 printing declaration.
            image_stream = StreamObject()
            image_stream.set_data(zlib.compress(white.tobytes()))
            image_stream.update({NameObject("/Type"): NameObject("/XObject"),
                NameObject("/Subtype"): NameObject("/Image"), NameObject("/Width"): NumberObject(white.width),
                NameObject("/Height"): NumberObject(white.height), NameObject("/ColorSpace"): NameObject("/DeviceRGB"),
                NameObject("/BitsPerComponent"): NumberObject(8), NameObject("/Filter"): NameObject("/FlateDecode")})
            page = writer.add_blank_page(width=white.width, height=white.height)
            page[NameObject("/Resources")] = DictionaryObject({NameObject("/XObject"): DictionaryObject({
                NameObject("/Im0"): writer._add_object(image_stream)})})
            drawing = StreamObject()
            drawing.set_data(f"q {white.width} 0 0 {white.height} 0 0 cm /Im0 Do Q".encode("ascii"))
            page[NameObject("/Contents")] = writer._add_object(drawing)
            white.close()
            image.close()
    output = BytesIO()
    writer.write(output)
    return "图片审核参考.pdf", output.getvalue()


async def create_review(request, db, user, payload, supplier=False):
    initial = source(db, user, payload, supplier)
    db.rollback()
    try:
        name, pdf = await run_in_threadpool(reference_pdf, initial["selected"])
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, "原文件无法整理为审核参考，请检查文件是否损坏或加密") from exc
    _lock_receipt_factory(db, initial["factory"])
    user = get_current_user(request, db)
    list(db.scalars(select(CartonMarkAsset).where(CartonMarkAsset.factory_id == initial["factory"],
        CartonMarkAsset.id.in_([row.id for row in payload.assets])).order_by(CartonMarkAsset.id).with_for_update()))
    current = source(db, user, payload, supplier)
    if initial != current:
        raise HTTPException(409, "整理期间订单或原文件已变化，请重新选择")
    result = CartonMarkDocumentCheckResponse(excel_file_name="", pdf_file_name=name,
        summary=dict(overall_status="需复核", pass_count=0, changed_count=0, missing_count=0, unexpected_count=0, review_count=1),
        excel_items=[], pdf_items=[], comparisons=[], extraction=[], review_method="manual_sources",
        review_note=payload.note.strip(), review_order_id=payload.order_id,
        source_assets=[{key: row[key] for key in ("id", "revision", "kind", "file_name", "sha256")} for row in current["selected"]])
    identity = current["identity"]
    record = _persist_carton_mark_template(db, user, factory_id=current["factory"],
        customer_name=identity["customer_name"], po=identity["customer_po"], item=identity["item_no"],
        contract_number=identity["contract_no"], excel_file_name="", excel_bytes=b"", pdf_file_name=name,
        pdf_bytes=pdf, check_result=result, supplier_context=current["context"], commit=not payload.approve)
    if payload.approve:
        from app.services.carton_mark_library import manually_release_carton_mark_template
        record = manually_release_carton_mark_template(db, user, factory_id=current["factory"],
            template_id=record.id, reason="")
    if supplier:
        from app.services.carton_supplier_mark_check import _check_out
        return _check_out(record, current["context"])
    return record


def original_source(db, factory, source_assets, asset_id):
    expected = next((row for row in source_assets if row["id"] == asset_id), None)
    asset = db.scalar(select(CartonMarkAsset).where(CartonMarkAsset.id == asset_id, CartonMarkAsset.factory_id == factory))
    if not expected or asset is None:
        raise HTTPException(404, "未找到此审核版本的原文件")
    content = bytes(asset.content)
    if asset.sha256 != expected["sha256"] or hashlib.sha256(content).hexdigest() != expected["sha256"]:
        raise HTTPException(409, "审核原件完整性校验失败")
    return CartonMarkDocumentDownload(expected["file_name"], asset.content_type, len(content), expected["sha256"], content)


def validate_release(db, user, factory, template, result):
    scope(user, factory, "carton_mark:template_release")
    order = next((row for row in orders_all(db, factory) if row.id == result.review_order_id), None)
    if order is None or tuple(" ".join(str(value or "").strip().split()) for value in (
            order.customer_name, order.customer_po, order.item_no, order.contract_no)) != (
            template.customer_name, template.po, template.item, template.contract_number):
        raise HTTPException(409, "审核订单已取消、删除或业务资料已变化，请重新提交审核")
    for row in result.source_assets:
        original_source(db, factory, result.source_assets, row["id"])
