"""Surgical OOXML template output; preserve original drawings, styles and guide."""
import base64
import binascii
from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
from pathlib import Path
import posixpath
import re
from zipfile import ZipFile, ZIP_DEFLATED

from lxml import etree as ET
from PIL import Image
from app.services.indonesia_material_calculations import number, decimal_text, require, precise_decimals

NS = dict(s='http://schemas.openxmlformats.org/spreadsheetml/2006/main',
          r='http://schemas.openxmlformats.org/officeDocument/2006/relationships',
          p='http://schemas.openxmlformats.org/package/2006/relationships',
          xdr='http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing',
          a='http://schemas.openxmlformats.org/drawingml/2006/main')
TEMPLATE = Path(__file__).resolve().parents[1] / 'templates' / 'indonesia_materials_v1.xlsx'
SHEET_NAME = '5.21出货明细'
SHEET_PART = 'xl/worksheets/sheet6.xml'
DRAWING_PART = 'xl/drawings/drawing2.xml'
CUSTOMS_BLANK = {'B', 'C', 'E', 'N', 'O', *('V W X Y Z AA AB AC AD AE AF AG AH AI AJ AK'.split())}
CALC_NAME = '出货计算'
CALC_PART = 'xl/worksheets/indonesia-calculations.xml'
CALC_PREFIX = "'" + CALC_NAME + "'!"


def customs_conversion(material):
    rule = material.get('customs_rule')
    if rule:
        divisor = number(rule.get('divisor'))
        require(rule.get('basis') in {'weight', 'quantity'} and divisor > 0, '报关单位快照换算规则无效', 422)
        return rule['basis'], divisor
    unit, quantity_unit = material['customs_unit'].upper(), material['unit'].upper()
    if unit in {'KG', 'KGM', 'TNE'}:
        return 'weight', Decimal(1000 if unit == 'TNE' else 1)
    require(unit == quantity_unit or {unit, quantity_unit} <= {'PCS', 'PCE'}, '报关单位缺少明确换算关系', 422)
    return 'quantity', Decimal(1)


def xml(content):
    return ET.fromstring(content, ET.XMLParser(resolve_entities=False, no_network=True))


def serialized(node):
    return ET.tostring(node, encoding='UTF-8', xml_declaration=True, standalone=True)


def relationship_path(part):
    folder, name = posixpath.split(part)
    return posixpath.join(folder, '_rels', name + '.rels')


def target_path(part, target):
    return posixpath.normpath(posixpath.join(posixpath.dirname(part), target)).lstrip('/')


def reachable_parts(parts):
    """Drop all unreferenced worksheets/media, including unrelated source business data."""
    keep, queue = {'[Content_Types].xml'}, ['']
    while queue:
        part = queue.pop()
        if part:
            if part in keep:
                continue
            keep.add(part)
        rel_path = relationship_path(part) if part else '_rels/.rels'
        if rel_path not in parts:
            continue
        keep.add(rel_path)
        for rel in xml(parts[rel_path]):
            if rel.get('TargetMode') == 'External':
                continue
            target = target_path(part, rel.get('Target'))
            if target in parts and target not in keep:
                queue.append(target)
    return keep


def write_package(parts):
    keep = reachable_parts(parts)
    types = xml(parts['[Content_Types].xml'])
    for entry in list(types):
        if ET.QName(entry).localname == 'Override' and entry.get('PartName', '').lstrip('/') not in keep:
            types.remove(entry)
    parts['[Content_Types].xml'] = serialized(types)
    out = BytesIO()
    with ZipFile(out, 'w', ZIP_DEFLATED) as archive:
        for path in sorted(keep):
            archive.writestr(path, parts[path])
    return out.getvalue()


def prepare_template(source, destination):
    """Build a distributable template containing only the output and its dictionaries."""
    with ZipFile(source) as archive:
        parts = {p: archive.read(p) for p in archive.namelist() if not p.endswith('/')}
    workbook = xml(parts['xl/workbook.xml'])
    sheets = workbook.find('s:sheets', NS)
    keep_names = {SHEET_NAME, '类别金额', '单位对照'}
    retained = [s for s in sheets if s.get('name') in keep_names]
    require(len(retained) == 3, '原版模板的出货明细及单位／类别字典不完整', 422)
    retained.sort(key=lambda s: s.get('name') != SHEET_NAME)
    sheets[:] = retained
    for index, sheet in enumerate(sheets):
        sheet.set('state', 'visible' if index == 0 else 'hidden')
    rels = xml(parts['xl/_rels/workbook.xml.rels'])
    sheet_ids = {s.get('{'+NS['r']+'}id') for s in sheets}
    for rel in list(rels):
        category = rel.get('Type').rsplit('/', 1)[-1]
        if (category == 'worksheet' and rel.get('Id') not in sheet_ids) or category not in {'worksheet', 'styles', 'sharedStrings', 'theme'}:
            rels.remove(rel)
    for name in ('definedNames', 'externalReferences'):
        node = workbook.find('s:'+name, NS)
        if node is not None:
            workbook.remove(node)
    names = ET.Element('{'+NS['s']+'}definedNames')
    calculation = workbook.find('s:calcPr', NS)
    workbook.insert(workbook.index(calculation) if calculation is not None else len(workbook), names)
    ET.SubElement(names, '{'+NS['s']+'}definedName', name='_xlnm.Print_Area', localSheetId='0').text = f"'{SHEET_NAME}'!$A$3:$BE$64"
    book_view = workbook.find('s:bookViews/s:workbookView', NS)
    if book_view is not None:
        book_view.set('activeTab', '0')
        book_view.set('firstSheet', '0')
    parts['xl/workbook.xml'] = serialized(workbook)
    parts['xl/_rels/workbook.xml.rels'] = serialized(rels)
    drawing = xml(parts[DRAWING_PART])
    for anchor in list(drawing):
        # Latest user direction removes tutorial/example pictures. Actual
        # material photos are inserted from the shipment snapshot at export.
        if anchor.find('xdr:pic', NS) is not None:
            drawing.remove(anchor)
    drawing_rels = xml(parts[relationship_path(DRAWING_PART)])
    embedded = {n.get('{'+NS['r']+'}embed') for n in drawing.findall('.//a:blip', NS)}
    for rel in list(drawing_rels):
        if rel.get('Id') not in embedded:
            drawing_rels.remove(rel)
    parts[DRAWING_PART] = serialized(drawing)
    parts[relationship_path(DRAWING_PART)] = serialized(drawing_rels)
    # Compact shared strings to references on the three retained sheets only.
    shared = xml(parts['xl/sharedStrings.xml'])
    string_map, strings, refs = {}, [], 0
    for rel in rels:
        if not rel.get('Type').endswith('/worksheet'):
            continue
        path = target_path('xl/workbook.xml', rel.get('Target'))
        sheet = xml(parts[path])
        if path != SHEET_PART:
            # Hidden helpers carry only lookup dictionaries, never unrelated
            # source-workbook monetary summaries or shipment history.
            for row in sheet.findall('s:sheetData/s:row', NS):
                for cell in list(row):
                    ref = cell.get('r', '')
                    match = re.fullmatch(r'([A-Z]+)(\d+)', ref)
                    keep = bool(match) and ((path.endswith('sheet2.xml') and match[1] == 'B' and 3 <= int(match[2]) <= 39)
                                             or (path.endswith('sheet13.xml') and match[1] in {'A', 'B'} and int(match[2]) <= 18))
                    if not keep:
                        row.remove(cell)
        for cell in sheet.findall('.//s:c', NS):
            if cell.get('t') != 's':
                continue
            value = cell.find('s:v', NS)
            if value is None:
                continue
            original = int(value.text)
            if original not in string_map:
                string_map[original] = len(strings)
                strings.append(deepcopy(shared[original]))
            value.text = str(string_map[original])
            refs += 1
        parts[path] = serialized(sheet)
    shared[:] = strings
    shared.set('count', str(refs)); shared.set('uniqueCount', str(len(strings)))
    parts['xl/sharedStrings.xml'] = serialized(shared)
    # Source workbook application metadata lists unrelated business-sheet names.
    root_rels = xml(parts['_rels/.rels'])
    for rel in list(root_rels):
        if rel.get('Type').endswith('/extended-properties') or rel.get('Type').endswith('/custom-properties'):
            root_rels.remove(rel)
    parts['_rels/.rels'] = serialized(root_rels)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(write_package(parts))


def validate_image(data_uri):
    match = re.fullmatch(r'data:image/(png|jpeg);base64,([A-Za-z0-9+/=\r\n]+)', data_uri)
    require(match is not None, '物料图片仅支持 PNG／JPEG 文件', 422)
    try:
        content = base64.b64decode(match.group(2), validate=True)
        require(len(content) <= 1500000, '物料图片不能超过 1.5 MB', 422)
        with Image.open(BytesIO(content)) as picture:
            require(picture.format in {'PNG', 'JPEG'} and picture.width * picture.height <= 16000000, '图片格式不正确或尺寸过大', 422)
            width, height = picture.size
            picture.verify()
    except (ValueError, OSError, binascii.Error, Image.DecompressionBombError) as exc:
        require(False, '无法读取物料图片，请选择有效 PNG／JPEG', 422)
    return content, 'png' if match.group(1) == 'png' else 'jpeg', width, height


def set_cell(cell, value=None, formula=None):
    require(not isinstance(value, str) or len(value) <= 32767, '出货字段内容过长，无法在原版单元格中完整显示，请核对来源资料', 422)
    require(formula is None or len(formula) <= 8192, '出货计算公式过长，请核对本次采购及包装明细', 422)
    for node in list(cell):
        cell.remove(node)
    cell.attrib.pop('t', None)
    if formula is not None:
        if isinstance(value, str):
            cell.set('t', 'str')
        ET.SubElement(cell, '{'+NS['s']+'}f').text = formula
        ET.SubElement(cell, '{'+NS['s']+'}v').text = value if isinstance(value, str) else decimal_text(value)
    elif value is None or value == '':
        return
    elif isinstance(value, (Decimal, int)):
        ET.SubElement(cell, '{'+NS['s']+'}v').text = str(value)
    else:
        # Inline strings never evaluate user values as Excel formulas.
        cell.set('t', 'inlineStr')
        text = ET.SubElement(ET.SubElement(cell, '{'+NS['s']+'}is'), '{'+NS['s']+'}t')
        text.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
        text.text = str(value)


def shift_reference(reference, delta):
    return re.sub(r'(\$?[A-Z]{1,3}\$?)(\d+)', lambda m: m[1] + str(int(m[2]) + delta if int(m[2]) >= 6 else int(m[2])), reference)


def unique_text(values):
    return '／'.join(dict.fromkeys(str(v) for v in values if v))


def sum_refs(refs):
    return 'SUM(' + ','.join(refs) + ')'


def wrap_cell(parts, cell):
    """Inherit the original font/number/border style, allowing source lists to wrap."""
    styles = xml(parts['xl/styles.xml'])
    formats = styles.find('s:cellXfs', NS)
    style = deepcopy(formats[int(cell.get('s', '0'))])
    alignment = style.find('s:alignment', NS)
    if alignment is not None and alignment.get('wrapText') == '1':
        return
    if alignment is None:
        alignment = ET.SubElement(style, '{'+NS['s']+'}alignment')
    alignment.set('wrapText', '1')
    style.set('applyAlignment', '1')
    cell.set('s', str(len(formats)))
    formats.append(style); formats.set('count', str(len(formats)))
    parts['xl/styles.xml'] = serialized(styles)


class Calculations:
    """Hidden, frozen commercial and physical inputs; no duplicated visible rows."""
    def __init__(self):
        self.sheet = ET.Element('{'+NS['s']+'}worksheet', nsmap={None: NS['s']})
        self.data = ET.SubElement(self.sheet, '{'+NS['s']+'}sheetData')
        self.add(dict(zip([*'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'AA', 'AB'], [
            '类型', '物料编码', '供应商／包装组', '币种', '正常数量', '免费备品', '采购单价', '计费因子',
            '计价单重（kg）', '采购金额', '物理箱数', '物料净重', '分摊纸箱重', '每箱毛重', '长(cm)',
            '宽(cm)', '高(cm)', '单箱CBM', '组总CBM', '实装数量', '单件净重', '纸箱单重', '组物料净重',
            '采购日期', '每箱毛重组合／供应商总额', '采购单号', '成品合同', '货号'])))

    def add(self, values, formulas=None):
        index = len(self.data) + 1
        row = ET.SubElement(self.data, '{'+NS['s']+'}row', r=str(index))
        for col in sorted(values, key=lambda c: (len(c), c)):
            cell = ET.SubElement(row, '{'+NS['s']+'}c', r=f'{col}{index}')
            set_cell(cell, values[col], (formulas or {}).get(col))
        return index

    def ref(self, col, row):
        return f'{CALC_PREFIX}{col}{row}'


@precise_decimals
def build_rows(shipment):
    snapshots = {r['allocation_id']: r for r in shipment['snapshot_lines']}
    materials, sources, supplier_currencies = {}, {}, {}
    calc = Calculations()
    identity = ('specification', 'unit', 'customs_unit', 'net_weight_kg', 'export_company')
    for line in snapshots.values():
        material, supply = line['material'], line['supply']
        code = material['code']
        currency = supply['currency'].upper()
        require(supplier_currencies.setdefault(supply['supplier'], currency) == currency,
                f'供应商 {supply["supplier"]} 本次采购币种不一致，请核对采购资料；同供应商本次只能使用一种币种', 422)
        require(all(material.get(f) for f in ('english_name', 'category', 'usage', 'department', 'export_company', 'image_data')),
                '请补齐英文名、类别、用途、使用部门、出口公司及物料图片后再确认出货', 422)
        if code not in materials:
            materials[code] = dict(material=material, lines=[], packs=[], amounts={}, currency=currency)
        target = materials[code]
        require(customs_conversion(material) == customs_conversion(target['material']), f'物料 {code} 的报关换算快照不一致，不能合并', 422)
        require(all((number(material[f]) == number(target['material'][f]) if f == 'net_weight_kg'
                     else material[f] == target['material'][f]) for f in identity),
                f'物料 {code} 的规格、单位、单重或出口公司快照不一致，请核对出货资料后再汇总', 422)
        require(target['currency'] == currency,
                f'物料 {code} 的采购来源币种不一致，不能把不同币种合计为一行金额，请核对采购资料或本次出货范围', 422)
        normal, spare = number(line['normal_quantity']), number(line['spare_quantity'])
        basis = normal
        weight_field = 'net_weight_kg' if supply.get('billing_weight_source') == 'net_weight_kg' else 'billing_weight_kg'
        weight = number(material.get(weight_field) or 0)
        index = len(calc.data) + 1
        expression = f'E{index}*G{index}/H{index}'
        if supply['billing_basis'] == 'weight' and normal > 0:
            require(weight > 0, '按重量计价缺少有效计价单重，请补全本批出货资料', 422)
            basis *= weight
            expression = f'E{index}*I{index}*G{index}/H{index}'
        amount = basis * number(supply['price']) / number(supply['billing_factor'])
        source = calc.add(dict(A='采购来源', B=code, C=supply['supplier'], D=currency, E=normal, F=spare,
                              G=number(supply['price']), H=number(supply['billing_factor']), I=weight, J=amount,
                              X=supply['purchase_date'], Z=supply['purchase_no'], AA=line['contract_no'], AB=line['item_no']), {'J': expression})
        sources[line['allocation_id']] = code
        target['lines'].append(line)
        target['amounts'].setdefault(supply['supplier'], []).append((source, amount))

    supplier_totals = {}
    for code, target in materials.items():
        amounts = {}
        for supplier, entries in target['amounts'].items():
            amount = sum((amount for _, amount in entries), Decimal(0)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
            row = calc.add(dict(A='供应商物料分项', B=code, C=supplier, D=target['currency'], J=amount),
                           {'J': 'ROUND('+sum_refs([f'J{r}' for r, _ in entries])+',2)'})
            amounts[supplier] = (row, amount)
            supplier_totals.setdefault(supplier, []).append((row, amount))
        target['amounts'] = amounts

    parents = {code: code for code in materials}
    def root(code):
        while parents[code] != code:
            parents[code] = parents[parents[code]]
            code = parents[code]
        return code
    groups = []
    for group in shipment['packing_totals']['groups']:
        packed = {}
        for item in group['items']:
            code = sources[item['allocation_id']]
            entry = packed.setdefault(code, dict(normal=Decimal(0), spare=Decimal(0)))
            entry['normal'] += number(item['normal_quantity']); entry['spare'] += number(item['spare_quantity'])
        require(packed, '包装组不能为空', 422)
        leader = next(iter(packed))
        for code in packed:
            parents[root(code)] = root(leader)
        weight_sum = sum(((e['normal'] + e['spare']) * number(materials[c]['material']['net_weight_kg']) for c, e in packed.items()), Decimal(0))
        index = len(calc.data) + 1
        group_ref = calc.add(dict(A='实际包装组', C=group['label'], K=group['cartons'], O=number(group['length_cm']),
                                 P=number(group['width_cm']), Q=number(group['height_cm']), R=number(group['single_cbm']),
                                 S=number(group['total_cbm']), V=number(group['carton_weight_kg']), W=weight_sum),
                             {'R': f'O{index}*P{index}*Q{index}/28316.75*0.0283', 'S': f'ROUND(R{index}*K{index},2)'})
        for code, entry in packed.items():
            target = materials[code]
            dimensions = tuple(number(group[f]) for f in ('length_cm', 'width_cm', 'height_cm'))
            require(target.setdefault('dimensions', dimensions) == dimensions,
                    f'物料 {code} 本次纸箱长宽高不一致，请核对包装资料；同物料本次纸箱尺寸须相同', 422)
            physical = entry['normal'] + entry['spare']
            net = physical * number(target['material']['net_weight_kg'])
            carton = number(group['carton_weight_kg']) * group['cartons'] * net / weight_sum
            index = len(calc.data) + 1
            per_box = (net+carton)/group['cartons']
            detail = calc.add(dict(A='箱内物料', B=code, C=group['label'], E=entry['normal'], F=entry['spare'],
                                   K=group['cartons'], L=net, M=carton, N=(net+carton)/group['cartons'], T=physical,
                                   U=number(target['material']['net_weight_kg']),
                                   Y=f'{group["cartons"]}箱×{format(per_box.quantize(Decimal(".000001"), rounding=ROUND_HALF_UP), ".6f")} kg'),
                               {'K': f'K{group_ref}', 'L': f'(E{index}+F{index})*U{index}',
                                'M': f'V{group_ref}*K{group_ref}*L{index}/W{group_ref}',
                                'N': f'(L{index}+M{index})/K{index}', 'T': f'E{index}+F{index}',
                                'Y': f'K{index}&"箱×"&TEXT(N{index},"0.000000")&" kg"'})
            target['packs'].append(dict(group=group, ref=detail, physical=physical, net=net, carton=carton))
        groups.append(dict(codes=list(packed), group=group, ref=group_ref))

    components = {}
    for code in materials:
        components.setdefault(root(code), dict(codes=[], groups=[]))['codes'].append(code)
    for group in groups:
        components[root(group['codes'][0])]['groups'].append(group)
    result = []
    for component in components.values():
        first = len(result)
        for code in component['codes']:
            target = materials[code]; material = target['material']; packs = target['packs']; lines = target['lines']
            require(packs, f'物料 {code} 没有包装明细', 422)
            normal = sum((number(line['normal_quantity']) for line in lines), Decimal(0))
            spare = sum((number(line['spare_quantity']) for line in lines), Decimal(0))
            physical = normal + spare
            net = sum((p['net'] for p in packs), Decimal(0)); carton = sum((p['carton'] for p in packs), Decimal(0))
            unit = material['customs_unit'].upper()
            customs_basis, customs_divisor = customs_conversion(material)
            customs = net / customs_divisor if customs_basis == 'weight' else physical
            amount = sum((amount for _, amount in target['amounts'].values()), Decimal(0))
            loadings = {}
            for p in packs:
                loading = p['physical'] / p['group']['cartons']
                loadings[loading] = loadings.get(loading, 0) + p['group']['cartons']
            gross_per_box = [(p['net']+p['carton'])/p['group']['cartons'] for p in packs]
            values = dict(D=unique_text(line['item_no'] for line in lines), F=material['name'], G=material['english_name'],
                          H=material['specification'], I=material['category'], J=material['customs_unit'], K=customs, L=normal,
                          M=material['unit'], P=net+carton, Q=net, R=number(packs[0]['group']['single_cbm']), U=material['usage'],
                          AL=unique_text(target['amounts']), AM=unique_text(line['supply']['purchase_date'] for line in lines),
                          AN=unique_text(line['supply']['purchase_no'] for line in lines),
                          AO=(amount/customs).quantize(Decimal('.0001'), rounding=ROUND_HALF_UP), AP=amount,
                          AR=material['export_company'], AS='華登製品實業有限公司' if shipment['recipient'] == 'RRI' else '華登(全球)有限公司',
                          AU='＋'.join(f'{count}箱×{decimal_text(loading.normalize())}' for loading, count in loadings.items()),
                          AV=unique_text(p['group']['pallet'] for p in packs),
                          AW=target['dimensions'][0], AX=target['dimensions'][1], AY=target['dimensions'][2], AZ=code,
                          BA=material['department'], BC=(net+carton)/physical, BD=number(material['net_weight_kg']),
                          BE='；'.join(value for value in [f'备品 {decimal_text(spare)} {material["unit"]}，免费' if spare else '',
                              f'采购币种 {target["currency"]}', '合同 '+unique_text(line['contract_no'] for line in lines),
                              unique_text(p['group']['label'] for p in packs), shipment['remarks']] if value))
            if len(set(gross_per_box)) == 1:
                values['BB'] = gross_per_box[0]
                bb_formula = calc.ref('N', packs[0]['ref'])
            else:
                values['BB'] = '＋'.join(f'{p["group"]["cartons"]}箱×{format(weight.quantize(Decimal(".000001"), rounding=ROUND_HALF_UP), ".6f")} kg' for p, weight in zip(packs, gross_per_box))
                bb_formula = '&"＋"&'.join(calc.ref('Y', p['ref']) for p in packs)
            result.append(dict(values=values, material=material, physical=physical, customs_unit=unit, customs_basis=customs_basis, customs_divisor=customs_divisor, packs=packs,
                               amounts=target['amounts'], bb_formula=bb_formula))
        start = result[first]
        start['component'] = component
        start['span'] = len(component['codes'])
        start['values']['AT'] = sum(g['group']['cartons'] for g in component['groups'])
        start['values']['S'] = sum((number(g['group']['total_cbm']) for g in component['groups']), Decimal(0))
    require(0 < len(result) <= 2000, '正式出货明细需有装箱内容且不能超过 2000 行', 422)
    summaries = {}
    for supplier, entries in supplier_totals.items():
        amount = sum((amount for _, amount in entries), Decimal(0))
        index = len(calc.data) + 1
        ref = calc.add(dict(A='供应商出货合计', C=supplier, D=supplier_currencies[supplier], J=amount,
                            Y=f'{supplier}: {format(amount, ".2f")}'),
                       {'J': sum_refs([f'J{r}' for r, _ in entries]), 'Y': f'C{index}&": "&TEXT(J{index},"0.00")'})
        summaries[supplier] = (ref, amount)
    return result, calc, summaries


def add_image(parts, drawing, rels, data_uri, row, sequence):
    content, extension, width, height = validate_image(data_uri)
    path = f'xl/media/indonesia-material-{sequence}.{extension}'
    rel_id = f'rrnMaterial{sequence}'
    parts[path] = content
    ET.SubElement(rels, '{'+NS['p']+'}Relationship', Id=rel_id, Type=NS['r']+'/image', Target=f'../media/indonesia-material-{sequence}.{extension}')
    anchor = ET.SubElement(drawing, '{'+NS['xdr']+'}oneCellAnchor')
    start = ET.SubElement(anchor, '{'+NS['xdr']+'}from')
    for tag, value in [('col', 19), ('colOff', 250190), ('row', row-1), ('rowOff', 98425)]:
        ET.SubElement(start, '{'+NS['xdr']+'}'+tag).text = str(value)
    scale = min(1240155 / 9525 / width, 1228725 / 9525 / height)
    cx, cy = int(width * scale * 9525), int(height * scale * 9525)
    ET.SubElement(anchor, '{'+NS['xdr']+'}ext', cx=str(cx), cy=str(cy))
    pic = ET.SubElement(anchor, '{'+NS['xdr']+'}pic')
    nv = ET.SubElement(pic, '{'+NS['xdr']+'}nvPicPr')
    ET.SubElement(nv, '{'+NS['xdr']+'}cNvPr', id=str(1000+sequence), name=f'物料图片 {sequence}')
    ET.SubElement(nv, '{'+NS['xdr']+'}cNvPicPr')
    fill = ET.SubElement(pic, '{'+NS['xdr']+'}blipFill')
    ET.SubElement(fill, '{'+NS['a']+'}blip', {'{'+NS['r']+'}embed': rel_id})
    stretch = ET.SubElement(fill, '{'+NS['a']+'}stretch'); ET.SubElement(stretch, '{'+NS['a']+'}fillRect')
    shape = ET.SubElement(pic, '{'+NS['xdr']+'}spPr')
    transform = ET.SubElement(shape, '{'+NS['a']+'}xfrm')
    ET.SubElement(transform, '{'+NS['a']+'}off', x='0', y='0'); ET.SubElement(transform, '{'+NS['a']+'}ext', cx=str(cx), cy=str(cy))
    geometry = ET.SubElement(shape, '{'+NS['a']+'}prstGeom', prst='rect'); ET.SubElement(geometry, '{'+NS['a']+'}avLst')
    ET.SubElement(anchor, '{'+NS['xdr']+'}clientData')
    types = xml(parts['[Content_Types].xml'])
    if not any(t.get('Extension') == extension for t in types):
        ET.SubElement(types, '{http://schemas.openxmlformats.org/package/2006/content-types}Default', Extension=extension,
                      ContentType='image/png' if extension == 'png' else 'image/jpeg')
        parts['[Content_Types].xml'] = serialized(types)


def export_shipment(shipment):
    return export_shipment_with_summary(shipment)[0]


def export_shipment_with_summary(shipment):
    require(TEMPLATE.is_file(), '出货明细原版模板未安装，请联系管理员', 503)
    items, calc, supplier_summaries = build_rows(shipment)
    with ZipFile(TEMPLATE) as archive:
        parts = {p: archive.read(p) for p in archive.namelist()}
    sheet = xml(parts[SHEET_PART]); data = sheet.find('s:sheetData', NS)
    base_row = next(r for r in data if r.get('r') == '4')
    delta = max(len(items)-2, 0)
    # Keep the entire guide below the expanding output, including cell comments and objects.
    for old in list(data):
        index = int(old.get('r'))
        if index in {4, 5}:
            data.remove(old)
        elif index >= 6 and delta:
            old.set('r', str(index + delta))
            for cell in old:
                cell.set('r', shift_reference(cell.get('r'), delta))
    for reference in sheet.xpath('//*[@sqref or @ref]'):
        for attribute in ('sqref', 'ref'):
            if reference.get(attribute):
                reference.set(attribute, shift_reference(reference.get(attribute), delta))
    drawing = xml(parts[DRAWING_PART]); rels = xml(parts[relationship_path(DRAWING_PART)])
    if delta:
        for r in drawing.findall('.//xdr:row', NS):
            if int(r.text) >= 5:
                r.text = str(int(r.text) + delta)
        comments = xml(parts['xl/comments2.xml'])
        for comment in comments.findall('s:commentList/s:comment', NS):
            comment.set('ref', shift_reference(comment.get('ref'), delta))
        parts['xl/comments2.xml'] = serialized(comments)
        vml = xml(parts['xl/drawings/vmlDrawing2.vml'])
        for node in vml.iter():
            if ET.QName(node).localname == 'Row' and node.text and int(node.text) >= 5:
                node.text = str(int(node.text) + delta)
            elif ET.QName(node).localname == 'Anchor' and node.text:
                coords = [int(x.strip()) for x in node.text.split(',')]
                for offset in (2, 6):
                    if coords[offset] >= 5:
                        coords[offset] += delta
                node.text = ', '.join(str(x) for x in coords)
        parts['xl/drawings/vmlDrawing2.vml'] = serialized(vml)
    shown_suppliers = set()
    merge_ranges = []
    for index, item in enumerate(items, 4):
        row = deepcopy(base_row); row.set('r', str(index))
        columns = {}
        for cell in row:
            column = re.sub(r'\d+', '', cell.get('r'))
            if len(column) <= 2 and (len(column) == 1 or column <= 'BE'):
                cell.set('r', column + str(index)); set_cell(cell); columns[column] = cell
        for cell in list(row):
            if re.sub(r'\d+', '', cell.get('r')) not in columns:
                row.remove(cell)
        values = dict(A=index-3, **item['values'])
        for column, value in values.items():
            set_cell(columns[column], value)
        for column in CUSTOMS_BLANK:
            set_cell(columns[column])
        formulas = dict(Q=f'{decimal_text(item["physical"])}*BD{index}',
                        P=f'Q{index}+'+sum_refs([calc.ref('M', p['ref']) for p in item['packs']]),
                        R=f'AW{index}*AX{index}*AY{index}/28316.75*0.0283',
                        AP=sum_refs([calc.ref('J', r) for r, _ in item['amounts'].values()]),
                        AO=f'ROUND(AP{index}/K{index},4)', BB=item['bb_formula'], BC=f'P{index}/{decimal_text(item["physical"])}')
        if 'component' in item:
            formulas['S'] = sum_refs([calc.ref('S', g['ref']) for g in item['component']['groups']])
            if item['span'] > 1:
                merge_ranges.extend(f'{col}{index}:{col}{index+item["span"]-1}' for col in ('AT', 'S'))
        formulas['K'] = (f'Q{index}' if item['customs_divisor'] == 1 else f'Q{index}/{decimal_text(item["customs_divisor"])}') if item['customs_basis'] == 'weight' else decimal_text(item['physical'])
        for column, formula in formulas.items():
            set_cell(columns[column], values[column], formula)
        pending_suppliers = [s for s in item['amounts'] if s not in shown_suppliers]
        if pending_suppliers:
            supplier_values, supplier_formulas = [], []
            for supplier in pending_suppliers:
                reference, total = supplier_summaries[supplier]
                supplier_values.append(f'{supplier}: {format(total, ".2f")}')
                supplier_formulas.append(calc.ref('Y', reference))
            if len(item['amounts']) == 1:
                supplier = pending_suppliers[0]
                reference, total = supplier_summaries[supplier]
                set_cell(columns['AQ'], total, sum_refs([calc.ref('J', reference)]))
            else:
                set_cell(columns['AQ'], '\n'.join(supplier_values), '&CHAR(10)&'.join(supplier_formulas))
                wrap_cell(parts, columns['AQ'])
            shown_suppliers.update(pending_suppliers)
        data.append(row)
        add_image(parts, drawing, rels, item['material']['image_data'], index, index-3)
    if merge_ranges:
        merges = sheet.find('s:mergeCells', NS)
        if merges is None:
            merges = ET.Element('{'+NS['s']+'}mergeCells')
            # OOXML requires merges before data validations and page/drawing nodes.
            previous = sheet.find('s:sheetData', NS)
            for name in ('sheetProtection', 'protectedRanges', 'scenarios', 'autoFilter', 'sortState', 'dataConsolidate', 'customSheetViews'):
                found = sheet.find('s:'+name, NS)
                if found is not None:
                    previous = found
            sheet.insert(sheet.index(previous)+1, merges)
        for reference in merge_ranges:
            ET.SubElement(merges, '{'+NS['s']+'}mergeCell', ref=reference)
        merges.set('count', str(len(merges)))
    for cell in sheet.findall('s:sheetData/s:row/s:c', NS):
        if cell.get('r') in {'N1', 'Z1', 'AB2', 'AP1', 'AP2', 'AQ1', 'AQ2'}:
            set_cell(cell)
    data[:] = sorted(data, key=lambda row: int(row.get('r')))
    # Restrict category dropdowns to actual item cells; the source accidentally included guide cells.
    validations = sheet.find('s:dataValidations', NS)
    if validations is not None:
        base = deepcopy(validations[0]); validations[:] = [base]
        validations.set('count', '1'); base.set('sqref', f'I4:I{len(items)+3}')
    workbook = xml(parts['xl/workbook.xml'])
    for name in workbook.findall('s:definedNames/s:definedName', NS):
        name.text = shift_reference(name.text, delta)
    calculation = workbook.find('s:calcPr', NS)
    if calculation is not None:
        calculation.set('fullCalcOnLoad', '1'); calculation.set('forceFullCalc', '1')
    rels_book = xml(parts['xl/_rels/workbook.xml.rels'])
    calc_rel = 'rrnCalculations'
    ET.SubElement(rels_book, '{'+NS['p']+'}Relationship', Id=calc_rel, Type=NS['r']+'/worksheet',
                  Target='worksheets/indonesia-calculations.xml')
    sheets = workbook.find('s:sheets', NS)
    ET.SubElement(sheets, '{'+NS['s']+'}sheet', name=CALC_NAME,
                  sheetId=str(max(int(s.get('sheetId')) for s in sheets)+1), state='hidden',
                  attrib={'{'+NS['r']+'}id': calc_rel})
    types = xml(parts['[Content_Types].xml'])
    ET.SubElement(types, '{http://schemas.openxmlformats.org/package/2006/content-types}Override',
                  PartName='/'+CALC_PART, ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml')
    parts['[Content_Types].xml'] = serialized(types)
    parts['xl/_rels/workbook.xml.rels'] = serialized(rels_book)
    parts[CALC_PART] = serialized(calc.sheet)
    parts['xl/workbook.xml'] = serialized(workbook)
    parts[SHEET_PART] = serialized(sheet)
    parts[DRAWING_PART] = serialized(drawing)
    parts[relationship_path(DRAWING_PART)] = serialized(rels)
    currencies = {line['supply']['supplier']: line['supply']['currency'].upper() for line in shipment['snapshot_lines']}
    summary = [dict(name=supplier, currency=currencies[supplier],
                    materials=sum(supplier in item['amounts'] for item in items), amount=format(amount, '.2f'))
               for supplier, (_, amount) in supplier_summaries.items()]
    return write_package(parts), summary
