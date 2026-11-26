"""Import a factory schedule workbook into shipping tasks."""
from __future__ import annotations

import hashlib
import io
import json
import re
from datetime import date, datetime
from pathlib import Path

import openpyxl
import xlrd
from fastapi import HTTPException
from sqlalchemy import select

from app.models.shipping_mail import ShippingTask


def _text(value) -> str:
    if value is None:
        return ''
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, (datetime, date)):
        return value.isoformat()[:10]
    return str(value).strip()


def _number(value) -> float | None:
    try:
        return float(value) if value not in (None, '') else None
    except (TypeError, ValueError):
        return None


def _pack(value) -> float | None:
    text = _text(value)
    if not text:
        return None
    try:
        return float(text.split('/')[-1]) if '/' in text else float(text)
    except ValueError:
        return None


def _day(value) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = _text(value)
    if not text:
        return ''
    if re.fullmatch(r'\d{5}(\.0)?', text):
        try:
            return xlrd.xldate.xldate_as_datetime(float(text), 0).date().isoformat()
        except (ValueError, OverflowError):
            return ''
    match = re.search(r'(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})', text)
    if match:
        return f'{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}'
    return text[:10]


def _rows_from_xlsx(raw: bytes) -> list[list]:
    workbook = openpyxl.load_workbook(io.BytesIO(raw), data_only=True, read_only=True)
    try:
        sheet = next((item for item in workbook.worksheets if '接单表' in item.title), workbook.worksheets[0])
        return [list(row) for row in sheet.iter_rows(values_only=True)]
    finally:
        workbook.close()


def _rows_from_xls(raw: bytes) -> list[list]:
    workbook = xlrd.open_workbook(file_contents=raw)
    sheet = next((item for item in workbook.sheets() if '接单表' in item.name), workbook.sheet_by_index(0))
    return [[sheet.cell_value(r, c) for c in range(sheet.ncols)] for r in range(sheet.nrows)]


ALIASES = {
    'contract': ('合同号', '合同', 'contractno', 'contract'),
    'so': ('so', 'so#', 'so号', '订单号', 'reference', 'so#/reference', 'so/reference'),
    'customer': ('客名', '客户', '客户名称', 'customer'),
    'code': ('产品编号', '货号', '备案货号', 'item', 'itemno', 'sku'),
    'name': ('产品名称', '产品中文名称', '品名', '货名', 'description'),
    'quantity': ('数量', '數量', 'qty', 'quantity'),
    'cartons': ('箱数', 'ctns', 'cartons'),
    'coefficient': ('装箱数', '装箱', 'coefficient', '每箱个数'),
    'gross': ('毛重', 'gross', 'grossweight'),
    'net': ('净重', 'net', 'netweight'),
    'cbm': ('cbm', '体积'),
    'date': ('客要求走货期', '要求走货期', '出货日期', '计划出货日', 'scheduledate', 'etd', '走货期'),
    'order_date': ('客出单日期', '订单日期', 'orderdate'),
    'inspection_date': ('验货日期', 'inspectiondate'),
    'requested_ship_date': ('客要求走货期', '要求走货期', 'requestedshipdate'),
    'port': ('出货港口', '出港口', '港口', '起运港', 'port'),
    'country': ('目的国家', '国家', 'country'),
    'standard': ('国家标准', 'standard'),
    'remark': ('备注', 'remark', 'remarks'),
    'po': ('po#', 'po', '客户po', 'pono'),
    'brand': ('品牌', 'brand'),
}


def _normalize(value) -> str:
    return re.sub(r'[\s:：/\\_\-.#]', '', _text(value).lower())


def _header_map(row: list) -> dict[str, int]:
    normalized = [_normalize(cell) for cell in row]
    result: dict[str, int] = {}
    for field, aliases in ALIASES.items():
        for index, header in enumerate(normalized):
            if any(header == _normalize(alias) for alias in aliases):
                result[field] = index
                break
    return result


def _group_key(factory_id: str, customer: str, reference: str, ship_date: str, port: str) -> str:
    raw = f'{factory_id}|file|{customer}|{reference}|{ship_date}|{port}'
    return hashlib.sha1(raw.encode('utf-8')).hexdigest()[:32]


def _find_matching_task(db, factory_id: str, group: dict):
    contracts = {str(item.get('contract_no') or '').strip() for item in group['items'] if item.get('contract_no')}
    codes = {str(item.get('product_code') or '').strip() for item in group['items'] if item.get('product_code')}
    if not contracts or not codes:
        return None
    candidates = db.scalars(select(ShippingTask).where(
        ShippingTask.factory_id == factory_id,
        ShippingTask.source == 'schedule',
    )).all()
    for task in candidates:
        for item in json.loads(task.items_json or '[]'):
            if (str(item.get('contract_no') or '').strip() in contracts
                    and str(item.get('product_code') or '').strip() in codes
                    and item.get('quantity') is not None):
                return task
    return None


def import_schedule_workbook(db, user, factory_id: str, filename: str, raw: bytes) -> dict:
    from app.services.shipping_mail_service import authorize  # local import avoids a cycle
    authorize(user, factory_id, 'write')
    suffix = Path(filename).suffix.lower()
    if suffix not in ('.xlsx', '.xlsm', '.xls'):
        raise HTTPException(422, '请上传 Excel 排期表（.xlsx / .xls）')
    try:
        rows = _rows_from_xls(raw) if suffix == '.xls' else _rows_from_xlsx(raw)
    except Exception as error:  # noqa: BLE001
        raise HTTPException(422, f'Excel 读取失败：{type(error).__name__}') from error
    header_row = -1
    columns: dict[str, int] = {}
    for index, row in enumerate(rows[:15]):
        candidate = _header_map(row)
        if 'code' in candidate and ('contract' in candidate or 'so' in candidate):
            header_row = index
            columns = candidate
            break
    if header_row < 0:
        raise HTTPException(422, '未找到货号/合同号表头，请使用工厂排期模板')

    def value(row: list, field: str) -> str:
        index = columns.get(field)
        return _text(row[index]) if index is not None and index < len(row) else ''

    groups: dict[str, dict] = {}
    imported = 0
    for row in rows[header_row + 1:]:
        code = value(row, 'code')
        contract = value(row, 'contract')
        so = value(row, 'so')
        if not code or not (contract or so):
            continue
        ship_date = _day(row[columns['date']]) if 'date' in columns and columns['date'] < len(row) else ''
        if not ship_date:
            continue
        customer = value(row, 'customer')
        reference = so or contract
        port = value(row, 'port')
        key = _group_key(factory_id, customer, reference, ship_date, port)
        group = groups.setdefault(key, {
            'customer': customer, 'reference': reference, 'ship_date': ship_date, 'port': port,
            'country': value(row, 'country'), 'items': [],
        })
        group['items'].append({
            'product_code': code,
            'product_name': value(row, 'name'),
            'quantity': _number(row[columns['quantity']]) if 'quantity' in columns and columns['quantity'] < len(row) else None,
            'cartons': _number(row[columns['cartons']]) if 'cartons' in columns and columns['cartons'] < len(row) else None,
            'coefficient': _pack(row[columns['coefficient']]) if 'coefficient' in columns and columns['coefficient'] < len(row) else None,
            'gross_weight': _number(row[columns['gross']]) if 'gross' in columns and columns['gross'] < len(row) else None,
            'net_weight': _number(row[columns['net']]) if 'net' in columns and columns['net'] < len(row) else None,
            'cbm': _number(row[columns['cbm']]) if 'cbm' in columns and columns['cbm'] < len(row) else None,
            'contract_no': contract,
            'customer_po': value(row, 'po'),
            'country': value(row, 'country'),
            'standard': value(row, 'standard'),
            'order_date': _day(row[columns['order_date']]) if 'order_date' in columns and columns['order_date'] < len(row) else '',
            'inspection_date': _day(row[columns['inspection_date']]) if 'inspection_date' in columns and columns['inspection_date'] < len(row) else '',
            'requested_ship_date': _day(row[columns['requested_ship_date']]) if 'requested_ship_date' in columns and columns['requested_ship_date'] < len(row) else ship_date,
            'sales_order_no': so or contract,
            'remark': value(row, 'remark'),
            'brand': value(row, 'brand'),
            'origin_port': port,
        })
        imported += 1
    if not groups:
        raise HTTPException(422, '未读取到有效排期行（需含货号、合同/SO、出货日期）')
    created = updated = 0
    now = datetime.now().isoformat(timespec='seconds')
    for key, group in groups.items():
        task = db.scalar(select(ShippingTask).where(
            ShippingTask.factory_id == factory_id,
            ShippingTask.source == 'schedule',
            ShippingTask.source_group_key == key,
        ))
        if task is None:
            task = _find_matching_task(db, factory_id, group)
        if task is None:
            task = ShippingTask(
                id=f'task-file-{key}', factory_id=factory_id, mail_item_id=None,
                source_group_key=key, source='schedule',
                so_number=group['reference'][:64], customer=group['customer'][:200],
                container_type='', port=group['port'][:64], destination_country=group['country'][:64],
                shipment_mode='container', status='review', planned_ship_date=group['ship_date'],
                si_deadline='', cutoff_date='', items_json='[]', warnings_json='[]',
                created_at=now, updated_at=now,
            )
            db.add(task)
            created += 1
        else:
            updated += 1
        current = [row for row in json.loads(task.items_json or '[]') if isinstance(row, dict)]
        for item in group['items']:
            match = next((row for row in current
                          if str(row.get('contract_no') or '').strip() == str(item.get('contract_no') or '').strip()
                          and str(row.get('product_code') or '').strip() == str(item.get('product_code') or '').strip()), None)
            if match is None:
                current.append(item)
            else:
                for field, value in item.items():
                    if value not in (None, ''):
                        match[field] = value
        task.items_json = json.dumps(current, ensure_ascii=False)
        task.updated_at = now
    db.commit()
    return {
        'filename': filename, 'rows': imported, 'groups': len(groups),
        'created': created, 'updated': updated,
    }
