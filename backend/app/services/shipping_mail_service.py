"""Shipping mail import and task creation: factory-scoped, server-computed, no silent guesses."""
import json
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import or_, select

from app.models.shipping_mail import ShippingMailBatch, ShippingMailItem, ShippingTask
from app.services.auth import AuthContext, authorization_decision
from app.services.shipping_mail.fields import PARSER_VERSION
from app.services.shipping_mail.pipeline import parse_shipping_document, parse_shipping_email
from app.services.shipping_schedule import (
    ShippingRuleError,
    TruckCargo,
    TruckPlan,
    can_transition,
    resolve_planned_ship_date,
    truck_type_format_error,
    validate_warehouse_trips,
)

# 船务管理只对华兴、华登、华康 A/B/D 开放；华康 C 与集团不显示、也不允许直接写入。
SHIPPING_FACTORIES = ('huaxing', 'huadeng', 'huakang-a', 'huakang-b', 'huakang-d')
PERMISSION = {
    'read': 'shipping:read',
    'import': 'shipping:import',
    'confirm': 'shipping:confirm',
    'write': 'shipping:write',
}


def authorize(user: AuthContext, factory_id: str, action: str = 'read') -> None:
    if factory_id not in SHIPPING_FACTORIES:
        raise HTTPException(422, '船务管理目前只对华兴、华登、华康 A、华康 B、华康 D 开放')
    if not authorization_decision(user, PERMISSION['read'], factory_id)[0]:
        raise HTTPException(403, '没有该厂区船务管理的查看权限')
    if action != 'read' and not authorization_decision(user, PERMISSION[action], factory_id)[0]:
        raise HTTPException(403, '没有该厂区船务管理的相应操作权限')


def _enrich_product_names(db, factory_id: str, items: list[dict]) -> None:
    wanted = {str(item.get('product_code') or '').strip() for item in items if not item.get('product_name')}
    wanted.discard('')
    if not wanted:
        return
    lookup: dict[str, dict] = {}
    tasks = db.scalars(select(ShippingTask).where(
        ShippingTask.factory_id == factory_id,
        ShippingTask.source == 'schedule',
    )).all()
    for task in tasks:
        for item in _loads(task.items_json):
            if not isinstance(item, dict):
                continue
            code = str(item.get('product_code') or '').strip()
            if code in wanted and item.get('product_name'):
                lookup.setdefault(code, item)
    for item in items:
        if item.get('product_name'):
            continue
        match = lookup.get(str(item.get('product_code') or '').strip())
        if not match:
            continue
        for field in ('product_name', 'country', 'standard', 'brand'):
            if not item.get(field) and match.get(field):
                item[field] = match[field]


def _contract_key(value) -> str:
    return re.sub(r'/\d+$', '', str(value or '').strip()).lower()


def lookup_contract_items(db, factory_id: str, contract: str) -> tuple[list[dict], str]:
    """1) factory schedule first; 2) customer order ledger fallback."""
    key = _contract_key(contract)
    if not key:
        return [], ''
    items: list[dict] = []
    seen: set[tuple[str, str]] = set()
    tasks = db.scalars(select(ShippingTask).where(
        ShippingTask.factory_id == factory_id,
        ShippingTask.source == 'schedule',
    )).all()
    for task in tasks:
        for item in _loads(task.items_json):
            if not isinstance(item, dict):
                continue
            if _contract_key(item.get('contract_no')) != key:
                continue
            code = str(item.get('product_code') or '').strip()
            if (key, code) in seen:
                continue
            seen.add((key, code))
            items.append(item)
    if items:
        return items, 'factory_schedule'
    from app.models.customer_order_ledger import OrderLedgerLine
    lines = db.scalars(select(OrderLedgerLine).where(
        OrderLedgerLine.factory_id == factory_id,
        OrderLedgerLine.status == 'active',
    )).all()
    for line in lines:
        data = line.data if isinstance(line.data, dict) else {}
        if _contract_key(data.get('contract_no')) != key:
            continue
        code = str(line.product_no or '').strip()
        if (key, code) in seen:
            continue
        seen.add((key, code))
        items.append({
            'product_code': code,
            'product_name': data.get('product_name_zh') or data.get('product_name') or '',
            'quantity': line.quantity,
            'cartons': data.get('carton_count'),
            'coefficient': data.get('coefficient') or data.get('pack_qty'),
            'gross_weight': data.get('gross_weight'),
            'net_weight': data.get('net_weight'),
            'cbm': data.get('cbm'),
            'contract_no': data.get('contract_no') or line.reference_no,
            'customer_po': data.get('po_no'),
            'country': data.get('country'),
            'brand': data.get('brand') or data.get('brand_name') or '',
            'consignee': data.get('consignee'),
        })
    return items, ('customer_order_ledger' if items else '')


def preview(factory_id: str, filename: str, raw: bytes, user: AuthContext, db=None) -> dict:
    """Parse one uploaded file without persisting anything."""
    authorize(user, factory_id, 'import')
    filename = _decoded_filename(filename)
    if _is_email_message(raw, filename):
        parsed = parse_shipping_email(raw, filename)
    else:
        result = parse_shipping_document(raw, filename)
        parsed = {
            'filename': filename,
            'subject': '',
            'sender': '',
            'received_at': '',
            'fields': result['fields'],
            'items': result['items'],
            'attachments': [result],
            'warnings': result['warnings'],
            'rule_trace': [],
            'parser_version': result['parser_version'],
            'status': result['status'],
        }
    if db is not None and not parsed.get('items'):
        contract = str((parsed.get('fields') or {}).get('contract_no') or '').strip()
        if contract:
            found, source = lookup_contract_items(db, factory_id, contract)
            if found:
                parsed['items'] = found
                parsed.setdefault('warnings', []).append(
                    f'已按合同号 {contract} 从'
                    + ('工厂排期' if source == 'factory_schedule' else '厂区总排期')
                    + f'带出 {len(found)} 行货物明细'
                )
                parsed['cargo_source'] = source
    if db is not None and parsed.get('items'):
        _enrich_product_names(db, factory_id, parsed['items'])
    return parsed


def create_batch(db, user: AuthContext, factory_id: str, files: list[tuple[str, bytes]]) -> dict:
    authorize(user, factory_id, 'import')
    return create_batch_internal(db, factory_id, files, created_by=user.id, source='upload')


def create_batch_internal(
    db, factory_id: str, files: list[tuple[str, bytes]], *, created_by: str, source: str = 'upload',
) -> dict:
    """Persist one batch without authorization; callers must authorize first or be a system worker."""
    if not files:
        raise HTTPException(422, '请至少上传一封邮件')
    now = _now()
    batch = ShippingMailBatch(
        id=_new_id('batch'), factory_id=factory_id, source=source,
        filename=', '.join(name for name, _ in files)[:500], status='pending',
        total_count=0, parsed_count=0, failed_count=0, parser_version=PARSER_VERSION,
        created_by=created_by, created_at=now,
    )
    db.add(batch)
    db.flush()
    items = []
    seen = 0
    for filename, raw in files:
        item = _build_item(factory_id, batch.id, filename, raw, now)
        if item.fingerprint:
            duplicate = db.scalar(
                select(ShippingMailItem.id).where(
                    ShippingMailItem.factory_id == factory_id,
                    ShippingMailItem.fingerprint == item.fingerprint,
                )
            )
            if duplicate:
                seen += 1
                continue
        if not _loads(item.items_json):
            fields = _loads(item.fields_json)
            contract = str((fields or {}).get('contract_no') or '').strip()
            if contract:
                found, source = lookup_contract_items(db, factory_id, contract)
                if found:
                    item.items_json = _dump(found)
                    warnings = _loads(item.warnings_json)
                    warnings.append(
                        f'已按合同号 {contract} 从'
                        + ('工厂排期' if source == 'factory_schedule' else '厂区总排期')
                        + f'带出 {len(found)} 行货物明细'
                    )
                    item.warnings_json = _dump(warnings)
        item_list = _loads(item.items_json)
        if item_list:
            _enrich_product_names(db, factory_id, item_list)
            item.items_json = _dump(item_list)
        db.add(item)
        items.append(item)
        if item.filename.lower().endswith('.eml') or _is_email_message(raw, item.filename):
            from app.services.shipping_customs import capture_from_eml
            capture_from_eml(db, factory_id, item.id, raw, _loads(item.fields_json))
        batch.total_count += 1
        if item.status == 'failed':
            batch.failed_count += 1
        else:
            batch.parsed_count += 1
    if not items:
        db.delete(batch)
        db.commit()
        return {'batch': None, 'items': [], 'duplicates': seen}
    db.commit()
    return {'batch': _batch_dict(batch), 'items': [_item_dict(item) for item in items], 'duplicates': seen}


def list_batches(db, user: AuthContext, factory_id: str) -> list[dict]:
    authorize(user, factory_id, 'read')
    rows = db.scalars(
        select(ShippingMailBatch)
        .where(ShippingMailBatch.factory_id == factory_id)
        .order_by(ShippingMailBatch.created_at.desc())
        .limit(50)
    ).all()
    return [_batch_dict(row) for row in rows]


def delete_batch(db, user: AuthContext, batch_id: str, factory_id: str) -> dict:
    authorize(user, factory_id, 'write')
    batch = _load_batch(db, batch_id, factory_id)
    items = db.scalars(select(ShippingMailItem).where(ShippingMailItem.batch_id == batch.id)).all()
    item_ids = [item.id for item in items]
    if item_ids:
        for task in db.scalars(select(ShippingTask).where(ShippingTask.mail_item_id.in_(item_ids))).all():
            task.mail_item_id = None
        for item in items:
            db.delete(item)
    db.delete(batch)
    db.commit()
    return {'deleted': True, 'items': len(items)}


def batch_detail(db, user: AuthContext, batch_id: str, factory_id: str) -> dict:
    authorize(user, factory_id, 'read')
    batch = _load_batch(db, batch_id, factory_id)
    items = db.scalars(
        select(ShippingMailItem).where(ShippingMailItem.batch_id == batch.id).order_by(ShippingMailItem.created_at)
    ).all()
    return {'batch': _batch_dict(batch), 'items': [_item_dict(item) for item in items]}


def task_fields(db, task) -> dict:
    """Fields from the task's own email, or from a same-SO email task (factory schedule + email merge)."""
    item = None
    if task.mail_item_id:
        item = db.get(ShippingMailItem, task.mail_item_id)
    if item is None and task.so_number:
        related = db.scalar(select(ShippingTask).where(
            ShippingTask.factory_id == task.factory_id,
            ShippingTask.so_number == task.so_number,
            ShippingTask.mail_item_id.isnot(None),
        ))
        if related is not None:
            item = db.get(ShippingMailItem, related.mail_item_id)
    if item is None:
        return {}
    fields = json.loads(item.fields_json or '{}')
    if item.received_at:
        fields['received_at'] = item.received_at
    return fields


def confirm_batch(db, user: AuthContext, batch_id: str, factory_id: str, item_ids: list[str],
                  overrides: dict | None = None, modules: list[str] | None = None) -> dict:
    authorize(user, factory_id, 'confirm')
    batch = _load_batch(db, batch_id, factory_id)
    if not item_ids:
        raise HTTPException(422, '请选择要确认的邮件')
    items = db.scalars(
        select(ShippingMailItem).where(
            ShippingMailItem.batch_id == batch.id, ShippingMailItem.id.in_(item_ids),
        )
    ).all()
    if len(items) != len(set(item_ids)):
        raise HTTPException(404, '部分邮件不存在或不属于该批次')
    tasks = []
    for item in items:
        if item.status != 'pending':
            raise HTTPException(409, f'{item.filename} 当前状态为 {item.status}，不能建任务')
        fields = _loads(item.fields_json)
        if overrides:
            changed = False
            for key, value in overrides.items():
                if value not in (None, ''):
                    fields[key] = value
                    changed = True
            if changed:
                item.fields_json = json.dumps(fields, ensure_ascii=False)
        if not str(fields.get('so_number') or '').strip():
            raise HTTPException(422, f'{item.filename} 缺少 SO/BN 订舱号，请人工补充后再确认')
        planned = resolve_planned_ship_date(
            ship_date=fields.get('ship_date', ''),
            cutoff_date=fields.get('cutoff_date', ''),
            si_deadline=fields.get('si_deadline', ''),
            received_at=item.received_at,
        )
        if planned is None and overrides:
            planned = date.today()
        if planned is None:
            raise HTTPException(422, f'{item.filename} 缺少可用日期：需要明确出货日或截关/SI 截止时间')
        existing = db.scalar(select(ShippingTask).where(ShippingTask.mail_item_id == item.id))
        so_number = str(fields.get('so_number') or '').strip()
        if existing is None:
            schedule_task = db.scalar(select(ShippingTask).where(
                ShippingTask.factory_id == factory_id,
                ShippingTask.source == 'schedule',
                ShippingTask.so_number == so_number,
                ShippingTask.mail_item_id.is_(None),
            ).order_by(ShippingTask.planned_ship_date.desc()))
            if schedule_task is None:
                schedule_task = db.scalar(select(ShippingTask).where(
                    ShippingTask.factory_id == factory_id,
                    ShippingTask.source == 'schedule',
                    ShippingTask.so_number == so_number,
                ).order_by(ShippingTask.planned_ship_date.desc(), ShippingTask.created_at.desc()))
            if schedule_task is None:
                schedule_task = _match_schedule_task(db, factory_id, _loads(item.items_json))
            if schedule_task is not None:
                schedule_task.mail_item_id = item.id
                _merge_task_items(schedule_task, _loads(item.items_json))
                for key, value in (
                    ('container_type', fields.get('container_type')),
                    ('port', fields.get('from_port')),
                    ('destination_country', fields.get('destination_country')),
                    ('si_deadline', fields.get('si_deadline')),
                    ('cutoff_date', fields.get('cutoff_date')),
                ):
                    text = str(value or '').strip()
                    if text:
                        setattr(schedule_task, key, text)
                if not str(schedule_task.planned_ship_date or '').strip():
                    schedule_task.planned_ship_date = planned.isoformat()[:10] if hasattr(planned, 'isoformat') else str(planned)
                task = schedule_task
            else:
                task = _new_task(
                    factory_id=factory_id, fields=fields, items=_loads(item.items_json),
                    source='mail', mail_item_id=item.id, warnings=_loads(item.warnings_json), planned=planned,
                )
                db.add(task)
                db.flush()
        else:
            task = existing
        item.status = 'confirmed'
        item.task_ids_json = _dump([task.id])
        item.updated_at = _now()
        tasks.append(task)
    batch.status = 'confirmed'
    db.commit()
    try:
        from app.services.shipping_autogen import generate_for_task
        module_map = {'so': {'so_dk'}, 'truck': {'truck_buzzbee', 'truck_bulk'}, 'supplement': {'supplement'}}
        selected: set[str] | None = None
        if modules:
            selected = set()
            for module in modules:
                selected.update(module_map.get(module, set()))
        for task in tasks:
            generate_for_task(db, user, factory_id, task.id, selected, replace=True)
    except Exception:  # noqa: BLE001 - generation must not fail the confirmation
        pass
    return {'batch': _batch_dict(batch), 'tasks': [_task_dict(task) for task in tasks]}


def schedule_rows(db, user: AuthContext, factory_id: str) -> dict:
    """工厂排期单按 合同号 × 备案货号 拆行，供页面直接展示两个编号。"""
    authorize(user, factory_id, 'read')
    tasks = db.scalars(
        select(ShippingTask)
        .where(ShippingTask.factory_id == factory_id, ShippingTask.source == 'schedule')
        .order_by(ShippingTask.planned_ship_date.desc(), ShippingTask.created_at.desc())
    ).all()
    return {'rows': expand_schedule_rows(tasks), 'tasks': len(tasks)}


def expand_schedule_rows(tasks) -> list[dict]:
    """One row per item so a 备案货号 with several 合同号 appears as several rows."""
    rows: list[dict] = []
    for task in tasks:
        items = _loads(task.items_json) or []
        exportable = [item for item in items if isinstance(item, dict)]
        if not exportable:
            rows.append(_schedule_row(task, {}))
            continue
        for item in exportable:
            rows.append(_schedule_row(task, item))
    return rows


def _schedule_row(task: ShippingTask, item: dict) -> dict:
    return {
        'task_id': task.id,
        'so_number': task.so_number,
        'customer': task.customer,
        'container_type': task.container_type,
        'port': task.port,
        'destination_country': task.destination_country,
        'planned_ship_date': task.planned_ship_date,
        'si_deadline': task.si_deadline,
        'cutoff_date': task.cutoff_date,
        'status': task.status,
        'contract_no': str(item.get('contract_no') or ''),
        'product_code': str(item.get('product_code') or ''),
        'product_name': str(item.get('product_name') or ''),
        'customer_po': str(item.get('customer_po') or ''),
        'quantity': item.get('quantity'),
        'cartons': item.get('cartons'),
        'cbm': item.get('cbm'),
        'order_date': str(item.get('order_date') or ''),
        'inspection_date': str(item.get('inspection_date') or ''),
        'requested_ship_date': str(item.get('requested_ship_date') or task.planned_ship_date or ''),
        'sales_order_no': str(item.get('sales_order_no') or task.so_number or ''),
        'packing': item.get('coefficient'),
        'standard': str(item.get('standard') or item.get('country') or task.destination_country or ''),
        'remark': str(item.get('remark') or ''),
    }


def create_manual_task(db, user: AuthContext, payload: dict) -> dict:
    """Create a task from manually entered fields (used for scanned documents)."""
    factory_id = payload.get('factory_id', '')
    authorize(user, factory_id, 'write')
    fields = payload.get('fields') or {}
    so_number = str(fields.get('so_number') or '').strip()
    if not so_number:
        raise HTTPException(422, '请填写 SO/BN 订舱号')
    planned = resolve_planned_ship_date(
        ship_date=fields.get('ship_date', ''),
        cutoff_date=fields.get('cutoff_date', ''),
        si_deadline=fields.get('si_deadline', ''),
        received_at=payload.get('received_at', ''),
    )
    if planned is None:
        raise HTTPException(422, '缺少可用日期：请填写出货日，或截关/SI 截止时间用于推导')
    items = payload.get('items') or []
    warnings = list(payload.get('warnings') or [])
    trips = payload.get('warehouse_trips')
    if trips:
        warnings.extend(_validate_trips(items, trips))
        fields['shipment_mode'] = 'warehouse'
    task = _new_task(
        factory_id=factory_id, fields=fields, items=items, source='manual',
        warnings=warnings, planned=planned,
    )
    db.add(task)
    db.commit()
    return {'task': _task_dict(task)}


def list_tasks(db, user: AuthContext, factory_id: str, status: str | None = None, q: str = '') -> list[dict]:
    authorize(user, factory_id, 'read')
    query = select(ShippingTask).where(ShippingTask.factory_id == factory_id)
    if status:
        query = query.where(ShippingTask.status == status)
    if q.strip():
        needle = q.strip()
        query = query.where(or_(
            ShippingTask.so_number.contains(needle),
            ShippingTask.customer.contains(needle),
            ShippingTask.port.contains(needle),
        ))
    rows = db.scalars(query.order_by(ShippingTask.planned_ship_date.desc(), ShippingTask.created_at.desc()).limit(2000)).all()
    return [_task_dict(row) for row in rows]


def update_task_status(db, user: AuthContext, task_id: str, factory_id: str, status: str) -> dict:
    authorize(user, factory_id, 'write')
    task = db.scalar(select(ShippingTask).where(ShippingTask.id == task_id, ShippingTask.factory_id == factory_id))
    if task is None:
        raise HTTPException(404, '船务任务不存在')
    if not can_transition(task.status, status):
        raise HTTPException(409, f'不允许从 {task.status} 变更为 {status}')
    if status == 'shipment' and not task.planned_ship_date:
        raise HTTPException(422, '缺少计划出货日，不能进入待出货')
    task.status = status
    task.updated_at = _now()
    db.commit()
    return {'task': _task_dict(task)}


def _decoded_filename(filename: str) -> str:
    from email.header import decode_header
    parts = []
    for value, charset in decode_header(filename or ''):
        if isinstance(value, bytes):
            parts.append(value.decode(charset or 'utf-8', errors='replace'))
        else:
            parts.append(value)
    return ''.join(parts) or 'upload.bin'


def _is_email_message(raw: bytes, filename: str) -> bool:
    if filename.lower().endswith('.eml'):
        return True
    head = raw[:4000].lstrip()
    return head.startswith(b'Subject:') and b'Content-Type:' in raw[:8000]


def _build_item(factory_id: str, batch_id: str, filename: str, raw: bytes, now: str) -> ShippingMailItem:
    filename = _decoded_filename(filename)
    try:
        if _is_email_message(raw, filename):
            parsed = parse_shipping_email(raw, filename)
            status = 'pending'
            if any(attachment['status'] == 'needs_ocr' for attachment in parsed['attachments']):
                status = 'needs_ocr'
            fields, items, warnings = parsed['fields'], parsed['items'], parsed['warnings']
            trace = parsed['rule_trace']
            subject, sender, received_at = parsed['subject'], parsed['sender'], parsed['received_at']
            fingerprint = parsed['fingerprint']
        else:
            parsed = parse_shipping_document(raw, filename)
            status = 'needs_ocr' if parsed['status'] == 'needs_ocr' else 'pending'
            fields, items, warnings, trace = parsed['fields'], parsed['items'], parsed['warnings'], []
            subject = sender = received_at = ''
            fingerprint = ''
    except Exception as error:  # noqa: BLE001 - 单封失败只影响该封邮件
        return ShippingMailItem(
            id=_new_id('mail'), batch_id=batch_id, factory_id=factory_id, filename=filename[:500],
            fingerprint='', subject='', sender='', received_at='', status='failed',
            fields_json='{}', items_json='[]', warnings_json=_dump([f'解析失败：{type(error).__name__}']),
            trace_json='[]', task_ids_json='[]', created_at=now, updated_at=now,
        )
    return ShippingMailItem(
        id=_new_id('mail'), batch_id=batch_id, factory_id=factory_id, filename=filename[:500],
        fingerprint=fingerprint[:64], subject=str(subject)[:500], sender=str(sender)[:500],
        received_at=str(received_at)[:80], status=status,
        fields_json=_dump(fields), items_json=_dump(items), warnings_json=_dump(warnings),
        trace_json=_dump(trace), task_ids_json='[]', created_at=now, updated_at=now,
    )


def _validate_trips(items: list[dict], trips: list[dict]) -> list[str]:
    cargo: list[TruckCargo] = []
    for index, item in enumerate(items):
        key = str(item.get('key') or index)
        try:
            cbm = Decimal(str(item.get('cbm') or '0'))
        except (InvalidOperation, ValueError):
            raise HTTPException(422, f'货物 {key} 的 CBM 无效') from None
        cargo.append(TruckCargo(key=key, cbm=cbm, packing_group=str(item.get('packing_group') or '')))
    plans: list[TruckPlan] = []
    for index, trip in enumerate(trips):
        vehicle = str(trip.get('vehicle_type') or '')
        error = truck_type_format_error(vehicle) if vehicle else None
        if error:
            raise HTTPException(422, f'第{index + 1}车{error}')
        cargo_keys = tuple(str(key) for key in (trip.get('cargo_keys') or []))
        total = sum((item.cbm for item in cargo if item.key in cargo_keys), Decimal('0'))
        plans.append(TruckPlan(
            key=str(index + 1), warehouse=str(trip.get('warehouse') or ''), cargo_keys=cargo_keys,
            cbm=total, vehicle_type=vehicle,
        ))
    try:
        validate_warehouse_trips(cargo, plans)
    except ShippingRuleError as error:
        raise HTTPException(422, str(error)) from None
    return []


def _match_schedule_task(db, factory_id: str, items: list[dict]):
    """Find an internal schedule task with the same contract + item/PO, for DO/booking merge."""
    contracts = {str(item.get('contract_no') or '').strip() for item in items if item.get('contract_no')}
    codes = {str(item.get('product_code') or '').strip() for item in items if item.get('product_code')}
    pos = {str(item.get('customer_po') or '').strip() for item in items if item.get('customer_po')}
    if not codes or not (contracts or pos):
        return None
    for source in ('schedule', 'mail'):
        candidates = db.scalars(select(ShippingTask).where(
            ShippingTask.factory_id == factory_id,
            ShippingTask.source == source,
        )).all()
        for task in candidates:
            for row in _loads(task.items_json):
                code = str((row or {}).get('product_code') or '').strip()
                contract = str((row or {}).get('contract_no') or '').strip()
                po = str((row or {}).get('customer_po') or '').strip()
                if code in codes and (contract in contracts or po in pos):
                    return task
    return None


def _merge_task_items(task, incoming: list[dict]) -> None:
    current = [row for row in _loads(task.items_json) if isinstance(row, dict)]
    for item in incoming:
        contract = str(item.get('contract_no') or '').strip()
        code = str(item.get('product_code') or '').strip()
        po = str(item.get('customer_po') or '').strip()
        if not contract:
            same_code = next((row for row in current
                              if str(row.get('product_code') or '').strip() == code
                              and str(row.get('customer_po') or '').strip() == po
                              and str(row.get('contract_no') or '').strip()), None)
            if same_code:
                contract = str(same_code.get('contract_no') or '').strip()
                item['contract_no'] = contract
        match = next((row for row in current if str(row.get('contract_no') or '').strip() == contract
                      and str(row.get('product_code') or '').strip() == code), None)
        if match is None:
            current.append(item)
            continue
        for key, value in item.items():
            if value not in (None, '') and match.get(key) in (None, ''):
                match[key] = value
    task.items_json = _dump(current)


def _new_task(*, factory_id: str, fields: dict, items: list, source: str, planned: date,
              mail_item_id: str | None = None, warnings: list | None = None) -> ShippingTask:
    now = _now()
    return ShippingTask(
        id=_new_id('task'), factory_id=factory_id, mail_item_id=mail_item_id, source_group_key='',
        source=source, so_number=str(fields.get('so_number') or '')[:64],
        customer=str(fields.get('customer') or '')[:200],
        container_type=str(fields.get('container_type') or '')[:64],
        port=str(fields.get('port') or '')[:64],
        destination_country=str(fields.get('destination_country') or '')[:64],
        shipment_mode=str(fields.get('shipment_mode') or 'unknown')[:24],
        status='review', planned_ship_date=planned.isoformat(),
        si_deadline=str(fields.get('si_deadline') or '')[:20],
        cutoff_date=str(fields.get('cutoff_date') or '')[:20],
        items_json=_dump(items), warnings_json=_dump(list(warnings or [])),
        created_at=now, updated_at=now,
    )


def _load_batch(db, batch_id: str, factory_id: str) -> ShippingMailBatch:
    batch = db.scalar(
        select(ShippingMailBatch).where(
            ShippingMailBatch.id == batch_id, ShippingMailBatch.factory_id == factory_id,
        )
    )
    if batch is None:
        raise HTTPException(404, '邮件批次不存在')
    return batch


def _batch_dict(batch: ShippingMailBatch) -> dict:
    return {
        'id': batch.id, 'factory_id': batch.factory_id, 'source': batch.source,
        'filename': batch.filename, 'status': batch.status, 'total_count': batch.total_count,
        'parsed_count': batch.parsed_count, 'failed_count': batch.failed_count,
        'parser_version': batch.parser_version, 'created_at': batch.created_at,
    }


def _item_dict(item: ShippingMailItem) -> dict:
    return {
        'id': item.id, 'batch_id': item.batch_id, 'filename': item.filename, 'status': item.status,
        'subject': item.subject, 'sender': item.sender, 'received_at': item.received_at,
        'fields': _loads(item.fields_json), 'items': _loads(item.items_json),
        'warnings': _loads(item.warnings_json), 'rule_trace': _loads(item.trace_json),
        'task_ids': _loads(item.task_ids_json), 'created_at': item.created_at,
    }


def _task_dict(task: ShippingTask) -> dict:
    return {
        'id': task.id, 'factory_id': task.factory_id, 'mail_item_id': task.mail_item_id,
        'source': task.source, 'so_number': task.so_number, 'customer': task.customer,
        'container_type': task.container_type, 'port': task.port,
        'destination_country': task.destination_country, 'shipment_mode': task.shipment_mode,
        'status': task.status, 'planned_ship_date': task.planned_ship_date,
        'si_deadline': task.si_deadline, 'cutoff_date': task.cutoff_date,
        'items': _loads(task.items_json), 'warnings': _loads(task.warnings_json),
        'created_at': task.created_at, 'updated_at': task.updated_at,
    }


def _new_id(prefix: str) -> str:
    return f'{prefix}-{uuid4().hex}'


def _now() -> str:
    return datetime.now().isoformat(timespec='seconds')


def _dump(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def _loads(text: str):
    try:
        return json.loads(text or 'null')
    except json.JSONDecodeError:
        return None
