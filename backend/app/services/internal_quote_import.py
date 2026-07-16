from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from io import BytesIO
from typing import Any, Callable

from openpyxl import load_workbook


IMPORT_TYPE_DEPARTMENTS = {
    "mold": "engineering",
    "electronic": "electronic",
    "painting": "painting",
    "sewing": "sewing",
    "assembly": "assembly",
}
MAX_WORKBOOK_ROWS = 2000
MAX_WORKBOOK_COLUMNS = 100
MAX_OOXML_UNCOMPRESSED_SIZE = 120 * 1024 * 1024
MAX_OOXML_ENTRIES = 5000

PAINTING_PROCESSES = (
    ("夹模", "clamp"),
    ("移印", "pad_print"),
    ("散枪", "spray"),
    ("边模", "edge"),
    ("油色", "paint"),
    ("浸油", "dip"),
    ("抹油", "wipe"),
)


@dataclass
class ParsedInternalQuoteImport:
    target_department: str
    sheet_name: str
    header_row: int
    row_count: int
    payload_fragment: dict[str, Any]
    warnings: list[str] = field(default_factory=list)


def text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value).strip()


def normalized(value: object) -> str:
    return (
        re.sub(r"\s+", "", text(value))
        .replace("（", "(")
        .replace("）", ")")
        .upper()
    )


def number(value: object, default: Decimal | None = None) -> Decimal | None:
    if value is None or value == "":
        return default
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, (int, float)):
        result = Decimal(str(value))
    else:
        token = re.sub(r"[^\d.\-]", "", text(value).replace(",", ""))
        if not token or token in {"-", ".", "-."}:
            return default
        try:
            result = Decimal(token)
        except InvalidOperation:
            return default
    return result if result.is_finite() else default


def decimal_text(value: Decimal | int | float | str | None) -> str:
    parsed = number(value, Decimal("0")) or Decimal("0")
    return format(parsed.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP), "f")


def _validate_ooxml(content: bytes) -> None:
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_OOXML_ENTRIES:
                raise ValueError("Excel 内部文件数量异常，已拒绝解析")
            if sum(item.file_size for item in entries) > MAX_OOXML_UNCOMPRESSED_SIZE:
                raise ValueError("Excel 解压后体积超过限制，已拒绝解析")
            if "[Content_Types].xml" not in archive.namelist():
                raise ValueError("文件不是有效的 xlsx/xlsm 工作簿")
    except zipfile.BadZipFile as error:
        raise ValueError("文件不是有效的 xlsx/xlsm 工作簿") from error


def workbook_rows(content: bytes) -> list[tuple[str, list[list[object]]]]:
    _validate_ooxml(content)
    try:
        workbook = load_workbook(BytesIO(content), data_only=True, read_only=True)
    except Exception as error:
        raise ValueError("无法读取 Excel，请确认文件为有效的 xlsx/xlsm 工作簿") from error
    sheets: list[tuple[str, list[list[object]]]] = []
    try:
        for sheet in workbook.worksheets:
            rows = [
                list(row[:MAX_WORKBOOK_COLUMNS])
                for row in sheet.iter_rows(
                    min_row=1,
                    max_row=min(sheet.max_row, MAX_WORKBOOK_ROWS),
                    values_only=True,
                )
            ]
            if any(any(text(cell) for cell in row) for row in rows):
                sheets.append((sheet.title, rows))
    finally:
        workbook.close()
    if not sheets:
        raise ValueError("工作簿为空")
    return sheets


def row_has(row: list[object], *patterns: str) -> bool:
    joined = "|".join(normalized(cell) for cell in row)
    return all(any(normalized(token) in joined for token in pattern.split("|")) for pattern in patterns)


def find_header(
    sheets: list[tuple[str, list[list[object]]]],
    import_type: str,
) -> tuple[str, list[list[object]], int]:
    patterns = {
        "mold": ("模号|模具编号|MOLDNO|产品名称", "名称|模价|总价|材质|材料|AMOUNT"),
        "electronic": ("零件名称", "规格", "用量"),
        "sewing": ("物料名称", "裁片部位", "用量", "价钱"),
        "assembly": ("工序名称", "人数"),
        "painting": ("位置", "夹模|移印|散枪|边模|抹油"),
    }[import_type]
    for sheet_name, rows in sheets:
        for index, row in enumerate(rows[:40]):
            if row_has(row, *patterns):
                return sheet_name, rows, index
    raise ValueError(
        {
            "mold": "未找到模具编号/名称/价格表头",
            "electronic": "未找到零件名称/规格/用量表头",
            "sewing": "未找到物料名称/裁片部位/用量/价钱表头",
            "assembly": "未找到工序名称/人数表头",
            "painting": "未找到位置及喷油工序表头",
        }[import_type]
    )


def column_index(header: list[object], aliases: tuple[str, ...]) -> int | None:
    tokens = tuple(normalized(alias) for alias in aliases)
    for index, value in enumerate(header):
        header_token = normalized(value)
        if header_token and any(alias in header_token for alias in tokens):
            return index
    return None


def value_at(row: list[object], index: int | None) -> object:
    return row[index] if index is not None and index < len(row) else None


def _next_number(row: list[object], start: int) -> Decimal | None:
    for value in row[start + 1 :]:
        parsed = number(value)
        if parsed is not None:
            return parsed
    return None


def _parse_mold(
    rows: list[list[object]],
    header_index: int,
    *,
    fallback_qty: Decimal,
    **_: object,
) -> tuple[dict[str, Any], int, list[str]]:
    header = rows[header_index]
    columns = {
        "mold_no": column_index(header, ("模号", "模具编号", "客人模具编号", "MOLD NO")),
        "name": column_index(header, ("产品名称", "零件名称", "配件名称", "模具名称", "加工内容", "名称")),
        "material": column_index(header, ("产品材质", "塑胶原料", "胶料类型", "材质", "材料")),
        "weight": column_index(header, ("零件重量", "克重", "净重", "PART WEIGHT")),
        "cavity": column_index(header, ("出模数", "型腔", "模数", "CAV")),
        "sets": column_index(header, ("套数", "数量/件", "数量", "UP")),
        "price": column_index(header, ("含税模价", "总价", "模价", "TOTAL AMOUNT", "AMOUNT")),
        "machine": column_index(header, ("机型(TON)", "INJECTION MACHINE TYPE", "机型")),
        "target": column_index(header, ("模具预计日啤数", "目标数", "CYCLES/DAY")),
        "structure": column_index(header, ("模具结构", "滑块", "行位", "加工内容")),
        "mold_size": column_index(header, ("模具尺寸", "模胚尺寸", "模胚型号")),
        "color": column_index(header, ("颜色", "COLOR")),
        "note": column_index(header, ("备注", "说明", "REMARK")),
    }
    warnings: list[str] = []
    molds: list[dict[str, Any]] = []
    last_mold_no = ""
    amortization_candidates: list[Decimal] = []

    explicit_amortization: Decimal | None = None
    for row in rows:
        for index, cell in enumerate(row):
            if re.search(r"分摊(数量|套数)|摊分(数量|套数)", text(cell)):
                explicit_amortization = _next_number(row, index)
                if explicit_amortization and explicit_amortization > 0:
                    break

    for source_row, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
        joined = "".join(text(cell) for cell in row)
        if re.search(r"^[一二三四五六七八九十]、.+部分", joined):
            break
        if re.search(r"^(合计|小计|总计|说明|备注|客户确认|签名)", joined):
            continue
        mold_no = text(value_at(row, columns["mold_no"])) or last_mold_no
        name = text(value_at(row, columns["name"]))
        price = number(value_at(row, columns["price"]))
        if mold_no:
            last_mold_no = mold_no
        if not mold_no and not name:
            continue
        if not name:
            name = mold_no
        if price is None:
            warnings.append(f"第 {source_row} 行 {name} 未识别模具价格，已按 0 预览")
            price = Decimal("0")
        sets = number(value_at(row, columns["sets"]), Decimal("1")) or Decimal("1")
        quantity = sets
        if sets > 100:
            amortization_candidates.append(sets)
            quantity = Decimal("1")
            warnings.append(f"第 {source_row} 行套数 {decimal_text(sets)} 较大，按分摊数量候选处理，模具数量按 1")
        molds.append(
            {
                "item": name,
                "mold_no": mold_no,
                "quantity": decimal_text(max(quantity, Decimal("0"))),
                "cost_rmb": decimal_text(max(price, Decimal("0"))),
                "material": text(value_at(row, columns["material"])),
                "net_weight_g": decimal_text(number(value_at(row, columns["weight"]), Decimal("0"))),
                "cavity": text(value_at(row, columns["cavity"])),
                "machine_code": text(value_at(row, columns["machine"])),
                "target_output": decimal_text(number(value_at(row, columns["target"]), Decimal("0"))),
                "structure": text(value_at(row, columns["structure"])),
                "mold_size": text(value_at(row, columns["mold_size"])),
                "color": text(value_at(row, columns["color"])),
                "note": text(value_at(row, columns["note"])),
                "source_row": source_row,
            }
        )
    if not molds:
        raise ValueError("已识别模具表头，但没有解析到模具明细")

    amortization_qty = explicit_amortization
    if amortization_qty is None and amortization_candidates:
        amortization_qty = amortization_candidates[0]
    if amortization_qty is None:
        amortization_qty = max(fallback_qty, Decimal("1"))
        warnings.append(f"未识别模具分摊数量，预览按报价数量 {decimal_text(amortization_qty)} 填入")
    warnings.append("嵌入模具图片不自动写入报价，请在对应工程分段上传图片附件")
    return {"molds": molds, "amortization_qty": decimal_text(amortization_qty)}, len(molds), warnings


def _parse_electronic(
    rows: list[list[object]],
    header_index: int,
    *,
    rmb_hkd: Decimal,
    **_: object,
) -> tuple[dict[str, Any], int, list[str]]:
    header = rows[header_index]
    columns = {
        "name": column_index(header, ("零件名称",)),
        "spec": column_index(header, ("规格",)),
        "qty": column_index(header, ("用量", "数量")),
        "unit": column_index(header, ("单价",)),
        "amount": column_index(header, ("合计", "金额")),
        "note": column_index(header, ("备注",)),
    }
    unit_header = normalized(value_at(header, columns["unit"]))
    source_is_hkd = "HKD" in unit_header or "港币" in unit_header
    divisor = Decimal("1") if source_is_hkd else rmb_hkd
    if divisor <= 0:
        raise ValueError("报价参考快照的 RMB/HKD 汇率无效")

    scalar_labels = {
        "邦定": "bonding_hkd",
        "贴片": "smt_hkd",
        "SMT": "smt_hkd",
        "人工成本": "labor_hkd",
        "测试": "testing_hkd",
        "包装运输": "packaging_hkd",
        "抵税差额": "tax_credit_difference_hkd",
    }
    fragment: dict[str, Any] = {"components": []}
    for row in rows:
        row_text = "|".join(text(cell) for cell in row)
        for index, cell in enumerate(row):
            label = text(cell)
            for keyword, target in scalar_labels.items():
                if keyword in label and target not in fragment:
                    parsed = _next_number(row, index)
                    if parsed is not None:
                        fragment[target] = decimal_text(parsed / divisor)
        profit = re.search(r"(\d{1,3}(?:\.\d+)?)%\s*利润", row_text)
        if profit:
            fragment["profit_rate_percent"] = decimal_text(Decimal(profit.group(1)))

    warnings: list[str] = []
    last_parent: dict[str, Any] | None = None
    stop_words = tuple(scalar_labels) + ("零件成本", "含税报价", "合计成本", "报价人", "审核", "核准")
    for source_row, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
        name = text(value_at(row, columns["name"]))
        spec = text(value_at(row, columns["spec"]))
        qty = number(value_at(row, columns["qty"]))
        unit = number(value_at(row, columns["unit"]))
        amount_value = number(value_at(row, columns["amount"]))
        row_text = "|".join(text(cell) for cell in row)
        if any(keyword in row_text for keyword in stop_words):
            continue
        if unit is None and amount_value is not None and qty and qty > 0:
            unit = amount_value / qty
        if not name and not spec:
            continue
        if qty is None:
            qty = Decimal("1")
        if unit is None:
            unit = Decimal("0")
            warnings.append(f"第 {source_row} 行 {name or spec} 未识别单价，已按 0 预览")
        component = {
            "item": name,
            "specification": spec,
            "quantity": decimal_text(max(qty, Decimal("0"))),
            "unit_price_hkd": decimal_text(max(unit / divisor, Decimal("0"))),
            "source_unit_price": decimal_text(unit),
            "source_currency": "HKD" if source_is_hkd else "RMB",
            "note": text(value_at(row, columns["note"])),
            "source_row": source_row,
            "children": [],
        }
        if not name and spec and last_parent is not None:
            last_parent["children"].append(component)
            continue
        if name:
            fragment["components"].append(component)
            last_parent = component
    if not fragment["components"]:
        raise ValueError("已识别电子表头，但没有解析到电子零件明细")
    if not source_is_hkd:
        warnings.append(f"电子表未标明 HKD，已按快照 RMB/HKD={decimal_text(rmb_hkd)} 将人民币单价换算为港币")
    return fragment, len(fragment["components"]), warnings


def _parse_painting(
    rows: list[list[object]],
    header_index: int,
    **_: object,
) -> tuple[dict[str, Any], int, list[str]]:
    header = rows[header_index]
    position_column = column_index(header, ("位置",))
    note_column = column_index(header, ("备注",))
    process_columns: list[tuple[str, str, int, int]] = []
    for label, key in PAINTING_PROCESSES:
        qty_column = next(
            (
                index
                for index, value in enumerate(header)
                if normalized(label) in normalized(value) and "单价" not in normalized(value)
            ),
            None,
        )
        if qty_column is not None:
            process_columns.append((label, key, qty_column, qty_column + 1))
    output: list[dict[str, Any]] = []
    warnings: list[str] = []
    for source_row, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
        position = text(value_at(row, position_column))
        if not position or re.search(r"合计|小计|总报价|[:：]$", position):
            continue
        operations = {
            key: {"quantity": "0.0000", "unit_price_hkd": "0.0000"}
            for _, key in PAINTING_PROCESSES
        }
        has_quantity = False
        for label, key, qty_column, unit_column in process_columns:
            qty = number(value_at(row, qty_column), Decimal("0")) or Decimal("0")
            unit = number(value_at(row, unit_column), Decimal("0")) or Decimal("0")
            if qty > 0:
                has_quantity = True
                if unit <= 0:
                    warnings.append(f"第 {source_row} 行 {position}/{label} 未识别单价，已按 0 预览")
            operations[key] = {
                "quantity": decimal_text(max(qty, Decimal("0"))),
                "unit_price_hkd": decimal_text(max(unit, Decimal("0"))),
            }
        if has_quantity:
            output.append(
                {
                    "item": position,
                    "operations": operations,
                    "note": text(value_at(row, note_column)),
                    "source_row": source_row,
                }
            )
    if not output:
        raise ValueError("已识别喷油表头，但没有解析到喷油工序明细")
    warnings.append("嵌入喷油图片不自动写入报价，请在对应喷油分段上传图片附件")
    return {"rows": output}, len(output), warnings


def _parse_sewing(
    rows: list[list[object]],
    header_index: int,
    **_: object,
) -> tuple[dict[str, Any], int, list[str]]:
    groups: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    columns: dict[str, int | None] | None = None
    pending_title = ""
    warnings: list[str] = []
    total_rows = 0

    for source_index, row in enumerate(rows, start=1):
        nonempty = [text(value) for value in row if text(value)]
        if row_has(row, "物料名称", "裁片部位", "用量", "价钱"):
            columns = {
                "material": column_index(row, ("物料名称",)),
                "part": column_index(row, ("裁片部位",)),
                "supplier": column_index(row, ("供应商",)),
                "usage": column_index(row, ("用量",)),
                "unit": column_index(row, ("单价", "物料价")),
                "markup": column_index(row, ("码点",)),
                "price": column_index(row, ("价钱",)),
                "note": column_index(row, ("备注",)),
            }
            name = pending_title or f"导入产品 {len(groups) + 1}"
            current = {
                "name": name,
                "category": "hair" if "发" in name else "clothes",
                "materials": [],
                "labor_rmb": "0.0000",
            }
            groups.append(current)
            pending_title = ""
            continue
        if source_index <= header_index + 1 and nonempty and len(nonempty) <= 2:
            candidate = " ".join(nonempty)
            if not re.search(r"^明细表|^DATE|日期|^20\d\d", candidate, re.I):
                pending_title = candidate
            continue
        if current is None or columns is None:
            continue
        material = text(value_at(row, columns["material"]))
        usage = number(value_at(row, columns["usage"]))
        unit = number(value_at(row, columns["unit"]))
        price = number(value_at(row, columns["price"]))
        part = text(value_at(row, columns["part"]))
        if "合计" in material:
            current = None
            columns = None
            continue
        if material and usage is None and unit is None and price is None and not part:
            if current["materials"]:
                current = {
                    "name": material,
                    "category": "hair" if "发" in material else "clothes",
                    "materials": [],
                    "labor_rmb": "0.0000",
                }
                groups.append(current)
            else:
                current["name"] = material
                current["category"] = "hair" if "发" in material else "clothes"
            continue
        if not material:
            continue
        if unit is None:
            unit = price or Decimal("0")
            warnings.append(f"第 {source_index} 行 {material} 未识别物料单价，使用价钱列或 0")
        current["materials"].append(
            {
                "item": material,
                "part": part,
                "supplier": text(value_at(row, columns["supplier"])),
                "usage": decimal_text(max(usage or Decimal("1"), Decimal("0"))),
                "unit_price_rmb": decimal_text(max(unit, Decimal("0"))),
                "markup": decimal_text(max(number(value_at(row, columns["markup"]), Decimal("1")) or Decimal("1"), Decimal("0"))),
                "note": text(value_at(row, columns["note"])),
                "source_row": source_index,
            }
        )
        total_rows += 1
    groups = [group for group in groups if group["materials"]]
    if not groups:
        raise ValueError("已识别车缝表头，但没有解析到车缝产品分组")
    return {"groups": groups}, total_rows, warnings


def _assembly_pairs(header: list[object]) -> list[tuple[int, int, str]]:
    pairs: list[tuple[int, int, str]] = []
    pending: tuple[int, str] | None = None
    for index, value in enumerate(header):
        token = text(value)
        if "工序名称" in token:
            pending = (index, token.replace("工序名称", "").strip() or "装配")
        elif "人数" in token and pending:
            pairs.append((pending[0], index, pending[1]))
            pending = None
    return pairs


def _parse_assembly(
    rows: list[list[object]],
    header_index: int,
    *,
    fallback_qty: Decimal,
    **_: object,
) -> tuple[dict[str, Any], int, list[str]]:
    groups: list[dict[str, Any]] = []
    warnings: list[str] = []
    total_rows = 0
    for name_column, people_column, group_name in _assembly_pairs(rows[header_index]):
        production_qty: Decimal | None = None
        for row in rows[header_index + 1 :]:
            label = text(value_at(row, people_column - 1))
            capacity = number(value_at(row, people_column))
            if "产能" in label and capacity and capacity > 0:
                production_qty = capacity
                break
        if production_qty is None:
            production_qty = max(fallback_qty, Decimal("1"))
            warnings.append(f"{group_name} 未识别产能，预览按报价数量 {decimal_text(production_qty)} 填入")
        processes: list[dict[str, Any]] = []
        for source_row, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
            name = text(value_at(row, name_column))
            people = number(value_at(row, people_column))
            if not name or people is None or people <= 0:
                continue
            if re.search(r"序号|工序名称|生产拉线|产品图片|客名|货号|目标数|说明|注意事项", name):
                continue
            processes.append(
                {
                    "name": name,
                    "persons": decimal_text(people),
                    "teams": "1.0000",
                    "production_qty": decimal_text(production_qty),
                    "note": text(value_at(row, people_column + 2)),
                    "source_row": source_row,
                }
            )
        if processes:
            category = "packaging" if re.search(r"包装|混装|装箱|入箱|彩盒|外箱|吸塑", group_name) else "assembly"
            groups.append({"name": group_name, "category": category, "processes": processes})
            total_rows += len(processes)
    if not groups:
        raise ValueError("已识别装配表头，但没有解析到生产排拉工序")
    return {"groups": groups}, total_rows, warnings


PARSERS: dict[str, Callable[..., tuple[dict[str, Any], int, list[str]]]] = {
    "mold": _parse_mold,
    "electronic": _parse_electronic,
    "painting": _parse_painting,
    "sewing": _parse_sewing,
    "assembly": _parse_assembly,
}


def parse_internal_quote_workbook(
    content: bytes,
    import_type: str,
    *,
    rmb_hkd: Decimal = Decimal("0.85"),
    fallback_qty: Decimal = Decimal("1"),
) -> ParsedInternalQuoteImport:
    if import_type not in IMPORT_TYPE_DEPARTMENTS:
        raise ValueError("不支持的内部报价导入类型")
    sheets = workbook_rows(content)
    sheet_name, rows, header_index = find_header(sheets, import_type)
    rows = [list(row) for row in rows]
    if header_index + 1 < len(rows):
        next_row = rows[header_index + 1]
        header_words = (
            "名称",
            "编号",
            "规格",
            "用量",
            "数量",
            "单价",
            "金额",
            "材质",
            "人数",
            "位置",
            "备注",
            "NAME",
            "MATERIAL",
            "AMOUNT",
        )
        next_text = "|".join(normalized(cell) for cell in next_row)
        hits = sum(1 for word in header_words if normalized(word) in next_text)
        numeric_cells = sum(1 for cell in next_row if number(cell) is not None)
        if hits >= 2 and numeric_cells <= 1:
            width = max(len(rows[header_index]), len(next_row))
            rows[header_index] = [
                " ".join(
                    value
                    for value in (
                        text(value_at(rows[header_index], column)),
                        text(value_at(next_row, column)),
                    )
                    if value
                )
                for column in range(width)
            ]
            rows[header_index + 1] = []
    fragment, row_count, warnings = PARSERS[import_type](
        rows,
        header_index,
        rmb_hkd=rmb_hkd,
        fallback_qty=fallback_qty,
    )
    return ParsedInternalQuoteImport(
        target_department=IMPORT_TYPE_DEPARTMENTS[import_type],
        sheet_name=sheet_name,
        header_row=header_index + 1,
        row_count=row_count,
        payload_fragment=fragment,
        warnings=warnings,
    )
