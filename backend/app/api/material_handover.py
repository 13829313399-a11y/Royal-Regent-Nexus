import hashlib
import json
import sqlite3
import time
from typing import Literal
from urllib.parse import quote
from uuid import UUID
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Request, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from app.db import get_db
from app.services.auth import AuthContext, get_current_user
from app.models.material_handover import HandoverIssuer, HandoverDocument, HandoverSource, HandoverSupplierBinding
from app.schemas.material_handover import (
    IssuerInput, IssuerRevoke, IssuerRenew, IssuerBind, DocumentSave, DocumentAction, ScanInput, PostingInput,
    ReceiptLinkInput, ReceiptUnlinkInput, ReceiptPurchaseLinkInput, RejectionFollowupInput,
)
from app.services import material_handover as service
from app.services import material_handover_files as files
from app.services import material_handover_receipts as receipts
from app.services import material_handover_purchase_review as purchase_review
from app.services import material_handover_rejections as rejections

router = APIRouter(prefix='/api/material-handover', tags=['material-handover'])


def public_result(result):
    # Keep internal purchase IDs, warehouse batch IDs and staff identities within the warehouse.
    data = result['data']
    lines = [{**line, 'purchase_detail_id': ''} for line in data['lines']]
    return {**{k: v for k, v in result.items() if k not in {'receipt_observations', 'receipt_rejection', 'prior_receipts', 'revoked_receipt_links'}}, 'data': {**data, 'lines': lines},
        'movements': [{k: v for k, v in movement.items() if k not in {'actor_name', 'batch_id', 'manual_reference'}}
        for movement in result.get('movements', [])]}


def factory(value):
    service.inventory.procurement.require_factory(value)


def staff_access(db, actor, factory_id, action='read'):
    factory(factory_id); service.ensure_schema(db)
    return service.staff(actor, action)


def refresh_staff(request, db, factory_id, action='operate'):
    service.inventory.procurement.lock_factory(db)
    actor = get_current_user(request, db)
    return actor, staff_access(db, actor, factory_id, action)


def response_file(content, name, media):
    return Response(content, media_type=media, headers={'Content-Disposition': "inline; filename*=UTF-8''" + quote(name),
        'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer'})


def source_response(db, access, identifier):
    service.document(db, access, identifier)
    source = db.get(HandoverSource, identifier)
    if source is None or hashlib.sha256(source.content).hexdigest() != source.sha256:
        raise HTTPException(409, '原件完整性校验失败，请联系仓库')
    return response_file(source.content, source.file_name, source.content_type)


def print_snapshot(db, access, identifier, expected_revision):
    row = service.document(db, access, identifier)
    service.require_preparer(db, access, row)
    service.check_revision(row, expected_revision)
    if row.status != 'CONFIRMED':
        raise HTTPException(409, '只有已确认的有效单据可以准备原单加码打印')
    source = db.get(HandoverSource, identifier)
    if source is None or hashlib.sha256(source.content).hexdigest() != source.sha256:
        raise HTTPException(409, '原件完整性校验失败，请联系仓库')
    return dict(name=source.file_name, content=source.content, data=json.loads(row.data_json),
                extraction=json.loads(row.extraction_json), code=service.code(row), signature=row.data_json)


def check_print_snapshot(db, access, identifier, snapshot):
    row = service.document(db, access, identifier)
    service.require_preparer(db, access, row)
    if row.status != 'CONFIRMED' or service.code(row) != snapshot['code'] or row.data_json != snapshot['signature']:
        raise HTTPException(409, '单据状态已变化，请刷新后准备原单打印')


def print_database_step(db, operation):
    for retry in (True, False):
        try:
            return operation()
        except (OperationalError, HTTPException) as error:
            # The shared factory lock can wrap a SQLite lock error in HTTP 409.
            cause = error if isinstance(error, OperationalError) else error.__cause__
            driver_error = cause.orig if isinstance(cause, OperationalError) else None
            if not isinstance(driver_error, sqlite3.OperationalError):
                raise
            code = getattr(driver_error, 'sqlite_errorcode', 0) & 0xff
            if code not in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                raise
            db.rollback()
            if not retry:
                raise HTTPException(503, '数据库正在处理其他操作，请稍后重试原单加码打印',
                                    headers={'Retry-After': '1'}) from error
            time.sleep(0.15)


def prepare_original_print(db, identifier, expected_revision, corner, access, fresh_access):
    snapshot = print_database_step(db, lambda: print_snapshot(db, access(), identifier, expected_revision))
    db.rollback()
    content = files.render_original(snapshot['name'], snapshot['content'], snapshot['data'],
                                    snapshot['extraction'], snapshot['code'], corner)

    def recheck():
        service.inventory.procurement.lock_factory(db)
        check_print_snapshot(db, fresh_access(), identifier, snapshot)

    print_database_step(db, recheck)
    return response_file(content, identifier+'-原单加码.pdf', 'application/pdf')


@router.get('/documents/{identifier}/print')
def original_print(request: Request, identifier: str, factory_id: str, expected_revision: int = Query(..., ge=1),
                   corner: Literal['left', 'right'] = 'right', db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    return prepare_original_print(
        db, identifier, expected_revision, corner,
        lambda: staff_access(db, actor, factory_id),
        lambda: staff_access(db, get_current_user(request, db), factory_id),
    )


@router.get('/external/documents/{identifier}/print')
def external_original_print(identifier: str, expected_revision: int = Query(..., ge=1), corner: Literal['left', 'right'] = 'right',
                            x_handover_key: str = Header(default=''), db: Session = Depends(get_db)):
    def access():
        return service.external(db, x_handover_key)

    return prepare_original_print(db, identifier, expected_revision, corner, access, access)


def list_documents(db, access, limit, offset, status, search='', kind='ALL', supplier_id=''):
    # Read metadata only; never load original files or extraction evidence for list filtering.
    query = select(HandoverDocument.id, HandoverDocument.status, HandoverDocument.revision,
        HandoverDocument.created_at, HandoverDocument.confirmed_at, HandoverDocument.data_json,
        HandoverSupplierBinding.supplier_id.label('bound_supplier_id')).outerjoin(HandoverSupplierBinding,
        (HandoverSupplierBinding.issuer_id == HandoverDocument.issuer_id) &
        (HandoverSupplierBinding.factory_id == HandoverDocument.factory_id)
    ).where(HandoverDocument.factory_id == service.FACTORY, service.document_scope(db, access))
    if status != 'ALL':
        query = query.where(HandoverDocument.status == status)
    rows = db.execute(query.order_by(HandoverDocument.updated_at.desc(), HandoverDocument.id))
    needle = search.strip().casefold()
    items, total = [], 0
    delivery_lines = {}
    for row in rows:
        body = json.loads(row.data_json)
        if kind != 'ALL' and body.get('kind') != kind:
            continue
        if supplier_id and (body.get('kind') != 'DELIVERY' or
                (row.bound_supplier_id or body.get('supplier_id', '')) != supplier_id):
            continue
        if needle:
            values = [body.get(field, '') for field in
                ('source_no', 'counterparty', 'contract_no', 'production_no', 'product_no')]
            values.extend(line.get(field, '') for line in body.get('lines', [])
                for field in ('item_code', 'item_name', 'contract_no', 'production_no', 'product_no'))
            if not any(needle in str(value or '').casefold() for value in values):
                continue
        # Filtering and access checks precede pagination, including searches beyond the first 50 rows.
        if offset <= total < offset + limit:
            items.append({'id': row.id, 'status': row.status, 'revision': row.revision,
                'created_at': row.created_at, 'confirmed_at': row.confirmed_at,
                'data': {key: value for key, value in body.items() if key != 'lines'},
                'line_count': len(body.get('lines', []))})
            if not access.issuer_id and row.status == 'CONFIRMED' and body.get('kind') == 'DELIVERY':
                delivery_lines[row.id] = body.get('lines', [])
        total += 1
    statuses = service.receipt_processing_statuses(db, delivery_lines)
    for item in items:
        if item['id'] in statuses:
            item['processing_status'] = statuses[item['id']]
    if not access.issuer_id:
        rejections.add_summaries(db, items)
    return {'items': items, 'total': total, 'limit': limit, 'offset': offset}


@router.get('/workspace')
def workspace(factory_id: str, db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    staff_access(db, actor, factory_id)
    from app.services.fabric_master import records, record_data
    return {'factory_id': service.FACTORY, 'inventory': service.inventory.workspace(db, 'fabric'),
        'can_operate': service.can(actor, 'fabric_operations:operate', service.FACTORY, 'pmc-warehouse'),
        'can_manage': service.can(actor, 'fabric_warehouse:import', service.FACTORY, 'pmc-warehouse'),
        'can_read_purchase': service.can(actor, 'fabric_warehouse:read', service.FACTORY, 'pmc-warehouse'),
        'materials': [record_data(r) for r in records(db) if r.kind == 'MATERIAL' and r.status == 'ACTIVE'],
        'suppliers': [record_data(r) for r in records(db) if r.kind == 'SUPPLIER']}


@router.get('/pending-deliveries')
def pending_deliveries(factory_id: str, limit: int = Query(50, ge=1, le=50), offset: int = Query(0, ge=0),
                       db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    staff_access(db, actor, factory_id)
    from fastapi.responses import JSONResponse
    from app.services.material_handover_dashboard import pending_deliveries as report
    return JSONResponse(report(db, limit, offset), headers={'Cache-Control': 'no-store'})


@router.get('/issuers')
def issuers(factory_id: str, db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    staff_access(db, actor, factory_id, 'manage')
    return [service.issuer_out(r,db) for r in db.scalars(select(HandoverIssuer).where(HandoverIssuer.factory_id == service.FACTORY).order_by(HandoverIssuer.created_at.desc()))]


@router.post('/issuers')
def create_issuer(request: Request, payload: IssuerInput, db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    actor, _ = refresh_staff(request, db, payload.factory_id, 'manage')
    return service.create_issuer(db, actor, payload)


@router.post('/issuers/{identifier}/revoke')
def revoke_issuer(request: Request, identifier: str, payload: IssuerRevoke, db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    actor, _ = refresh_staff(request, db, payload.factory_id, 'manage')
    return service.revoke_issuer(db, actor, identifier, payload)


@router.post('/issuers/{identifier}/renew')
def renew_issuer(request: Request, identifier: str, payload: IssuerRenew, db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    actor,_=refresh_staff(request,db,payload.factory_id,'manage')
    from app.services.material_handover_suppliers import action
    return action(db,actor,identifier,payload,'RENEW')


@router.post('/issuers/{identifier}/bind')
def bind_issuer(request: Request, identifier: str, payload: IssuerBind, db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    actor,_=refresh_staff(request,db,payload.factory_id,'manage')
    from app.services.material_handover_suppliers import action
    return action(db,actor,identifier,payload,'BIND')


@router.get('/monthly')
def monthly(factory_id: str, month: str = Query(...,max_length=7), supplier_id: str = Query('',max_length=64),
            db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    from app.services.material_handover_monthly import report
    return report(db,staff_access(db,actor,factory_id),month,supplier_id)


@router.get('/monthly/export')
def monthly_export(factory_id: str, month: str = Query(...,max_length=7), supplier_id: str = Query('',max_length=64),
                   db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    from app.services.material_handover_monthly import report,export_xlsx
    result=report(db,staff_access(db,actor,factory_id),month,supplier_id)
    return response_file(export_xlsx(result),month+'-供应商数量对账.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@router.get('/documents')
def documents(factory_id: str, limit: int = Query(50, ge=1, le=50), offset: int = Query(0, ge=0),
              status: Literal['ALL', 'DRAFT', 'CONFIRMED', 'VOID'] = 'ALL', search: str = Query('', max_length=200),
              kind: Literal['ALL', 'DELIVERY', 'ISSUE'] = 'ALL', supplier_id: str = Query('', max_length=64),
              db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    return list_documents(db, staff_access(db, actor, factory_id), limit, offset, status, search, kind, supplier_id)


async def uploaded(file):
    from app.services.material_handover_parser import validate_file, MAX_BYTES
    content = await file.read(MAX_BYTES + 1)
    from app.services.document_tools.document_ir import ToolError
    try:
        name = validate_file(file.filename or '', content)
    except ToolError as error:
        raise HTTPException(422, str(error)) from error
    return name, content


@router.post('/documents/upload')
async def upload(request: Request, factory_id: str = Form(...), request_id: UUID = Form(...), file: UploadFile = File(...),
                 db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    access = staff_access(db, actor, factory_id, 'operate')
    name, content = await uploaded(file)
    old = service.duplicate_upload(db, access, hashlib.sha256(content).hexdigest())
    if old:
        return service.output(db, old)
    db.rollback()
    extraction = await run_in_threadpool(files.extract, name, content)
    _, access = refresh_staff(request, db, factory_id)
    return service.create_document(db, access, name, content, extraction, request_id)


@router.post('/scan')
def scan(payload: ScanInput, db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    return service.scan(db, staff_access(db, actor, payload.factory_id), payload.code,
                        with_receipt_observations=True, with_receipt_review=receipts.can_review(actor))


@router.get('/documents/{identifier}')
def detail(identifier: str, factory_id: str, db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    return service.output(db, service.document(db, staff_access(db, actor, factory_id), identifier),
                          with_receipt_observations=True, with_receipt_review=receipts.can_review(actor))


@router.get('/documents/{identifier}/source')
def source(identifier: str, factory_id: str, db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    return source_response(db, staff_access(db, actor, factory_id), identifier)


@router.get('/documents/{identifier}/purchase-sources')
def purchase_sources(identifier: str, factory_id: str, db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    from app.services.material_handover_procurement import source_choices
    row = service.document(db, staff_access(db, actor, factory_id), identifier)
    return source_choices(db, actor, row)


@router.get('/documents/{identifier}/qr')
def qr(identifier: str, factory_id: str, db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    access = staff_access(db, actor, factory_id)
    row = service.document(db, access, identifier)
    service.require_preparer(db, access, row)
    return response_file(service.qr_svg(row), row.id + '.svg', 'image/svg+xml')


@router.put('/documents/{identifier}')
def save(request: Request, identifier: str, payload: DocumentSave, factory_id: str, db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    _, access = refresh_staff(request, db, factory_id)
    return service.save_document(db, access, identifier, payload)


@router.post('/documents/{identifier}/actions/{action}')
def action(request: Request, identifier: str, action: Literal['confirm', 'void'], payload: DocumentAction,
           factory_id: str, db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    _, access = refresh_staff(request, db, factory_id)
    return (service.confirm if action == 'confirm' else service.void)(db, access, identifier, payload)


@router.post('/documents/{identifier}/post')
def post(request: Request, identifier: str, payload: PostingInput, db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    actor, _ = refresh_staff(request, db, payload.factory_id)
    return service.post(db, actor, identifier, payload)


@router.post('/documents/{identifier}/rejection-followup')
def rejection_followup(request: Request, identifier: str, payload: RejectionFollowupInput,
                       db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    actor, _ = refresh_staff(request, db, payload.factory_id)
    return rejections.record_followup(db, actor, identifier, payload)


@router.post('/documents/{identifier}/link-receipt')
def link_receipt(request: Request, identifier: str, payload: ReceiptLinkInput, db: Session = Depends(get_db),
                 actor: AuthContext = Depends(get_current_user)):
    actor, _ = refresh_staff(request, db, payload.factory_id)
    return receipts.link_receipt(db, actor, identifier, payload)


@router.post('/documents/{identifier}/unlink-receipt')
def unlink_receipt(request: Request, identifier: str, payload: ReceiptUnlinkInput, db: Session = Depends(get_db),
                   actor: AuthContext = Depends(get_current_user)):
    actor, _ = refresh_staff(request, db, payload.factory_id)
    return receipts.unlink_receipt(db, actor, identifier, payload)


@router.get('/receipts/{operation_id}/purchase-review')
def receipt_purchase_review(operation_id: str, factory_id: str, db: Session = Depends(get_db),
                            actor: AuthContext = Depends(get_current_user)):
    staff_access(db, actor, factory_id)
    return purchase_review.purchase_review(db, actor, operation_id)


@router.post('/receipts/{operation_id}/purchase-link')
def receipt_purchase_link(request: Request, operation_id: str, payload: ReceiptPurchaseLinkInput,
                          db: Session = Depends(get_db), actor: AuthContext = Depends(get_current_user)):
    actor, _ = refresh_staff(request, db, payload.factory_id)
    return purchase_review.link_purchase(db, actor, operation_id, payload)


@router.get('/external/context')
def external_context(x_handover_key: str = Header(default=''), db: Session = Depends(get_db)):
    access = service.external(db, x_handover_key)
    return service.issuer_out(db.get(HandoverIssuer, access.issuer_id),db)


@router.get('/external/monthly')
def external_monthly(month: str = Query(...,max_length=7), supplier_id: str = Query('',max_length=64),
                     x_handover_key: str = Header(default=''), db: Session = Depends(get_db)):
    service.inventory.procurement.lock_factory(db)
    from app.services.material_handover_monthly import report
    return report(db,service.external(db,x_handover_key),month,supplier_id)


@router.get('/external/monthly/export')
def external_monthly_export(month: str = Query(...,max_length=7), x_handover_key: str = Header(default=''), db: Session = Depends(get_db)):
    service.inventory.procurement.lock_factory(db)
    from app.services.material_handover_monthly import report,export_xlsx
    result=report(db,service.external(db,x_handover_key),month)
    return response_file(export_xlsx(result),month+'-本供应商数量对账.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@router.get('/external/documents')
def external_documents(limit: int = Query(50, ge=1, le=50), offset: int = Query(0, ge=0),
                       status: Literal['ALL', 'DRAFT', 'CONFIRMED', 'VOID'] = 'ALL', search: str = Query('', max_length=200),
                       kind: Literal['ALL', 'DELIVERY', 'ISSUE'] = 'ALL',
                       x_handover_key: str = Header(default=''), db: Session = Depends(get_db)):
    return list_documents(db, service.external(db, x_handover_key), limit, offset, status, search, kind)


@router.post('/external/documents/upload')
async def external_upload(request_id: UUID = Form(...), file: UploadFile = File(...), x_handover_key: str = Header(default=''), db: Session = Depends(get_db)):
    access = service.external(db, x_handover_key)
    name, content = await uploaded(file)
    old = service.duplicate_upload(db, access, hashlib.sha256(content).hexdigest())
    if old:
        return public_result(service.output(db, old))
    db.rollback()
    extraction = await run_in_threadpool(files.extract, name, content)
    service.inventory.procurement.lock_factory(db)
    access = service.external(db, x_handover_key)
    return public_result(service.create_document(db, access, name, content, extraction, request_id))


@router.get('/external/documents/{identifier}')
def external_detail(identifier: str, x_handover_key: str = Header(default=''), db: Session = Depends(get_db)):
    return public_result(service.output(db, service.document(db, service.external(db, x_handover_key), identifier)))


@router.get('/external/documents/{identifier}/{file_kind}')
def external_file(identifier: str, file_kind: Literal['source', 'qr'], x_handover_key: str = Header(default=''), db: Session = Depends(get_db)):
    access = service.external(db, x_handover_key)
    if file_kind == 'source':
        return source_response(db, access, identifier)
    row = service.document(db, access, identifier)
    return response_file(service.qr_svg(row), row.id + '.svg', 'image/svg+xml')


@router.put('/external/documents/{identifier}')
def external_save(identifier: str, payload: DocumentSave, x_handover_key: str = Header(default=''), db: Session = Depends(get_db)):
    service.inventory.procurement.lock_factory(db)
    return public_result(service.save_document(db, service.external(db, x_handover_key), identifier, payload))


@router.post('/external/documents/{identifier}/{action}')
def external_action(identifier: str, action: Literal['confirm', 'void'], payload: DocumentAction, x_handover_key: str = Header(default=''), db: Session = Depends(get_db)):
    service.inventory.procurement.lock_factory(db)
    return public_result((service.confirm if action == 'confirm' else service.void)(db, service.external(db, x_handover_key), identifier, payload))
