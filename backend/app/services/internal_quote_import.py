from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from io import BytesIO
from uuid import uuid4

from openpyxl import load_workbook

from app.schemas.internal_quote import InternalQuoteCostLine


IMPORT_TYPE_DEPARTMENTS = {
    "mold": "engineering",
    "electronic": "electronic",
    "sewing": "sewing",
    "assembly": "assembly",
    "painting": "painting",
}

PAINTING_PROCESSES = (
    ("夹模", "clamp"),
    ("移印", "pad"),
    ("散枪", "spray"),
    ("边模", "edge"),
    ("油色", "color"),
    ("浸油", "dip"),
    ("抹油", "oil"),
)


@dataclass
class ParsedInternalQuoteImport:
    target_department: str
    sheet_name: str
    header_row: int
    rows: list[InternalQuoteCostLine]
    parameters: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value).strip()


def normalized(value: object) -> str:
    return re.sub(r"\s+", "", text(value)).replace("（", "(").replace("）", ")").upper()


def number(value: object, default: float | None = None) -> float | None:
    if value is None or value == "":
        return default
    if isinstance(value, (int, float)):
        return float(value)
    token = re.sub(r"[^\d.\-]", "", text(value).replace(",", ""))
    if not token or token in {"-", ".", "-."}:
        return default
    try:
        return float(token)
    except ValueError:
        return default


def make_line(
    *,
    category: str,
    item_name: str,
    specification: str = "",
    quantity: float = 0,
    unit_price_hkd: float = 0,
    note: str = "",
    fields: dict[str, object] | None = None,
) -> InternalQuoteCostLine:
    return InternalQuoteCostLine(
        id=f"import-{uuid4().hex[:16]}",
        category=category[:128],
        item_name=item_name[:255],
        specification=specification[:255],
        quantity=max(float(quantity or 0), 0),
        unit_price_hkd=max(float(unit_price_hkd or 0), 0),
        amount_hkd=0,
        note=note[:500],
        fields=fields or {},
    )


def workbook_rows(content: bytes) -> list[tuple[str, list[list[object]]]]:
    try:
        workbook = load_workbook(BytesIO(content), data_only=True, read_only=True)
    except Exception as exc:
        raise ValueError("无法读取 Excel，请确认文件为有效的 xlsx/xlsm 工作簿") from exc
    sheets: list[tuple[str, list[list[object]]]] = []
    for sheet in workbook.worksheets:
        rows = [list(row) for row in sheet.iter_rows(min_row=1, max_row=min(sheet.max_row, 2000), values_only=True)]
        if any(any(text(cell) for cell in row) for row in rows):
            sheets.append((sheet.title, rows))
    workbook.close()
    if not sheets:
        raise ValueError("工作簿为空")
    return sheets


def row_has(row: list[object], *patterns: str) -> bool:
    joined = "|".join(normalized(cell) for cell in row)
    return all(any(token in joined for token in pattern.split("|")) for pattern in patterns)


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
    raise ValueError({
        "mold": "未找到模具编号/名称/价格表头",
        "electronic": "未找到零件名称/规格/用量表头",
        "sewing": "未找到物料名称/裁片部位/用量/价钱表头",
        "assembly": "未找到工序名称/人数表头",
        "painting": "未找到位置及喷油工序表头",
    }[import_type])


def column_index(header: list[object], aliases: tuple[str, ...]) -> int | None:
    normalized_aliases = tuple(normalized(alias) for alias in aliases)
    for index, value in enumerate(header):
        token = normalized(value)
        if token and any(alias in token for alias in normalized_aliases):
            return index
    return None


def value_at(row: list[object], index: int | None) -> object:
    return row[index] if index is not None and index < len(row) else None


def parse_mold(rows: list[list[object]], header_index: int) -> tuple[list[InternalQuoteCostLine], dict[str, float], list[str]]:
    header = rows[header_index]
    columns = {
        "mold_no": column_index(header, ("模号", "模具编号", "客人模具编号", "MOLD NO")),
        "name": column_index(header, ("产品名称", "零件名称", "模具名称", "加工内容", "名称")),
        "material": column_index(header, ("产品材质", "塑胶原料", "材质", "材料")),
        "weight": column_index(header, ("零件重量", "克重", "净重", "PART WEIGHT")),
        "cavity": column_index(header, ("出模数", "型腔", "模数", "CAV")),
        "sets": column_index(header, ("套数", "数量/件", "数量")),
        "price": column_index(header, ("含税模价", "总价", "模价", "TOTAL AMOUNT", "AMOUNT")),
        "machine": column_index(header, ("机型(TON)", "INJECTION MACHINE TYPE", "机型")),
        "target": column_index(header, ("模具预计日啤数", "目标数", "CYCLES/DAY")),
        "note": column_index(header, ("备注", "说明", "REMARK")),
    }
    output: list[InternalQuoteCostLine] = []
    warnings: list[str] = []
    last_mold_no = ""
    for source_row, row in enumerate(rows[header_index + 1:], start=header_index + 2):
        mold_no = text(value_at(row, columns["mold_no"])) or last_mold_no
        name = text(value_at(row, columns["name"]))
        price = number(value_at(row, columns["price"]), 0) or 0
        if mold_no:
            last_mold_no = mold_no
        joined = "".join(text(cell) for cell in row)
        if re.search(r"^(合计|小计|总计|说明|备注)", joined):
            continue
        if not mold_no and not name:
            continue
        if not name:
            name = mold_no
        if not price:
            warnings.append(f"第 {source_row} 行 {name} 未识别模具价格，已按 0 预览")
        output.append(make_line(
            category="模具",
            item_name=name,
            specification=mold_no,
            quantity=1,
            note=text(value_at(row, columns["note"])),
            fields={
                "mode": "mold",
                "mold_price_rmb": price,
                "amortization_qty": max(number(value_at(row, columns["sets"]), 1) or 1, 1),
                "material": text(value_at(row, columns["material"])),
                "weight_g": number(value_at(row, columns["weight"]), 0) or 0,
                "cavity": text(value_at(row, columns["cavity"])),
                "machine_model": text(value_at(row, columns["machine"])),
                "target": number(value_at(row, columns["target"]), 0) or 0,
                "source_row": source_row,
            },
        ))
    return output, {}, warnings


def parse_electronic(rows: list[list[object]], header_index: int) -> tuple[list[InternalQuoteCostLine], dict[str, float], list[str]]:
    header = rows[header_index]
    columns = {
        "name": column_index(header, ("零件名称",)),
        "spec": column_index(header, ("规格",)),
        "qty": column_index(header, ("用量", "数量")),
        "unit": column_index(header, ("单价",)),
        "note": column_index(header, ("备注",)),
    }
    parameters = {
        "bonding_cost_rmb": 0.0,
        "smt_cost_rmb": 0.0,
        "labor_cost_rmb": 0.0,
        "test_repair_rmb": 0.0,
        "packing_shipping_rmb": 0.0,
        "profit_pct": 0.0,
        "tax_diff_rmb": 0.0,
    }
    labels = {
        "邦定成本": "bonding_cost_rmb",
        "贴片成本": "smt_cost_rmb",
        "人工成本": "labor_cost_rmb",
        "测试费用": "test_repair_rmb",
        "包装运输": "packing_shipping_rmb",
        "抵税差额": "tax_diff_rmb",
    }
    for row in rows:
        for index, cell in enumerate(row):
            label = text(cell)
            for keyword, key in labels.items():
                if keyword in label:
                    parameters[key] = number(value_at(row, index + 1), 0) or 0
            profit = re.search(r"(\d{1,3}(?:\.\d+)?)%\s*利润", label)
            if profit:
                parameters["profit_pct"] = float(profit.group(1))

    output: list[InternalQuoteCostLine] = []
    warnings: list[str] = []
    last_parent = ""
    for source_row, row in enumerate(rows[header_index + 1:], start=header_index + 2):
        name = text(value_at(row, columns["name"]))
        spec = text(value_at(row, columns["spec"]))
        qty = number(value_at(row, columns["qty"]))
        unit = number(value_at(row, columns["unit"]))
        row_text = "|".join(text(cell) for cell in row)
        if any(keyword in row_text for keyword in (*labels, "零件成本", "含税报价", "合计成本", "报价人", "审核", "核准")):
            continue
        if name:
            last_parent = name
        elif spec and last_parent:
            name = last_parent
        if not name or (qty is None and unit is None):
            continue
        if unit is None:
            warnings.append(f"第 {source_row} 行 {name} 未识别 RMB 单价，已按 0 预览")
        output.append(make_line(
            category="电子料",
            item_name=name,
            specification=spec,
            quantity=qty if qty is not None else 1,
            note=text(value_at(row, columns["note"])),
            fields={"unit_price_rmb": unit or 0, "source_row": source_row},
        ))
    return output, parameters, warnings


def parse_sewing(rows: list[list[object]], header_index: int) -> tuple[list[InternalQuoteCostLine], dict[str, float], list[str]]:
    header = rows[header_index]
    columns = {
        "material": column_index(header, ("物料名称",)),
        "part": column_index(header, ("裁片部位",)),
        "supplier": column_index(header, ("供应商",)),
        "usage": column_index(header, ("用量",)),
        "unit": column_index(header, ("单价", "物料价")),
        "markup": column_index(header, ("码点",)),
        "price": column_index(header, ("价钱",)),
        "note": column_index(header, ("备注",)),
    }
    output: list[InternalQuoteCostLine] = []
    warnings: list[str] = []
    for source_row, row in enumerate(rows[header_index + 1:], start=header_index + 2):
        material = text(value_at(row, columns["material"]))
        usage = number(value_at(row, columns["usage"]))
        line_price = number(value_at(row, columns["price"]))
        unit = number(value_at(row, columns["unit"]))
        if "合计" in material:
            continue
        if not material and usage is None and line_price is None:
            continue
        if not material:
            continue
        if unit is None:
            unit = line_price or 0
            warnings.append(f"第 {source_row} 行 {material} 未识别物料单价，使用价钱列或 0")
        part = text(value_at(row, columns["part"]))
        supplier = text(value_at(row, columns["supplier"]))
        output.append(make_line(
            category="车缝人工" if "人工" in material else "车缝物料",
            item_name=material,
            specification=" / ".join(value for value in (part, supplier) if value),
            note=text(value_at(row, columns["note"])),
            fields={
                "usage": usage if usage is not None else 1,
                "material_price_hkd": unit,
                "markup": number(value_at(row, columns["markup"]), 1) or 1,
                "source_row": source_row,
            },
        ))
    return output, {}, warnings


def assembly_column_pairs(header: list[object]) -> list[tuple[int, int, str]]:
    pairs: list[tuple[int, int, str]] = []
    pending_name: tuple[int, str] | None = None
    for index, value in enumerate(header):
        token = text(value)
        if "工序名称" in token:
            pending_name = (index, token.replace("工序名称", "").strip() or "装配")
        elif "人数" in token and pending_name:
            pairs.append((pending_name[0], index, pending_name[1]))
            pending_name = None
    return pairs


def parse_assembly(rows: list[list[object]], header_index: int) -> tuple[list[InternalQuoteCostLine], dict[str, float], list[str]]:
    pairs = assembly_column_pairs(rows[header_index])
    output: list[InternalQuoteCostLine] = []
    warnings: list[str] = []
    for name_column, people_column, group_name in pairs:
        production_qty = 1.0
        for row in rows[header_index + 1:]:
            side_label = text(value_at(row, people_column - 1))
            capacity = number(value_at(row, people_column))
            if "产能" in side_label and capacity and capacity > 0:
                production_qty = capacity
        category = "包装" if re.search(r"包装|混装|装箱|入箱|彩盒|外箱|吸塑", group_name) else "装配"
        for source_row, row in enumerate(rows[header_index + 1:], start=header_index + 2):
            name = text(value_at(row, name_column))
            people = number(value_at(row, people_column))
            if not name or people is None or people <= 0:
                continue
            if re.search(r"序号|工序名称|生产拉线|产品图片|客名|货号|目标数|说明|注意事项", name):
                continue
            output.append(make_line(
                category=category,
                item_name=name,
                specification=group_name,
                note=text(value_at(row, people_column + 2)),
                fields={
                    "mode": "process",
                    "base_rate_hkd": 310,
                    "people_count": people,
                    "team_count": 1,
                    "production_qty": production_qty,
                    "source_row": source_row,
                },
            ))
    if any(number(row.fields.get("production_qty"), 0) == 1 for row in output):
        warnings.append("部分排拉分组未识别产能，暂按每组产量 1 预览，请确认后修改")
    return output, {}, warnings


def parse_painting(rows: list[list[object]], header_index: int) -> tuple[list[InternalQuoteCostLine], dict[str, float], list[str]]:
    header = rows[header_index]
    position_column = column_index(header, ("位置",))
    note_column = column_index(header, ("备注",))
    process_columns: list[tuple[str, int, int]] = []
    for label, _key in PAINTING_PROCESSES:
        qty_column = next((index for index, value in enumerate(header) if text(value) == label), None)
        if qty_column is not None:
            process_columns.append((label, qty_column, qty_column + 1))
    output: list[InternalQuoteCostLine] = []
    warnings: list[str] = []
    for source_row, row in enumerate(rows[header_index + 1:], start=header_index + 2):
        position = text(value_at(row, position_column))
        if not position or re.search(r"合计|小计|总报价|[:：]$", position):
            continue
        for label, qty_column, unit_column in process_columns:
            qty = number(value_at(row, qty_column), 0) or 0
            if qty <= 0:
                continue
            unit = number(value_at(row, unit_column), 0) or 0
            if not unit:
                warnings.append(f"第 {source_row} 行 {position}/{label} 未识别单价，已按 0 预览")
            output.append(make_line(
                category="二次加工",
                item_name=f"{position}-{label}",
                specification=position,
                quantity=qty,
                unit_price_hkd=unit,
                note=text(value_at(row, note_column)),
                fields={"mode": "operation", "operation": label, "source_row": source_row},
            ))
    return output, {}, warnings


PARSERS = {
    "mold": parse_mold,
    "electronic": parse_electronic,
    "sewing": parse_sewing,
    "assembly": parse_assembly,
    "painting": parse_painting,
}


def parse_internal_quote_workbook(content: bytes, import_type: str) -> ParsedInternalQuoteImport:
    if import_type not in IMPORT_TYPE_DEPARTMENTS:
        raise ValueError("不支持的内部报价导入类型")
    sheets = workbook_rows(content)
    sheet_name, rows, header_index = find_header(sheets, import_type)
    parsed_rows, parameters, warnings = PARSERS[import_type](rows, header_index)
    if not parsed_rows:
        raise ValueError("已识别表头，但没有解析到可导入的明细行")
    return ParsedInternalQuoteImport(
        target_department=IMPORT_TYPE_DEPARTMENTS[import_type],
        sheet_name=sheet_name,
        header_row=header_index + 1,
        rows=parsed_rows,
        parameters=parameters,
        warnings=warnings,
    )
