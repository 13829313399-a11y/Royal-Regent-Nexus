"""Domain-scoped location identities; catalog changes never rewrite stock evidence."""
import json
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select
from app.core.time import business_now
from app.models.warehouse_operations import WarehouseOperation
from app.services import fabric_procurement as procurement
from app.services.fabric_procurement_parser import digest, dump


def catalog(db, warehouse):
    if warehouse == 'fabric':
        from app.services.fabric_master import records
        return [dict(id=r.id, warehouse=json.loads(r.data_json).get('warehouse', ''), code=r.code,
                     label=f"{json.loads(r.data_json).get('warehouse', '')}／{r.code}", status=r.status, revision=r.revision)
                for r in records(db) if r.kind == 'LOCATION']
    current = {}
    for row in db.scalars(select(WarehouseOperation).where(WarehouseOperation.factory_id == procurement.FACTORY,
            WarehouseOperation.warehouse == warehouse, WarehouseOperation.kind == 'MASTER_LOCATION').order_by(WarehouseOperation.sequence)):
        value = json.loads(row.payload_json)['location_record']
        current[value['id']] = value
    return list(current.values())


def resolve(db, warehouse, identifier, *, inbound=True):
    location = next((r for r in catalog(db, warehouse) if r['id'] == identifier), None)
    if not location:
        raise HTTPException(422, '请先在本仓基础资料建立仓库和仓位，再选择有效仓位；不能填写未建档仓位')
    if inbound and location['status'] != 'ACTIVE':
        raise HTTPException(422, '目标仓位未启用，不能入库或调入')
    return location


def save_semi(db, actor, payload):
    from app.services import warehouse_operations as operations
    operations.ensure_schema(db)
    state = procurement.lock_factory(db)
    body = payload.model_dump(mode='json')
    signature = digest(['semi-location', actor.id, body])
    previous = db.scalar(select(WarehouseOperation).where(WarehouseOperation.factory_id == procurement.FACTORY,
        WarehouseOperation.warehouse == 'semi', WarehouseOperation.request_id == str(payload.request_id)))
    if previous:
        if previous.request_hash != signature:
            raise HTTPException(409, '该请求已用于其他资料或内容')
        result = json.loads(previous.payload_json)['location_record']; db.rollback(); return result
    places = catalog(db, 'semi')
    old = next((r for r in places if r['id'] == payload.id), None)
    if (payload.id and not old) or payload.expected_revision != (old['revision'] if old else 0):
        raise HTTPException(409, '仓位资料已变化，请刷新后修改')
    if old and (old['code'] != payload.code or old['warehouse'] != payload.warehouse):
        raise HTTPException(422, '仓位身份创建后不可改换仓库或编码；实物移动请使用调仓')
    if any(r['id'] != payload.id and (r['warehouse'].casefold(), r['code'].casefold()) ==
           (payload.warehouse.casefold(), payload.code.casefold()) for r in places):
        raise HTTPException(409, '该仓库中已存在相同仓位，请修改原资料')
    identifier = 'SL-' + uuid4().hex
    record = dict(id=old['id'] if old else identifier, warehouse=payload.warehouse, code=payload.code,
                  label=f'{payload.warehouse}／{payload.code}', status=payload.status, revision=payload.expected_revision + 1)
    rows = operations.documents(db, 'semi')
    now = business_now()
    db.add(WarehouseOperation(id=identifier, factory_id=procurement.FACTORY, warehouse='semi',
        sequence=max((r.sequence for r in rows), default=0) + 1, request_id=str(payload.request_id), request_hash=signature,
        kind='MASTER_LOCATION', business_date=now.date().isoformat(), payload_json=dump({'location_record': record, 'before': old}),
        actor_id=actor.id, actor_name=actor.display_name, occurred_at=now.isoformat()))
    state.revision += 1
    db.commit()
    return record
