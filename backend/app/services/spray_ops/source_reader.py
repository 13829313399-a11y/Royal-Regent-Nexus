"""Bounded, signature-based source extraction. Never evaluates workbook formulas."""
from datetime import date, datetime
from io import BytesIO
import hashlib
import re
import zipfile
from xml.etree import ElementTree as ET

from .common import require, DomainError

MAX_FILE = 20 * 1024 * 1024
MAX_EXPANDED = 64 * 1024 * 1024
MAX_CELLS = 250_000
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

# Profiles describe distinct fact categories. Overlapping files cannot silently
# produce the same fact twice, and historical summary sheets never create output.
PROFILES = {
    "spray-intake-v1": dict(label="接单订单", sources=["S03"], targets=["demand"], payroll=False),
    "spray-plan-followup-v1": dict(label="计划与实绩跟进", sources=["S04"], targets=["reference"], payroll=False),
    "spray-part-tracking-v1": dict(label="胶件跟踪与期初", sources=["S05"], targets=["batch", "delivery", "opening", "reference"], payroll=False),
    "spray-legacy-inbound-v1": dict(label="历史生产入库矩阵", sources=["S06"], targets=["opening", "reference"], payroll=False),
    "spray-intercompany-v1": dict(label="兄弟厂月结与退货", sources=["S07"], targets=["delivery", "return", "container", "reference"], payroll=False),
    "spray-internal-settlement-v1": dict(label="内部交收与请款", sources=["S08"], targets=["delivery", "container", "settlement", "reference"], payroll=False),
    "spray-daily-payroll-v1": dict(label="生产日报与工资来源", sources=["S09"], targets=["report", "reference"], payroll=True),
    "spray-operating-reference-v1": dict(label="历史经营汇总", sources=["S09"], targets=["expense", "reference"], payroll=True),
    "spray-purchase-v1": dict(label="油漆采购", sources=["S10"], targets=["purchase"], payroll=False),
    "spray-material-receipt-v1": dict(label="材料到货匹配", sources=["S11"], targets=["material_receipt"], payroll=False),
    "spray-purchase-saving-v1": dict(label="采购减价分析", sources=["S12"], targets=["saving"], payroll=False),
    "spray-paper-daily-v1": dict(label="纸质日报人工复核", sources=["S02"], targets=["report", "reference"], payroll=True),
}


def cell_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, (int, float)):
        return str(value)
    return value


def read_source(payload):
    require(0 < len(payload) <= MAX_FILE, "file_size", "文件须为 1 字节至 20 MB", 413)
    sha = hashlib.sha256(payload).hexdigest()
    if payload.startswith(b"%PDF-"):
        from pypdf import PdfReader
        try:
            reader = PdfReader(BytesIO(payload))
            require(not reader.is_encrypted and len(reader.pages) <= 50, "pdf_limit", "仅支持未加密且不超过 50 页的扫描表单", 422)
            return dict(sha256=sha, format="PDF", pages=len(reader.pages), sheets=[], warnings=[dict(code="manual_review_required", message="扫描原件须逐页人工复核，不能自动生成正式报工")])
        except DomainError:
            raise
        except Exception as error:
            raise DomainError("invalid_pdf", "无法读取 PDF 原件", 422) from error
    if payload.startswith(b"PK\x03\x04"):
        return dict(sha256=sha, format="OOXML", **read_ooxml(payload))
    if payload.startswith(bytes.fromhex("d0cf11e0a1b11ae1")):
        return dict(sha256=sha, format="BIFF8", **read_biff(payload))
    raise DomainError("unsupported_signature", "文件内容不是 OOXML、BIFF 工作簿或 PDF", 422)


def read_ooxml(payload):
    import openpyxl
    try:
        with zipfile.ZipFile(BytesIO(payload)) as archive:
            infos = archive.infolist()
            require(len(infos) <= 2000 and sum(info.file_size for info in infos) <= MAX_EXPANDED, "archive_limit", "工作簿解压规模超出限制", 413)
            require(all(not info.flag_bits & 1 for info in infos), "encrypted_workbook", "不支持加密工作簿", 422)
            names = {info.filename for info in infos}
            require("xl/workbook.xml" in names and not any("vbaproject" in name.lower() for name in names), "workbook_content", "只接受不含宏的工作簿", 422)
            has_external_links = any(name.startswith("xl/externalLinks/") for name in names)
            raw_sheets, count = {}, 0
            for name in names:
                if not re.fullmatch(r"xl/worksheets/[^/]+\.xml", name):
                    continue
                cells = {}
                with archive.open(name) as stream:
                    for _, element in ET.iterparse(stream, events=("end",)):
                        if element.tag != "{" + NS["s"] + "}c":
                            continue
                        count += 1
                        require(count <= MAX_CELLS, "cell_limit", "实际单元格数量超过限制", 413)
                        value, formula = element.find("s:v", NS), element.find("s:f", NS)
                        inline = element.find("s:is", NS)
                        if value is not None or formula is not None or inline is not None:
                            coordinate = element.attrib.get("r", "")
                            require(re.fullmatch(r"[A-Z]{1,3}[1-9]\d{0,6}", coordinate), "cell_coordinate", "单元格坐标无效", 422)
                            cells[coordinate] = dict(raw_value=value.text if value is not None else None, formula_xml=formula.text if formula is not None else None, formula_attributes=formula.attrib.copy() if formula is not None else {}, raw_type=element.attrib.get("t", "n"))
                        element.clear()
                raw_sheets[name] = cells
            # Build explicit relationship mapping; worksheets are not necessarily
            # numbered in display order and hidden/reserved sheets are retained.
            rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            targets = {}
            for rel in rels:
                target = rel.attrib["Target"]
                targets[rel.attrib["Id"]] = target.lstrip("/") if target.startswith("/") else "xl/" + target
            workbook_xml = ET.fromstring(archive.read("xl/workbook.xml"))
            mapping = {sheet.attrib["name"]: targets[sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]] for sheet in workbook_xml.find("s:sheets", NS)}
        book = openpyxl.load_workbook(BytesIO(payload), data_only=False, keep_links=False)
        cached = openpyxl.load_workbook(BytesIO(payload), data_only=True, keep_links=False)
        sheets = []
        warnings = [dict(code="external_links_not_resolved", message="保留外部引用公式和现有缓存；未访问外部文件或网络")] if has_external_links else []
        for sheet in book:
            extracted = []
            raw_cells = raw_sheets.get(mapping[sheet.title], {})
            for coordinate, raw in raw_cells.items():
                cell, cache = sheet[coordinate], cached[sheet.title][coordinate]
                formula = cell.value if cell.data_type == "f" else None
                value = cache.value if formula else cell.value
                error = cache.value if cache.data_type == "e" else cell.value if cell.data_type == "e" else None
                formatted = cell_value(value)
                if isinstance(value, (int, float)) and re.fullmatch(r"0{2,20}", cell.number_format) and value == int(value):
                    formatted = str(int(value)).zfill(len(cell.number_format))
                flags = []
                if error:
                    flags.append("cached_error")
                if formula and raw["raw_value"] is None:
                    flags.append("formula_cache_missing")
                extracted.append(dict(coordinate=coordinate, row=cell.row, column=cell.column, value=cell_value(value), formatted=formatted, formula=formula, cached=cell_value(cache.value) if formula else None, error=error, number_format=cell.number_format, flags=flags, **raw))
            sheets.append(dict(name=sheet.title, state=sheet.sheet_state, cells=extracted, merges=[str(item) for item in sheet.merged_cells.ranges], dimension=sheet.calculate_dimension()))
        return dict(epoch=book.epoch.isoformat(), sheets=sheets, warnings=warnings)
    except DomainError:
        raise
    except Exception as error:
        raise DomainError("invalid_workbook", "工作簿损坏或含无法安全解析的内容", 422) from error


def read_biff(payload):
    import xlrd
    from openpyxl.utils import get_column_letter
    try:
        book = xlrd.open_workbook(file_contents=payload, formatting_info=True, on_demand=True, ragged_rows=True)
        sheets, total = [], 0
        for sheet in book.sheets():
            cells = []
            # BIFF stores actual row arrays; row_len avoids padded full dimensions.
            for row in range(sheet.nrows):
                for col in range(sheet.row_len(row)):
                    cell = sheet.cell(row, col)
                    if cell.ctype in {xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK}:
                        continue
                    total += 1
                    require(total <= MAX_CELLS, "cell_limit", "实际单元格数量超过限制", 413)
                    fmt = book.format_map[book.xf_list[cell.xf_index].format_key].format_str
                    error = xlrd.error_text_from_code.get(cell.value) if cell.ctype == xlrd.XL_CELL_ERROR else None
                    value = xlrd.xldate_as_datetime(cell.value, book.datemode).isoformat() if cell.ctype == xlrd.XL_CELL_DATE else cell_value(cell.value)
                    formatted = value
                    if cell.ctype == xlrd.XL_CELL_NUMBER and re.fullmatch(r"0{2,20}", fmt) and cell.value == int(cell.value):
                        formatted = str(int(cell.value)).zfill(len(fmt))
                    cells.append(dict(coordinate=f"{get_column_letter(col+1)}{row+1}", row=row+1, column=col+1, value=value, formatted=formatted, raw_value=cell_value(cell.value), raw_type=str(cell.ctype), number_format=fmt, formula=None, cached=None, error=error, flags=["biff_formula_unavailable"] + (["cached_error"] if error else [])))
            sheets.append(dict(name=sheet.name, state="hidden" if sheet.visibility else "visible", cells=cells, merges=[list(merge) for merge in sheet.merged_cells], dimension=None))
        book.release_resources()
        return dict(epoch="1904" if book.datemode else "1900", sheets=sheets, warnings=[dict(code="biff_formula_unavailable", message="BIFF 原始公式未还原；仅提取单元格结果与格式，不视为公式校验通过")])
    except DomainError:
        raise
    except Exception as error:
        raise DomainError("invalid_workbook", "无法读取 BIFF 工作簿", 422) from error
