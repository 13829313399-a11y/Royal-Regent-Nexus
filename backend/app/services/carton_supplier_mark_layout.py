"""Customer layouts are versioned within an issued supplier/customer boundary."""
import base64
import hashlib
import io
import json
import re
from pathlib import Path
from uuid import uuid4
from functools import wraps
from threading import RLock

from fastapi import HTTPException
from pypdf import PdfReader
from sqlalchemy import select

from app.models.carton_mark import CartonMarkLayout
from app.models.carton_procurement import CartonOrder, CartonAuditEvent
from app.schemas.carton_supplier_portal import MarkLayoutConfig, SupplierMarkLayoutOut
from app.services import carton_supplier_portal as portal
from app.services.carton_mark_library import _now_text

_pdf_lock = RLock()


def serialized_pdf(operation):
    @wraps(operation)
    def call(*args, **kwargs):
        with _pdf_lock:
            return operation(*args, **kwargs)
    return call


def context(db, user, factory, order_id, issue_id, *, write=False):
    if write:
        portal.supplier_access(db, user, factory, "carton_supplier:edit")
    supplier, _, eligible = portal._supplier_mark_orders(db, user, factory)
    order = eligible.get(order_id)
    if not order:
        raise HTTPException(404, "未找到当前供应商的采购订单")
    if order["issue_id"] != issue_id:
        raise HTTPException(409, "采购订单已改版，请刷新后重新选择")
    model = db.get(CartonOrder, order_id)
    header = portal._purchase_order_snapshot(portal.latest_issue(db, model)).get("order", {})
    normalize = lambda value: " ".join(str(value or "").split()).casefold()
    code, name = normalize(header.get("customer_code")), normalize(order["customer_name"])
    if not name:
        raise HTTPException(422, "采购订单缺少客户名称，请先补齐订单")
    return dict(factory_id=factory, supplier_id=supplier.id, customer_key="code:" + code if code else "name:" + name,
        customer_name=order["customer_name"])


def rows(db, scope):
    return list(db.scalars(select(CartonMarkLayout).where(*(getattr(CartonMarkLayout, key) == scope[key]
        for key in ("factory_id", "supplier_id", "customer_key"))).order_by(CartonMarkLayout.version.desc())))


def output(row):
    return SupplierMarkLayoutOut(**{key: getattr(row, key) for key in
        ("id", "factory_id", "customer_name", "name", "version", "reference_name", "created_at")},
        config=MarkLayoutConfig.model_validate_json(row.config_json))


def frozen(row):
    content = bytes(row.reference_content)
    if len(content) != row.reference_size or hashlib.sha256(content).hexdigest() != row.reference_sha256:
        raise HTTPException(409, "客户历史稿完整性校验失败")
    return dict(id=row.id, name=row.name, version=row.version, config=json.loads(row.config_json),
        reference_bytes=content, reference_sha256=row.reference_sha256)


def current(db, user, factory, order_id, issue_id, identifier):
    scope = context(db, user, factory, order_id, issue_id, write=True)
    versions = rows(db, scope)
    if not versions or versions[0].id != identifier:
        raise HTTPException(409, "客户模板已更新或不存在，请刷新选择最新模板")
    return frozen(versions[0])


@serialized_pdf
def validate_reference(content, config):
    if not content or len(content) > 20 * 1024 * 1024:
        raise HTTPException(413, "历史 PDF 须为 1 字节至 20 MB")
    try:
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted or not 1 <= len(reader.pages) <= 20:
            raise ValueError("pages")
        if config.reference_page >= len(reader.pages):
            raise ValueError("page")
        page = reader.pages[config.reference_page]
        # PDFium returns the displayed crop/rotation dimensions used by the editor.
        import pypdfium2 as pdfium
        with pdfium.PdfDocument(content) as document:
            rendered = document[config.reference_page]
            try:
                width, height = (value * 25.4 / 72 for value in rendered.get_size())
            finally:
                rendered.close()
        if not 10 <= width <= 1000 or not 10 <= height <= 1000:
            raise ValueError("dimensions")
        for region in (config.logo_region, config.stamp_region):
            if region and (region.x + region.width > width + .01 or region.y + region.height > height + .01):
                raise ValueError("region")
        return width, height, len(reader.pages), page.extract_text() or ""
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, "历史稿须为有效未加密 PDF（最多 20 页），选取区域须位于页面内") from exc


@serialized_pdf
def reference_image(content, page=0):
    config = MarkLayoutConfig(reference_page=page)
    width, height, count, text = validate_reference(content, config)
    import pypdfium2 as pdfium
    with pdfium.PdfDocument(content) as document:
        rendered = document[page]
        try:
            bitmap = rendered.render(scale=1100 / max(rendered.get_size()))
            try:
                picture = bitmap.to_pil()
                stream = io.BytesIO(); picture.save(stream, "PNG"); picture.close()
            finally:
                bitmap.close()
        finally:
            rendered.close()
    return dict(preview_data_url="data:image/png;base64," + base64.b64encode(stream.getvalue()).decode(),
        page_width_mm=width, page_height_mm=height, page_count=count,
        suggested_side_address="\n".join(line.strip() for line in text.splitlines()
            if re.search(r"@|\b(?:rue|road|street|avenue|boulevard|postcode|postal)\b|(?:省|市|区|路|街)\S*\d", line, re.I))[:500])


@serialized_pdf
def crop_reference(content, page, region):
    """Exact artwork crop; never reuse historical variable text as a new order."""
    import pypdfium2 as pdfium
    with pdfium.PdfDocument(content) as document:
        rendered = document[page]
        try:
            scale = min(3, 2400 / max(rendered.get_size()))
            bitmap = rendered.render(scale=scale)
            try:
                picture = bitmap.to_pil()
                factor = 72 / 25.4 * scale
                cropped = picture.crop(tuple(round(v * factor) for v in
                    (region["x"], region["y"], region["x"] + region["width"], region["y"] + region["height"])))
                stream = io.BytesIO(); cropped.save(stream, "PNG"); cropped.close(); picture.close()
                return stream.getvalue()
            finally:
                bitmap.close()
        finally:
            rendered.close()


def save(db, user, scope, name, config, reference, expected_version):
    versions = rows(db, scope)
    version = versions[0].version if versions else 0
    if version != expected_version:
        raise HTTPException(409, "客户模板已改版，请刷新后再保存")
    filename, content = reference
    row = CartonMarkLayout(id="CML-" + uuid4().hex, **scope, name=name.strip() or scope["customer_name"] + "箱唛",
        version=version + 1, config_json=config.model_dump_json(), reference_name=Path(filename.replace("\\", "/")).name[:255],
        reference_content=content, reference_size=len(content), reference_sha256=hashlib.sha256(content).hexdigest(),
        created_by=user.id, created_by_name=user.display_name, created_at=_now_text())
    db.add(row)
    db.add(CartonAuditEvent(id="CAE-" + uuid4().hex, factory_id=scope["factory_id"], entity_type="carton_mark_layout",
        entity_id=row.id, event_type="CARTON_MARK_LAYOUT_CREATED", actor_user_id=user.id,
        actor_name=user.display_name, created_at=row.created_at, detail_json=json.dumps(dict(
            supplier_id=scope["supplier_id"], customer_key=scope["customer_key"], version=row.version,
            reference_sha256=row.reference_sha256, config_sha256=hashlib.sha256(row.config_json.encode()).hexdigest()))))
    db.commit()
    return output(row)
