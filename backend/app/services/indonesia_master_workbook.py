"""Read template-specific cell evidence and embedded photos without evaluating Excel."""
import base64
from collections import defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from io import BytesIO
import posixpath
from xml.etree import ElementTree as ET

from PIL import Image

NS = {
    's': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'xdr': 'http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing',
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
}
NUMERIC_LABELS = {'net_weight_kg': '单个净重', 'price': '采购单价', 'piece_usage': '单件用量', 'procurement_days': '采购周期'}
IMAGE_LIMIT = 1_500_000
IMAGE_TOTAL_LIMIT = 12_000_000


def template_units(headers, normalize):
    """Column positions are meaningful only after recognizing this exact detail layout."""
    expected = {4: '货号', 6: '产品中文名称', 7: '产品英文名称', 9: '类别', 10: '单位',
                11: '送货KG重量', 12: '送货数量', 13: '单位', 20: '图片', 41: '采购单价',
                52: '物料编码', 56: '单个净重'}
    if all(len(headers) >= col and normalize(str(headers[col - 1]).split('\n')[0]) == normalize(title)
           for col, title in expected.items()):
        return {'customs_unit': 10, 'unit': 13}
    return {}


def formula_cache(field, cached):
    """Only numeric business inputs may use saved results; never execute formulas/links."""
    if field not in NUMERIC_LABELS or cached.data_type == 'e' or isinstance(cached.value, bool) or not isinstance(cached.value, (int, float, Decimal)):
        return None
    try:
        value = Decimal(str(cached.value))
        if not value.is_finite() or not 0 <= value <= Decimal('1000000000000'):
            return None
        if field == 'procurement_days':
            return str(int(value)) if value == value.to_integral_value() and value <= 3650 else None
        with localcontext() as context:
            context.prec = 40
            return format(value.quantize(Decimal('.00000001'), rounding=ROUND_HALF_UP), 'f')
    except (InvalidOperation, ValueError, OverflowError):
        return None


def relationships(archive, part):
    path = posixpath.join(posixpath.dirname(part), '_rels', posixpath.basename(part) + '.rels')
    if path not in archive.namelist():
        return {}
    result = {}
    for node in ET.fromstring(archive.read(path)):
        target = node.get('Target', '')
        if node.get('TargetMode') == 'External' or not target or '\\' in target or ':' in target:
            continue
        resolved = posixpath.normpath(target.lstrip('/') if target.startswith('/') else posixpath.join(posixpath.dirname(part), target))
        if resolved.startswith('xl/') and resolved in archive.namelist():
            result[node.get('Id')] = (resolved, node.get('Type', ''))
    return result


def sheet_photos(archive, sheet_part, sheet_xml, image_column, rows, budget):
    """Return one verified embedded raster per actual material row; ambiguity stays visible."""
    result, warnings = {}, defaultdict(list)
    if not image_column or not rows:
        return result, warnings
    sheet_rels = relationships(archive, sheet_part)
    candidates = defaultdict(list)
    for drawing in sheet_xml.findall('s:drawing', NS):
        relation = sheet_rels.get(drawing.get('{'+NS['r']+'}id'))
        if not relation or not relation[1].endswith('/drawing'):
            continue
        part = relation[0]
        image_rels = relationships(archive, part)
        for anchor in ET.fromstring(archive.read(part)):
            start = anchor.find('xdr:from', NS)
            pictures = anchor.findall('xdr:pic', NS)
            if start is None or not pictures:
                continue
            try:
                row = int(start.findtext('xdr:row', namespaces=NS)) + 1
                col = int(start.findtext('xdr:col', namespaces=NS)) + 1
            except (TypeError, ValueError):
                continue
            if row not in rows or col != image_column:
                continue
            end = anchor.find('xdr:to', NS)
            if end is not None:
                try:
                    end_row = int(end.findtext('xdr:row', namespaces=NS)) + 1
                    end_offset = int(end.findtext('xdr:rowOff', default='0', namespaces=NS))
                except (TypeError, ValueError):
                    warnings[row].append('图片定位无法识别，请核对后补充图片')
                    continue
                if end_row > row + 1 or end_row == row + 1 and end_offset > 0 or end_row < row:
                    warnings[row].append('图片跨越多行，未自动关联，请核对后补充图片')
                    continue
            for picture in pictures:
                blip = picture.find('xdr:blipFill/a:blip', NS)
                image = image_rels.get(blip.get('{'+NS['r']+'}embed')) if blip is not None else None
                candidates[row].append(image[0] if image and image[1].endswith('/image') else None)
    decoded = {}
    for row, paths in candidates.items():
        if warnings[row] or len(paths) != 1 or not paths[0]:
            warnings[row].append('图片缺少唯一的内嵌来源，未自动关联，请核对后补充图片')
            continue
        path = paths[0]
        try:
            if path not in decoded:
                if archive.getinfo(path).file_size > IMAGE_LIMIT:
                    raise ValueError('large image')
                content = archive.read(path)
                with Image.open(BytesIO(content)) as picture:
                    if picture.format not in {'PNG', 'JPEG'} or picture.width * picture.height > 16_000_000:
                        raise ValueError('invalid image')
                    mime = 'png' if picture.format == 'PNG' else 'jpeg'
                    picture.verify()
                decoded[path] = f'data:image/{mime};base64,' + base64.b64encode(content).decode('ascii')
            data = decoded[path]
            if len(data) > 2_000_000:
                raise ValueError('large encoded image')
            if budget['bytes'] + len(data) > IMAGE_TOTAL_LIMIT:
                warnings[row].append('本次图片总量较大，未读取此图；请分批导入或另行补图')
                continue
            budget['bytes'] += len(data)
            result[row] = data
        except (ValueError, OSError, SyntaxError, Image.DecompressionBombError):
            warnings[row].append('图片格式或尺寸不符合要求，请补充 1.5 MB 内的 PNG／JPEG 图片')
    return result, warnings
