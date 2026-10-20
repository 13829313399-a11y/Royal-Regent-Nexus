"""Source-file classifications projected from audited events, separate from QC release.

Existing assets without an event remain unclassified. Writers share the factory
lock and asset revision with binding/archive operations; original bytes never change.
"""
import json

from fastapi import HTTPException
from sqlalchemy import select, update

from app.models.carton_mark import CartonMarkAsset, CartonMarkAssetOrderBinding
from app.models.carton_procurement import CartonAuditEvent
from app.schemas.carton_mark import CartonMarkAssetWorkflow
from app.services.carton_mark_library import _now_text

EVENT = 'CARTON_MARK_ASSET_CLASSIFIED'


def states(db, factory, ids=None):
    if ids is not None and not ids:
        return {}
    query = select(CartonAuditEvent).where(CartonAuditEvent.factory_id == factory,
        CartonAuditEvent.entity_type == 'carton_mark_asset', CartonAuditEvent.event_type == EVENT)
    if ids is not None:
        query = query.where(CartonAuditEvent.entity_id.in_(ids))
    latest = {}
    for event in db.scalars(query):
        detail = json.loads(event.detail_json)
        if event.entity_id not in latest or detail['revision'] > latest[event.entity_id][0]:
            latest[event.entity_id] = (detail['revision'], CartonMarkAssetWorkflow.model_validate(detail['workflow']))
    return {identifier: value[1] for identifier, value in latest.items()}


def current(db, asset):
    return states(db, asset.factory_id, [asset.id]).get(asset.id, CartonMarkAssetWorkflow())


def record(db, user, asset, state):
    from app.services.carton_mark_assets import audit
    audit(db, user, asset, EVENT, {'revision': asset.revision, 'sha256': asset.sha256,
        'workflow': state.model_dump()})


def bump(db, asset, revision):
    if db.execute(update(CartonMarkAsset).where(CartonMarkAsset.id == asset.id,
            CartonMarkAsset.factory_id == asset.factory_id, CartonMarkAsset.is_archived.is_(False),
            CartonMarkAsset.revision == revision).values(revision=revision + 1, updated_at=_now_text())).rowcount != 1:
        raise HTTPException(409, '资料已被修改，请刷新后重试')
    db.refresh(asset)


def binding_key(asset):
    return (asset.contract_number, asset.bound_order_id, asset.recognition_source,
        tuple(sorted(link.order_id for link in asset.order_bindings)))


def initialize(db, user, asset, options):
    from app.services.carton_mark_assets import active_asset
    state = CartonMarkAssetWorkflow(status=options.status, note=options.note.strip(),
        updated_by_name=user.display_name, updated_at=_now_text())
    if options.previous_asset_id:
        if options.status == 'READY':
            raise HTTPException(422, '修改稿须重新确认，请先选择待打版或待确认')
        parent = active_asset(db, asset.factory_id, options.previous_asset_id)
        if options.previous_revision is None or parent.revision != options.previous_revision:
            raise HTTPException(409, '原版本已变化，请刷新后重新上传修改稿')
        parent_state = current(db, parent)
        if parent_state.status == 'HISTORY':
            raise HTTPException(409, '请从当前版本上传修改稿，不能继续替换历史版本')
        if parent.kind != asset.kind:
            raise HTTPException(422, '修改稿须与原版本保持相同文件类型')
        if parent.photo_group_id:
            raise HTTPException(409, '请先解除照片组，再替换其中的单张图片')
        active_ids = set(db.scalars(select(CartonMarkAsset.id).where(
            CartonMarkAsset.factory_id == asset.factory_id, CartonMarkAsset.is_archived.is_(False))))
        if any(s.previous_asset_id == parent.id and identifier in active_ids
                for identifier, s in states(db, asset.factory_id).items()):
            raise HTTPException(409, '此资料已有修改稿，请在资料库继续处理该稿件')
        bump(db, parent, options.previous_revision)
        asset.contract_number, asset.bound_order_id = parent.contract_number, parent.bound_order_id
        asset.recognition_source, asset.warning = parent.recognition_source, parent.warning
        asset.candidates_json = parent.candidates_json
        asset.order_bindings = [CartonMarkAssetOrderBinding(asset_id=asset.id,
            factory_id=asset.factory_id, order_id=link.order_id) for link in parent.order_bindings]
        state.version = parent_state.version + 1
        state.previous_asset_id = parent.id
    elif options.status == 'READY':
        state.confirmed_by_name, state.confirmed_at = user.display_name, state.updated_at
        state.confirmation_note = state.note
    db.flush()
    record(db, user, asset, state)


def classify(db, user, factory, asset_id, payload, *, commit=True, material_confirmation=False):
    from app.services.carton_mark_assets import active_asset, asset_out, available_orders
    from app.services.carton_procurement import _lock_receipt_factory
    _lock_receipt_factory(db, factory)
    try:
        asset = active_asset(db, factory, asset_id)
        from app.services.carton_mark_sharing import ensure_asset_access
        ensure_asset_access(db, user, asset, write=not material_confirmation)
        before = current(db, asset)
        if before.superseded_by_asset_id and payload.status != 'HISTORY':
            raise HTTPException(409, '历史稿仅供追溯，请从当前版本上传修改稿')
        bump(db, asset, payload.revision)
        state = before.model_copy(update={'status': payload.status, 'note': payload.note.strip(),
            'updated_by_name': user.display_name, 'updated_at': _now_text()})
        if payload.status == 'READY':
            state.confirmed_by_name, state.confirmed_at = user.display_name, state.updated_at
            state.confirmation_note = state.note
            # Reconfirming the exact current file is allowed, but never revive an
            # old ancestor after its successor was already approved.
            parent_id, seen = state.previous_asset_id, {asset.id}
            while parent_id:
                if parent_id in seen:
                    raise HTTPException(409, '版本关系异常，请核实原稿')
                seen.add(parent_id)
                parent = active_asset(db, factory, parent_id)
                parent_state = current(db, parent)
                if binding_key(parent) != binding_key(asset):
                    raise HTTPException(409, '新旧版本的关联范围已变化，请核实并保持一致后确认')
                if parent_state.status != 'HISTORY' or not parent_state.superseded_by_asset_id:
                    bump(db, parent, parent.revision)
                    archived = parent_state.model_copy(update={'status': 'HISTORY', 'superseded_by_asset_id': asset.id,
                        'updated_by_name': user.display_name, 'updated_at': state.updated_at})
                    record(db, user, parent, archived)
                parent_id = parent_state.previous_asset_id
        record(db, user, asset, state)
        if commit: db.commit()
        else: db.flush()
    except Exception:
        db.rollback()
        raise
    return asset_out(asset, available_orders(db, factory))


def history(db, factory, asset_id):
    from app.services.carton_mark_assets import active_asset
    active_asset(db, factory, asset_id)
    rows = db.scalars(select(CartonAuditEvent).where(CartonAuditEvent.factory_id == factory,
        CartonAuditEvent.entity_type == 'carton_mark_asset', CartonAuditEvent.entity_id == asset_id,
        CartonAuditEvent.event_type == EVENT))
    return sorted([json.loads(row.detail_json) for row in rows], key=lambda item: item['revision'], reverse=True)
