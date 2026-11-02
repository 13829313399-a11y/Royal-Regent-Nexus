"""Order-scoped source collaboration. Append-only facts; no procurement/QC mutations."""
import copy
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select, or_, func

from app.models.carton_procurement import CartonAuditEvent, CartonImportBatch, CartonOrder, CartonSupplier
from app.models.carton_mark import CartonMarkAsset
from app.services import carton_procurement as core, carton_supplier_portal as portal
from app.services.business_authz import ensure_permission_for_departments, has_permission_for_departments
from app.services.carton_customer_assignment import ensure_customer_operation
from app.services.carton_mark_assets import identity

ENTITY = 'carton_material_folder'
DEFAULTS = 'carton_material_default'
REQUESTS = 'carton_material_request'
EVENT = 'CARTON_MATERIAL_CHANGED'
PARTY = {'sales': 'SALES', 'warehouse': 'WAREHOUSE', 'supplier': 'SUPPLIER'}
LABELS = {'SALES': '业务', 'WAREHOUSE': '仓库', 'SUPPLIER': '供应商'}


def writes_enabled():
    # Explicit server-process opt-in; default remains read-only. No local .env
    # or production settings are changed by this module or its capabilities API.
    return os.environ.get('CARTON_MATERIALS_V2_WRITES_ENABLED', '').strip().lower() in {'true', '1'}


def require_writes():
    if not writes_enabled():
        raise HTTPException(403, '订单资料写入尚未启用，当前可继续查看和下载历史资料')


def capabilities(db, user, factory, audience):
    from sqlalchemy import inspect
    authorize(db,user,factory,audience)
    return dict(contract_entry=True, writes_enabled=writes_enabled(), switch='CARTON_MATERIALS_V2_WRITES_ENABLED',
                shared_references=True,reference_projection_ready=inspect(db.connection()).has_table('carton_material_references'),
                batch_approval=True)


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def digest(data):
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def events(db, factory, entity=ENTITY, identifier=None):
    query = select(CartonAuditEvent).where(CartonAuditEvent.factory_id == factory, CartonAuditEvent.entity_type == entity)
    if identifier: query = query.where(CartonAuditEvent.entity_id == identifier)
    return list(db.scalars(query.order_by(CartonAuditEvent.sequence)))


def folders(db, factory):
    # Compatibility callers checking a schedule row must fetch only that key.
    # Explicit iteration remains available to the legacy flat-folder list.
    from app.services.carton_materials_resolver import AuthorityLookup
    return AuthorityLookup(db,factory)


def get(db, factory, identifier):
    """Raw authority snapshot; public entry points use the common resolver."""
    event = db.scalar(select(CartonAuditEvent).where(CartonAuditEvent.factory_id == factory,
        CartonAuditEvent.entity_type == ENTITY, CartonAuditEvent.entity_id == identifier).order_by(CartonAuditEvent.sequence.desc()).limit(1))
    if not event: raise HTTPException(404, '订单资料不存在')
    return json.loads(event.detail_json)['state']


def has_supplier_folders(db, factory, supplier_id):
    from app.services.carton_materials_resolver import state_field
    latest = select(func.max(CartonAuditEvent.sequence)).where(CartonAuditEvent.factory_id==factory,
        CartonAuditEvent.entity_type==ENTITY).group_by(CartonAuditEvent.entity_id)
    return db.scalar(select(CartonAuditEvent.sequence).where(CartonAuditEvent.sequence.in_(latest),
        state_field(db,'supplier_id')==supplier_id).limit(1)) is not None


def authorize(db, user, factory, audience, state=None, *, write=False):
    if write: require_writes()
    core.require_carton_factory(factory)
    if write and state: core.get_active_customer(db, factory, state['customer_code'])
    if audience == 'supplier':
        supplier = portal.supplier_access(db, user, factory, 'carton_supplier:edit' if write else 'carton_supplier:read')
        if state and state.get('supplier_id') != supplier.id: raise HTTPException(404, '未找到本供应商的订单资料')
        return supplier
    if audience == 'sales':
        if write:
            from app.services.customer_order_carton_schedule import authorize_sales
            authorize_sales(db, user, factory)
        else:
            ensure_permission_for_departments(db, user, 'customer_order:read', factory, ('sales-business',))
    else:
        ensure_permission_for_departments(db, user, 'carton_mark:template_upload' if write else 'carton_mark:read',
            factory, ('pmc-warehouse', 'carton'))
        if state: ensure_customer_operation(db, user, factory, state['customer_code'])
    return None


def locked(db, user, factory, audience, refresh, state=None):
    require_writes()
    from app.services.carton_special_requests import locked_actor
    locked_actor(db, user, factory)
    actor = refresh()
    authorize(db, actor, factory, audience, state, write=True)
    return actor


def default(db, factory, customer):
    identifier = 'CMD-' + digest([factory, customer])
    rows = events(db, factory, DEFAULTS, identifier)
    return json.loads(rows[-1].detail_json)['state'] if rows else dict(mode='UNDECIDED', revision=0)


def suppliers(db, factory):
    # The current supplier platform represents Dongkang, not arbitrary accounts.
    return [dict(id=row.id, name=row.supplier_name) for row in db.scalars(select(CartonSupplier).where(
        CartonSupplier.factory_id == factory, CartonSupplier.status == 'ACTIVE', CartonSupplier.supplier_code == 'HEYUAN-DONGKANG'))]


def _resolve_target(db, factory, audience, target, *, allow_ambiguous=False):
    from app.services.carton_schedule_tracking import effective_po
    if target.kind == 'SCHEDULE':
        batch = db.get(CartonImportBatch, target.id)
        if not batch or batch.factory_id != factory or batch.import_type != 'WEEKLY_SCHEDULE' or batch.status == 'REJECTED':
            raise HTTPException(404, '有效排期不存在')
        data = json.loads(batch.parse_summary_json)
        rows = [row for row in data.get('rows', []) if row.get('source_sheet') == target.sheet and row.get('source_row') == target.row]
        if len(rows) != 1: raise HTTPException(422, '排期行身份不明确，请刷新后选择')
        row = rows[0]
        key = lambda value: tuple(identity(str(value.get(k) or '')) for k in ('contract_no', 'item_no')) + (identity(effective_po(value)),)
        if not allow_ambiguous and sum(key(other) == key(row) for other in data.get('rows', [])) != 1:
            raise HTTPException(422, '排期有相同合同、货号和P/O的多行，请先核对拆单归属')
        code = (data.get('schedule_customer') or {}).get('customer_code')
        customer = core.get_active_customer(db, factory, code or '')
        return dict(customer_id=customer.id, customer_code=customer.customer_code, customer_name=customer.customer_name,
            contract_no=str(row.get('contract_no') or ''), item_no=str(row.get('item_no') or ''), po=effective_po(row), supplier_id='')
    if target.kind == 'PURCHASE':
        if audience == 'sales': raise HTTPException(403, '业务请从订单台账或排期选择资料归属')
        matches = list(db.scalars(select(CartonOrder).where(CartonOrder.factory_id == factory,
            or_(CartonOrder.id == target.id, CartonOrder.order_no == target.id), CartonOrder.deleted_at.is_(None))))
        if len(matches) != 1: raise HTTPException(404, '采购单不存在或身份不明确')
        order = matches[0]
        return dict(customer_code=order.customer_code, customer_name=order.customer_name, contract_no=order.contract_no,
            item_no=order.item_no, po=order.customer_po or '', supplier_id=order.supplier_id)
    if audience != 'sales': raise HTTPException(403, '请从仓库排期或采购单选择资料归属')
    from app.models.customer_order_ledger import OrderLedgerLine
    from app.services.customer_order_carton_schedule import resolve_customer
    from app.api.customer_order import CUSTOMER_NAMES
    line = db.get(OrderLedgerLine, target.id)
    if not line or line.factory_id != factory: raise HTTPException(404, '业务订单不存在')
    customer = resolve_customer(db, factory, line.customer_code, CUSTOMER_NAMES.get(line.customer_code, line.customer_code))
    data = line.data or {}
    return dict(customer_id=customer.id, customer_code=customer.customer_code, customer_name=customer.customer_name, contract_no=data.get('contract_no') or line.reference_no,
        item_no=line.product_no, po=data.get('reference_no') or line.reference_no or data.get('po_no') or '', supplier_id='')


def resolve_target(db, factory, audience, target):
    from app.services.carton_materials_resolver import Resolver
    entry = Resolver(db,factory,audience).resolve(target=target)
    if entry['ambiguous']: raise HTTPException(422,'资料归属待核对，请先核对拆单归属')
    data = dict(entry['data'])
    if entry['state']: data['_authority_id'] = entry['state']['id']
    return data


def legacy_folder_id(factory, target):
    return 'CMF-' + digest([factory, *[identity(str(target[key])) for key in ('customer_code', 'contract_no', 'item_no', 'po')]])


def folder_id(factory, target):
    return target.get('_authority_id') or legacy_folder_id(factory,target)


def append(db, actor, factory, identifier, state, action, request_id, fingerprint, entity=ENTITY):
    return core._audit(db, actor, factory, EVENT, entity, identifier,
        dict(state=state, action=action, request_id=request_id, fingerprint=fingerprint))


def replay(db, factory, identifier, request_id, fingerprint):
    for event in events(db, factory, identifier=identifier):
        data = json.loads(event.detail_json)
        if data.get('request_id') == request_id:
            if data.get('fingerprint') != fingerprint: raise HTTPException(409, '此操作编号已用于不同内容，请勿重复提交')
            return True
    return False


def output(state, audience):
    result = copy.deepcopy(state)
    if audience == 'supplier':
        result['versions'] = [v for v in result['versions'] if v['role'] != 'EVIDENCE']
        if result.get('approval'): result['approval']['note'] = ''
        result['timeline'] = [{**event, 'note': '' if event['action'] == 'APPROVE' else event.get('public_note', '')} for event in result['timeline']]
    owner = result['owners'].get(result['next_party'], {})
    result['current_handler'] = (result.get('supplier_name') if result['next_party'] == 'SUPPLIER' else owner.get('name')) or LABELS.get(result['next_party'], '已完成')
    result['status_label'] = ('已确认可使用' if result['status'] == 'READY' else '待客户确认' if result['status'] == 'WAITING_CUSTOMER'
        else '待补充资料' if not result['versions'] else '待' + LABELS.get(result['next_party'], '内部') + '处理')
    if result.get('scope_kind')=='UNASSIGNED': result['status_label']='合同未分配资料 · '+result['status_label']
    return result


def create(db, user, factory, audience, body, refresh):
    from app.services.carton_materials_resolver import Resolver
    if audience == 'supplier': raise HTTPException(403, '资料由业务或仓库建立后交接')
    actor = locked(db, user, factory, audience, refresh)
    request_key = 'CMR-' + digest([actor.id, body.request_id])
    fingerprint = digest(dict(actor=actor.id, audience=audience, body=body.model_dump(exclude_none=True)))
    previous = events(db, factory, REQUESTS, request_key)
    if previous:
        saved = json.loads(previous[-1].detail_json)
        if saved['fingerprint'] != fingerprint: raise HTTPException(409, '此操作编号已用于不同资料归属')
        resolver = Resolver(db,factory,audience,actor)
        current = resolver.resolve(target=body.target,contract=body.contract,write=True)
        owner = current['state']['id'] if current['state'] else current['root']['id']
        if owner != saved['state']['folder_id']:
            raise HTTPException(409, '原订单资料归属已变更，请人工核对')
        resolver.resolve(identifier=owner,write=True)
        return detail(db, actor, factory, audience, saved['state']['folder_id'])
    resolver = Resolver(db,factory,audience,actor)
    entry = resolver.resolve(target=body.target,contract=body.contract,write=True,create=True,actor=actor,request_id=body.request_id)
    identifier = entry['state']['id'] if entry['state'] else entry['root']['id']
    append(db, actor, factory, request_key, dict(folder_id=identifier), 'CREATE', body.request_id, fingerprint, REQUESTS)
    db.commit()
    return detail(db, actor, factory, audience, identifier)


def detail(db, user, factory, audience, identifier):
    from app.services.carton_materials_resolver import Resolver
    resolver = Resolver(db,factory,audience,user)
    return resolver.view(resolver.resolve(identifier=identifier))


def resolve_entry(db,user,factory,audience,identifier,*,authority_id='',write=False):
    from app.services.carton_materials_resolver import Resolver
    return Resolver(db,factory,audience,user).resolve(identifier=identifier,authority_id=authority_id,write=write)


def statuses(db,user,factory,audience,targets):
    from app.services.carton_materials_resolver import Resolver,CONTRACTS,BINDINGS,context_id,target_key
    authorize(db,user,factory,audience)
    resolver=Resolver(db,factory,audience,user)
    facts=[]; roots=[]; owners=[]; keys=[]
    for target in targets:
        try:
            data,customer,root=resolver.facts(target=target)
            facts.append(data); roots.append(root)
            owners.extend([legacy_folder_id(factory,data),context_id(root,data)])
            keys.append(target_key(factory,target))
        except HTTPException:
            facts.append(None)
    resolver.prefetch(CONTRACTS,roots)
    resolver.prefetch(BINDINGS,keys)
    resolver.prefetch(ENTITY,owners)
    # Explicit aliases can point to an original CMF with non-current metadata.
    resolver.prefetch(ENTITY,[v['authority_id'] for (kind,_),v in list(resolver.cache.items()) if kind==BINDINGS and v and v.get('authority_id')])
    items=[]
    for target,data in zip(targets,facts):
        item=dict(target=target.model_dump(),folder_id='',contract_folder_id='',label='资料归属待核对',ready=False,handler='')
        try:
            if data is None: raise HTTPException(422,'资料归属待核对')
            entry=resolver.resolve(target=target,data=data)
            if entry['ambiguous']: raise HTTPException(422,'资料归属待核对')
            state=entry['state']; value=output(state,audience) if state else None
            item.update(contract_folder_id=entry['root']['id'],folder_id=state['id'] if state else '',
                label=value['status_label'] if value else '暂无订单资料',ready=bool(state and state['status']=='READY'),
                handler=value['current_handler'] if value else '')
        except HTTPException: pass
        items.append(item)
    return dict(items=items)


def contract_detail(db,user,factory,audience,identifier):
    from app.services.carton_materials_resolver import Resolver,CONTRACTS
    resolver=Resolver(db,factory,audience,user)
    entry=resolver.resolve(identifier=identifier,contract_summary=True)
    root=resolver.read(CONTRACTS,entry['root']['id']) or entry['root']
    if not root: raise HTTPException(404,'合同规范入口尚未登记，请从原资料夹查看历史')
    return resolver.contract_view(root)


def contract_listing(db,user,factory,audience,q='',limit=50,offset=0):
    from app.services.carton_materials_resolver import Resolver,CONTRACTS,legacy_rows,customer_for,contract_id
    import json
    authorize(db,user,factory,audience)
    sequences=select(func.max(CartonAuditEvent.sequence)).where(CartonAuditEvent.factory_id==factory,
        CartonAuditEvent.entity_type==CONTRACTS,CartonAuditEvent.entity_id.like('CMF2-%')).group_by(CartonAuditEvent.entity_id)
    roots={row.entity_id:json.loads(row.detail_json)['state'] for row in db.scalars(
        select(CartonAuditEvent).where(CartonAuditEvent.sequence.in_(sequences)))}
    # Unregistered legacy contracts remain discoverable without a read-side write.
    for row in legacy_rows(db,factory):
        try:
            customer=customer_for(db,factory,row); identifier=contract_id(factory,customer.id,row['contract_no'])
        except HTTPException: continue
        if identifier not in roots:
            roots[identifier]=dict(id=identifier,factory_id=factory,customer_id=customer.id,
                customer_code=customer.customer_code,customer_name=customer.customer_name,contract_no=row['contract_no'],
                revision=0,kind='LEGACY_MAP',authority_ids=[])
        if roots[identifier]['revision']==0: roots[identifier]['authority_ids'].append(row['id'])
    resolver=Resolver(db,factory,audience,user); result=[]
    for root in roots.values():
        if q.casefold() not in (' '.join([root['customer_name'],root['contract_no']])).casefold(): continue
        try:
            if audience=='supplier':
                visible=resolver.contract_view(root)
                count=visible['authority_count']
            else:
                authorize(db,user,factory,audience,root)
                count=len(root['authority_ids'])
        except HTTPException: continue
        result.append({key:root[key] for key in ('id','factory_id','customer_id','customer_code','customer_name','contract_no','kind','revision')}
                      | dict(contract_folder_id=root['id'],authority_count=count,registered=bool(root['revision'])))
    result.sort(key=lambda row:(row['contract_no'],row['id']))
    return dict(items=result[offset:offset+limit],total=len(result))


def map_legacy(db,user,factory,audience,identifier,body,refresh):
    from app.services.carton_materials_resolver import Resolver,signature
    if audience=='supplier': raise HTTPException(403,'旧夹归属由业务或仓库核对')
    actor=locked(db,user,factory,audience,refresh)
    resolver=Resolver(db,factory,audience,actor)
    data,customer,root_id=resolver.facts(target=body.target)
    authorize(db,actor,factory,audience,data,write=True)
    entry=resolver.resolve(identifier=body.folder_id)
    state=entry['state']
    if not state or not state['id'].startswith('CMF-') or root_id!=identifier or entry['root']['id']!=identifier:
        raise HTTPException(422,'请选择本合同下的原旧资料夹')
    authorize(db,actor,factory,audience,state,write=True)
    if signature(state)!=signature(data): raise HTTPException(422,'旧夹与订单合同、货号或P/O不符，不能猜测归属')
    current=resolver.resolve(target=body.target,data=data)
    if current['state'] and current['state']['id']!=state['id']:
        raise HTTPException(409,'本订单已有其他权威资料记录，不能另建并行映射')
    fingerprint=digest(dict(action='MAP_LEGACY',actor=actor.id,contract=identifier,body=body.model_dump()))
    request_key='CMR-'+digest([actor.id,body.request_id])
    previous=events(db,factory,REQUESTS,request_key)
    if previous:
        if json.loads(previous[-1].detail_json)['fingerprint']!=fingerprint:
            raise HTTPException(409,'此操作编号已用于不同内容')
        return contract_detail(db,actor,factory,audience,identifier)
    if state['revision']!=body.revision: raise HTTPException(409,'旧资料已更新，请刷新后重新核对归属')
    entry=resolver.resolve(identifier=body.folder_id,write=True,actor=actor,request_id=body.request_id,permit_ambiguity=True)
    resolver.bind(entry['root'],state,body.target,data,actor,body.request_id,manual=True)
    append(db,actor,factory,request_key,dict(folder_id=state['id'],contract_folder_id=identifier),
           'MAP_LEGACY',body.request_id,fingerprint,REQUESTS)
    db.commit()
    return contract_detail(db,actor,factory,audience,identifier)


def approval_plan(db,actor,factory,audience,state,revision,version_ids,note,*,references_only=False,
                  replaying=False,allow_stale_duplicate=False):
    """Read/validate only. Both single and batch approval use this contract."""
    from app.services.carton_material_references import hydrate
    if audience=='supplier': raise HTTPException(403,'供应商不能确认资料可用')
    if state['mode']=='UNDECIDED': raise HTTPException(422,'请先明确内部确认或需要客户确认')
    if state['mode']=='CUSTOMER' and audience!='sales': raise HTTPException(403,'客户确认结果由业务登记')
    if not note.strip(): raise HTTPException(422,'请填写确认依据，客户回复截图可作为资料附件保存')
    selected=set(version_ids)
    eligible={v['id'] for v in hydrate(db,factory,audience,actor,state)['versions']
              if v['role']!='EVIDENCE' and (not references_only or v.get('is_reference'))}
    if not selected or len(selected)!=len(version_ids) or not selected<=eligible:
        raise HTTPException(422,'请选择本目标当前有效引用中的制作版本，客户凭据不可确认' if references_only
                            else '请选择本单具体的可用文件或文字版本，客户回复凭据不能作为制作稿')
    approval=state.get('approval')
    duplicate=bool(approval and approval.get('mode')==state['mode'] and set(state['approved_version_ids'])==selected)
    if state['revision']!=revision and not replaying and not (
        allow_stale_duplicate and duplicate and revision<=state['revision']):
        raise HTTPException(409,'资料已更新，请刷新后再处理；本次未保存')
    if len(state['timeline'])>=1000 and not (duplicate and allow_stale_duplicate) and not replaying:
        raise HTTPException(422,'本单资料记录过多，请联系管理员核对')
    return dict(version_ids=list(version_ids),note=note.strip(),duplicate=duplicate)


def apply_approval(db,actor,factory,audience,state,plan,request_id,fingerprint,*,batch_receipt_id=''):
    """Append one order's approval. Never locks or commits; caller owns transaction."""
    old_party,old_status=state['next_party'],state['status']
    stamp=now()
    state.update(status='READY',next_party='SUPPLIER' if state['supplier_id'] else PARTY[audience],
        approved_version_ids=plan['version_ids'],approval=dict(by=actor.display_name,at=stamp,mode=state['mode'],note=plan['note']))
    state['revision']+=1; state['updated_at']=stamp
    if old_party!=state['next_party'] or old_status!=state['status']: state['waiting_since']=stamp
    state['timeline'].append(dict(action='APPROVE',by=actor.display_name,at=stamp,note=plan['note'],public_note=''))
    audit=append(db,actor,factory,state['id'],state,'APPROVE',request_id,fingerprint)
    if batch_receipt_id:
        evidence=json.loads(audit.detail_json)
        evidence['batch_receipt_id']=batch_receipt_id
        audit.detail_json=json.dumps(evidence,ensure_ascii=False,sort_keys=True)
    db.flush()
    return audit


def change(db, user, factory, audience, identifier, body, refresh, prepared=None, *, _actor=None, _commit=True):
    from app.services.carton_materials_resolver import Resolver
    from app.services.carton_material_references import hydrate
    actor = _actor if _actor is not None else locked(db, user, factory, audience, refresh)
    entry = Resolver(db,factory,audience,actor).resolve(identifier=identifier,authority_id=body.authority_id,
        write=True,actor=actor,request_id=body.request_id)
    state = entry['state']
    if not state: raise HTTPException(422,'请选择合同下具体订单资料后处理，不能确认合同汇总')
    identifier = state['id']
    fingerprint = digest(dict(actor=actor.id, body=body.model_dump(exclude={'authority_id'}), file={key: prepared[key]
        for key in ('sha256', 'file_name', 'content_type')} if prepared else None))
    if replay(db, factory, identifier, body.request_id, fingerprint):
        return detail(db, actor, factory, audience, identifier) if _commit else state
    if state['revision'] != body.revision: raise HTTPException(409, '资料已更新，请刷新后再处理；本次未保存')
    old_party, old_status = state['next_party'], state['status']
    action = 'ADD_VERSION' if hasattr(body, 'role') else body.action
    if len(state['timeline']) >= 1000: raise HTTPException(422, '本单资料记录过多，请联系管理员核对')
    if audience == 'supplier' and action not in {'ADD_VERSION', 'COMMENT', 'HANDOFF', 'CLAIM'}:
        raise HTTPException(403, '供应商可回稿、补充说明或交回内部，不能修改确认要求或确认可用')
    if action == 'ADD_VERSION':
        if not body.text.strip() and not prepared: raise HTTPException(422, '请上传文件或填写文字说明')
        if len(state['versions']) >= 100: raise HTTPException(422, '每单最多保留100份资料，请联系管理员核对')
        if audience == 'supplier' and body.role == 'EVIDENCE': raise HTTPException(403, '客户回复凭据由内部经办人登记')
        if body.previous_id and not any(v['id'] == body.previous_id and (audience != 'supplier' or v['role'] != 'EVIDENCE') for v in hydrate(db,factory,audience,actor,state)['versions']): raise HTTPException(422, '修改来源不属于本单可见资料')
        asset_id = ''
        if prepared:
            asset_id = 'CMA-' + uuid4().hex
            db.add(CartonMarkAsset(id=asset_id, factory_id=factory, file_name=prepared['file_name'], kind=prepared['kind'],
                content=prepared['content'], content_type=prepared['content_type'], size_bytes=len(prepared['content']),
                sha256=prepared['sha256'], contract_number='', recognition_source='materials_folder',
                candidates_json=json.dumps([identifier]), warning='', revision=1, is_archived=False,
                created_by=actor.id, created_by_name=actor.display_name, created_at=now(), updated_at=now()))
        version = dict(id='CMV-' + uuid4().hex, number=len(state['versions']) + 1, title=body.title.strip() or (prepared['file_name'] if prepared else '文字说明'),
            text=body.text.strip(), role=body.role, previous_id=body.previous_id, asset_id=asset_id,
            sha256=prepared['sha256'] if prepared else digest(body.text.strip()), file_name=prepared['file_name'] if prepared else '',
            by=actor.display_name, party=PARTY[audience], at=now())
        state['versions'].append(version)
        if body.role != 'EVIDENCE':
            state.update(status='PROCESSING', next_party=('SALES' if state['owners'].get('SALES') else 'WAREHOUSE') if audience == 'supplier' else PARTY[audience])
    elif action == 'RULE':
        if state['mode'] != body.mode: state.update(approved_version_ids=[], approval=None, status='PROCESSING')
        state['mode'] = body.mode
        chosen = next((s for s in suppliers(db, factory) if s['id'] == body.supplier_id), None) if body.supplier_id else None
        if body.supplier_id and not chosen: raise HTTPException(422, '请选择本厂供应商平台支持的有效供应商')
        if state.get('supplier_id') != body.supplier_id:
            state.update(approved_version_ids=[], approval=None, status='PROCESSING')
            if state['next_party'] == 'SUPPLIER': state['next_party'] = PARTY[audience]
        state.update(supplier_id=body.supplier_id, supplier_name=chosen['name'] if chosen else '')
        if body.save_customer_default:
            previous = default(db, factory, state['customer_code'])
            if previous['revision'] != body.default_revision: raise HTTPException(409, '客户默认要求已更新，请刷新后重试')
            append(db, actor, factory, 'CMD-' + digest([factory, state['customer_code']]),
                dict(mode=body.mode, revision=previous['revision'] + 1), action, body.request_id, fingerprint, DEFAULTS)
    elif action in {'HANDOFF', 'REQUEST_CHANGES'}:
        if body.next_party == 'SUPPLIER' and not state.get('supplier_id'): raise HTTPException(422, '请先选择供应商')
        if audience == 'supplier' and body.next_party == 'SUPPLIER': raise HTTPException(422, '请选择业务或仓库接回资料')
        if action == 'REQUEST_CHANGES' and not body.note.strip(): raise HTTPException(422, '请填写需修改或补充的内容')
        state['next_party'] = body.next_party
        if action == 'REQUEST_CHANGES': state.update(approved_version_ids=[], approval=None, status='PROCESSING')
        elif state['status'] != 'READY': state['status'] = 'PROCESSING'
        if body.next_party == 'SALES' and state['mode'] == 'CUSTOMER' and state['status'] != 'READY': state['status'] = 'WAITING_CUSTOMER'
    elif action == 'CLAIM':
        if state['next_party'] != PARTY[audience]: raise HTTPException(403, '当前环节不属于本岗位')
        state['owners'][PARTY[audience]] = dict(id=actor.id, name=actor.display_name)
    elif action == 'APPROVE':
        plan=approval_plan(db,actor,factory,audience,state,body.revision,body.version_ids,body.note)
        apply_approval(db,actor,factory,audience,state,plan,body.request_id,fingerprint)
        if not _commit: return state
        db.commit()
        return detail(db,actor,factory,audience,identifier)
    elif action == 'COMMENT' and not body.note.strip(): raise HTTPException(422, '请填写说明')
    state['revision'] += 1
    state['updated_at'] = now()
    if old_party != state['next_party'] or old_status != state['status'] or action == 'REQUEST_CHANGES': state['waiting_since'] = state['updated_at']
    note = body.text.strip() if action == 'ADD_VERSION' else body.note.strip()
    state['timeline'].append(dict(action=action, by=actor.display_name, at=state['updated_at'], note=note,
        public_note='' if action == 'APPROVE' or action == 'ADD_VERSION' else note))
    append(db, actor, factory, identifier, state, action, body.request_id, fingerprint)
    if not _commit:
        db.flush()
        return state
    db.commit()
    return detail(db, actor, factory, audience, identifier)


def prepare_file(file_name, content):
    # Runs in the existing isolated worker; never writes business data.
    from app.services.carton_mark_assets import recognize_asset, IMAGE_CONTENT_TYPES
    from app.services.carton_mark_library import _excel_content_type
    recognition = recognize_asset(file_name, content, [])
    kind, name = recognition['kind'], recognition['file_name']
    content_type = IMAGE_CONTENT_TYPES[Path(name).suffix.lower()] if kind == 'image' else 'application/pdf' if kind == 'pdf' else _excel_content_type(name)
    return dict(file_name=name, kind=kind, content_type=content_type, content=content, sha256=hashlib.sha256(content).hexdigest())


def document(db, user, factory, audience, identifier, version_id):
    from app.services.carton_materials_resolver import Resolver
    state = Resolver(db,factory,audience,user).resolve(identifier=identifier)['state']
    if not state: raise HTTPException(404,'请通过原权威记录下载具体资料')
    pointer=next((v for v in state['versions'] if v['id']==version_id and v.get('is_reference')),None)
    if pointer:
        from app.services.carton_material_references import document as reference_document
        return reference_document(db,user,factory,audience,state,version_id)
    version = next((v for v in state['versions'] if v['id'] == version_id and (audience != 'supplier' or v['role'] != 'EVIDENCE')), None)
    asset = db.get(CartonMarkAsset, version['asset_id']) if version and version['asset_id'] else None
    if not asset or asset.factory_id != factory or asset.is_archived or asset.sha256 != version['sha256'] or hashlib.sha256(asset.content).hexdigest() != version['sha256']:
        raise HTTPException(404, '资料文件不存在或不可访问')
    return asset


def list_folders(db, user, factory, audience, q='', todo=False):
    supplier = authorize(db, user, factory, audience)
    result = []
    for state in folders(db, factory).values():
        if state.get('scope_kind')=='UNASSIGNED' and not state['versions']: continue
        if audience == 'supplier':
            if state.get('supplier_id') != supplier.id: continue
        else:
            try: authorize(db, user, factory, audience, state)
            except HTTPException: continue
        if todo and (state['next_party'] != PARTY[audience] or state['status'] == 'READY'): continue
        if q.casefold() not in ' '.join(str(state.get(k, '')) for k in ('customer_name', 'contract_no', 'item_no', 'po')).casefold(): continue
        from app.services.carton_material_references import hydrate
        item = output(hydrate(db,factory,audience,user,state), audience)
        item['version_count'] = len(item.pop('versions'))
        item.pop('timeline'); item.pop('approval')
        result.append(item)
    return dict(items=sorted(result, key=lambda r: r['updated_at'], reverse=True), total=len(result))


def candidates(db, user, factory, audience, q=''):
    authorize(db, user, factory, audience)
    if audience == 'supplier': return dict(items=[])
    from app.schemas.carton_materials import Target
    targets = []
    from app.services.carton_schedule_coverage import batches
    seen = set()
    for entry in batches(db, factory):
        batch, summary = entry['batch'], entry['summary']
        code = (summary.get('schedule_customer') or {}).get('customer_code')
        if not code or code in seen or batch.status == 'REJECTED': continue
        seen.add(code)
        for row in summary.get('rows', []):
            if row.get('contract_no') and row.get('source_sheet'):
                targets.append(Target(kind='SCHEDULE', id=batch.id, sheet=row['source_sheet'], row=row['source_row']))
    if audience == 'sales':
        from app.models.customer_order_ledger import OrderLedgerLine
        targets += [Target(kind='LEDGER', id=row.id) for row in db.scalars(select(OrderLedgerLine).where(OrderLedgerLine.factory_id == factory,
            OrderLedgerLine.status == 'active').limit(1000))]
    else:
        targets += [Target(kind='PURCHASE', id=row.id) for row in db.scalars(select(CartonOrder).where(CartonOrder.factory_id == factory,
            CartonOrder.deleted_at.is_(None)).limit(1000))]
    result = []
    for target in targets:
        try:
            data = resolve_target(db, factory, audience, target)
            authorize(db, user, factory, audience, data)
            identifier = folder_id(factory, data)
        except HTTPException: continue
        if q.casefold() in ' '.join(str(v) for v in data.values()).casefold():
            result.append(dict(target=target.model_dump(), **data, folder_id=identifier))
    unique = {item['folder_id']: item for item in reversed(result)}
    return dict(items=list(unique.values())[:100], total=len(unique))
