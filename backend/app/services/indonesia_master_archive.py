"""Bound large photo workbooks and stream sparse worksheet evidence."""
from contextlib import contextmanager
from threading import BoundedSemaphore
from xml.etree import ElementTree as ET

from openpyxl.worksheet._reader import WorkSheetParser

from app.services.indonesia_material_calculations import require

MAX_FILE_BYTES = 200 * 1024 * 1024
MAX_EXPANDED_BYTES = 512 * 1024 * 1024
MAX_ENTRIES = 10000
MAX_SOURCE_ROWS = 10000
S = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
_upload_slot = BoundedSemaphore(1)


@contextmanager
def upload_slot():
    # Admission precedes reading UploadFile's disk spool into API memory. The
    # existing document worker still owns its independent process/time budget.
    require(_upload_slot.acquire(blocking=False), '已有统一资料正在处理，请稍后重试；当前草稿保留', 429)
    try:
        yield
    finally:
        _upload_slot.release()


def validate_archive(archive):
    entries = archive.infolist()
    require(len(entries) <= MAX_ENTRIES, '文件内部项目过多，请分批导入', 422)
    require(len({item.filename for item in entries}) == len(entries), '文件包含重复内部项目，请重新保存 Excel 后导入', 422)
    require(sum(item.file_size for item in entries) <= MAX_EXPANDED_BYTES, '文件解压后过大，请分批导入', 422)
    for item in entries:
        if item.filename.lower().endswith(('.xml', '.rels')):
            limit = 80 if item.filename.startswith('xl/worksheets/') else 16
            require(item.file_size <= limit * 1024 * 1024, '文件单项内容过大，请清理空白格式或分批导入', 422)


def worksheet_evidence(archive, part):
    """Retain only merge/drawing references and occupied row numbers, not the XML tree."""
    metadata = ET.Element(S+'worksheet')
    occupied, stack = set(), []
    row_number = 0
    with archive.open(part) as source:
        for event, node in ET.iterparse(source, events=('start', 'end')):
            if event == 'start':
                stack.append(node)
                continue
            if node.tag == S+'row':
                row_number = int(node.get('r', row_number + 1))
                require(1 <= row_number <= 1048576, '工作表行号无效，请重新保存 Excel 后导入', 422)
                if any(cell.find(S+'f') is not None or any(''.join(value.itertext()).strip()
                       for value in cell if value.tag in {S+'v', S+'is'}) for cell in node):
                    occupied.add(row_number)
                    require(len(occupied) <= MAX_SOURCE_ROWS, '工作表有效数据行过多，请保留物料明细后分批导入', 422)
                stack[-2].remove(node)
                node.clear()
            elif node.tag in {S+'mergeCell', S+'drawing'}:
                require(len(metadata) < 10000, '工作表合并区域或图片引用过多，请分批导入', 422)
                ET.SubElement(metadata, node.tag, node.attrib)
            if len(stack) == 2:
                stack[-2].remove(node)
                node.clear()
            stack.pop()
    return metadata, occupied


def sparse_row_pairs(sheet, start, occupied):
    """Use openpyxl's decoder without inventing cells for gaps or trusting dimensions.

    Keep the private parser adapter here: it is the same decoder/ReadOnlyCell
    conversion as ReadOnlyWorksheet._cells_by_row, with sparse row iteration.
    Both readers share the book's strings/styles rather than loading it twice.
    """
    if not occupied:
        return
    last = max(occupied)
    options = dict(epoch=sheet.parent.epoch, date_formats=sheet.parent._date_formats,
                   timedelta_formats=sheet.parent._timedelta_formats)
    with sheet._get_source() as raw_source, sheet._get_source() as cached_source:
        raw = WorkSheetParser(raw_source, sheet._shared_strings, data_only=False, **options)
        cached = WorkSheetParser(cached_source, sheet._shared_strings, data_only=True, **options)
        for (number, cells), (cache_number, cache_cells) in zip(raw.parse(), cached.parse()):
            require(number == cache_number, '工作表行号不一致，请重新保存 Excel 后导入', 422)
            if number > last:
                break
            if number >= start and number in occupied:
                yield number, sheet._get_row(cells, 1, 120), sheet._get_row(cache_cells, 1, 120)
