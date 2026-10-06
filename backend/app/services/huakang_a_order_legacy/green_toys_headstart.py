from __future__ import annotations

import math
import re
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Iterable

from pypdf import PdfReader

from app.services.carton_mark import (
    find_tesseract_cmd,
    missing_tesseract_message,
    select_tesseract_language,
)
from app.services.huaxing_order_legacy.new_order_excel import (
    append_column_records_to_workbook,
    load_complete_workbook_compatible,
)


HEADSTART_SHEET_NAMES = ("2026年HS客排期表", "2026年HS客排期表 ")
GREEN_TOYS_SHEET_NAMES = ("2026年排期",)


class HuakangASpecialCustomerError(ValueError):
    """A Green Toys or HeadStart document cannot be mapped safely."""


@dataclass
class SpecialPreparedBatch:
    records: list[dict[str, Any]]
    warnings: list[str]
    sheet_name: str


@dataclass(frozen=True)
class _ScheduleLayout:
    sheet_names: tuple[str, ...]
    header_row: int
    max_col: int
    detail_columns: tuple[int, ...]
    po_column: int
    item_column: int
    description_column: int
    quantity_column: int
    carton_column: int


_LAYOUTS = {
    "green-toys": _ScheduleLayout(
        sheet_names=GREEN_TOYS_SHEET_NAMES,
        header_row=3,
        max_col=37,
        detail_columns=(2, 4, 8),
        po_column=2,
        item_column=4,
        description_column=7,
        quantity_column=8,
        carton_column=20,
    ),
    "headstart": _ScheduleLayout(
        sheet_names=HEADSTART_SHEET_NAMES,
        header_row=6,
        max_col=45,
        detail_columns=(3, 4, 7),
        po_column=3,
        item_column=4,
        description_column=5,
        quantity_column=7,
        carton_column=22,
    ),
}


_MONTHS = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _number(value: Any) -> float | int | None:
    if value in (None, ""):
        return None
    cleaned = re.sub(r"[^0-9.\-]", "", _text(value))
    if not cleaned or cleaned in {"-", "."}:
        return None
    try:
        number = Decimal(cleaned)
    except InvalidOperation:
        return None
    return int(number) if number == number.to_integral_value() else float(number)


def _iso_date(value: str) -> str:
    text = _text(value).replace("−", "-").replace("–", "-")
    for pattern in ("%d-%b-%y", "%d-%b-%Y", "%d %b %Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(text.title(), pattern).date().isoformat()
        except ValueError:
            continue
    return ""


def _date_value(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    normalized = _iso_date(_text(value))
    try:
        return date.fromisoformat(normalized or _text(value))
    except ValueError:
        return None


def _item_key(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", _text(value).upper().replace("−", "-"))


def _description_key(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", _text(value).upper())


def _quantity_key(value: Any) -> str:
    try:
        return format(Decimal(str(value)).normalize(), "f")
    except (InvalidOperation, TypeError, ValueError):
        return _text(value)


def _base_green_po(value: Any) -> str:
    text = _text(value).upper()
    return re.sub(r"-\d+$", "", text)


def _headstart_contract_key(value: Any) -> str:
    key = re.sub(r"[^A-Z0-9]", "", _text(value).upper())
    if len(key) == 10 and re.fullmatch(r"20\d{5}[A-Z]{3}", key) and key.endswith("A"):
        return key[:-1]
    return key


def _identity_key(customer_code: str, po: Any, item: Any) -> tuple[str, str]:
    order_key = (
        _base_green_po(po)
        if customer_code == "green-toys"
        else _headstart_contract_key(po)
    )
    return order_key, _item_key(item)


def _extract_headstart_text(content: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        raise HuakangASpecialCustomerError(f"无法读取 HeadStart PDF：{exc}") from exc


_HEADSTART_LINE_RE = re.compile(
    r"(?P<item>\d{5}(?:[-−]\d{4})?)\s+"
    r"(?P<description>.+?)\s+"
    r"(?P<quantity>\d[\d,]*)\s+"
    r"(?P<unit_price>\d+\.\d{2,4})\s+"
    r"(?P<amount>[\d,]+\.\d{2})\s*"
    r"(?P<delivery>\d{1,2}\s+[A-Z]{3}\s+\d{4})\s*"
    r"(?P<barcode>\d{12,14})\s+"
    r"(?P<carton_qty>\d+(?:\.\d+)?)\s+"
    r"(?P<cartons>\d+)",
    re.IGNORECASE,
)


def parse_headstart_pdf(file_name: str, content: bytes) -> list[dict[str, Any]]:
    text = _extract_headstart_text(content).replace("\u00a0", " ")
    normalized = text.replace("−", "-").replace("–", "-")
    order_match = re.search(r"\b(20\d{5}[A-Z]{2})\b\s*\nPURCHASE ORDER", normalized)
    if not order_match:
        order_match = re.search(r"\b20\d{5}[A-Z]{2}\b", normalized)
    order_no = order_match.group(1) if order_match else ""
    date_match = re.search(r"\b\d{1,2}-[A-Z]{3}-\d{2,4}\b", normalized, re.IGNORECASE)
    po_date = _iso_date(date_match.group(0)) if date_match else ""
    account_match = re.search(
        r"Account Code\s+Currency\s+Order Terms\s*\n\s*([A-Z0-9]+)",
        normalized,
        re.IGNORECASE,
    )
    account_code = account_match.group(1).upper() if account_match else ""
    date_code_match = re.search(r">\s*Date Code\s*:\s*([^\r\n]+)", normalized, re.IGNORECASE)
    date_code = _text(date_code_match.group(1)) if date_code_match else ""
    requirement_lines = [
        _text(line.lstrip("> "))
        for line in normalized.splitlines()
        if line.strip().startswith(">")
    ]

    records: list[dict[str, Any]] = []
    for match in _HEADSTART_LINE_RE.finditer(normalized):
        delivery = _iso_date(match.group("delivery"))
        inspection = _date_value(delivery)
        warnings: list[str] = []
        if not order_no:
            warnings.append("未识别合同号")
        if not delivery:
            warnings.append("未识别验货日期")
        record = {
            "file_name": file_name,
            "contract_no": order_no,
            "customer_po": "",
            "order_date": po_date,
            "item_no": match.group("item").replace("−", "-"),
            "description": re.sub(r"\s+", " ", match.group("description")).strip(),
            "quantity": _number(match.group("quantity")),
            "master_carton_qty": _number(match.group("carton_qty")),
            "total_cartons": _number(match.group("cartons")),
            "planned_inspection_date": delivery,
            "factory_commit_date": (
                (inspection + timedelta(days=7)).isoformat() if inspection else ""
            ),
            "unit_price_usd": _number(match.group("unit_price")),
            "amount_usd": _number(match.group("amount")),
            "barcode": match.group("barcode"),
            "date_code": date_code,
            "account_code": account_code,
            "country": "澳洲",
            "packaging": "；".join(requirement_lines),
            "parse_warnings": warnings,
            "parse_ok": not warnings,
        }
        records.append(record)
    if records:
        return records
    return [{
        "file_name": file_name,
        "contract_no": order_no,
        "order_date": po_date,
        "item_no": "",
        "description": "",
        "quantity": None,
        "parse_ok": False,
        "parse_warnings": ["未识别 HeadStart PO 明细"],
    }]


def _ocr_green_toys_image(path: Path) -> str:
    tesseract_cmd = find_tesseract_cmd()
    if not tesseract_cmd:
        raise HuakangASpecialCustomerError(missing_tesseract_message())
    language = select_tesseract_language(tesseract_cmd)
    try:
        completed = subprocess.run(
            [
                tesseract_cmd,
                str(path),
                "stdout",
                "-l",
                language,
                "--psm",
                "4",
                "-c",
                "preserve_interword_spaces=1",
            ],
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=45,
        )
    except Exception as exc:
        raise HuakangASpecialCustomerError(f"Green Toys 图片 OCR 失败：{exc}") from exc
    if completed.returncode != 0 or not completed.stdout.strip():
        detail = _text(completed.stderr) or "未识别到文字"
        raise HuakangASpecialCustomerError(f"Green Toys 图片 OCR 失败：{detail}")
    return completed.stdout


def _normalize_green_item(value: str) -> str:
    item = re.sub(r"[^A-Z0-9-]", "", value.upper())
    item = re.sub(r"^(DTK|FTK)OIR$", r"\g<1>01R", item)
    item = re.sub(r"^RBHI-", "RBH1-", item)
    return item


def _green_numeric_token(value: str) -> float | int | None:
    cleaned = re.sub(r"[^0-9.,]", "", value)
    if not cleaned:
        return None
    if cleaned.count(".") > 1:
        return None
    return _number(cleaned)


def _green_record(file_name, po_no, po_date, delivery, item, description, quantity, unit_price, warnings):
    ship_date = _date_value(delivery)
    problems = list(warnings)
    for value, message in ((po_no, '未识别 PO 号'), (item, '未识别货号'),
                           (quantity, '未识别数量'), (delivery, '未识别走货期'),
                           (unit_price, '未识别 USD 单价')):
        if not value:
            problems.append(message)
    return {
        'file_name': file_name, 'contract_no': po_no, 'customer_po': po_no,
        'order_date': po_date, 'item_no': item, '_ocr_item_no': item,
        'description': description, 'quantity': quantity,
        'planned_inspection_date': (ship_date - timedelta(days=1)).isoformat() if ship_date else '',
        'factory_commit_date': delivery, 'unit_price_usd': unit_price,
        'amount_usd': round(float(quantity) * float(unit_price), 2) if quantity and unit_price else None,
        'country': '美國', 'transportation_mode': "40'YT", 'parse_warnings': problems,
        'parse_ok': bool(po_no and item and quantity and delivery and unit_price),
    }


def _green_decimal(value: str) -> Decimal:
    token = value.strip().removeprefix('$').strip()
    if not re.fullmatch(r'(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?', token):
        raise HuakangASpecialCustomerError(f'Green Toys PO 数字无法确认：{value}')
    return Decimal(token.replace(',', ''))


def parse_green_toys_html(file_name: str, content: bytes) -> list[dict[str, Any]]:
    """Read static table evidence only; never execute scripts or fetch resources."""
    from lxml import html
    document = html.fromstring(content, parser=html.HTMLParser(no_network=True))
    for element in document.xpath('//script | //style'):
        element.drop_tree()
    if 'green toys' not in ' '.join(document.text_content().lower().split()):
        raise HuakangASpecialCustomerError('原始 HTML 不是 Green Toys PO')
    cells = lambda row: [' '.join(c.text_content().split()) for c in row.xpath('./td | ./th')]
    labels: dict[str, set[str]] = defaultdict(set)
    for row in document.xpath('//tr'):
        values = cells(row)
        if len(values) == 3 and values[0] in {'PO Date', 'PO #', 'Deliver By Date'}:
            labels[values[0]].add(values[-1])
    if any(len(labels[key]) != 1 for key in ('PO Date', 'PO #', 'Deliver By Date')):
        raise HuakangASpecialCustomerError('Green Toys HTML 的 PO号或日期缺失/不唯一')
    po_no = next(iter(labels['PO #']))
    po_date = _iso_date(next(iter(labels['PO Date'])))
    delivery = _iso_date(next(iter(labels['Deliver By Date'])))
    if not re.fullmatch(r'\d{4,}', po_no) or not po_date or not delivery:
        raise HuakangASpecialCustomerError('Green Toys HTML 的 PO号或日期无效')
    headers = ['Item', 'Description', 'Order Quantity', 'Received', 'Inventory Detail', 'Unit Price', 'Amount']
    tables = [table for table in document.xpath('//table')
              if any(cells(row) == headers for row in table.xpath('./tr | ./tbody/tr | ./thead/tr'))]
    if len(tables) != 1:
        raise HuakangASpecialCustomerError('Green Toys HTML 明细表缺失/不唯一')
    records, totals = [], []
    header_seen, total_seen = False, False
    for row in tables[0].xpath('./tr | ./tbody/tr | ./thead/tr | ./tfoot/tr'):
        values = cells(row)
        if values == headers:
            header_seen = True
            continue
        if not any(values):
            continue
        if values[0].casefold() == 'total':
            totals.append(_green_decimal(values[-1]))
            total_seen = True
            continue
        if not header_seen or total_seen or len(values) != 7:
            raise HuakangASpecialCustomerError('Green Toys HTML 存在无法确认的明细行')
        item, description = values[:2]
        if not re.fullmatch(r'[A-Z0-9][A-Z0-9-]{2,30}', item) or not description:
            raise HuakangASpecialCustomerError('Green Toys HTML 明细货号/品名不完整')
        quantity, unit_price, amount = (_green_decimal(values[i]) for i in (2, 5, 6))
        if quantity <= 0 or quantity != quantity.to_integral_value() or unit_price <= 0:
            raise HuakangASpecialCustomerError(f'{item}：数量或单价无效')
        if abs((quantity * unit_price).quantize(Decimal('0.01')) - amount) > Decimal('0.01'):
            raise HuakangASpecialCustomerError(f'{item}：数量×单价与原单金额不符')
        record = _green_record(file_name, po_no, po_date, delivery, item, description, int(quantity), float(unit_price), [])
        record['amount_usd'] = float(amount)
        record['customer_po'] = f'{po_no}-{len(records) + 1}'
        records.append(record)
    if not records or len(totals) != 1 or sum(Decimal(str(r['amount_usd'])) for r in records) != totals[0]:
        raise HuakangASpecialCustomerError('Green Toys HTML 明细合计与原单总金额不符或总金额缺失')
    return records


def parse_green_toys_po(file_name: str, content: bytes) -> list[dict[str, Any]]:
    if Path(file_name).suffix.lower() in {'.html', '.htm'}:
        return parse_green_toys_html(file_name, content)
    if Path(file_name).suffix.lower() not in {'.png', '.jpg', '.jpeg'}:
        raise HuakangASpecialCustomerError('Green Toys PO 只支持 HTML 或 PNG/JPG 图片')
    return parse_green_toys_image(file_name, content)


def parse_green_toys_ocr_text(
    file_name: str,
    text: str,
) -> list[dict[str, Any]]:
    po_match = re.search(r"\bPO\s*(?:#|No\.?|e)?\s*[:#]?\s*(\d{4,})\b", text, re.IGNORECASE)
    file_po = re.search(r"\d{4,}", Path(file_name).stem)
    po_no = (po_match.group(1) if po_match else "") or (file_po.group(0) if file_po else "")
    date_match = re.search(r"PO Date\s+(\d{1,2}/\d{1,2}/\d{4})", text, re.IGNORECASE)
    delivery_match = re.search(
        r"Deliver By Date\s+(\d{1,2}/\d{1,2}/\d{4})",
        text,
        re.IGNORECASE,
    )
    po_date = _iso_date(date_match.group(1)) if date_match else ""
    delivery = _iso_date(delivery_match.group(1)) if delivery_match else ""
    records: list[dict[str, Any]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        item_match = re.match(r"([A-Z0-9][A-Z0-9,.:\-]{2,20})(?:\s+(.+))?$", line, re.IGNORECASE)
        if not item_match:
            continue
        raw_item = item_match.group(1)
        if not re.search(r'[A-Z]', raw_item, re.I) or not re.search(r'\d', raw_item):
            continue
        item_no = _normalize_green_item(raw_item)
        rest = item_match.group(2) or ''
        # A right-hand numeric tail supports both single and preserved spacing.
        tail = re.fullmatch(r"(.+?)\s+(\d[\d,]*[|\]°]?)\s+(\d[\d,]*[|\]°]?)\s+(\d[\d,.]*)\s+(\$?[\d,.]+)", rest)
        spans = ([raw_item, tail[1], tail[2], tail[3], tail[4], tail[5]] if tail else
                 [raw_item] + [part.strip(' |') for part in re.split(r'\s{2,}', rest) if part.strip(' |')])
        quantity_index = next(
            (
                index
                for index, part in enumerate(spans[1:], start=1)
                if re.fullmatch(r"[\d,]+[|\]°]?", part.strip())
                and (_green_numeric_token(part) or 0) > 0
            ),
            None,
        )
        quantity = _green_numeric_token(spans[quantity_index]) if quantity_index is not None else None
        trailing = [
            number
            for part in spans[quantity_index + 1 :]
            if (number := _green_numeric_token(part)) not in (None, 0)
        ] if quantity_index is not None else []
        unit_price = float(trailing[0]) if trailing else None
        if unit_price is not None and unit_price >= 100 and float(unit_price).is_integer():
            unit_price /= 100
        if len(trailing) >= 2 and float(quantity):
            printed_amount = float(trailing[1])
            amount_unit_price = round(printed_amount / float(quantity), 4)
            if unit_price is not None and (abs(amount_unit_price - unit_price) <= 0.02
                    or ('.' not in spans[quantity_index + 2] and abs(amount_unit_price - unit_price / 10) <= 0.0001)):
                unit_price = amount_unit_price
        if unit_price is not None and unit_price > 20:
            unit_price = None
        description = re.sub(r"^[‘'\[]+", "", " ".join(spans[1:quantity_index]) if quantity_index is not None else rest).strip()
        line_number = len(records) + 1
        warnings = ["图片 PO 使用 OCR 识别，请复核货号、数量、价格和走货期"]
        record = _green_record(file_name, po_no, po_date, delivery, item_no, description, quantity, unit_price, warnings)
        record['customer_po'] = f'{po_no}-{line_number}' if po_no else ''
        records.append(record)
    if records:
        totals = re.findall(r'\bTotal\s+\$?\s*([\d,]+\.\d{2})\b', text, re.I)
        if totals:
            if len(totals) != 1 or any(r['amount_usd'] is None for r in records) or abs(
                sum(Decimal(str(r['amount_usd'])) for r in records) - _green_decimal(totals[0])
            ) > Decimal('0.01'):
                raise HuakangASpecialCustomerError('Green Toys OCR 明细与原单总金额不符，可能漏行；请上传原始 HTML 或清晰图片')
        else:
            for record in records:
                record['parse_warnings'].append('OCR 未识别原单总金额，无法校验是否漏行；建议上传原始 HTML')
        return records
    return [{
        "file_name": file_name,
        "contract_no": po_no,
        "customer_po": po_no,
        "order_date": po_date,
        "item_no": "",
        "description": "",
        "quantity": None,
        "factory_commit_date": delivery,
        "parse_ok": False,
        "parse_warnings": ["未识别 Green Toys PO 明细"],
    }]


def parse_green_toys_image(file_name: str, content: bytes) -> list[dict[str, Any]]:
    with TemporaryDirectory(prefix="green-toys-ocr-") as temp_dir:
        suffix = Path(file_name).suffix.lower() or ".png"
        path = Path(temp_dir) / f"po{suffix}"
        path.write_bytes(content)
        return parse_green_toys_ocr_text(file_name, _ocr_green_toys_image(path))


def _logical_rows(worksheet, *, header_row: int, max_col: int) -> Iterable[int]:
    return sorted({
        row_no
        for row_no, column_no in list(worksheet._cells)
        if row_no > header_row and column_no <= max_col
    })


def _unique_value(values: Iterable[Any]) -> Any:
    unique: dict[str, Any] = {}
    for value in values:
        text = _text(value)
        if text and not text.startswith("=") and text not in {"/", "-"}:
            unique.setdefault(text.casefold(), value)
    return next(iter(unique.values())) if len(unique) == 1 else None


def _schedule_snapshot(customer_code: str, schedule_content: bytes, file_name: str):
    layout = _LAYOUTS[customer_code]
    workbook = load_complete_workbook_compatible(schedule_content, filename=file_name)
    worksheet = next(
        (workbook[name] for name in layout.sheet_names if name in workbook.sheetnames),
        None,
    )
    if worksheet is None:
        workbook.close()
        raise HuakangASpecialCustomerError(
            f"排期缺少目标工作表：{' / '.join(layout.sheet_names)}"
        )
    detail_rows = [
        row_no
        for row_no in _logical_rows(
            worksheet,
            header_row=layout.header_row,
            max_col=layout.max_col,
        )
        if worksheet.cell(row_no, layout.po_column).value not in (None, "")
        and worksheet.cell(row_no, layout.item_column).value not in (None, "")
    ]
    return workbook, worksheet, layout, detail_rows


def _reconcile_green_item(
    record: dict[str, Any],
    item_rows: dict[str, list[dict[str, Any]]],
) -> str:
    raw_item = _item_key(record.get("item_no"))
    if raw_item in item_rows:
        return _text(item_rows[raw_item][0]["item_no"])
    source_description = _description_key(record.get("description"))
    if not source_description:
        return _text(record.get("item_no"))
    candidates: list[tuple[float, str]] = []
    for rows in item_rows.values():
        target_description = _description_key(_unique_value(row["description"] for row in rows))
        if not target_description:
            continue
        score = SequenceMatcher(None, source_description, target_description).ratio()
        candidates.append((score, _text(rows[0]["item_no"])))
    candidates.sort(reverse=True)
    if candidates and candidates[0][0] >= 0.82 and (
        len(candidates) == 1 or candidates[0][0] - candidates[1][0] >= 0.05
    ):
        return candidates[0][1]
    return _text(record.get("item_no"))


def prepare_special_batch(
    customer_code: str,
    po_files: list[tuple[str, bytes]],
    schedule_file_name: str,
    schedule_content: bytes,
) -> SpecialPreparedBatch:
    if customer_code not in _LAYOUTS:
        raise HuakangASpecialCustomerError(f"不支持的华康A特殊客户：{customer_code}")
    workbook, worksheet, layout, detail_rows = _schedule_snapshot(
        customer_code,
        schedule_content,
        schedule_file_name,
    )
    try:
        schedule_rows: list[dict[str, Any]] = []
        for row_no in detail_rows:
            base = {
                "row_no": row_no,
                "po": worksheet.cell(row_no, layout.po_column).value,
                "item_no": worksheet.cell(row_no, layout.item_column).value,
                "description": worksheet.cell(row_no, layout.description_column).value,
                "quantity": worksheet.cell(row_no, layout.quantity_column).value,
                "master_carton_qty": worksheet.cell(row_no, layout.carton_column).value,
            }
            if customer_code == "green-toys":
                base.update({
                    "product_name_zh": worksheet.cell(row_no, 6).value,
                    "country": worksheet.cell(row_no, 16).value,
                    "port": worksheet.cell(row_no, 17).value,
                })
            else:
                base.update({
                    "product_name": worksheet.cell(row_no, 5).value,
                    "customer_keycode": worksheet.cell(row_no, 18).value,
                    "contact": worksheet.cell(row_no, 20).value,
                    "country": worksheet.cell(row_no, 17).value,
                })
            schedule_rows.append(base)

        item_rows: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
        existing_by_identity: defaultdict[tuple[str, str], set[str]] = defaultdict(set)
        for row in schedule_rows:
            item_rows[_item_key(row["item_no"])].append(row)
            existing_by_identity[
                _identity_key(customer_code, row["po"], row["item_no"])
            ].add(_quantity_key(row["quantity"]))

        records: list[dict[str, Any]] = []
        warnings: list[str] = []
        for file_name, content in po_files:
            parsed = (
                parse_green_toys_po(file_name, content)
                if customer_code == "green-toys"
                else parse_headstart_pdf(file_name, content)
            )
            for record in parsed:
                record["_source_po_file_name"] = file_name
                if customer_code == "green-toys":
                    reconciled = _reconcile_green_item(record, item_rows)
                    if _item_key(reconciled) != _item_key(record.get("item_no")):
                        warnings.append(
                            f"{file_name}：OCR货号 {record.get('item_no')} 已按排期同品名校正为 {reconciled}"
                        )
                        record["item_no"] = reconciled
                matches = item_rows.get(_item_key(record.get("item_no")), [])
                record["master_carton_qty"] = (
                    record.get("master_carton_qty")
                    or _unique_value(row["master_carton_qty"] for row in matches)
                )
                if customer_code == "green-toys":
                    record["product_name_zh"] = _unique_value(
                        row.get("product_name_zh") for row in matches
                    )
                    record["country"] = (
                        _unique_value(row.get("country") for row in matches)
                        or record.get("country")
                    )
                    record["port"] = _unique_value(row.get("port") for row in matches)
                else:
                    record["product_name"] = (
                        _unique_value(row.get("product_name") for row in matches)
                        or record.get("description")
                    )
                    record["customer_keycode"] = (
                        _unique_value(row.get("customer_keycode") for row in matches)
                        or record.get("account_code")
                    )
                    record["contact"] = (
                        _unique_value(row.get("contact") for row in matches) or "Billie"
                    )
                    record["country"] = (
                        _unique_value(row.get("country") for row in matches)
                        or record.get("country")
                    )

                identity = _identity_key(
                    customer_code,
                    record.get("customer_po") if customer_code == "green-toys" else record.get("contract_no"),
                    record.get("item_no"),
                )
                existing_quantities = existing_by_identity.get(identity, set())
                quantity = _quantity_key(record.get("quantity"))
                if existing_quantities and quantity in existing_quantities:
                    record["_duplicate_existing"] = True
                elif existing_quantities:
                    record["_existing_quantity_conflict"] = True
                if not record.get("master_carton_qty"):
                    record.setdefault("parse_warnings", []).append("未找到外箱装箱数")
                    record["parse_ok"] = False
                records.append(record)
                warnings.extend(
                    f"{file_name}：{message}"
                    for message in record.get("parse_warnings") or []
                    if "OCR" not in _text(message)
                )
        return SpecialPreparedBatch(
            records=records,
            warnings=warnings,
            sheet_name=worksheet.title,
        )
    finally:
        workbook.close()


def total_cartons(record: dict[str, Any]) -> int | str:
    explicit = _number(record.get("total_cartons"))
    if explicit is not None:
        return int(explicit) if float(explicit).is_integer() else explicit
    quantity = _number(record.get("quantity"))
    carton_qty = _number(record.get("master_carton_qty"))
    if quantity is None or carton_qty in (None, 0):
        return ""
    return math.ceil(float(quantity) / float(carton_qty))


def preview_fields(customer_code: str, record: dict[str, Any]) -> dict[str, Any]:
    unit_usd = float(record.get("unit_price_usd") or 0)
    quantity = float(record.get("quantity") or 0)
    unit_hkd = round(unit_usd * 7.8, 4) if unit_usd else ""
    amount_hkd = round(unit_usd * quantity * 7.8, 2) if unit_usd and quantity else ""
    if customer_code == "green-toys":
        return {
            "po_no": record.get("customer_po"),
            "contract_no": record.get("contract_no"),
            "customer_name": "Green Toys",
            "country": record.get("country") or "美國",
            "product_no": record.get("item_no"),
            "product_name_zh": record.get("product_name_zh"),
            "product_name_en": record.get("description"),
            "quantity": record.get("quantity"),
            "units_per_carton": record.get("master_carton_qty"),
            "carton_count": total_cartons(record),
            "standard": f"USD {unit_usd:g}" if unit_usd else "",
            "unit_price_hkd": unit_hkd,
            "amount_hkd": amount_hkd,
            "packaging": "40'YT",
            "line_q": record.get("planned_inspection_date"),
            "customer_q": "",
            "requested_ship_date": record.get("factory_commit_date"),
        }
    return {
        "po_no": record.get("customer_po"),
        "contract_no": record.get("contract_no"),
        "customer_name": "HeadStart",
        "country": record.get("country") or "澳洲",
        "product_no": record.get("item_no"),
        "product_name_zh": "",
        "product_name_en": record.get("product_name") or record.get("description"),
        "quantity": record.get("quantity"),
        "units_per_carton": record.get("master_carton_qty"),
        "carton_count": total_cartons(record),
        "standard": "；".join(
            value
            for value in (
                f"Date Code {record.get('date_code')}" if record.get("date_code") else "",
                f"APN {record.get('barcode')}" if record.get("barcode") else "",
                f"USD {unit_usd:g}" if unit_usd else "",
            )
            if value
        ),
        "unit_price_hkd": unit_hkd,
        "amount_hkd": amount_hkd,
        "packaging": record.get("packaging"),
        "line_q": record.get("planned_inspection_date"),
        "customer_q": "",
        "requested_ship_date": record.get("factory_commit_date"),
    }


def issues_for_record(
    customer_code: str,
    customer_name: str,
    record: dict[str, Any],
    row_id: str,
) -> list[dict[str, Any]]:
    field_by_message = {
        "未识别 PO 号": "po_no",
        "未识别合同号": "contract_no",
        "未识别货号": "product_no",
        "未识别数量": "quantity",
        "未识别走货期": "requested_ship_date",
        "未识别验货日期": "line_q",
        "未找到外箱装箱数": "units_per_carton",
        "未识别 HeadStart PO 明细": "row",
        "未识别 Green Toys PO 明细": "row",
    }
    issues: list[dict[str, Any]] = []
    for index, message in enumerate(record.get("parse_warnings") or [], start=1):
        field = field_by_message.get(_text(message), "row")
        is_ocr_review = "OCR" in _text(message)
        code = ("ocr_review" if index == 1 else f"ocr_review_{index}") if is_ocr_review else (
            f"missing_{field}" if field != "row" else f"parse_warning_{index}"
        )
        issues.append({
            "severity": "warning" if is_ocr_review else "blocked",
            "code": code,
            "field": field,
            "message": _text(message) or "PO 字段需要人工复核",
            "can_skip": False,
            "skip_key": f"{row_id}:{code}",
            "skip_label": "",
        })
    if not record.get("parse_ok") and not any(
        issue["severity"] == "blocked" for issue in issues
    ):
        issues.append({
            "severity": "blocked",
            "code": "parse_failed",
            "field": "row",
            "message": "PO 关键字段解析失败",
            "can_skip": False,
            "skip_key": f"{row_id}:parse_failed",
            "skip_label": "",
        })
    if record.get("_existing_quantity_conflict"):
        issues.append({
            "severity": "blocked",
            "code": "existing_quantity_conflict",
            "field": "quantity",
            "message": f"相同{('PO' if customer_code == 'green-toys' else '合同')}及货号已存在排期，但数量不同；按修改/补单阻断",
            "can_skip": False,
            "skip_key": f"{row_id}:existing_quantity_conflict",
            "skip_label": "",
        })
    if record.get("_duplicate_existing"):
        identity = "；".join(
            value
            for value in (
                _text(record.get("customer_po") or record.get("contract_no")),
                _text(record.get("item_no")),
            )
            if value
        ) or "当前订单"
        issues.append({
            "severity": "blocked",
            "code": "duplicate_existing_order",
            "field": "contract_no",
            "message": f"{identity} 已存在当前华康A {customer_name}排期；测试阶段可人工确认后重复导入",
            "can_skip": True,
            "skip_key": f"{row_id}:duplicate_existing_order",
            "skip_label": "测试阶段确认重复导入当前排期已有订单",
        })
    return issues


def _green_row_values(record: dict[str, Any], row_no: int, received_date: str) -> dict[int, Any]:
    unit = float(record.get("unit_price_usd") or 0)
    return {
        1: _date_value(received_date),
        2: record.get("customer_po"),
        3: "GT",
        4: record.get("item_no"),
        5: record.get("item_no"),
        6: record.get("product_name_zh"),
        7: record.get("description"),
        8: _number(record.get("quantity")),
        10: _date_value(record.get("planned_inspection_date")),
        12: _date_value(record.get("factory_commit_date")),
        13: "/",
        14: "GT箱唛",
        16: record.get("country") or "美國",
        17: record.get("port"),
        18: "/",
        20: _number(record.get("master_carton_qty")),
        21: f"=CEILING(H{row_no}/T{row_no},1)",
        22: "40'YT",
        23: unit or None,
        24: f"=W{row_no}*H{row_no}",
        25: f"=W{row_no}*7.8",
        26: f"=Y{row_no}*H{row_no}",
        29: "已入",
    }


def _headstart_row_values(record: dict[str, Any], row_no: int, received_date: str) -> dict[int, Any]:
    return {
        1: "Headstart",
        2: _date_value(received_date),
        3: record.get("contract_no"),
        4: record.get("item_no"),
        5: record.get("product_name") or record.get("description"),
        7: _number(record.get("quantity")),
        11: _date_value(record.get("planned_inspection_date")),
        12: _date_value(record.get("factory_commit_date")),
        16: record.get("packaging"),
        17: record.get("country") or "澳洲",
        18: record.get("customer_keycode"),
        19: "/",
        20: record.get("contact") or "Billie",
        22: _number(record.get("master_carton_qty")),
        24: f"=G{row_no}/V{row_no}",
        25: record.get("date_code"),
        26: record.get("barcode"),
        27: _number(record.get("unit_price_usd")),
        28: f"=AA{row_no}*G{row_no}",
        29: f"=AA{row_no}*7.8",
        30: f"=AC{row_no}*G{row_no}",
        33: "已入",
        34: record.get("item_no"),
    }


def export_special_schedule(
    customer_code: str,
    records: list[dict[str, Any]],
    *,
    received_date: str,
    schedule_file_name: str,
    schedule_content: bytes,
    output_path: Path,
) -> dict[str, Any]:
    layout = _LAYOUTS[customer_code]
    if customer_code == "green-toys":
        row_values = lambda record, row_no: _green_row_values(record, row_no, received_date)
        group_values = lambda record, _row_no: {
            1: " ".join(
                value
                for value in (
                    _text(record.get("item_no")),
                    _text(record.get("product_name_zh") or record.get("description")),
                )
                if value
            )
        }
    else:
        row_values = lambda record, row_no: _headstart_row_values(record, row_no, received_date)
        group_values = lambda record, _row_no: {
            1: record.get("item_no"),
            2: record.get("product_name") or record.get("description"),
        }
    return append_column_records_to_workbook(
        schedule_content,
        output_path,
        records,
        filename=schedule_file_name,
        sheet_names=layout.sheet_names,
        header_row=layout.header_row,
        max_col=layout.max_col,
        detail_columns=layout.detail_columns,
        row_values_factory=row_values,
        group_key_factory=lambda record: _item_key(record.get("item_no")),
        group_row_values_factory=group_values,
        new_row_fill_color="CCFFCC",
    )
