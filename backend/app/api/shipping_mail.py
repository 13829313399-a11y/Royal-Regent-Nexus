"""Shipping management endpoints: mail preview/import, manual entry and task state."""
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from urllib.parse import quote

from app.db import get_db
from app.services import shipping_mail_service as service
from app.services import shipping_mail_account_service as accounts
from app.services import shipping_loading
from app.services import shipping_exports
from app.services import shipping_zuru
from app.services import shipping_truck
from app.services import shipping_bulk_truck
from app.services import shipping_supplement
from app.services import shipping_customs
from app.services import shipping_schedule_import
from app.services import shipping_autogen
from app.services import shipping_product_history
from app.services.auth import AuthContext, get_current_user
from app.models.shipping_mail import ShippingTask

router = APIRouter(prefix='/api/shipping', tags=['shipping'])
Db = Annotated[Session, Depends(get_db)]
User = Annotated[AuthContext, Depends(get_current_user)]

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_FILES = 20


class ConfirmRequest(BaseModel):
    factory_id: str
    item_ids: list[str] = Field(min_length=1)
    fields: dict = Field(default_factory=dict)


class ManualTaskRequest(BaseModel):
    factory_id: str
    fields: dict
    items: list[dict] = Field(default_factory=list)
    warehouse_trips: list[dict] | None = None
    received_at: str = ''


class StatusRequest(BaseModel):
    factory_id: str
    status: str


class MailAccountRequest(BaseModel):
    factory_id: str
    host: str
    port: int = 993
    username: str
    password: str = ''
    use_ssl: bool = True
    folder: str = 'INBOX'
    enabled: bool = True


class MailTestRequest(BaseModel):
    factory_id: str
    password: str = ''


class LoadingDraftRequest(BaseModel):
    factory_id: str
    task_id: str


class LoadingExportRequest(BaseModel):
    factory_id: str
    taskId: str = ''
    header: dict
    lines: list[dict] = Field(default_factory=list)


class ZuruExportRequest(BaseModel):
    factory_id: str
    taskId: str = ''
    header: dict
    lines: list[dict] = Field(default_factory=list)


@router.post('/mail/preview')
def preview_mail(
    db: Db, user: User,
    factory_id: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
):
    raw = _read(file)
    return service.preview(factory_id, file.filename or 'upload.bin', raw, user)


@router.post('/mail/batches')
def create_batch(
    db: Db, user: User,
    factory_id: Annotated[str, Form()],
    files: Annotated[list[UploadFile], File()],
):
    if len(files) > MAX_FILES:
        raise HTTPException(422, f'一次最多上传 {MAX_FILES} 封邮件')
    payload = [(file.filename or f'mail-{index}.eml', _read(file)) for index, file in enumerate(files)]
    return service.create_batch(db, user, factory_id, payload)


@router.get('/mail/batches')
def list_batches(db: Db, user: User, factory_id: str = Query(...)):
    return {'batches': service.list_batches(db, user, factory_id)}


@router.get('/mail/batches/{batch_id}')
def batch_detail(db: Db, user: User, batch_id: str, factory_id: str = Query(...)):
    return service.batch_detail(db, user, batch_id, factory_id)


@router.post('/mail/batches/{batch_id}/confirm')
def confirm_batch(db: Db, user: User, batch_id: str, body: ConfirmRequest):
    return service.confirm_batch(db, user, batch_id, body.factory_id, body.item_ids, body.fields)


@router.delete('/mail/batches/{batch_id}')
def delete_mail_batch(db: Db, user: User, batch_id: str, factory_id: str = Query(...)):
    return service.delete_batch(db, user, batch_id, factory_id)


@router.get('/mail/account')
def mail_account(db: Db, user: User, factory_id: str = Query(...)):
    service.authorize(user, factory_id, 'read')
    return {'account': accounts.account_payload(accounts.get_account(db, factory_id))}


@router.put('/mail/account')
def save_mail_account(db: Db, user: User, body: MailAccountRequest):
    return {'account': accounts.save_account(db, user, body.model_dump())}


@router.post('/mail/account/test')
def test_mail_account(db: Db, user: User, body: MailTestRequest):
    return accounts.test_account(db, user, body.factory_id, body.password)


@router.post('/mail/account/sync')
def sync_mail_account(db: Db, user: User, factory_id: str = Query(...)):
    service.authorize(user, factory_id, 'import')
    return {'run': accounts.sync_account(db, factory_id, trigger='manual')}


@router.get('/mail/account/runs')
def mail_account_runs(db: Db, user: User, factory_id: str = Query(...)):
    return {'runs': accounts.list_runs(db, user, factory_id)}


@router.post('/loading-sheets/draft')
def loading_draft(db: Db, user: User, body: LoadingDraftRequest):
    return shipping_loading.draft(db, user, body.factory_id, body.task_id)


@router.get('/loading-sheets/schedule-lines')
def loading_schedule_lines(db: Db, user: User, factory_id: str = Query(...), q: str = Query(...)):
    return shipping_loading.schedule_lines(db, user, factory_id, q)


@router.post('/loading-sheets/export')
def loading_export(db: Db, user: User, body: LoadingExportRequest):
    filename, content = shipping_loading.export_sheet(db, user, body.factory_id, body.model_dump())
    shipping_exports.save_import_file('so_dk', filename, content)
    headers = {'Content-Disposition': f"attachment; filename*=UTF-8''{quote(filename)}"}
    return Response(content=content, media_type='application/vnd.ms-excel', headers=headers)


@router.get('/customs-docs')
def customs_docs(db: Db, user: User, factory_id: str = Query(...)):
    return shipping_customs.list_docs(db, user, factory_id)


@router.post('/customs-docs/read')
def customs_docs_read(db: Db, user: User, body: MailTestRequest):
    return shipping_customs.mark_read(db, user, body.factory_id)


@router.post('/customs-docs/{doc_id}/save')
def customs_doc_save(db: Db, user: User, doc_id: str, factory_id: str = Query(...)):
    return shipping_customs.save_doc(db, user, factory_id, doc_id)


@router.delete('/customs-docs/{doc_id}')
def customs_doc_delete(db: Db, user: User, doc_id: str, factory_id: str = Query(...)):
    return shipping_customs.delete_doc(db, user, factory_id, doc_id)


@router.post('/customs-docs/{doc_id}/open')
def customs_doc_open(db: Db, user: User, doc_id: str, factory_id: str = Query(...)):
    return shipping_customs.open_doc(db, user, factory_id, doc_id)


@router.get('/customs-docs/{doc_id}/download')
def customs_doc_download(db: Db, user: User, doc_id: str, factory_id: str = Query(...)):
    filename, content = shipping_customs.get_content(db, user, factory_id, doc_id)
    return Response(
        content=content,
        media_type='application/octet-stream',
        headers={'Content-Disposition': f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.post('/loading-sheets/supplement/draft')
def supplement_draft(db: Db, user: User, body: LoadingDraftRequest):
    return shipping_supplement.draft_supplement(db, user, body.factory_id, body.task_id)


@router.post('/loading-sheets/supplement/export')
def supplement_export(db: Db, user: User, body: LoadingExportRequest):
    service.authorize(user, body.factory_id, 'read')
    content = shipping_supplement.render_supplement_xlsx(body.model_dump())
    name = f"{body.header.get('to') or 'PLAYMATE'}补料单.xlsx"
    shipping_exports.save_import_file('supplement', name, content)
    return Response(
        content=content,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f"attachment; filename*=UTF-8''{quote(name)}"},
    )


@router.post('/loading-sheets/bulk-truck/draft')
def bulk_truck_draft(db: Db, user: User, body: LoadingDraftRequest):
    return shipping_bulk_truck.draft_bulk(db, user, body.factory_id, body.task_id)


@router.post('/loading-sheets/bulk-truck/export')
def bulk_truck_export(db: Db, user: User, body: LoadingExportRequest):
    service.authorize(user, body.factory_id, 'read')
    name = f"{body.header.get('tableName') or '2026年盐田散货'}.xlsx"
    content = shipping_bulk_truck.render_bulk_xlsx(body.model_dump())
    shipping_exports.save_import_file('truck_bulk', name, content)
    return Response(
        content=content,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f"attachment; filename*=UTF-8''{quote(name)}"},
    )


@router.post('/loading-sheets/truck/draft')
def truck_draft(db: Db, user: User, body: LoadingDraftRequest):
    return shipping_truck.draft_truck(db, user, body.factory_id, body.task_id)


@router.post('/loading-sheets/truck/export')
def truck_export(db: Db, user: User, body: LoadingExportRequest):
    service.authorize(user, body.factory_id, 'read')
    name = f"{body.header.get('tableName') or '客上车'}.xls"
    content = shipping_truck.render_truck_xls(body.model_dump())
    shipping_exports.save_import_file('truck_buzzbee', name, content)
    return Response(
        content=content,
        media_type='application/vnd.ms-excel',
        headers={'Content-Disposition': f"attachment; filename*=UTF-8''{quote(name)}"},
    )


@router.post('/loading-sheets/zuru/draft')
def zuru_draft(db: Db, user: User, body: LoadingDraftRequest):
    return shipping_zuru.draft_zuru(db, user, body.factory_id, body.task_id)


@router.post('/loading-sheets/zuru/export')
def zuru_export(db: Db, user: User, body: ZuruExportRequest):
    service.authorize(user, body.factory_id, 'read')
    filename = shipping_loading.sheet_xlsx_filename(body.header)
    content = shipping_zuru.render_zuru_xlsx(body.model_dump())
    shipping_exports.save_import_file('so_zuru', filename, content)
    return Response(
        content=content,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.get('/loading-sheets')
def loading_sheets(db: Db, user: User, factory_id: str = Query(...)):
    return {'sheets': shipping_loading.list_sheets(db, user, factory_id)}


@router.post('/product-history/import')
def import_product_history(
    db: Db, user: User,
    factory_id: Annotated[str, Form()],
    customer: Annotated[str, Form()],
    files: Annotated[list[UploadFile], File()],
):
    if len(files) > MAX_FILES:
        raise HTTPException(422, f'一次最多上传 {MAX_FILES} 个文件')
    payload = [(file.filename or f'file-{index}.xlsx', _read(file)) for index, file in enumerate(files)]
    return shipping_product_history.import_files(db, user, factory_id, customer, payload)


@router.get('/product-history')
def product_history(db: Db, user: User, factory_id: str = Query(...), customer: str = Query('')):
    return {'records': shipping_product_history.list_records(db, user, factory_id, customer)}


class GenerateDocsRequest(BaseModel):
    factory_id: str
    task_id: str
    modules: list[str] = Field(default_factory=list)




@router.post('/generated-docs/generate')
def generated_docs_generate(db: Db, user: User, body: GenerateDocsRequest):
    service.authorize(user, body.factory_id, 'write')
    mapping = {
        'so': {'so_dk'},
        'truck': {'truck_buzzbee', 'truck_bulk'},
        'supplement': {'supplement'},
    }
    selected: set[str] = set()
    for module in body.modules:
        selected.update(mapping.get(module, set()))
    if not selected:
        return {'docs': []}
    return {'docs': shipping_autogen.generate_for_task(db, user, body.factory_id, body.task_id, selected)}


@router.get('/generated-docs')
def generated_docs(db: Db, user: User, factory_id: str = Query(...), module: str = Query('')):
    return {'docs': shipping_autogen.list_docs(db, user, factory_id, module)}


@router.post('/generated-docs/{doc_id}/save')
def generated_doc_save(db: Db, user: User, doc_id: str, factory_id: str = Query(...)):
    return shipping_autogen.save_doc(db, user, factory_id, doc_id)


@router.delete('/generated-docs/{doc_id}')
def generated_doc_delete(db: Db, user: User, doc_id: str, factory_id: str = Query(...)):
    return shipping_autogen.delete_doc(db, user, factory_id, doc_id)


@router.post('/generated-docs/{doc_id}/open')
def generated_doc_open(db: Db, user: User, doc_id: str, factory_id: str = Query(...)):
    return shipping_autogen.open_doc(db, user, factory_id, doc_id)


@router.get('/generated-docs/{doc_id}')
def generated_doc_detail(db: Db, user: User, doc_id: str, factory_id: str = Query(...)):
    return shipping_autogen.get_doc(db, user, factory_id, doc_id)


@router.patch('/generated-docs/{doc_id}')
def generated_doc_update(db: Db, user: User, doc_id: str, body: dict):
    return shipping_autogen.update_doc(
        db, user, str(body.get('factory_id') or ''), doc_id,
        body.get('header') or {}, body.get('lines') or [],
    )


@router.get('/generated-docs/{doc_id}/download')
def generated_doc_download(db: Db, user: User, doc_id: str, factory_id: str = Query(...)):
    filename, content = shipping_autogen.download(db, user, factory_id, doc_id)
    media = 'application/vnd.ms-excel' if filename.endswith('.xls') else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    return Response(
        content=content,
        media_type=media,
        headers={'Content-Disposition': f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.post('/schedule-import')
def schedule_import(db: Db, user: User, factory_id: str = Query(...), history: bool = Query(False)):
    service.authorize(user, factory_id, 'write')
    return shipping_schedule_import.import_factory_schedule(db, factory_id, include_history=history)


@router.get('/schedule/rows')
def schedule_rows(db: Db, user: User, factory_id: str = Query(...)):
    return service.schedule_rows(db, user, factory_id)


@router.get('/schedule-import/status')
def schedule_import_status(db: Db, user: User, factory_id: str = Query(...)):
    service.authorize(user, factory_id, 'read')
    rows = db.scalars(select(ShippingTask).where(
        ShippingTask.factory_id == factory_id, ShippingTask.source == 'schedule',
    )).all()
    return {'tasks': len(rows)}


@router.post('/tasks')
def create_task(db: Db, user: User, body: ManualTaskRequest):
    return service.create_manual_task(db, user, body.model_dump())


@router.get('/tasks')
def list_tasks(db: Db, user: User, factory_id: str = Query(...), status: str = Query(''), q: str = Query('')):
    return {'tasks': service.list_tasks(db, user, factory_id, status or None, q)}


@router.post('/tasks/{task_id}/status')
def update_status(db: Db, user: User, task_id: str, body: StatusRequest):
    return service.update_task_status(db, user, task_id, body.factory_id, body.status)


def _read(file: UploadFile) -> bytes:
    raw = file.file.read(MAX_FILE_BYTES + 1)
    if len(raw) > MAX_FILE_BYTES:
        raise HTTPException(413, f'{file.filename} 超过 20 MB，请拆分后再上传')
    if not raw:
        raise HTTPException(422, f'{file.filename} 是空文件')
    return raw
