from io import BytesIO
from types import SimpleNamespace
from zipfile import ZipFile

import openpyxl
import pytest
from fastapi import HTTPException
from lxml import etree

from app.services.order_workbook_bounds import worksheet_bounds
from app.services.customer_order_history import parse_workbook
from app.services.indonesia_warehouse_import import parse_warehouse_receipts


def missing_dimensions(content, references='keep'):
    result = BytesIO()
    with ZipFile(BytesIO(content)) as source, ZipFile(result, 'w') as target:
        for info in source.infolist():
            data = source.read(info.filename)
            if info.filename.startswith('xl/worksheets/') and info.filename.endswith('.xml'):
                tree = etree.fromstring(data)
                for dimension in tree.findall('{*}dimension'):
                    tree.remove(dimension)
                if references != 'keep':
                    for cell in tree.findall('.//{*}c'):
                        cell.attrib.pop('r', None)
                if references == 'none':
                    for row in tree.findall('.//{*}row'):
                        row.attrib.pop('r', None)
                data = etree.tostring(tree)
            target.writestr(info, data)
    return result.getvalue()


@pytest.mark.parametrize('kind', ['receipt', 'schedule'])
@pytest.mark.parametrize('references', ['keep', 'rows', 'none'])
def test_optional_empty_sheet_without_dimensions_does_not_block_valid_data(kind, references):
    book = openpyxl.Workbook(); sheet = book.active
    if kind == 'receipt':
        sheet.append(['收料单号', '行号', '实收日期', '物料名称', '实收数量'])
        sheet.append(['WH-001', 1, '2026-10-22', '物料A', 10])
    else:
        sheet.title = 'ITEM表'
        # Keep two explicit blank rows when optional row coordinates are removed.
        sheet.append(['']); sheet.append([''])
        sheet.append(['Contract No.', 'SO#/Reference', 'P/O#:', '产品编号', '数量', '客要求走货期'])
        sheet.append(['CTR', 'SO', 'PO', '40149', 10, '2026-12-18'])
    book.create_sheet('空白ITEM表')
    stream = BytesIO(); book.save(stream)
    content = missing_dimensions(stream.getvalue(), references)
    rows = parse_warehouse_receipts(content, 'receipts.xlsx') if kind == 'receipt' else parse_workbook(content)[0]
    assert len(rows) == 1


@pytest.mark.parametrize('xml', ['<row r="1048576"/>', '<row r="1"><c r="XFD1"/></row>'])
def test_missing_dimensions_rejects_sparse_extreme_coordinates_before_expansion(xml):
    source = BytesIO()
    with ZipFile(source, 'w') as archive:
        archive.writestr('sheet.xml', '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'+xml+'</sheetData></worksheet>')
    with ZipFile(BytesIO(source.getvalue())) as archive:
        book = SimpleNamespace(_archive=archive)
        sheet = SimpleNamespace(max_row=None, max_column=None, _worksheet_path='sheet.xml')
        with pytest.raises(HTTPException, match='bounded'):
            worksheet_bounds(book, sheet, 2000, 80, 'bounded')
