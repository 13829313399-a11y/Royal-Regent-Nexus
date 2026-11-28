"""Current workbench schedule in the approved, date-filterable worksheet."""
from datetime import date
from hashlib import sha256
import hmac
from io import BytesIO
from math import isclose
from pathlib import Path
import re

from fastapi import HTTPException
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from openpyxl.drawing.image import Image
from openpyxl.drawing.spreadsheet_drawing import AnchorMarker, TwoCellAnchor
from openpyxl.packaging.custom import StringProperty
from openpyxl.utils.units import pixels_to_EMU
from app.core.config import settings
from app.services.qc_monthly_excel import _photo_slots, PHOTO_PADDING

from app.services.qc_inspection_print import as_date, fit_record_text, quantity_value, saved_records

TEMPLATE = Path(__file__).resolve().parents[1] / 'templates/qc-schedule/inspection-desk.xlsx'
ORDER_FIELDS = ('customer', 'poNo', 'country', 'productNo', 'productName', 'quantity',
                'unitsPerCarton', 'cartonCount', 'production', 'agency', 'customerPo')
PHOTO_PROOF_PREFIX = 'QcAnnotatedPhotoSource_'
PHOTO_PROOF_PATTERN = re.compile(r'([a-f0-9]{64}):([a-f0-9]{64}):([a-f0-9]{64})')


def photo_group_digest(digests):
    return sha256(','.join(sorted(digests)).encode()).hexdigest()


def sign_photo_proof(key, factory, rendered, source):
    return hmac.new(key, f'qc-schedule-photo-source-v1:{factory}:{rendered}:{source}'.encode(), sha256).hexdigest()


def photo_source_proofs(book, factory):
    """Verify both the factory and the exact exported images before trusting their source."""
    key = settings.qc_department_gateway_token.get_secret_value().encode()
    proofs = {}
    if factory and key:
        for prop in book.custom_doc_props:
            if not isinstance(prop, StringProperty) or not prop.name.startswith(PHOTO_PROOF_PREFIX):
                continue
            if match := PHOTO_PROOF_PATTERN.fullmatch(prop.value):
                rendered, source, signature = match.groups()
                if hmac.compare_digest(signature, sign_photo_proof(key, factory, rendered, source)):
                    proofs.setdefault(rendered, set()).add(source)
    return proofs


def add_photos(sheet, row, photos):
    if not photos:
        return
    width = int(sheet.column_dimensions['Q'].width * 7) - 5
    height = min(530, 84 * len(photos))
    sheet.row_dimensions[row].height = max(sheet.row_dimensions[row].height, height * .75)
    cols, slot_w, slot_h = _photo_slots(len(photos), width, height)
    for i, content in enumerate(photos):
        image = Image(BytesIO(content))
        scale = min(slot_w / image.width, slot_h / image.height, 1)
        w, h = image.width * scale, image.height * scale
        x = PHOTO_PADDING + (i % cols) * (slot_w + PHOTO_PADDING) + (slot_w - w) / 2
        y = PHOTO_PADDING + (i // cols) * (slot_h + PHOTO_PADDING) + (slot_h - h) / 2
        origin = AnchorMarker(col=16, row=row - 1, colOff=pixels_to_EMU(x), rowOff=pixels_to_EMU(y))
        end = AnchorMarker(col=16, row=row - 1, colOff=pixels_to_EMU(x + w), rowOff=pixels_to_EMU(y + h))
        image.anchor = TwoCellAnchor(_from=origin, to=end)
        sheet.add_image(image)


def date_label(start, end):
    if not start or start == end or not end:
        return start or end
    if start.year == end.year and start.month == end.month:
        return f'{start.month}月{start.day}日-{end.day}日'
    return f'{start.isoformat()} 至 {end.isoformat()}'


def export(factory, body):
    if set(body) != {'entries'}:
        raise HTTPException(422, '排期表导出参数不正确')
    return schedule_workbook(saved_records(factory, body['entries']), factory=factory)


def schedule_workbook(records, *, factory=None):
    book = load_workbook(TEMPLATE)
    sheet = book.active
    styles = [cell._style for cell in sheet[7]]
    widths = {i: sheet.column_dimensions[get_column_letter(i)].width for i in range(1, 19)}
    dates = []
    key = settings.qc_department_gateway_token.get_secret_value().encode() if factory else b''
    records.sort(key=lambda r: as_date(r.get('dateFrom')) or as_date(r.get('dateTo')) or date.max)
    for row, record in enumerate(records, 7):
        start, end = (as_date(record.get(k)) for k in ('dateFrom', 'dateTo'))
        dates.extend(d for d in (start, end) if d)
        execution = record.get('inspectionExecution') or {}
        sample = execution.get('sampleQuantity')
        inspector = execution.get('inspector')
        values = [date_label(start, end), *(record.get(key) for key in ORDER_FIELDS),
                  record.get('result'), record.get('sampleQuantity') if sample is None else sample,
                  record.get('inspectionProblem'), record.get('remark'), None,
                  record.get('inspector') if inspector is None else inspector]
        sheet.row_dimensions[row].height = 23
        for col, (value, style) in enumerate(zip(values, styles), 1):
            cell = sheet.cell(row, col)
            cell._style = style
            if col in (7, 8, 9, 14):
                value = quantity_value(value)
                if isinstance(value, float) and not value.is_integer():
                    cell.number_format = '#,##0.########'
            elif col != 1 and value is not None:
                value = str(value)
            cell.value = value if value != '' else None
            if isinstance(cell.value, str):
                cell.data_type = 's'
        qty, pack, cartons = (sheet.cell(row, c).value for c in (7, 8, 9))
        if all(type(v) in (int, float) for v in (qty, pack, cartons)) and pack and isclose(qty / pack, cartons, rel_tol=0, abs_tol=1e-9):
            sheet.cell(row, 9).value = f'=G{row}/H{row}'
        fit_record_text(sheet, row, values, widths)
        photos = record.get('photos') or []
        add_photos(sheet, row, photos)
        if key and (source_digests := record.get('annotatedPhotoSource')):
            source = photo_group_digest(source_digests)
            rendered = photo_group_digest(sha256(photo).hexdigest() for photo in photos)
            signature = sign_photo_proof(key, factory, rendered, source)
            book.custom_doc_props.append(StringProperty(name=PHOTO_PROOF_PREFIX + str(row),
                                                        value=f'{rendered}:{source}:{signature}'))
    if dates:
        start, end = min(dates), max(dates)
        sheet['A3'] = f'{start.year}年{start.month}月{start.day}日'
        if start != end:
            year = f'{end.year}年' if start.year != end.year else ''
            sheet['A3'] = f'{sheet["A3"].value} 至 {year}{end.month}月{end.day}日'
    sheet.auto_filter.ref = f'A6:R{sheet.max_row}'
    sheet.print_area = f'A1:R{sheet.max_row}'
    stream = BytesIO()
    book.save(stream)
    return stream.getvalue()
