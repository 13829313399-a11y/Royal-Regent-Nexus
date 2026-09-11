"""Render into the original workbook layout without editing the stored source."""
from io import BytesIO
from zipfile import ZipFile
from xml.etree import ElementTree as ET
import posixpath
import re
from decimal import Decimal as D
from sqlalchemy import select
from app.models import spray_production as m
from app.services import spray_production as s
from app.services.spray_history import NUMBERS
from app.services.spray_calculations import arithmetic
from openpyxl.formula.translate import Translator
from openpyxl.utils.cell import range_boundaries, get_column_letter
NS={"s":"http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
TAG="{"+NS["s"]+"}"


def expand_shared_formulas(root):
    entries=[];bases={}
    for cell in root.findall('s:sheetData/s:row/s:c',NS):
        formula=cell.find('s:f',NS)
        if formula is not None and formula.attrib.get('t')=='shared':
            entries.append((cell.attrib['r'],formula))
            if formula.text:bases[formula.attrib['si']]=(cell.attrib['r'],formula.text)
    for address,formula in entries:
        if not formula.text and formula.attrib.get('si') in bases:
            origin,expression=bases[formula.attrib['si']]
            formula.text=Translator('='+expression,origin=origin).translate_formula(address)[1:]
        if formula.text:
            for key in ('t','si','ref'):formula.attrib.pop(key,None)


def refresh_formula_caches(root):
    cells={cell.attrib['r']:cell for cell in root.findall('s:sheetData/s:row/s:c',NS)}
    shared={}
    formulas={}
    for address,cell in cells.items():
        formula=cell.find('s:f',NS)
        if formula is not None and formula.text and formula.attrib.get('t')=='shared':shared[formula.attrib['si']]=(address,formula.text)
    for address,cell in cells.items():
        formula=cell.find('s:f',NS)
        if formula is not None:
            expression=formula.text or ''
            if not expression and formula.attrib.get('t')=='shared' and formula.attrib.get('si') in shared:
                origin,base=shared[formula.attrib['si']];expression=Translator('='+base,origin=origin).translate_formula(address)[1:]
            formulas[address]=expression
    memo={};visiting=set()
    def expand_sum(match):
        terms=[]
        for part in match.group(1).split(','):
            if ':' not in part:terms.append(part);continue
            a,b,c,d=range_boundaries(part.replace('$',''))
            if (c-a+1)*(d-b+1)>10000:raise ValueError('range too large')
            terms.extend(f'{get_column_letter(col)}{row}' for col in range(a,c+1) for row in range(b,d+1))
        return '('+'+'.join(terms)+')'
    def value(address):
        if address in memo:return memo[address]
        if address in visiting:raise ValueError('cycle')
        visiting.add(address)
        try:
            if address not in formulas:
                cell=cells.get(address)
                if cell is None:result=D(0)  # Excel's actual blank-cell arithmetic.
                elif cell.attrib.get('t','n') not in ('n','b'):raise ValueError('not numeric')
                else:
                    node=cell.find('s:v',NS)
                    if node is None or node.text is None:raise ValueError('missing cache')
                    result=D(node.text)
            else:
                expression=re.sub(r'SUM\(([^()]+)\)',expand_sum,formulas[address],flags=re.I)
                names=set(re.findall(r'\b[A-Z]+\d+\b',expression.replace('$','')))
                result=arithmetic(expression,{name:value(name) for name in names})
            memo[address]=result;return result
        finally:visiting.discard(address)
    for address in formulas:
        cell=cells[address];cached=cell.find('s:v',NS)
        try:
            result=value(address)
            if not result.is_finite():raise ValueError('non finite')
            if cached is None:cached=ET.SubElement(cell,TAG+'v')
            cached.text=str(result);cell.attrib.pop('t',None)
        except (ValueError,ArithmeticError,SyntaxError,KeyError,RecursionError):
            if cached is not None:cell.remove(cached)
            cell.attrib.pop('t',None)


def history_patches(db,factory,source):
    patches={}
    query=select(m.SprayHistoryLink,m.SprayImportRow,m.SprayHistoryFact).join(m.SprayImportRow,m.SprayHistoryLink.import_row_id==m.SprayImportRow.id).join(m.SprayHistoryFact,m.SprayHistoryLink.fact_id==m.SprayHistoryFact.id).where(m.SprayImportRow.import_id==source.id,m.SprayHistoryLink.status=="active",m.SprayHistoryFact.status=="active")
    for link,row,fact in db.execute(query):
        for field,evidence in link.snapshot.get("evidence",{}).items():
            if evidence.get("cell") and fact.values.get(field)!=link.snapshot["values"].get(field):
                patches[(row.sheet,evidence["cell"])]=(fact.values.get(field,""),field in NUMBERS)
    return patches


def patch_workbook(source,patches):
    if not patches:return source.content
    if source.format=="PDF":s.fail("扫描 PDF 原件可下载；填报输出请选择已数字化的 Excel 模板")
    if source.format=="BIFF":
        import xlrd
        import xlwt
        from xlutils.copy import copy
        book=xlrd.open_workbook(file_contents=source.content,formatting_info=True)
        from openpyxl.styles.numbers import BUILTIN_FORMATS
        for code,format in book.format_map.items():
            if format.format_str is None:
                format.format_str=BUILTIN_FORMATS.get(code,"General")
        output=copy(book)
        # copy() preserves original cell style indexes in the destination workbook.
        for (name,address),(value,numeric) in patches.items():
            if name not in book.sheet_names():s.fail("模板表页不存在")
            col,ri=re.fullmatch(r"([A-Z]+)([1-9]\d*)",address).groups()
            ci=0
            for char in col:ci=ci*26+ord(char)-64
            ri=int(ri)-1;ci-=1
            source_sheet=book.sheet_by_name(name);target=output.get_sheet(book.sheet_names().index(name))
            # Existing style object is retained when assigning the new cell value.
            original=target.row(ri)._Row__cells.get(ci)
            style_index=original.xf_idx if original else None
            target.write(ri,ci,float(D(str(value))) if numeric and value!="" else str(value))
            if style_index is not None:target.row(ri)._Row__cells[ci].xf_idx=style_index
        stream=BytesIO();output.save(stream);return stream.getvalue()
    archive=ZipFile(BytesIO(source.content))
    workbook=ET.fromstring(archive.read("xl/workbook.xml"))
    rels={v.attrib["Id"]:v.attrib["Target"] for v in ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))}
    paths={sheet.attrib["name"]:rels[sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]] for sheet in workbook.findall("s:sheets/s:sheet",NS)}
    changed={}
    for name in {key[0] for key in patches}:
        if name not in paths:s.fail("模板表页不存在")
        target=paths[name];path=target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
        root=ET.fromstring(archive.read(path));data=root.find("s:sheetData",NS)
        if data is None:s.fail("模板缺少可写表格区域")
        expand_shared_formulas(root)
        for (sheet,address),(value,numeric) in patches.items():
            if sheet!=name:continue
            match=re.fullmatch(r"([A-Z]+)([1-9]\d*)",address)
            if not match:s.fail("模板目标单元格无效")
            ri=int(match[2]);row=data.find(f"s:row[@r='{ri}']",NS)
            if row is None:row=ET.SubElement(data,TAG+'row',{'r':str(ri)})
            cell=row.find(f"s:c[@r='{address}']",NS)
            if cell is None:cell=ET.SubElement(row,TAG+'c',{'r':address})
            for child in list(cell):cell.remove(child)
            if numeric and value!="":
                cell.attrib['t']='n';ET.SubElement(cell,TAG+'v').text=str(D(str(value)))
            else:
                cell.attrib['t']='inlineStr';ET.SubElement(ET.SubElement(cell,TAG+'is'),TAG+'t').text=str(value)
        # Preserve drawings, print definitions, merges and all untouched package members.
        if any(numeric for (sheet,_),(_,numeric) in patches.items() if sheet==name):refresh_formula_caches(root)
        changed[path]=ET.tostring(root,encoding='utf-8',xml_declaration=True)
    calc=workbook.find('s:calcPr',NS)
    if calc is None:calc=ET.SubElement(workbook,TAG+'calcPr')
    calc.attrib.update(fullCalcOnLoad='1',forceFullCalc='1',calcMode='auto')
    changed['xl/workbook.xml']=ET.tostring(workbook,encoding='utf-8',xml_declaration=True)
    stream=BytesIO()
    with ZipFile(stream,'w') as output:
        for item in archive.infolist():output.writestr(item,changed.get(item.filename,archive.read(item.filename)))
    return stream.getvalue()


def render(db,factory,source,p):
    collections={"order":m.SprayOrder,"order_line":m.SprayOrderLine,"shipment":m.SprayShipment,"shipment_line":m.SprayShipmentLine,"settlement":m.SpraySettlement,"payroll":m.SprayPayroll,"report_line":m.SprayReportLine,"purchase":m.SprayPurchase,"material_event":m.SprayMaterialEvent,"returnable":m.SprayReturnable}
    bindings=s.rows(p.get('bindings'))
    patches={}
    for binding in bindings:
        cls=collections.get(binding.get('kind'))
        if cls is None:s.fail('模板业务来源类型无效')
        item=s.find(db,cls,factory,binding.get('record_id'))
        values=s.serial(item)
        field=binding.get('field')
        if field not in values or isinstance(values[field],(dict,list)):s.fail('请选择可导出的业务字段')
        value=values[field]
        numeric=field in NUMBERS or field in ('good','regular_qty','overtime_qty','cost')
        key=(s.text(binding.get('sheet'),'模板表页',128),s.text(binding.get('cell'),'模板单元格',12).upper())
        if key in patches:s.fail('同一模板单元格不能绑定两项业务')
        patches[key]=(value if value is not None else '',numeric)
    return patch_workbook(source,patches)
