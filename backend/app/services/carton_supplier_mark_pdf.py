"""Export supplier-visible originals without granting template or QC approval."""
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select

from app.core.config import settings
from app.models.carton_mark import CartonMarkAsset
from app.services import carton_mark_assets as assets
from app.services import carton_supplier_portal as portal
from app.services.carton_mark import MAX_DOCUMENT_FILE_BYTES
from app.services.carton_mark_library import _now_text
from app.services.carton_supplier_mark_check import check_source
from app.services import carton_supplier_mark_layout as layouts
from app.services.carton_mark_layout_renderer import render


def source(db, user, payload):
    original = check_source(db, user, payload.factory_id, payload.order_id,
        payload.issue_id, payload.excel_asset_id, payload.expected_revision)
    if not settings.document_tools_enabled:
        raise HTTPException(503, "文档转换服务暂未启用")
    content = original["excel_bytes"]
    if not content or len(content) > MAX_DOCUMENT_FILE_BYTES:
        raise HTTPException(413, "Excel 文件须为 1 字节至 20 MB")
    if hashlib.sha256(content).hexdigest() != original["excel_sha256"]:
        raise HTTPException(409, "Excel 原稿完整性校验失败，请联系仓库核实")
    if Path(original["excel_file_name"]).suffix.lower() not in {".xls", ".xlsx"}:
        raise HTTPException(422, "目前支持 .xls / .xlsx，请将其他 Excel 格式另存为 .xlsx")
    original["layout"] = layouts.current(db, user, payload.factory_id, payload.order_id, payload.issue_id, payload.layout_id)
    return original


def prepare_pdf(original):
    # Render outside the business transaction, without modifying originals.
    return render(original)


def save_pdf(db, user, payload, original, prepared):
    # The caller holds the factory lock. Binding/archive also lock this row.
    db.scalar(select(CartonMarkAsset).where(CartonMarkAsset.id == payload.excel_asset_id,
        CartonMarkAsset.factory_id == payload.factory_id).with_for_update())
    current = source(db, user, payload)
    if current != original:
        raise HTTPException(409, "订单或 Excel 资料已变更，请刷新后重新生成")
    content, pages, warnings = prepared
    timestamp = _now_text()
    name = Path(original["excel_file_name"]).stem[:230] + "_排版.pdf"
    asset = CartonMarkAsset(id=f"CMA-{uuid4().hex}", factory_id=payload.factory_id,
        file_name=name, kind="pdf", content_type="application/pdf", content=content,
        size_bytes=len(content), sha256=hashlib.sha256(content).hexdigest(),
        contract_number=original["contract_no"], bound_order_id=payload.order_id,
        recognition_source="manual_order", candidates_json="[]",
        warning="由 Excel 生成，尚未核对或审核", revision=1, is_archived=False,
        created_by=user.id, created_by_name=user.display_name, created_at=timestamp, updated_at=timestamp)
    db.add(asset)
    db.flush()
    assets.audit(db, user, asset, "CARTON_MARK_ASSET_CREATED", dict(sha256=asset.sha256,
        contract_number=asset.contract_number, conversion=dict(method="customer_layout",
            source_asset_id=original["excel_asset_id"], source_revision=original["asset_revision"],
            source_sha256=original["excel_sha256"], page_count=pages,
            layout_id=payload.layout_id, layout_version=original["layout"]["version"],
            layout_reference_sha256=original["layout"]["reference_sha256"],
            layout_config_sha256=hashlib.sha256(json.dumps(original["layout"]["config"], sort_keys=True).encode()).hexdigest()),
        supplier_context=dict(supplier_id=original["supplier_id"], order_id=payload.order_id,
            issue_id=payload.issue_id, source="supplier_excel_to_pdf")))
    row = next((row for row in portal.supplier_mark_assets(db, user, payload.factory_id) if row["id"] == asset.id), None)
    if row is None:
        raise HTTPException(409, "订单资料范围已变更，请刷新后重试")
    db.commit()
    return dict(asset=row, page_count=pages, warnings=warnings, layout_id=payload.layout_id,
        layout_name=original["layout"]["name"], layout_version=original["layout"]["version"])
