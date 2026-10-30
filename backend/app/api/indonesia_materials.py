from typing import Annotated, Literal
from urllib.parse import quote
from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from fastapi.routing import APIRoute
from pydantic import ValidationError
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.db import get_db
from app.schemas.indonesia_materials import Command, ReceiptTemplate, MasterImportContext
from app.services.auth import AuthContext, get_current_user
from app.services import indonesia_materials as service
from app.services import indonesia_material_import as imports
from app.services import indonesia_shared_options as shared_options
from app.services import indonesia_warehouse_import as warehouse_import
from app.services import indonesia_master_import as master_import
from app.services.customer_order_jobs import order_job_request, run_order_job


class MaterialRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()
        async def handler(request: Request):
            if len(request.query_params.getlist('factory_id')) > 1:
                return JSONResponse({'detail': '厂区参数不能重复'}, status_code=422)
            try:
                return await original(request)
            except ValidationError as exc:
                return JSONResponse({'detail': [{'loc': list(e['loc']), 'msg': e['msg']} for e in exc.errors()]}, status_code=422)
        return handler


router = APIRouter(prefix='/api/indonesia-materials', tags=['indonesia-materials'], route_class=MaterialRoute)
Db = Annotated[Session, Depends(get_db)]
User = Annotated[AuthContext, Depends(get_current_user)]


def refresh_user(request, db):
    return get_current_user(request, db)


@router.get('/workspace')
def workspace(db: Db, user: User, factory_id: str = Query(...)):
    return service.workspace(db, user, factory_id)


@router.post('/commands')
def command(body: Command, db: Db, user: User, request: Request):
    return service.run_command(db, user, body, refresh_user=lambda: refresh_user(request, db))


@router.get('/draft-assignees')
def draft_assignees(db: Db, user: User, factory_id: str = Query(...), search: str = Query('', max_length=128)):
    service.authorize(user, factory_id, 'write')
    from app.services.indonesia_material_ownership import assignees
    return assignees(db, user, factory_id, search)


@router.get('/shared-options')
def shared_workspace(db: Db, user: User):
    return shared_options.workspace(db, user)


@router.post('/shared-options/commands')
def shared_command(body: Command, db: Db, user: User, request: Request):
    return shared_options.run_command(db, user, body, refresh_user=lambda: refresh_user(request, db))


@router.post('/imports/preview', dependencies=[Depends(order_job_request)])
async def preview(db: Db, user: User, request: Request,
                  factory_id: str = Form(...), customer: str = Form(..., min_length=1, max_length=160),
                  recipient: Literal['RRI', 'RRM'] = Form(...), file: UploadFile = File(...)):
    service.authorize(user, factory_id, 'write')
    service.ready(db)
    form = await request.form()
    service.require(all(len(form.getlist(k)) == 1 for k in ('factory_id', 'customer', 'recipient', 'file')), '上传字段不能重复', 422)
    content = await file.read(25 * 1024 * 1024 + 1)
    service.require(0 < len(content) <= 25 * 1024 * 1024, '排期文件为空或超过 25 MB', 413)
    workbook = await run_order_job(imports.parse_workbook, content, db=db)
    return imports.preview(db, user, factory_id, customer.strip(), recipient, file.filename or '排期.xlsx', content,
                           workbook, refresh_user=lambda: refresh_user(request, db))


def download(asset):
    return Response(asset.content, media_type=asset.media_type,
                    headers={'Content-Disposition': "attachment; filename*=UTF-8''" + quote(asset.filename), 'Cache-Control': 'no-store'})


@router.post('/master-imports/preview', dependencies=[Depends(order_job_request)])
async def master_preview(db: Db, user: User, request: Request,
                         factory_id: str = Form(...), customer: str = Form(..., min_length=1, max_length=160),
                         context: str = Form(..., max_length=30000), file: UploadFile = File(...)):
    service.authorize(user, factory_id, 'write')
    service.ready(db)
    form = await request.form()
    service.require(all(len(form.getlist(key)) == 1 for key in ('factory_id', 'customer', 'context', 'file')), '上传字段不能重复', 422)
    selection = MasterImportContext.model_validate_json(context)
    products = master_import.selected_products(service.Ledger(db, factory_id), customer.strip(), selection.product_ids)
    product_codes = [product.data['code'] for product in products]
    from app.services.indonesia_master_archive import MAX_FILE_BYTES, upload_slot
    service.require(file.size is None or 0 < file.size <= MAX_FILE_BYTES, '文件为空或超过 200 MB', 413)
    with upload_slot():
        content = await file.read(MAX_FILE_BYTES + 1)
        service.require(0 < len(content) <= MAX_FILE_BYTES, '文件为空或超过 200 MB', 413)
        filename = file.filename or '统一资料.xlsx'
        parsed = await run_order_job(master_import.parse_material_book, content, filename, selection.mappings, product_codes, db=db)
        return master_import.preview(db, user, factory_id, customer.strip(), selection.product_ids, filename, content, parsed,
                                     refresh_user=lambda: refresh_user(request, db))


@router.get('/warehouse-imports/template')
def warehouse_template(db: Db, user: User, factory_id: str = Query(...)):
    service.authorize(user, factory_id, 'write')
    from io import StringIO
    import csv
    output = StringIO()
    csv.writer(output).writerow(warehouse_import.TEMPLATE)
    return Response(output.getvalue().encode('utf-8-sig'), media_type='text/csv; charset=utf-8',
        headers={'Content-Disposition': "attachment; filename*=UTF-8''" + quote('仓库实收导入模板.csv'), 'Cache-Control': 'no-store'})


@router.post('/warehouse-imports/template')
def order_receipt_template(body: ReceiptTemplate, db: Db, user: User):
    from app.services.indonesia_receipt_template import build_template
    content = build_template(db, user, body)
    return Response(content, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': "attachment; filename*=UTF-8''" + quote('仓库实收回传模板.xlsx'), 'Cache-Control': 'no-store'})


@router.post('/warehouse-imports/preview', dependencies=[Depends(order_job_request)])
async def warehouse_preview(db: Db, user: User, request: Request,
                            factory_id: str = Form(...), customer: str = Form(..., min_length=1, max_length=160),
                            recipient: Literal['RRI', 'RRM'] = Form(...), warehouse: str = Form('', max_length=160), file: UploadFile = File(...)):
    service.authorize(user, factory_id, 'write')
    service.ready(db)
    form = await request.form()
    service.require(all(len(form.getlist(key)) == 1 for key in ('factory_id', 'customer', 'recipient', 'warehouse', 'file')), '上传字段不能重复', 422)
    content = await file.read(25 * 1024 * 1024 + 1)
    service.require(0 < len(content) <= 25 * 1024 * 1024, '实收单为空或超过 25 MB', 413)
    filename = file.filename or '实收单.xlsx'
    rows = await run_order_job(warehouse_import.parse_warehouse_receipts, content, filename, db=db)
    return warehouse_import.preview(db, user, factory_id, customer.strip(), recipient, warehouse.strip(), filename, content, rows,
        refresh_user=lambda: refresh_user(request, db))


@router.get('/shipments/{entity_id}/export')
def export(entity_id: str, db: Db, user: User, factory_id: str = Query(...)):
    service.authorize(user, factory_id, 'export')
    service.ready(db)
    row = service.Ledger(db, factory_id).get(entity_id, 'shipment')
    service.require(row.data['status'] == 'confirmed', '请先由业务核对并确认出货')
    asset = db.get(service.Asset, row.data['export_asset_id'])
    service.require(asset is not None and asset.factory_id == factory_id, '导出版本不存在', 404)
    return download(asset)


@router.get('/assets/{entity_id}')
def asset(entity_id: str, db: Db, user: User, factory_id: str = Query(...)):
    service.authorize(user, factory_id)
    service.ready(db)
    row = db.get(service.Asset, entity_id)
    service.require(row is not None and row.factory_id == factory_id, '原始资料不存在', 404)
    from app.services.indonesia_material_ownership import Access
    access = Access(db, user, factory_id)
    sources = list(db.scalars(select(service.Record).where(service.Record.factory_id == factory_id,
        service.Record.kind == 'import', service.Record.data['asset_id'].as_string() == entity_id)))
    service.require(not sources or any(access.visible(source) for source in sources), '原始资料不存在或已转交其他跟客', 404)
    export_owner = db.scalar(select(service.Record.id).where(service.Record.factory_id == factory_id,
                            service.Record.kind == 'shipment', service.Record.data['export_asset_id'].as_string() == entity_id))
    if export_owner:
        service.authorize(user, factory_id, 'export')
    return download(row)
