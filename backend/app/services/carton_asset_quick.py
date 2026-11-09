"""v1a backend foundation; all content remains in CartonMarkAsset."""
import hashlib,json
from pathlib import Path
from uuid import uuid4
from sqlalchemy import select,or_
from fastapi import HTTPException
from app.models.carton_mark import CartonMarkAsset
from app.services import carton_asset_access as access,carton_asset_targets as targets
from app.services import carton_mark_assets as assets,carton_mark_asset_workflow as lifecycle
from app.services import carton_mark_associations as requests,carton_mark_sharing as sharing
from app.schemas.carton_mark import CartonMarkAssetUploadOptions,CartonMarkAssetClassification
from app.services import carton_asset_supplier_collaboration as collaboration


def locked(db,user,factory,extra_factories=()):
    from app.services.carton_special_requests import locked_actor
    from app.services.carton_procurement import require_carton_factory
    db.expire_all()
    if extra_factories:
        from app.services.identity_policy import lock_mutation
        from app.services.carton_procurement import _lock_receipt_factory
        from app.models.auth import AuthUser
        from app.services.auth import build_auth_context
        lock_mutation(db)
        for identifier in sorted({factory,*extra_factories}):
            _lock_receipt_factory(db,require_carton_factory(identifier))
        actor=db.get(AuthUser,user.id)
        if actor is None or actor.status!='active':raise HTTPException(403,'账号已停用')
        return build_auth_context(db,actor)
    return locked_actor(db,user,require_carton_factory(factory))


def prepare(body,name=None,content=None):
    if content is not None:
        if body.text:raise HTTPException(422,'文件和纯文字请选择一种保存')
        if not content or len(content)>20*1024*1024:raise HTTPException(422,'文件须为1字节至20MB')
        result=assets.recognize_asset(name or '',content,[])
        return result,content
    if not body.text.strip():raise HTTPException(422,'请上传文件或填写文字')
    content=body.text.encode('utf-8')
    title=Path((body.title or '文字资料').replace('\\','/')).name
    result=dict(file_name=title.removesuffix('.txt')+'.txt',kind='text',contract_number='',recognition_source='text',candidates=[],warning='')
    # Recognition uses explicit labels only, never an HTML parser or external AI.
    import re
    found=re.findall(r'(?:合同(?:编号|号)?|CONTRACT\s*(?:NO\.?|NUMBER|#)?)\s*[:：#]?\s*([A-Za-z0-9][A-Za-z0-9._/-]{3,127})',body.text,re.I)
    values={assets.identity(x):x for x in found}
    result['candidates']=sorted(values.values())
    if len(values)==1:result['contract_number']=next(iter(values.values()))
    if len(values)>1:result['warning']='识别到多个合同号，请手工选择目标'
    return result,content


def supplier_for(db,user,factory,department,*,write=False):
    if department!='supplier':return None
    from app.services.carton_supplier_portal import supplier_access
    return supplier_access(db,user,factory,'carton_supplier:edit' if write else 'carton_supplier:read')


def receiver(db,asset,rows):
    if asset.asset_purpose=='EVIDENCE':return ''
    ids={x.get('supplier_id','') for x in rows if x.get('supplier_id')}
    if not ids:
        # Pre-purchase schedule has no supplier ID. Infer only one active Dongkang.
        from app.services.carton_procurement_imports import _dongkang_identity
        from app.models.carton_procurement import CartonSupplier
        choices=list(db.scalars(select(CartonSupplier).where(CartonSupplier.factory_id==asset.factory_id,
            CartonSupplier.supplier_code=='HEYUAN-DONGKANG',CartonSupplier.status=='ACTIVE')))
        if len(choices)==1:ids={choices[0].id}
    if len(ids)==1:
        from app.models.carton_procurement import CartonSupplier
        supplier=db.get(CartonSupplier,next(iter(ids)))
        if supplier and supplier.factory_id==asset.factory_id and supplier.status=='ACTIVE' and supplier.supplier_code=='HEYUAN-DONGKANG':return supplier.id
    return ''


def save(db,user,factory,body,prepared,refresh_actor=None):
    try:
        access.writes();user=locked(db,user,factory)
        if refresh_actor:user=refresh_actor()
        department,supplier_id=access.owner(db,user,factory,body.owner_department,supplier=body.owner_department=='supplier')
        if department=='supplier' and body.sharing_mode is not None:
            raise HTTPException(422,'供应商资料请使用共享厂区设置')
        if body.purpose=='EVIDENCE' and body.sharing_mode=='SUPPLIER':
            raise HTTPException(403,'客户凭据禁止共享给供应商')
        supplier=supplier_for(db,user,factory,department)
        if supplier and body.purpose=='EVIDENCE':raise HTTPException(403,'客户凭据只允许内部上传')
        recognition,content=prepared
        sha=hashlib.sha256(content).hexdigest()
        # Omitted audience keeps the pre-upgrade request digest for uncertain retries.
        body_data=body.model_dump(exclude={'sharing_mode'} if body.sharing_mode is None else set())
        rid,saved=requests.request_event(db,user,factory,body.request_id,'QUICK_UPLOAD',dict(body=body_data,sha256=sha,name=recognition['file_name']))
        if saved and 'result' in saved:
            asset=assets.active_asset(db,factory,saved['result']['asset_id'])
            access.ensure(db,user,asset,write=True,supplier=supplier)
            db.rollback();return output(db,user,asset,supplier=supplier)
        parent=assets.active_asset(db,factory,body.previous_asset_id) if body.previous_asset_id else None
        if parent:
            access.ensure(db,user,parent,write=True,supplier=supplier)
            if parent.owner_department!=department or parent.owner_supplier_id!=supplier_id or parent.asset_purpose!=body.purpose:
                raise HTTPException(422,'修改稿必须保留原部门、供应商归属和用途')
        contract=recognition['contract_number'] if body.contract_number is None else body.contract_number.strip()
        if body.association=='MANUAL':
            selected=body.targets or ([body.target] if body.target else [])
            if not selected:raise HTTPException(422,'请选择关联订单')
            if body.targets and body.target:raise HTTPException(422,'不能同时提交两组关联目标')
            rows=resolve_many(db,user,factory,selected,supplier,scope=body.target_scope)
        elif body.target is not None or body.targets:raise HTTPException(422,'自动匹配或不关联时不可暗带目标')
        elif parent:rows=targets.valid(db,parent)
        else:
            candidates=targets.candidates(db,user,factory,contract,supplier=supplier,scope=body.target_scope) if contract and body.association=='AUTO' else []
            # Multiple items of one exact customer/contract are legitimate links.
            keys=[(x['kind'],tuple(x['identity'])) for x in candidates]
            rows=candidates if len({x['customer_code'] for x in candidates})==1 and len(keys)==len(set(keys)) else []
        if body.status=='READY' and body.purpose!='MATERIAL':
            raise HTTPException(403,'内部凭据不是制作资料')
        if body.status=='READY' and not supplier and not access.can_confirm(user,factory,department):
            raise HTTPException(403,'没有资料状态确认权限')
        if parent and body.status=='READY':raise HTTPException(422,'新稿必须重新待确认')
        stamp=assets._now_text()
        asset=CartonMarkAsset(id='CMA-'+uuid4().hex,factory_id=factory,owner_department=department,
            owner_supplier_id=supplier_id,asset_purpose=body.purpose,file_name=recognition['file_name'],kind=recognition['kind'],
            content_type='text/plain' if recognition['kind']=='text' else assets.IMAGE_CONTENT_TYPES[Path(recognition['file_name']).suffix.lower()]
                if recognition['kind']=='image' else 'application/pdf' if recognition['kind']=='pdf' else assets._excel_content_type(recognition['file_name']),
            content=content,size_bytes=len(content),sha256=sha,contract_number=contract,recognition_source='manual_orders',
            candidates_json=json.dumps(recognition['candidates']),warning=recognition['warning'],revision=1,is_archived=False,
            created_by=user.id,created_by_name=user.display_name,created_at=stamp,updated_at=stamp)
        db.add(asset)
        lifecycle.initialize(db,user,asset,CartonMarkAssetUploadOptions(status=body.status,previous_asset_id=body.previous_asset_id,previous_revision=body.previous_revision))
        targets.record(db,user,asset,rows)
        from app.services.carton_asset_visibility import record as record_visibility
        record_visibility(db,user,asset,body.shared_factory_ids)
        recipient=receiver(db,asset,rows)
        if body.sharing_mode=='SUPPLIER' and not recipient:
            raise HTTPException(422,'当前厂区未配置唯一有效的对应供应商，请核对或选择仅内部可见')
        mode=body.sharing_mode or ('SUPPLIER' if recipient else 'INTERNAL')
        if parent and body.sharing_mode is None:
            previous=sharing.current(db,parent)
            if previous['sharing_mode'] in {'SUPPLIER','INTERNAL'}:
                mode=previous['sharing_mode'];recipient=previous['shared_supplier_id']
        sharing.record(db,user,asset,mode,recipient if mode=='SUPPLIER' else '')
        assets.audit(db,user,asset,'CARTON_MARK_ASSET_CREATED',dict(sha256=sha,owner_department=department,owner_supplier_id=supplier_id,purpose=body.purpose))
        requests.record_request(db,user,asset,rid,saved,dict(asset_id=asset.id))
        result=output(db,user,asset,supplier=supplier)
        db.commit();return result
    except BaseException:db.rollback();raise


def audience_editable(asset):
    return collaboration.internal(asset) or (asset.owner_department is None and asset.asset_purpose == 'MATERIAL')


def output(db,user,asset,*,supplier=None,view_factory=None,schedule_rows_by_factory=None,supplier_candidates=None):
    if supplier is None and view_factory in (None,asset.factory_id):supplier=access.external_actor(db,user,asset)
    access.ensure(db,user,asset,supplier=supplier,view_factory=view_factory)
    state=lifecycle.current(db,asset)
    audience=sharing.current(db,asset)
    from app.services.carton_asset_visibility import factories
    can_manage=access.visible(db,user,asset,write=True,supplier=supplier,view_factory=view_factory,collaborate=True,collaboration_action='associate')
    can_share=bool(supplier) and access.visible(db,user,asset,write=True,supplier=supplier,view_factory=view_factory,collaboration_action='share')
    can_classify=access.visible(db,user,asset,write=True,supplier=supplier,view_factory=view_factory,collaborate=True,classification=True)
    can_confirm=access.visible(db,user,asset,write=True,confirm=True,supplier=supplier,view_factory=view_factory,collaborate=True,classification=True)
    statuses=(['DRAFT','PENDING','HISTORY'] if can_classify else []) + (['READY'] if can_confirm and asset.asset_purpose=='MATERIAL' else [])
    if state.superseded_by_asset_id:statuses=[]
    visible_targets=targets.valid(db,asset,view_factory,schedule_rows_by_factory=schedule_rows_by_factory)
    if view_factory in (None,asset.factory_id):visible_targets=collaboration.display_targets(db,asset,visible_targets)
    if supplier:
        purchase_ids=targets.purchase_order_ids(db,asset)
        special_ids={(x['kind'],x['id']) for x in visible_targets if x.get('supplier_id')==supplier.id}
        candidates=targets.candidates(db,user,asset.factory_id,supplier=supplier) if supplier_candidates is None else supplier_candidates
        visible_targets=[x for x in candidates
            if x['kind']=='REGULAR' and x['id'] in purchase_ids or (x['kind'],x['id']) in special_ids]
    blocker=association_blocker(db,asset,supplier)
    original_manage=access.visible(db,user,asset,write=True,supplier=supplier,view_factory=view_factory)
    return dict(id=asset.id,factory_id=asset.factory_id,owner_department=asset.owner_department,
        legacy_source=not bool(asset.owner_department),association_blocker=blocker,
        can_manage_original=original_manage,photo_group_id=asset.photo_group_id,
        sharing_mode=audience['sharing_mode'],shared_supplier_name=audience['shared_supplier_name'],
        can_change_audience=bool(not supplier and audience_editable(asset) and view_factory in (None,asset.factory_id)
            and original_manage),
        view_factory_id=view_factory or asset.factory_id,shared_factory_ids=factories(db,asset),
        can_classify=bool(statuses),allowed_statuses=statuses,can_associate=can_manage and not blocker,can_share=can_share,
        required_shared_factory_ids=[asset.factory_id] if collaboration.internal(asset) else [],
        created_by_name=asset.created_by_name,created_at=asset.created_at,
        owner_supplier_id=asset.owner_supplier_id,purpose=asset.asset_purpose,kind=asset.kind,file_name=asset.file_name,
        content_type=asset.content_type,sha256=asset.sha256,revision=asset.revision,contract_number=asset.contract_number,
        text=asset.content.decode('utf-8') if asset.kind=='text' else None,workflow=state.model_dump(),
        targets=[{k:v for k,v in row.items() if k not in {'customer_code','identity','revision','supplier_id'}}
            if supplier else row for row in visible_targets],uploaded=True,warning=asset.warning)


def association_blocker(db,asset,supplier=None):
    state=lifecycle.current(db,asset)
    if state.status=='HISTORY' or state.superseded_by_asset_id:
        return '历史版本保留原关联，不能修改；请打开当前版本。'
    if asset.photo_group_id:
        return '照片组须整体维护关联，请打开资料详情。'
    if not asset.owner_department:
        return '旧资料保留原匹配方式，请在资料详情中维护关联。'
    if supplier and collaboration.internal(asset) and not targets.current(db,asset):
        return '请内部人员先关联客户订单，供应商随后可维护同客户的已发送订单。'
    return ''


def listing(db,user,factory,department=None,*,history=False):
    from app.services.carton_procurement import require_carton_factory
    require_carton_factory(factory)
    supplier=supplier_for(db,user,factory,department)
    permitted=['supplier'] if supplier else [d for d in access.DEPARTMENTS if access.allowed(user,factory,d)]
    if department and department not in permitted:raise HTTPException(403,'没有该部门资料读取权限')
    if not permitted:raise HTTPException(403,'没有部门资料读取权限')
    query=select(CartonMarkAsset).where(CartonMarkAsset.is_archived.is_(False),CartonMarkAsset.recognition_source!='materials_folder',
        or_(CartonMarkAsset.factory_id==factory,CartonMarkAsset.owner_department=='supplier',CartonMarkAsset.id.in_(collaboration.shared_asset_ids(db))))
    if supplier:query=query.where(CartonMarkAsset.factory_id==factory)
    if history:query=query.where(CartonMarkAsset.owner_department.is_(None))
    result=[]
    # Local to this listing; never retain schedule rows across requests/writes.
    schedule_rows_by_factory={}
    supplier_candidates=None
    for asset in db.scalars(query.order_by(CartonMarkAsset.created_at.desc(),CartonMarkAsset.id)):
        if access.visible(db,user,asset,library=True,supplier=supplier,view_factory=factory):
            # The viewer, supplier and factory are fixed for this list. Build the
            # authorized order choices once, then retain each source's own links.
            # Details, mutations and the next listing always query afresh.
            if supplier is not None and supplier_candidates is None:
                supplier_candidates=targets.candidates(db,user,factory,supplier=supplier)
            result.append(output(db,user,asset,supplier=supplier,view_factory=factory,
                schedule_rows_by_factory=schedule_rows_by_factory,supplier_candidates=supplier_candidates))
    return dict(items=result,total=len(result))


def associate(db,user,factory,identifier,body,refresh_actor=None):
    try:
        access.writes();asset=db.get(CartonMarkAsset,identifier)
        if not asset:raise HTTPException(404,'资料不存在')
        user=locked(db,user,asset.factory_id)
        if refresh_actor:user=refresh_actor()
        if factory!=asset.factory_id:
            from app.services.carton_procurement import _lock_receipt_factory
            _lock_receipt_factory(db,factory)
        supplier=access.external_actor(db,user,asset) if factory==asset.factory_id else None
        access.ensure(db,user,asset,write=True,supplier=supplier,view_factory=factory,collaborate=True,collaboration_action='associate')
        rid,saved=requests.request_event(db,user,factory,body.request_id,'QUICK_ASSOCIATE',dict(id=identifier,body=body.model_dump()))
        if not saved or 'result' not in saved:
            blocker=association_blocker(db,asset,supplier)
            if blocker:raise HTTPException(409,blocker)
            if body.targets and body.target:raise HTTPException(422,'不能同时提交两组关联目标')
            rows=resolve_many(db,user,factory,body.targets or ([body.target] if body.target else []),supplier,scope=body.target_scope,retain=asset)
            lifecycle.bump(db,asset,body.revision)
            if supplier and collaboration.internal(asset):
                collaboration.record(db,user,asset,supplier,collaboration.TARGETS,targets=rows)
            else:
                if body.target_scope=='ORDERS':
                    # Warehouse edits only purchase targets. Hidden business
                    # schedule references retain their original identity/state.
                    rows=[row for row in targets.current(db,asset,factory) if row['kind']=='SCHEDULE']+rows
                targets.record(db,user,asset,rows,factory)
                # Audience is an independent user choice. Linking or unlinking
                # orders must not overwrite an explicit INTERNAL/SUPPLIER setting.
                if factory==asset.factory_id:
                    current_audience=sharing.current(db,asset)
                    if current_audience['sharing_mode']=='SUPPLIER':
                        sharing.validate_recipient(db,asset,'SUPPLIER',current_audience['shared_supplier_id'])
            requests.record_request(db,user,asset,rid,saved,dict(asset_id=asset.id))
            result=output(db,user,asset,supplier=supplier,view_factory=factory);db.commit();return result
        else:db.rollback()
        return output(db,user,asset,supplier=supplier,view_factory=factory)
    except BaseException:db.rollback();raise


def audience(db,user,factory,identifier,body,refresh_actor=None):
    try:
        access.writes();asset=db.get(CartonMarkAsset,identifier)
        if not asset or asset.factory_id!=factory:raise HTTPException(404,'资料不存在')
        user=locked(db,user,factory)
        if refresh_actor:user=refresh_actor()
        access.ensure(db,user,asset,write=True)
        if not audience_editable(asset):raise HTTPException(403,'仅内部普通资料可设置此共享范围')
        sharing.ensure_audience_scope(db,user,asset)
        rid,saved=requests.request_event(db,user,factory,body.request_id,'QUICK_AUDIENCE',dict(id=identifier,body=body.model_dump()))
        if not saved or 'result' not in saved:
            recipient=receiver(db,asset,targets.current(db,asset)) if body.sharing_mode=='SUPPLIER' else ''
            if body.sharing_mode=='SUPPLIER' and not recipient:
                raise HTTPException(422,'当前厂区未配置唯一有效的对应供应商，请核对或选择仅内部可见')
            sharing.validate_recipient(db,asset,body.sharing_mode,recipient)
            lifecycle.bump(db,asset,body.revision)
            sharing.record(db,user,asset,body.sharing_mode,recipient)
            requests.record_request(db,user,asset,rid,saved,dict(asset_id=asset.id))
            result=output(db,user,asset);db.commit();return result
        db.rollback();return output(db,user,asset)
    except BaseException:db.rollback();raise


def classify(db,user,factory,identifier,body,refresh_actor=None):
    try:
        access.writes();asset=db.get(CartonMarkAsset,identifier)
        if not asset:raise HTTPException(404,'资料不存在')
        user=locked(db,user,asset.factory_id)
        if refresh_actor:user=refresh_actor()
        supplier=access.external_actor(db,user,asset) if factory==asset.factory_id else None
        access.ensure(db,user,asset,write=True,confirm=body.status=='READY',supplier=supplier,view_factory=factory,collaborate=True,classification=True)
        if body.status=='READY' and asset.asset_purpose!='MATERIAL':raise HTTPException(422,'内部凭据不是制作资料')
        rid,saved=requests.request_event(db,user,factory,body.request_id,'QUICK_CLASSIFY',dict(id=identifier,body=body.model_dump()))
        if not saved or 'result' not in saved:
            lifecycle.classify(db,user,asset.factory_id,identifier,CartonMarkAssetClassification(revision=body.revision,status=body.status),commit=False,view_factory=factory)
            requests.record_request(db,user,asset,rid,saved,dict(asset_id=asset.id))
            result=output(db,user,asset,supplier=supplier,view_factory=factory);db.commit();return result
        else:db.rollback()
        return output(db,user,asset,supplier=supplier,view_factory=factory)
    except BaseException:db.rollback();raise


def resolve_many(db,user,factory,selected,supplier,*,scope='ALL',retain=None):
    rows=[targets.resolve(db,user,factory,target,supplier=supplier,scope=scope,retain=retain) for target in selected]
    keys=[(row['kind'],row['id'],row['sheet'],row['row']) for row in rows]
    if len(keys)!=len(set(keys)):raise HTTPException(422,'关联订单不能重复')
    return rows


def share(db,user,factory,identifier,body,refresh_actor=None):
    from app.services.carton_asset_visibility import record
    try:
        access.writes();user=locked(db,user,factory,body.shared_factory_ids);asset=assets.active_asset(db,factory,identifier)
        if refresh_actor:user=refresh_actor()
        supplier=supplier_for(db,user,factory,'supplier',write=True)
        access.ensure(db,user,asset,write=True,supplier=supplier,collaboration_action='share')
        recipients=collaboration.share_recipients(db,user,body.shared_factory_ids)
        rid,saved=requests.request_event(db,user,factory,body.request_id,'QUICK_SHARE',dict(id=identifier,body=body.model_dump()))
        if not saved or 'result' not in saved:
            lifecycle.bump(db,asset,body.revision)
            if collaboration.internal(asset):
                collaboration.record(db,user,asset,supplier,collaboration.FACTORIES,recipients=recipients)
            else:record(db,user,asset,body.shared_factory_ids)
            requests.record_request(db,user,asset,rid,saved,dict(asset_id=asset.id))
        result=output(db,user,asset,supplier=supplier);db.commit();return result
    except BaseException:db.rollback();raise
