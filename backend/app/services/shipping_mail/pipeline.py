"""Turn realistic shipping emails and their attachments into reviewable fields and items."""
import copy
import hashlib
import re
from datetime import datetime
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .documents import read_docx_text, read_pdf_ocr_text, read_pdf_tables, read_pdf_text, read_xls_rows, read_xlsx_rows
from .email import read_eml
from .fields import PARSER_VERSION, _contract_tails, extract_fields

PACKING_SUFFIXES = {'.xlsx', '.xlsm', '.xls', '.pdf', '.docx'}
_BRAND_NAMES = ('ZURU', 'BUZZBEE', 'PLAYMATES', 'MOOSE', 'SPIN MASTER', 'HASBRO', 'MATTEL', 'TOMY', 'BUKI', 'DICKIE', 'SIMBA')
_HEADER_ALIASES = {
    'product_code': ('货号', 'item', 'item no', 'itemno', 'product code', 'sku', '款号', '产品编号'),
    'product_name': ('品名', 'description', '产品名称', '货名', 'name'),
    'customer_po': ('客户po', 'customer po', 'po', 'po no', 'po#', '订单号'),
    'quantity': ('数量', 'qty', 'quantity', '订单数量', 'order qty'),
    'cartons': ('箱数', 'cartons', 'ctns', '件数', 'no of carton'),
    'cbm': ('cbm', '体积', 'volume'),
    'gross_weight': ('毛重', 'gross weight', 'g.w', 'gw'),
    'net_weight': ('净重', 'net weight', 'n.w', 'nw'),
}


_CONTRACT_IN_FILENAME = re.compile(r"(?<![A-Z0-9])([A-Z]{2,12}-\d{4,})(?=[-_.]|$)", re.I)


def _contract_from_filename(filename: str) -> str:
    match = _CONTRACT_IN_FILENAME.search(Path(filename).stem)
    return match.group(1) if match else ''


def parse_shipping_email(raw: bytes, filename: str = 'message.eml', *, received_at: str = '') -> dict:
    message = read_eml(raw)
    contact = received_at or message.received_at
    body = f'{message.subject}\n{message.body_text}'
    extraction = extract_fields(body, received_at=contact)
    fields = extraction.fields
    if not fields.get('brand'):
        subject_upper = message.subject.upper()
        for brand in _BRAND_NAMES:
            if brand in subject_upper:
                fields['brand'] = brand
                break
    warnings = list(extraction.warnings)
    trace = list(extraction.trace)
    items: list[dict] = []
    attachments: list[dict] = []
    booking_fields: dict = {}
    def parse_one(attachment):
        return _parse_attachment(attachment.filename, attachment.data)

    workers = min(4, len(message.attachments)) or 1
    with ThreadPoolExecutor(max_workers=workers) as pool:
        parsed_attachments = list(pool.map(parse_one, message.attachments))

    for attachment, parsed in zip(message.attachments, parsed_attachments):
        attachments.append(parsed)
        warnings.extend(parsed['warnings'])
        items.extend(parsed['items'])
        if parsed.get('kind') == 'booking':
            for key, value in (parsed.get('fields') or {}).items():
                if value:
                    booking_fields[key] = value
        # 正文里的最新指令优先，附件只补正文缺失的字段。
        for key, value in (parsed.get('fields') or {}).items():
            if value and not fields.get(key):
                fields[key] = value
    if booking_fields:
        fields.update(booking_fields)
        fields['table_name'] = f"{fields.get('terminal') or fields.get('port') or '待定码头'}SO排期表"
    if fields.get('so_number'):
        warnings = [w for w in warnings if 'SO/BN' not in w]
    if fields.get('si_deadline'):
        warnings = [w for w in warnings if 'SI 截止' not in w]
    if fields.get('cutoff_date'):
        warnings = [w for w in warnings if '截关' not in w]
    if items and not fields.get('cargo_source'):
        fields['cargo_source'] = 'attachment'
    warnings = _dedupe(warnings)
    return {
        'filename': filename,
        'fingerprint': message.fingerprint,
        'subject': message.subject,
        'sender': message.sender,
        'received_at': contact,
        'fields': fields,
        'items': items,
        'attachments': attachments,
        'warnings': warnings,
        'rule_trace': trace,
        'parser_version': PARSER_VERSION,
    }


def parse_shipping_document(data: bytes, filename: str) -> dict:
    """Parse one attachment on its own, for direct upload or preview."""
    parsed = _parse_attachment(filename, data)
    return {
        'filename': filename,
        'fields': parsed.get('fields') or {},
        'items': parsed['items'],
        'warnings': parsed['warnings'],
        'kind': parsed['kind'],
        'status': parsed['status'],
        'parser_version': PARSER_VERSION,
    }


_ATTACHMENT_CACHE: dict[tuple[str, str], dict] = {}
_ATTACHMENT_CACHE_LOCK = threading.Lock()


def _parse_attachment(filename: str, data: bytes) -> dict:
    key = (filename, hashlib.sha256(data).hexdigest())
    with _ATTACHMENT_CACHE_LOCK:
        cached = _ATTACHMENT_CACHE.get(key)
    if cached is not None:
        return copy.deepcopy(cached)
    result = _parse_attachment_uncached(filename, data)
    with _ATTACHMENT_CACHE_LOCK:
        if len(_ATTACHMENT_CACHE) >= 128:
            _ATTACHMENT_CACHE.clear()
        _ATTACHMENT_CACHE[key] = result
    return copy.deepcopy(result)


_DELIVERY_ORDER = re.compile(r'Delivery\s+order|送货单号|入仓通知', re.I)


def _delivery_date(text: str) -> str:
    match = re.search(r'Delivery\s+Date\s*[:：]\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4})', text, re.I)
    if not match:
        return ''
    try:
        return datetime.strptime(match.group(1), '%d %B %Y').date().isoformat()
    except ValueError:
        try:
            return datetime.strptime(match.group(1), '%d %b %Y').date().isoformat()
        except ValueError:
            return ''


def _delivery_order_items(tables: list[list[list]]) -> list[dict]:
    for table in tables:
        header_index = None
        for index, row in enumerate(table):
            headers = [str(cell or '').strip().lower() for cell in row]
            if 'item no.' in headers and 'qty' in headers:
                header_index = index
                break
        if header_index is None:
            continue
        header = [str(cell or '').strip().lower() for cell in table[header_index]]
        def column(name: str, fallback: int) -> int:
            for i, cell in enumerate(header):
                if cell == name:
                    return i
            return fallback
        col_no = column('no', 0)
        col_contract = column('s/c number', 1)
        col_item = column('item no.', 3)
        col_qty = column('qty', 4)
        col_ctns = column('ctns', 5)
        col_cbm = column('cbm', 6)
        col_po = column('po number', 7)
        col_material = column('cust. material', 8)
        col_remark = column('remark', 9)
        items = []
        for row in table[header_index + 1:]:
            if not row or not str(row[col_no] or '').strip():
                continue
            item = str(row[col_item] or '').strip() if col_item < len(row) else ''
            if not item:
                continue
            def value(index: int) -> str:
                return str(row[index] or '').strip() if index < len(row) else ''
            def number(index: int):
                try:
                    return float(value(index)) if value(index) else None
                except ValueError:
                    return None
            items.append({
                'product_code': item,
                'product_name': '',
                'quantity': number(col_qty),
                'cartons': number(col_ctns),
                'cbm': number(col_cbm),
                'contract_no': value(col_contract),
                'customer_po': value(col_po),
                'remark': ' '.join(part for part in (value(col_material), value(col_remark)) if part),
            })
        if items:
            return items
    return []


def _parse_delivery_order(filename: str, data: bytes, text: str) -> dict:
    tables = read_pdf_tables(data)
    items = _delivery_order_items(tables)
    customer = ''
    match = re.search(r'Customer\s+([^\n]+)', text, re.I)
    if match:
        customer = re.sub(r'\s+', ' ', match.group(1)).strip()
    do_no = ''
    match = re.search(r'Delivery\s+order\s+No\.?\s*[:：]?\s*([A-Z0-9-]+)', text, re.I)
    if match:
        do_no = match.group(1).strip()
    if not do_no:
        match = re.search(r'送货单号\s*([A-Z0-9-]+)', text)
        if match:
            do_no = match.group(1).strip()
    contract = items[0].get('contract_no') if items else ''
    delivery_date = _delivery_date(text)
    fields = {
        'so_number': do_no,
        'booking_no': do_no,
        'contract_no': contract or '',
        'contract_tails': _contract_tails(contract or ''),
        'customer': customer,
        'brand': customer,
        'planned_ship_date': delivery_date,
        'ship_date': delivery_date,
        'shipment_mode': 'warehouse',
        'cargo_source': 'attachment',
    }
    warnings = [] if items else ['未识别到入仓单商品明细，请人工确认表格格式']
    return {
        'filename': filename,
        'kind': 'delivery_order',
        'status': 'parsed',
        'fields': fields,
        'items': items,
        'warnings': warnings,
        'text': text,
    }


def _parse_attachment_uncached(filename: str, data: bytes) -> dict:
    suffix = Path(filename).suffix.lower()
    empty = {'filename': filename, 'kind': 'unknown', 'status': 'ignored', 'fields': {}, 'items': [], 'warnings': []}
    if suffix not in PACKING_SUFFIXES:
        empty['warnings'] = [f'未解析附件类型：{filename}']
        return empty
    if suffix in ('.xlsx', '.xlsm', '.xls'):
        try:
            rows = read_xls_rows(data) if suffix == '.xls' else read_xlsx_rows(data)
        except Exception as error:  # noqa: BLE001 - 单个附件失败不能中断整封邮件
            return {**empty, 'status': 'failed', 'warnings': [f'Excel 附件读取失败：{filename}（{type(error).__name__}）']}
        items = _packing_items(rows, filename)
        warnings = [] if items else [f'已读取 {filename}，但未识别到货号/数量列，请人工确认表格格式']
        return {'filename': filename, 'kind': 'packing_list', 'status': 'parsed', 'fields': {}, 'items': items, 'warnings': warnings}
    if suffix == '.pdf':
        document = read_pdf_text(data)
        if _DELIVERY_ORDER.search(document.text):
            return _parse_delivery_order(filename, data, document.text)
        if document.scanned:
            try:
                document = read_pdf_ocr_text(data)
            except Exception as error:  # noqa: BLE001
                return {
                    'filename': filename, 'kind': 'scanned_document', 'status': 'needs_ocr',
                    'fields': {}, 'items': [],
                    'warnings': [f'{filename} 是扫描件，OCR 失败（{type(error).__name__}），需人工录入'],
                }
            if not document.text:
                return {
                    'filename': filename, 'kind': 'scanned_document', 'status': 'needs_ocr',
                    'fields': {}, 'items': [],
                    'warnings': [f'{filename} 是扫描件，OCR 未识别到文字，需人工录入'],
                }
        extraction = extract_fields(document.text)
        if not extraction.fields.get('contract_no'):
            file_contract = _contract_from_filename(filename)
            if file_contract:
                extraction.fields['contract_no'] = file_contract
                extraction.fields['contract_tails'] = _contract_tails(file_contract)
        return {
            'filename': filename, 'kind': 'booking', 'status': 'parsed',
            'fields': extraction.fields, 'items': [], 'warnings': extraction.warnings,
            'text': document.text,
        }
    try:
        text = read_docx_text(data)
    except Exception as error:  # noqa: BLE001
        return {**empty, 'status': 'failed', 'warnings': [f'Word 附件读取失败：{filename}（{type(error).__name__}）']}
    extraction = extract_fields(text)
    return {
        'filename': filename, 'kind': 'text_document', 'status': 'parsed',
        'fields': extraction.fields, 'items': [], 'warnings': extraction.warnings,
        'text': text,
    }


def _packing_items(rows: list[list], filename: str) -> list[dict]:
    for index, row in enumerate(rows[:40]):
        headers = [str(cell or '').strip().lower() for cell in row]
        mapping = _column_map(headers)
        if len(mapping) < 2 or 'product_code' not in mapping:
            continue
        items = []
        for values in rows[index + 1:]:
            item = _row_item(values, mapping, filename)
            if item:
                items.append(item)
        return items
    return []


def _column_map(headers: list[str]) -> dict:
    mapping: dict[str, int] = {}
    for field, aliases in _HEADER_ALIASES.items():
        for position, header in enumerate(headers):
            if any(header == alias or (len(alias) > 2 and alias in header) for alias in aliases):
                mapping.setdefault(field, position)
                break
    return mapping


def _row_item(values, mapping: dict, filename: str) -> dict | None:
    def cell(field: str):
        index = mapping.get(field)
        return values[index] if index is not None and index < len(values) else None

    code = str(cell('product_code') or '').strip()
    if not code or code.lower() in {'合计', 'total', '小计'}:
        return None
    quantity = _number(cell('quantity'))
    cartons = _number(cell('cartons'))
    if quantity is None and cartons is None:
        return None
    return {
        'product_code': code,
        'product_name': str(cell('product_name') or '').strip(),
        'customer_po': str(cell('customer_po') or '').strip(),
        'quantity': quantity,
        'cartons': cartons,
        'cbm': _number(cell('cbm')),
        'gross_weight': _number(cell('gross_weight')),
        'net_weight': _number(cell('net_weight')),
        'source_file': filename,
    }


def _number(value) -> float | None:
    if value is None or value == '':
        return None
    try:
        return float(str(value).replace(',', '').strip())
    except ValueError:
        return None


def _dedupe(values: list[str]) -> list[str]:
    seen: list[str] = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return seen


def looks_like_email(filename: str) -> bool:
    return bool(re.search(r'\.eml$', filename, re.I))
