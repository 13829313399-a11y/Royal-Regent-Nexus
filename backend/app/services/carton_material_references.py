"""Explicit immutable-version adoption. Audit is evidence; one table is a cache.

Targets store pointers, never source bytes/text/approval. The first relation event
pins a source audit sequence so target downloads do not depend on source visibility.
Every writer uses the existing IAM -> factory lock and caller's one transaction.
"""
import copy
import json

from fastapi import HTTPException
from sqlalchemy import delete, func, inspect, select

from app.models.carton_materials import CartonMaterialReference as Reference
from app.models.carton_procurement import CartonAuditEvent
from app.services.carton_materials_resolver import Resolver, customer_for

TABLE = Reference.__tablename__
KIND = 'MATERIAL_REFERENCE_V1'
FIELDS = tuple(column.name for column in Reference.__table__.columns)
IDENTITY = ('factory_id','reference_id','customer_id','version_id','source_context_id','source_order_key',
            'target_context_id','target_order_key','contract_id')


def service():
    from app.services import carton_materials
    return carton_materials


def require_schema(db):
    if db.info.get('carton_material_reference_schema_ready'): return
    inspector=inspect(db.connection())
    if not inspector.has_table(TABLE) or {c['name'] for c in inspector.get_columns(TABLE)}!=set(FIELDS):
        raise HTTPException(503,'资料引用需要先执行 20261030_0186 迁移；未改写资料')
    db.info['carton_material_reference_schema_ready']=True


def event(db,factory,sequence):
    row=db.get(CartonAuditEvent,sequence)
    if not row or row.factory_id!=factory:
        raise HTTPException(409,'引用证据缺失，请核对或重建投影')
    return row,json.loads(row.detail_json)


def frozen(db,row):
    origin,proof=event(db,row.factory_id,row.origin_event_sequence)
    payload=proof.get('state',{})
    if origin.entity_type!=service().REQUESTS or origin.entity_id!=row.reference_id or payload.get('kind')!=KIND:
        raise HTTPException(409,'引用证据归属不符')
    if any(payload.get(key)!=getattr(row,key) for key in IDENTITY):
        raise HTTPException(409,'引用投影与原始证据不一致，请重建投影')
    last,last_data=event(db,row.factory_id,row.last_event_sequence)
    current=last_data.get('state',{})
    if (last.entity_type!=service().REQUESTS or last.entity_id!=row.reference_id or current.get('kind')!=KIND or
        any(current.get(key)!=getattr(row,key) for key in IDENTITY+('active','revision'))):
        raise HTTPException(409,'引用当前态与最新证据不一致，请重建投影')
    version_event,data=event(db,row.factory_id,payload['version_event_sequence'])
    if version_event.entity_type!=service().ENTITY or version_event.entity_id!=row.source_context_id:
        raise HTTPException(409,'来源版本证据归属不符')
    version=next((v for v in data.get('state',{}).get('versions',[]) if v['id']==row.version_id and not v.get('is_reference')),None)
    if not version: raise HTTPException(409,'不可变来源版本证据缺失')
    if not version.get('asset_id') and version.get('sha256')!=service().digest(version.get('text','')):
        raise HTTPException(409,'不可变文字版本完整性校验未通过')
    return copy.deepcopy(version),payload['version_event_sequence']


def lookup(db,factory,target,version,*,active=True):
    require_schema(db)
    query=select(Reference).where(Reference.factory_id==factory,Reference.target_context_id==target,
                                  Reference.version_id==version)
    if active: query=query.where(Reference.active.is_(True))
    return db.scalar(query)


def read_source(db,factory,audience,user,identifier,version_id,*,verify_asset=True):
    entry=Resolver(db,factory,audience,user).resolve(identifier=identifier)
    state=entry['state']
    if not state or state.get('is_archived') or state.get('hidden'):
        raise HTTPException(404,'来源资料不可引用')
    version=next((v for v in state['versions'] if v['id']==version_id),None)
    if not version: raise HTTPException(404,'来源版本不存在')
    adopted=bool(version.get('is_reference'))
    if adopted:
        row=lookup(db,factory,state['id'],version_id)
        if not row or row.reference_id!=version['reference_id']: raise HTTPException(404,'来源引用已解除')
        original,sequence=frozen(db,row)
        origin=dict(context_id=row.source_context_id,order_key=row.source_order_key,version_event_sequence=sequence)
        version=original
    else:
        sequence=db.scalar(select(CartonAuditEvent.sequence).where(CartonAuditEvent.factory_id==factory,
            CartonAuditEvent.entity_type==service().ENTITY,CartonAuditEvent.entity_id==state['id']).order_by(CartonAuditEvent.sequence.desc()).limit(1))
        origin=dict(context_id=state['id'],order_key=order_key(entry),version_event_sequence=sequence)
    if audience=='supplier' and version['role']=='EVIDENCE': raise HTTPException(404,'来源版本不可访问')
    if verify_asset and version.get('asset_id'):
        validate_asset(db,factory,version,allow_archived=adopted)
    return entry,version,origin


def order_key(entry):
    # The authority key remains valid when several typed views describe one
    # logical order. Never invent a PO/physical-order identity from display text.
    return entry['state']['id']


def validate_asset(db,factory,version,*,allow_archived):
    from app.models.carton_mark import CartonMarkAsset
    import hashlib
    asset=db.get(CartonMarkAsset,version.get('asset_id')) if version.get('asset_id') else None
    if (not asset or asset.factory_id!=factory or asset.recognition_source!='materials_folder' or
        (asset.is_archived and not allow_archived) or asset.sha256!=version['sha256'] or
        hashlib.sha256(asset.content).hexdigest()!=version['sha256']):
        raise HTTPException(404,'资料文件不存在或完整性校验未通过')
    return asset


def source_visible(db,factory,audience,user,identifier):
    try:
        state=Resolver(db,factory,audience,user).resolve(identifier=identifier)['state']
        return bool(state and not state.get('is_archived') and not state.get('hidden'))
    except HTTPException: return False


def hydrate(db,factory,audience,user,state):
    """Only selected pointers are projected. Ordinary folders perform no query."""
    pointers=[v for v in state['versions'] if v.get('is_reference')]
    if not pointers: return copy.deepcopy(state)
    require_schema(db)
    rows={row.reference_id:row for row in db.scalars(select(Reference).where(Reference.factory_id==factory,
        Reference.target_context_id==state['id'],Reference.version_id.in_([v['id'] for v in pointers]),Reference.active.is_(True)))}
    result=copy.deepcopy(state); versions=[]
    visibility={}
    for pointer in result['versions']:
        if not pointer.get('is_reference'):
            versions.append(pointer); continue
        row=rows.get(pointer['reference_id'])
        if not row or row.version_id!=pointer['id']:
            continue  # Retain historical approval in audit, never grant a dead reference.
        value,_=frozen(db,row)
        if audience=='supplier' and value['role']=='EVIDENCE': continue
        if row.source_context_id not in visibility:
            visibility[row.source_context_id]=source_visible(db,factory,audience,user,row.source_context_id)
        visible=visibility[row.source_context_id]
        value.update(reference_id=row.reference_id,is_reference=True,reference_active=True,number=pointer['number'],
                     reference_revision=row.revision,asset_id='',source_visible=visible)
        if visible:
            value['source']=dict(context_id=row.source_context_id,order_key=row.source_order_key)
        else:
            for key in ('by','party','at','previous_id'): value.pop(key,None)
        versions.append(value)
    result['versions']=versions
    visible_ids={v['id'] for v in versions}
    result['approved_version_ids']=[v for v in result['approved_version_ids'] if v in visible_ids]
    return result


def target_entries(db,factory,audience,actor,targets,source_id,customer_id):
    if len({target.context_id for target in targets})!=len(targets):
        raise HTTPException(422,'目标订单不可重复；请显式选择每张目标订单')
    values=[]
    for target in targets:
        entry=Resolver(db,factory,audience,actor).resolve(identifier=target.context_id,write=True)
        state=entry['state']
        if not state or state.get('scope_kind')=='UNASSIGNED' or state['id']==source_id:
            raise HTTPException(422,'请选择独立目标订单，不可关联来源自身或合同未分配记录')
        if state.get('hidden') or state.get('is_archived'): raise HTTPException(404,'目标资料不可写')
        if customer_for(db,factory,state).id!=customer_id:
            raise HTTPException(422,'仅可关联同厂同一客户的订单')
        values.append((target,entry))
    return values


def receipt(db,factory,actor,request_id,fingerprint):
    key='CMR-'+service().digest([actor.id,request_id])
    previous=service().events(db,factory,service().REQUESTS,key)
    if not previous: return key,None
    data=json.loads(previous[-1].detail_json)
    if data.get('fingerprint')!=fingerprint: raise HTTPException(409,'此操作编号已用于不同目标、版本或内容')
    return key,data['state']


def write_projection(db,actor,factory,row,payload,action,request_id,fingerprint):
    audit=service().core._audit(db,actor,factory,service().EVENT,service().REQUESTS,row.reference_id,
        dict(state=dict(payload,kind=KIND),action=action,request_id=request_id,fingerprint=fingerprint))
    db.flush()  # Audit sequence exists before cache write, in this same transaction.
    row.last_event_sequence=audit.sequence
    if not row.origin_event_sequence: row.origin_event_sequence=audit.sequence
    db.add(row)
    db.flush()


def persist_target(db,actor,factory,state,action,request_id,fingerprint):
    state['revision']+=1; state['updated_at']=service().now()
    state['timeline'].append(dict(action=action,by=actor.display_name,at=state['updated_at'],note='显式资料引用变更'))
    service().append(db,actor,factory,state['id'],state,action,request_id,fingerprint)
    db.flush()


def link(db,actor,factory,audience,source_entry,version,origin,targets,request_id,fingerprint):
    result=[]
    for target,entry in targets:
        state=entry['state']
        row=lookup(db,factory,state['id'],version['id'],active=False)
        if row and row.active:
            frozen(db,row)  # An idempotent adoption cannot hide a corrupt cache.
            result.append(row.reference_id); continue
        if state['revision']!=target.revision: raise HTTPException(409,'目标资料已更新，请刷新后重新选择')
        if len(state['versions'])>=100 and not row: raise HTTPException(422,'目标资料版本数已达上限')
        if len(state['timeline'])>=1000: raise HTTPException(422,'目标资料历史已达上限')
        if row:
            original,sequence=frozen(db,row)
            if sequence!=origin['version_event_sequence'] and original!=version:
                raise HTTPException(409,'同一版本内容与原始引用不一致')
            row.active=True; row.revision+=1
        else:
            row=Reference(factory_id=factory,reference_id='CMREF-'+service().digest([factory,state['id'],version['id']]),
                customer_id=source_entry['root']['customer_id'],version_id=version['id'],
                source_context_id=origin['context_id'],source_order_key=origin['order_key'],
                target_context_id=state['id'],target_order_key=order_key(entry),contract_id=entry['root']['id'],
                active=True,revision=1,origin_event_sequence=0,last_event_sequence=0)
            sequence=origin['version_event_sequence']
        payload={key:getattr(row,key) for key in IDENTITY+('active','revision')}
        payload['version_event_sequence']=sequence
        write_projection(db,actor,factory,row,payload,'REFERENCE_LINK',request_id,fingerprint)
        pointer=next((v for v in state['versions'] if v['id']==version['id']),None)
        if pointer and not pointer.get('is_reference'): raise HTTPException(409,'目标已有同版本原件，不能改写为引用')
        if not pointer:
            state['versions'].append(dict(id=version['id'],reference_id=row.reference_id,is_reference=True,
                number=len(state['versions'])+1,role=version['role']))
        if version['role']!='EVIDENCE':
            state.update(status='PROCESSING',next_party=('SALES' if state['owners'].get('SALES') else 'WAREHOUSE')
                         if audience=='supplier' else service().PARTY[audience],waiting_since=service().now())
        persist_target(db,actor,factory,state,'REFERENCE_LINK',request_id,fingerprint)
        result.append(row.reference_id)
    return result


def associate(db,user,factory,audience,body,refresh,*,upload_identifier=None,prepared=None):
    s=service(); actor=s.locked(db,user,factory,audience,refresh); require_schema(db)
    source_id=upload_identifier or body.source_context_id
    upload=upload_identifier is not None
    if upload:
        source_entry=Resolver(db,factory,audience,actor).resolve(identifier=source_id,authority_id=body.authority_id,write=True)
        if not source_entry['state']: raise HTTPException(422,'请选择具体来源资料记录')
    else:
        source_entry=Resolver(db,factory,audience,actor).resolve(identifier=source_id)
        if not source_entry['state'] or source_entry['state'].get('hidden') or source_entry['state'].get('is_archived'):
            raise HTTPException(404,'来源资料不可引用')
    customer_id=customer_for(db,factory,source_entry['state']).id
    # All target auth/identity checks precede replay and all mutations.
    targets=target_entries(db,factory,audience,actor,body.targets,source_entry['state']['id'],customer_id)
    fingerprint=s.digest(dict(action='UPLOAD_AND_REFERENCE' if upload else 'REFERENCE',actor=actor.id,audience=audience,
        source=source_id,body=body.model_dump(),file={key:prepared[key] for key in ('sha256','file_name','content_type')} if prepared else None))
    key,previous=receipt(db,factory,actor,body.request_id,fingerprint)
    if not upload:
        source_entry,version,origin=read_source(db,factory,audience,actor,source_id,body.version_id)
    if previous: return previous
    if upload:
        from app.schemas.carton_materials import Version
        if any(json.loads(e.detail_json).get('request_id')==body.request_id for e in s.events(db,factory,identifier=source_entry['state']['id'])):
            raise HTTPException(409,'此操作编号已用于来源单的其他操作，请核对原结果')
        local=Version.model_validate(body.model_dump(exclude={'targets'}))
        state=s.change(db,actor,factory,audience,source_id,local,refresh,prepared,_actor=actor,_commit=False)
        source_entry,version,origin=read_source(db,factory,audience,actor,state['id'],state['versions'][-1]['id'])
    references=link(db,actor,factory,audience,source_entry,version,origin,targets,body.request_id,fingerprint)
    result=dict(source_context_id=source_entry['state']['id'],version_id=version['id'],reference_ids=references,
                target_context_ids=[entry['state']['id'] for _,entry in targets])
    s.append(db,actor,factory,key,result,'REFERENCE_REQUEST',body.request_id,fingerprint,s.REQUESTS)
    db.commit()
    return result


def remove(db,user,factory,audience,identifier,reference_id,body,refresh):
    s=service(); actor=s.locked(db,user,factory,audience,refresh); require_schema(db)
    entry=Resolver(db,factory,audience,actor).resolve(identifier=identifier,write=True)
    state=entry['state']
    row=db.get(Reference,(factory,reference_id))
    if not state or not row or row.target_context_id!=state['id']: raise HTTPException(404,'目标引用不存在')
    original,sequence=frozen(db,row)
    if audience=='supplier' and original['role']=='EVIDENCE': raise HTTPException(404,'客户凭据仅内部可维护')
    fingerprint=s.digest(dict(action='REFERENCE_UNLINK',actor=actor.id,audience=audience,target=identifier,reference=reference_id,body=body.model_dump()))
    key,previous=receipt(db,factory,actor,body.request_id,fingerprint)
    if previous: return previous
    if row.active:
        if state['revision']!=body.revision or row.revision!=body.reference_revision: raise HTTPException(409,'引用或目标已更新，请刷新')
        if len(state['timeline'])>=1000: raise HTTPException(422,'目标资料历史已达上限')
        row.active=False; row.revision+=1
        payload={key:getattr(row,key) for key in IDENTITY+('active','revision')}
        payload['version_event_sequence']=sequence
        write_projection(db,actor,factory,row,payload,'REFERENCE_UNLINK',body.request_id,fingerprint)
        if row.version_id in state['approved_version_ids']:
            state.update(approved_version_ids=[],approval=None,status='PROCESSING',next_party=s.PARTY[audience],waiting_since=s.now())
        persist_target(db,actor,factory,state,'REFERENCE_UNLINK',body.request_id,fingerprint)
    result=dict(reference_id=row.reference_id,active=False,reference_revision=row.revision)
    s.append(db,actor,factory,key,result,'REFERENCE_REQUEST',body.request_id,fingerprint,s.REQUESTS)
    db.commit()
    return result


def document(db,user,factory,audience,state,version_id):
    row=lookup(db,factory,state['id'],version_id)
    if not row: raise HTTPException(404,'引用未生效或已解除')
    version,_=frozen(db,row)
    if audience=='supplier' and version['role']=='EVIDENCE': raise HTTPException(404,'客户凭据仅内部可见')
    return validate_asset(db,factory,version,allow_archived=True)


def reverse(db,user,factory,audience,source_context_id,version_id='',limit=50,offset=0):
    s=service(); s.authorize(db,user,factory,audience); require_schema(db)
    if version_id:
        entry,_,_=read_source(db,factory,audience,user,source_context_id,version_id,verify_asset=False)
    else:
        entry=Resolver(db,factory,audience,user).resolve(identifier=source_context_id)
    if not entry['state']: raise HTTPException(404,'来源资料不存在')
    query=select(Reference).where(Reference.factory_id==factory,Reference.active.is_(True),
        Reference.customer_id==customer_for(db,factory,entry['state']).id)
    query=query.where(Reference.version_id==version_id) if version_id else query.where(Reference.source_context_id==entry['state']['id'])
    query=query.order_by(Reference.target_context_id if version_id else Reference.reference_id).limit(limit).offset(offset)
    rows=list(db.scalars(query)); items=[]; visibility={}
    for row in rows:
        try:
            target=Resolver(db,factory,audience,user).resolve(identifier=row.target_context_id)['state']
            if not target: continue
            version,_=frozen(db,row)
            if audience=='supplier' and version['role']=='EVIDENCE': continue
        except HTTPException: continue
        value=dict(reference_id=row.reference_id,version_id=row.version_id,target_context_id=row.target_context_id,
                   active=row.active,revision=row.revision)
        if row.source_context_id not in visibility:
            visibility[row.source_context_id]=source_visible(db,factory,audience,user,row.source_context_id)
        if visibility[row.source_context_id]:
            value['source_context_id']=row.source_context_id; value['source_order_key']=row.source_order_key
        items.append(value)
    # No unauthorized factory-wide totals; cursor advances over bounded index rows.
    return dict(items=items,next_offset=offset+limit if len(rows)==limit else None)


def rebuild(db,factory,*,apply=False):
    """Offline maintenance only; all rows validated before replacing this factory."""
    require_schema(db)
    if apply:
        from app.services.identity_policy import lock_mutation
        lock_mutation(db); service().core._lock_receipt_factory(db,factory)
    states={}; unique={}; skipped=conflicts=events=0
    query=select(CartonAuditEvent).where(CartonAuditEvent.factory_id==factory,
        CartonAuditEvent.entity_type==service().REQUESTS,CartonAuditEvent.entity_id.like('CMREF-%')).order_by(CartonAuditEvent.sequence)
    for audit in db.scalars(query.execution_options(yield_per=200)):
        events+=1
        try:
            data=json.loads(audit.detail_json)['state']
            if data.get('kind')!=KIND or data['factory_id']!=factory or data['reference_id']!=audit.entity_id: raise ValueError()
            values={key:data[key] for key in IDENTITY+('active','revision')}
            prior=states.get(audit.entity_id)
            if prior and (any(prior[key]!=values[key] for key in IDENTITY) or values['revision']!=prior['revision']+1 or
                          prior['version_event_sequence']!=data['version_event_sequence']):
                conflicts+=1; continue
            if not prior and (values['revision']!=1 or not values['active']): conflicts+=1; continue
            key=(values['target_context_id'],values['version_id'])
            if key in unique and unique[key]!=audit.entity_id: conflicts+=1; continue
            unique[key]=audit.entity_id
            values.update(origin_event_sequence=prior['origin_event_sequence'] if prior else audit.sequence,
                last_event_sequence=audit.sequence,version_event_sequence=data['version_event_sequence'])
            candidate=Reference(**{k:v for k,v in values.items() if k in FIELDS})
            frozen(db,candidate)
            states[audit.entity_id]=values
        except (ValueError,KeyError,TypeError,HTTPException): skipped+=1
    result=dict(factory_id=factory,events=events,rows=len(states),skipped=skipped,conflicts=conflicts,applied=False)
    if apply:
        if skipped or conflicts: raise HTTPException(409,dict(message='引用证据存在跳过或冲突，未替换投影',**result))
        db.execute(delete(Reference).where(Reference.factory_id==factory))
        db.flush()
        for values in states.values(): db.add(Reference(**{k:v for k,v in values.items() if k in FIELDS}))
        db.flush(); result['applied']=True
    return result
