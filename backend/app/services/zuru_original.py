"""Bounded source readers reused by the Huaxing ZURU PO adapter.

Reads only populated XML cells and keeps complete identifiers, including punctuation.
"""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
import posixpath
import re
from zipfile import ZipFile, BadZipFile

from xml.etree import ElementTree as XML
from openpyxl.utils.datetime import from_excel, CALENDAR_MAC_1904, CALENDAR_WINDOWS_1900

NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
REL = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'


def xml_bytes(archive, path):
    data = archive.read(path)
    if b'\x00' in data or b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ValueError('Excel XML 不接受 DTD、实体或 UTF-16 编码')
    return data


def text(value):
    return '' if value is None else str(value).strip()


def key(value):
    return re.sub(r'\s+', '', text(value)).upper()


class SourceBook:
    def __init__(self, content, name):
        self.name = name
        try:
            self.archive = ZipFile(BytesIO(content))
            infos = self.archive.infolist()
            names = [i.filename for i in infos]
            if (len(infos) > 5000 or len(set(names)) != len(names)
                    or sum(i.file_size for i in infos) > 200 * 1024**2
                    or any(i.flag_bits & 1 for i in infos)):
                raise ValueError('Excel 解压尺寸、加密或重复条目不符合安全限制')
            root = XML.fromstring(xml_bytes(self.archive, 'xl/workbook.xml'))
            relationships = XML.fromstring(xml_bytes(self.archive, 'xl/_rels/workbook.xml.rels'))
            targets = {r.get('Id'): r.get('Target') for r in relationships if r.get('TargetMode') != 'External'}
            self.sheets = {}
            for s in root.findall(f'{NS}sheets/{NS}sheet'):
                target = targets.get(s.get(REL), '')
                path = posixpath.normpath(target.lstrip('/') if target.startswith('/') else 'xl/' + target)
                if not path.startswith('xl/') or path not in names:
                    raise ValueError('工作表路径不正确')
                self.sheets[s.get('name')] = path
            if not 1 <= len(self.sheets) <= 50:
                raise ValueError('工作表数量超出限制')
            properties = root.find(f'{NS}workbookPr')
            self.epoch = CALENDAR_MAC_1904 if properties is not None and properties.get('date1904') in ('1', 'true') else CALENDAR_WINDOWS_1900
            self.strings = []
            if 'xl/sharedStrings.xml' in names:
                with BytesIO(xml_bytes(self.archive, 'xl/sharedStrings.xml')) as stream:
                    for _, node in XML.iterparse(stream, events=('end',)):
                        if node.tag == f'{NS}si':
                            value = ''.join(n.text or '' for n in node.iter(f'{NS}t'))
                            if len(value) > 50000 or len(self.strings) >= 500000:
                                raise ValueError('文本大小超出限制')
                            self.strings.append(value)
                            node.clear()
        except (BadZipFile, KeyError, XML.ParseError, ValueError) as exc:
            if hasattr(self, 'archive'):
                self.archive.close()
            raise ValueError(f'{name}：无法安全读取 Excel：{exc}') from exc

    def close(self):
        self.archive.close()

    def rows(self, sheet, *, max_rows=50000):
        """Only enumerate XML cells, never trust a million-row/XFD dimension."""
        count = 0
        with BytesIO(xml_bytes(self.archive, self.sheets[sheet])) as stream:
            for _, node in XML.iterparse(stream, events=('end',)):
                if node.tag != f'{NS}row':
                    continue
                number = int(node.get('r', '0'))
                values, formulas = {}, set()
                for cell in node.findall(f'{NS}c'):
                    count += 1
                    if count > 1000000:
                        raise ValueError(f'{self.name}/{sheet} 实际单元格过多，请拆分排期')
                    address = cell.get('r', '')
                    match = re.fullmatch(r'([A-Z]{1,3})([1-9][0-9]*)', address)
                    if not match or int(match[2]) != number:
                        raise ValueError(f'{self.name}/{sheet} 单元格坐标不正确')
                    column = match[1]
                    raw = cell.find(f'{NS}v')
                    value = raw.text if raw is not None else None
                    if cell.find(f'{NS}f') is not None:
                        formulas.add(column)
                    if cell.get('t') == 's' and value is not None:
                        try:
                            index = int(value)
                            if index < 0:
                                raise ValueError()
                            value = self.strings[index]
                        except (ValueError, IndexError) as exc:
                            raise ValueError('Excel 文本索引不正确') from exc
                    elif cell.get('t') == 'inlineStr':
                        value = ''.join(t.text or '' for t in cell.iter(f'{NS}t'))
                    if value not in (None, ''):
                        if len(value) > 50000:
                            raise ValueError('单元格文本超出限制')
                        values[column] = value
                if values or formulas:
                    if not 1 <= number <= max_rows:
                        raise ValueError(f'{self.name}/{sheet} 有效数据超出 {max_rows} 行限制')
                    yield number, values, formulas
                node.clear()


def numeric(value, label, *, integer=False, positive=False, optional=False):
    if not text(value):
        if optional:
            return None
        raise ValueError(f'{label}缺失')
    try:
        number = Decimal(key(value).replace(',', ''))
        if not number.is_finite() or number < 0 or number > Decimal('1e10'):
            raise InvalidOperation
        if positive and number == 0 or integer and number != number.to_integral_value():
            raise InvalidOperation
        return int(number) if integer else float(number)
    except (InvalidOperation, ValueError):
        raise ValueError(f'{label}必须是可核对的非负有限数值' + ('，且为正整数' if positive else '')) from None


def iso_date(value, epoch):
    raw = text(value)
    try:
        if re.fullmatch(r'\d+(?:\.\d+)?', raw):
            result = from_excel(float(raw), epoch)
            if not isinstance(result, datetime):
                raise ValueError()
            result = result.date()
        else:
            result = date.fromisoformat(raw.split(' ')[0].replace('/', '-'))
        if not 2000 <= result.year <= 2100:
            raise ValueError()
        return result.isoformat()
    except (ValueError, OverflowError):
        raise ValueError('PO 日期或交期缺失/无效，请核对原件') from None
