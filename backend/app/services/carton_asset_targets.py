"""Explicit old-asset targets, including pre-purchase schedule identity snapshots."""
import hashlib,json
from collections import defaultdict
from sqlalchemy import select
from fastapi import HTTPException
from app.models.carton_procurement import CartonImportBatch,CartonAuditEvent
from app.services import carton_mark_assets as assets
from app.services.carton_schedule_tracking import effective_po, identity as schedule_identity, material_identity, normalized, tracked

EVENT='CARTON_ASSET_TARGETS_V1'


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()


def identity(row):
    return list(material_identity(row))


def schedules(db,factory):
    seen=set(); result=[]
    from app.services import carton_procurement as core
    from app.services.carton_schedule_tracking import mark_for_row
    state=core.schedule_order_state(db,factory)
    orders=assets.available_orders(db,factory)
    from app.services.carton_schedule_coverage import batches
    # Reimports may share the same second. The existing immutable import audit
    # sequence, rather than random batch IDs, defines the newest source.
    for entry in batches(db,factory):
        batch=entry['batch']
        if batch.status=='REJECTED':continue
        summary=core.import_batch_out(batch).parse_summary
        customer=summary.get('schedule_customer') or {};code=customer.get('customer_code','')
        if not code or assets.identity(code) in seen:continue
        seen.add(assets.identity(code))
        for row in summary.get('rows',[]):
            if not isinstance(row,dict) or row.get('schedule_section') not in (None,'','PENDING'): continue
            item=dict(kind='SCHEDULE',id=batch.id,sheet=row.get('source_sheet',''),row=row.get('source_row',0),
                customer_code=row.get('schedule_customer_code') or code,customer_name=customer.get('customer_name',''),
                contract_no=row.get('contract_no',''),item_no=row.get('item_no',''),customer_po=effective_po(row),supplier_id='')
            if not item['sheet'] or not item['row']:continue
            item['identity']=identity(item);item['fingerprint']=digest(dict(batch=batch.id,row=row,customer=code))
            item['ordered']=bool(mark_for_row(row,state).get('marked') or
                state.get(row.get('schedule_identity'),{}).get('order_ids') or
                any(identity(dict(customer_code=o.customer_code,contract_no=o.contract_no,item_no=o.item_no,customer_po=o.customer_po))==item['identity'] for o in orders))
            result.append(item)
    return result


def customer_allowed(db,user,factory,code):
    # Reuse the existing current customer responsibility rule; no quote customers.
    from app.services.carton_customer_assignment import ensure_customer_operation
    if not code:raise HTTPException(403,'资料目标缺少受管客户')
    ensure_customer_operation(db,user,factory,code)


def schedule_customer_allowed(db,user,factory,code):
    # Sales owns the upstream schedule. Warehouse responsibility assignments
    # cannot take away a sales operator's existing factory schedule authority.
    from app.services import carton_asset_access as access
    from app.services.business_authz import canonical_permission_for_departments
    from app.models.carton_procurement import CartonCustomer
    if access.allowed(user,factory,'sales-business','manage') and canonical_permission_for_departments(
            user,'customer_order:read',factory,('sales-business',)) and db.scalar(select(CartonCustomer.id).where(
                CartonCustomer.factory_id==factory,CartonCustomer.customer_code==code,CartonCustomer.status=='ACTIVE')):
        return
    customer_allowed(db,user,factory,code)


def candidates(db,user,factory,contract='',*,supplier=None,scope='ALL',retain=None):
    from app.services import carton_supplier_portal as portal
    result=[]
    eligible=portal._supplier_mark_orders(db,user,factory)[2] if supplier else None
    for order in assets.available_orders(db,factory):
        if supplier and order.id not in eligible:continue
        try:
            if not supplier:customer_allowed(db,user,factory,order.customer_code)
        except HTTPException:continue
        issue=portal.latest_issue(db,order)
        snapshot=eligible[order.id] if supplier else {}
        row=dict(kind='REGULAR',id=order.id,sheet='',row=0,contract_no=snapshot.get('contract_no',order.contract_no),
            item_no=snapshot.get('item_no',order.item_no),customer_code=order.customer_code,
            customer_name=snapshot.get('customer_name',order.customer_name),customer_po=snapshot.get('customer_po',order.customer_po),
            supplier_id=order.supplier_id,revision=order.revision,issue_id=issue.id if issue else '')
        row['identity']=identity(row);row['fingerprint']=digest(row);result.append(row)
    if not supplier and scope!='ORDERS':
        for row in schedules(db,factory):
            try:schedule_customer_allowed(db,user,factory,row['customer_code'])
            except HTTPException:continue
            result.append(row)
    # Existing explicit sample/misc association contracts remain reusable.
    from app.services import carton_mark_sharing as sharing
    try: special_rows=sharing.binding_targets(db,user,factory,external=bool(supplier))
    except HTTPException: special_rows=[]
    for value in special_rows:
        if value['order_kind']=='REGULAR':continue
        from app.models.carton_special_requests import SpecialRequest
        special=db.get(SpecialRequest,value['order_id'])
        if not special:continue
        row=dict(kind=value['order_kind'],id=value['order_id'],sheet='',row=0,
            contract_no=value.get('contract_no',''),item_no=value.get('item_no',''),
            customer_code=special.customer_code,customer_name=value.get('customer_name',''),customer_po='',
            supplier_id=special.supplier_id,revision=value.get('revision',value.get('expected_revision',0)),issue_id=value.get('issue_id',''))
        row['identity']=identity(row);row['fingerprint']=digest(row)
        # Display metadata must not invalidate existing applicability fingerprints.
        row.update(order_no=value.get('order_no',''),ordered_at=value.get('ordered_at',''))
        result.append(row)
    # Do not collapse an unproven order/schedule match into a fictitious singleton.
    if contract:result=[x for x in result if assets.identity(x['contract_no'])==assets.identity(contract)]
    if supplier and retain is not None:
        from app.services.carton_asset_supplier_collaboration import internal
        if internal(retain):
            codes={row['customer_code'] for row in current(db,retain)}
            result=[row for row in result if row['customer_code'] in codes]
    if scope=='PENDING_SCHEDULE':
        retained_rows=valid(db,retain,factory) if retain else []
        retained={(x['kind'],x['id'],x['sheet'],x['row']) for x in retained_rows}
        result=[x for x in result if (x['kind']=='SCHEDULE' and not x.get('ordered')) or
            (x['kind'],x['id'],x['sheet'],x['row']) in retained]
        existing={(x['kind'],x['id'],x['sheet'],x['row']) for x in result}
        for row in retained_rows:
            if supplier or (row['kind'],row['id'],row['sheet'],row['row']) in existing:continue
            try:
                (schedule_customer_allowed if row['kind']=='SCHEDULE' else customer_allowed)(db,user,factory,row['customer_code'])
            except HTTPException:continue
            if not contract or assets.identity(row['contract_no'])==assets.identity(contract):result.append(row)
    return result


def resolve(db,user,factory,target,*,supplier=None,scope='ALL',retain=None):
    values=candidates(db,user,factory,supplier=supplier,scope=scope,retain=retain)
    found=next((x for x in values if (x['kind'],x['id'],x['sheet'],x['row'])==(target.kind,target.id,target.sheet,target.row)),None)
    if not found:raise HTTPException(404,'关联目标不存在、已失效或无当前权限')
    if target.fingerprint!=found['fingerprint']:raise HTTPException(409,'关联目标已更新，请刷新重新选择')
    return found


def states(db,factory,ids=None):
    query=select(CartonAuditEvent).where(CartonAuditEvent.factory_id==factory,
        CartonAuditEvent.entity_type=='carton_mark_asset',CartonAuditEvent.event_type==EVENT)
    if ids is not None:
        if not ids:return {}
        query=query.where(CartonAuditEvent.entity_id.in_(ids))
    result={}
    for event in db.scalars(query.order_by(CartonAuditEvent.sequence)):
        result[event.entity_id]=json.loads(event.detail_json).get('targets',[])
    return result


def current(db,asset,factory=None):
    factory=factory or asset.factory_id
    saved=states(db,factory,[asset.id])
    # A recorded empty target set is an explicit unlink. Fallback is limited to
    # trustworthy owned legacy originals with physical, explicit bindings.
    return saved[asset.id] if asset.id in saved else legacy_targets(db,asset) if factory==asset.factory_id else []


def legacy_targets(db,asset,*,current_authorized=False):
    if not asset.owner_department:
        # Read the original matcher without changing its mode, IDs or bindings.
        # In particular, manual_orders + [] is an intentional empty selection.
        orders=assets.matching_asset_orders(asset,assets.available_orders(db,asset.factory_id))
        if asset.recognition_source not in {'manual_orders','manual_order'} and not asset.bound_order_id:
            if len({assets.identity(o.customer_code) for o in orders})>1:orders=[]
        result=[]
        for order in orders:
            row=dict(kind='REGULAR',id=order.id,sheet='',row=0,customer_code=order.customer_code,
                customer_name=order.customer_name,contract_no=order.contract_no,item_no=order.item_no,
                customer_po=order.customer_po,supplier_id=order.supplier_id,revision=order.revision)
            row['identity']=identity(row);row['fingerprint']=digest(row);result.append(row)
        # Special links already carry their frozen customer/supplier evidence.
        from app.services.carton_mark_sharing import current as sharing_current
        for link in sharing_current(db,asset)['special_orders']:
            if not link.get('customer_code') or not link.get('supplier_id'):continue
            row=dict(kind=link['order_kind'],id=link['order_id'],sheet='',row=0,
                customer_code=link['customer_code'],contract_no='',item_no='',customer_po='',
                supplier_id=link['supplier_id'],line_id=link.get('line_id',''))
            row['identity']=identity(row);row['fingerprint']=digest(row);result.append(row)
        return result
    from app.models.carton_procurement import CartonOrder
    from app.models.carton_special_requests import SpecialRequest
    from app.services import carton_mark_sharing as sharing
    ids={x.order_id for x in asset.order_bindings}
    if asset.bound_order_id:ids.add(asset.bound_order_id)
    result=[]
    snapshots={}
    audience=sharing.current(db,asset)
    for target in audience.get('associations',[]):
        if target['order_kind']=='REGULAR' and target.get('customer_code'):
            snapshots[target['order_id']]=target
    from app.models.carton_procurement import CartonPurchaseOrderIssue
    for event in db.scalars(select(CartonAuditEvent).where(CartonAuditEvent.factory_id==asset.factory_id,
            CartonAuditEvent.entity_id==asset.id,CartonAuditEvent.entity_type=='carton_mark_asset',
            CartonAuditEvent.event_type=='CARTON_MARK_ASSET_CREATED',CartonAuditEvent.actor_user_id==asset.created_by)):
        context=json.loads(event.detail_json).get('supplier_context',{})
        issue=db.get(CartonPurchaseOrderIssue,context.get('issue_id','')) if context.get('issue_id') else None
        if issue and issue.factory_id==asset.factory_id:
            from app.services.carton_supplier_portal import _purchase_order_snapshot
            frozen=_purchase_order_snapshot(issue).get('order',{})
            if frozen.get('supplier_id')==asset.owner_supplier_id:
                snapshots[context.get('order_id','')]=frozen
    for identifier in sorted(ids):
        order=db.get(CartonOrder,identifier)
        if not order or order.factory_id!=asset.factory_id:continue
        original=snapshots.get(identifier)
        if not current_authorized and not original:continue
        value=(dict(customer_code=order.customer_code,contract_no=order.contract_no,item_no=order.item_no,
            customer_po=order.customer_po,supplier_id=order.supplier_id) if current_authorized else original)
        row=dict(kind='REGULAR',id=order.id,sheet='',row=0,customer_code=order.customer_code,
            contract_no=order.contract_no,item_no=order.item_no,customer_po=order.customer_po,
            supplier_id=order.supplier_id,revision=order.revision)
        row.update({k:value.get(k,'') for k in ('customer_code','contract_no','item_no','customer_po','supplier_id')})
        row['identity']=identity(row);row['fingerprint']=digest(row);result.append(row)
    for link in audience['special_orders']:
        order=db.get(SpecialRequest,link['order_id'])
        if not order or order.factory_id!=asset.factory_id:continue
        # Link audit is the original customer/supplier evidence, not the current
        # mutable order alone. Old links without that evidence cannot project.
        if not link.get('customer_code') or not link.get('supplier_id'):continue
        row=dict(kind='SAMPLE' if order.kind=='SAMPLE' else 'MISC',id=order.id,sheet='',row=0,
            customer_code=link['customer_code'],contract_no='',item_no='',customer_po='',
            supplier_id=link['supplier_id'],line_id=link.get('line_id',''))
        row['identity']=identity(row);row['fingerprint']=digest(row);result.append(row)
    return result


def _saved_schedule_source(db, factory, target, cache):
    from app.services import carton_procurement as core

    batch = db.get(CartonImportBatch, target['id'])
    if not batch or batch.factory_id != factory or batch.import_type != 'WEEKLY_SCHEDULE' or batch.status == 'REJECTED':
        return None, '', False
    _, source, key = core._schedule_event_source(db, factory, '', {
        'batch_id': batch.id, 'source_sheet': target['sheet'], 'source_row': target['row'],
    }, cache)
    if source is None:
        return None, '', False
    index = cache[batch.id]
    code = source.get('schedule_customer_code') or index.customer_code
    if identity({**source, 'customer_code': code}) != target['identity']:
        return None, '', False
    unique = key == schedule_identity(source) and index.pending_source_is_unique(source)
    return source, key, unique


def _purchase_links(db, factory):
    from app.services import carton_procurement as core

    links = defaultdict(list)
    for key, order, evidence, detail in core._schedule_order_link_evidence(db, factory):
        if evidence is not None:
            links[key].append((order, evidence, detail))
    return links


def _schedule_purchase_ids(target, source, unique, links):
    source_po = normalized(source.get('customer_po'))
    result = set()
    for order, (original, original_unique), detail in links:
        exact = (detail.get('batch_id'), detail.get('source_sheet'), detail.get('source_row')) == (
            target['id'], target['sheet'], target['row'])
        if not exact and (not unique or not original_unique or not tracked(source)):
            continue
        # SO identifies the schedule row. The actual P/O# belongs to the
        # purchase; only legacy creation evidence can treat SO as that PO.
        if source_po != normalized(original.get('customer_po')):
            continue
        order_po = normalized(order.customer_po)
        po_matches = order_po == source_po or (detail.get('po_semantics') != 'SOURCE_PO' and order_po == effective_po(source))
        order_identity = identity(dict(customer_code=order.customer_code, contract_no=order.contract_no, item_no=order.item_no))
        if po_matches and order_identity[:3] == target['identity'][:3]:
            result.add(order.id)
    return result


def valid(db,asset,factory=None,*,schedule_rows_by_factory=None):
    factory=factory or asset.factory_id
    from app.models.carton_procurement import CartonOrder
    latest=None;result=[]
    source_cache = {}
    links = None
    for target in current(db,asset,factory):
        if target['kind']=='SCHEDULE':
            # Unassociated/ordinary-order sources do not need a factory schedule
            # scan. A library read may reuse rows within this one response only.
            if latest is None:
                if schedule_rows_by_factory is None:
                    latest=schedules(db,factory)
                else:
                    if factory not in schedule_rows_by_factory:
                        schedule_rows_by_factory[factory]=schedules(db,factory)
                    latest=schedule_rows_by_factory[factory]
            exact=[x for x in latest if (x['id'],x['sheet'],x['row'],x['identity'])==(target['id'],target['sheet'],target['row'],target['identity'])]
            if len(exact) == 1:
                result.append(exact[0])
                continue
            original, key, unique = _saved_schedule_source(db, factory, target, source_cache)
            if original is None:
                continue
            # An old duplicate has only its original batch/sheet/row identity.
            # A later singleton does not tell us which of the duplicates survived.
            matches = [x for x in latest if x['identity'] == target['identity']] if unique else []
            if len(matches) == 1:
                current_source, _, _ = _saved_schedule_source(db, factory, matches[0], source_cache)
                if current_source is not None and normalized(current_source.get('customer_po')) == normalized(original.get('customer_po')):
                    result.append(matches[0])
                    continue
            if factory == asset.factory_id:
                if links is None:
                    links = _purchase_links(db, factory)
                if _schedule_purchase_ids(target, original, unique, links.get(key, ())):
                    result.append(dict(target, ordered=True))
        elif target['kind']=='REGULAR':
            order=db.get(CartonOrder,target['id'])
            if order and order.factory_id==factory and not order.deleted_at and order.status!='CANCELLED':
                row=dict(customer_code=order.customer_code,contract_no=order.contract_no,item_no=order.item_no,customer_po=order.customer_po)
                if identity(row)==target['identity'] and order.supplier_id==target['supplier_id']:result.append(target)
        elif target['kind'] in {'SAMPLE','MISC'}:
            from app.models.carton_special_requests import SpecialRequest,SpecialVersion,SpecialLine
            order=db.get(SpecialRequest,target['id'])
            if order and order.factory_id==factory and order.status not in {'SUBMITTED','CANCELLED'} and order.supplier_id==target.get('supplier_id') \
                    and identity(dict(customer_code=order.customer_code))==target['identity'] \
                    and (not target.get('line_id') or db.scalar(select(SpecialLine.id).where(SpecialLine.id==target['line_id'],SpecialLine.request_id==order.id))) \
                    and not db.scalar(select(SpecialVersion.id).where(SpecialVersion.request_id==order.id,SpecialVersion.action=='DELETED').limit(1)):
                result.append(target)
    return result


def record(db,user,asset,rows,factory=None):
    factory=factory or asset.factory_id
    if factory!=asset.factory_id:
        from app.services.carton_procurement import _audit
        _audit(db,user,factory,EVENT,'carton_mark_asset',asset.id,dict(revision=asset.revision,targets=rows,sha256=asset.sha256))
        db.flush()
        return
    from app.models.carton_mark import CartonMarkAssetOrderBinding
    asset.recognition_source='manual_orders';asset.bound_order_id=None
    asset.order_bindings[:]=[CartonMarkAssetOrderBinding(asset_id=asset.id,factory_id=asset.factory_id,order_id=x['id']) for x in rows if x['kind']=='REGULAR']
    assets.audit(db,user,asset,EVENT,dict(revision=asset.revision,targets=rows,sha256=asset.sha256))
    db.flush()


def source_purchase_order_ids(db,asset,*,schedule_target=None):
    """Follow explicit schedule creation evidence, never a contract-wide guess.

    Read the saved source batch so later schedule removal cannot erase a purchase
    link. Current order identity and factory still have to match that source.
    """
    from app.models.carton_procurement import CartonOrder
    result=set()
    source_cache = {}
    links = None
    for target in [schedule_target] if schedule_target else current(db,asset):
        if target['kind']=='REGULAR':
            order=db.get(CartonOrder,target['id'])
            if order and order.factory_id==asset.factory_id and not order.deleted_at and order.status!='CANCELLED' and order.supplier_id==target.get('supplier_id') and identity(dict(
                customer_code=order.customer_code,contract_no=order.contract_no,item_no=order.item_no,customer_po=order.customer_po))==target['identity']:result.add(order.id)
            continue
        if target['kind']!='SCHEDULE':continue
        source, key, unique = _saved_schedule_source(db, asset.factory_id, target, source_cache)
        if not key:
            continue
        if links is None:
            links = _purchase_links(db, asset.factory_id)
        result.update(_schedule_purchase_ids(target, source, unique, links.get(key, ())))
    return result


def purchase_order_ids(db,asset,*,schedule_target=None):
    from app.services.carton_asset_supplier_collaboration import purchase_ids
    source_ids=source_purchase_order_ids(db,asset,schedule_target=schedule_target)
    return source_ids if schedule_target is not None else purchase_ids(db,asset,source_ids)


def shared_with_internal(db,user,asset):
    for target in valid(db,asset):
        try:
            if target['kind'] in {'SAMPLE','MISC'}:
                from app.services import carton_special_requests
                carton_special_requests.access(db,user,asset.factory_id,target['id'])
            customer_allowed(db,user,asset.factory_id,target['customer_code']);return True
        except HTTPException:continue
    return False


def shared_with_supplier(db,asset,supplier):
    from app.services import carton_mark_sharing as sharing
    state=sharing.current(db,asset)
    if asset.asset_purpose!='MATERIAL' or state['sharing_mode']=='INTERNAL':return False
    if state['sharing_mode']=='SUPPLIER' and state['shared_supplier_id']==supplier.id:
        from app.services.carton_asset_access import DEPARTMENTS
        # A named, same-factory supplier audience grants source access independently
        # of purchasing. Order projections still require their own explicit links.
        if asset.owner_department in DEPARTMENTS and asset.factory_id == supplier.factory_id:
            return True
        rows=valid(db,asset)
        from app.services import carton_supplier_portal as portal
        from app.models.carton_procurement import CartonOrder
        for identifier in source_purchase_order_ids(db,asset):
            order=db.get(CartonOrder,identifier)
            issue=portal.latest_issue(db,order)
            header=portal._purchase_order_snapshot(issue).get('order',{}) if issue else {}
            if order.supplier_id==supplier.id and header.get('supplier_id')==supplier.id and order.status in portal.OPEN_STATES | {'COMPLETED'} and identity(header)==identity(dict(
                customer_code=order.customer_code,contract_no=order.contract_no,item_no=order.item_no,customer_po=order.customer_po)):
                return True
        return any(x['kind'] in {'SAMPLE','MISC'} and x.get('supplier_id')==supplier.id for x in rows)
    return False


def sync_legacy(db,user,asset):
    """Replace quick provenance after a legacy explicit binding edit as well."""
    if not asset.owner_department:return
    rows=legacy_targets(db,asset,current_authorized=True)
    # Never rebuild an implicit contract-wide match for an owned source.
    assets.audit(db,user,asset,EVENT,dict(revision=asset.revision,targets=rows,sha256=asset.sha256))
    db.flush()
