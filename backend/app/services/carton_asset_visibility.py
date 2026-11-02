"""Explicit supplier sharing; private by default, without duplicating file bytes."""
import json
from fastapi import HTTPException
from sqlalchemy import select
from app.models.carton_procurement import CartonAuditEvent

EVENT = 'CARTON_ASSET_SHARED_FACTORIES'


def factories(db, asset):
    event = db.scalar(select(CartonAuditEvent).where(
        CartonAuditEvent.entity_type == 'carton_mark_asset',
        CartonAuditEvent.entity_id == asset.id,
        CartonAuditEvent.factory_id == asset.factory_id,
        CartonAuditEvent.event_type == EVENT).order_by(CartonAuditEvent.sequence.desc()).limit(1))
    if event:return json.loads(event.detail_json).get('factory_ids', [])
    # Preserve existing supplier-to-order sharing. New uploads always record an
    # explicit empty list, which must never fall back to an order association.
    if asset.owner_department=='supplier':
        from app.services.carton_asset_targets import valid
        if valid(db,asset):return [asset.factory_id]
    return []


def record(db, user, asset, factory_ids):
    from app.services import carton_asset_access as access, carton_mark_assets as assets
    from app.services.carton_supplier_portal import supplier_access
    if asset.owner_department != 'supplier':
        if factory_ids:
            raise HTTPException(422, '内部资料仅在所属厂区共享')
        return
    for factory in factory_ids:
        supplier_access(db, user, factory, 'carton_supplier:edit')
        if not access.allowed(user, factory, 'supplier', 'manage'):
            raise HTTPException(403, '没有所选厂区的供应商资料权限')
    assets.audit(db, user, asset, EVENT, dict(factory_ids=sorted(set(factory_ids)), revision=asset.revision))


def internal_read(db, user, asset, factory):
    from app.services import carton_asset_access as access
    access.internal_scope(user, factory)
    if asset.asset_purpose != 'MATERIAL':
        raise HTTPException(404, '内部凭据不可共享')
    if asset.owner_department == 'supplier':
        if factory not in factories(db, asset):
            raise HTTPException(404, '供应商未向此厂区共享资料')
    elif asset.factory_id != factory:
        raise HTTPException(404, '资料不属于当前厂区')
