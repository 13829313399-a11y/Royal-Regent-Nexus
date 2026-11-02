from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from datetime import date
from uuid import UUID
from fastapi.responses import Response
from sqlalchemy.orm import Session
from app.db import get_db
from app.services.auth import AuthContext, can, get_current_user
from app.schemas.warehouse_operations import WarehouseDocumentRequest, WarehouseLocationSave, WarehouseBulkIssue
from app.services import warehouse_locations
from app.services import warehouse_operations as service
from app.schemas.fabric_inventory_setup import CountCreate, CountAction
from app.services import fabric_inventory_setup as setup
from app.services import fabric_legacy_stock

router = APIRouter(prefix='/api/warehouse-operations', tags=['warehouse-operations'])
Warehouse = Literal['fabric', 'semi']


from app.schemas.fabric_issue_groups import GroupSave, GroupPreview, GroupIssue, GroupRecovery
from app.services import fabric_issue_groups


def group_access(actor, factory_id):
    permissions = capabilities(actor, 'fabric', factory_id)
    if not permissions['read'] or not permissions['operate']:
        raise HTTPException(403, '无布料仓配套发料权限')


@router.post('/fabric/issue-groups')
def save_issue_group(payload: GroupSave, db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    group_access(actor, payload.factory_id)
    return fabric_issue_groups.save(db, actor, payload)


@router.post('/fabric/issue-groups/preview')
def preview_issue_group(payload: GroupPreview, db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    group_access(actor, payload.factory_id)
    from fastapi.responses import JSONResponse
    return JSONResponse(fabric_issue_groups.preview(db, actor, payload), headers={'Cache-Control': 'no-store'})


@router.post('/fabric/issue-groups/issue')
def post_issue_group(payload: GroupIssue, db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    group_access(actor, payload.factory_id)
    return fabric_issue_groups.post(db, actor, payload)


@router.post('/fabric/issue-groups/recover')
def recover_issue_group(payload: GroupRecovery, db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    if not capabilities(actor, 'fabric', payload.body.factory_id)['read']:
        raise HTTPException(403, '无布料仓查询权限')
    return fabric_issue_groups.recover(db, actor, payload)


def capabilities(actor, warehouse, factory_id):
    service.procurement.require_factory(factory_id)
    family = 'fabric_operations' if warehouse == 'fabric' else 'semi_operations'
    return {action: can(actor, f'{family}:{action}', factory_id, 'pmc-warehouse')
            for action in ('read', 'operate', 'quality', 'correct', 'master')}


def setup_access(actor, factory_id, action='read'):
    permissions = capabilities(actor, 'fabric', factory_id)
    if not permissions['read'] or not permissions[action]:
        raise HTTPException(403, '无布料仓本项权限；期初和盘点入账需要库存更正权限')
    return permissions


@router.post('/fabric/legacy-stock/preview')
def legacy_stock_preview(factory_id: str = Form(...), file: UploadFile = File(...),
                         db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    if not capabilities(actor, 'fabric', factory_id)['read']:
        raise HTTPException(403, '无布料仓收发查询权限，无法预检旧库存表')
    from fastapi.responses import JSONResponse
    return JSONResponse(fabric_legacy_stock.preview(db, file.filename or '', file.file.read(fabric_legacy_stock.MAX_BYTES + 1)),
                        headers={'Cache-Control': 'no-store'})


@router.get('/fabric/inventory-setup')
def inventory_setup(factory_id: str, db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    permissions = setup_access(actor, factory_id)
    from fastapi.responses import JSONResponse
    return JSONResponse({**setup.workspace(db), 'permissions':permissions}, headers={'Cache-Control':'no-store'})


@router.get('/fabric/inventory-setup/template')
def opening_template(factory_id: str, db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    setup_access(actor, factory_id)
    service.ensure_schema(db)
    return Response(setup.template(db), media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition':'attachment; filename="fabric-opening-inventory.xlsx"','Cache-Control':'no-store'})


@router.post('/fabric/inventory-setup/preview')
def opening_preview(factory_id: str = Form(...), cutoff: date = Form(...), source_no: str = Form(..., max_length=128), file: UploadFile = File(...),
                    db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    setup_access(actor, factory_id, 'correct')
    return setup.opening_preview(db, actor, file.filename or '', file.file.read(setup.MAX_BYTES+1), cutoff, source_no)


@router.post('/fabric/inventory-setup/import')
def opening_import(factory_id: str = Form(...), cutoff: date = Form(...), source_no: str = Form(..., max_length=128), file: UploadFile = File(...),
                   request_id: UUID = Form(...), token: str = Form(..., min_length=64, max_length=64), confirmed: bool = Form(False),
                   db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    setup_access(actor, factory_id, 'correct')
    return setup.apply_opening(db, actor, file.filename or '', file.file.read(setup.MAX_BYTES+1), cutoff, source_no, request_id, token, confirmed)


@router.post('/fabric/inventory-setup/counts')
def create_count(payload: CountCreate, db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    setup_access(actor, payload.factory_id, 'operate')
    return setup.create_count(db, actor, payload)


@router.post('/fabric/inventory-setup/counts/{identifier}')
def act_count(identifier: str, payload: CountAction, db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    setup_access(actor, payload.factory_id, 'correct' if payload.action == 'POST' else 'operate')
    return setup.act_count(db, actor, identifier, payload)


def quantity_monthly(db, actor, factory_id, month, direction, channel, party_key, search='', unit='', date_order='DESC'):
    if not capabilities(actor, 'fabric', factory_id)['read']:
        raise HTTPException(403, '无布料仓月度数量查询权限')
    from app.services.fabric_quantity_monthly import report
    return report(db, month, direction, channel, party_key, search, unit, date_order)


@router.get('/fabric/monthly')
def monthly(factory_id: str, month: str, direction: str = '', channel: str = '', party_key: str = '',
            search: str = '', unit: str = '', date_order: str = 'DESC',
            db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    from fastapi.responses import JSONResponse
    return JSONResponse(quantity_monthly(db, actor, factory_id, month, direction, channel, party_key, search, unit, date_order),
                        headers={'Cache-Control': 'no-store'})


@router.get('/fabric/monthly/export')
def export_monthly(factory_id: str, month: str, direction: str = '', channel: str = '', party_key: str = '',
                   search: str = '', unit: str = '', date_order: str = 'DESC',
                   version: str = '', db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    from app.services.fabric_quantity_monthly import export_xlsx
    result = quantity_monthly(db, actor, factory_id, month, direction, channel, party_key, search, unit, date_order)
    if version and version != result['version']:
        raise HTTPException(409, '收发记录已变化，请刷新月度汇总后再导出')
    return Response(export_xlsx(result), media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Cache-Control': 'no-store', 'Content-Disposition': f'attachment; filename="fabric-{month}-quantities.xlsx"'})


@router.get('/fabric/order-summary')
def order_summary(factory_id: str, date_from: str = '', date_to: str = '', search: str = '', supplier: str = '',
                  db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    if not capabilities(actor, 'fabric', factory_id)['read'] or not can(actor, 'fabric_warehouse:read', factory_id, 'pmc-warehouse'):
        raise HTTPException(403, '无布料仓订单收发查询权限')
    from fastapi.responses import JSONResponse
    from app.services.fabric_order_summary import report
    return JSONResponse(report(db, date_from, date_to, search, supplier), headers={'Cache-Control': 'no-store'})


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


@router.post('/{warehouse}/documents/recover')
def recover(warehouse: Warehouse, payload: WarehouseDocumentRequest, db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    permissions = capabilities(actor, warehouse, payload.factory_id)
    # Recovery cannot post stock. Read access plus the original actor/content hash
    # lets a user resolve their uncertain command after write permission is revoked.
    if not permissions['read']:
        raise HTTPException(403, '无当前仓库查询权限')
    return service.recover(db, actor, warehouse, payload)


@router.post('/semi/locations')
def save_location(payload: WarehouseLocationSave, db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    permissions = capabilities(actor, 'semi', payload.factory_id)
    if not permissions['read'] or not permissions['master']:
        raise HTTPException(403, '无半成品仓基础资料维护权限')
    return warehouse_locations.save_semi(db, actor, payload)
