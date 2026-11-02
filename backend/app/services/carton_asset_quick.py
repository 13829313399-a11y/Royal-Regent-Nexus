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


def locked(db,user,factory):
    from app.services.carton_special_requests import locked_actor
    from app.services.carton_procurement import require_carton_factory
    db.expire_all()
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
        supplier=supplier_for(db,user,factory,department)
        if supplier and body.purpose=='EVIDENCE':raise HTTPException(403,'客户凭据只允许内部上传')
        recognition,content=prepared
        sha=hashlib.sha256(content).hexdigest()
        rid,saved=requests.request_event(db,user,factory,body.request_id,'QUICK_UPLOAD',dict(body=body.model_dump(),sha256=sha,name=recognition['file_name']))
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
        sharing.record(db,user,asset,'SUPPLIER' if recipient else 'INTERNAL',recipient)
        assets.audit(db,user,asset,'CARTON_MARK_ASSET_CREATED',dict(sha256=sha,owner_department=department,owner_supplier_id=supplier_id,purpose=body.purpose))
        requests.record_request(db,user,asset,rid,saved,dict(asset_id=asset.id))
        result=output(db,user,asset,supplier=supplier)
        db.commit();return result
    except BaseException:db.rollback();raise


def output(db,user,asset,*,supplier=None,view_factory=None):
    if supplier is None and view_factory in (None,asset.factory_id):supplier=access.external_actor(db,user,asset)
    access.ensure(db,user,asset,supplier=supplier,view_factory=view_factory)
    state=lifecycle.current(db,asset)
    from app.services.carton_asset_visibility import factories
    can_manage=access.visible(db,user,asset,write=True,supplier=supplier,view_factory=view_factory,collaborate=True)
    can_confirm=access.visible(db,user,asset,write=True,confirm=True,supplier=supplier,view_factory=view_factory,collaborate=True)
    statuses=(['DRAFT','PENDING','HISTORY'] if can_manage else []) + (['READY'] if can_confirm and asset.asset_purpose=='MATERIAL' else [])
    if state.superseded_by_asset_id:statuses=[]
    visible_targets=targets.valid(db,asset,view_factory)
    if supplier:
        purchase_ids=targets.purchase_order_ids(db,asset)
        special_ids={(x['kind'],x['id']) for x in visible_targets if x.get('supplier_id')==supplier.id}
        visible_targets=[x for x in targets.candidates(db,user,asset.factory_id,supplier=supplier)
            if x['kind']=='REGULAR' and x['id'] in purchase_ids or (x['kind'],x['id']) in special_ids]
    return dict(id=asset.id,factory_id=asset.factory_id,owner_department=asset.owner_department,
        view_factory_id=view_factory or asset.factory_id,shared_factory_ids=factories(db,asset),
        can_classify=bool(statuses),allowed_statuses=statuses,can_associate=can_manage,
        created_by_name=asset.created_by_name,created_at=asset.created_at,
        owner_supplier_id=asset.owner_supplier_id,purpose=asset.asset_purpose,kind=asset.kind,file_name=asset.file_name,
        content_type=asset.content_type,sha256=asset.sha256,revision=asset.revision,contract_number=asset.contract_number,
        text=asset.content.decode('utf-8') if asset.kind=='text' else None,workflow=state.model_dump(),
        targets=[{k:v for k,v in row.items() if k not in {'customer_code','identity','revision','supplier_id'}}
            if supplier else row for row in visible_targets],uploaded=True,warning=asset.warning)


def listing(db,user,factory,department=None,*,history=False):
    from app.services.carton_procurement import require_carton_factory
    require_carton_factory(factory)
    supplier=supplier_for(db,user,factory,department)
    permitted=['supplier'] if supplier else [d for d in access.DEPARTMENTS if access.allowed(user,factory,d)]
    if department and department not in permitted:raise HTTPException(403,'没有该部门资料读取权限')
    if not permitted:raise HTTPException(403,'没有部门资料读取权限')
    query=select(CartonMarkAsset).where(CartonMarkAsset.is_archived.is_(False),CartonMarkAsset.recognition_source!='materials_folder',
        or_(CartonMarkAsset.factory_id==factory,CartonMarkAsset.owner_department=='supplier'))
    if supplier:query=query.where(CartonMarkAsset.factory_id==factory)
    if history:query=query.where(CartonMarkAsset.owner_department.is_(None))
    result=[]
    for asset in db.scalars(query.order_by(CartonMarkAsset.created_at.desc(),CartonMarkAsset.id)):
        if access.visible(db,user,asset,library=True,supplier=supplier,view_factory=factory):result.append(output(db,user,asset,supplier=supplier,view_factory=factory))
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
        access.ensure(db,user,asset,write=True,supplier=supplier,view_factory=factory,collaborate=True)
        rid,saved=requests.request_event(db,user,factory,body.request_id,'QUICK_ASSOCIATE',dict(id=identifier,body=body.model_dump()))
        if not saved or 'result' not in saved:
            if body.targets and body.target:raise HTTPException(422,'不能同时提交两组关联目标')
            rows=resolve_many(db,user,factory,body.targets or ([body.target] if body.target else []),supplier,scope=body.target_scope,retain=asset)
            lifecycle.bump(db,asset,body.revision);targets.record(db,user,asset,rows,factory)
            if factory==asset.factory_id:
                recipient=receiver(db,asset,rows);sharing.record(db,user,asset,'SUPPLIER' if recipient else 'INTERNAL',recipient)
            requests.record_request(db,user,asset,rid,saved,dict(asset_id=asset.id))
            result=output(db,user,asset,supplier=supplier,view_factory=factory);db.commit();return result
        else:db.rollback()
        return output(db,user,asset,supplier=supplier,view_factory=factory)
    except BaseException:db.rollback();raise


def classify(db,user,factory,identifier,body,refresh_actor=None):
    try:
        access.writes();asset=db.get(CartonMarkAsset,identifier)
        if not asset:raise HTTPException(404,'资料不存在')
        user=locked(db,user,asset.factory_id)
        if refresh_actor:user=refresh_actor()
        supplier=access.external_actor(db,user,asset) if factory==asset.factory_id else None
        access.ensure(db,user,asset,write=True,confirm=body.status=='READY',supplier=supplier,view_factory=factory,collaborate=True)
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
        access.writes();user=locked(db,user,factory);asset=assets.active_asset(db,factory,identifier)
        if refresh_actor:user=refresh_actor()
        supplier=supplier_for(db,user,factory,'supplier',write=True)
        access.ensure(db,user,asset,write=True,supplier=supplier)
        rid,saved=requests.request_event(db,user,factory,body.request_id,'QUICK_SHARE',dict(id=identifier,body=body.model_dump()))
        if not saved or 'result' not in saved:
            lifecycle.bump(db,asset,body.revision);record(db,user,asset,body.shared_factory_ids)
            requests.record_request(db,user,asset,rid,saved,dict(asset_id=asset.id))
        result=output(db,user,asset,supplier=supplier);db.commit();return result
    except BaseException:db.rollback();raise
