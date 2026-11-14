"""Shipping mail import and task creation: factory-scoped, server-computed, no silent guesses."""
import json
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


def preview(factory_id: str, filename: str, raw: bytes, user: AuthContext) -> dict:
    """Parse one uploaded file without persisting anything."""
    authorize(user, factory_id, 'import')
    if filename.lower().endswith('.eml'):
        return parse_shipping_email(raw, filename)
    result = parse_shipping_document(raw, filename)
    return {
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
        db.add(item)
        items.append(item)
        if filename.lower().endswith('.eml'):
            from app.services.shipping_customs import capture_from_eml
            capture_from_eml(db, factory_id, item.id, raw)
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


def batch_detail(db, user: AuthContext, batch_id: str, factory_id: str) -> dict:
    authorize(user, factory_id, 'read')
    batch = _load_batch(db, batch_id, factory_id)
    items = db.scalars(
        select(ShippingMailItem).where(ShippingMailItem.batch_id == batch.id).order_by(ShippingMailItem.created_at)
    ).all()
    return {'batch': _batch_dict(batch), 'items': [_item_dict(item) for item in items]}


def confirm_batch(db, user: AuthContext, batch_id: str, factory_id: str, item_ids: list[str]) -> dict:
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
        if not str(fields.get('so_number') or '').strip():
            raise HTTPException(422, f'{item.filename} 缺少 SO/BN 订舱号，请人工补充后再确认')
        planned = resolve_planned_ship_date(
            ship_date=fields.get('ship_date', ''),
            cutoff_date=fields.get('cutoff_date', ''),
            si_deadline=fields.get('si_deadline', ''),
            received_at=item.received_at,
        )
        if planned is None:
            raise HTTPException(422, f'{item.filename} 缺少可用日期：需要明确出货日或截关/SI 截止时间')
        existing = db.scalar(select(ShippingTask).where(ShippingTask.mail_item_id == item.id))
        if existing is None:
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
    return {'batch': _batch_dict(batch), 'tasks': [_task_dict(task) for task in tasks]}


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
    rows = db.scalars(query.order_by(ShippingTask.planned_ship_date.desc(), ShippingTask.created_at.desc()).limit(200)).all()
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


def _build_item(factory_id: str, batch_id: str, filename: str, raw: bytes, now: str) -> ShippingMailItem:
    try:
        if filename.lower().endswith('.eml'):
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
