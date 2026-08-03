# -*- coding: utf-8 -*-
"""华康C排期工作簿写入与安全副本生成。"""
from __future__ import annotations

import json
import os
import re
import xml.etree.ElementTree as ET
import zipfile
from copy import copy
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

import openpyxl
import xlrd
from openpyxl import Workbook
from openpyxl.styles import PatternFill
from openpyxl.styles.numbers import BUILTIN_FORMATS, is_date_format
from openpyxl.utils import get_column_letter


APP_DIR = Path(__file__).resolve().parent
STORAGE_DIR = Path(os.environ.get("HUAKANG_STORAGE_DIR") or APP_DIR).expanduser().resolve()
DEFAULT_TEMPLATE_DIR = APP_DIR / "data" / "default_templates"
ACTIVE_TEMPLATE_DIR = STORAGE_DIR / "data" / "active_templates"
BLUE_FILL = PatternFill("solid", fgColor="4F81BD")


@dataclass(frozen=True)
class ScheduleProfile:
    code: str
    label: str
    default_file: str
    sheets: tuple[str, ...]
    header_rows: int
    max_col: int
    style_row: int
    key_cols: tuple[int, ...]
    scan_cols: tuple[int, ...]
    description: str


PROFILES: dict[str, ScheduleProfile] = {
    "index": ScheduleProfile(
        "index",
        "INDEX",
        "index_schedule.xlsx",
        ("建文客排期表", "生产排期"),
        3,
        46,
        6,
        (5, 6),
        (3, 4, 5, 6, 8, 10),
        "PO号、产品、数量、48pcs/carton、货期和美元价格",
    ),
    "jazwares": ScheduleProfile(
        "jazwares",
        "JAZWARES",
        "jazwares_schedule.xlsx",
        ("生产排期 (2)", "生产排期"),
        1,
        53,
        2,
        (4, 9),
        (1, 4, 5, 6, 8, 9, 10, 11),
        "PO、版本、出售客户、PCS/CTN、走货日和价格",
    ),
    "maxx": ScheduleProfile(
        "maxx",
        "MAXX",
        "maxx_schedule.xlsx",
        ("排期", "MAXX放产表"),
        1,
        57,
        2,
        (5, 8),
        (1, 3, 4, 5, 6, 8, 10, 11),
        "S.C.合同号、货号、数量、DELIVERY 和 USD 价格",
    ),
    "strottman": ScheduleProfile(
        "strottman",
        "STROTTMAN",
        "strottman_schedule.xlsx",
        ("2026正单", "Strottman放产表"),
        2,
        58,
        3,
        (5, 8),
        (1, 3, 4, 5, 6, 8, 10, 11),
        "箱数换算件数、Special Instructions 多货期和金额",
    ),
    "supplier": ScheduleProfile(
        "supplier",
        "华康车衣 / JP（待真实PO样本）",
        "supplier_schedule.xlsx",
        ("总表",),
        2,
        20,
        3,
        (4, 5),
        (1, 2, 3, 4, 5, 6, 7),
        "暂无真实采购单样本，当前仅保留模板结构，不计入准确度验收",
    ),
}


def profile_public(profile: ScheduleProfile) -> dict[str, Any]:
    data = asdict(profile)
    data["sheets"] = list(profile.sheets)
    return data


def _active_candidates(code: str) -> list[Path]:
    return [ACTIVE_TEMPLATE_DIR / f"{code}{ext}" for ext in (".xlsx", ".xlsm", ".xls")]


def _metadata_path(code: str) -> Path:
    return ACTIVE_TEMPLATE_DIR / f"{code}.meta.json"


def _read_template_metadata(code: str) -> dict[str, Any]:
    path = _metadata_path(code)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def get_template_path(code: str) -> Path:
    if code not in PROFILES:
        raise KeyError(f"未知模板类型：{code}")
    for path in _active_candidates(code):
        if path.exists():
            return path
    return DEFAULT_TEMPLATE_DIR / PROFILES[code].default_file


def template_statuses() -> list[dict[str, Any]]:
    statuses = []
    for code, profile in PROFILES.items():
        path = get_template_path(code)
        active = any(candidate.exists() and candidate == path for candidate in _active_candidates(code))
        metadata = _read_template_metadata(code) if active else {}
        uploaded_at = metadata.get("uploaded_at", "")
        if active and not uploaded_at:
            uploaded_at = datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds")
        statuses.append({
            **profile_public(profile),
            "path": str(path),
            "filename": path.name,
            "display_filename": metadata.get("original_filename") or path.name,
            "exists": path.exists(),
            "active_upload": active,
            "uploaded_at": uploaded_at,
            "size": path.stat().st_size if path.exists() else 0,
        })
    return statuses


def install_active_template(
    code: str,
    source_path: str,
    extension: str,
    original_filename: str = "",
) -> Path:
    if code not in PROFILES:
        raise KeyError(f"未知模板类型：{code}")
    extension = extension.lower()
    if extension not in {".xlsx", ".xlsm", ".xls"}:
        raise ValueError("排期模板仅支持 .xlsx、.xlsm 或 .xls")
    source = Path(source_path)
    workbook = _load_workbook(source)
    try:
        _select_sheet(workbook, PROFILES[code])
    finally:
        workbook.close()
    ACTIVE_TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    for candidate in _active_candidates(code):
        if candidate.exists():
            candidate.unlink()
    destination = ACTIVE_TEMPLATE_DIR / f"{code}{extension}"
    os.replace(source, destination)
    metadata = {
        "original_filename": original_filename or source.name,
        "uploaded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "extension": extension,
    }
    _metadata_path(code).write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return destination


def reset_active_template(code: str) -> Path:
    if code not in PROFILES:
        raise KeyError(f"未知模板类型：{code}")
    for candidate in _active_candidates(code):
        if candidate.exists():
            candidate.unlink()
    metadata = _metadata_path(code)
    if metadata.exists():
        metadata.unlink()
    return get_template_path(code)


def _excel_date(value: str) -> datetime | str:
    if not value:
        return ""
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except (TypeError, ValueError):
        return value


def _formula_number(value: float) -> str:
    return f"{float(value):.8f}".rstrip("0").rstrip(".")


def _norm(value: Any) -> str:
    if value in (None, ""):
        return ""
    text = str(value).strip().upper()
    text = re.sub(r"\s+", "", text)
    return text


def _same_value(left: Any, right: Any) -> bool:
    if left in (None, "") and right in (None, ""):
        return True
    if isinstance(left, datetime) and isinstance(right, datetime):
        return left.date() == right.date()
    try:
        if not isinstance(left, str) and not isinstance(right, str):
            return abs(float(left) - float(right)) < 1e-8
    except (TypeError, ValueError):
        pass
    return str(left).strip() == str(right).strip()


def _copy_cell_style(source, destination) -> None:
    if source.has_style:
        destination.font = copy(source.font)
        destination.fill = copy(source.fill)
        destination.border = copy(source.border)
        destination.alignment = copy(source.alignment)
        destination.number_format = source.number_format
        destination.protection = copy(source.protection)


def _copy_row_style(ws, source_row: int, target_row: int, max_col: int) -> None:
    if source_row == target_row:
        return
    if source_row in ws.row_dimensions:
        ws.row_dimensions[target_row].height = ws.row_dimensions[source_row].height
    for col in range(1, max_col + 1):
        source = ws.cell(source_row, col)
        target = ws.cell(target_row, col)
        if not target.has_style:
            _copy_cell_style(source, target)


def _load_xls(path: str) -> Workbook:
    """将旧版 .xls 载入可写的 openpyxl 工作簿。

    xlrd 只能提供旧格式的计算结果，因此转换后保留值、日期、合并区域和基础列宽；
    原始 .xls 永远不会被覆盖。
    """
    source = xlrd.open_workbook(path, formatting_info=False)
    wb = Workbook()
    wb.remove(wb.active)
    for source_sheet in source.sheets():
        ws = wb.create_sheet(source_sheet.name[:31] or "Sheet")
        for row in range(source_sheet.nrows):
            for col in range(source_sheet.ncols):
                cell = source_sheet.cell(row, col)
                value = cell.value
                if cell.ctype == xlrd.XL_CELL_DATE:
                    try:
                        value = xlrd.xldate.xldate_as_datetime(value, source.datemode)
                    except (ValueError, TypeError):
                        pass
                ws.cell(row + 1, col + 1, value)
        for row_low, row_high, col_low, col_high in source_sheet.merged_cells:
            if row_high > row_low and col_high > col_low:
                ws.merge_cells(
                    start_row=row_low + 1,
                    end_row=row_high,
                    start_column=col_low + 1,
                    end_column=col_high,
                )
    return wb


def _repair_invalid_xlsx_dates(path: Path) -> tuple[BytesIO | None, list[str]]:
    """在内存副本中保留被错误套用日期格式的大整数。

    部分业务表把 SO/流水号单元格误设为日期。openpyxl 会把超出日期范围的值
    转成 ``#VALUE!``；这里复制原样式但改为常规数字格式，确保安全副本不丢原值。
    """
    namespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    q = lambda name: f"{{{namespace}}}{name}"
    with zipfile.ZipFile(path, "r") as source:
        try:
            styles_data = source.read("xl/styles.xml")
        except KeyError:
            return None, []
        styles = ET.fromstring(styles_data)
        custom_formats = {
            int(node.attrib["numFmtId"]): node.attrib.get("formatCode", "")
            for node in styles.findall(f".//{q('numFmt')}")
            if "numFmtId" in node.attrib
        }
        cell_xfs = styles.find(q("cellXfs"))
        if cell_xfs is None:
            return None, []
        date_styles = set()
        for index, xf in enumerate(list(cell_xfs)):
            num_format_id = int(xf.attrib.get("numFmtId", "0"))
            format_code = custom_formats.get(num_format_id, BUILTIN_FORMATS.get(num_format_id, ""))
            if format_code and is_date_format(format_code):
                date_styles.add(index)
        if not date_styles:
            return None, []

        replacements: dict[int, int] = {}
        changed: dict[str, bytes] = {}
        repairs = []
        worksheet_names = [name for name in source.namelist() if name.startswith("xl/worksheets/") and name.endswith(".xml")]
        for name in worksheet_names:
            root = ET.fromstring(source.read(name))
            dirty = False
            for cell in root.iter(q("c")):
                if cell.find(q("f")) is not None:
                    continue
                try:
                    style_index = int(cell.attrib.get("s", "0"))
                except ValueError:
                    continue
                if style_index not in date_styles:
                    continue
                value_node = cell.find(q("v"))
                if value_node is None or value_node.text in (None, ""):
                    continue
                try:
                    numeric = float(value_node.text)
                except ValueError:
                    continue
                if 0 <= numeric <= 2958465.999999:
                    continue
                if style_index not in replacements:
                    original = list(cell_xfs)[style_index]
                    replacement = deepcopy(original)
                    replacement.set("numFmtId", "0")
                    replacement.attrib.pop("applyNumberFormat", None)
                    replacements[style_index] = len(cell_xfs)
                    cell_xfs.append(replacement)
                cell.set("s", str(replacements[style_index]))
                repairs.append(f"{name}:{cell.attrib.get('r', '')}={value_node.text}")
                dirty = True
            if dirty:
                changed[name] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        if not repairs:
            return None, []
        cell_xfs.set("count", str(len(cell_xfs)))
        changed["xl/styles.xml"] = ET.tostring(styles, encoding="utf-8", xml_declaration=True)

        stream = BytesIO()
        with zipfile.ZipFile(stream, "w") as destination:
            for info in source.infolist():
                destination.writestr(info, changed.get(info.filename, source.read(info.filename)))
        stream.seek(0)
        return stream, repairs


def _load_workbook(path: Path) -> Workbook:
    if path.suffix.lower() == ".xls":
        return _load_xls(str(path))
    repaired_stream, repairs = _repair_invalid_xlsx_dates(path)
    workbook = openpyxl.load_workbook(
        repaired_stream or path,
        keep_vba=path.suffix.lower() == ".xlsm",
    )
    workbook._huakang_date_repairs = repairs
    return workbook


def _select_sheet(wb: Workbook, profile: ScheduleProfile):
    for name in profile.sheets:
        if name in wb.sheetnames:
            return wb[name]
    raise ValueError(f"模板缺少工作表：{' / '.join(profile.sheets)}")


def _last_data_row(ws, profile: ScheduleProfile) -> int:
    last = profile.header_rows
    for row in range(profile.header_rows + 1, ws.max_row + 1):
        if any(ws.cell(row, col).value not in (None, "") for col in profile.scan_cols):
            last = row
    return last


def _row_key_from_sheet(ws, profile: ScheduleProfile, row: int) -> tuple[str, ...]:
    return tuple(_norm(ws.cell(row, col).value) for col in profile.key_cols)


def _row_key_from_order(profile: ScheduleProfile, order: dict[str, Any], line: dict[str, Any]) -> tuple[str, ...]:
    if profile.code == "index":
        return _norm(order.get("contract_no") or order.get("po_number")), _norm(line.get("item_code"))
    if profile.code == "jazwares":
        return _norm(order.get("po_number")), _norm(line.get("item_code"))
    if profile.code == "maxx":
        return _norm(order.get("contract_no") or order.get("po_number")), _norm(line.get("item_code"))
    if profile.code == "strottman":
        item = re.sub(r"-F\d+$", "", str(line.get("item_code") or ""), flags=re.I)
        return _norm(order.get("contract_no") or order.get("po_number")), _norm(item)
    return _norm(order.get("contract_no") or order.get("po_number")), _norm(line.get("item_code"))


def _product_columns(profile: ScheduleProfile) -> tuple[tuple[int, ...], int]:
    if profile.code == "index":
        return (6, 7, 3), 8
    if profile.code == "jazwares":
        return (9, 8), 10
    if profile.code == "maxx":
        return (8, 9), 10
    if profile.code == "strottman":
        return (8, 9), 10
    return (5,), 6


def _product_item_keys(profile: ScheduleProfile, value: Any) -> list[str]:
    key = _norm(value)
    if not key or key in {"/", "-", "--", "N/A", "NA", "无", "空"}:
        return []
    keys = [key]
    if profile.code == "strottman":
        base = _norm(re.sub(r"-F\d+$", "", str(value or ""), flags=re.I))
        if base and base not in keys:
            keys.append(base)
    return keys


def _build_product_catalog(ws, profile: ScheduleProfile) -> tuple[dict[str, str], list[dict[str, Any]]]:
    item_cols, product_col = _product_columns(profile)
    values: dict[str, dict[str, str]] = {}
    for row in range(profile.header_rows + 1, ws.max_row + 1):
        product = re.sub(r"\s+", " ", str(ws.cell(row, product_col).value or "").strip())
        if not product or product.startswith("="):
            continue
        product_key = re.sub(r"[\W_]+", "", product.casefold())
        if not product_key:
            continue
        for item_col in item_cols:
            for item_key in _product_item_keys(profile, ws.cell(row, item_col).value):
                values.setdefault(item_key, {})[product_key] = product

    catalog: dict[str, str] = {}
    conflicts: list[dict[str, Any]] = []
    for item, product_values in values.items():
        if len(product_values) == 1:
            catalog[item] = next(iter(product_values.values()))
        elif len(product_values) > 1:
            conflicts.append({
                "item": item,
                "field": "product_name",
                "values": list(product_values.values())[:8],
            })
    return catalog, conflicts


def _inherit_product_names(
    ws,
    profile: ScheduleProfile,
    entries: list[tuple[dict[str, Any], dict[str, Any]]],
) -> tuple[list[tuple[dict[str, Any], dict[str, Any]]], dict[str, Any]]:
    catalog, conflicts = _build_product_catalog(ws, profile)
    inherited_entries = []
    applied = 0
    matched = 0
    for order, source_line in entries:
        line = dict(source_line)
        standard = ""
        for key in _product_item_keys(profile, line.get("item_code")):
            if catalog.get(key):
                standard = catalog[key]
                break
        if standard:
            matched += 1
            original = str(line.get("description") or "").strip()
            line["_po_description"] = original
            line["_product_name_source"] = "按货号从当前排期继承"
            if re.sub(r"[\W_]+", "", original.casefold()) != re.sub(r"[\W_]+", "", standard.casefold()):
                line["description"] = standard
                applied += 1
        else:
            line["_product_name_source"] = "PO识别值（排期无唯一映射）"
        inherited_entries.append((order, line))
    return inherited_entries, {
        "rule": "same_schedule_same_item_unique_name",
        "mapped_items": len(catalog),
        "matched_rows": matched,
        "applied": applied,
        "conflicts": conflicts,
    }


def _notes(order: dict[str, Any], line: dict[str, Any]) -> str:
    parts = []
    if order.get("po_number"):
        parts.append(f"客户PO {order['po_number']}")
    if line.get("carton_qty"):
        parts.append(f"{line['carton_qty']}箱")
    if line.get("pcs_per_carton"):
        parts.append(f"{line['pcs_per_carton']}件/箱")
    dates = order.get("ship_dates") or []
    if len(dates) > 1:
        parts.append("分批货期 " + " / ".join(dates))
    if order.get("version"):
        parts.append(f"PO版本 {order['version']}")
    return "；".join(parts)


def compose_row(
    profile: ScheduleProfile,
    order: dict[str, Any],
    line: dict[str, Any],
    row: int,
    exchange_rate: float,
) -> dict[int, Any]:
    po_date = _excel_date(order.get("po_date", ""))
    ship_date = _excel_date(order.get("ship_date", ""))
    po = order.get("po_number", "")
    contract = order.get("contract_no") or po
    item = line.get("item_code", "")
    description = line.get("description", "")
    qty = int(line.get("qty") or 0)
    usd = float(line.get("unit_price_usd") or 0)
    hkd = float(line.get("unit_price_hkd") or 0)
    rate = _formula_number(exchange_rate)
    usd_formula = f"={_formula_number(usd)}*{rate}" if usd else ""

    if profile.code == "index":
        customer = order.get("ship_to") or profile.label
        return {
            3: item,
            4: po_date,
            5: contract,
            6: item,
            7: item,
            8: description,
            10: qty,
            13: ship_date,
            19: customer,
            20: po,
            23: int(line["pcs_per_carton"]) if line.get("pcs_per_carton") else "",
            24: f"=IFERROR(J{row}/W{row},\"\")" if line.get("pcs_per_carton") else "",
            27: usd or "",
            28: usd_formula,
            29: f"=AA{row}*J{row}" if usd and qty else "",
            30: f"=AB{row}*J{row}" if usd and qty else "",
            33: _notes(order, line),
        }

    if profile.code == "jazwares":
        customer = order.get("ship_to") or profile.label
        values: dict[int, Any] = {
            1: po_date,
            4: po,
            5: contract,
            6: customer,
            8: item,
            9: item,
            10: description,
            11: qty,
            24: f"一箱{line['pcs_per_carton']}个" if line.get("pcs_per_carton") else "",
            41: ship_date,
            42: usd_formula,
            43: f"=AP{row}*K{row}" if usd and qty else "",
            44: ship_date,
            49: _notes(order, line),
        }
        if line.get("pcs_per_carton"):
            values[25] = f"=IFERROR(K{row}/{int(line['pcs_per_carton'])},\"\")"
        return values

    if profile.code == "maxx":
        return {
            1: po_date,
            3: "MAXX",
            4: po,
            5: contract,
            6: order.get("ship_to") or "MAXX",
            7: "MAXX",
            8: item,
            9: item,
            10: description,
            11: qty,
            12: f"=IFERROR(K{row}/{int(line['pcs_per_carton'])},\"\")" if line.get("pcs_per_carton") else "",
            25: f"一箱{line['pcs_per_carton']}个" if line.get("pcs_per_carton") else "",
            42: ship_date,
            43: usd_formula,
            44: f"=AQ{row}*K{row}" if usd and qty else "",
            51: _notes(order, line),
        }

    if profile.code == "strottman":
        base_item = re.sub(r"-F\d+$", "", str(item), flags=re.I)
        return {
            1: po_date,
            3: po,
            4: "STROTTMAN",
            5: contract,
            6: order.get("ship_to") or "Strottman",
            7: "Strottman",
            8: base_item,
            9: item if _norm(item) != _norm(base_item) else "",
            10: description,
            11: qty,
            12: f"=IFERROR(K{row}/{int(line['pcs_per_carton'])},\"\")" if line.get("pcs_per_carton") else "",
            23: f"一箱{line['pcs_per_carton']}个" if line.get("pcs_per_carton") else "",
            39: ship_date,
            40: usd_formula,
            43: f"=AN{row}*K{row}" if usd and qty else "",
            48: _notes(order, line),
        }

    price = hkd or (usd * exchange_rate if usd else 0)
    return {
        1: po_date,
        2: po_date,
        4: contract,
        5: item,
        6: description,
        7: qty,
        11: line.get("version") or order.get("version", ""),
        15: f"{order.get('ship_date', '')}前交货" if order.get("ship_date") else "",
        17: ship_date,
        18: price or "",
        19: f"=R{row}*G{row}" if price and qty else "",
        20: _notes(order, line),
    }


def _build_existing_index(ws, profile: ScheduleProfile) -> dict[tuple[str, ...], list[int]]:
    # 同一 (合同/PO, 货号) 可能分批出货占多行，必须收集全部行号；
    # 单行映射会让多条订单行写进同一行互相覆盖。
    index: dict[tuple[str, ...], list[int]] = {}
    for row in range(profile.header_rows + 1, ws.max_row + 1):
        key = _row_key_from_sheet(ws, profile, row)
        if all(key):
            index.setdefault(key, []).append(row)
    return index


def _write_values(ws, row: int, values: dict[int, Any], *, update_only: bool = False) -> list[str]:
    changes = []
    for col, value in values.items():
        if value in (None, ""):
            continue
        cell = ws.cell(row, col)
        if _same_value(cell.value, value):
            continue
        old = cell.value
        cell.value = value
        cell.fill = copy(BLUE_FILL)
        if isinstance(value, datetime):
            cell.number_format = "yyyy/m/d"
        changes.append(f"{get_column_letter(col)}: {old if old not in (None, '') else '空'} → {value}")
    return changes


def _copy_headers(source_ws, destination_ws, profile: ScheduleProfile) -> None:
    for row in range(1, profile.header_rows + 1):
        if row in source_ws.row_dimensions:
            destination_ws.row_dimensions[row].height = source_ws.row_dimensions[row].height
        for col in range(1, profile.max_col + 1):
            source = source_ws.cell(row, col)
            destination = destination_ws.cell(row, col, source.value)
            _copy_cell_style(source, destination)
    for col in range(1, profile.max_col + 1):
        letter = get_column_letter(col)
        width = source_ws.column_dimensions[letter].width
        if width:
            destination_ws.column_dimensions[letter].width = width
    destination_ws.freeze_panes = source_ws.freeze_panes


def _new_rows_workbook(
    source_ws,
    profile: ScheduleProfile,
    new_entries: list[tuple[dict[str, Any], dict[str, Any]]],
    exchange_rate: float,
    path: Path,
    inheritance: dict[str, Any] | None = None,
) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "新增排期"
    _copy_headers(source_ws, ws, profile)
    for offset, (order, line) in enumerate(new_entries, start=profile.header_rows + 1):
        _copy_row_style(ws, profile.style_row, offset, profile.max_col)
        _write_values(ws, offset, compose_row(profile, order, line, offset, exchange_rate))

    detail = wb.create_sheet("解析明细")
    headers = [
        "客户", "PO号", "合同号", "接单日期", "走货日期", "货号", "产品名称", "数量",
        "箱数", "每箱件数", "USD单价", "USD金额", "HKD换算单价", "品名来源",
        "PO原产品名称", "来源文件",
    ]
    for col, title in enumerate(headers, 1):
        cell = detail.cell(1, col, title)
        cell.fill = copy(BLUE_FILL)
    for row, (order, line) in enumerate(new_entries, 2):
        values = [
            profile.label,
            order.get("po_number", ""),
            order.get("contract_no", ""),
            order.get("po_date", ""),
            " / ".join(order.get("ship_dates") or [order.get("ship_date", "")]),
            line.get("item_code", ""),
            line.get("description", ""),
            line.get("qty", 0),
            line.get("carton_qty", 0),
            line.get("pcs_per_carton", 0),
            line.get("unit_price_usd", 0),
            line.get("amount_usd", 0),
            round(float(line.get("unit_price_usd") or 0) * exchange_rate, 6),
            line.get("_product_name_source", ""),
            line.get("_po_description", ""),
            order.get("filename", ""),
        ]
        for col, value in enumerate(values, 1):
            detail.cell(row, col, value)
    detail.freeze_panes = "A2"
    for col, width in enumerate((14, 18, 18, 13, 24, 18, 48, 12, 10, 12, 12, 14, 15, 26, 48, 34), 1):
        detail.column_dimensions[get_column_letter(col)].width = width
    if inheritance and (inheritance.get("matched_rows") or inheritance.get("conflicts")):
        check = wb.create_sheet("排期继承检查")
        check_headers = ("状态", "货号", "字段", "排期值")
        for col, title in enumerate(check_headers, 1):
            check.cell(1, col, title).fill = copy(BLUE_FILL)
        check.cell(2, 1, "已按货号匹配标准品名")
        check.cell(2, 2, f"{inheritance.get('matched_rows', 0)} 行")
        row_no = 3
        for conflict in inheritance.get("conflicts", []):
            values = (
                "排期存在冲突，未自动继承",
                conflict.get("item", ""),
                conflict.get("field", ""),
                " / ".join(conflict.get("values", [])),
            )
            for col, value in enumerate(values, 1):
                check.cell(row_no, col, value)
            row_no += 1
        check.freeze_panes = "A2"
        for col, width in enumerate((28, 20, 18, 64), 1):
            check.column_dimensions[get_column_letter(col)].width = width
    wb.save(path)
    wb.close()


class ScheduleWriter:
    """按客户模板只生成新单 Excel；永不修改或覆盖原排期。"""

    def __init__(self, exchange_rate: float = 7.75):
        self.exchange_rate = float(exchange_rate)
        if not 1 <= self.exchange_rate <= 20:
            raise ValueError("汇率超出合理范围")

    def write(self, orders: list[dict[str, Any]], export_dir: str) -> dict[str, Any]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for order in orders:
            code = str(order.get("customer_code") or "")
            if code not in PROFILES:
                continue
            grouped.setdefault(code, []).append(order)
        if not grouped:
            return {"ok": False, "msg": "没有可写入的已识别订单", "results": []}
        Path(export_dir).mkdir(parents=True, exist_ok=True)
        results = [self._write_profile(code, group, Path(export_dir)) for code, group in grouped.items()]
        return {
            "ok": all(result.get("ok") for result in results),
            "msg": "；".join(result.get("msg", "") for result in results),
            "results": results,
            "exchange_rate": self.exchange_rate,
        }

    def _write_profile(
        self,
        code: str,
        orders: list[dict[str, Any]],
        export_dir: Path,
    ) -> dict[str, Any]:
        profile = PROFILES[code]
        template_path = get_template_path(code)
        if not template_path.exists():
            return {"ok": False, "profile": code, "msg": f"{profile.label} 模板不存在"}
        wb = _load_workbook(template_path)
        try:
            ws = _select_sheet(wb, profile)
            new_entries = [
                (order, line)
                for order in orders
                for line in order.get("lines", [])
            ]
            new_entries, inheritance = _inherit_product_names(ws, profile, new_entries)
            new_details = [
                {
                    "po": order.get("po_number", ""),
                    "item": line.get("item_code", ""),
                    "row": profile.header_rows + offset,
                "description": line.get("description", ""),
                    "product_name_source": line.get("_product_name_source", ""),
                }
                for offset, (order, line) in enumerate(new_entries, 1)
            ]

            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            new_name = ""
            if new_entries:
                new_name = f"{profile.label.replace(' / ', '-')}_新单_{stamp}.xlsx"
                _new_rows_workbook(
                    ws,
                    profile,
                    new_entries,
                    self.exchange_rate,
                    export_dir / new_name,
                    inheritance,
                )

            conflict_suffix = (
                f"；另有 {len(inheritance['conflicts'])} 组货号/品名冲突未自动继承"
                if inheritance["conflicts"] else ""
            )
            return {
                "ok": True,
                "profile": code,
                "label": profile.label,
                "msg": (
                    f"{profile.label}：已按新单生成 {len(new_entries)} 行 Excel，原排期未修改"
                    if new_entries else f"{profile.label}：无可生成的新单行"
                ) + conflict_suffix,
                "template": template_path.name,
                "sheet": ws.title,
                "full_output": "",
                "new_output": new_name,
                "new_count": len(new_entries),
                "modified": 0,
                "unchanged": 0,
                "new_details": new_details,
                "modified_details": [],
                "inheritance": inheritance,
                "mode": "new_order_only",
            }
        except Exception as exc:
            return {
                "ok": False,
                "profile": code,
                "label": profile.label,
                "msg": f"{profile.label} 写入失败：{exc}",
            }
        finally:
            wb.close()
