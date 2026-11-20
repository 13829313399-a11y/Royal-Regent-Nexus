from collections import Counter, defaultdict
from dataclasses import dataclass
from io import BytesIO
from math import ceil, isfinite
from unicodedata import east_asian_width

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.hyperlink import Hyperlink
from openpyxl.worksheet.worksheet import Worksheet

from app.core.time import parse_business_timestamp
from app.models.molding_sample import MoldingSampleInventoryMovement, MoldingSampleRequisition
from app.schemas.molding_sample import MoldingSampleDetailResponse, MoldingSampleItemOut
from app.services.molding_sample import (
    factory_label, normalize_material_name, parse_legacy_material_components, price_material_component,
    round_component_weight, round_money,
)
from app.services.molding_sample_excel import MATERIAL_USAGE_TYPE_LABELS, MOLD_PRESENCE_STATUS_LABELS


ORDER_COLUMNS = (
    ("啤办单号", 24), ("开单日期", 15), ("生产状态", 13), ("客户", 20), ("产品名称", 30),
    ("产品编号", 22), ("模具明细数", 15), ("来源厂区", 14), ("承接生产厂", 15),
    ("阶段", 12), ("单据类型", 14), ("填写部", 16), ("发至", 16), ("落单人", 16),
    ("审核主管", 16), ("文件编号", 21), ("系统提交时间", 23), ("派厂时间", 23),
    ("流程完成日期", 17), ("注意事项 / 开单事由", 44),
)
ITEM_COLUMNS = (
    ("啤办单号", 24), ("产品名称", 28), ("项次", 9), ("模具编号", 23), ("模具名称", 27),
    ("原料", 32), ("用料用途", 14), ("颜色 / PMS", 21), ("色粉编号", 16),
    ("啤 / 套", 12), ("啤数", 11), ("报价目标（啤/日）", 22),
    ("所需用料（kg）", 18), ("实领用料（kg）", 18), ("实际用料（kg）", 18),
    ("需办日期", 16), ("领料单号", 20), ("生产机台", 17), ("适配机型", 17),
    ("工模尺寸", 24), ("模具在厂状态", 17), ("模具回厂时间", 22), ("毛重（g）", 14),
    ("备注", 40),
)
COST_COLUMNS = (("实际料费（HKD）", 21), ("啤办费（RMB）", 20), ("啤办费（HKD）", 20))
ORDER_WEIGHT_COLUMNS = (
    ("已填实耗项数", 16), ("预计用料合计（kg）", 21), ("实领用料合计（kg）", 21), ("实际耗用合计（kg）", 21),
)
ORDER_FEE_COLUMNS = (
    ("预计料费合计（HKD）", 23), ("已存料费合计（HKD）", 23), ("啤办费合计（HKD）", 21),
    ("全单费用（HKD）", 21), ("费用齐全项数", 16),
)
MOLD_KEY = (("啤办单号", 25), ("项次", 8), ("模具编号", 19), ("模具名称", 24))
RECONCILE_WEIGHTS = MOLD_KEY + (
    ("预计用料（kg）", 18), ("回填实领（kg）", 18), ("实际耗用（kg）", 18),
)
RECONCILE_TOTALS = (("已存实际料费（HKD）", 23), ("啤办费（HKD）", 19), ("单模合计（HKD）", 20))
RECONCILE_RECEIPT = (("回填领料单号", 22), ("耗用减预计（kg）", 20), ("实领减耗用（kg）", 20))
RECONCILE_WAREHOUSE = (("领料匹配情况", 22), ("仓库领料状态", 16), ("本模申请（kg）", 19))
RECONCILE_FEES = (
    ("预计料费（HKD）", 20), ("实耗估算（HKD）", 20), ("啤办费（RMB）", 19),
    ("保存汇率（HKD/RMB）", 24), ("结算记录", 31),
)
MOLD_REFERENCE = (("产品名称", 28), ("模具明细编号", 37))
RECIPE_COLUMNS = MOLD_KEY + (
    ("用料口径", 16), ("原料名称", 35), ("原料来源", 13), ("配比", 13), ("分项重量（kg）", 19),
)
RECIPE_FEES = (("单价（HKD/lb）", 19), ("分项料费（HKD）", 20))
RECEIPT_KEY = (("啤办单号", 25), ("仓库领料单号", 24), ("模具归属", 21), ("关联项次", 13), ("关联模号", 24))
REQUISITION_COLUMNS = RECEIPT_KEY + (
    ("申请日期", 15), ("原料名称", 32), ("申请重量（kg）", 18), ("领料状态", 15),
    ("申请人", 17), ("当前出库批次", 21), ("当前出库时间", 22), ("领料备注", 42),
)
MOVEMENT_COLUMNS = RECEIPT_KEY + (
    ("发生时间", 22), ("业务动作", 16), ("批次号", 21), ("原料名称", 32),
    ("库存变动（kg）", 19), ("操作人", 17), ("原因", 38),
)
QUEUE_LABELS = {"待生产": "待接单", "生产中": "生产中", "已完成": "已回传"}

HEADER_FONT = Font(name="Microsoft YaHei", bold=True, color="FFFFFF", size=10)
TEXT_ALIGNMENT = Alignment(horizontal="left", vertical="center", wrap_text=True, indent=1)
NUMBER_ALIGNMENT = Alignment(horizontal="right", vertical="center", indent=1)
BAND_FILL = PatternFill("solid", fgColor="EFF6F7")
LINK_FONT = Font(name="Microsoft YaHei", color="096A75", underline="single")


@dataclass(frozen=True)
class MaterialLine:
    basis: str
    material: str
    source: str
    ratio: float | None
    weight: float | None
    unit_price: float | None
    amount: float | None
    note: str


def _complete_total(values, rounding=round_money):
    """Preserve missing values and genuine zeroes in a total."""
    values = list(values)
    if not values or any(value is None for value in values):
        return None
    return rounding(sum(values))


def _material_lines(item: MoldingSampleItemOut, prices: dict[str, float], can_view_cost: bool) -> list[MaterialLine]:
    if item.material_components:
        recipe = [component.model_dump() for component in item.material_components]
        recipe_source = "开单配方"
    else:
        recipe = parse_legacy_material_components(item.material)
        recipe_source = "原单原料栏"
        if recipe == [] and item.material.strip():
            recipe = [{"material": item.material.strip(), "source_type": "virgin", "ratio_percent": 100.0}]

    snapshot = item.actual_material_cost_components if can_view_cost else []
    valid_snapshot = bool(snapshot) and abs(sum(part.ratio_percent for part in snapshot) - 100) <= 0.01 and all(
        part.material.strip() and part.ratio_percent > 0 and part.unit_price > 0 and part.weight_kg >= 0
        and part.amount_hkd >= 0 and all(isfinite(n) for n in (part.ratio_percent, part.unit_price, part.weight_kg, part.amount_hkd))
        for part in snapshot
    )
    bases = [("计划用料", item.required_material_kg)]
    if not valid_snapshot and item.actual_weight_kg is not None:
        bases.append(("实耗按配比", item.actual_weight_kg))

    lines = []
    for basis, total_weight in bases:
        if not recipe:
            if item.material.strip():
                lines.append(MaterialLine(basis, item.material, "", None, None, None, None, "原单配比无法拆分"))
            continue
        for part in recipe:
            material, ratio = part["material"], part["ratio_percent"]
            unit_price = prices.get(normalize_material_name(material)) if can_view_cost else None
            weight, amount = price_material_component(total_weight, ratio, unit_price)
            source = "水口料" if part["source_type"] == "runner" else "原料"
            note = recipe_source
            if can_view_cost:
                note += " · 导出时原料价" if unit_price is not None else " · 缺当前原料价"
            lines.append(MaterialLine(basis, material, source, ratio / 100, weight, unit_price, amount, note))
    if valid_snapshot:
        for part in snapshot:
            source = "水口料" if part.source_type == "runner" else "原料"
            lines.append(MaterialLine(
                "已存结算", part.material, source, part.ratio_percent / 100, part.weight_kg,
                part.unit_price, part.amount_hkd, "保存结算时的配比、重量及单价",
            ))
    return lines


@dataclass(frozen=True)
class MoldFees:
    expected: float | None
    actual_estimate: float | None
    saved: float | None
    total: float | None
    note: str


def _mold_fees(item: MoldingSampleItemOut, lines: list[MaterialLine]) -> MoldFees:
    expected = _complete_total(line.amount for line in lines if line.basis == "计划用料")
    estimate = _complete_total(line.amount for line in lines if line.basis == "实耗按配比")
    saved_parts = _complete_total(line.amount for line in lines if line.basis == "已存结算")
    saved = item.actual_amount_hkd if item.actual_amount_hkd is not None else saved_parts
    if saved_parts is not None:
        note = "已存结算分项"
    elif saved is not None:
        note = "历史仅存料费合计"
    else:
        note = "未存实际料费"
    if item.injection_cost_hkd is None:
        note += " · 缺港币啤办费"
    return MoldFees(expected, estimate, saved, _complete_total((saved, item.injection_cost_hkd)), note)


def _excel_date(value: str):
    timestamp = parse_business_timestamp(value)
    if timestamp is None:
        return value or None
    if len(value.strip()) == 10:
        return timestamp.date()
    return timestamp.replace(tzinfo=None)


def _prepare_sheet(sheet: Worksheet, columns: tuple, title: str, subtitle: str, color: str, freeze_panes: str = "B4"):
    fill = PatternFill("solid", fgColor=color)
    for row, value in ((1, title), (2, subtitle)):
        sheet.merge_cells(start_row=row, start_column=1, end_row=row, end_column=8)
        cell = sheet.cell(row, 1, value)
        cell.font = Font(name="Microsoft YaHei", size=15 if row == 1 else 10,
                         bold=row == 1, color=color)
        cell.alignment = Alignment(vertical="center")
    for index, (label, width) in enumerate(columns, start=1):
        cell = sheet.cell(3, index, label)
        cell.font = HEADER_FONT
        cell.fill = PatternFill("solid", fgColor="274765") if "HKD" in label or "RMB" in label else fill
        cell.alignment = Alignment(vertical="center", horizontal="left", indent=1)
        sheet.column_dimensions[get_column_letter(index)].width = width
    sheet.row_dimensions[1].height = 32
    sheet.row_dimensions[2].height = 23
    sheet.row_dimensions[3].height = 26
    sheet.sheet_format.defaultRowHeight = 22
    sheet.freeze_panes = freeze_panes
    sheet.sheet_view.showGridLines = False
    sheet.sheet_properties.tabColor = color
    sheet.print_title_rows = "1:3"
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.paperSize = sheet.PAPERSIZE_A3
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_setup.fitToWidth = 2 if len(columns) > 18 else 1
    sheet.page_setup.fitToHeight = 0
    sheet.print_title_cols = "A:A"


def _write_row(sheet: Worksheet, row: int, values: tuple, shaded: bool):
    lines = 1
    for index, value in enumerate(values, start=1):
        if isinstance(value, str):
            value = ILLEGAL_CHARACTERS_RE.sub("", value)
        cell = sheet.cell(row, index, value)
        if isinstance(value, str):
            # Business identifiers, notes and names must remain literal in Excel.
            cell.data_type = "s"
            cell.number_format = "@"
            cell.alignment = TEXT_ALIGNMENT
            width = sheet.column_dimensions[cell.column_letter].width - 2
            if len(value) * 2 > width or "\n" in value:
                wrapped_lines = 0
                for part in value.split("\n"):
                    text_width = sum(2 if east_asian_width(char) in {"W", "F"} else 1 for char in part)
                    wrapped_lines += max(1, ceil(text_width / width))
                lines = max(lines, wrapped_lines)
        else:
            cell.alignment = NUMBER_ALIGNMENT
            if isinstance(value, (float, int)):
                header = sheet.cell(3, index).value
                if header == "配比":
                    cell.number_format = "0.00%"
                elif header.endswith(("（HKD/lb）", "（HKD/RMB）")):
                    cell.number_format = "#,##0.00######"
                elif header.endswith(("（HKD）", "（RMB）")):
                    cell.number_format = "#,##0.00"
                elif header.endswith(("（kg）", "（g）")):
                    cell.number_format = "#,##0.00##"
        if shaded:
            cell.fill = BAND_FILL
    if lines > 1:
        sheet.row_dimensions[row].height = min(400, lines * 16 + 5)


def _link(cell, target: Worksheet, row: int):
    cell.hyperlink = Hyperlink(ref=cell.coordinate, location=f"'{target.title}'!A{row}")
    cell.font = LINK_FONT


@dataclass(frozen=True)
class ReceiptMatch:
    row: int
    allocation: str
    status: str
    mold_requested: float | None
    mold_issued: float | None


def _write_warehouse_sheets(workbook, scope, requisitions, movements, by_receipt):
    if requisitions is None:
        return {}
    warehouse = workbook.create_sheet("领料记录")
    columns = REQUISITION_COLUMNS + ((("流水净出库（kg）", 21),) if movements is not None else ())
    _prepare_sheet(warehouse, columns, f"仓库领料记录　{scope}",
                   f"共 {len(requisitions)} 张领料单　每张单列一次，同单同领料号才关联到模具。", "73542C", "C4")
    by_requisition = defaultdict(list)
    movement_row = 4
    if movements is not None:
        ledger = workbook.create_sheet("出库流水")
        _prepare_sheet(ledger, MOVEMENT_COLUMNS, f"出库与撤回流水　{scope}",
                       f"共 {len(movements)} 笔　库存扣减为负，撤回出库为正。", "73542C", "C4")
        for movement in movements:
            by_requisition[movement.requisition_id].append(movement)

    matches = {}
    for row, req in enumerate(requisitions, start=4):
        items = by_receipt.get((req.order_id, req.req_number), [])
        allocation = "已关联模具" if len(items) == 1 else ("多模共用，未分摊" if items else "仅关联到啤办单")
        key = (req.order_id, req.req_number, allocation, "、".join(str(item.sort_order) for item in items),
               "、".join(item.mold_id for item in items if item.mold_id))
        group = by_requisition[req.id]
        values = (*key, _excel_date(req.date), req.material, req.requested_weight_kg, req.status,
                  req.applicant, req.inventory_batch_no, _excel_date(req.issued_at), req.notes)
        net = round_component_weight(-sum(movement.quantity_kg for movement in group)) if group else None
        if movements is not None:
            values += (net,)
        _write_row(warehouse, row, values, row % 2 != 0)
        matches[(req.order_id, req.req_number)] = ReceiptMatch(
            row, allocation, req.status, req.requested_weight_kg if len(items) == 1 else None,
            net if len(items) == 1 else None,
        )
        for movement in group:
            _write_row(ledger, movement_row, (
                *key, _excel_date(movement.created_at), movement.movement_type, movement.batch_no,
                movement.material, movement.quantity_kg, movement.actor_name, movement.reason,
            ), row % 2 != 0)
            _link(ledger.cell(movement_row, 2), warehouse, row)
            movement_row += 1
    return matches


def build_production_month_workbook(
    records: list[MoldingSampleDetailResponse], factory: str, month: str, *,
    prices: dict[str, float] | None = None, requisitions: list[MoldingSampleRequisition] | None = None,
    movements: list[MoldingSampleInventoryMovement] | None = None,
) -> bytes:
    workbook = Workbook()
    summary = workbook.active
    summary.title = "单据汇总"
    reconcile = workbook.create_sheet("逐模对账")
    recipe = workbook.create_sheet("配料明细")
    item_count = sum(len(record.items) for record in records)
    statuses = Counter(record.order.status for record in records)
    scope = f"{factory} · {month} · 按业务开单日期"
    counts = "　".join(f"{label} {statuses[status]} 张" for status, label in QUEUE_LABELS.items())
    show_cost = any(record.can_view_cost for record in records)
    summary_columns = ORDER_COLUMNS + ORDER_WEIGHT_COLUMNS + (ORDER_FEE_COLUMNS if show_cost else ())
    _prepare_sheet(summary, summary_columns, f"啤办单汇总　{scope}",
                   f"共 {len(records)} 张　{counts}　各项合计在本单对应明细填齐后显示。", "17385E")
    totals_columns = RECONCILE_TOTALS if show_cost else ()
    warehouse_columns = RECONCILE_WAREHOUSE if requisitions is not None else ()
    if movements is not None and requisitions is not None:
        warehouse_columns += (("本模净出库（kg）", 20),)
    reconcile_columns = (RECONCILE_WEIGHTS + totals_columns + RECONCILE_RECEIPT + warehouse_columns
                         + (RECONCILE_FEES if show_cost else ()) + (("原单原料", 36), ("用料用途", 15)) + MOLD_REFERENCE)
    receipt_column = len(RECONCILE_WEIGHTS) + len(totals_columns) + 1
    _prepare_sheet(reconcile, reconcile_columns, f"逐模用料与领料对账　{scope}",
                   f"共 {item_count} 项模具　点击有下划线的模号查看配料。重量空白表示未填。"
                   + ("单模合计为已存港币料费与港币啤办费之和。" if show_cost else ""), "135E69", "E4")
    recipe_columns = RECIPE_COLUMNS + (RECIPE_FEES if show_cost else ()) + (("数据来源", 38),) + MOLD_REFERENCE
    _prepare_sheet(recipe, recipe_columns, f"逐模配料明细　{scope}",
                   "按模具、用料口径和原料成分逐行列示。"
                   + ("计划和实耗估算采用导出时原料价，已存结算采用保存时的数据。" if show_cost else ""), "0F766E", "E4")
    for sheet in (reconcile, recipe):
        sheet.sheet_view.zoomScale = 85
    by_receipt = defaultdict(list)
    for record in records:
        for item in sorted(record.items, key=lambda item: (item.sort_order, item.id)):
            if item.receipt_no.strip():
                by_receipt[(record.order.id, item.receipt_no.strip())].append(item)
    receipt_matches = _write_warehouse_sheets(workbook, scope, requisitions, movements, by_receipt)
    details = workbook.create_sheet("模具明细")
    detail_columns = ITEM_COLUMNS + (COST_COLUMNS if show_cost else ())
    _prepare_sheet(details, detail_columns, f"模具明细　{scope}", f"{len(records)} 张啤办单　共 {item_count} 项明细", "0F766E")
    workbook.active = reconcile
    prices = prices or {}

    detail_row = 4
    recipe_row = 4
    for row, record in enumerate(records, start=4):
        order = record.order
        shaded = row % 2 != 0
        first_detail_row = detail_row
        order_fees = []
        for item in sorted(record.items, key=lambda item: (item.sort_order, item.id)):
            mold_key = (order.id, item.sort_order, item.mold_id, item.mold_name)
            reference = (order.product_name, item.id)
            lines = _material_lines(item, prices, record.can_view_cost)
            first_recipe_row = recipe_row
            for line in lines:
                values = (*mold_key, line.basis, line.material, line.source, line.ratio, line.weight)
                if show_cost:
                    values += (line.unit_price, line.amount) if record.can_view_cost else (None, None)
                _write_row(recipe, recipe_row, (*values, line.note, *reference), shaded)
                recipe_row += 1

            actual, planned, collected = item.actual_weight_kg, item.required_material_kg, item.collected_weight_kg
            vs_plan = round_component_weight(actual - planned) if actual is not None and planned is not None else None
            vs_collected = round_component_weight(collected - actual) if actual is not None and collected is not None else None
            totals, fee_fields = (), ()
            if record.can_view_cost:
                fees = _mold_fees(item, lines)
                order_fees.append(fees)
                totals = (fees.saved, item.injection_cost_hkd, fees.total)
                fee_fields = (fees.expected, fees.actual_estimate, item.injection_cost, item.exchange_rate_at_save, fees.note)
            elif show_cost:
                totals = (None,) * len(RECONCILE_TOTALS)
                fee_fields = (None,) * (len(RECONCILE_FEES) - 1) + ("无成本权限",)
            match = receipt_matches.get((order.id, item.receipt_no.strip()))
            warehouse_fields = ()
            if requisitions is not None:
                if match:
                    warehouse_fields = (match.allocation, match.status, match.mold_requested)
                else:
                    warehouse_fields = ("回填单号未匹配" if item.receipt_no.strip() else "未关联到本模", None, None)
                if movements is not None:
                    warehouse_fields += (match.mold_issued if match else None,)
            _write_row(reconcile, detail_row, (
                *mold_key, planned, collected, actual, *totals, item.receipt_no, vs_plan, vs_collected,
                *warehouse_fields, *fee_fields, item.material, MATERIAL_USAGE_TYPE_LABELS[item.material_usage_type], *reference,
            ), shaded)
            if lines and item.mold_id:
                _link(reconcile.cell(detail_row, 3), recipe, first_recipe_row)
            if match:
                _link(reconcile.cell(detail_row, receipt_column), workbook["领料记录"], match.row)

            values = (
                order.id, order.product_name, item.sort_order, item.mold_id, item.mold_name,
                item.material, MATERIAL_USAGE_TYPE_LABELS[item.material_usage_type], item.color,
                item.pigment_no, item.quantity, item.shoot_qty, item.quote_target_daily_qty,
                item.required_material_kg, item.collected_weight_kg, item.actual_weight_kg,
                _excel_date(item.completion_time), item.receipt_no, item.production_machine,
                item.machine_type, item.mold_dimensions, MOLD_PRESENCE_STATUS_LABELS[item.mold_presence_status],
                _excel_date(item.mold_return_time), item.gross_weight_g, item.notes,
            )
            if show_cost:
                costs = (item.actual_amount_hkd, item.injection_cost, item.injection_cost_hkd)
                values += costs if record.can_view_cost else ("无成本权限", None, None)
            _write_row(details, detail_row, values, shaded)
            detail_row += 1

        values = (
            order.id, _excel_date(order.date), QUEUE_LABELS[order.status], order.client_name,
            order.product_name, order.order_number, len(record.items), factory_label(order.factory_id),
            factory, order.stage, order.order_type, order.workshop, order.send_to, order.eng_name,
            order.supervisor, order.doc_number, _excel_date(order.created_at),
            _excel_date(order.production_assigned_at), _excel_date(order.completed_date), order.reason,
            sum(item.actual_weight_kg is not None for item in record.items),
            _complete_total((item.required_material_kg for item in record.items), round_component_weight),
            _complete_total((item.collected_weight_kg for item in record.items), round_component_weight),
            _complete_total((item.actual_weight_kg for item in record.items), round_component_weight),
        )
        if show_cost and record.can_view_cost:
            values += (_complete_total(fees.expected for fees in order_fees), _complete_total(fees.saved for fees in order_fees),
                       _complete_total(item.injection_cost_hkd for item in record.items),
                       _complete_total(fees.total for fees in order_fees), sum(fees.total is not None for fees in order_fees))
        elif show_cost:
            values += (None,) * len(ORDER_FEE_COLUMNS)
        _write_row(summary, row, values, shaded)
        if record.items:
            _link(summary.cell(row, 1), reconcile, first_detail_row)

    for sheet in workbook:
        sheet.auto_filter.ref = f"A3:{get_column_letter(sheet.max_column)}{sheet.max_row}"
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()
