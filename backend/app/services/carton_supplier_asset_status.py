"""Supplier-owned source progress, separate from internal confirmation and QC."""
import json
from fastapi import HTTPException
from sqlalchemy import select
from app.models.carton_procurement import CartonAuditEvent
from app.services import carton_asset_access as ownership, carton_mark_asset_workflow as lifecycle


def legacy_origins(db, assets):
    rows = {asset.id: asset for asset in assets if asset.owner_department is None}
    result = {identifier: set() for identifier in rows}
    if not rows:
        return result
    factories = {asset.factory_id for asset in rows.values()}
    events = db.scalars(select(CartonAuditEvent).where(CartonAuditEvent.factory_id.in_(factories),
        CartonAuditEvent.entity_id.in_(rows), CartonAuditEvent.entity_type == 'carton_mark_asset',
        CartonAuditEvent.event_type == 'CARTON_MARK_ASSET_CREATED'))
    for event in events:
        asset = rows[event.entity_id]
        if event.factory_id != asset.factory_id or event.actor_user_id != asset.created_by:
            continue
        try:
            supplier_id = json.loads(event.detail_json).get('supplier_context', {}).get('supplier_id')
        except (ValueError, TypeError, AttributeError):
            continue
        if isinstance(supplier_id, str) and supplier_id:
            result[asset.id].add(supplier_id)
    return result


def can_classify(db, user, asset, supplier, *, workflow=None, origins=None):
    from app.services import carton_supplier_portal as portal
    state = workflow or lifecycle.current(db, asset)
    if asset.is_archived or asset.recognition_source == 'materials_folder' or asset.asset_purpose != 'MATERIAL':
        return False
    if state.status not in {'UNCLASSIFIED', 'DRAFT', 'PENDING'} or state.superseded_by_asset_id:
        return False
    if not all(portal.supplier_permission(user, code, asset.factory_id)
               for code in ['carton_supplier:read', 'carton_supplier:edit']):
        return False
    if ownership.managed(asset):
        if asset.owner_department != 'supplier' or asset.owner_supplier_id != supplier.id:
            return False
        return ownership.visible(db, user, asset, write=True, supplier=supplier)
    # Visibility or creator identity alone is not ownership. Legacy producers
    # recorded the creating supplier in the actor-matched creation audit.
    values = (origins if origins is not None else legacy_origins(db, [asset])).get(asset.id, set())
    return values == {supplier.id}


def classify(db, user, factory, identifier, payload, refresh_actor):
    from app.services.carton_asset_quick import locked
    from app.services import carton_supplier_portal as portal, carton_mark_assets as assets
    from app.services import carton_mark_associations as requests
    try:
        if payload.status not in {'DRAFT', 'PENDING'}:
            raise HTTPException(422, '供应商只能设置待处理或待确认')
        locked(db, user, factory)
        actor = refresh_actor()  # Recheck the original session after the lock.
        supplier = portal.supplier_access(db, actor, factory, 'carton_supplier:edit')
        asset = assets.active_asset(db, factory, identifier)
        before = lifecycle.current(db, asset)
        if not can_classify(db, actor, asset, supplier, workflow=before):
            raise HTTPException(403, '只能设置本供应商自有且未确认的资料；已确认、历史稿及内部共享原件不可修改')
        if not ownership.managed(asset) and not any(row.id == asset.id for row, _ in portal._supplier_mark_assets(db, actor, factory, asset_ids=[identifier])):
            raise HTTPException(403, '资料不在本供应商当前可见范围内')
        rid, saved = requests.request_event(db, actor, factory, payload.request_id, 'SUPPLIER_ASSET_STATUS',
            dict(id=identifier, body=payload.model_dump()))
        if not saved or 'result' not in saved:
            lifecycle.bump(db, asset, payload.revision)
            state = before.model_copy(update=dict(status=payload.status, updated_by_name=actor.display_name, updated_at=lifecycle._now_text()))
            lifecycle.record(db, actor, asset, state)
            requests.record_request(db, actor, asset, rid, saved, dict(asset_id=identifier))
            db.flush()
        result = dict(id=asset.id, revision=asset.revision, file_name=asset.file_name, kind=asset.kind,
            photo_group_id=asset.photo_group_id, size_bytes=asset.size_bytes, contract_number=asset.contract_number,
            created_at=asset.created_at, orders=[], workflow=lifecycle.current(db, asset).model_dump(),
            can_classify=can_classify(db, actor, asset, supplier))
        db.commit()
        return result
    except BaseException:
        db.rollback()
        raise
