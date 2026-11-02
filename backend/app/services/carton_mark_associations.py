"""Direct, version-checked file evidence; never a procurement or QC approval."""
import hashlib
import json
from fastapi import HTTPException
from sqlalchemy import select
from app.models.carton_procurement import CartonAuditEvent
from app.models.carton_mark import CartonMarkAssetOrderBinding
from app.services import carton_mark_assets as assets, carton_mark_sharing as sharing
from app.services import carton_mark_asset_workflow as lifecycle


def freeze_files(db, user, order, *, order_kind='REGULAR'):
    if order_kind == 'REGULAR':
        from app.services.carton_print_split import order_info, download
        info = order_info(db, order)
        if info and info['status'] == 'ACTIVE' and (info.get('print_changed', True) or info['files']):
            result = []
            for file in info['files']:
                download(db, user, order.factory_id, info['id'], file['id'], supplier=True)
                result.append(dict(asset_id=file.get('asset_id', file['id']), print_file_id=file['id'], asset_revision=file['revision'], sha256=file['sha256'],
                    filename=file['file_name'], line_id='', print_split_id=info['id']))
            return result
    """Freeze current shared originals without certifying printing or QC readiness."""
    from app.models.carton_mark import CartonMarkAsset
    from app.models.carton_special_requests import SpecialAttachment
    from app.services import carton_special_requests as special
    from app.services.carton_supplier_portal import _supplier_mark_assets
    audiences = sharing.states(db, order.factory_id)
    result = []
    for asset, visible_orders in _supplier_mark_assets(db, user, order.factory_id):
        audience = audiences.get(asset.id, {})
        if audience.get('sharing_mode') == 'INTERNAL' or (audience.get('sharing_mode') == 'SUPPLIER'
                and audience.get('shared_supplier_id') != order.supplier_id): continue
        if lifecycle.current(db, asset).status == 'HISTORY': continue
        if order_kind == 'REGULAR':
            if not any(x['id'] == order.id for x in visible_orders): continue
            line_ids = ['']
        else:
            line_ids = sorted({x.get('line_id', '') for x in audience.get('special_orders', []) if x['order_id'] == order.id})
            if not line_ids: continue
        for line_id in line_ids:
            evidence = dict(asset_id=asset.id, asset_revision=asset.revision, sha256=asset.sha256,
                filename=asset.file_name, line_id=line_id)
            if order_kind != 'REGULAR':
                # Archived/rebound library records cannot erase dispatched bytes.
                attachment = SpecialAttachment(id=special.uid('CSA-SP-'), factory_id=order.factory_id,
                    request_id=order.id, line_id=line_id, role='REFERENCE', filename=asset.file_name,
                    media_type=asset.content_type, sha256=asset.sha256, size=asset.size_bytes, content=asset.content,
                    created_by=user.id, created_at=special.core.now_text(), version=special.next_attachment_version(db, order))
                db.add(attachment)
                evidence['attachment_id'] = attachment.id
            result.append(evidence)
    return result


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def request_event(db, user, factory, request_id, action, data):
    if not request_id: return '', None
    identifier = 'CAE-MARK-' + hashlib.sha256(f'{factory}:{user.id}:{action}:{request_id}'.encode()).hexdigest()
    event = db.scalar(select(CartonAuditEvent).where(CartonAuditEvent.id == identifier))
    digest = fingerprint(data)
    if event:
        saved = json.loads(event.detail_json)
        if saved['fingerprint'] != digest: raise HTTPException(409, '此请求已使用其他文件或关联内容，请刷新后核实')
        return identifier, saved
    return identifier, {'fingerprint': digest}


def record_request(db, user, asset, identifier, saved, result):
    if not identifier: return
    from app.services.carton_mark_library import _now_text
    db.add(CartonAuditEvent(id=identifier, factory_id=asset.factory_id, event_type='CARTON_MARK_REQUEST_SAVED',
        entity_type='carton_mark_asset', entity_id=asset.id,
        detail_json=json.dumps(saved | {'result': result}, ensure_ascii=False, sort_keys=True),
        actor_user_id=user.id, actor_name=user.display_name, created_at=_now_text()))
    db.flush()


def projection(db, asset, regular, audience):
    from app.services import carton_supplier_portal as portal, carton_special_requests as special
    from app.models.carton_special_requests import SpecialRequest, SpecialVersion
    result = []
    for row in regular:
        from app.models.carton_procurement import CartonOrder
        row = db.get(CartonOrder, row.id)
        if not row or row.deleted_at or row.status == 'CANCELLED': continue
        issue = portal.latest_issue(db, row)
        result.append(dict(order_kind='REGULAR', order_id=row.id, order_no=row.order_no,
            contract_no=row.contract_no, customer_name=row.customer_name, item_no=row.item_no,
            expected_revision=row.revision, issue_id=issue.id if issue else '', line_id=''))
    seen = set()
    for link in audience.get('special_orders', []):
        key = (link['order_id'], link.get('line_id', ''))
        if key in seen: continue
        seen.add(key)
        row = db.get(SpecialRequest, link['order_id'])
        if not row or row.factory_id != asset.factory_id or row.status == 'CANCELLED' or db.scalar(select(SpecialVersion.id).where(
                SpecialVersion.request_id == row.id, SpecialVersion.action == 'DELETED').limit(1)): continue
        result.append(dict(order_kind='SAMPLE' if row.kind == 'SAMPLE' else 'MISC', order_id=row.id,
            order_no=row.request_no, contract_no='', customer_name=row.customer_name, item_no='',
            expected_revision=row.revision, issue_id=row.current_version_id, line_id=link.get('line_id', '')))
    return result


def target_rows(db, user, factory, targets, *, external=False):
    from app.services import carton_supplier_portal as portal, carton_special_requests as special
    from app.models.carton_special_requests import SpecialVersion
    supplier = portal.supplier_access(db, user, factory, 'carton_supplier:edit') if external else None
    eligible = portal._supplier_mark_orders(db, user, factory)[2] if external else None
    regular = {o.id: o for o in assets.available_orders(db, factory)}
    result, seen = [], set()
    for item in targets:
        key = (item.order_kind, item.order_id, item.line_id)
        if key in seen: raise HTTPException(422, '关联目标不能重复')
        seen.add(key)
        if item.order_kind == 'REGULAR':
            row = regular.get(item.order_id)
            if not row or (external and row.id not in eligible): raise HTTPException(404, '未找到可关联的当前采购订单')
            if item.line_id: raise HTTPException(422, '正单资料按订单关联，无需指定纸品')
            issue = portal.latest_issue(db, row)
            issue_id = issue.id if issue else ''
            if item.issue_id != issue_id or item.expected_revision != row.revision:
                raise HTTPException(409, '采购订单版本已变化，请刷新关联目标')
            if not external: sharing.ensure_customer(db, user, row)
            result.append(dict(order_kind='REGULAR', order_id=row.id, order_no=row.order_no,
                contract_no=row.contract_no, item_no=row.item_no, customer_name=row.customer_name,
                customer_code=row.customer_code, supplier_id=row.supplier_id, expected_revision=row.revision,
                issue_id=issue_id, line_id=''))
        else:
            row = special.access(db, user, factory, item.order_id, external=external)
            if row.status == 'CANCELLED' or db.scalar(select(SpecialVersion.id).where(
                    SpecialVersion.factory_id == factory, SpecialVersion.request_id == row.id, SpecialVersion.action == 'DELETED').limit(1)):
                raise HTTPException(409, '已取消或删除的订单不能新关联资料')
            expected_kind = 'SAMPLE' if row.kind == 'SAMPLE' else 'MISC'
            if item.order_kind != expected_kind: raise HTTPException(422, '订单类别不匹配')
            if row.revision != item.expected_revision or row.current_version_id != item.issue_id:
                raise HTTPException(409, '纸品订单版本已变化，请刷新关联目标')
            if supplier and row.supplier_id != supplier.id: raise HTTPException(404, '未找到此供应商订单')
            if not external: sharing.ensure_customer(db, user, row)
            if item.line_id and not any(x.id == item.line_id for x in special.lines(db, row)):
                raise HTTPException(404, '纸品不属于此订单')
            result.append(dict(order_kind=item.order_kind, order_id=row.id, order_no=row.request_no,
                contract_no='', item_no='', customer_name=row.customer_name, customer_code=row.customer_code,
                supplier_id=row.supplier_id, expected_revision=row.revision, issue_id=row.current_version_id, line_id=item.line_id))
    return result


def apply(db, user, asset, targets, *, external=False, bump_revision=None):
    from app.services import carton_asset_access as ownership,carton_supplier_portal as portal
    if external and ownership.managed(asset):
        ownership.ensure(db,user,asset,write=True,supplier=portal.supplier_access(db,user,asset.factory_id,'carton_supplier:edit'))
    rows = target_rows(db, user, asset.factory_id, targets, external=external)
    audience = sharing.current(db, asset)
    previous = sharing.related_orders(db, asset)
    if not external:
        sharing.ensure_asset_access(db, user, asset, write=True)
        for row in previous: sharing.ensure_customer(db, user, row)
    suppliers = {x.supplier_id for x in previous} | {x['supplier_id'] for x in rows}
    customers = {assets.identity(x.customer_code) for x in previous} | {assets.identity(x['customer_code']) for x in rows}
    if len(suppliers) > 1 or (audience['sharing_mode'] == 'SUPPLIER' and any(
            x != audience['shared_supplier_id'] for x in suppliers)):
        raise HTTPException(422, '资料与目标订单供应商不一致，请分别维护')
    if len(customers) > 1: raise HTTPException(422, '同一资料不能跨客户关联，请分别维护')
    if lifecycle.current(db, asset).status == 'HISTORY': raise HTTPException(409, '历史资料不能新关联，请选择当前原件')
    if asset.photo_group_id: raise HTTPException(409, '整组照片请先解除分组，再调整关联')
    if bump_revision is not None: lifecycle.bump(db, asset, bump_revision)
    existing = {x.order_id: x for x in asset.order_bindings}
    identifiers = {x['order_id'] for x in rows if x['order_kind'] == 'REGULAR'}
    asset.recognition_source = 'manual_orders'; asset.bound_order_id = None; asset.contract_number = ''
    asset.order_bindings[:] = [existing.get(x) or CartonMarkAssetOrderBinding(asset_id=asset.id,
        factory_id=asset.factory_id, order_id=x) for x in sorted(identifiers)]
    resolved = [x['id'] for x in audience['pending_bindings'] if x['order_id'] in identifiers]
    assets.audit(db, user, asset, sharing.ASSOCIATED,
        {'revision': asset.revision, 'targets': rows, 'resolved_pending_ids': resolved, 'sha256': asset.sha256})
    from app.services import carton_asset_targets
    carton_asset_targets.sync_legacy(db,user,asset)
    db.flush()
    return rows


def save(db, user, factory, identifier, payload, *, external=False):
    from app.services import carton_special_requests as special, carton_supplier_portal as portal
    user = special.locked_actor(db, user, factory) if external else sharing.internal_actor(db, user, factory)
    if external:
        portal.supplier_access(db, user, factory, 'carton_supplier:edit')
        asset = portal.supplier_mark_asset_document(db, user, factory, identifier)
        from app.services import carton_asset_access as ownership
        if ownership.managed(asset):
            ownership.ensure(db,user,asset,write=True,supplier=portal.supplier_access(db,user,factory,'carton_supplier:edit'))
    else:
        asset = assets.active_asset(db, factory, identifier)
        sharing.ensure_asset_access(db, user, asset, write=True)
    request_id, saved = request_event(db, user, factory, payload.request_id, 'ASSOCIATE',
        {'asset_id': identifier, **payload.model_dump(mode='json')})
    if not saved or 'result' not in saved:
        apply(db, user, asset, payload.targets, external=external, bump_revision=payload.revision)
        record_request(db, user, asset, request_id, saved, {'asset_id': asset.id})
        db.commit()
    return next(x for x in portal.supplier_mark_assets(db, user, factory) if x['id'] == asset.id) if external \
        else assets.asset_out(asset, assets.available_orders(db, factory))
