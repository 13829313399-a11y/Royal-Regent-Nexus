from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db import get_db
from app.services.auth import AuthContext, can, get_current_user
from app.schemas.warehouse_operations import WarehouseDocumentRequest, WarehouseLocationSave, WarehouseBulkIssue
from app.services import warehouse_locations
from app.services import warehouse_operations as service

router = APIRouter(prefix='/api/warehouse-operations', tags=['warehouse-operations'])
Warehouse = Literal['fabric', 'semi']


def capabilities(actor, warehouse, factory_id):
    service.procurement.require_factory(factory_id)
    family = 'fabric_operations' if warehouse == 'fabric' else 'semi_operations'
    return {action: can(actor, f'{family}:{action}', factory_id, 'pmc-warehouse')
            for action in ('read', 'operate', 'quality', 'correct', 'master')}


@router.get('/{warehouse}')
def workspace(warehouse: Warehouse, factory_id: str, db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    permissions = capabilities(actor, warehouse, factory_id)
    if not permissions['read']:
        raise HTTPException(403, '无当前仓库收发查询权限')
    return {**service.workspace(db, warehouse), 'permissions': permissions}


@router.post('/{warehouse}/documents')
def post(warehouse: Warehouse, payload: WarehouseDocumentRequest, db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    permissions = capabilities(actor, warehouse, payload.factory_id)
    action = 'quality' if payload.kind == 'QUALITY' else 'correct' if payload.kind in {'CORRECTION', 'LOCATION_BIND'} else 'operate'
    if not permissions['read'] or not permissions[action]:
        raise HTTPException(403, '无当前仓库本项操作权限')
    return service.post(db, actor, warehouse, payload)


@router.post('/{warehouse}/issues/bulk')
def bulk_issue(warehouse: Warehouse, payload: WarehouseBulkIssue, db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    permissions = capabilities(actor, warehouse, payload.factory_id)
    if not permissions['read'] or not permissions['operate']:
        raise HTTPException(403, '无当前仓库出库权限')
    return service.bulk_issue(db, actor, warehouse, payload)


@router.post('/semi/locations')
def save_location(payload: WarehouseLocationSave, db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    permissions = capabilities(actor, 'semi', payload.factory_id)
    if not permissions['read'] or not permissions['master']:
        raise HTTPException(403, '无半成品仓基础资料维护权限')
    return warehouse_locations.save_semi(db, actor, payload)
