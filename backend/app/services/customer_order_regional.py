"""Explicit unified-schedule field rules for Huadeng and Huakang D."""
from datetime import date, timedelta
from decimal import Decimal
import re

from openpyxl.utils.datetime import to_excel


CUSTOMERS = {
    'huadeng': {'casdon', 'jakks', 'simba', 'spin', 'goliath'},
    'huakang-d': {'index', 'jazwares', 'maxx', 'strottman', 'ubtech', 'seasons'},
}
TARGET_TEMPLATE = 'HEYUAN_BUSINESS_UNIFIED_REGIONAL_V3'
CASDON_HEADERS = {
    'country': '走货国家', 'container_type': '柜型/车型', 'brand': '品牌',
    'end_customer_po': '客PO',
}


def enabled(factory_id, customer_code):
    return customer_code in CUSTOMERS.get(factory_id, set())


def extra_columns(sheet, factory_id, customer_code):
    from app.services.customer_order_unified import _normalized_header
    headers = CASDON_HEADERS if (factory_id, customer_code) == ('huadeng', 'casdon') else {}
    if (factory_id, customer_code) == ('huadeng', 'goliath'):
        headers = {'remarks': '备注'}
    columns = {}
    for field, label in headers.items():
        matches = [c.column for c in sheet[3] if c.column > 28 and _normalized_header(c.value) == _normalized_header(label)]
        if len(matches) == 1:
            columns[field] = matches[0]
    return columns


def history_reference(factory_id, customer_code, contract, reference, po):
    if factory_id == 'huakang-d':
        return reference or po or contract
    return reference or contract or po


def history_number(cell, workbook, customer_code, *, pack=False):
    from app.services.customer_order_unified import _text
    if isinstance(cell.value, date):
        # Excel dates in numeric columns are serials with the wrong cell format.
        return _text(to_excel(cell.value, workbook.epoch))
    value = _text(cell.value)
    if customer_code == 'simba' and pack and re.fullmatch(r'\d+\s*/\s*\d+', value):
        return value.split('/')[-1].strip()
    return value


def map_huadeng(row, record, customer_code):
    from app.services.customer_order_unified import _text
    row['_regional_customer'] = customer_code
    # Legacy preview strings are not national standards or product packaging.
    row['standard'] = _text(record.get('national_standard'))
    row['packaging'] = _text(record.get('product_packaging'))
    if customer_code == 'casdon':
        row['end_customer_po'] = _text(record.get('po_no'))
        row['po_no'] = _text(record.get('contract_no'))
        row['reference_no'] = _text(record.get('contract_no'))
    elif customer_code == 'jakks':
        if record.get('document_kind') == 'supplementary_contract':
            row['_jakks_supplementary'] = True
            row.setdefault('issues', []).append({
                'severity': 'warning', 'code': 'supplementary_contract', 'field': 'order_type',
                'message': '补充合同（箱唛资料）先行排产；未提供的价格保持空白，正式 PO 到齐后核对，避免重复排单。',
                'can_skip': False,
            })
        row['packaging'] = _text(record.get('product_packaging'))
        for field, label in (('standard', 'PRODUCT MEETS'), ('packaging', 'NOTES')):
            if row.get(field):
                row.setdefault('lineage', {})[field] = f"{record.get('source_file', '')} · PO {label}"
        row['reference_no'] = _text(record.get('confirmation_no')) or _text(record.get('contract_no'))
        row['_missing_confirmation'] = not _text(record.get('confirmation_no'))
        unit = _text(record.get('unit')).upper()
        if unit and unit not in {'PC', 'PCS', 'PCE', 'EA', 'EACH', '件', '个'}:
            row.setdefault('issues', []).append({
                'severity': 'blocked', 'code': 'unsupported_quantity_unit', 'field': 'quantity',
                'message': f'此单数量单位为 {unit}，不能按成品件数写入；请核对是否为 Jakks 客户 PO。',
                'can_skip': False,
            })
    elif customer_code == 'simba':
        contract, line = _text(record.get('contract_no')), _text(record.get('contract_line'))
        row['reference_no'] = f'{contract}/{line}' if contract and line and '/' not in contract else contract
    elif customer_code in {'spin', 'spin-master'}:
        row['reference_no'] = _text(record.get('unified_reference'))
        row['product_no'] = _text(record.get('material_group'))
    else:
        row['reference_no'] = _text(record.get('contract_no') or record.get('po_no'))
    aliases = {
        'carton_mark': ('carton_mark', 'shipping_mark'),
        'customer_label': ('customer_label',), 'date_code': ('date_code',),
        'container_type': ('container_type',), 'brand': ('brand',),
    }
    for field, sources in aliases.items():
        for source in sources:
            if record.get(source) not in (None, ''):
                row[field] = _text(record[source])
                break
    row.setdefault('lineage', {})['reference_no'] = f'华登 {customer_code} PO · 订单识别号'
    if customer_code == 'goliath':
        for field in ('unit_price_usd','amount_usd','barcode','po_order_date','remarks'):
            row[field] = _text(record.get(field))
            row['lineage'][field] = f"{record.get('source_file')} · {record.get('source_sheet')} · {field}"
        row['unit_price_hkd'] = str(Decimal(row['unit_price_usd']) * Decimal('7.75')) if row['unit_price_usd'] else ''
        row['lineage']['unit_price_hkd'] = 'Goliath Ai 方案 · USD × 7.75'
        row['customer_q'] = _text(record.get('customer_inspection_date'))
        if row.get('requested_ship_date'):
            code_date = date.fromisoformat(row['requested_ship_date']) - timedelta(days=10)
            while code_date.weekday() >= 5:
                code_date -= timedelta(days=1)
            row['date_code'] = f'RR{code_date.timetuple().tm_yday:03d}{code_date.year % 10}'
            row['lineage']['date_code'] = f'Goliath Ai 方案 · 走货期前10天，周末前移至{code_date.isoformat()}；节假日待复核'
            row.setdefault('issues', []).append({'severity':'warning','code':'holiday_calendar_review','field':'date_code','message':'日期码已按走货期前10天并避开周末计算，节假日待复核。','can_skip':False})
    return row


def map_huakang_d(row, order, line, customer_code):
    from app.services.customer_order_unified import _text, _number
    row['_regional_customer'] = customer_code
    row['reference_no'] = _text(order.get('po_number')) or _text(order.get('contract_no'))
    row['standard'] = _text(line.get('national_standard') or order.get('national_standard'))
    row['packaging'] = _text(line.get('packaging') or order.get('packaging'))
    if _number(row.get('units_per_carton')) in (None, 0):
        row['units_per_carton'] = ''
        row['carton_count'] = ''
    row.setdefault('lineage', {})['reference_no'] = '华康D PO · Purchase Order Number'
    return row


def reconcile_product(row, history, factory_id, customer_code):
    from app.services.customer_order_unified import _key, _text
    if (factory_id, customer_code) == ('huadeng', 'jakks') and row.get('_missing_confirmation') and _key(row.get('contract_no')) and _key(row.get('product_no')):
        references = {h.reference_no for h in history if _key(h.contract_no) == _key(row.get('contract_no')) and _key(h.product_no) == _key(row.get('product_no')) and h.reference_no}
        if len(references) == 1:
            row['reference_no'] = references.pop()
            row.setdefault('lineage', {})['reference_no'] = 'ITEM表 · 同合同同货号唯一历史确认号'
    if (factory_id, customer_code) != ('huadeng', 'casdon'):
        return
    product = _text(row.get('product_no'))
    # Customer-specific article suffixes are only reusable with matching version.
    def parts(value):
        match = re.fullmatch(r'([^(.（]+)(?:\.[^(（]+)?[（(]([^）)]+)[）)]', value)
        return (_key(match[1]), _key(match[2])) if match else None
    wanted = parts(product)
    if not wanted:
        return
    candidates = [h for h in history if parts(h.product_no) == wanted]
    same_po = [h for h in candidates if _key(h.reference_no) == _key(row.get('reference_no'))]
    same_customer = [h for h in candidates if _key(h.customer_name) == _key(row.get('customer_name'))]
    products = {h.product_no for h in same_po or same_customer}
    if len(products) == 1:
        row['product_no'] = products.pop()


def enrich(row, history, factory_id, customer_code):
    from app.services.customer_order_unified import _key, _text
    if (factory_id, customer_code) == ('huadeng', 'casdon'):
        for field in ('country', 'brand'):
            if _text(row.get(field)):
                continue
            values = {h.extras[field] for h in history if _key(h.product_no) == _key(row.get('product_no')) and h.extras.get(field)}
            if len(values) == 1:
                row[field] = values.pop()
                row.setdefault('lineage', {})[field] = f"ITEM表 · 货号 {row.get('product_no')} 唯一历史值"
    row['target_template'] = TARGET_TEMPLATE


def write_extras(sheet, row_number, row, factory_id, customer_code):
    for field, column in extra_columns(sheet, factory_id, customer_code).items():
        value = row.get(field)
        sheet.cell(row_number, column).value = value if value not in (None, '') else None
