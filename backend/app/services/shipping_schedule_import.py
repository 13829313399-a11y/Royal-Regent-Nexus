"""Daily bridge: 厂区总排期 (customer order ledger) → 船务工厂排期 tasks."""
import asyncio
import hashlib
import json
from datetime import date, datetime, timedelta

from sqlalchemy import select

from app.models.customer_order_ledger import OrderLedgerLine
from app.models.shipping_mail import ShippingTask

SOURCE = 'schedule'


def _number(value) -> float | None:
    try:
        return float(value) if value not in (None, '') else None
    except (TypeError, ValueError):
        return None


def _text(value) -> str:
    return str(value or '').strip()


def _group_key(factory_id: str, customer: str, reference: str, ship_date: str, port: str) -> str:
    raw = f'{factory_id}|{customer}|{reference}|{ship_date}|{port}'
    return hashlib.sha1(raw.encode('utf-8')).hexdigest()[:32]


def _items(line: OrderLedgerLine, data: dict) -> dict:
    ordered = _number(line.quantity)
    shipped = _number(line.shipped_quantity) or 0
    remaining = ordered - shipped if ordered is not None else None
    return {
        'product_code': line.product_no,
        'product_name': _text(data.get('product_name_zh') or data.get('product_name_en')),
        'quantity': remaining,
        'cartons': _number(data.get('carton_count')),
        'coefficient': _number(data.get('coefficient') or data.get('pack_qty') or data.get('pieces_per_carton')
                               or data.get('qty_per_carton') or data.get('装箱数') or data.get('出箱数')),
        'cbm': _number(data.get('cbm')),
        'gross_weight': _number(data.get('gross_weight')),
        'net_weight': _number(data.get('net_weight')),
        'contract_no': _text(data.get('contract_no')),
        'customer_po': _text(data.get('po_no') or data.get('customer_po')),
        'country': _text(data.get('country')),
        'consignee': _text(data.get('consignee') or data.get('receiver') or data.get('consignee_name')),
        'transport_company': _text(data.get('transport_company') or data.get('transportCompany')
                                   or data.get('transport') or data.get('运输公司') or data.get('运输')),
        'brand': _text(data.get('brand') or data.get('brand_name') or data.get('brandName') or data.get('品牌')),
        'vehicle': _text(data.get('vehicle') or data.get('truck_no') or data.get('truckNo') or data.get('车次')),
        'truck_type': _text(data.get('truck_type') or data.get('truckType') or data.get('车型')),
        'cfs': _text(data.get('cfs') or data.get('CFS') or data.get('warehouse') or data.get('CFS/仓库')),
        'plate': _text(data.get('plate') or data.get('车牌')),
        'unit': _text(data.get('unit')),
        'source_line_id': line.id,
    }


_LAST_PURGE: dict[tuple[str, int, int], bool] = {}


def purge_previous_month(db, factory_id: str) -> dict:
    """Delete schedule items whose requested ship date is in the previous calendar month."""
    today = date.today()
    current_start = date(today.year, today.month, 1)
    previous_start = date(current_start.year - 1, 12, 1) if current_start.month == 1 else date(current_start.year, current_start.month - 1, 1)
    previous_end = current_start
    removed = deleted_tasks = 0
    tasks = db.scalars(select(ShippingTask).where(
        ShippingTask.factory_id == factory_id,
        ShippingTask.source == SOURCE,
    )).all()
    for task in tasks:
        items = json.loads(task.items_json or '[]')
        kept = []
        for item in items:
            if not isinstance(item, dict):
                continue
            raw = str(item.get('requested_ship_date') or item.get('ship_date') or task.planned_ship_date or '')[:10]
            try:
                item_day = date.fromisoformat(raw)
            except ValueError:
                kept.append(item)
                continue
            if previous_start <= item_day < previous_end:
                removed += 1
                continue
            kept.append(item)
        if len(kept) != len(items):
            if kept:
                task.items_json = json.dumps(kept, ensure_ascii=False)
                task.updated_at = datetime.now().isoformat(timespec='seconds')
            else:
                db.delete(task)
                deleted_tasks += 1
    if removed or deleted_tasks:
        db.commit()
    return {'removed_items': removed, 'deleted_tasks': deleted_tasks, 'month': previous_start.strftime('%Y-%m')}


def maybe_purge_previous_month(db, factory_id: str) -> None:
    today = date.today()
    key = (factory_id, today.year, today.month)
    if _LAST_PURGE.get(key):
        return
    _LAST_PURGE[key] = True
    purge_previous_month(db, factory_id)


def import_factory_schedule(db, factory_id: str, *, window_days: int = 120, include_history: bool = False) -> dict:
    """Upsert shipping tasks from 厂区总排期 lines (daily window or historical backfill)."""
    today = date.today()
    floor = '0001-01-01' if include_history else (today - timedelta(days=14)).isoformat()
    ceiling = (today + timedelta(days=window_days)).isoformat()
    filters = [OrderLedgerLine.factory_id == factory_id]
    filters.append(OrderLedgerLine.status != 'cancelled' if include_history else OrderLedgerLine.status == 'active')
    lines = db.scalars(select(OrderLedgerLine).where(*filters)).all()

    groups: dict[str, dict] = {}
    for line in lines:
        data = line.data or {}
        ship_date = _text(data.get('requested_ship_date'))
        if not ship_date or not (floor <= ship_date <= ceiling):
            continue
        ordered = _number(line.quantity)
        shipped = _number(line.shipped_quantity) or 0
        if not include_history and ordered is not None and ordered <= shipped:
            continue
        reference = _text(line.reference_no) or _text(data.get('contract_no')) or _text(data.get('po_no'))
        port = _text(data.get('port'))
        key = _group_key(factory_id, line.customer_code, reference, ship_date, port)
        group = groups.setdefault(key, {
            'customer_code': line.customer_code, 'customer_name': line.customer_name,
            'reference': reference, 'ship_date': ship_date, 'port': port,
            'country': _text(data.get('country')), 'items': [],
            'consignee': _text(data.get('consignee') or data.get('receiver') or data.get('consignee_name')),
        })
        item = _items(line, data)
        if include_history and ordered is not None:
            item['quantity'] = ordered
            item['shipped_quantity'] = shipped
            item['historical'] = True
        group['items'].append(item)

    created = updated = 0
    now = datetime.now().isoformat(timespec='seconds')
    for key, group in groups.items():
        task = db.scalar(select(ShippingTask).where(
            ShippingTask.factory_id == factory_id,
            ShippingTask.source == SOURCE,
            ShippingTask.source_group_key == key,
        ))
        if task is None:
            task = ShippingTask(
                id=f'task-sched-{key}', factory_id=factory_id, mail_item_id=None,
                source_group_key=key, source=SOURCE,
                so_number=group['reference'][:64], customer=group['customer_name'][:200],
                container_type='', port=group['port'][:64], destination_country=group['country'][:64],
                shipment_mode='container', status='review', planned_ship_date=group['ship_date'],
                si_deadline='', cutoff_date='', items_json='[]', warnings_json='[]',
                created_at=now, updated_at=now,
            )
            db.add(task)
            created += 1
        else:
            updated += 1
        task.items_json = json.dumps(group['items'], ensure_ascii=False)
        task.updated_at = now
    db.commit()
    return {
        'factory_id': factory_id, 'created': created, 'updated': updated,
        'groups': len(groups), 'lines': len(lines),
        'history': include_history,
        'window': {'from': floor, 'to': ceiling},
    }


async def worker() -> None:
    """Import once per day after 06:00 for every shipping factory."""
    from app.core.config import settings
    from app.db import SessionLocal

    await asyncio.sleep(15)
    last_run = None
    while True:
        now = datetime.now()
        if now.hour >= 6 and last_run != now.date():
            factories = [item.strip() for item in settings.shipping_mail_imap_factories.split(',') if item.strip()]
            for factory_id in factories:
                try:
                    with SessionLocal() as db:
                        import_factory_schedule(db, factory_id)
                except Exception:  # noqa: BLE001 - daily bridge must not crash the API
                    continue
            last_run = now.date()
        await asyncio.sleep(1800)
