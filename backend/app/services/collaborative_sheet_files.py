"""Lossless fill overlays: patch OOXML parts or BIFF8 records, never re-save a workbook.

Unchanged ZIP members / OLE streams remain byte-identical. BIFF cell tables and
their Index/DBCell pointers are rebuilt; formula and drawing records are copied.
The immutable source is always the basis of an export, never a prior export.
"""
from __future__ import annotations

import base64
from collections import defaultdict
from datetime import date, datetime, time
from decimal import Decimal, ROUND_HALF_UP, localcontext
from io import BytesIO
import math
import posixpath
import re
import struct
from zipfile import ZipFile, ZIP_DEFLATED

from lxml import etree as ET
import olefile
import openpyxl
from openpyxl.utils.cell import get_column_letter, coordinate_to_tuple, range_boundaries
from PIL import Image
import xlrd

MAX_FILE_MB = 100
MAX_FILE_BYTES = MAX_FILE_MB * 1024 * 1024
FILE_SIZE_ERROR = f"工作簿不能超过 {MAX_FILE_MB} MB"
MAX_CELLS = 100_000
MAX_ROWS = 5000
MAX_COLUMNS = 256
# OOXML permits formatting an entire column through XFD without creating any
# cells. This format boundary is separate from the bounded interactive grid.
XLSX_FORMAT_COLUMNS = 16384
MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
XML = "http://www.w3.org/XML/1998/namespace"
CELL_TYPES = {0x201, 0x203, 0x204, 0x205, 0xFD, 0x27E, 0x6, 0xBD, 0xBE, 0xD6}
FORMULA_EXTRA = {0x207, 0x3C, 0x221, 0x236, 0x4BC, 0x37}


class WorkbookError(ValueError):
    pass


def xml(data):
    return ET.fromstring(data, ET.XMLParser(resolve_entities=False, no_network=True, huge_tree=False))


def records(data):
    offset = 0
    while offset + 4 <= len(data):
        kind, size = struct.unpack_from("<HH", data, offset)
        if kind == 0 and size == 0:
            break  # OLE stream padding emitted by some producers.
        if size > 8224 or offset + 4 + size > len(data):
            raise WorkbookError("XLS 记录损坏或不支持此格式")
        yield offset, kind, data[offset + 4:offset + 4 + size]
        offset += 4 + size


def rec(kind, data):
    if len(data) > 8224:
        raise WorkbookError("单元格内容超出 XLS 记录限制")
    return struct.pack("<HH", kind, len(data)) + data


def _limits(sheets):
    if not sheets or len(sheets) > 50 or sum(s[0] * s[1] for s in sheets) > MAX_CELLS:
        raise WorkbookError("表格超过限制：最多 50 页、合计 100000 格")
    if any(r > MAX_ROWS or c > MAX_COLUMNS for r, c in sheets):
        raise WorkbookError("每页最多支持 5000 行、256 列，请缩小原表范围")


class _GridBudget:
    """Bound the *effective* grid before readers materialize implicit cells.

    Dimensions are only a producer hint. Merges, links and formulas can extend
    it, and overlapping expansion ranges can repeatedly traverse the same grid.
    """
    def __init__(self):
        self.rows = self.columns = self.work = 0
        self.occupied = defaultdict(set)

    def add(self, r1, c1, r2, c2, *, role=None, expand=False):
        if not (1 <= r1 <= r2 <= MAX_ROWS and 1 <= c1 <= c2 <= MAX_COLUMNS):
            raise WorkbookError("单元格或引用范围无效，或超出 5000 行、256 列限制")
        self.rows, self.columns = max(self.rows, r2), max(self.columns, c2)
        if self.rows * self.columns > MAX_CELLS:
            raise WorkbookError("引用范围扩展后的工作表超过 100000 格限制")
        area = (r2 - r1 + 1) * (c2 - c1 + 1)
        if expand:
            self.work += area
            if self.work > 4 * MAX_CELLS:
                raise WorkbookError("工作表累计展开范围超过处理限制")
        if role:
            occupied = self.occupied[role]
            # Extent/work checks above run before any coordinate enumeration.
            for r in range(r1, r2 + 1):
                for c in range(c1, c2 + 1):
                    point = (r - 1) * MAX_COLUMNS + c - 1
                    if point in occupied:
                        raise WorkbookError("工作表包含重复或重叠的合并、链接或数组范围")
                    occupied.add(point)

    def reference(self, value, *, single=False, role=None, expand=False):
        cell = r"\$?[A-Za-z]{1,3}\$?[1-9][0-9]{0,6}"
        if not isinstance(value, str) or not re.fullmatch(cell if single else cell + "(?::" + cell + ")?", value):
            raise WorkbookError("工作表包含无效单元格引用")
        c1, r1, c2, r2 = range_boundaries(value.upper())
        self.add(r1, c1, r2, c2, role=role, expand=expand)
        return r2, c2


def _preflight_xlsx(z, paths):
    if not 1 <= len(paths) <= 50 or len(set(paths)) != len(paths):
        raise WorkbookError("工作表数量无效或含重复工作表引用")
    dimensions, total_work = [], 0
    for path in paths:
        if z.getinfo(path).file_size > 12 * 1024 * 1024:
            raise WorkbookError("工作表 XML 超过填写视图处理限制")
        root = xml(z.read(path))
        grid = _GridBudget()
        for node in root.iter():
            if not isinstance(node.tag, str):
                continue
            if ET.QName(node).localname in {"c", "row", "col", "dimension", "mergeCell", "hyperlink", "f"} and ET.QName(node).namespace != MAIN:
                raise WorkbookError("工作表包含命名空间无效的单元格或范围声明")
        dim = root.find(f"{{{MAIN}}}dimension")
        if dim is not None:
            grid.reference(dim.get("ref"))
        row_counter = 0
        for row in root.findall(f"{{{MAIN}}}sheetData/{{{MAIN}}}row"):
            row_counter = int(row.get("r", row_counter + 1))
            if not 1 <= row_counter <= MAX_ROWS:
                raise WorkbookError("工作表行声明超出支持范围")
            column = 0
            for cell in row.findall(f"{{{MAIN}}}c"):
                if cell.get("r"):
                    _, column = grid.reference(cell.get("r"), single=True, role="cell", expand=True)
                else:
                    column += 1
                    grid.add(row_counter, column, row_counter, column, role="cell", expand=True)
                formula = cell.find(f"{{{MAIN}}}f")
                if formula is not None and formula.get("ref"):
                    grid.reference(formula.get("ref"), role="array" if formula.get("t") in {"array", "dataTable"} else None, expand=True)
        for tag, role in (("mergeCells/mergeCell", "merge"), ("hyperlinks/hyperlink", "hyperlink")):
            for node in root.findall("/".join(f"{{{MAIN}}}{part}" for part in tag.split("/"))):
                grid.reference(node.get("ref"), role=role, expand=True)
        for col in root.findall(f"{{{MAIN}}}cols/{{{MAIN}}}col"):
            # openpyxl stores one ColumnDimension per declaration; it does not
            # expand these formatting spans into cells. Only actual cell and
            # allocation-driving ranges above contribute to the grid budget.
            if not 1 <= int(col.get("min", 0)) <= int(col.get("max", 0)) <= XLSX_FORMAT_COLUMNS:
                raise WorkbookError("工作表列格式声明无效或超出 XLSX 格式范围")
        # Comments are loaded from related parts and attached using ws[ref].
        # A malicious comment range would therefore allocate cells as well.
        rel_path = posixpath.join(posixpath.dirname(path), "_rels", posixpath.basename(path) + ".rels")
        if rel_path in z.namelist():
            for rel in _relationships(z.read(rel_path)):
                if (rel.get("Type") or "").endswith("/comments"):
                    if rel.get("TargetMode") == "External":
                        raise WorkbookError("不支持外部批注引用")
                    target = rel.get("Target", "")
                    target = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join(posixpath.dirname(path), target))
                    if z.getinfo(target).file_size > 12 * 1024 * 1024:
                        raise WorkbookError("批注数据超过处理限制")
                    for comment in xml(z.read(target)).iter():
                        if isinstance(comment.tag, str) and ET.QName(comment).localname == "comment":
                            grid.reference(comment.get("ref"), single=True, role="comment", expand=True)
        dimensions.append((grid.rows, grid.columns))
        total_work += grid.work
        if total_work > 4 * MAX_CELLS:
            raise WorkbookError("工作簿累计展开范围超过处理限制")
        _limits(dimensions)


def _preflight_xls(stream, bounds):
    if not 1 <= len(bounds) <= 50 or len({b[1] for b in bounds}) != len(bounds):
        raise WorkbookError("XLS 工作表数量或位置无效")
    dimensions, total_work = [], 0
    for _, start, _ in bounds:
        if not 0 < start < len(stream):
            raise WorkbookError("XLS 工作表位置无效")
        end = min([b[1] for b in bounds if b[1] > start] + [len(stream)])
        grid = _GridBudget()
        for position, kind, value in records(stream[start:end]):
            if position == 0 and (kind != 0x809 or struct.unpack_from("<H", value)[0] != 0x600):
                raise WorkbookError("工作表不是标准 BIFF8 子流")
            if kind in {0x9, 0x209, 0x409, 0x206, 0x406}:
                raise WorkbookError("BIFF8 工作表包含不支持的旧格式记录")
            if kind == 0x809 and struct.unpack_from("<H", value, 2)[0] != 0x10:
                raise WorkbookError("暂不支持嵌入式图表或非标准 XLS 子流，请使用 XLSX")
            if kind == 0x200:
                r1, r2, c1, c2 = struct.unpack_from("<IIHH", value)
                if r2 or c2:
                    grid.add(r1 + 1, c1 + 1, r2, c2)
            elif kind in CELL_TYPES:
                r, c = struct.unpack_from("<HH", value)
                last = struct.unpack_from("<H", value, len(value) - 2)[0] if kind in {0xBD, 0xBE} else c
                grid.add(r + 1, c + 1, r + 1, last + 1, role="cell", expand=True)
            elif kind == 0xE5:  # MERGEDCELLS, inclusive zero-based ranges.
                count = struct.unpack_from("<H", value)[0]
                if len(value) != 2 + 8 * count:
                    raise WorkbookError("XLS 合并范围记录无效")
                for offset in range(2, len(value), 8):
                    r1, r2, c1, c2 = struct.unpack_from("<HHHH", value, offset)
                    grid.add(r1 + 1, c1 + 1, r2 + 1, c2 + 1, role="merge", expand=True)
            elif kind == 0x1B8:  # HLINK creates a per-cell hyperlink map in xlrd.
                r1, r2, c1, c2 = struct.unpack_from("<HHHH", value)
                grid.add(r1 + 1, c1 + 1, r2 + 1, c2 + 1, role="hyperlink", expand=True)
            elif kind in {0x221, 0x236}:  # ARRAY / TABLE generated result ranges.
                r1, r2, c1, c2 = struct.unpack_from("<HHBB", value)
                grid.add(r1 + 1, c1 + 1, r2 + 1, c2 + 1, role="array", expand=True)
            elif kind == 0x208 and struct.unpack_from("<H", value)[0] >= MAX_ROWS:
                raise WorkbookError("XLS 行声明超出支持范围")
        dimensions.append((grid.rows, grid.columns))
        total_work += grid.work
        if total_work > 4 * MAX_CELLS:
            raise WorkbookError("工作簿累计展开范围超过处理限制")
        _limits(dimensions)


def _zip(data):
    archive = ZipFile(BytesIO(data))
    entries = archive.infolist()
    if len(entries) > 5000 or sum(x.file_size for x in entries) > 160 * 1024 * 1024:
        raise WorkbookError("压缩工作簿解压后超过限制")
    if len({i.filename for i in entries}) != len(entries):
        raise WorkbookError("工作簿含重复文件项")
    if any(i.flag_bits & 1 for i in entries):
        raise WorkbookError("暂不支持加密工作簿")
    return archive


def _relationships(data):
    result = [node for node in xml(data) if isinstance(node.tag, str)]
    identities = [node.get("Id") for node in result]
    if not all(identities) or len(identities) != len(set(identities)):
        raise WorkbookError("工作簿包含缺失或重复的关系标识")
    return result


def _sheet_paths(z):
    root = xml(z.read("xl/workbook.xml"))
    relationships = {e.get("Id"): e.get("Target") for e in _relationships(z.read("xl/_rels/workbook.xml.rels"))}
    result = []
    for node in root.findall(f"{{{MAIN}}}sheets/{{{MAIN}}}sheet"):
        target = relationships[node.get(f"{{{REL}}}id")]
        path = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join("xl", target))
        if not path.startswith("xl/worksheets/"):
            raise WorkbookError("暂不支持宏表或图表工作表")
        result.append(path)
    return result


def _thumb(data):
    try:
        with Image.open(BytesIO(data)) as img:
            if img.width * img.height > 25_000_000:
                return None
            img.thumbnail((360, 240))
            out = BytesIO()
            img.convert("RGB").save(out, "JPEG", quality=78)
            return "data:image/jpeg;base64," + base64.b64encode(out.getvalue()).decode()
    except (OSError, ValueError, Image.DecompressionBombError):
        return None


def _wps_images(data):
    """WPS stores DISPIMG assets in an independent ZIP; keep it intact on export."""
    result = {}
    with _zip(data) as z:
        image_file = next((n for n in z.namelist() if n.lower() == "xl/cellimages.xml"), None)
        if not image_file:
            return result
        rel_file = "xl/_rels/" + posixpath.basename(image_file) + ".rels"
        rels = {e.get("Id"): e.get("Target") for e in xml(z.read(rel_file)) if e.get("TargetMode") != "External"}
        for picture in xml(z.read(image_file)):
            names = picture.xpath(".//*[local-name()='cNvPr']/@name")
            ids = picture.xpath(".//*[local-name()='blip']/@r:embed", namespaces={"r": REL})
            if names and ids and ids[0] in rels:
                target = posixpath.normpath(posixpath.join("xl", rels[ids[0]]))
                if target in z.namelist():
                    value = _thumb(z.read(target))
                    if value:
                        result[names[0]] = value
    return result


def _display(value, number_format="General", date_mode=0):
    """Conservative display formatting only; never round the stored scalar.

    Handle ordinary decimal/grouped/percent/date masks. Complex conditional,
    accounting, fraction and locale-specific masks retain a general display.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if not isinstance(value, (int, float, date, datetime, time)):
        return str(value)
    numeric = isinstance(value, (int, float))
    sections = (number_format or "General").split(";")
    negative = numeric and value < 0
    section = sections[1] if negative and len(sections) > 1 else sections[2] if numeric and value == 0 and len(sections) > 2 else sections[0]
    section = re.sub(r"\[(?:Black|Blue|Cyan|Green|Magenta|Red|White|Yellow)\]", "", section, flags=re.I).strip()
    # Simple date/time masks; 'm' after the hour token denotes minutes.
    date_mask = section.lower()
    if re.fullmatch(r"(?:yyyy|yy|mm|m|dd|d|hh|h|ss|s|[-/ :年月日时分秒])+", date_mask) and any(t in date_mask for t in ("y", "d", "h", "s")):
        try:
            current = xlrd.xldate_as_datetime(value, date_mode) if numeric else value
            time_part = False
            def component(match):
                nonlocal time_part
                token = match.group()
                if token[0] == "h":
                    time_part = True
                if token[0] == "y":
                    result = current.year if len(token) == 4 else current.year % 100
                elif token[0] == "m":
                    result = current.minute if time_part or isinstance(current, time) else current.month
                else:
                    result = getattr(current, {"d": "day", "h": "hour", "s": "second"}[token[0]])
                return str(result).zfill(len(token))
            return re.sub(r"yyyy|yy|mm|m|dd|d|hh|h|ss|s", component, date_mask)
        except (ValueError, OverflowError, AttributeError):
            pass
    if numeric:
        mask = re.fullmatch(r"([+\-($¥￥]?)(#,##0|0+|#0)(?:\.([0#]{1,12}))?(%)?(\))?", section)
        if mask and (mask[1] != "(" or mask[5] == ")"):
            prefix, integer, decimals, percent, suffix = mask.groups()
            places = len(decimals or "")
            magnitude = Decimal(str(abs(value) if negative and len(sections) > 1 else value))
            magnitude = magnitude * 100 if percent else magnitude
            with localcontext() as context:
                context.prec = max(40, magnitude.adjusted() + places + 3)
                magnitude = magnitude.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
                rendered = format(magnitude, ("," if "," in integer else "") + f".{places}f")
            if decimals and decimals.endswith("#"):
                required = len(decimals.rstrip("#"))
                whole, fraction = rendered.split(".")
                fraction = fraction.rstrip("0").ljust(required, "0")
                rendered = whole + ("." + fraction if fraction else "")
            if integer.count("0") > 1 and "," not in integer:
                sign = "-" if rendered.startswith("-") else ""
                rendered = sign + rendered.lstrip("-").zfill(integer.count("0") + (places + 1 if places else 0))
            return (prefix or "") + rendered + (percent or "") + (suffix or "")
        # Excel stores about 15 significant decimal digits. Avoid exposing
        # binary float noise in General/unsupported formats in the browser.
        return format(value, ".15g") if isinstance(value, float) else str(value)
    return value.isoformat()


def _color(value):
    if value is not None and value.type == "rgb" and isinstance(value.rgb, str):
        return "#" + value.rgb[-6:]
    return None


def inspect_xlsx(data):
    with _zip(data) as z:
        if any("vbaproject" in n.lower() or n.startswith("_xmlsignatures/") for n in z.namelist()):
            raise WorkbookError("暂不支持含宏或数字签名的工作簿")
        paths = _sheet_paths(z)
        _preflight_xlsx(z, paths)
        wps = _wps_images(data) if any(n.lower() == "xl/cellimages.xml" for n in z.namelist()) else {}
    book = openpyxl.load_workbook(BytesIO(data), data_only=False, keep_links=True)
    cached = openpyxl.load_workbook(BytesIO(data), data_only=True, keep_links=True)
    _limits([(s.max_row, s.max_column) for s in book])
    sheets = []
    for index, sheet in enumerate(book):
        if sheet.protection.sheet:
            raise WorkbookError("请先在原表解除工作表保护后上传")
        locked_formula_cells = set()
        for row in sheet:
            for c in row:
                if c.data_type == "f" and hasattr(c.value, "ref"):
                    c1, r1, c2, r2 = range_boundaries(c.value.ref)
                    if r2 > sheet.max_row or c2 > sheet.max_column:
                        raise WorkbookError("数组公式范围超出原表数据区，请先在 Excel / WPS 整理")
                    locked_formula_cells.update((r, c) for r in range(r1, r2 + 1) for c in range(c1, c2 + 1))
        cells = []
        for row in sheet:
            for c in row:
                if isinstance(c, openpyxl.cell.cell.MergedCell):
                    continue
                if c.value is None and not c.has_style and (c.row, c.column) not in locked_formula_cells:
                    continue
                formula = c.data_type == "f" or (c.row, c.column) in locked_formula_cells
                value = cached[sheet.title][c.coordinate].value if formula else c.value
                display = _display(value, c.number_format, int(book.epoch.year == 1904))
                if value is not None and not isinstance(value, (str, bool, int, float)):
                    value = value.isoformat() if hasattr(value, "isoformat") else str(value)
                style = {"fontFamily": c.font.name or "sans-serif", "fontSize": f"{c.font.sz or 11}pt",
                         "fontWeight": "bold" if c.font.bold else "normal", "fontStyle": "italic" if c.font.italic else "normal",
                         "textAlign": c.alignment.horizontal if c.alignment.horizontal in {"left", "center", "right", "justify"} else "left",
                         "verticalAlign": c.alignment.vertical or "middle", "whiteSpace": "pre-wrap"}
                if _color(c.font.color):
                    style["color"] = _color(c.font.color)
                if c.fill.patternType == "solid" and _color(c.fill.fgColor):
                    style["backgroundColor"] = _color(c.fill.fgColor)
                for side in ("top", "right", "bottom", "left"):
                    border = getattr(c.border, side)
                    if border and border.style:
                        style["border" + side.title()] = "1px solid " + (_color(border.color) or "#9ca3af")
                item = {"address": c.coordinate, "row": c.row - 1, "column": c.column - 1,
                        "value": value, "display": display, "number_format": c.number_format, "formula": formula, "style": style}
                if formula:
                    ids = re.findall(r"ID_[A-Fa-f0-9]{32}", str(c.value))
                    if ids and ids[0] in wps:
                        item["image"] = wps[ids[0]]
                cells.append(item)
        pictures = []
        for img in sheet._images:
            anchor = img.anchor
            if hasattr(anchor, "_from"):
                thumb = _thumb(img._data())
                if thumb:
                    pictures.append({"row": anchor._from.row, "column": anchor._from.col, "url": thumb,
                                     "width": min(img.width, 360), "height": min(img.height, 240)})
        sheets.append({"index": index, "name": sheet.title, "rows": sheet.max_row, "columns": sheet.max_column, "date_mode": int(book.epoch.year == 1904),
                       "hidden": sheet.sheet_state != "visible", "cells": cells,
                       "merges": [str(r) for r in sheet.merged_cells.ranges], "images": pictures,
                       "row_heights": {str(k - 1): (v.height or 15) * 4 / 3 for k, v in sheet.row_dimensions.items()},
                       "column_widths": {str(c - 1): max(24, (v.width or 13) * 7 + 5) for v in sheet.column_dimensions.values()
                                         for c in range(v.min or 1, min(sheet.max_column, v.max or v.min or 1) + 1)}})
    book.close()
    cached.close()
    return {"sheets": sheets, "warnings": ["浏览器显示原表内容、格式和可识别图片；打印布局及浮动对象以下载的原格式文件为准。", "公式只读；填写后公式显示值可能过期，请下载后用 Excel / WPS 重新计算。"]}


def _xls_source(data):
    o = olefile.OleFileIO(BytesIO(data))
    names = o.listdir()
    if o.sectorsize != 512 or any("vba" in "/".join(n).lower() or "digitalsignature" in "/".join(n).lower() for n in names):
        o.close()
        raise WorkbookError("只支持不含宏或数字签名的标准 BIFF8 XLS")
    name = "Workbook" if o.exists("Workbook") else "Book"
    stream = o.openstream(name).read()
    rr = list(records(stream))
    if not rr or rr[0][1] != 0x809 or struct.unpack_from("<H", rr[0][2])[0] != 0x600:
        raise WorkbookError("仅支持 BIFF8 格式 XLS，请使用 Excel / WPS 另存后上传")
    if any(t == 0x2F for _, t, _ in rr):
        raise WorkbookError("请先解除工作簿密码后上传")
    bounds = [(p, struct.unpack_from("<I", v)[0], v) for p, t, v in rr if t == 0x85]
    if any(v[5] != 0 for _, _, v in bounds):
        raise WorkbookError("暂不支持宏表或图表工作表")
    return o, name, stream, bounds


def inspect_xls(data):
    o, _, stream, bounds = _xls_source(data)
    try:
        _preflight_xls(stream, bounds)
        wps = _wps_images(o.openstream("ETCellImageData").read()) if o.exists("ETCellImageData") else {}
        book = xlrd.open_workbook(file_contents=data, formatting_info=True, on_demand=True)
        _limits([(s.nrows, s.ncols) for s in book.sheets()])
        sheets = []
        floating = False
        for index, sheet in enumerate(book.sheets()):
            start = bounds[index][1]
            end = min([b[1] for b in bounds if b[1] > start] + [len(stream)])
            formulas = {}
            array_ranges = []
            for _, t, v in records(stream[start:end]):
                if t == 0x809 and struct.unpack_from("<H", v, 2)[0] != 0x10:
                    raise WorkbookError("暂不支持嵌入式图表或非标准 XLS 子流，请使用 XLSX")
                if t == 0x12 and struct.unpack_from("<H", v)[0]:
                    raise WorkbookError("请先在原表解除工作表保护后上传")
                if t == 0x6:
                    r, c = struct.unpack_from("<HH", v)
                    ids = re.findall(r"ID_[A-Fa-f0-9]{32}", v.decode("utf-16-le", errors="ignore"))
                    if not ids:
                        ids = re.findall(r"ID_[A-Fa-f0-9]{32}", v.decode("latin-1"))
                    formulas[r, c] = ids[0] if ids else ""
                if t in {0x221, 0x236}:
                    r1, r2, c1, c2 = struct.unpack_from("<HHBB", v)
                    if r2 >= sheet.nrows or c2 >= sheet.ncols:
                        raise WorkbookError("数组公式范围超出原表数据区，请先在 Excel / WPS 整理")
                    array_ranges.append((r1, r2, c1, c2))
                if t in {0xEC, 0x7F}:
                    floating = True
            for r1, r2, c1, c2 in array_ranges:
                for r in range(r1, r2 + 1):
                    for c in range(c1, c2 + 1):
                        formulas.setdefault((r, c), "")
            cells = []
            for r in range(sheet.nrows):
                for c in range(sheet.ncols):
                    cell = sheet.cell(r, c)
                    if cell.ctype == 0 and cell.xf_index == 15 and (r, c) not in formulas:
                        continue
                    value = cell.value
                    if cell.ctype == xlrd.XL_CELL_BOOLEAN:
                        value = bool(value)
                    if cell.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
                        value = None
                    xf = book.xf_list[cell.xf_index]
                    number_format = book.format_map[xf.format_key].format_str
                    display = _display(value, number_format, book.datemode)
                    if cell.ctype == xlrd.XL_CELL_ERROR:
                        display = xlrd.error_text_from_code.get(value, "#ERROR")
                    font = book.font_list[xf.font_index]
                    color = lambda ix: ("#%02x%02x%02x" % book.colour_map[ix]) if book.colour_map.get(ix) else None
                    style = {"fontFamily": font.name, "fontSize": f"{font.height / 20:g}pt", "fontWeight": "bold" if font.bold else "normal",
                             "fontStyle": "italic" if font.italic else "normal", "whiteSpace": "pre-wrap",
                             "textAlign": {1: "left", 2: "center", 3: "right"}.get(xf.alignment.hor_align, "left"),
                             "verticalAlign": {0: "top", 1: "middle", 2: "bottom"}.get(xf.alignment.vert_align, "middle")}
                    if color(font.colour_index):
                        style["color"] = color(font.colour_index)
                    if xf.background.fill_pattern == 1 and color(xf.background.pattern_colour_index):
                        style["backgroundColor"] = color(xf.background.pattern_colour_index)
                    for side in ("top", "right", "bottom", "left"):
                        if getattr(xf.border, side + "_line_style"):
                            style["border" + side.title()] = "1px solid " + (color(getattr(xf.border, side + "_colour_index")) or "#9ca3af")
                    item = {"address": get_column_letter(c + 1) + str(r + 1), "row": r, "column": c, "value": value,
                            "display": display, "number_format": number_format, "formula": (r, c) in formulas, "style": style}
                    if formulas.get((r, c)) in wps:
                        item["image"] = wps[formulas[r, c]]
                        item["display"] = ""
                    cells.append(item)
            sheets.append({"index": index, "name": sheet.name, "rows": sheet.nrows, "columns": sheet.ncols, "date_mode": book.datemode,
                           "hidden": bool(sheet.visibility), "cells": cells, "images": [],
                           "merges": [f"{get_column_letter(c1 + 1)}{r1 + 1}:{get_column_letter(c2)}{r2}" for r1, r2, c1, c2 in sheet.merged_cells],
                           "row_heights": {str(r): x.height / 15 for r, x in sheet.rowinfo_map.items()},
                           "column_widths": {str(c): max(24, x.width / 256 * 7 + 5) for c, x in sheet.colinfo_map.items() if c < sheet.ncols}})
        warnings = ["公式只读；填写后公式显示值可能过期，请下载后用 Excel / WPS 重新计算。", "原文件的图片、公式及格式保留在同格式下载中；浏览器为填写视图，不等同打印预览。"]
        if floating:
            warnings.append("此 XLS 含浮动图形，浏览器未显示的图形仍完整保留在下载文件。")
        book.release_resources()
        return {"sheets": sheets, "warnings": warnings}
    finally:
        o.close()


def inspect_workbook(data, kind):
    if not data:
        raise WorkbookError("文件为空")
    if len(data) > MAX_FILE_BYTES:
        raise WorkbookError(FILE_SIZE_ERROR)
    try:
        return inspect_xls(data) if kind == "xls" else inspect_xlsx(data)
    except WorkbookError:
        raise
    except Exception as exc:
        raise WorkbookError("无法读取该工作簿，请确认文件未损坏且未加密") from exc


def patch_xlsx(data, overrides):
    with _zip(data) as z:
        paths = _sheet_paths(z)
        replacements = {}
        grouped = defaultdict(dict)
        for key, value in overrides.items():
            sheet, address = key.split(":", 1)
            grouped[int(sheet)][address] = value
        for index, changes in grouped.items():
            path = paths[index]
            root = xml(z.read(path))
            table = root.find(f"{{{MAIN}}}sheetData")
            if table is None:
                raise WorkbookError("工作表缺少单元格数据区")
            rows = {int(r.get("r")): r for r in table}
            for address, value in changes.items():
                r, c = coordinate_to_tuple(address)
                row = rows.get(r)
                if row is None:
                    row = ET.Element(f"{{{MAIN}}}row", r=str(r))
                    following = next((node for node in table if int(node.get("r")) > r), None)
                    if following is None:
                        table.append(row)
                    else:
                        table.insert(table.index(following), row)
                    rows[r] = row
                cell = next((node for node in row if node.get("r") == address), None)
                if cell is None:
                    cell = ET.Element(f"{{{MAIN}}}c", r=address)
                    following = next((node for node in row if coordinate_to_tuple(node.get("r"))[1] > c), None)
                    if following is None:
                        row.append(cell)
                    else:
                        row.insert(row.index(following), cell)
                if cell.find(f"{{{MAIN}}}f") is not None:
                    raise WorkbookError("原表公式不可覆盖")
                for node in list(cell):
                    if node.tag in {f"{{{MAIN}}}v", f"{{{MAIN}}}is"}:
                        cell.remove(node)
                cell.attrib.pop("t", None)
                if isinstance(value, str):
                    cell.set("t", "inlineStr")
                    text = ET.SubElement(ET.SubElement(cell, f"{{{MAIN}}}is"), f"{{{MAIN}}}t")
                    text.set(f"{{{XML}}}space", "preserve")
                    text.text = value
                elif value is not None:
                    cell.set("t", "b" if isinstance(value, bool) else "n")
                    ET.SubElement(cell, f"{{{MAIN}}}v").text = str(int(value)) if isinstance(value, bool) else str(value)
            replacements[path] = ET.tostring(root, encoding="utf-8", xml_declaration=True, standalone=True)
        root = xml(z.read("xl/workbook.xml"))
        calc = root.find(f"{{{MAIN}}}calcPr")
        if calc is None:
            calc = ET.Element(f"{{{MAIN}}}calcPr")
            # calcPr precedes these optional workbook children in ECMA-376.
            following = next((n for n in root if ET.QName(n).localname in {"oleSize", "customWorkbookViews", "pivotCaches", "smartTagPr", "smartTagTypes", "webPublishing", "fileRecoveryPr", "webPublishObjects", "extLst"}), None)
            if following is None:
                root.append(calc)
            else:
                root.insert(root.index(following), calc)
        calc.set("fullCalcOnLoad", "1")
        calc.set("forceFullCalc", "1")
        replacements["xl/workbook.xml"] = ET.tostring(root, encoding="utf-8", xml_declaration=True, standalone=True)
        out = BytesIO()
        with ZipFile(out, "w", ZIP_DEFLATED) as dest:
            for info in z.infolist():
                dest.writestr(info, replacements.get(info.filename, z.read(info.filename)))
        return out.getvalue()


def _replace_ole_stream(data, o, name, stream):
    """Append a regular stream and fresh FAT/DIFAT; retain every other stream.

    Existing mini-stream and directory trees remain untouched, except the target
    directory entry's start/size. Handles DIFAT (>6.875 MB), including WPS images.
    """
    FREE, END, FAT, DIF = 0xFFFFFFFF, 0xFFFFFFFE, 0xFFFFFFFD, 0xFFFFFFFC
    size = o.sectorsize
    output = bytearray(data)
    if len(output) % size:
        raise WorkbookError("OLE 文件扇区长度无效")
    old_count = len(output) // size - 1
    stream_size = max(4096, len(stream))
    nstream = (stream_size + size - 1) // size
    nfat = ndif = 0
    while True:
        nextfat = math.ceil((old_count + nstream + nfat + ndif) / 128)
        nextdif = max(0, math.ceil((nextfat - 109) / 127))
        if (nextfat, nextdif) == (nfat, ndif):
            break
        nfat, ndif = nextfat, nextdif
    fat_start = old_count + nstream
    dif_start = fat_start + nfat
    fat = list(o.fat[:old_count]) + [FREE] * (nfat * 128 - old_count)
    # Old allocation tables can be freed; directory and all other chains remain.
    for i in range(old_count):
        if fat[i] in (FAT, DIF):
            fat[i] = FREE
    sid = o._find(name)
    entry = o.direntries[sid]
    if entry.size >= 4096:
        sector = entry.isectStart
        seen = set()
        while sector != END:
            if sector in seen or sector >= old_count:
                raise WorkbookError("OLE 工作簿扇区链无效")
            seen.add(sector)
            following = fat[sector]
            fat[sector] = FREE
            sector = following
    for i in range(nstream):
        fat[old_count + i] = old_count + i + 1 if i + 1 < nstream else END
    for i in range(nfat):
        fat[fat_start + i] = FAT
    for i in range(ndif):
        fat[dif_start + i] = DIF
    output.extend(stream + bytes(nstream * size - len(stream)))
    output.extend(struct.pack(f"<{len(fat)}I", *fat))
    fat_ids = list(range(fat_start, fat_start + nfat))
    for i in range(ndif):
        ids = fat_ids[109 + i * 127:109 + (i + 1) * 127]
        output.extend(struct.pack("<128I", *(ids + [FREE] * (127 - len(ids)) + [dif_start + i + 1 if i + 1 < ndif else END])))
    struct.pack_into("<I", output, 44, nfat)
    struct.pack_into("<II", output, 68, dif_start if ndif else END, ndif)
    struct.pack_into("<109I", output, 76, *(fat_ids[:109] + [FREE] * max(0, 109 - nfat)))
    directory = struct.unpack_from("<I", data, 48)[0]
    for _ in range((sid * 128) // size):
        directory = o.fat[directory]
    location = (directory + 1) * size + (sid * 128) % size
    struct.pack_into("<IQ", output, location + 116, old_count, stream_size)
    return bytes(output)


def _cell_record(row, col, xf, value, string_indices):
    prefix = struct.pack("<HHH", row, col, xf)
    if value is None:
        return rec(0x201, prefix)
    if isinstance(value, bool):
        return rec(0x205, prefix + bytes([int(value), 0]))
    if isinstance(value, (int, float)):
        return rec(0x203, prefix + struct.pack("<d", float(value)))
    return rec(0xFD, prefix + struct.pack("<I", string_indices[value]))


def _rebuild_sheet(data, changes, string_indices, sheet_start, old_start):
    rr = list(records(data))
    rows, cells, consumed = {}, {}, set()
    first_table = None
    i = 0
    while i < len(rr):
        pos, kind, value = rr[i]
        if kind == 0x208:
            rows[struct.unpack_from("<H", value)[0]] = value
            consumed.add(i)
            first_table = i if first_table is None else first_table
        elif kind == 0xD7:
            consumed.add(i)
        elif kind in CELL_TYPES:
            first_table = i if first_table is None else first_table
            r, c = struct.unpack_from("<HH", value)
            group = rec(kind, value)
            consumed.add(i)
            if kind == 6:
                while i + 1 < len(rr) and rr[i + 1][1] in FORMULA_EXTRA:
                    i += 1
                    consumed.add(i)
                    group += rec(rr[i][1], rr[i][2])
            if kind in (0xBD, 0xBE):
                last = struct.unpack_from("<H", value, len(value) - 2)[0]
                stride = 6 if kind == 0xBD else 2
                if len(value) != 6 + stride * (last - c + 1):
                    raise WorkbookError("XLS 多格记录无效")
                for col in range(c, last + 1):
                    part = value[4 + (col - c) * stride:4 + (col - c + 1) * stride]
                    cells[r, col] = rec(0x27E if kind == 0xBD else 0x201, struct.pack("<HH", r, col) + part)
            else:
                cells[r, c] = group
        i += 1
    if first_table is None:
        raise WorkbookError("XLS 工作表没有可填写的数据区")
    for address, value in changes.items():
        r, c = coordinate_to_tuple(address)
        r, c = r - 1, c - 1
        previous = cells.get((r, c))
        if previous and struct.unpack_from("<H", previous)[0] == 6:
            raise WorkbookError("原表公式不可覆盖")
        xf = struct.unpack_from("<H", previous, 8)[0] if previous else 15
        cells[r, c] = _cell_record(r, c, xf, value, string_indices)
        if r not in rows:
            rows[r] = struct.pack("<8H", r, c, c + 1, 255, 0, 0, 0, 0)
    byrow = defaultdict(list)
    for (r, c), value in sorted(cells.items()):
        byrow[r].append((c, value))
    # Use original dimensions' first row for the 32-row block boundary.
    dimension = next((v for _, k, v in rr if k == 0x200), None)
    first_row = struct.unpack_from("<I", dimension)[0] if dimension else min(rows)
    blocks = defaultdict(list)
    for r in sorted(rows):
        blocks[(r - first_row) // 32].append(r)
    table, db_positions = bytearray(), []
    for block in sorted(blocks):
        row_positions, first_cells = [], []
        for r in blocks[block]:
            row_positions.append(len(table))
            value = bytearray(rows[r])
            if byrow[r]:
                struct.pack_into("<HH", value, 2, byrow[r][0][0], byrow[r][-1][0] + 1)
            table.extend(rec(0x208, value))
        previous_cell = row_positions[0] + 4 + len(rows[blocks[block][0]])
        for r in blocks[block]:
            if byrow[r]:
                offset = len(table) - previous_cell
                if not 0 <= offset <= 65535:
                    raise WorkbookError("填写内容使 XLS 行块过大，请减少每格文字")
                first_cells.append(offset)
                previous_cell = len(table)
                for _, value in byrow[r]:
                    table.extend(value)
            else:
                first_cells.append(0)
        db_positions.append(len(table))
        table.extend(rec(0xD7, struct.pack("<I", len(table) - row_positions[0]) + struct.pack(f"<{len(first_cells)}H", *first_cells)))
    # Build first, then fix Index pointers using actual record positions.
    output = bytearray()
    index_location = None
    table_location = None
    defcol_location = None
    for i, (pos, kind, value) in enumerate(rr):
        if i == first_table:
            table_location = len(output)
            output.extend(table)
        if i in consumed:
            continue
        if kind == 0x20B:
            index_location = len(output)
            value = value[:16] + bytes(4 * len(db_positions))
        if kind == 0x55:
            defcol_location = len(output)
        if kind == 0x5F:  # CalcSaveRecalc
            value = struct.pack("<H", 1)
        output.extend(rec(kind, value))
    if index_location is not None:
        if defcol_location is not None:
            struct.pack_into("<I", output, index_location + 16, sheet_start + defcol_location)
        for i, p in enumerate(db_positions):
            struct.pack_into("<I", output, index_location + 20 + 4 * i, sheet_start + table_location + p)
    return bytes(output)


def patch_xls(data, overrides):
    o, name, stream, bounds = _xls_source(data)
    try:
        rr = list(records(stream))
        sst = next(((p, v) for p, t, v in rr if t == 0xFC), None)
        strings = list(dict.fromkeys(v for v in overrides.values() if isinstance(v, str)))
        if strings and sst is None:
            raise WorkbookError("此 XLS 没有共享文本表，请用 Excel / WPS 另存后重试")
        first_sheet = min(b[1] for b in bounds)
        global_rr = list(records(stream[:first_sheet]))
        unique = struct.unpack_from("<I", sst[1], 4)[0] if sst else 0
        string_indices = {v: unique + i for i, v in enumerate(strings)}
        globals_out = bytearray()
        in_sst = False
        bounds_locations = []
        for p, kind, value in global_rr:
            if in_sst and kind != 0x3C:
                for s in strings:
                    raw = s.encode("utf-16-le")
                    globals_out.extend(rec(0x3C, struct.pack("<HB", len(raw) // 2, 1) + raw))
                in_sst = False
            if kind == 0xFC:
                total, count = struct.unpack_from("<II", value)
                value = struct.pack("<II", total + len(strings), count + len(strings)) + value[8:]
                in_sst = True
            if kind == 0x85:
                bounds_locations.append(len(globals_out))
            globals_out.extend(rec(kind, value))
        grouped = defaultdict(dict)
        for key, value in overrides.items():
            index, address = key.split(":", 1)
            grouped[int(index)][address] = value
        result = bytearray(globals_out)
        # Physical substream order need not equal tab order.
        for index in sorted(range(len(bounds)), key=lambda i: bounds[i][1]):
            start = bounds[index][1]
            end = min([b[1] for b in bounds if b[1] > start] + [len(stream)])
            new_start = len(result)
            struct.pack_into("<I", result, bounds_locations[index] + 4, new_start)
            if index in grouped:
                result.extend(_rebuild_sheet(stream[start:end], grouped[index], string_indices, new_start, start))
            else:
                raw = bytearray(stream[start:end])
                for p, kind, value in records(raw):
                    if kind == 0x20B:
                        for offset in range(12, len(value), 4):
                            pointer = struct.unpack_from("<I", value, offset)[0]
                            if pointer:
                                struct.pack_into("<I", raw, p + 4 + offset, pointer + new_start - start)
                result.extend(raw)
        return _replace_ole_stream(data, o, name, bytes(result))
    finally:
        o.close()


def export_workbook(data, kind, overrides):
    if not overrides:
        return data
    try:
        return patch_xls(data, overrides) if kind == "xls" else patch_xlsx(data, overrides)
    except WorkbookError:
        raise
    except Exception as exc:
        raise WorkbookError("无法安全生成原格式文件，请保留原表并联系管理员") from exc
