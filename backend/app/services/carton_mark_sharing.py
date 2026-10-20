"""Explicit supplier audience and proposed associations, independent of QC release.

Like source classification, these facts are revisioned audit projections. Existing
sources have no sharing event and retain their original issued-order boundary.
"""
import json
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select
from app.models.carton_procurement import CartonAuditEvent, CartonSupplier
from app.models.carton_mark import CartonMarkAssetOrderBinding
from app.services import carton_mark_assets as assets
from app.services import carton_mark_asset_workflow as lifecycle
from app.services.carton_procurement import _lock_receipt_factory
from app.services.carton_mark_library import _now_text

SHARED = 'CARTON_MARK_ASSET_SHARED'
PROPOSED = 'CARTON_MARK_BINDING_PROPOSED'
DECIDED = 'CARTON_MARK_BINDING_CONFIRMED'
SPECIAL = 'CARTON_MARK_SPECIAL_LINKED'


def recipients(db, factory):
    return [{'id': row.id, 'name': row.supplier_name} for row in db.scalars(
        select(CartonSupplier).where(CartonSupplier.factory_id == factory,
            CartonSupplier.status == 'ACTIVE').order_by(CartonSupplier.supplier_name, CartonSupplier.id))]


def states(db, factory, ids=None):
    query = select(CartonAuditEvent).where(CartonAuditEvent.factory_id == factory,
        CartonAuditEvent.entity_type == 'carton_mark_asset',
        CartonAuditEvent.event_type.in_([SHARED, PROPOSED, DECIDED, SPECIAL]))
    if ids is not None:
        if not ids: return {}
        query = query.where(CartonAuditEvent.entity_id.in_(ids))
    result = {}
    for event in db.scalars(query.order_by(CartonAuditEvent.created_at, CartonAuditEvent.id)):
        data = json.loads(event.detail_json)
        state = result.setdefault(event.entity_id, {'sharing_mode': 'ORDER_BOUND',
            'shared_supplier_id': '', 'shared_supplier_name': '', 'pending_bindings': [], 'special_orders': [], '_revision': -1})
        if event.event_type == SHARED and data['revision'] > state['_revision']:
            state.update({key: data[key] for key in ('sharing_mode', 'shared_supplier_id', 'shared_supplier_name')})
            state['_revision'] = data['revision']
        elif event.event_type == PROPOSED:
            state['pending_bindings'].append(data)
        elif event.event_type == DECIDED:
            state.setdefault('_decided', set()).add(data['id'])
        elif event.event_type == SPECIAL:
            state['special_orders'].append(data)
    for state in result.values():
        state.pop('_revision', None)
        decided = state.pop('_decided', set())
        state['pending_bindings'] = [x for x in state['pending_bindings'] if x['id'] not in decided]
    return result


def current(db, asset):
    return states(db, asset.factory_id, [asset.id]).get(asset.id, dict(sharing_mode='ORDER_BOUND',
        shared_supplier_id='', shared_supplier_name='', pending_bindings=[], special_orders=[]))


def ensure_customer(db, user, order):
    from app.services.carton_special_requests import ensure_customer_operation
    if order.customer_code: ensure_customer_operation(db, user, order.factory_id, order.customer_code)


def related_orders(db, asset, seen=None):
    from types import SimpleNamespace
    from app.models.carton_special_requests import SpecialRequest
    from app.models.carton_mark import CartonMarkAsset
    seen = set() if seen is None else seen
    if asset.id in seen: raise HTTPException(409, '资料版本关系异常，请核实')
    seen.add(asset.id)
    orders = assets.matching_asset_orders(asset, assets.available_orders(db, asset.factory_id))
    special_links = current(db, asset)['special_orders']
    for identifier in {x['order_id'] for x in special_links}:
        row = db.get(SpecialRequest, identifier)
        if row and row.factory_id == asset.factory_id: orders.append(row)
    for link in special_links:
        if 'supplier_id' in link and 'customer_code' in link:
            orders.append(SimpleNamespace(id=link['order_id'], factory_id=asset.factory_id,
                supplier_id=link['supplier_id'], customer_code=link['customer_code']))
    previous_id = lifecycle.current(db, asset).previous_asset_id
    parent = db.get(CartonMarkAsset, previous_id) if previous_id else None
    if parent and parent.factory_id == asset.factory_id:
        orders.extend(related_orders(db, parent, seen))
    return orders


def filter_internal(db, user, values):
    from app.models.carton_procurement import CartonOrder
    from app.services import carton_special_requests as special
    allowed_values = []
    for value in values:
        if value.sharing_mode != 'ORDER_BOUND' or value.special_orders or value.workflow.previous_asset_id:
            try: ensure_asset_access(db, user, assets.active_asset(db, value.factory_id, value.id))
            except HTTPException: continue
        pending = []
        for entry in value.pending_bindings:
            order = db.get(CartonOrder, entry['order_id'])
            if not order or order.deleted_at or order.status == 'CANCELLED': continue
            try: ensure_customer(db, user, order)
            except HTTPException: continue
            pending.append(entry)
        value.pending_bindings = pending
        links = []
        for entry in value.special_orders:
            try: special.access(db, user, value.factory_id, entry['order_id'])
            except HTTPException: continue
            links.append(entry)
        value.special_orders = links
        allowed_values.append(value)
    return allowed_values


def ensure_asset_access(db, user, asset, *, write=False):
    state = current(db, asset)
    if state['sharing_mode'] == 'ORDER_BOUND' and not state['special_orders'] and not lifecycle.current(db, asset).previous_asset_id:
        return
    from app.services.auth import authorization_decision
    from app.services.carton_mark_library import CARTON_MARK_READ_DEPARTMENTS
    if not any(authorization_decision(user, 'carton_mark:read', asset.factory_id, dep)[0]
               for dep in CARTON_MARK_READ_DEPARTMENTS):
        raise HTTPException(403, '没有本厂共享箱唛资料读取权限')
    if write:
        from app.services.carton_mark_library import CARTON_MARK_WRITE_DEPARTMENTS
        if not any(authorization_decision(user, 'carton_mark:template_upload', asset.factory_id, dep)[0]
                   for dep in CARTON_MARK_WRITE_DEPARTMENTS):
            raise HTTPException(403, '没有本厂共享箱唛资料维护权限')
    for order in related_orders(db, asset): ensure_customer(db, user, order)


def validate_recipient(db, asset, mode, supplier_id):
    if mode != 'SUPPLIER':
        if supplier_id: raise HTTPException(422, '仅内部资料不能同时指定共享供应商')
        return '', ''
    choices = recipients(db, asset.factory_id)
    if not supplier_id and len(choices) == 1: supplier_id = choices[0]['id']
    chosen = next((x for x in choices if x['id'] == supplier_id), None)
    if chosen is None: raise HTTPException(422, '请选择本厂有效的共享供应商')
    # Sharing a known other supplier/customer's document must not bypass its
    # existing boundary merely because it is not currently issued.
    matches = related_orders(db, asset)
    if any(row.supplier_id != supplier_id for row in matches):
        raise HTTPException(422, '资料关联订单包含其他供应商，请先核实共享范围')
    if len({assets.identity(row.customer_code) for row in matches}) > 1:
        raise HTTPException(422, '资料包含多个客户，请明确关联订单后再共享')
    return chosen['id'], chosen['name']


def record(db, user, asset, mode, supplier_id=''):
    identifier, name = validate_recipient(db, asset, mode, supplier_id)
    assets.audit(db, user, asset, SHARED, dict(revision=asset.revision,
        sharing_mode=mode, shared_supplier_id=identifier, shared_supplier_name=name, sha256=asset.sha256))


def initialize(db, user, asset, options):
    if options.previous_asset_id:
        parent = assets.active_asset(db, asset.factory_id, options.previous_asset_id)
        ensure_asset_access(db, user, parent)
        previous = current(db, parent)
        record(db, user, asset, previous['sharing_mode'], previous['shared_supplier_id'])
    elif options.sharing_mode != 'ORDER_BOUND':
        record(db, user, asset, options.sharing_mode, options.supplier_id)


def change(db, user, factory, identifier, payload):
    user = internal_actor(db, user, factory)
    asset = assets.active_asset(db, factory, identifier)
    for order in related_orders(db, asset):
        ensure_customer(db, user, order)
    validate_recipient(db, asset, payload.sharing_mode, payload.supplier_id)
    lifecycle.bump(db, asset, payload.revision)
    record(db, user, asset, payload.sharing_mode, payload.supplier_id)
    db.commit()
    return assets.asset_out(asset, assets.available_orders(db, factory))


def internal_actor(db, user, factory):
    from app.services.carton_special_requests import locked_actor
    from app.services.carton_mark_library import ensure_carton_mark_scope, CARTON_MARK_WRITE_DEPARTMENTS
    user = locked_actor(db, user, factory)
    ensure_carton_mark_scope(db, user, 'carton_mark:template_upload', factory, CARTON_MARK_WRITE_DEPARTMENTS)
    from app.services.auth import authorization_decision
    if not any(authorization_decision(user, 'carton_mark:template_upload', factory, dep)[0]
               for dep in CARTON_MARK_WRITE_DEPARTMENTS):
        raise HTTPException(403, '没有本厂共享箱唛资料维护权限')
    return user


def validate_binding_change(db, user, asset, payload):
    ensure_asset_access(db, user, asset, write=True)
    state = current(db, asset)
    if state['sharing_mode'] == 'ORDER_BOUND': return
    orders = assets.available_orders(db, asset.factory_id)
    selected = [o for o in orders if o.id in (payload.order_ids or []) or o.id == payload.order_id
        or (not payload.order_ids and not payload.order_id and payload.contract_number
            and assets.identity(o.contract_no) == assets.identity(payload.contract_number))]
    for order in selected:
        ensure_customer(db, user, order)
        if state['sharing_mode'] == 'SUPPLIER' and order.supplier_id != state['shared_supplier_id']:
            raise HTTPException(422, '所选订单与此资料共享供应商不一致')
    if len({assets.identity(x.customer_code) for x in related_orders(db, asset) + selected}) > 1:
        raise HTTPException(422, '此资料已用于其他客户的样板或杂单，请分别维护')


def propose(db, user, factory, identifier, payload):
    from app.services import carton_supplier_portal as portal
    from app.services.carton_special_requests import locked_actor
    user = locked_actor(db, user, factory)
    supplier = portal.supplier_access(db, user, factory, 'carton_supplier:edit')
    asset = portal.supplier_mark_asset_document(db, user, factory, identifier)
    if asset.photo_group_id:
        raise HTTPException(409, '整组照片请由仓库统一关联，或先解除分组')
    _, _, eligible = portal._supplier_mark_orders(db, user, factory)
    requested = set(payload.order_ids)
    if len(requested) != len(payload.order_ids) or not requested <= set(eligible):
        raise HTTPException(404, '请选择本供应商当前已下单订单')
    existing = related_orders(db, asset)
    targets = [row for row in assets.available_orders(db, factory) if row.id in requested]
    if len({assets.identity(row.customer_code) for row in existing + targets}) > 1:
        raise HTTPException(422, '同一资料不能跨客户关联，请分别上传和核实')
    lifecycle.bump(db, asset, payload.revision)
    pending = current(db, asset)['pending_bindings']
    for identifier in sorted(requested):
        if any(x['order_id'] == identifier and x['supplier_id'] == supplier.id for x in pending): continue
        target = next(x for x in targets if x.id == identifier)
        assets.audit(db, user, asset, PROPOSED, dict(id='CMB-' + uuid4().hex,
            order_id=identifier, order_no=target.order_no, contract_no=eligible[identifier]['contract_no'],
            item_no=eligible[identifier]['item_no'], issue_id=eligible[identifier]['issue_id'],
            supplier_id=supplier.id, sha256=asset.sha256, requested_at=_now_text()))
    db.commit()
    return next(x for x in portal.supplier_mark_assets(db, user, factory) if x['id'] == asset.id)


def confirm(db, user, factory, identifier, binding_id, payload):
    from app.services import carton_supplier_portal as portal
    user = internal_actor(db, user, factory)
    asset = assets.active_asset(db, factory, identifier)
    if asset.photo_group_id:
        raise HTTPException(409, '整组照片请由仓库统一关联，或先解除分组')
    request = next((x for x in current(db, asset)['pending_bindings'] if x['id'] == binding_id), None)
    if request is None: raise HTTPException(404, '未找到待确认的关联')
    order = portal.supplier_order(db, request['order_id'], factory, request['supplier_id'])
    ensure_customer(db, user, order)
    issue = portal.latest_issue(db, order)
    if order.deleted_at or order.status == 'CANCELLED' or not issue or issue.id != request['issue_id'] or request['sha256'] != asset.sha256:
        raise HTTPException(409, '订单或资料已变化，请重新绑定')
    supplier = db.get(CartonSupplier, request['supplier_id'])
    if not supplier or supplier.factory_id != factory or supplier.status != 'ACTIVE':
        raise HTTPException(409, '供应商已停用，请重新核实共享对象')
    if portal._purchase_order_snapshot(issue).get('order', {}).get('supplier_id') != supplier.id:
        raise HTTPException(409, '采购单供应商已变化，请重新绑定')
    current_state = current(db, asset)
    if current_state['sharing_mode'] == 'INTERNAL' or (current_state['sharing_mode'] == 'SUPPLIER'
            and current_state['shared_supplier_id'] != request['supplier_id']):
        raise HTTPException(409, '共享范围已变化，请重新核实')
    existing = assets.matching_asset_orders(asset, assets.available_orders(db, factory))
    if len({assets.identity(row.customer_code) for row in related_orders(db, asset) + [order]}) > 1:
        raise HTTPException(422, '同一资料不能跨客户关联')
    lifecycle.bump(db, asset, payload.revision)
    identifiers = {x.id for x in existing} | {order.id}
    asset.recognition_source = 'manual_orders'; asset.bound_order_id = None; asset.contract_number = ''
    previous = {x.order_id: x for x in asset.order_bindings}
    asset.order_bindings[:] = [previous.get(x) or CartonMarkAssetOrderBinding(asset_id=asset.id,
        factory_id=factory, order_id=x) for x in sorted(identifiers)]
    assets.audit(db, user, asset, DECIDED, dict(id=binding_id, order_id=order.id,
        revision=asset.revision, sha256=asset.sha256))
    db.commit()
    return assets.asset_out(asset, assets.available_orders(db, factory))


def binding_targets(db, user, factory, external=False):
    from app.services import carton_supplier_portal as portal
    from app.services import carton_special_requests as special
    if external:
        portal.supplier_access(db, user, factory, 'carton_supplier:edit')
        _, _, eligible = portal._supplier_mark_orders(db, user, factory)
    else: eligible = None
    result = []
    for o in assets.available_orders(db, factory):
        if eligible is not None and o.id not in eligible: continue
        if not external:
            try: ensure_customer(db, user, o)
            except HTTPException: continue
        result.append(dict(order_id=o.id, order_kind='REGULAR', order_no=o.order_no, contract_no=o.contract_no,
            customer_name=o.customer_name, item_no=o.item_no, revision=o.revision, lines=[]))
    from app.models.carton_special_requests import SpecialRequest
    for row in db.scalars(select(SpecialRequest).where(SpecialRequest.factory_id == factory, SpecialRequest.status != 'CANCELLED')):
        try: special.access(db, user, factory, row.id, external=external)
        except HTTPException: continue
        if not special.flags(db, user, row, external)['can_attach' if external else 'can_confirm_material']: continue
        result.append(dict(order_id=row.id, order_kind='SAMPLE' if row.kind == 'SAMPLE' else 'MISC', order_no=row.request_no, contract_no='',
            customer_name=row.customer_name, item_no='', revision=row.revision,
            lines=[dict(id=line.id, label=f'{line.packaging_type} · {line.item_no}') for line in special.lines(db, row)]))
    return result
