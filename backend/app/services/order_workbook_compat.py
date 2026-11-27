"""Normalize WPS whole-row native tables without rebuilding the workbook.

Original uploads stay immutable. Untouched ZIP members retain their bytes;
ordinary rectangular tables are never changed. Empty generated tail columns
are removed only when both table metadata and worksheet contents prove it safe.
"""
from io import BytesIO
import posixpath
import re
from zipfile import ZipFile

from lxml import etree as ET
from openpyxl.utils.cell import column_index_from_string, get_column_letter

MAIN = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
DOC_REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
NS = {'m': MAIN}
MAX_EXPANDED_BYTES = 200 * 1024**2


def _xml(raw):
    parser = ET.XMLParser(resolve_entities=False, no_network=True)
    root = ET.fromstring(raw, parser)
    if root.getroottree().docinfo.doctype:
        raise ValueError('排期 XML 不支持外部声明')
    return root


def _column(coordinate):
    match = re.fullmatch(r'\$?([A-Z]{1,3})\$?[1-9][0-9]*', coordinate or '')
    return column_index_from_string(match[1]) if match else None


def _wide_reference(value, right):
    # Conservative across all sheets: keep a tail if *any* formula/range might
    # use it, including whole-column references or structured column names.
    if re.search(r'列[1-9][0-9]*', value or ''):
        return True
    # Whole rows include the generated header cells; dynamic references cannot
    # be proven independent of the tail without evaluating the workbook.
    if re.search(r'(?<![\w.])\$?[1-9][0-9]*\s*:\s*\$?[1-9][0-9]*|\b(?:INDIRECT|OFFSET)\s*\(',
                 value or '', re.I):
        return True
    for ends in re.findall(r'(?<![\w.])\$?([A-Z]{1,3})\s*:\s*\$?([A-Z]{1,3})(?![\w.])',
                           (value or '').upper()):
        if any(column_index_from_string(col) > right for col in ends):
            return True
    return any(column_index_from_string(col) > right for col in re.findall(
        r'(?<![A-Za-z0-9_])\$?([A-Z]{1,3})(?=\$?[0-9]|\s*:|\s*$)', (value or '').upper()))


def _owner(archive, table_name):
    matches = []
    for name in archive.namelist():
        if not name.startswith('xl/worksheets/_rels/') or not name.endswith('.rels'):
            continue
        sheet_name = name.replace('/_rels/', '/').removesuffix('.rels')
        rels = _xml(archive.read(name))
        def resolved(target):
            return posixpath.normpath(target.lstrip('/') if target.startswith('/')
                else posixpath.join(posixpath.dirname(sheet_name), target))
        ids = {r.get('Id') for r in rels if r.get('TargetMode') != 'External'
               and r.get('Type', '').endswith('/table')
               and resolved(r.get('Target', '')) == table_name}
        if ids and sheet_name in archive.namelist():
            sheet = _xml(archive.read(sheet_name))
            if any(p.get('{%s}id' % DOC_REL) in ids for p in sheet.findall('m:tableParts/m:tablePart', NS)):
                matches.append((sheet_name, sheet))
    return matches[0] if len(matches) == 1 else (None, None)


def _empty_tail(archive, table_name, table, columns, first_row):
    """Return a proven empty generated suffix, otherwise preserve full width."""
    tail = next((i for i, col in enumerate(columns) if col.get('name') == '列1'), None)
    if tail is None or tail == 0 or tail == len(columns) - 1:
        return None
    for index, col in enumerate(columns[tail:], 1):
        if dict(col.attrib) != {'id': str(tail + index), 'name': f'列{index}'} or len(col):
            return None
    # Filter/sort/extensions may address columns by position rather than name.
    if any(ET.QName(child).localname not in {'autoFilter', 'tableColumns', 'tableStyleInfo'} for child in table):
        return None
    auto_filter = table.find('m:autoFilter', NS)
    if auto_filter is not None and len(auto_filter):
        return None
    sheet_name, sheet = _owner(archive, table_name)
    if sheet is None:
        return None
    shared = []
    if 'xl/sharedStrings.xml' in archive.namelist():
        shared = [''.join(s.itertext()) for s in _xml(archive.read('xl/sharedStrings.xml'))]
    cells = sheet.findall('m:sheetData/m:row/m:c', NS)
    removed = []
    for cell in cells:
        col = _column(cell.get('r'))
        if col is None:
            return None
        if col <= tail:
            continue
        if set(cell.attrib) - {'r', 's', 't'} or any(
                ET.QName(n).localname not in {'v', 'is'} for n in cell):
            return None
        if cell.get('r') != f'{get_column_letter(col)}{first_row}' or cell.find('m:f', NS) is not None:
            return None
        value = cell.find('m:v', NS)
        if cell.get('t') == 's' and value is not None:
            try:
                label = shared[int(value.text)]
            except (ValueError, TypeError, IndexError):
                return None
        elif cell.get('t') == 'inlineStr':
            inline = cell.find('m:is', NS)
            if inline is None:
                return None
            label = ''.join(inline.itertext())
        else:
            return None
        if label != f'列{col - tail}':
            return None
        removed.append(cell)
    if len(removed) != len(columns) - tail:
        return None
    # Preserve user dimensions and all non-cell structures. Exclude only views,
    # dimensions and the verified generated header row's spans.
    for node in sheet.iter():
        if not isinstance(node.tag, str):
            continue
        tag = ET.QName(node).localname
        if tag == 'col' and int(node.get('max', '0')) > tail:
            return None
        if tag not in {'dimension', 'c', 'row', 'selection', 'sheetView'}:
            if any(_wide_reference(v, tail) for k, v in node.attrib.items()
                   if k in {'ref', 'sqref', 'topLeftCell'}):
                return None
    for name in archive.namelist():
        if not name.endswith('.xml'):
            continue
        root = _xml(archive.read(name))
        for node in root.iter():
            if not isinstance(node.tag, str):
                continue
            tag = ET.QName(node).localname
            if tag in {'f', 'formula', 'formula1', 'formula2', 'definedName',
                       'calculatedColumnFormula', 'totalsRowFormula'}:
                expression = node.text or ''
                if _wide_reference(expression, tail) or any(re.search(
                        r'(?<![\w.])' + re.escape(label) + r'(?![\w.])', expression, re.I)
                        for label in (table.get('name'), table.get('displayName')) if label):
                    return None
            if tag == 'comment' and (_column(node.get('ref')) or 0) > tail:
                return None
    return tail, sheet_name, sheet, removed


def normalize_table_ranges(content):
    """Return compatible bytes and user-visible notes (no changes on no-op)."""
    patches, notes = {}, []
    with ZipFile(BytesIO(content)) as archive:
        if sum(info.file_size for info in archive.infolist()) > MAX_EXPANDED_BYTES:
            raise ValueError('排期解压后超过 200MB 限制')
        for name in archive.namelist():
            if not name.startswith('xl/tables/') or not name.endswith('.xml'):
                continue
            table = _xml(archive.read(name))
            match = re.fullmatch(r'([1-9][0-9]*):([1-9][0-9]*)', table.get('ref', ''))
            if not match:
                continue
            first, last = map(int, match.groups())
            columns_node = table.find('m:tableColumns', NS)
            columns = list(columns_node) if columns_node is not None else []
            rectangle = f'A{first}:XFD{last}'
            auto_filter = table.find('m:autoFilter', NS)
            if not (first <= last <= 1048576 and len(columns) == 16384
                    and columns_node.get('count') == '16384'
                    and auto_filter is not None and auto_filter.get('ref') == rectangle):
                raise ValueError('排期表格的整行范围与列数或筛选范围不一致，请核对原表')
            narrowed = _empty_tail(archive, name, table, columns, first)
            table.set('ref', rectangle)
            if narrowed:
                right, sheet_name, sheet, removed = narrowed
                if sheet_name in patches:
                    raise ValueError('同一工作表存在多个整行表格，请核对原表')
                rectangle = f'A{first}:{get_column_letter(right)}{last}'
                table.set('ref', rectangle)
                auto_filter.set('ref', rectangle)
                for col in columns[right:]:
                    columns_node.remove(col)
                columns_node.set('count', str(right))
                for cell in removed:
                    cell.getparent().remove(cell)
                row = sheet.find(f'm:sheetData/m:row[@r="{first}"]', NS)
                if row is not None and row.get('spans'):
                    row.set('spans', f'1:{right}')
                dimension = sheet.find('m:dimension', NS)
                if dimension is not None:
                    coordinates = [c.get('r') for c in sheet.findall('m:sheetData/m:row/m:c', NS)]
                    end = max(int(re.search(r'[0-9]+$', c)[0]) for c in coordinates)
                    dimension.set('ref', f'A1:{get_column_letter(right)}{end}')
                patches[sheet_name] = ET.tostring(sheet, encoding='utf-8', xml_declaration=True)
                notes.append(f'已兼容排期表格范围，清理 {len(removed)} 个无业务内容的自动空列表头；原订单、公式和格式保留。')
            else:
                notes.append('已兼容排期的整行表格范围，原表格内容保留。')
            patches[name] = ET.tostring(table, encoding='utf-8', xml_declaration=True)
        if not patches:
            return content, []
        output = BytesIO()
        with ZipFile(output, 'w') as target:
            target.comment = archive.comment
            for info in archive.infolist():
                target.writestr(info, patches.get(info.filename, archive.read(info.filename)))
        return output.getvalue(), notes
