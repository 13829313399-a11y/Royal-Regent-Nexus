"""Turn realistic shipping emails and their attachments into reviewable fields and items."""
import re
from pathlib import Path

from .documents import read_docx_text, read_pdf_ocr_text, read_pdf_text, read_xlsx_rows
from .email import read_eml
from .fields import PARSER_VERSION, extract_fields

PACKING_SUFFIXES = {'.xlsx', '.xlsm', '.pdf', '.docx'}
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


def parse_shipping_email(raw: bytes, filename: str = 'message.eml', *, received_at: str = '') -> dict:
    message = read_eml(raw)
    contact = received_at or message.received_at
    body = f'{message.subject}\n{message.body_text}'
    extraction = extract_fields(body, received_at=contact)
    fields = extraction.fields
    warnings = list(extraction.warnings)
    trace = list(extraction.trace)
    items: list[dict] = []
    attachments: list[dict] = []
    booking_fields: dict = {}
    for attachment in message.attachments:
        parsed = _parse_attachment(attachment.filename, attachment.data)
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


def _parse_attachment(filename: str, data: bytes) -> dict:
    suffix = Path(filename).suffix.lower()
    empty = {'filename': filename, 'kind': 'unknown', 'status': 'ignored', 'fields': {}, 'items': [], 'warnings': []}
    if suffix not in PACKING_SUFFIXES:
        empty['warnings'] = [f'未解析附件类型：{filename}']
        return empty
    if suffix in ('.xlsx', '.xlsm'):
        try:
            rows = read_xlsx_rows(data)
        except Exception as error:  # noqa: BLE001 - 单个附件失败不能中断整封邮件
            return {**empty, 'status': 'failed', 'warnings': [f'Excel 附件读取失败：{filename}（{type(error).__name__}）']}
        items = _packing_items(rows, filename)
        warnings = [] if items else [f'已读取 {filename}，但未识别到货号/数量列，请人工确认表格格式']
        return {'filename': filename, 'kind': 'packing_list', 'status': 'parsed', 'fields': {}, 'items': items, 'warnings': warnings}
    if suffix == '.pdf':
        document = read_pdf_text(data)
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
