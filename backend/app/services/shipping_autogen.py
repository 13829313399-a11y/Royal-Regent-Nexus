"""Auto-generate SO / truck / supplement sheets when an email task is confirmed."""
import json
from datetime import datetime
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select

from app.models.shipping_mail import ShippingGeneratedDoc, ShippingTask
from app.services.auth import AuthContext
from app.services import shipping_bulk_truck, shipping_loading, shipping_supplement, shipping_truck, shipping_zuru
from app.services import shipping_exports


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


def _render_content(module: str, draft: dict) -> bytes:
    if module == 'so_dk':
        return shipping_loading.render_xls(draft)
    if module == 'so_zuru':
        return shipping_zuru.render_zuru_xlsx(draft)
    if module == 'truck_buzzbee':
        return shipping_truck.render_truck_xls(draft)
    if module == 'truck_bulk':
        return shipping_bulk_truck.render_bulk_xlsx(draft)
    if module == 'supplement':
        return shipping_supplement.render_supplement_xlsx(draft)
    return b''


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
        filename = _filename(module, task.so_number, draft.get('header') or {})
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
    return [{
        'id': row.id, 'module': row.module, 'filename': row.filename,
        'task_id': row.task_id, 'created_at': row.created_at,
    } for row in rows]


def get_doc(db, user: AuthContext, factory_id: str, doc_id: str) -> dict:
    from app.services.shipping_mail_service import authorize
    authorize(user, factory_id, 'read')
    row = db.get(ShippingGeneratedDoc, doc_id)
    if row is None or row.factory_id != factory_id:
        raise HTTPException(404, '生成文件不存在')
    return {
        'id': row.id, 'module': row.module, 'filename': row.filename, 'task_id': row.task_id,
        'created_at': row.created_at,
        'header': json.loads(row.header_json or '{}'),
        'lines': json.loads(row.lines_json or '[]'),
    }


def update_doc(db, user: AuthContext, factory_id: str, doc_id: str, header: dict, lines: list[dict]) -> dict:
    from app.services.shipping_mail_service import authorize
    authorize(user, factory_id, 'write')
    row = db.get(ShippingGeneratedDoc, doc_id)
    if row is None or row.factory_id != factory_id:
        raise HTTPException(404, '生成文件不存在')
    row.header_json = json.dumps(header or {}, ensure_ascii=False)
    row.lines_json = json.dumps(lines or [], ensure_ascii=False)
    if row.module == 'so_dk':
        row.filename = shipping_loading.sheet_filename(header or {})
    elif row.module == 'so_zuru':
        row.filename = shipping_loading.sheet_xlsx_filename(header or {})
    db.commit()
    return get_doc(db, user, factory_id, doc_id)


def download(db, user: AuthContext, factory_id: str, doc_id: str) -> tuple[str, bytes]:
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
    if doc.module == 'so_dk':
        content = shipping_loading.render_xls(payload)
    elif doc.module == 'so_zuru':
        content = shipping_zuru.render_zuru_xlsx(payload)
    elif doc.module == 'truck_buzzbee':
        content = shipping_truck.render_truck_xls(payload)
    elif doc.module == 'truck_bulk':
        content = shipping_bulk_truck.render_bulk_xlsx(payload)
    else:
        content = shipping_supplement.render_supplement_xlsx(payload)
    try:
        shipping_exports.save_import_file(doc.module, doc.filename, content)
    except Exception:  # noqa: BLE001 - the drop-folder copy is best effort
        pass
    return doc.filename, content


def open_doc(db, user: AuthContext, factory_id: str, doc_id: str) -> dict:
    from app.services.file_open import open_bytes
    filename, content = download(db, user, factory_id, doc_id)
    path = open_bytes(filename, content)
    return {'opened': True, 'path': path}


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
