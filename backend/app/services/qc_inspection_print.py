"""Fill the confirmed inspection print worksheets from saved workbench records."""
from base64 import b64encode
from collections import defaultdict
from contextlib import closing
from copy import copy
from datetime import date
from io import BytesIO
import math
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Lock
from unicodedata import east_asian_width
from xml.sax.saxutils import escape

from fastapi import HTTPException
from openpyxl import load_workbook
from openpyxl.formula.translate import Translator
from pypdfium2 import PdfDocument
from PIL import Image, ImageOps

from app.services import qc_inspection_sheet as journal
from app.services.document_tools.office_engine import office_executable

TEMPLATES = ('各客验货排期', '各客验货排期 (2)')
FIELDS = ('actualDate', 'customer', 'poNo', 'country', 'productNo', 'productName',
          'quantity', 'unitsPerCarton', 'cartonCount', 'production', 'agency',
          'customerPo', 'result', 'remark')
HEADERS = ('日期', '客户', 'PO#', '出口国', '货号', '产品名称', '数量', '装箱',
           '箱数', '生产', '机构', '客PO#', '完成情况', '备注')
MAX_RECORDS = 500
MAX_PAGES = 60
PDF_RENDER_LOCK = Lock()


def saved_records(factory, entries):
    if not isinstance(entries, list) or not entries or len(entries) > MAX_RECORDS:
        raise HTTPException(422, f'请选择 1 至 {MAX_RECORDS} 条验货记录')
    requested = {}
    for entry in entries:
        if (not isinstance(entry, dict) or set(entry) != {'id', 'revision'}
                or not isinstance(entry['id'], str) or not re.fullmatch(r'[a-f0-9]{32}', entry['id'])
                or type(entry['revision']) is not int or entry['revision'] < 0 or entry['id'] in requested):
            raise HTTPException(422, '打印记录编号或版本不正确')
        requested[entry['id']] = entry['revision']
    path = journal.database_path()
    if not path.is_file():
        raise HTTPException(409, '请先刷新验货台再选择要打印的记录')
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=5)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute('BEGIN')
        saved = []
        image_bytes = 0
        for identity, revision in requested.items():
            row = journal.get(connection, factory, identity)
            journal.revision(row, {'revision': revision})
            record = journal.unpack(connection, row, include_photos=False)
            saved.append(record)
        if len(journal.workbench_items(saved)) != len(saved):
            raise HTTPException(409, '部分记录已离开验货台，请刷新后重新选择')
        # Keep evidence and text on the same checked revision, even during concurrent edits.
        for record in saved:
            pictures = connection.execute(
                'SELECT * FROM photos WHERE entry_id=? AND removed=0 ORDER BY created_at,id',
                (record['id'],))
            for photo in pictures:
                content, _ = journal.photo_assets.read(connection, photo, 'preview')
                with Image.open(BytesIO(content)) as original:
                    thumb = ImageOps.exif_transpose(original)
                    thumb.thumbnail((480, 480))
                    buffer = BytesIO()
                    thumb.convert('RGB').save(buffer, 'JPEG', quality=85)
                data = buffer.getvalue()
                image_bytes += len(data)
                if image_bytes > 32 * 1024 * 1024:
                    raise HTTPException(422, '所选照片总量过大，请分批选择记录')
                record['photos'].append(data)
    return saved


def as_date(value):
    value = str(value or '')
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == value else None


def quantity_value(value):
    if isinstance(value, str) and re.fullmatch(r'[+-]?\d+(?:\.\d+)?', value.strip()):
        value = float(value)
    if type(value) in (int, float):
        return value if math.isfinite(value) else None
    return value or None


def record_values(record):
    values = []
    for field in FIELDS:
        value = record.get(field)
        if field == 'actualDate':
            value = as_date(value)
        elif field in ('quantity', 'unitsPerCarton', 'cartonCount'):
            value = quantity_value(value)
        elif value is not None:
            value = str(value)
        values.append(value if value != '' else None)
    return values


def fit_record_text(sheet, row, values, widths):
    minimum = sheet.row_dimensions[row].height or 15
    height = minimum
    for column, value in enumerate(values, 1):
        if not isinstance(value, str):
            continue
        cell = sheet.cell(row, column)
        available = max(3, int((widths[column] - 1) * 0.85))
        lines = sum(max(1, math.ceil(sum(2 if east_asian_width(c) in 'WFA' else 1 for c in line)
                                     / available)) for line in value.split('\n'))
        if lines > 1:
            alignment = copy(cell.alignment)
            alignment.wrap_text = True
            cell.alignment = alignment
            height = max(height, lines * (cell.font.sz or 11) * 1.4 + 4)
    if height > 409:
        raise HTTPException(422, '所选记录有文字过长，无法在一行内完整打印')
    if height > minimum:
        sheet.row_dimensions[row].height = height


def fill_template(source, destination, template, records):
    """Fill the original cells; hide unused sample rows and copy rows only to grow.

    Unlike rebuilding a sheet from one sample row, this retains the supplied
    per-row formats, date bands, subtotal positions, merges and page settings.
    All historical values, including those in hidden rows, are cleared.
    """
    book = load_workbook(source, keep_links=False)
    try:
        if template not in book:
            raise HTTPException(422, '打印模板缺少已确认的工作表')
        sheet = book[template]
        if tuple(sheet.cell(3, n).value for n in range(1, 15)) != HEADERS:
            raise HTTPException(422, '打印模板的 A3:N3 表头与已确认版本不一致')
        starts = sorted(b.min_row for b in sheet.merged_cells.ranges
                        if b.min_col == 1 and b.max_col == 14 and b.min_row > 1
                        and isinstance(sheet.cell(b.min_row, 1).value, date))
        if not starts or starts[0] != 2:
            raise HTTPException(422, '打印模板缺少原有日期分组')
        # These two confirmed sheets contain no drawings. Keep the engine from
        # silently dropping new unsupported objects if the private asset changes.
        if sheet._images or sheet._charts:
            raise HTTPException(422, '模板已增加图片或图表，请先核对定位配置')
        total_example = next(r for r in range(4, sheet.max_row + 1) if sheet.cell(r, 6).value == '总数量')
        record_example = next(r for r in range(5, total_example) if sheet.cell(r, 2).value)

        def row_copy(row):
            return ([copy(cell) for cell in sheet[row][:14]], copy(sheet.row_dimensions[row]))

        record_source, total_source = row_copy(record_example), row_copy(total_example)
        band_source = [row_copy(r) for r in range(2, starts[1] if len(starts) > 1 else sheet.max_row + 1)]
        band_merges = [copy(b) for b in sheet.merged_cells.ranges
                       if 2 <= b.min_row and b.max_row < 2 + len(band_source)]
        widths = dict.fromkeys(range(1, 15), sheet.sheet_format.defaultColWidth or 8.43)
        for dimension in sheet.column_dimensions.values():
            for col in range(dimension.min, min(14, dimension.max) + 1):
                widths[col] = dimension.width
        for name in list(book.sheetnames):
            if name != template:
                del book[name]
        book.active = 0
        sheet.sheet_view.tabSelected = True
        visible, keep = {1}, set()

        def write(row, column, value):
            cell = sheet.cell(row, column)
            cell.value = value
            if isinstance(value, str):
                cell.data_type = 's'
            keep.add((row, column))

        def copy_row(target, source_row):
            cells, dimension = source_row
            sheet.row_dimensions[target] = copy(dimension)
            sheet.row_dimensions[target].index = target
            for col, original in enumerate(cells, 1):
                cell = sheet.cell(target, col)
                cell._style = copy(original._style)
                cell.value = original.value
                cell.data_type = original.data_type
                cell.comment = copy(original.comment)
                if original.data_type == 'f':
                    cell.value = Translator(original.value, origin=original.coordinate).translate_formula(cell.coordinate)

        def insert_rows(at, sources):
            nonlocal visible, keep
            amount = len(sources)
            merges = [copy(b) for b in sheet.merged_cells.ranges]
            # openpyxl does not shift row dimensions or merged ranges itself.
            for b in list(sheet.merged_cells.ranges):
                sheet.unmerge_cells(str(b))
            dimensions = {r: copy(d) for r, d in sheet.row_dimensions.items()}
            formulas = [(c.row, c.column, c.value, c.coordinate) for row in sheet for c in row
                        if c.row >= at and c.data_type == 'f']
            sheet.insert_rows(at, amount)
            sheet.row_dimensions.clear()
            for r, dimension in dimensions.items():
                target = r + amount if r >= at else r
                dimension.index = target
                sheet.row_dimensions[target] = dimension
            for r, col, formula, origin in formulas:
                cell = sheet.cell(r + amount, col)
                cell.value = Translator(formula, origin=origin).translate_formula(cell.coordinate)
            for b in merges:
                if b.min_row >= at:
                    b.shift(row_shift=amount)
                elif b.max_row >= at:
                    b.max_row += amount
                sheet.merge_cells(str(b))
            visible = {r + amount if r >= at else r for r in visible}
            keep = {(r + amount if r >= at else r, c) for r, c in keep}
            for offset, original in enumerate(sources):
                copy_row(at + offset, original)

        groups = defaultdict(lambda: defaultdict(list))
        for record in records:
            values = record_values(record)
            groups[values[0]][values[1]].append(values)
        while len(starts) < len(groups):
            target = sheet.max_row + 1
            for offset, original in enumerate(band_source):
                copy_row(target + offset, original)
            for original in band_merges:
                merged = copy(original)
                merged.shift(row_shift=target - 2)
                sheet.merge_cells(str(merged))
            starts.append(target)
        ends = starts[1:] + [sheet.max_row + 1]
        # Work from bottom to top so expansion never invalidates earlier offsets.
        for index in reversed(range(len(groups))):
            day, customers = list(groups.items())[index]
            start, end = starts[index], ends[index]
            totals = [r for r in range(start + 3, end) if sheet.cell(r, 6).value == '总数量']
            if not totals:
                raise HTTPException(422, '打印模板缺少客户合计行')
            sections = []
            previous = start + 3
            for total in totals:
                slots = [r for r in range(previous, total) if sheet.cell(r, 2).value]
                sections.append((slots, total))
                previous = total + 1
            # Extra customers inherit the original record/subtotal styles.
            for _ in range(max(0, len(customers) - len(sections))):
                at = sections[-1][1] + 1
                insert_rows(at, [record_source, total_source])
                sections.append(([at], at + 1))
            for group_index in reversed(range(len(customers))):
                rows = list(customers.values())[group_index]
                slots, total = sections[group_index]
                extra = max(0, len(rows) - len(slots))
                if extra:
                    insert_rows(total, [record_source] * extra)
                    slots = slots + list(range(total, total + extra))
                    total += extra
                used = slots[:len(rows)]
                for row, values in zip(used, rows):
                    formula = sheet.cell(row, 9).value
                    for column, value in enumerate(values, 1):
                        write(row, column, value)
                        # Some sample rows round cartons to whole numbers. Do not
                        # let that format turn a saved fractional quantity into a
                        # different number on paper.
                        if column in (7, 8, 9) and type(value) is float and not value.is_integer():
                            sheet.cell(row, column).number_format = '0.########'
                    quantity, packing, cartons = values[6:9]
                    if (formula == f'=G{row}/H{row}' and
                            all(type(v) in (int, float) for v in (quantity, packing, cartons)) and
                            packing and math.isclose(quantity / packing, cartons, rel_tol=0, abs_tol=1e-9)):
                        sheet.cell(row, 9).value = formula
                    fit_record_text(sheet, row, values, widths)
                visible.update(used)
                visible.add(total)
                write(total, 6, '总数量')
                area = f'G{used[0]}:G{used[-1]}'
                write(total, 7, None)
                sheet.cell(total, 7).value = f'=IF(COUNT({area})={len(used)},SUM({area}),"")'
            write(start, 1, day)
            visible.update((start, start + 1, start + 2))
            for column, value in enumerate(HEADERS, 1):
                write(start + 1, column, value)
        dates = sorted(day for day in groups if day)
        period = ''
        if dates:
            labels = [f'{d.month}.{d.day}' for d in (dates[0], dates[-1])]
            if dates[0].year != dates[-1].year:
                labels = [d.isoformat() for d in (dates[0], dates[-1])]
            period = labels[0] if dates[0] == dates[-1] else '-'.join(labels)
        write(1, 1, f'(客验货排期{period})')
        from openpyxl.cell.cell import MergedCell
        for row in sheet:
            for cell in row:
                if isinstance(cell, MergedCell) or (cell.row, cell.column) in keep:
                    continue
                # Preserve unused original formulas without historical operands
                # or error text. These rows remain outside the visible printout.
                cell.value = f'=IFERROR({cell.value[1:]},"")' if cell.data_type == 'f' else None
                cell.comment = None
            sheet.row_dimensions[row[0].row].hidden = row[0].row not in visible
        sheet.print_area = f'A1:N{max(visible)}'
        sheet.print_title_rows = sheet.print_title_rows or '3:3'
        sheet.auto_filter.ref = None
        book.save(destination)
    finally:
        book.close()


def office_environment(work_dir):
    if sys.platform != 'darwin' or os.getenv('FONTCONFIG_FILE'):
        return None
    # The bundled headless build uses fontconfig. Point its isolated profile at
    # local fonts so a missing Windows face cannot silently blank Chinese text.
    cache = work_dir / 'font-cache'
    cache.mkdir(exist_ok=True)
    config = work_dir / 'fonts.conf'
    config.write_text(f'''<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">
<fontconfig>
  <dir>/System/Library/Fonts</dir>
  <dir>/System/Library/Fonts/Supplemental</dir>
  <dir>/Library/Fonts</dir>
  <cachedir>{escape(str(cache))}</cachedir>
  <alias><family>宋体</family><prefer><family>Songti SC</family></prefer></alias>
  <alias><family>SimSun</family><prefer><family>Songti SC</family></prefer></alias>
  <alias><family>sans-serif</family><prefer><family>STHeiti</family><family>Arial</family></prefer></alias>
  <alias><family>serif</family><prefer><family>Songti SC</family><family>Times New Roman</family></prefer></alias>
</fontconfig>''', encoding='utf-8')
    return {**os.environ, 'FONTCONFIG_FILE': str(config)}


def convert_office(executable, work_dir, source, output_format):
    extension = output_format.partition(':')[0]
    output = source.with_suffix('.' + extension)
    command = [executable, '--headless', '--nologo', '--norestore',
               f'-env:UserInstallation={(work_dir / "office-profile").resolve().as_uri()}',
               '--convert-to', output_format, '--outdir', str(work_dir), str(source)]
    try:
        subprocess.run(command, check=True, capture_output=True, timeout=60, env=office_environment(work_dir))
    except (OSError, subprocess.SubprocessError) as error:
        raise HTTPException(503, 'LibreOffice 未能完成打印转换，请稍后重试') from error
    if not output.is_file() or not output.stat().st_size:
        raise HTTPException(503, 'LibreOffice 未生成打印文件')
    return output


def render_pages(pdf):
    with PDF_RENDER_LOCK, closing(PdfDocument(pdf)) as document:
        if not 1 <= len(document) <= MAX_PAGES:
            raise HTTPException(422, f'一次最多预览 {MAX_PAGES} 页，请分批选择记录')
        pages = []
        for index in range(len(document)):
            with closing(document[index]) as page:
                width, height = page.get_size()
                with closing(page.render(scale=2.5)) as bitmap:
                    image = BytesIO()
                    bitmap.to_pil().save(image, format='PNG')
                pages.append({'width': width, 'height': height, 'image': b64encode(image.getvalue()).decode()})
        return pages


def preview(factory, body):
    from app.services.qc_inspection_schedule_excel import schedule_workbook

    template = body.get('template')
    if set(body) != {'template', 'entries'} or template not in ('客户验货排期表', *TEMPLATES):
        raise HTTPException(422, '请选择已确认的打印模板')
    records = saved_records(factory, body['entries'])
    executable = office_executable()
    if not executable:
        raise HTTPException(503, '服务器缺少 LibreOffice 打印转换组件')
    with TemporaryDirectory(prefix='qc-print-', ignore_cleanup_errors=True) as directory:
        work_dir = Path(directory)
        workbook = work_dir / 'inspection.xlsx'
        workbook.write_bytes(schedule_workbook(records))
        pdf = convert_office(executable, work_dir, workbook, 'pdf:calc_pdf_Export').read_bytes()
        return {'template': template, 'count': len(records), 'pdf': b64encode(pdf).decode(), 'pages': render_pages(pdf)}
