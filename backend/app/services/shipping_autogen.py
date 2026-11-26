"""Auto-generate SO / truck / supplement sheets when an email task is confirmed."""
import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select

from app.models.shipping_mail import ShippingGeneratedDoc, ShippingMailItem, ShippingTask
from app.services.auth import AuthContext
from app.services.shipping_mail_service import task_fields
from app.services import shipping_bulk_truck, shipping_loading, shipping_supplement, shipping_truck, shipping_zuru
from app.services import shipping_exports


def _enrich_payload(db, row: ShippingGeneratedDoc, payload: dict) -> dict:
    """Fill legacy generated-doc headers from the linked mail task when fields are missing."""
    header = dict(payload.get('header') or {})
    task = db.get(ShippingTask, row.task_id) if row.task_id else None
    if task is not None:
        try:
            fields = task_fields(db, task)
        except Exception:  # noqa: BLE001 - enrichment is best effort
            fields = {}
        if not str(header.get('contractNo') or '').strip() and fields.get('contract_no'):
            header['contractNo'] = str(fields.get('contract_no'))
        if not str(header.get('poNo') or '').strip() and fields.get('po_no'):
            header['poNo'] = str(fields.get('po_no'))
        if not str(header.get('brandName') or '').strip():
            header['brandName'] = str(fields.get('brand') or task.customer or '')
        if not str(header.get('brandNote') or '').strip():
            header['brandNote'] = header['brandName']
        if not str(header.get('consignee') or '').strip():
            header['consignee'] = str(fields.get('consignee') or '')
        if str(header.get('consignee') or '').strip() and str(header.get('consignee')).strip() == str(task.customer or '').strip():
            header['consignee'] = ''
        if not str(header.get('country') or '').strip() and fields.get('destination_country'):
            header['country'] = str(fields.get('destination_country'))
    port = str(header.get('originPort') or '').strip()
    if not port or 'FLAG:' in port.upper() or '码头' in port:
        header['originPort'] = '盐田'
    payload = {**payload, 'header': header}
    return payload


def _now() -> str:
    return datetime.now().isoformat(timespec='seconds')


def _modules(task: ShippingTask) -> list[str]:
    modules = ['so_dk', 'supplement']
    port = (task.port or '').strip()
    customer = (task.customer or '').upper()
    if 'BUZZBEE' in customer:
        modules.append('truck_buzzbee')
    elif '盐田' in port or not port:
        modules.append('truck_bulk')
    else:
        modules.append('truck_bulk')
    return modules


def _draft(db, user: AuthContext, factory_id: str, task_id: str, module: str) -> dict:
    if module == 'so_dk':
        return shipping_loading.draft(db, user, factory_id, task_id)
    if module == 'so_zuru':
        return shipping_zuru.draft_zuru(db, user, factory_id, task_id)
    if module == 'truck_buzzbee':
        return shipping_truck.draft_truck(db, user, factory_id, task_id)
    if module == 'truck_bulk':
        return shipping_bulk_truck.draft_bulk(db, user, factory_id, task_id)
    return shipping_supplement.draft_supplement(db, user, factory_id, task_id)


def _filename(module: str, so_number: str, header: dict | None = None) -> str:
    if module == 'so_dk':
        return shipping_loading.sheet_filename(header or {})
    if module == 'so_zuru' and header:
        return shipping_loading.sheet_xlsx_filename(header)
    suffix = {
        'so_dk': ('SO出货表_DK', '.xls'),
        'so_zuru': ('SO出货表_ZURU', '.xlsx'),
        'truck_buzzbee': ('车的排出货表_客上车', '.xls'),
        'truck_bulk': ('车的排出货表_盐田散货', '.xlsx'),
        'supplement': ('补料单', '.xlsx'),
    }[module]
    return f'{suffix[0]}_{so_number or "未命名"}{suffix[1]}'


def filing_code_filename(
    header: dict, lines: list, ext: str = '.xlsx', *,
    db=None, factory_id: str = '', task_id: str = '', index: dict | None = None,
) -> str:
    """Build a filename solely from resolved unique filing/product codes."""
    codes = shipping_loading.resolve_filing_codes(
        db, factory_id, header or {}, lines or [], task_id=task_id, index=index,
    )
    return f"{'_'.join(codes)}{ext}" if codes else ''


def _resolved_doc_filename(
    module: str, raw_filename: str, header: dict, lines: list, *,
    db=None, factory_id: str = '', task_id: str = '', index: dict | None = None,
) -> str:
    ext = Path(raw_filename or '').suffix or (
        '.xls' if module in {'so_dk', 'truck_buzzbee', 'truck_export'} else '.xlsx'
    )
    return filing_code_filename(
        header, lines, ext, db=db, factory_id=factory_id, task_id=task_id, index=index,
    ) or raw_filename


def _render_content(module: str, draft: dict) -> bytes:
    if module == 'so_dk':
        return shipping_loading.render_xls(draft)
    if module == 'so_zuru':
        return shipping_zuru.render_zuru_xlsx(draft)
    if module == 'truck_buzzbee':
        return shipping_truck.render_truck_xls(draft)
    if module == 'truck_bulk' or module == 'truck_export':
        return shipping_bulk_truck.render_bulk_xlsx(draft)
    if module == 'supplement':
        return shipping_supplement.render_supplement_xlsx(draft)
    return b''


def record_export(db, user: AuthContext, factory_id: str, task_id: str, module: str,
                  filename: str, header: dict, lines: list[dict]) -> str:
    row = db.scalar(select(ShippingGeneratedDoc).where(
        ShippingGeneratedDoc.factory_id == factory_id,
        ShippingGeneratedDoc.task_id == task_id,
        ShippingGeneratedDoc.module == module,
    ))
    if row is None:
        row = ShippingGeneratedDoc(
            id=f'gen-{uuid4().hex}', factory_id=factory_id, task_id=task_id, module=module,
            filename=filename, header_json='{}', lines_json='[]',
            created_at=_now(), created_by=user.id,
        )
        db.add(row)
    row.filename = filename
    row.header_json = json.dumps(header, ensure_ascii=False)
    row.lines_json = json.dumps(lines, ensure_ascii=False)
    row.created_at = _now()
    row.created_by = user.id
    db.commit()
    return row.id


def generate_for_task(db, user: AuthContext, factory_id: str, task_id: str,
                      modules: set[str] | None = None, replace: bool = False) -> list[dict]:
    task = db.scalar(select(ShippingTask).where(
        ShippingTask.id == task_id, ShippingTask.factory_id == factory_id,
    ))
    if task is None:
        return []
    created = []
    for module in _modules(task):
        if modules and module not in modules:
            continue
        existing = db.scalar(select(ShippingGeneratedDoc).where(
            ShippingGeneratedDoc.task_id == task_id, ShippingGeneratedDoc.module == module,
        ))
        if existing is not None and not replace:
            continue
        try:
            draft = _draft(db, user, factory_id, task_id, module)
        except Exception:  # noqa: BLE001 - one template must not block the others
            continue
        header = draft.get('header') or {}
        lines = draft.get('lines') or []
        filename = _resolved_doc_filename(
            module, _filename(module, task.so_number, header), header, lines,
            db=db, factory_id=factory_id, task_id=task_id,
        )
        if existing is not None:
            existing.filename = filename
            existing.header_json = json.dumps(draft.get('header') or {}, ensure_ascii=False)
            existing.lines_json = json.dumps(draft.get('lines') or [], ensure_ascii=False)
            existing.created_at = _now()
            existing.created_by = user.id
            doc = existing
        else:
            doc = ShippingGeneratedDoc(
                id=f'gen-{uuid4().hex}', factory_id=factory_id, task_id=task_id, module=module,
                filename=filename, header_json=json.dumps(draft.get('header') or {}, ensure_ascii=False),
                lines_json=json.dumps(draft.get('lines') or [], ensure_ascii=False),
                created_at=_now(), created_by=user.id,
            )
            db.add(doc)
        try:
            shipping_exports.save_import_file(module, doc.filename, _render_content(module, draft))
        except Exception:  # noqa: BLE001 - export copy must not block generation
            pass
        created.append({'module': module, 'filename': doc.filename, 'id': doc.id})
    db.commit()
    return created


def _email_name(db, task_id: str) -> str:
    task = db.get(ShippingTask, task_id) if task_id else None
    if task is None or not task.mail_item_id:
        return ''
    item = db.get(ShippingMailItem, task.mail_item_id)
    if item is None:
        return ''
    return str(item.subject or item.filename or '').strip()


def list_docs(db, user: AuthContext, factory_id: str, module_prefix: str = '') -> list[dict]:
    from app.services.shipping_mail_service import authorize
    authorize(user, factory_id, 'read')
    query = select(ShippingGeneratedDoc).where(ShippingGeneratedDoc.factory_id == factory_id)
    if module_prefix == 'so':
        query = query.where(ShippingGeneratedDoc.module.in_(('so_dk', 'so_zuru')))
    elif module_prefix == 'truck':
        query = query.where(ShippingGeneratedDoc.module.in_(('truck_buzzbee', 'truck_bulk')))
    elif module_prefix:
        query = query.where(ShippingGeneratedDoc.module == module_prefix)
    rows = db.scalars(query.order_by(ShippingGeneratedDoc.created_at.desc()).limit(100)).all()
    index = shipping_loading.build_filing_code_index(db, factory_id)
    result = []
    for row in rows:
        try:
            header = json.loads(row.header_json or '{}')
            lines = json.loads(row.lines_json or '[]')
        except (TypeError, ValueError):
            header, lines = {}, []
        brand = str(header.get('brandName') or header.get('brandNote') or header.get('brand') or '')
        if not brand and isinstance(lines, list):
            brand = next((str((line or {}).get('brand') or '') for line in lines if (line or {}).get('brand')), '')
        if not brand and row.task_id:
            task = index['task_by_id'].get(row.task_id) or db.get(ShippingTask, row.task_id)
            brand = str(task.customer or '') if task is not None else ''
        filename = _resolved_doc_filename(
            row.module, row.filename, header, lines,
            db=db, factory_id=factory_id, task_id=row.task_id, index=index,
        )
        result.append({
            'id': row.id, 'module': row.module, 'filename': filename,
            'email_name': _email_name(db, row.task_id),
            'brand_name': brand,
            'task_id': row.task_id, 'created_at': row.created_at,
        })
    return result


def get_doc(db, user: AuthContext, factory_id: str, doc_id: str) -> dict:
    from app.services.shipping_mail_service import authorize
    authorize(user, factory_id, 'read')
    row = db.get(ShippingGeneratedDoc, doc_id)
    if row is None or row.factory_id != factory_id:
        raise HTTPException(404, '生成文件不存在')
    payload = _enrich_payload(db, row, {
        'header': json.loads(row.header_json or '{}'),
        'lines': json.loads(row.lines_json or '[]'),
    })
    filename = _resolved_doc_filename(
        row.module, row.filename, payload['header'], payload['lines'],
        db=db, factory_id=factory_id, task_id=row.task_id,
    )
    return {
        'id': row.id, 'module': row.module, 'filename': filename, 'task_id': row.task_id,
        'email_name': _email_name(db, row.task_id),
        'created_at': row.created_at,
        'header': payload['header'],
        'lines': payload['lines'],
    }


def update_doc(db, user: AuthContext, factory_id: str, doc_id: str, header: dict, lines: list[dict]) -> dict:
    from app.services.shipping_mail_service import authorize
    authorize(user, factory_id, 'write')
    row = db.get(ShippingGeneratedDoc, doc_id)
    if row is None or row.factory_id != factory_id:
        raise HTTPException(404, '生成文件不存在')
    row.header_json = json.dumps(header or {}, ensure_ascii=False)
    row.lines_json = json.dumps(lines or [], ensure_ascii=False)
    row.filename = _resolved_doc_filename(
        row.module, row.filename, header or {}, lines or [],
        db=db, factory_id=factory_id, task_id=row.task_id,
    )
    db.commit()
    return get_doc(db, user, factory_id, doc_id)


def download_with_path(
    db, user: AuthContext, factory_id: str, doc_id: str, *, archive: bool = True,
) -> tuple[str, bytes, str]:
    from app.services.shipping_mail_service import authorize
    authorize(user, factory_id, 'read')
    doc = db.scalar(select(ShippingGeneratedDoc).where(
        ShippingGeneratedDoc.id == doc_id, ShippingGeneratedDoc.factory_id == factory_id,
    ))
    if doc is None:
        from fastapi import HTTPException
        raise HTTPException(404, '文件不存在')
    payload = {
        'factory_id': factory_id, 'taskId': doc.task_id,
        'header': json.loads(doc.header_json or '{}'), 'lines': json.loads(doc.lines_json or '[]'),
    }
    payload = _enrich_payload(db, doc, payload)
    if doc.module == 'so_dk':
        content = shipping_loading.render_xls(payload)
    elif doc.module == 'so_zuru':
        content = shipping_zuru.render_zuru_xlsx(payload)
    elif doc.module == 'truck_buzzbee':
        content = shipping_truck.render_truck_xls(payload)
    elif doc.module == 'truck_bulk' or doc.module == 'truck_export':
        content = shipping_bulk_truck.render_bulk_xlsx(payload)
    else:
        content = shipping_supplement.render_supplement_xlsx(payload)
    filename = _resolved_doc_filename(
        doc.module, doc.filename, payload['header'], payload['lines'],
        db=db, factory_id=factory_id, task_id=doc.task_id,
    )
    saved_path = ''
    if archive:
        try:
            saved_path = shipping_exports.save_import_file(doc.module, filename, content)
        except Exception:  # noqa: BLE001 - the drop-folder copy is best effort
            saved_path = ''
    return filename, content, saved_path


def download(db, user: AuthContext, factory_id: str, doc_id: str, *, archive: bool = True) -> tuple[str, bytes]:
    filename, content, _ = download_with_path(db, user, factory_id, doc_id, archive=archive)
    return filename, content


def open_doc(db, user: AuthContext, factory_id: str, doc_id: str) -> dict:
    from app.services import file_open, shipping_exports
    filename, content, _ = download_with_path(db, user, factory_id, doc_id, archive=False)
    folder = shipping_exports.EXPORT_ROOT / shipping_exports.FOLDERS.get(
        db.scalar(select(ShippingGeneratedDoc).where(ShippingGeneratedDoc.id == doc_id)).module,
        '',
    )
    target = shipping_exports.build_so_target(folder, filename)
    if not target.exists():
        safe = shipping_exports._safe_name(filename)
        target = next((item for item in folder.glob(f'*年*月/{safe}') if item.exists()), target)
    if target.exists():
        path = file_open.open_path(str(target))
    else:
        saved = shipping_exports.save_import_file(
            db.scalar(select(ShippingGeneratedDoc).where(ShippingGeneratedDoc.id == doc_id)).module,
            filename, content,
        )
        path = file_open.open_path(saved) if saved and Path(saved).exists() else file_open.open_bytes(filename, content)
    return {'opened': True, 'path': path, 'filename': filename, 'sheets': file_open.workbook_preview(filename, content)}


def preview_doc(db, user: AuthContext, factory_id: str, doc_id: str) -> dict:
    from app.services.file_open import workbook_preview
    filename, content = download(db, user, factory_id, doc_id, archive=False)
    return {'opened': False, 'path': '', 'filename': filename, 'sheets': workbook_preview(filename, content)}


def delete_doc(db, user: AuthContext, factory_id: str, doc_id: str) -> dict:
    from app.services.shipping_mail_service import authorize
    authorize(user, factory_id, 'write')
    doc = db.scalar(select(ShippingGeneratedDoc).where(
        ShippingGeneratedDoc.id == doc_id, ShippingGeneratedDoc.factory_id == factory_id,
    ))
    if doc is None:
        from fastapi import HTTPException
        raise HTTPException(404, '文件不存在')
    db.delete(doc)
    db.commit()
    return {'deleted': True}


def save_doc(db, user: AuthContext, factory_id: str, doc_id: str) -> dict:
    from app.services.file_open import save_to_downloads
    filename, content = download(db, user, factory_id, doc_id)
    path = save_to_downloads(filename, content)
    return {'saved': True, 'path': path}
