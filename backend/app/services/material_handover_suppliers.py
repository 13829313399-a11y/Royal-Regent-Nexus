"""Supplier masters are identities; expiring credentials do not own their history."""
import hashlib
import json
import secrets
from datetime import timedelta
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select
from app.core.time import business_now
from app.models.material_handover import HandoverIssuer, HandoverSupplierBinding, HandoverLinkCommand
from app.models.fabric_master import FabricMasterRecord
from app.services.fabric_master import record_data
from app.services.fabric_procurement_parser import dump, digest

FACTORY = 'huakang-c'


def supplier(db, identifier, *, active=True):
    row=db.scalar(select(FabricMasterRecord).where(FabricMasterRecord.id==identifier,
        FabricMasterRecord.factory_id==FACTORY, FabricMasterRecord.kind=='SUPPLIER'))
    if row is None or (active and row.status!='ACTIVE'):
        raise HTTPException(422,'请先在基础资料中启用对应供应商，不能按名称猜测归属')
    return row


def binding(db, identifier):
    return db.get(HandoverSupplierBinding, identifier)


def bind(db, actor, row, identifier):
    master=supplier(db, identifier)
    if row.kind!='SUPPLIER' or row.name!=master.name:
        raise HTTPException(422,'原入口名称须与选中的供应商基础资料一致；不能改绑历史单据到另一家供应商')
    old=binding(db,row.id)
    if old:
        if old.supplier_id!=identifier: raise HTTPException(409,'已绑定的供应商身份不能改写')
        return
    db.add(HandoverSupplierBinding(issuer_id=row.id,factory_id=FACTORY,supplier_id=identifier,
        supplier_snapshot_json=dump(record_data(master)),created_by=actor.id,created_at=business_now().isoformat()))
    db.flush()


def replay(db, actor, request_id, signature):
    old=db.scalar(select(HandoverLinkCommand).where(HandoverLinkCommand.factory_id==FACTORY,
        HandoverLinkCommand.actor_key=='user:'+actor.id,HandoverLinkCommand.request_id==str(request_id)))
    if old:
        if old.request_hash!=signature: raise HTTPException(409,'链接操作编号已用于其他内容')
        return {**json.loads(old.result_json),'replayed':True}
    return None


def record(db, actor, row, payload, signature, kind, result):
    db.add(HandoverLinkCommand(id='MHC-'+uuid4().hex,factory_id=FACTORY,issuer_id=row.id,
        actor_key='user:'+actor.id,actor_name=actor.display_name,request_id=str(payload.request_id),request_hash=signature,
        kind=kind,detail_json=dump(payload.model_dump(mode='json')),result_json=dump({k:v for k,v in result.items() if k!='token'}),
        occurred_at=business_now().isoformat()))


def create(db, actor, payload):
    from app.services import material_handover as service
    service.ensure_schema(db);service.staff(actor,'manage');service.inventory.procurement.lock_factory(db)
    signature=digest(['CREATE',payload.model_dump(mode='json')])
    old=replay(db,actor,payload.request_id,signature)
    if old is not None:return old
    if payload.kind=='SUPPLIER':
        master=supplier(db,payload.supplier_id)
        if payload.name and payload.name!=master.name:raise HTTPException(422,'供应商名称与基础资料不一致')
        existing=db.scalar(select(HandoverIssuer).join(HandoverSupplierBinding,HandoverSupplierBinding.issuer_id==HandoverIssuer.id)
            .where(HandoverSupplierBinding.factory_id==FACTORY,HandoverSupplierBinding.supplier_id==master.id,HandoverIssuer.active==1))
        if existing:raise HTTPException(409,'该供应商已有固定入口，请续期或更新原链接以保留历史')
        name=master.name
    else:
        if not payload.name or payload.supplier_id:raise HTTPException(422,'请填写车间 / 裁床名称；领料方不绑定供应商账')
        name=payload.name
    token=secrets.token_urlsafe(32);now=business_now()
    row=HandoverIssuer(id='MHI-'+uuid4().hex,factory_id=FACTORY,name=name,kind=payload.kind,
        token_hash=hashlib.sha256(token.encode()).hexdigest(),expires_at=(now+timedelta(days=payload.valid_days)).isoformat(),
        active=1,revision=1,created_by=actor.id,created_at=now.isoformat())
    db.add(row);db.flush()
    if payload.kind=='SUPPLIER':bind(db,actor,row,payload.supplier_id)
    result={**service.issuer_out(row,db),'token':token}
    record(db,actor,row,payload,signature,'CREATE',result);db.commit();return result


def action(db, actor, identifier, payload, kind):
    from app.services import material_handover as service
    service.ensure_schema(db);service.staff(actor,'manage');service.inventory.procurement.lock_factory(db)
    signature=digest([kind,identifier,payload.model_dump(mode='json')])
    old=replay(db,actor,payload.request_id,signature)
    if old is not None:return old
    row=db.scalar(select(HandoverIssuer).where(HandoverIssuer.id==identifier,HandoverIssuer.factory_id==FACTORY).with_for_update())
    if row is None:raise HTTPException(404,'未找到当前厂区入口')
    service.check_revision(row,payload.expected_revision)
    token=''
    if kind=='BIND':bind(db,actor,row,payload.supplier_id)
    elif kind=='RENEW':
        identity=binding(db,row.id)
        if row.kind=='SUPPLIER':
            if identity is None:raise HTTPException(422,'请先把原入口关联到供应商基础资料')
            supplier(db,identity.supplier_id)
        token=secrets.token_urlsafe(32);row.token_hash=hashlib.sha256(token.encode()).hexdigest()
        row.active=1;row.expires_at=(business_now()+timedelta(days=payload.valid_days)).isoformat()
    elif kind=='REVOKE':row.active=0
    else:raise HTTPException(422,'未知入口操作')
    row.revision+=1;db.flush();result=service.issuer_out(row,db)
    if token:result['token']=token
    record(db,actor,row,payload,signature,kind,result);db.commit();return result
