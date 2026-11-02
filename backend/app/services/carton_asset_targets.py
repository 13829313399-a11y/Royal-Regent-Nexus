"""Explicit old-asset targets, including pre-purchase schedule identity snapshots."""
import hashlib,json
from sqlalchemy import select
from fastapi import HTTPException
from app.models.carton_procurement import CartonImportBatch,CartonAuditEvent
from app.services import carton_mark_assets as assets
from app.services.carton_schedule_tracking import effective_po

EVENT='CARTON_ASSET_TARGETS_V1'


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()


def identity(row):
    return [assets.identity(str(row.get(k) or '')) for k in ('customer_code','contract_no','item_no')] + [assets.identity(effective_po(row))]


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
    if not supplier:
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
        row['identity']=identity(row);row['fingerprint']=digest(row);result.append(row)
    # Do not collapse an unproven order/schedule match into a fictitious singleton.
    if contract:result=[x for x in result if assets.identity(x['contract_no'])==assets.identity(contract)]
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
    if not asset.owner_department:return []
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


def valid(db,asset,factory=None):
    factory=factory or asset.factory_id
    from app.models.carton_procurement import CartonOrder
    latest=schedules(db,factory);result=[]
    for target in current(db,asset,factory):
        if target['kind']=='SCHEDULE':
            exact=[x for x in latest if (x['id'],x['sheet'],x['row'],x['identity'])==(target['id'],target['sheet'],target['row'],target['identity'])]
            matches=exact or [x for x in latest if x['identity']==target['identity']]
            if len(matches)==1:result.append(matches[0])
            elif factory==asset.factory_id and purchase_order_ids(db,asset,schedule_target=target):result.append(dict(target,ordered=True))
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


def purchase_order_ids(db,asset,*,schedule_target=None):
    """Follow explicit schedule creation evidence, never a contract-wide guess.

    Read the saved source batch so later schedule removal cannot erase a purchase
    link. Current order identity and factory still have to match that source.
    """
    from app.services import carton_procurement as core
    from app.models.carton_procurement import CartonOrder
    result=set()
    state=core.schedule_order_state(db,asset.factory_id)
    for target in [schedule_target] if schedule_target else current(db,asset):
        if target['kind']=='REGULAR':
            order=db.get(CartonOrder,target['id'])
            if order and order.factory_id==asset.factory_id and not order.deleted_at and order.status!='CANCELLED' and order.supplier_id==target.get('supplier_id') and identity(dict(
                customer_code=order.customer_code,contract_no=order.contract_no,item_no=order.item_no,customer_po=order.customer_po))==target['identity']:result.add(order.id)
            continue
        if target['kind']!='SCHEDULE':continue
        batch=db.get(CartonImportBatch,target['id'])
        if not batch or batch.factory_id!=asset.factory_id or batch.status=='REJECTED':continue
        rows=core.import_batch_out(batch).parse_summary.get('rows',[])
        source=next((r for r in rows if r.get('source_sheet')==target['sheet'] and r.get('source_row')==target['row']),None)
        if not source:continue
        for identifier in state.get(source.get('schedule_identity'),{}).get('order_ids',[]):
            order=db.get(CartonOrder,identifier)
            if order and order.factory_id==asset.factory_id and not order.deleted_at and order.status!='CANCELLED' and identity(dict(
                customer_code=order.customer_code,contract_no=order.contract_no,item_no=order.item_no,customer_po=order.customer_po))==target['identity']:
                result.add(order.id)
    return result


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
        rows=valid(db,asset)
        from app.services import carton_supplier_portal as portal
        from app.models.carton_procurement import CartonOrder
        for identifier in purchase_order_ids(db,asset):
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
