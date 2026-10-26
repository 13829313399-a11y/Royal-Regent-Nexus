"""Bounded OOXML text extraction. Never invokes Office, formulas or relationships.

Imported inside the existing disposable parser after its OS limit is installed.
ZIP entries stay in memory; no package path is extracted to the filesystem.
"""
from io import BytesIO
from decimal import Decimal, InvalidOperation
import posixpath
import re
from zipfile import ZipFile, BadZipFile, ZIP_DEFLATED, ZIP_STORED

from lxml import etree
from openpyxl.styles.numbers import BUILTIN_FORMATS, is_date_format
from openpyxl.utils.cell import range_boundaries, coordinate_to_tuple
from openpyxl.utils.datetime import from_excel, MAC_EPOCH, WINDOWS_EPOCH
from openpyxl.formula.translate import Translator


MAX_ENTRIES = 2048
MAX_EXPANDED = 64 * 1024 * 1024
MAX_PART = 16 * 1024 * 1024
MAX_CELLS = 20000
MAX_MERGES = 1000
NS_WORD = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
NS_SHEET = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
NS_REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'


class OfficeError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def require(condition, code='office_invalid'):
    if not condition:
        raise OfficeError(code)


def local(tag):
    return tag.rsplit('}', 1)[-1] if isinstance(tag, str) else ''


def xml(raw):
    parser = etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True, huge_tree=False)
    root = etree.fromstring(raw, parser)
    require(not root.getroottree().docinfo.doctype, 'office_active_content')
    return root


def rich_text(node):
    return ''.join(t.text or '' for t in node.iter('{' + NS_SHEET + '}t')
                   if not any(local(a.tag) == 'rPh' for a in t.iterancestors()))


class Package:
    def __init__(self, raw, extension):
        require(raw.startswith(b'PK\x03\x04'), 'office_signature')
        self.zip = ZipFile(BytesIO(raw))
        try:
            self.validate(extension)
        except BaseException:
            self.zip.close()
            raise

    def validate(self, extension):
        infos = self.zip.infolist()
        require(len(infos) <= MAX_ENTRIES, 'office_expansion_limit')
        require(sum(i.file_size for i in infos) <= MAX_EXPANDED, 'office_expansion_limit')
        self.names = set()
        for info in infos:
            name = info.filename
            require(name not in self.names and not name.startswith('/') and '\\' not in name
                    and '..' not in name.split('/') and ':' not in name, 'office_package_path')
            require(not info.flag_bits & 1, 'office_encrypted')
            require(info.compress_type in (ZIP_STORED, ZIP_DEFLATED), 'office_signature')
            require(info.file_size <= MAX_PART and info.file_size <= max(1, info.compress_size) * 200,
                    'office_expansion_limit')
            require(not any(x in name.lower() for x in ('vbaproject', 'activex/', 'embeddings/', 'macrosheets/')),
                    'office_active_content')
            self.names.add(name)
        types = self.read('[Content_Types].xml')
        require(local(types.tag) == 'Types', 'office_signature')
        content_types = {e.get('PartName'): e.get('ContentType', '') for e in types if local(e.tag) == 'Override'}
        require(not any(any(word in e.get('ContentType', '').lower() for word in
                            ('macroenabled', 'vba', 'activex', 'oleobject', 'macrosheet')) for e in types), 'office_active_content')
        main, expected = ('/word/document.xml', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml') if extension == '.docx' else (
            '/xl/workbook.xml', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml')
        require(content_types.get(main) == expected, 'office_signature')

    def read(self, name):
        require(name in self.names, 'office_signature')
        # Validate actual inflated length, not only archive header claims.
        with self.zip.open(name) as stream:
            raw = stream.read(MAX_PART + 1)
        require(len(raw) <= MAX_PART, 'office_expansion_limit')
        return xml(raw)


def docx(package, add, max_units):
    root = package.read('word/document.xml')
    require(root.tag == '{' + NS_WORD + '}document', 'office_signature')
    ns = {'w': NS_WORD}
    body = root.find('w:body', ns)
    require(body is not None)
    styles = {}
    if 'word/styles.xml' in package.names:
        for style in package.read('word/styles.xml').findall('w:style', ns):
            name = style.find('w:name', ns)
            level = style.find('w:pPr/w:outlineLvl', ns)
            styles[style.get('{' + NS_WORD + '}styleId')] = (
                name.get('{' + NS_WORD + '}val', '') if name is not None else '', level is not None)
    heading, paragraph = '', 0
    for node in body.iter('{' + NS_WORD + '}p'):
        # Deletions are not current displayed paragraph text.
        if any(local(parent.tag) == 'del' for parent in node.iterancestors()):
            continue
        paragraph += 1
        require(paragraph <= max_units * 100, 'office_paragraph_limit')
        text = []
        for child in node.iter():
            if child.tag not in ('{' + NS_WORD + '}' + tag for tag in ('t', 'tab', 'br', 'cr')):
                continue
            ancestors = list(child.iterancestors())
            if next((a for a in ancestors if local(a.tag) == 'p'), None) is not node:
                continue
            if any(local(a.tag) in ('del', 'instrText') for a in ancestors):
                continue
            text.append(child.text or '' if local(child.tag) == 't' else '\t' if local(child.tag) == 'tab' else '\n')
        value = ''.join(text)
        style = node.find('w:pPr/w:pStyle', ns)
        style_id = style.get('{' + NS_WORD + '}val', '') if style is not None else ''
        style_name, outline = styles.get(style_id, (style_id, False))
        if outline or re.match(r'(heading|标题)\s*\d', style_name, re.I):
            heading = value
        metadata = dict(format='docx', heading=heading or None,
                        coverage='正文及表格段落，计入空段落；不推算页码；不含页眉、页脚、批注、脚注及图片文字。域和链接只读取已保存文字，未更新或执行。')
        if any(local(a.tag) == 'tc' for a in node.iterancestors()):
            metadata['in_table'] = True
        add(value, dict(kind='paragraph', paragraph=paragraph), metadata)


def cell_value(node, strings, number_format, epoch):
    ns = {'s': NS_SHEET}
    value = node.find('s:v', ns)
    kind = node.get('t', 'n')
    raw = value.text if value is not None else None
    if kind == 'inlineStr':
        return rich_text(node.find('s:is', ns)) if node.find('s:is', ns) is not None else '', None
    if kind == 's':
        require(raw is not None and raw.isdigit() and int(raw) < len(strings))
        return strings[int(raw)], raw
    if kind == 'b':
        require(raw in ('0', '1'))
        return raw == '1', raw
    if kind == 'e':
        return None, raw
    if kind == 'str':
        return raw if raw is not None else '' if value is not None else None, raw
    if raw is None:
        return None, None
    if kind == 'd':
        return raw, raw
    require(kind == 'n')
    try:
        number = Decimal(raw)
        require(number.is_finite())
        if is_date_format(number_format):
            return from_excel(float(number), epoch).isoformat(), raw
        return format(number, 'f'), raw
    except (InvalidOperation, OverflowError, ValueError):
        raise OfficeError('office_invalid') from None


def xlsx(package, add, max_units):
    ns = {'s': NS_SHEET}
    book = package.read('xl/workbook.xml')
    require(book.tag == '{' + NS_SHEET + '}workbook', 'office_signature')
    properties = book.find('s:workbookPr', ns)
    epoch = MAC_EPOCH if properties is not None and properties.get('date1904') in ('1', 'true') else WINDOWS_EPOCH
    relationships = {r.get('Id'): r for r in package.read('xl/_rels/workbook.xml.rels')}
    strings = []
    if 'xl/sharedStrings.xml' in package.names:
        strings = [rich_text(e) for e in package.read('xl/sharedStrings.xml') if local(e.tag) == 'si']
    formats = ['General']
    if 'xl/styles.xml' in package.names:
        styles = package.read('xl/styles.xml')
        custom = {int(e.get('numFmtId')): e.get('formatCode', 'General') for e in styles.findall('s:numFmts/s:numFmt', ns)}
        formats = [custom.get(int(e.get('numFmtId', '0')), BUILTIN_FORMATS.get(int(e.get('numFmtId', '0')), 'General'))
                   for e in styles.findall('s:cellXfs/s:xf', ns)] or ['General']
    sheets = book.findall('s:sheets/s:sheet', ns)
    require(len(sheets) <= min(max_units, 256), 'office_sheet_limit')
    total_cells = 0
    for sheet in sheets:
        relation = relationships.get(sheet.get('{' + NS_REL + '}id'))
        require(relation is not None and relation.get('TargetMode') != 'External', 'office_signature')
        require(relation.get('Type', '').endswith('/worksheet'), 'office_signature')
        target = relation.get('Target', '')
        target = posixpath.normpath(target.lstrip('/') if target.startswith('/') else 'xl/' + target)
        require(target.startswith('xl/') and '\\' not in target and ':' not in target, 'office_package_path')
        page = package.read(target)
        require(page.tag == '{' + NS_SHEET + '}worksheet', 'office_signature')
        merges = [m.get('ref', '') for m in page.findall('s:mergeCells/s:mergeCell', ns)]
        require(len(merges) <= MAX_MERGES, 'office_cell_limit')
        ranges = [(m, range_boundaries(m)) for m in merges]
        shared = {}
        seen = set()
        for row in page.findall('s:sheetData/s:row', ns):
            for cell in row.findall('s:c', ns):
                total_cells += 1
                require(total_cells <= MAX_CELLS, 'office_cell_limit')
                address = cell.get('r', '')
                require(re.fullmatch(r'[A-Z]{1,3}[1-9]\d{0,6}', address) and address not in seen)
                seen.add(address)
                row_number, column = coordinate_to_tuple(address)
                require(row_number <= 1048576 and column <= 16384)
                style = int(cell.get('s', '0'))
                require(0 <= style < len(formats))
                value, raw = cell_value(cell, strings, formats[style], epoch)
                formula = cell.find('s:f', ns)
                formula_text = None
                if formula is not None:
                    formula_text = '=' + (formula.text or '')
                    if formula.get('t') == 'shared':
                        key = formula.get('si')
                        if formula.text:
                            shared[key] = (address, formula_text)
                        else:
                            require(key in shared)
                            origin, expression = shared[key]
                            formula_text = Translator(expression, origin=origin).translate_formula(address)
                if value is None and formula is None and cell.get('t') != 'e':
                    continue
                merged = next((ref for ref, (left, top, right, bottom) in ranges
                               if left <= column <= right and top <= row_number <= bottom), None)
                metadata = dict(format='xlsx', cell_type=cell.get('t', 'n'), raw_value=raw,
                                number_format=formats[style], sheet_state=sheet.get('state', 'visible'),
                                coverage='读取文件已保存的单元格；未计算公式、未更新缓存、未打开外部链接。')
                if merged:
                    metadata.update(merged_range=merged, merged_anchor=merged.split(':')[0])
                if formula is not None:
                    metadata.update(formula=formula_text, cache_status='missing' if value is None else 'available')
                    if formula.get('ref'): metadata['formula_range'] = formula.get('ref')
                if cell.get('t') == 'e': metadata['cell_error'] = raw
                if row.get('hidden') in ('1', 'true'): metadata['hidden_row'] = True
                text = '未知（公式未保存可用缓存）' if formula is not None and value is None else '未知（单元格错误）' if cell.get('t') == 'e' else str(value)
                add(text, dict(kind='sheet', sheet=sheet.get('name', ''), cells=address), metadata)


def extract_office(raw, extension, max_units, add):
    package = None
    try:
        package = Package(raw, extension)
        (docx if extension == '.docx' else xlsx)(package, add, max_units)
    except OfficeError:
        raise
    except (BadZipFile, KeyError, ValueError, TypeError, etree.LxmlError, OSError, RuntimeError):
        raise OfficeError('office_invalid') from None
    finally:
        if package is not None: package.zip.close()
