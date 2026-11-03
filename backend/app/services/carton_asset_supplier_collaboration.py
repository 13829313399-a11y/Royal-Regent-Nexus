"""Supplier edits to shared internal materials, without replacing source provenance."""
import json
from fastapi import HTTPException
from sqlalchemy import select
from app.models.carton_procurement import CartonAuditEvent, CartonOrder

TARGETS = 'CARTON_ASSET_SUPPLIER_TARGETS'
FACTORIES = 'CARTON_ASSET_SUPPLIER_FACTORIES'


def internal(asset):
    from app.services.carton_asset_access import DEPARTMENTS
    return asset.owner_department in DEPARTMENTS and asset.asset_purpose == 'MATERIAL'


def source_stamp(db, asset):
    from app.services import carton_asset_targets as targets, carton_mark_sharing as sharing
    events = list(db.scalars(select(CartonAuditEvent.sequence).where(
        CartonAuditEvent.factory_id == asset.factory_id,
        CartonAuditEvent.entity_type == 'carton_mark_asset', CartonAuditEvent.entity_id == asset.id,
        CartonAuditEvent.event_type.in_([targets.EVENT, sharing.SHARED, sharing.ASSOCIATED, sharing.SPECIAL])
    ).order_by(CartonAuditEvent.sequence)))
    return dict(events=events, targets=targets.current(db,asset))


def latest(db, asset, event_type):
    if not internal(asset):
        return None
    return db.scalar(select(CartonAuditEvent).where(
        CartonAuditEvent.factory_id == asset.factory_id,
        CartonAuditEvent.entity_type == 'carton_mark_asset', CartonAuditEvent.entity_id == asset.id,
        CartonAuditEvent.event_type == event_type).order_by(CartonAuditEvent.sequence.desc()).limit(1))


def authorized_event(db, asset, event_type):
    """Published extensions expire when their source or granting actor loses authority."""
    event = latest(db, asset, event_type)
    if not event:
        return None
    data = json.loads(event.detail_json)
    if data.get('source_stamp') != source_stamp(db, asset):
        return None
    from app.models.auth import AuthUser
    from app.services.auth import build_auth_context
    from app.services import carton_asset_access as access
    from app.services.carton_supplier_portal import supplier_access
    actor = db.get(AuthUser, event.actor_user_id)
    if actor is None or actor.status != 'active':
        return None
    user = build_auth_context(db, actor)
    try:
        supplier = supplier_access(db, user, asset.factory_id, 'carton_supplier:edit')
        if supplier.id != data.get('supplier_id') or not access.allowed(user, asset.factory_id, 'supplier', 'manage'):
            return None
        # This guard follows only original business targets, never these extensions.
        access.ensure(db, user, asset, supplier=supplier)
    except HTTPException:
        return None
    return user, supplier, data


def record(db, user, asset, supplier, event_type, **data):
    from app.services.carton_mark_assets import audit
    audit(db, user, asset, event_type, dict(revision=asset.revision,
        source_stamp=source_stamp(db, asset), supplier_id=supplier.id, **data))
    db.flush()


def selected_targets(db, asset):
    state = authorized_event(db, asset, TARGETS)
    if not state:
        return None
    user, supplier, data = state
    from app.services import carton_asset_targets as targets
    saved = {(row['kind'], row['id'], tuple(row['identity'])) for row in data['targets']}
    rows = [row for row in targets.candidates(db, user, asset.factory_id, supplier=supplier)
        if (row['kind'], row['id'], tuple(row['identity'])) in saved]
    return supplier.id, rows


def purchase_ids(db, asset, source_ids):
    state = selected_targets(db, asset)
    if state is None:
        return source_ids
    supplier_id, rows = state
    kept = {identifier for identifier in source_ids
        if (order := db.get(CartonOrder, identifier)) and order.supplier_id != supplier_id}
    return kept | {row['id'] for row in rows if row['kind'] == 'REGULAR'}


def display_targets(db, asset, rows):
    state = selected_targets(db, asset)
    if state is None:
        return rows
    supplier_id, selected = state
    # Upstream schedule links remain intact even when the supplier changes its orders.
    return [row for row in rows if row['kind'] == 'SCHEDULE' or row.get('supplier_id') != supplier_id] + selected


def share_recipients(db, user, factory_ids):
    from app.services import carton_asset_access as access
    from app.services.carton_supplier_portal import supplier_access
    recipients = {}
    for factory in sorted(set(factory_ids)):
        supplier = supplier_access(db, user, factory, 'carton_supplier:edit')
        if not access.allowed(user, factory, 'supplier', 'manage') or not access.allowed(user, factory, 'supplier', 'read'):
            raise HTTPException(403, '没有所选厂区的供应商资料权限')
        recipients[factory] = supplier.id
    return recipients


def shared_factories(db, asset):
    result = {asset.factory_id}
    state = authorized_event(db, asset, FACTORIES)
    if state:
        user, _, data = state
        for factory, identifier in data['recipients'].items():
            try:
                if share_recipients(db, user, [factory]).get(factory) == identifier:
                    result.add(factory)
            except HTTPException:
                continue
    return sorted(result)


def shared_asset_ids(db):
    # The per-asset access guard revalidates the latest grant; this is only a query prefilter.
    return select(CartonAuditEvent.entity_id).where(
        CartonAuditEvent.entity_type == 'carton_mark_asset', CartonAuditEvent.event_type == FACTORIES)
