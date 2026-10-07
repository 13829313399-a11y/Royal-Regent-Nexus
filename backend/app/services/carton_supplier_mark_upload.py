"""Supplier originals are explicitly bound to a current own issued order."""
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.carton_mark import CartonMarkAsset
from app.models.carton_procurement import CartonPurchaseOrderIssue
from app.services import carton_mark_assets as assets
from app.services import carton_supplier_portal as portal
from app.services.carton_mark import CartonMarkDocumentError, CartonMarkDocumentConfigurationError
from app.services.carton_mark_library import _excel_content_type, _now_text


def upload_orders(db, user, factory):
    portal.supplier_access(db, user, factory, "carton_supplier:edit")
    _, _, orders = portal._supplier_mark_orders(db, user, factory)
    issues = {issue.id: issue for issue in db.scalars(select(CartonPurchaseOrderIssue).where(
        CartonPurchaseOrderIssue.factory_id == factory, CartonPurchaseOrderIssue.id.in_([order["issue_id"] for order in orders.values()])))}
    result = [dict(order, document_no=issues[order["issue_id"]].document_no,
        order_date=str(portal._purchase_order_snapshot(issues[order["issue_id"]]).get("order", {}).get("order_date") or ""))
        for order in orders.values()]
    return sorted(result, key=lambda order: (order["contract_no"], order["item_no"], order["id"]))


def recognize_batch(files, orders):
    contracts = [order["contract_no"] for order in orders if order["contract_no"]]
    result = []
    for name, content in files:
        try:
            recognition = assets.recognize_asset(name, content, contracts)
            result.append(dict(file_name=recognition["file_name"], content=content, recognition=recognition))
        except (CartonMarkDocumentError, CartonMarkDocumentConfigurationError) as exc:
            result.append(dict(file_name=Path(name.replace("\\", "/")).name, error=str(exc)))
    return result


def _target(recognition, orders, selected_order):
    candidates = {assets.identity(value) for value in recognition["candidates"]}
    if selected_order:
        if candidates and candidates != {assets.identity(selected_order["contract_no"])}:
            raise HTTPException(422, "文件识别的合同与所选订单不一致，请核实后重新上传")
        return selected_order
    if len(candidates) != 1:
        raise HTTPException(422, "无法唯一识别合同，请选择本次关联采购订单后重试此文件")
    matching = [order for order in orders if assets.identity(order["contract_no"]) in candidates]
    if len(matching) != 1:
        raise HTTPException(422, "未匹配到唯一的本供应商已下单订单，请选择采购订单后重试此文件")
    return matching[0]


def _visible_duplicate(db, user, factory, existing, order_id):
    if existing and not existing.is_archived:
        row = next((row for row in portal.supplier_mark_assets(db, user, factory)
            if row["id"] == existing.id and any(order["id"] == order_id for order in row["orders"])), None)
        if row:
            return dict(status="duplicate", message="已存在，保留原资料和关联", asset=row)
    # Do not reveal, restore, rename or rebind an inaccessible/archived original.
    raise HTTPException(409, "相同文件已有其他关联或已归档，请联系仓库核实")


def save_batch(db, user, factory, parsed, original_orders, order_id="", issue_id=""):
    supplier = portal.supplier_access(db, user, factory, "carton_supplier:edit")
    current_orders = upload_orders(db, user, factory)
    if current_orders != original_orders:
        raise HTTPException(409, "采购订单或服务范围已变更，请刷新后重新上传")
    selected = next((order for order in current_orders if order["id"] == order_id), None)
    if order_id and (selected is None or selected["issue_id"] != issue_id):
        raise HTTPException(409, "所选采购订单已变更，请刷新后重新选择")
    outcomes = []
    for item in parsed:
        outcome = dict(file_name=item["file_name"], status="failed", message=item.get("error", ""), asset=None)
        if "error" in item:
            outcomes.append(outcome)
            continue
        recognition, content = item["recognition"], item["content"]
        try:
            order = _target(recognition, current_orders, selected)
            if not order["contract_no"]:
                raise HTTPException(422, "采购订单缺少合同号，请联系仓库核实")
            sha = hashlib.sha256(content).hexdigest()
            existing = db.scalar(select(CartonMarkAsset).where(CartonMarkAsset.factory_id == factory,
                CartonMarkAsset.sha256 == sha).with_for_update())
            if existing:
                outcome.update(_visible_duplicate(db, user, factory, existing, order["id"]))
            else:
                timestamp = _now_text()
                asset = CartonMarkAsset(id=f"CMA-{uuid4().hex}", factory_id=factory,
                    file_name=recognition["file_name"], kind=recognition["kind"], content=content,
                    content_type=assets.IMAGE_CONTENT_TYPES[Path(recognition["file_name"]).suffix.lower()]
                        if recognition["kind"] == "image" else "application/pdf" if recognition["kind"] == "pdf"
                        else _excel_content_type(recognition["file_name"]),
                    sha256=sha, size_bytes=len(content), contract_number=order["contract_no"],
                    bound_order_id=order["id"], recognition_source="manual_order",
                    candidates_json=json.dumps(recognition["candidates"]), warning=recognition["warning"],
                    created_by=user.id, created_by_name=user.display_name,
                    created_at=timestamp, updated_at=timestamp, revision=1, is_archived=False)
                try:
                    # Internal uploads do not take the supplier factory lock. A
                    # concurrent hash collision must not roll back other files.
                    with db.begin_nested():
                        db.add(asset)
                        db.flush()
                        assets.audit(db, user, asset, "CARTON_MARK_ASSET_CREATED", dict(sha256=sha,
                            contract_number=asset.contract_number, supplier_context=dict(supplier_id=supplier.id,
                                order_id=order["id"], issue_id=order["issue_id"], source="supplier_upload")))
                    row = next(row for row in portal.supplier_mark_assets(db, user, factory) if row["id"] == asset.id)
                    outcome.update(status="created", message=recognition["warning"], asset=row)
                except IntegrityError:
                    existing = db.scalar(select(CartonMarkAsset).where(CartonMarkAsset.factory_id == factory,
                        CartonMarkAsset.sha256 == sha).with_for_update())
                    outcome.update(_visible_duplicate(db, user, factory, existing, order["id"]))
        except HTTPException as exc:
            outcome.update(status="failed", message=str(exc.detail), asset=None)
        outcomes.append(outcome)
    db.commit()
    return outcomes
