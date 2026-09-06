"""Read metadata and exactly one selected worksheet, without its fake rectangle.

Formula text/cache are evidence only. No external links or formula evaluation.
"""

import hashlib
import io
import posixpath
import re
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta
from xml.etree import ElementTree as ET

from openpyxl.formula.translate import Translator, TranslatorError

from .calculations import TZ

NS = {
    "s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


def column_number(letters):
    n = 0
    for c in letters:
        n = n * 26 + ord(c) - 64
    return n


def excel_date(value, date1904=False):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    try:
        return (
            datetime(1904, 1, 1, tzinfo=TZ)
            if date1904
            else datetime(1899, 12, 30, tzinfo=TZ)
        ) + timedelta(days=value)
    except (OverflowError, ValueError):
        return None


def read_sheet(content: bytes, sheet_name: str):
    if len(content) > 40 * 1024 * 1024:
        raise ValueError("工作簿超过 40 MB")
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        if len(archive.infolist()) > 10000:
            raise ValueError("工作簿包含过多压缩项")

        def read(name, limit=128 * 1024 * 1024):
            info = archive.getinfo(name)
            if info.file_size > limit or (
                info.file_size > 1024 * 1024
                and info.file_size / max(1, info.compress_size) > 1000
            ):
                raise ValueError("工作簿 XML 体积异常")
            data = archive.read(name)
            if b"<!DOCTYPE" in data or b"<!ENTITY" in data:
                raise ValueError("不支持带外部实体的工作簿")
            return data

        workbook = ET.fromstring(read("xl/workbook.xml", 2 * 1024 * 1024))
        rels = ET.fromstring(read("xl/_rels/workbook.xml.rels", 2 * 1024 * 1024))
        targets = {
            r.attrib["Id"]: r.attrib["Target"]
            for r in rels
            if r.attrib.get("TargetMode") != "External"
        }
        sheets = {
            n.attrib["name"]: n.attrib[f"{{{NS['r']}}}id"]
            for n in workbook.findall("s:sheets/s:sheet", NS)
        }
        if sheet_name not in sheets:
            raise ValueError(f"未找到工作表 {sheet_name}")
        target = targets[sheets[sheet_name]]
        target = (
            target.lstrip("/")
            if target.startswith("/")
            else posixpath.normpath(posixpath.join("xl", target))
        )
        if not target.startswith("xl/worksheets/") or ".." in target.split("/"):
            raise ValueError("工作表路径不合法")
        props = workbook.find("s:workbookPr", NS)
        date1904 = props is not None and props.attrib.get("date1904") in {"1", "true"}
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            for _, node in ET.iterparse(
                io.BytesIO(read("xl/sharedStrings.xml")), events=("end",)
            ):
                if node.tag == f"{{{NS['s']}}}si":
                    strings.append(
                        "".join(t.text or "" for t in node.findall(".//s:t", NS))
                    )
                    node.clear()
        rows = defaultdict(dict)
        formulas = {}
        shared = {}
        merged = []
        stored = 0
        dimension = ""
        for _, node in ET.iterparse(io.BytesIO(read(target)), events=("end",)):
            local = node.tag.rsplit("}", 1)[-1]
            if local == "dimension":
                dimension = node.attrib.get("ref", "")
            elif local == "mergeCell":
                merged.append(node.attrib["ref"])
            elif local == "c":
                stored += 1
                if stored > 1500000:
                    raise ValueError("目标工作表实际单元格超过限制")
                address = node.attrib["r"]
                m = re.fullmatch(r"([A-Z]+)(\d+)", address)
                if not m:
                    raise ValueError("单元格坐标不合法")
                kind = node.attrib.get("t")
                v = node.find("s:v", NS)
                value = v.text if v is not None else None
                if kind == "s" and value is not None:
                    value = strings[int(value)]
                elif kind == "inlineStr":
                    value = "".join(t.text or "" for t in node.findall(".//s:t", NS))
                elif value is not None and kind not in {"str", "e"}:
                    try:
                        num = float(value)
                        value = int(num) if num.is_integer() else num
                    except ValueError:
                        pass
                f = node.find("s:f", NS)
                if value is not None or f is not None:
                    cell = {
                        "cached_value": value,
                        "type": kind,
                        "formula_original": f.text if f is not None else None,
                        "formula_expanded": f.text if f is not None else None,
                        "formula_attributes": dict(f.attrib) if f is not None else None,
                    }
                    rows[int(m.group(2))][m.group(1)] = cell
                    if f is not None:
                        formulas[address] = cell
                        if f.attrib.get("t") == "shared" and f.text:
                            shared[f.attrib["si"]] = (address, f.text)
                node.clear()
            elif local == "row":
                node.clear()
        for address, cell in formulas.items():
            attrs = cell["formula_attributes"]
            if attrs.get("t") == "shared" and not cell["formula_original"]:
                base = shared.get(attrs.get("si"))
                if base:
                    try:
                        cell["formula_expanded"] = Translator(
                            "=" + base[1], origin=base[0]
                        ).translate_formula(address)[1:]
                    except (TranslatorError, ValueError):
                        cell["formula_issue"] = "UNRESOLVED_SHARED_FORMULA"
                else:
                    cell["formula_issue"] = "UNRESOLVED_SHARED_FORMULA"
    return {
        "sha256": hashlib.sha256(content).hexdigest(),
        "sheet_name": sheet_name,
        "date1904": date1904,
        "rows": dict(rows),
        "formula_cells": formulas,
        "merged_ranges": merged,
        "stored_cell_count": stored,
        "declared_dimension": dimension,
        "read_worksheets": [target],
    }
