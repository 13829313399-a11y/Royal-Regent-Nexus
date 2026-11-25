"""Import 柜单 workbooks into the per-customer product history."""
from datetime import datetime
import io
from uuid import uuid4

import xlrd
from fastapi import HTTPException
from openpyxl import load_workbook
from sqlalchemy import select

from app.models.shipping_mail import ShippingProductHistory
from app.services.auth import AuthContext
from app.services.shipping_mail_service import authorize

_ALIASES = {
    'code': ('货号', '工厂备案货号', '备案货号', '出货申报货号', '走货申报货号', '产品编号', 'itemno', 'item', 'sku'),
    'name': ('货名', '品名', '产品名称', 'description', 'name'),
    'category': ('玩具类别', '类别'),
    'gross': ('每箱毛重', 'kg/箱(毛重)', 'kg/箱（毛重）', '每箱毛重(kg)'),
    'net': ('每箱净重', 'kg/箱(净重)', 'kg/箱（净重）', '每箱净重(kg)'),
}


def _normalize(value) -> str:
    text = '' if value is None else str(value)
    return (text.replace(' ', '').replace('\n', '').replace('（', '(').replace('）', ')')
            .replace('\r', '').lower())


def _read_rows(data: bytes, filename: str) -> list[list]:
    if filename.lower().endswith('.xls'):
        book = xlrd.open_workbook(file_contents=data)
        sheet = book.sheet_by_index(0)
        return [[sheet.cell_value(row, col) for col in range(sheet.ncols)] for row in range(sheet.nrows)]
    try:
        book = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as error:  # noqa: BLE001
        raise HTTPException(422, f'{filename} 无法读取：{type(error).__name__}') from error
    sheet = book.worksheets[0]
    return [[cell for cell in row] for row in sheet.iter_rows(values_only=True)]


def _column_map(rows: list[list]) -> tuple[int, dict[str, int]] | None:
    for index, row in enumerate(rows[:40]):
        headers = [_normalize(cell) for cell in row]
        mapping: dict[str, int] = {}
        for field, aliases in _ALIASES.items():
            for alias in aliases:
                normalized = _normalize(alias)
                if normalized in headers:
                    mapping[field] = headers.index(normalized)
                    break
        if 'code' in mapping:
            return index, mapping
    return None


def _text(value) -> str:
    if value is None:
        return ''
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def parse_products(data: bytes, filename: str) -> list[dict]:
    rows = _read_rows(data, filename)
    header = _column_map(rows)
    if header is None:
        raise HTTPException(422, f'{filename} 未找到货号表头')
    index, mapping = header
    products = []
    for row in rows[index + 1:]:
        def cell(field: str) -> str:
            position = mapping.get(field)
            return _text(row[position]) if position is not None and position < len(row) else ''
        code = cell('code')
        if not code or code in ('合计', '小计', '总计'):
            continue
        products.append({
            'product_code': code[:120],
            'product_name': cell('name')[:300],
            'category': cell('category')[:120],
            'gross_per_carton': cell('gross')[:32],
            'net_per_carton': cell('net')[:32],
        })
    return products


def _now() -> str:
    return datetime.now().isoformat(timespec='seconds')


def _record(row: ShippingProductHistory) -> dict:
    return {
        'id': row.id, 'product_code': row.product_code, 'product_name': row.product_name,
        'category': row.category, 'gross_per_carton': row.gross_per_carton,
        'net_per_carton': row.net_per_carton, 'customer': row.customer, 'source': row.source,
        'updated_at': row.updated_at,
    }


def import_files(db, user: AuthContext, factory_id: str, customer: str,
                 files: list[tuple[str, bytes]]) -> dict:
    authorize(user, factory_id, 'import')
    customer = (customer or '').strip()[:64]
    if not customer:
        raise HTTPException(422, '请选择归属客户')
    created = updated = 0
    for filename, data in files:
        for product in parse_products(data, filename):
            row = db.scalar(select(ShippingProductHistory).where(
                ShippingProductHistory.factory_id == factory_id,
                ShippingProductHistory.customer == customer,
                ShippingProductHistory.product_code == product['product_code'],
            ))
            if row is None:
                row = ShippingProductHistory(
                    id=f'prod-{uuid4().hex}', factory_id=factory_id, customer=customer,
                    product_code=product['product_code'], product_name='', category='',
                    gross_per_carton='', net_per_carton='', source='daily',
                    created_at=_now(), updated_at=_now(),
                )
                db.add(row)
                created += 1
            else:
                updated += 1
            for key in ('product_name', 'category', 'gross_per_carton', 'net_per_carton'):
                if product[key]:
                    setattr(row, key, product[key])
            row.updated_at = _now()
    db.commit()
    return {
        'created': created, 'updated': updated, 'total': created + updated,
        'records': list_records(db, user, factory_id, customer),
    }


def list_records(db, user: AuthContext, factory_id: str, customer: str = '', limit: int = 200) -> list[dict]:
    authorize(user, factory_id, 'read')
    query = select(ShippingProductHistory).where(ShippingProductHistory.factory_id == factory_id)
    if customer:
        query = query.where(ShippingProductHistory.customer == customer)
    rows = db.scalars(query.order_by(ShippingProductHistory.updated_at.desc()).limit(limit)).all()
    return [_record(row) for row in rows]
