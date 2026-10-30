"""Read template-specific cell evidence and embedded photos without evaluating Excel."""
from collections import defaultdict
from decimal import Decimal, DecimalException, InvalidOperation, ROUND_HALF_UP, localcontext
import posixpath
import re
from xml.etree import ElementTree as ET

from PIL import Image
from app.services.indonesia_master_images import SOURCE_IMAGE_LIMIT, prepare_photo

NS = {
    's': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'xdr': 'http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing',
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
}
NUMERIC_LABELS = {'net_weight_kg': '单个净重', 'price': '采购单价', 'piece_usage': '单件用量', 'procurement_days': '采购周期'}
IMAGE_TOTAL_LIMIT = 12_000_000


def template_units(headers, normalize):
    """Recognize the shipping quantity block, not a fixed number/order of all columns."""
    labels = [normalize(str(value).split('\n')[0]) for value in headers]
    # The maintained 57-column and alternate 49-column forms share this semantic layout.
    required = {'货号', '产品中文名称', '产品英文名称', '类别', '图片'}
    if not {normalize(value) for value in required}.issubset(labels):
        return {}
    blocks = [index for index in range(len(labels) - 3)
              if labels[index:index + 4] == [normalize(value) for value in
                  ('单位', '送货KG重量', '送货数量', '单位')]]
    if len(blocks) == 1:
        return {'customs_unit': blocks[0] + 1, 'unit': blocks[0] + 4}
    return {}


def named_piece_usage(name):
    """Only the approved Chinese-name quantity suffix; dimensions stay manual."""
    match = re.fullmatch(r'(.*?[\u3400-\u9fff])\s*[*＊]\s*(\d+(?:\.\d{1,8})?)\s*', name or '')
    if not match or re.search(r'[*＊×]', match[1]):
        return None
    value = Decimal(match[2])
    return str(value) if 0 < value <= Decimal('1000000000000') else None


def shipment_weight_columns(headers, columns, normalize):
    units = template_units(headers, normalize)
    if not units or any(columns.get(key) != col for key, col in units.items()):
        return None
    totals = [index for index, title in enumerate(headers, 1) if normalize(title) in {
        normalize('净重总重Total Net weight（KGM）'), normalize('净重总重（KGM）'),
        normalize('总净重（kg）'), normalize('总净重（KGM）')}]
    return (totals[0], units['unit'] - 1) if len(totals) == 1 else None


def price_currency(number_format):
    """Only explicit currency literals on the chosen price cell, never a bare $/¥."""
    literals = re.findall(r'"([^"]*)"', number_format or '')
    literals += re.findall(r'\[\$([A-Za-z$]+)(?:-[^\]]+)?\]', number_format or '')
    codes = set()
    for literal in literals:
        for pattern, code in [(r'US\$|USD|美元', 'USD'), (r'HK\$|HKD|港币', 'HKD'),
                              (r'RMB|CNY|人民币', 'RMB')]:
            if re.search(r'(?<![A-Za-z])(?:' + pattern + r')(?![A-Za-z])', literal, re.IGNORECASE):
                codes.add(code)
    return next(iter(codes)) if len(codes) == 1 else None


def derived_net_weight(cells, cached_cells, total_col, quantity_col, unit):
    """Per-quantity-unit net weight from an individual row's KG total and quantity."""
    if not unit:
        return None
    inputs = []
    for col in (total_col, quantity_col):
        cell = cells[col - 1]
        cached = cached_cells[col - 1] if cell.data_type == 'f' else cell
        if cached.data_type in {'e', 'f'} or isinstance(cached.value, bool):
            return None
        if cell.data_type == 'f' and not isinstance(cached.value, (int, float, Decimal)):
            return None
        try:
            if len(str(cached.value)) > 100:
                return None
            value = Decimal(str(cached.value))
            if not value.is_finite() or not 0 <= value <= Decimal('1000000000000'):
                return None
        except (InvalidOperation, ValueError, TypeError):
            return None
        inputs.append(dict(cell=cell.coordinate, value=str(value),
                           **(dict(formula=cell.value, cached_value=str(cached.value)) if cell.data_type == 'f' else {})))
    total, quantity = (Decimal(entry['value']) for entry in inputs)
    if quantity <= 0:
        return None
    try:
        with localcontext() as context:
            context.prec = 40
            value = total / quantity
            if value > Decimal('1000000000000'):
                return None
            value = value.quantize(Decimal('.00000001'), rounding=ROUND_HALF_UP)
    except (DecimalException, OverflowError):
        return None
    if total > 0 and value == 0:
        return None
    return dict(value=format(value, 'f'), inputs=inputs, quantity_unit=unit, method='total_net_div_quantity')


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
    result, seen = {}, set()
    for node in ET.fromstring(archive.read(path)):
        relation_id = node.get('Id')
        if relation_id in seen:
            result.pop(relation_id, None)
            continue
        seen.add(relation_id)
        target = node.get('Target', '')
        if node.get('TargetMode') == 'External' or not target or '\\' in target or ':' in target:
            continue
        resolved = posixpath.normpath(target.lstrip('/') if target.startswith('/') else posixpath.join(posixpath.dirname(part), target))
        if resolved.startswith('xl/') and resolved in archive.namelist():
            result[relation_id] = (resolved, node.get('Type', ''))
    return result


def cell_image_candidates(archive, references):
    """Resolve static WPS DISPIMG IDs only; never evaluate formulas or fetch links."""
    result = defaultdict(list)
    if not references or 'xl/cellimages.xml' not in archive.namelist():
        return result
    rels = relationships(archive, 'xl/cellimages.xml')
    for picture in ET.fromstring(archive.read('xl/cellimages.xml')).iter('{'+NS['xdr']+'}pic'):
        name = picture.find('xdr:nvPicPr/xdr:cNvPr', NS)
        if name is None or name.get('name') not in references:
            continue
        blip = picture.find('xdr:blipFill/a:blip', NS)
        image = rels.get(blip.get('{'+NS['r']+'}embed')) if blip is not None else None
        result[name.get('name')].append(image[0] if image and image[1].endswith('/image') else None)
    return result


def sheet_photos(archive, sheet_part, sheet_xml, image_column, rows, budget, cell_images=None):
    """Return one verified embedded raster per actual material row; ambiguity stays visible."""
    result, warnings, evidence = {}, defaultdict(list), {}
    if not image_column or not rows:
        return result, warnings, evidence
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
    cell_ids = {}
    for row, formula in (cell_images or {}).items():
        if row not in rows:
            continue
        match = re.fullmatch(r'\s*=(?:_xlfn\.)?DISPIMG\(\s*"([^"\r\n]{1,200})"\s*[,;]\s*1\s*\)\s*', formula, re.IGNORECASE)
        if match:
            cell_ids[row] = match[1]
        else:
            warnings[row].append('图片单元格不是可识别的内嵌图片引用，请核对后补图')
    embedded = cell_image_candidates(archive, set(cell_ids.values()))
    for row, name in cell_ids.items():
        candidates[row].extend(embedded.get(name, [None]))
    decoded, failed = {}, {}
    for row, paths in candidates.items():
        if warnings[row] or len(paths) != 1 or not paths[0]:
            warnings[row].append('图片缺少唯一的内嵌来源，未自动关联，请核对后补充图片')
            continue
        path = paths[0]
        if path in failed:
            warnings[row].append(failed[path])
            continue
        if budget['bytes'] >= IMAGE_TOTAL_LIMIT:
            warnings[row].append('本次图片总量较大，未读取此图；请分批导入或另行补图')
            continue
        try:
            if path in decoded:
                data, info = decoded[path]
            else:
                if archive.getinfo(path).file_size > SOURCE_IMAGE_LIMIT:
                    raise ValueError('large image')
                content = archive.read(path)
                data, info = prepare_photo(content)
            if budget['bytes'] + len(data) > IMAGE_TOTAL_LIMIT:
                failed[path] = '本次图片总量较大，未读取此图；请分批导入或另行补图'
                warnings[row].append(failed[path])
                continue
            decoded[path] = data, info
            budget['bytes'] += len(data)
            result[row] = data
            evidence[row] = dict(info, source_part=path)
        except (ValueError, OSError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            failed[path] = '图片无法自动处理：请核对图片是否损坏、为静态 PNG／JPEG，且不超过 32 MB／1600 万像素；物料行已保留'
            warnings[row].append(failed[path])
    return result, warnings, evidence
