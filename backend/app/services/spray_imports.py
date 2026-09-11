"""Sparse, non-executing workbook inspection. Imports default to historical evidence."""
from io import BytesIO
from hashlib import sha256
import re
from decimal import Decimal
import posixpath
from zipfile import ZipFile, BadZipFile
from xml.etree import ElementTree as ET

from openpyxl.formula.translate import Translator
from openpyxl.styles.numbers import BUILTIN_FORMATS, is_date_format
from openpyxl.utils.datetime import from_excel, CALENDAR_MAC_1904, CALENDAR_WINDOWS_1900
from sqlalchemy import select
from app.models import spray_production as m
from app.services.spray_production import add, fail, find, serial, text

NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
MAX_BYTES = 20 * 1024 * 1024


def identifier_display(value, number_format):
    """Retain identifier zero padding without guessing accounting/date formats."""
    if not re.fullmatch(r'0{2,}', number_format or ''):return None
    try:
        number=Decimal(str(value))
        if number.is_finite() and number>=0 and number==number.to_integral_value():return str(int(number)).zfill(len(number_format))
    except ArithmeticError:pass
    return None


def parse_source(content):
    if len(content) > MAX_BYTES:
        fail("单文件最大 20 MB")
    if content.startswith(b"%PDF"):
        return "PDF", [{"sheet": "原始扫描凭证", "row_number": 1, "cells": {"A1": {"raw_value": "扫描文件，须人工数字化后确认；没有自动产生业务数量"}}, "role": "document"}]
    if content.startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
        import xlrd
        workbook = xlrd.open_workbook(file_contents=content, on_demand=True, formatting_info=True)
        result = []
        for sheet in workbook.sheets():
            if sheet.nrows * max(sheet.ncols, 1) > 2000000:
                fail("BIFF 表页过大，请先拆分来源")
            for ri in range(sheet.nrows):
                cells = {}
                for ci in range(sheet.ncols):
                    cell = sheet.cell(ri, ci)
                    if cell.ctype == xlrd.XL_CELL_EMPTY:
                        continue
                    address = xlrd.formula.colname(ci) + str(ri + 1)
                    value = cell.value
                    cells[address] = {"raw_value": value, "cached_value": value, "formula_type": "biff_cache_only",
                                      "validation_status": "cached_error" if cell.ctype == xlrd.XL_CELL_ERROR else "unverified_formula"}
                    xf=workbook.xf_list[sheet.cell_xf_index(ri,ci)]
                    fmt=workbook.format_map.get(xf.format_key)
                    display=identifier_display(value,fmt.format_str if fmt else '')
                    if display is not None:cells[address]['display_value']=display
                    if cell.ctype == xlrd.XL_CELL_DATE:
                        cells[address]["normalized_value"] = xlrd.xldate_as_datetime(value, workbook.datemode).isoformat()
                if cells:
                    result.append({"sheet": sheet.name, "row_number": ri + 1, "cells": cells, "role": "historical_review"})
        workbook.release_resources()
        return "BIFF", result
    if not content.startswith(b"PK"):
        fail("仅支持 OOXML、原生 BIFF Excel/ET 和 PDF；文件签名不匹配")
    try:
        archive = ZipFile(BytesIO(content))
        if len(archive.infolist()) > 3000 or sum(i.file_size for i in archive.infolist()) > 150 * 1024 * 1024:
            fail("压缩内容超过解析限制")
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            strings = ["".join(n.itertext()) for n in ET.fromstring(archive.read("xl/sharedStrings.xml"))]
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        properties = workbook.find('s:workbookPr', NS)
        date1904 = properties is not None and properties.attrib.get('date1904') in ('1', 'true')
        epoch = CALENDAR_MAC_1904 if date1904 else CALENDAR_WINDOWS_1900
        date_styles = set(); style_formats={}
        if 'xl/styles.xml' in archive.namelist():
            styles = ET.fromstring(archive.read('xl/styles.xml'))
            formats = {**BUILTIN_FORMATS, **{int(v.attrib['numFmtId']): v.attrib['formatCode'] for v in styles.findall('s:numFmts/s:numFmt', NS)}}
            date_styles = {str(i) for i, v in enumerate(styles.findall('s:cellXfs/s:xf', NS)) if is_date_format(formats.get(int(v.attrib.get('numFmtId', '0')), 'General'))}
            style_formats={str(i):formats.get(int(v.attrib.get('numFmtId','0')),'General') for i,v in enumerate(styles.findall('s:cellXfs/s:xf',NS))}
        relations = {r.attrib["Id"]: r.attrib["Target"] for r in ET.fromstring(archive.read("xl/_rels/workbook.xml.rels")) if r.attrib.get("TargetMode") != "External"}
        result = []
        for sheet in workbook.findall("s:sheets/s:sheet", NS):
            target = relations[sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]]
            path = target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/" + target)
            if not path.startswith("xl/"):
                fail("工作簿包含无效表页引用")
            root = ET.fromstring(archive.read(path))
            merged = [node.attrib['ref'] for node in root.findall('s:mergeCells/s:mergeCell', NS)]
            result.append({'sheet': sheet.attrib['name'], 'row_number': 0, 'role': 'sheet_metadata', 'cells': {'表页说明': {'raw_value': '隐藏' if sheet.attrib.get('state') in ('hidden','veryHidden') else '可见', 'date_system': '1904' if date1904 else '1900', 'merged_ranges': merged}}})
            shared = {}
            for row in root.findall("s:sheetData/s:row", NS):
                cells = {}
                for cell in row.findall("s:c", NS):
                    address = cell.attrib["r"]
                    value_node, formula = cell.find("s:v", NS), cell.find("s:f", NS)
                    value = value_node.text if value_node is not None else None
                    kind = cell.attrib.get("t", "n")
                    if kind == "s" and value is not None:
                        value = strings[int(value)]
                    elif kind == "inlineStr":
                        value = "".join(cell.find("s:is", NS).itertext())
                    if value is None and formula is None:
                        continue
                    entry = {"raw_value": value, "cached_value": value, "cell_type": kind, "style_id": cell.attrib.get("s"), "validation_status": "cached_error" if kind == "e" else "review"}
                    if kind=='n':
                        display=identifier_display(value,style_formats.get(cell.attrib.get('s'),''))
                        if display is not None:entry['display_value']=display
                    if kind == 'n' and cell.attrib.get('s') in date_styles and value is not None:
                        try:
                            entry['normalized_value'] = from_excel(float(value), epoch).isoformat()
                        except (ValueError, OverflowError):
                            entry['validation_status'] = 'invalid_date'
                    if formula is not None:
                        source_formula = formula.text or ""
                        entry["formula_type"] = formula.attrib.get("t", "normal")
                        if entry["formula_type"] == "shared":
                            si = formula.attrib["si"]
                            if source_formula:
                                shared[si] = (address, source_formula)
                            elif si in shared:
                                origin, base = shared[si]
                                source_formula = Translator("=" + base, origin=origin).translate_formula(address)[1:]
                                entry["shared_formula_base"] = origin
                        entry["raw_formula"] = source_formula
                        if value is None:
                            entry["validation_status"] = "missing_cache"
                    cells[address] = entry
                if cells:
                    name = sheet.attrib["name"]
                    role = "comparison" if any(k in name for k in ("汇总", "预算", "总表", "请款", "Sheet2")) else "historical_review"
                    result.append({"sheet": name, "row_number": int(row.attrib["r"]), "cells": cells, "role": role})
                    if len(result) > 50000:
                        fail("来源超过 50,000 个非空行，请拆分文件")
        return "OOXML", result
    except (BadZipFile, ET.ParseError, KeyError, IndexError, ValueError) as error:
        fail(f"工作簿结构无法识别：{type(error).__name__}；请核对原文件")


def store_source(db, factory, actor, filename, content):
    digest = sha256(content).hexdigest()
    old = db.scalar(select(m.SprayImport).where(m.SprayImport.factory_id == factory, m.SprayImport.sha256 == digest))
    if old:
        return {"id": old.id, "reused": True, "sha256": digest}
    format_name, source_rows = parse_source(content)
    item = add(db, m.SprayImport, factory, actor, filename=text(filename, "原文件名"), sha256=digest, content=content, format=format_name)
    for value in source_rows:
        add(db, m.SprayImportRow, factory, actor, import_id=item.id, **value)
    return {"id": item.id, "sha256": digest, "rows": len(source_rows), "format": format_name}


def apply_source(db, factory, actor, p):
    item = find(db, m.SprayImport, factory, p.get("import_id"))
    if item.status == "archived":
        return {"id": item.id, "added": 0, "linked": 1}
    if p.get("mode") != "historical_evidence":
        fail("当前导入只接受历史证据归档；现存库存必须由实收或确认期初建立")
    item.mapping = {"factory": factory, "reason": text(p.get("reason"), "归属确认依据", 2000), "mode": "historical_evidence"}
    item.status = "archived"
    return {"id": item.id, "added": 0, "linked": 1, "stock_effect": 0, "pending": "业务事件映射仍需逐行确认"}
