"""Bounded, read-only historical BOM extraction; never executes formulas/macros."""
from io import BytesIO
from pathlib import PurePath
from zipfile import ZipFile, BadZipFile
from decimal import Decimal, InvalidOperation
import hashlib
from fastapi import HTTPException
from xml.etree.ElementTree import ParseError
from xlrd.biffh import XLRDError
try:
    from lxml.etree import XMLSyntaxError
except ImportError:
    XMLSyntaxError = ParseError
from app.services.engineering_bom import materials, imported_documents

LIMIT = 5 * 1024 * 1024


def rows(content, filename):
    suffix = PurePath(filename).suffix.lower()
    if not content or len(content) > LIMIT:
        raise HTTPException(422, '文件为空或超过 5MB')
    try:
        if suffix == '.xlsx':
            with ZipFile(BytesIO(content)) as archive:
                entries = archive.infolist()
                if len(entries) > 1000 or sum(e.file_size for e in entries) > 30 * 1024 * 1024:
                    raise ValueError('解压内容过大')
                if any('vbaProject' in e.filename or 'externalLinks/' in e.filename for e in entries):
                    raise ValueError('不接受宏或外部链接')
            import openpyxl
            book = openpyxl.load_workbook(BytesIO(content), read_only=True, data_only=False, keep_links=False)
            try:
                result = []
                for sheet in book:
                    if sheet.max_row > 550 or sheet.max_column > 30:
                        raise ValueError('每张表最多 550 行、30 列')
                    values = [list(row) for row in sheet.iter_rows(values_only=True)]
                    if any(any(c is not None for c in row) for row in values):
                        result.append((sheet.title, values))
                return result
            finally:
                book.close()
        if suffix == '.xls':
            import xlrd
            book = xlrd.open_workbook(file_contents=content, on_demand=True)
            try:
                result = []
                for sheet in book.sheets():
                    if sheet.nrows > 550 or sheet.ncols > 30:
                        raise ValueError('每张表最多 550 行、30 列')
                    values = [sheet.row_values(i) for i in range(sheet.nrows)]
                    if any(any(c not in ('', None) for c in row) for row in values):
                        result.append((sheet.name, values))
                return result
            finally:
                book.release_resources()
        raise ValueError('请选择 .xls 或 .xlsx 历史 BOM')
    except (ValueError, BadZipFile, KeyError, OSError, XLRDError, ParseError, XMLSyntaxError, EOFError, IndexError, TypeError) as error:
        raise HTTPException(422, '无法识别历史 BOM：' + str(error)[:160]) from error


def preview(db, content, filename):
    sheets = rows(content, filename)
    if len(sheets) != 1:
        raise HTTPException(422, '当前需一张有效 BOM 工作表；请拆分多张业务表后核对')
    sheet, values = sheets[0]
    headers = ['BOM层级', '子项物料编码', '物料名称', '物料属性', 'BOM版本', '数据状态', '单位',
               '用量：分子', '用量：分母', '标准用量', '子项类型', '实际数量', '备注']
    header_index = next((i for i, row in enumerate(values[:10]) if 'BOM层级' in row), None)
    if header_index is not None:
        header = [str(v).strip() if v is not None else '' for v in values[header_index]]
        if not all(h in header for h in headers[:-1]):
            raise HTTPException(422, '历史 BOM 缺少必要表头')
        columns = [header.index(h) if h in header else -1 for h in headers]
        start = header_index + 1
    else:
        # Legacy 92167 export: first column empty; verified 14-column layout only.
        columns = list(range(1, 14))
        start = next((i for i, row in enumerate(values) if any(c not in ('', None) for c in row)), len(values))
        if start == len(values) or len(values[start]) != 14 or values[start][1] not in (0, '0'):
            raise HTTPException(422, '未识别的无表头格式，请保留标准 BOM 表头')
    catalog = {r['code']: r for r in materials(db)}
    nodes, issues, stack = [], [], {}
    def number(value):
        try:
            n = Decimal(str(value))
            if not n.is_finite() or n < 0 or n > 100000000:
                raise ValueError()
            return str(n)
        except (InvalidOperation, ValueError):
            raise ValueError('用量必须为有限非负数字')
    for index, raw in enumerate(values[start:], start + 1):
        if all(c in ('', None) for c in raw):
            continue
        cells = [raw[c] if c >= 0 and c < len(raw) else '' for c in columns]
        source = {h: str(v) if v is not None else '' for h, v in zip(headers, cells)} | {'sheet': sheet, 'row': str(index)}
        try:
            if any(isinstance(v, str) and v.startswith('=') for v in cells):
                raise ValueError('公式单元格需另行核对，不能作为已确认用量')
            level = int(cells[0])
            if str(cells[0]) not in (str(level), f'{level}.0') or not 0 <= level <= 31:
                raise ValueError('层级无效')
            if level and level - 1 not in stack:
                raise ValueError('层级跳跃或缺少上级')
            if level == 0 and nodes:
                raise ValueError('文件包含多个根项')
            numerator, denominator = ('1', '1') if level == 0 else (number(cells[7]), number(cells[8]))
            if Decimal(denominator) == 0:
                raise ValueError('子项分母为零')
            code, name, unit = str(cells[1] or ''), str(cells[2] or ''), str(cells[6] or '')
            if not code or not name or not unit:
                raise ValueError('编码、名称或单位缺失')
            key = f'row-{index}'
            found = catalog.get(code)
            match = bool(found and found['status'] == 'ACTIVE' and found['name'] == name
                         and found['data'].get('unit') == unit
                         and found['data'].get('engineering', {}).get('approval') == 'APPROVED')
            warnings = []
            if PurePath(filename).suffix.lower() == '.xls':
                warnings.append('旧版 XLS 读取缓存值，须核对原表用量依据')
            if not match:
                warnings.append('物料未匹配／未审核，或名称单位不同')
            if cells[9] != cells[11]:
                warnings.append('标准用量与实际数量不一致')
            if level and Decimal(numerator) / Decimal(denominator) != Decimal(number(cells[9])):
                warnings.append('分子／分母与来源标准用量口径不同，请核对配比／上级展开')
            parent = stack.get(level - 1, '') if level else ''
            nodes.append(dict(key=key, parent=parent, material_id=found['id'] if match else '',
                material_version=found['version'] if match else 0, source_code=code, source_name=name,
                unit=unit, numerator=numerator, denominator=denominator, process='', exempt_loss=False,
                note=str(cells[12] or ''), source=source, review_required=bool(warnings), review_note=''))
            issues.extend(dict(row=index, message=w, blocking=False) for w in warnings)
            stack = {k: v for k, v in stack.items() if k < level}
            stack[level] = key
        except (ValueError, InvalidOperation, TypeError) as error:
            issues.append(dict(row=index, message=str(error), blocking=True))
            # Do not attach following rows to an earlier branch after malformed input.
            stack.clear()
    if not nodes or len(nodes) > 500:
        raise HTTPException(422, '需要 1～500 行有效用料')
    digest = hashlib.sha256(content).hexdigest()
    duplicates = imported_documents(db, digest)
    if duplicates:
        issues.append(dict(row=0, message='此文件已保存；请查看货号 ' + '、'.join(d['item_no'] for d in duplicates) + '，不同货号请复制原 BOM', blocking=True))
    return dict(filename=filename, sha256=digest, sheet=sheet, duplicates=duplicates,
                row_count=len(nodes), material_count=len({n['source_code'] for n in nodes}), issues=issues,
                can_save=not any(i['blocking'] for i in issues),
                data=dict(item_no='', name=nodes[0]['source_name'], specification='', nodes=nodes,
                          source_reference=f'{filename} / {sheet}', source_sha256=digest))
