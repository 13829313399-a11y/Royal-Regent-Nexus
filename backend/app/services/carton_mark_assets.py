"""Contract-based source repository, independent of approved QC templates."""
import hashlib
import json
import re
import unicodedata
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.models.carton_mark import CartonMarkAsset
from app.models.carton_procurement import CartonAuditEvent, CartonOrder
from app.schemas.carton_mark import CartonMarkAssetOut, CartonMarkAssetOrderOut
from app.services.carton_mark import (
    CartonMarkDocumentConfigurationError, CartonMarkDocumentError,
    extract_excel_document_items, validate_carton_mark_document_file,
)
from app.services.carton_mark_library import _excel_content_type, _now_text


def identity(value):
    return " ".join(unicodedata.normalize("NFKC", value).strip().split()).casefold()


def available_orders(db, factory):
    return list(db.scalars(select(CartonOrder).where(
        CartonOrder.factory_id == factory, CartonOrder.deleted_at.is_(None),
        CartonOrder.status != "CANCELLED")))


def recognize_asset(file_name, content, known_contracts):
    # Windows and POSIX upload paths both reduce to a harmless original basename.
    safe_name = Path((file_name or "").replace("\\", "/")).name
    kind = "pdf" if Path(safe_name).suffix.lower() == ".pdf" else "excel"
    safe_name = validate_carton_mark_document_file(safe_name, content, kind=kind)
    if len(safe_name) > 255:
        raise CartonMarkDocumentError("文件名不能超过 255 个字符")
    warning = ""
    if kind == "excel":
        try:
            extracted = extract_excel_document_items(safe_name, content)
            text = "\n".join(item.text for item in extracted.items)
        except CartonMarkDocumentConfigurationError:
            text, warning = "", "正文读取组件未就绪，已按文件名识别，可手工关联。"
    else:
        from pypdf import PdfReader
        try:
            reader = PdfReader(BytesIO(content), strict=False)
            if len(reader.pages) > 100 or not reader.pages:
                raise CartonMarkDocumentError("PDF 页数必须为 1–100 页")
            text = "\n".join((page.extract_text() or "")[:50000] for page in reader.pages)
            if not text.strip():
                warning = "PDF 没有可读取文字，已按文件名识别，可手工关联。"
        except CartonMarkDocumentError:
            raise
        except Exception as exc:
            raise CartonMarkDocumentError("PDF 无法读取，请检查是否损坏或加密") from exc
    stem = unicodedata.normalize("NFKC", Path(safe_name).stem).strip()
    stem = re.sub(r"[ _-]*(?:shipping[ _-]*marks?|carton[ _-]*marks?|箱唛|打印版|正唛|侧唛)(?:[ _-]*\(\d+\))?$", "", stem, flags=re.I)
    sources = {}
    if len(stem) >= 5 and len(stem) <= 128 and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", stem) and re.search(r"\d", stem):
        sources[identity(stem)] = (stem, "filename")
    for candidate in re.findall(r"(?:合同(?:编号|号)?|CONTRACT\s*(?:NO\.?|NUMBER|#)?)\s*[:：#]?\s*([A-Za-z0-9][A-Za-z0-9._/-]{3,127})", text, flags=re.I):
        sources[identity(candidate)] = (candidate, "document")
    normalized_text = unicodedata.normalize("NFKC", text)
    for contract in known_contracts:
        if len(contract) < 5:
            continue
        if re.search(r"(?<![\w./-])" + re.escape(contract) + r"(?![\w./-])", normalized_text, re.I):
            sources.setdefault(identity(contract), (contract, "order_contract"))
    values = sorted(sources.values())
    contract, source = values[0] if len(values) == 1 else ("", "")
    if len(values) > 1:
        warning = "识别到多个合同号，请选择订单或手工确认合同号。"
    return dict(file_name=safe_name, kind=kind, contract_number=contract,
                recognition_source=source, candidates=[v[0] for v in values], warning=warning)


def asset_out(asset, orders):
    matches = [o for o in orders if identity(o.contract_no) == identity(asset.contract_number)] if asset.contract_number else []
    if asset.recognition_source == "manual_order" or asset.bound_order_id:
        matches = [o for o in matches if o.id == asset.bound_order_id]
    ambiguous = not asset.bound_order_id and len({identity(o.customer_code) for o in matches}) > 1
    status = "AMBIGUOUS" if ambiguous else "BOUND" if matches else "NO_ORDER" if asset.contract_number else "UNBOUND"
    return CartonMarkAssetOut(id=asset.id, factory_id=asset.factory_id, file_name=asset.file_name,
        kind=asset.kind, size_bytes=asset.size_bytes, sha256=asset.sha256,
        contract_number=asset.contract_number, bound_order_id=asset.bound_order_id,
        recognition_source=asset.recognition_source, candidates=json.loads(asset.candidates_json),
        warning=asset.warning, binding_status=status, revision=asset.revision,
        created_by_name=asset.created_by_name, created_at=asset.created_at,
        orders=[CartonMarkAssetOrderOut(id=o.id, order_no=o.order_no, contract_no=o.contract_no,
            customer_name=o.customer_name, item_no=o.item_no) for o in matches])


def active_asset(db, factory, asset_id):
    asset = db.scalar(select(CartonMarkAsset).where(CartonMarkAsset.id == asset_id,
        CartonMarkAsset.factory_id == factory, CartonMarkAsset.is_archived.is_(False)))
    if asset is None:
        raise HTTPException(404, "未找到箱唛原文件")
    return asset


def list_assets(db, factory, order_id=None):
    orders = available_orders(db, factory)
    if order_id and not any(o.id == order_id for o in orders):
        raise HTTPException(404, "未找到本厂订单")
    assets = db.scalars(select(CartonMarkAsset).where(CartonMarkAsset.factory_id == factory,
        CartonMarkAsset.is_archived.is_(False)).order_by(CartonMarkAsset.created_at.desc(), CartonMarkAsset.id))
    result = [asset_out(asset, orders) for asset in assets]
    if order_id:
        result = [asset for asset in result if asset.binding_status == "BOUND" and any(o.id == order_id for o in asset.orders)]
    return result


def audit(db, user, asset, event, detail):
    db.add(CartonAuditEvent(id=f"CAE-{uuid4().hex}", factory_id=asset.factory_id,
        event_type=event, entity_type="carton_mark_asset", entity_id=asset.id,
        detail_json=json.dumps(detail, ensure_ascii=False, sort_keys=True), actor_user_id=user.id,
        actor_name=user.display_name, created_at=_now_text()))


def save_asset(db, user, factory, content, recognition):
    sha = hashlib.sha256(content).hexdigest()
    previous = db.scalar(select(CartonMarkAsset).where(CartonMarkAsset.factory_id == factory, CartonMarkAsset.sha256 == sha))
    if previous:
        if previous.is_archived:
            restored = db.execute(update(CartonMarkAsset).where(
                CartonMarkAsset.id == previous.id, CartonMarkAsset.is_archived.is_(True),
                CartonMarkAsset.revision == previous.revision).values(
                    is_archived=False, revision=previous.revision + 1, updated_at=_now_text()))
            if restored.rowcount != 1:
                db.rollback()
                raise HTTPException(409, "资料发生并发变化，请刷新重试")
            audit(db, user, previous, "CARTON_MARK_ASSET_RESTORED", {"sha256": sha})
            db.commit()
            db.refresh(previous)
            return asset_out(previous, available_orders(db, factory)), "restored"
        return asset_out(previous, available_orders(db, factory)), "duplicate"
    timestamp = _now_text()
    asset = CartonMarkAsset(id=f"CMA-{uuid4().hex}", factory_id=factory,
        file_name=recognition["file_name"], kind=recognition["kind"], content=content,
        content_type="application/pdf" if recognition["kind"] == "pdf" else _excel_content_type(recognition["file_name"]),
        sha256=sha, size_bytes=len(content), contract_number=recognition["contract_number"],
        recognition_source=recognition["recognition_source"], candidates_json=json.dumps(recognition["candidates"]),
        warning=recognition["warning"], created_by=user.id, created_by_name=user.display_name,
        created_at=timestamp, updated_at=timestamp, revision=1, is_archived=False)
    db.add(asset)
    audit(db, user, asset, "CARTON_MARK_ASSET_CREATED", {"sha256": sha, "contract_number": asset.contract_number})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        previous = db.scalar(select(CartonMarkAsset).where(CartonMarkAsset.factory_id == factory, CartonMarkAsset.sha256 == sha))
        if previous is None or previous.is_archived:
            raise HTTPException(409, "资料发生并发变化，请刷新重试")
        return asset_out(previous, available_orders(db, factory)), "duplicate"
    return asset_out(asset, available_orders(db, factory)), "created"


def change_binding(db, user, factory, asset_id, payload):
    asset = active_asset(db, factory, asset_id)
    contract = payload.contract_number.strip()
    if payload.order_id:
        order = next((o for o in available_orders(db, factory) if o.id == payload.order_id), None)
        if order is None:
            raise HTTPException(404, "未找到本厂订单")
        if contract and identity(contract) != identity(order.contract_no):
            raise HTTPException(422, "合同号与所选订单不一致")
        contract = order.contract_no
    try:
        result = db.execute(update(CartonMarkAsset).where(CartonMarkAsset.id == asset.id,
            CartonMarkAsset.revision == payload.revision, CartonMarkAsset.is_archived.is_(False)).values(
                contract_number=contract, bound_order_id=payload.order_id,
                recognition_source="manual_order" if payload.order_id else "manual",
                warning="", revision=payload.revision + 1, updated_at=_now_text()))
        if result.rowcount != 1:
            db.rollback()
            raise HTTPException(409, "资料已被修改，请刷新后重试")
        audit(db, user, asset, "CARTON_MARK_ASSET_BOUND", {"contract_number": contract, "order_id": payload.order_id})
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "目标订单已变化，请刷新后重新关联") from exc
    db.refresh(asset)
    return asset_out(asset, available_orders(db, factory))


def archive_asset(db, user, factory, asset_id, revision):
    asset = active_asset(db, factory, asset_id)
    result = db.execute(update(CartonMarkAsset).where(CartonMarkAsset.id == asset.id,
        CartonMarkAsset.revision == revision, CartonMarkAsset.is_archived.is_(False)).values(
            is_archived=True, revision=revision + 1, updated_at=_now_text()))
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "资料已被修改，请刷新后重试")
    audit(db, user, asset, "CARTON_MARK_ASSET_ARCHIVED", {"revision": revision})
    db.commit()
