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
    # Warehouse uploads may retain several independent copies of identical bytes.
    # Reuse only a copy already visible for this supplier's exact selected order.
    identifiers = {asset.id for asset in existing if not asset.is_archived}
    row = next((row for row in portal.supplier_mark_assets(db, user, factory)
        if row["id"] in identifiers and any(order["id"] == order_id for order in row["orders"])), None)
    if row:
        return dict(status="duplicate", message="已存在，保留原资料和关联", asset=row)
    raise HTTPException(409, "相同文件已有其他关联或已归档，请联系仓库核实")


def save_batch(db, user, factory, parsed, original_orders, order_id="", issue_id="", *, shared_unbound=False, targets=None, request_id=''):
    supplier = portal.supplier_access(db, user, factory, "carton_supplier:edit")
    current_orders = upload_orders(db, user, factory)
    if targets is None and not request_id and current_orders != original_orders:
        raise HTTPException(409, "采购订单或服务范围已变更，请刷新后重新上传")
    selected = next((order for order in current_orders if order["id"] == order_id), None)
    if order_id and (selected is None or selected["issue_id"] != issue_id):
        raise HTTPException(409, "所选采购订单已变更，请刷新后重新选择")
    if targets is not None or request_id:
        return save_shared_batch(db, user, factory, supplier, parsed, selected, targets=targets, request_id=request_id)
    if shared_unbound:
        return save_shared_batch(db, user, factory, supplier, parsed, selected)
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
            existing = list(db.scalars(select(CartonMarkAsset).where(CartonMarkAsset.factory_id == factory,
                CartonMarkAsset.sha256 == sha).with_for_update()))
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
                    # A malformed file must not roll back other files in this batch.
                    with db.begin_nested():
                        db.add(asset)
                        db.flush()
                        assets.audit(db, user, asset, "CARTON_MARK_ASSET_CREATED", dict(sha256=sha,
                            contract_number=asset.contract_number, supplier_context=dict(supplier_id=supplier.id,
                                order_id=order["id"], issue_id=order["issue_id"], source="supplier_upload")))
                    row = next(row for row in portal.supplier_mark_assets(db, user, factory) if row["id"] == asset.id)
                    outcome.update(status="created", message=recognition["warning"], asset=row)
                except IntegrityError:
                    existing = list(db.scalars(select(CartonMarkAsset).where(CartonMarkAsset.factory_id == factory,
                        CartonMarkAsset.sha256 == sha).with_for_update()))
                    outcome.update(_visible_duplicate(db, user, factory, existing, order["id"]))
        except HTTPException as exc:
            outcome.update(status="failed", message=str(exc.detail), asset=None)
        outcomes.append(outcome)
    db.commit()
    return outcomes


def save_shared_batch(db, user, factory, supplier, parsed, selected, *, targets=None, request_id=''):
    from app.services import carton_mark_sharing as sharing, carton_mark_asset_workflow as lifecycle
    from app.schemas.carton_mark import CartonMarkAssetUploadOptions
    from app.services import carton_mark_associations as associations
    from app.schemas.carton_mark import CartonMarkAssociationTarget
    if selected:
        from app.models.carton_procurement import CartonOrder
        row = db.get(CartonOrder, selected['id'])
        targets = [CartonMarkAssociationTarget(order_kind='REGULAR', order_id=row.id,
            expected_revision=row.revision, issue_id=selected['issue_id'])]
    targets = targets or []
    batch_data = {'files': [{'name': x['file_name'], 'sha256': hashlib.sha256(x.get('content', b'')).hexdigest(),
        'error': x.get('error', '')} for x in parsed], 'targets': [x.model_dump(mode='json') for x in targets]}
    rid, saved = associations.request_event(db, user, factory, request_id, 'SUPPLIER_UPLOAD', batch_data)
    if saved and 'result' in saved:
        visible = {x['id']: x for x in portal.supplier_mark_assets(db, user, factory)}
        results = []
        for value in saved['result']['outcomes']:
            value = dict(value)
            asset_id = value.pop('asset_id', '')
            if asset_id and asset_id not in visible: raise HTTPException(404, '原上传资料已不可访问，请核实原记录')
            value['asset'] = visible.get(asset_id)
            results.append(value)
        return results
    outcomes = []
    for item in parsed:
        outcome = dict(file_name=item['file_name'], status='failed', message=item.get('error', ''), asset=None)
        if 'error' in item:
            outcomes.append(outcome); continue
        recognition, content = item['recognition'], item['content']
        try:
            # Never reuse or expose an inaccessible equal-hash original. Each new
            # shared upload is an independent file, as warehouse uploads are.
            candidates = {assets.identity(x) for x in recognition['candidates']}
            known = [o for o in assets.available_orders(db, factory) if assets.identity(o.contract_no) in candidates]
            if any(o.supplier_id != supplier.id for o in known):
                raise HTTPException(422, '文件合同包含其他供应商订单，请核实文件')
            if known and targets:
                checked = associations.target_rows(db, user, factory, targets, external=True)
                if len({assets.identity(o.customer_code) for o in known} | {assets.identity(x['customer_code']) for x in checked}) > 1:
                    raise HTTPException(422, '文件合同与所选订单客户不一致，请分别维护')
            timestamp = _now_text()
            asset = CartonMarkAsset(id=f'CMA-{uuid4().hex}', factory_id=factory,
                file_name=recognition['file_name'], kind=recognition['kind'], content=content,
                content_type=assets.IMAGE_CONTENT_TYPES[Path(recognition['file_name']).suffix.lower()]
                    if recognition['kind'] == 'image' else 'application/pdf' if recognition['kind'] == 'pdf'
                    else _excel_content_type(recognition['file_name']),
                sha256=hashlib.sha256(content).hexdigest(), size_bytes=len(content), contract_number='',
                recognition_source='manual_orders', candidates_json=json.dumps(recognition['candidates']),
                warning=recognition['warning'], created_by=user.id, created_by_name=user.display_name,
                created_at=timestamp, updated_at=timestamp, revision=1, is_archived=False)
            with db.begin_nested():
                db.add(asset); db.flush()
                lifecycle.initialize(db, user, asset, CartonMarkAssetUploadOptions(status='PENDING'))
                sharing.record(db, user, asset, 'SUPPLIER', supplier.id)
                assets.audit(db, user, asset, 'CARTON_MARK_ASSET_CREATED', dict(sha256=asset.sha256,
                    supplier_context=dict(supplier_id=supplier.id, source='supplier_shared_upload')))
                associations.apply(db, user, asset, targets, external=True)
            db.flush()
            output = next(x for x in portal.supplier_mark_assets(db, user, factory) if x['id'] == asset.id)
            outcome.update(status='created', message='已共享并关联订单' if targets else '已共享，可稍后关联订单', asset=output)
        except HTTPException as exc:
            outcome.update(message=str(exc.detail))
        outcomes.append(outcome)
    if rid:
        # Batch idempotency includes failed outcomes; explicit new request retries
        # a corrected batch, while an uncertain original request never copies files.
        from types import SimpleNamespace
        anchor = next((x['asset']['id'] for x in outcomes if x.get('asset')), 'upload-' + request_id)
        associations.record_request(db, user, SimpleNamespace(id=anchor, factory_id=factory), rid, saved,
            {'outcomes': [{k: v for k, v in x.items() if k != 'asset'} | {'asset_id': x['asset']['id'] if x.get('asset') else ''} for x in outcomes]})
    db.commit()
    return outcomes
