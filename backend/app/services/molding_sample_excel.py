from __future__ import annotations

import re
from datetime import UTC, datetime
from datetime import timedelta
from io import BytesIO
from xml.etree import ElementTree
from zipfile import ZIP_DEFLATED, ZipFile

from app.models.molding_sample import MoldingSampleMaterialPrice, MoldingSampleOrder
from app.schemas.molding_sample import MoldingSampleCreateRequest, MoldingSampleItemIn, MoldingSampleOrderIn
from app.services.molding_sample import (
    calculate_material_amount_hkd,
    canonical_material_display,
    parse_legacy_material_components,
)

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
SHEET_NAME = "啤办单"
TEMPLATE_TITLE = "啤办单导入导出"
NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

ORDER_FIELDS = [
    ("单据ID", "id"),
    ("工厂ID", "factory_id"),
    ("订单号", "order_number"),
    ("文件编号", "doc_number"),
    ("产品名称", "product_name"),
    ("客户", "client_name"),
    ("日期", "date"),
    ("阶段", "stage"),
    ("单据类型", "order_type"),
    ("车间", "workshop"),
    ("发往", "send_to"),
    ("主管", "supervisor"),
    ("工程师", "eng_name"),
    ("原因", "reason"),
]

ITEM_COLUMNS = [
    ("明细ID", "id"),
    ("排序", "sort_order"),
    ("模具编号", "mold_id"),
    ("模具名称", "mold_name"),
    ("工模尺寸", "mold_dimensions"),
    ("适配机型", "machine_type"),
    ("模具是否在厂", "mold_presence_status"),
    ("原料", "material"),
    ("颜色", "color"),
    ("色粉编号", "pigment_no"),
    ("数量", "quantity"),
    ("啤数", "shoot_qty"),
    ("毛重g", "gross_weight_g"),
    ("需料kg", "required_material_kg"),
    ("预计料费HKD", "expected_amount_hkd"),
    ("模具回厂时间", "mold_return_time"),
    ("完成时间", "completion_time"),
    ("用料用途", "material_usage_type"),
    ("备注", "notes"),
    ("领料单号", "receipt_no"),
    ("领料kg", "collected_weight_kg"),
    ("实际用料kg", "actual_weight_kg"),
    ("料费HKD", "actual_amount_hkd"),
    ("啤办费RMB", "injection_cost"),
    ("啤办费HKD", "injection_cost_hkd"),
    ("保存汇率", "exchange_rate_at_save"),
]

# The engineering import sheet intentionally mirrors only the editable fields in
# the current "新建啤办单" screen.  Keep this separate from ITEM_COLUMNS: the
# latter is the full formal-order export contract and includes production
# fillback, calculated cost, and historical compatibility fields.
ENGINEERING_IMPORT_COLUMNS = [
    ("模具编号", "mold_id"),
    ("模具名称", "mold_name"),
    ("所需用料", "material"),
    ("颜色", "color"),
    ("PMS", "pms"),
    ("色粉", "pigment_no"),
    ("啤/套", "quantity"),
    ("啤数", "shoot_qty"),
    ("所需用料(kg)", "required_material_kg"),
    ("需办日期", "required_date"),
    ("工模尺寸", "mold_dimensions"),
    ("模具状态（是否在厂）", "mold_presence_status"),
    ("用料用途", "material_usage_type"),
    ("备注", "notes"),
]

ENGINEERING_IMPORT_COLUMN_WIDTHS = [14, 22, 24, 14, 14, 14, 11, 11, 16, 16, 18, 18, 14, 30]

BATCH_ORDER_COLUMNS = [
    ("单据ID", "id"),
    ("工厂ID", "factory_id"),
    ("订单号", "order_number"),
    ("文件编号", "doc_number"),
    ("产品名称", "product_name"),
    ("客户", "client_name"),
    ("日期", "date"),
    ("阶段", "stage"),
    ("单据类型", "order_type"),
    ("车间", "workshop"),
    ("发往", "send_to"),
    ("主管", "supervisor"),
    ("工程师", "eng_name"),
    ("原因", "reason"),
    ("状态", "status"),
    ("驳回原因", "reject_reason"),
    ("完成日期", "completed_date"),
    ("更新时间", "updated_at"),
]

BATCH_EXPORT_COLUMNS = BATCH_ORDER_COLUMNS + ITEM_COLUMNS

ORDER_ALIASES = {
    "单据id": "id",
    "单据ID": "id",
    "工厂ID": "factory_id",
    "工厂id": "factory_id",
    "订单号": "order_number",
    "产品编号": "order_number",
    "文件编号": "doc_number",
    "订单编号": "doc_number",
    "产品名称": "product_name",
    "客户": "client_name",
    "客户名称": "client_name",
    "日期": "date",
    "开单日期": "date",
    "落单日期": "date",
    "阶段": "stage",
    "单据类型": "order_type",
    "车间": "workshop",
    "填写部": "workshop",
    "发往": "send_to",
    "发至": "send_to",
    "主管": "supervisor",
    "审核主管": "supervisor",
    "工程师": "eng_name",
    "工程": "eng_name",
    "落单人": "eng_name",
    "开单人": "eng_name",
    "原因": "reason",
    "备注": "reason",
    "注意事项": "reason",
    "开单事由": "reason",
}

ITEM_ALIASES = {
    label: field for label, field in ITEM_COLUMNS
}
ITEM_ALIASES.update(
    {
        "id": "id",
        "模号": "mold_id",
        "模具": "mold_name",
        "客模具编号": "mold_id",
        "机型": "machine_type",
        "机型/吨位": "machine_type",
        "模具是否在厂": "mold_presence_status",
        "模具在厂状态": "mold_presence_status",
        "模具状态（是否在厂）": "mold_presence_status",
        "模具状态(是否在厂)": "mold_presence_status",
        "材料": "material",
        "用料": "material",
        "所需用料": "material",
        "所需颜色": "color",
        "PMS": "pms",
        "色粉": "pigment_no",
        "色粉编号": "pigment_no",
        "套/啤": "quantity",
        "啤/套": "quantity",
        "啤数/模数": "shoot_qty",
        "啤办数（啤）": "shoot_qty",
        "啤办数(啤)": "shoot_qty",
        "毛重": "gross_weight_g",
        "需料": "required_material_kg",
        "需料KG": "required_material_kg",
        "所需用料(kg)": "required_material_kg",
        "所需用料（kg）": "required_material_kg",
        "所需用料kg": "required_material_kg",
        "用料重量（KG)": "required_material_kg",
        "用料重量(KG)": "required_material_kg",
        "用料重量kg": "required_material_kg",
        "用途": "material_usage_type",
        "用料类型": "material_usage_type",
        "回模时间": "mold_return_time",
        "报价周期": "quote_cycle",
        "需办日期": "required_date",
        "要求": "requirement",
        "领料KG": "collected_weight_kg",
        "实际用料KG": "actual_weight_kg",
        "啤办费": "injection_cost",
    }
)

NUMERIC_ITEM_FIELDS = {
    "gross_weight_g",
    "required_material_kg",
    "expected_amount_hkd",
    "collected_weight_kg",
    "actual_weight_kg",
    "actual_amount_hkd",
    "injection_cost",
    "injection_cost_hkd",
    "exchange_rate_at_save",
}

MOLD_PRESENCE_STATUS_LABELS = {
    "unknown": "待确认",
    "in_factory": "在厂",
    "out_of_factory": "不在厂",
}

MATERIAL_USAGE_TYPE_LABELS = {
    "production": "正式生产",
    "trial": "试料",
}

DETAIL_HEADER_ROW_INDEX = 10
TITLE_STYLE_ID = 1
ORDER_LABEL_STYLE_ID = 2
ORDER_VALUE_STYLE_ID = 3
DETAIL_HEADER_STYLE_ID = 4
DETAIL_BODY_STYLE_ID = 5
MISSING_VALUE_STYLE_ID = 6
SUBTOTAL_STYLE_ID = 7
TOTAL_STYLE_ID = 8
BATCH_ORDER_HEADER_STYLE_ID = 9
BATCH_ITEM_HEADER_STYLE_ID = 10
BATCH_ORDER_GROUP_A_STYLE_ID = 11
BATCH_ORDER_GROUP_B_STYLE_ID = 12

FILLBACK_REQUIRED_FIELDS = {
    "actual_weight_kg",
    "actual_amount_hkd",
    "injection_cost",
    "injection_cost_hkd",
}

ITEM_COLUMN_WIDTHS = [
    22,
    24,
    20,
    30,
    20,
    14,
    14,
    22,
    18,
    15,
    11,
    11,
    12,
    12,
    14,
    15,
    15,
    14,
    30,
    18,
    12,
    14,
    14,
    14,
    14,
    12,
]

BATCH_COLUMN_WIDTHS = [
    22,
    14,
    16,
    18,
    24,
    18,
    14,
    10,
    12,
    14,
    14,
    18,
    18,
    30,
    12,
    24,
    14,
    18,
    22,
    10,
    18,
    22,
    20,
    14,
    14,
    22,
    18,
    15,
    11,
    11,
    12,
    12,
    14,
    15,
    15,
    14,
    30,
    18,
    12,
    14,
    14,
    14,
    14,
    12,
]


def export_order_to_excel(
    order: MoldingSampleOrder,
    material_prices: list[MoldingSampleMaterialPrice] | None = None,
) -> bytes:
    last_column = _column_name(len(ITEM_COLUMNS))
    actual_weight_column_index = _field_column_index("actual_weight_kg")
    actual_amount_column_index = _field_column_index("actual_amount_hkd")
    total_label_end_column = _column_name(actual_amount_column_index - 1)
    total_amount_start_column = _column_name(actual_amount_column_index)
    title = f"啤办单 · {_safe_text(order.product_name)}（{order.id}） · {_safe_text(order.status)}"
    rows: list[list[object | None]] = [
        [title],
        [
            "单据ID",
            order.id,
            "产品 / 客户",
            f"{_safe_text(order.product_name)} / {_safe_text(order.client_name)}",
            "阶段 / 车间",
            f"{_safe_text(order.stage)} / {_safe_text(order.workshop)}（{_safe_text(order.send_to, '内部')}）",
        ],
        [
            "工程 / 主管",
            f"{_safe_text(order.eng_name)} / {_safe_text(order.supervisor)}",
            "开单日期",
            _safe_text(order.date),
            "开单事由",
            _safe_text(order.reason),
        ],
        [],
        [label for label, _ in ITEM_COLUMNS],
    ]
    style_matrix: dict[tuple[int, int], int] = {}
    missing_count = 0

    for item in order.items:
        row: list[object | None] = []
        row_index = len(rows) + 1
        for column_index, (_, field) in enumerate(ITEM_COLUMNS, start=1):
            value = _get_export_item_value(item, field, material_prices)
            formatted_value, is_missing = _format_export_item_value(field, value)
            row.append(formatted_value)
            if is_missing:
                style_matrix[(row_index, column_index)] = MISSING_VALUE_STYLE_ID
                missing_count += 1
        rows.append(row)

    subtotal = _build_single_export_subtotal_row(order)
    subtotal_row_index = len(rows) + 1
    rows.append(subtotal)
    total_row_index = len(rows) + 1
    rows.append(_build_single_export_total_row(order, missing_count))

    for column_index in range(1, len(ITEM_COLUMNS) + 1):
        style_matrix[(subtotal_row_index, column_index)] = SUBTOTAL_STYLE_ID
        style_matrix[(total_row_index, column_index)] = TOTAL_STYLE_ID

    return _build_workbook(
        _sheet_xml(
            rows,
            header_row_index=5,
            style_matrix=style_matrix,
            merge_ranges=[
                f"A1:{last_column}1",
                f"F2:{last_column}2",
                f"F3:{last_column}3",
                f"A{subtotal_row_index}:{_column_name(actual_weight_column_index - 1)}{subtotal_row_index}",
                f"A{total_row_index}:{total_label_end_column}{total_row_index}",
                f"{total_amount_start_column}{total_row_index}:{last_column}{total_row_index}",
            ],
        ),
    )


def export_orders_to_excel(
    orders: list[MoldingSampleOrder],
    material_prices: list[MoldingSampleMaterialPrice] | None = None,
) -> bytes:
    date_values = sorted({str(order.date or "").strip() for order in orders if str(order.date or "").strip()})
    date_range = ""
    if len(date_values) == 1:
        date_range = f" · {date_values[0]}"
    elif len(date_values) > 1:
        date_range = f" · {date_values[0]} ~ {date_values[-1]}"

    rows: list[list[object | None]] = [
        [f"啤办单批量导出 · {len(orders)} 张{date_range}"],
        [label for label, _ in BATCH_EXPORT_COLUMNS],
    ]
    style_matrix: dict[tuple[int, int], int] = {}
    merge_ranges = [f"A1:{_column_name(len(BATCH_EXPORT_COLUMNS))}1"]

    for column_index in range(1, len(BATCH_EXPORT_COLUMNS) + 1):
        style_matrix[(2, column_index)] = (
            BATCH_ORDER_HEADER_STYLE_ID
            if column_index <= len(BATCH_ORDER_COLUMNS)
            else BATCH_ITEM_HEADER_STYLE_ID
        )

    for order_index, order in enumerate(orders):
        order_values = [getattr(order, field, "") for _, field in BATCH_ORDER_COLUMNS]
        items = list(order.items)
        group_style = BATCH_ORDER_GROUP_A_STYLE_ID if order_index % 2 == 0 else BATCH_ORDER_GROUP_B_STYLE_ID
        first_row_index = len(rows) + 1

        if not items:
            rows.append(order_values + ["" for _ in ITEM_COLUMNS])
            for column_index in range(1, len(BATCH_ORDER_COLUMNS) + 1):
                style_matrix[(len(rows), column_index)] = group_style
            continue

        for item_index, item in enumerate(items):
            current_order_values = order_values if item_index == 0 else ["" for _ in BATCH_ORDER_COLUMNS]
            row_index = len(rows) + 1
            rows.append(
                current_order_values
                + [
                    _format_export_item_value(field, _get_export_item_value(item, field, material_prices))[0]
                    for _, field in ITEM_COLUMNS
                ],
            )
            for column_index in range(1, len(BATCH_ORDER_COLUMNS) + 1):
                style_matrix[(row_index, column_index)] = group_style

        last_row_index = len(rows)
        if last_row_index > first_row_index:
            for column_index in range(1, len(BATCH_ORDER_COLUMNS) + 1):
                column_name = _column_name(column_index)
                merge_ranges.append(f"{column_name}{first_row_index}:{column_name}{last_row_index}")

    return _build_workbook(
        _sheet_xml(
            rows,
            column_widths=BATCH_COLUMN_WIDTHS,
            header_row_index=2,
            style_matrix=style_matrix,
            merge_ranges=merge_ranges,
        ),
    )


def build_engineering_import_template() -> bytes:
    """Build the engineering-facing import workbook from the current entry fields.

    No formula is used for required material: engineers enter ``所需用料(kg)``
    directly, matching the current manual form.
    """

    last_column = _column_name(len(ENGINEERING_IMPORT_COLUMNS))
    detail_start_row = 9
    detail_end_row = detail_start_row + 30 - 1
    rows: list[list[object | None]] = [
        ["工程部啤办通知单 · 基础资料与模具明细导入模板"],
        ["客户", "", "产品编号", "", "产品名称", ""],
        ["开单日期", "", "阶段", "T0", "填写部", "工程部"],
        ["发至", "内部", "审核主管", "", "落单人", ""],
        ["注意事项", ""],
        ["填写说明：基础资料填在上方；每一行代表一项模具明细；多原料请按“比例%原料 + 比例%原料水口料”填写；完整规则和例子请查看“填写说明”工作表。"],
        [],
        [label for label, _ in ENGINEERING_IMPORT_COLUMNS],
        *[["" for _ in ENGINEERING_IMPORT_COLUMNS] for _ in range(30)],
    ]
    style_matrix: dict[tuple[int, int], int] = {}
    for column_index in range(1, len(ENGINEERING_IMPORT_COLUMNS) + 1):
        style_matrix[(8, column_index)] = DETAIL_HEADER_STYLE_ID
        for row_index in range(detail_start_row, detail_end_row + 1):
            style_matrix[(row_index, column_index)] = DETAIL_BODY_STYLE_ID

    guide_rows: list[list[object | None]] = [
        ["工程部啤办单导入模板 · 填写说明与字段映射"],
        ["区域", "表格字段", "填写方式 / 字段映射", "业务规则与例子"],
        ["基础资料", "客户", "填写在 B2", "对应新建啤办单的“客户”"],
        ["基础资料", "产品编号", "填写在 D2", "对应新建啤办单的“产品编号”"],
        ["基础资料", "产品名称", "填写在 F2", "对应新建啤办单的“产品名称”"],
        ["基础资料", "开单日期", "填写在 B3", "建议使用 YYYY-MM-DD；系统也兼容 YYYY/MM/DD"],
        ["基础资料", "阶段 / 填写部", "填写在 D3 / F3", "默认阶段 T0、填写部 工程部"],
        ["基础资料", "发至 / 审核主管 / 落单人", "填写在 B4 / D4 / F4", "分别映射新建单的发至、审核主管、落单人"],
        ["基础资料", "注意事项", "填写在 B5", "映射新建单的注意事项 / 开单事由"],
        ["模具明细", "模具编号、模具名称", "每个模具占一行", "第 9 至 38 行可直接填写，共预留 30 行"],
        ["模具明细", "所需用料", "填写单一原料名称，或在同一格填写完整比例组成", "单料例：ABS PA-757"],
        ["多原料", "同一种原料 + 水口料", "例：80%ABS PA-757 + 20%ABS PA-757水口料", "10kg 表示 8kg 原料 + 2kg 同料水口；同一种原料均按 ABS PA-757 价格计算"],
        ["多原料", "同料水口简写", "也可写：80%ABS PA-757 + 20%水口料", "水口料未写原料名时，系统自动继承前面的 ABS PA-757"],
        ["多原料", "不同原料 + 水口料", "例：80%ABS PA-757 + 20%PVC 90度（本白,普通）水口料", "10kg 表示 8kg ABS + 2kg PVC 水口；不同原料按各自价格分别计算后合计"],
        ["多原料", "比例规则", "每段必须是“比例%原料”，各段用 + 分隔", "比例合计必须为 100%；水口料段请以“水口”或“水口料”结尾"],
        ["模具明细", "颜色 / PMS / 色粉", "分别填写颜色、PMS 和色粉", "PMS 会与颜色共同显示，色粉单独保存"],
        ["模具明细", "啤/套 / 啤数", "分别填写每套啤数说明和啤数", "啤数请填写数字"],
        ["模具明细", "所需用料(kg)", "直接填写本行模具所需总重量", "多原料时系统按各成分比例拆分重量"],
        ["模具明细", "需办日期", "建议使用 YYYY-MM-DD", "映射明细的需办 / 完成日期"],
        ["模具明细", "工模尺寸", "直接填写尺寸", "例如 207*789 或 650 × 450 × 380 mm"],
        ["模具明细", "模具状态（是否在厂）", "使用下拉选择：在厂 / 不在厂 / 待确认", "留空按待确认处理"],
        ["模具明细", "用料用途", "使用下拉选择：正式生产 / 试料", "试料不计入物料结余；留空按正式生产处理"],
        ["模具明细", "备注", "填写本行补充信息", "不影响用料比例及费用计算"],
        ["系统维护", "价格、费用与实际回填", "无需在导入模板填写", "原料价格、预计料费、实际用料和实际料费由系统维护"],
    ]
    guide_style_matrix = {
        (row_index, column_index): DETAIL_BODY_STYLE_ID
        for row_index in range(3, len(guide_rows) + 1)
        for column_index in range(1, 5)
    }

    return _build_workbook(
        _sheet_xml(
            rows,
            column_widths=ENGINEERING_IMPORT_COLUMN_WIDTHS,
            header_row_index=8,
            style_matrix=style_matrix,
            merge_ranges=[f"A1:{last_column}1", "B5:F5", f"A6:{last_column}6"],
            data_validations=[
                (f"L{detail_start_row}:L{detail_end_row}", ["在厂", "不在厂", "待确认"], "请选择在厂状态"),
                (f"M{detail_start_row}:M{detail_end_row}", ["正式生产", "试料"], "请选择用料用途"),
            ],
        ),
        additional_sheets=[
            (
                "填写说明",
                _sheet_xml(
                    guide_rows,
                    column_widths=[18, 28, 58, 86],
                    header_row_index=2,
                    style_matrix=guide_style_matrix,
                    merge_ranges=["A1:D1"],
                ),
            )
        ],
    )


def _safe_text(value: object, fallback: str = "—") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def _format_decimal(value: float | int | None, digits = 2) -> str:
    if value is None:
        return ""
    return f"{float(value):.{digits}f}"


def _format_export_item_value(field: str, value: object) -> tuple[object | None, bool]:
    if field == "mold_presence_status":
        return MOLD_PRESENCE_STATUS_LABELS[_normalize_mold_presence_status(value)], False
    if field == "material_usage_type":
        return MATERIAL_USAGE_TYPE_LABELS[_normalize_material_usage_type(value)], False

    if value is None or str(value).strip() == "":
        if field in FILLBACK_REQUIRED_FIELDS:
            return "缺", True
        if field in NUMERIC_ITEM_FIELDS:
            return "—", False
        return "", False

    if field in NUMERIC_ITEM_FIELDS:
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            return value, False
        if field == "exchange_rate_at_save":
            return f"{numeric_value:.4g}", False
        return _format_decimal(numeric_value), False

    return value, False


def _normalize_mold_presence_status(value: object) -> str:
    return {
        "": "unknown",
        "待确认": "unknown",
        "unknown": "unknown",
        "在厂": "in_factory",
        "in_factory": "in_factory",
        "不在厂": "out_of_factory",
        "out_of_factory": "out_of_factory",
    }.get(str(value or "").strip(), "unknown")


def _normalize_material_usage_type(value: object) -> str:
    text = str(value or "").strip().casefold()
    normalized = {
        "": "production",
        "production": "production",
        "正式": "production",
        "正式生产": "production",
        "生产": "production",
        "trial": "trial",
        "试料": "trial",
        "试模": "trial",
    }.get(text)
    if normalized is None:
        raise ValueError("用料用途仅支持“正式生产”或“试料”")
    return normalized


def _field_column_index(field: str) -> int:
    for index, (_, column_field) in enumerate(ITEM_COLUMNS, start=1):
        if column_field == field:
            return index

    raise ValueError(f"Unknown item export field: {field}")


def _calculate_expected_amount_hkd(
    item: object,
    material_prices: list[MoldingSampleMaterialPrice] | None,
) -> float | None:
    if not material_prices:
        return None

    required_material_kg = getattr(item, "required_material_kg", None)
    try:
        expected_weight_kg = float(required_material_kg)
    except (TypeError, ValueError):
        return None

    amount_hkd, _ = calculate_material_amount_hkd(
        expected_weight_kg,
        str(getattr(item, "material", "") or ""),
        list(getattr(item, "material_components", None) or []),
        material_prices,
    )
    return amount_hkd


def _get_export_item_value(
    item: object,
    field: str,
    material_prices: list[MoldingSampleMaterialPrice] | None,
) -> object:
    if field == "expected_amount_hkd":
        return _calculate_expected_amount_hkd(item, material_prices)

    return getattr(item, field, "")


def _sum_item_field(order: MoldingSampleOrder, field: str) -> float:
    total = 0.0
    for item in order.items:
        value = getattr(item, field, None)
        try:
            total += float(value)
        except (TypeError, ValueError):
            continue
    return total


def _build_single_export_subtotal_row(order: MoldingSampleOrder) -> list[object | None]:
    materials = sorted({str(item.material or "").strip() for item in order.items if str(item.material or "").strip()})
    material_label = "、".join(materials[:4])
    if len(materials) > 4:
        material_label = f"{material_label} 等 {len(materials)} 种原料"
    elif not material_label:
        material_label = "未填写原料"

    row: list[object | None] = ["" for _ in ITEM_COLUMNS]
    row[0] = f"原料小计（{material_label}，实际用料合计）"
    row[_field_column_index("actual_weight_kg") - 1] = _format_decimal(_sum_item_field(order, "actual_weight_kg"))
    row[_field_column_index("actual_amount_hkd") - 1] = _format_decimal(_sum_item_field(order, "actual_amount_hkd"))
    row[_field_column_index("injection_cost") - 1] = _format_decimal(_sum_item_field(order, "injection_cost"))
    row[_field_column_index("injection_cost_hkd") - 1] = _format_decimal(_sum_item_field(order, "injection_cost_hkd"))
    return row


def _build_single_export_total_row(order: MoldingSampleOrder, missing_count: int) -> list[object | None]:
    material_total = _sum_item_field(order, "actual_amount_hkd")
    injection_total = _sum_item_field(order, "injection_cost_hkd")
    row: list[object | None] = ["" for _ in ITEM_COLUMNS]
    row[0] = f"总计 料费 {_format_decimal(material_total)} + 啤办费 {_format_decimal(injection_total)} ="
    pending_text = f"（含 {missing_count} 项待回填）" if missing_count else "（资料完整）"
    row[_field_column_index("actual_amount_hkd") - 1] = f"HKD {_format_decimal(material_total + injection_total)}{pending_text}"
    return row


def _build_workbook(
    sheet_xml: str,
    additional_sheets: list[tuple[str, str]] | None = None,
) -> bytes:
    sheets = [(SHEET_NAME, sheet_xml), *(additional_sheets or [])]
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as workbook:
        workbook.writestr("[Content_Types].xml", _content_types_xml(len(sheets)))
        workbook.writestr("_rels/.rels", _root_rels_xml())
        workbook.writestr("docProps/app.xml", _app_xml())
        workbook.writestr("docProps/core.xml", _core_xml())
        workbook.writestr("xl/workbook.xml", _workbook_xml([name for name, _ in sheets]))
        workbook.writestr("xl/_rels/workbook.xml.rels", _workbook_rels_xml(len(sheets)))
        workbook.writestr("xl/styles.xml", _styles_xml())
        for sheet_index, (_, current_sheet_xml) in enumerate(sheets, start=1):
            workbook.writestr(f"xl/worksheets/sheet{sheet_index}.xml", current_sheet_xml)

    return buffer.getvalue()


def parse_order_excel(
    workbook_bytes: bytes,
    order_id_override: str | None = None,
    factory_id_override: str | None = None,
) -> MoldingSampleCreateRequest:
    rows = _read_first_sheet_rows(workbook_bytes)
    if not rows:
        raise ValueError("Excel 文件没有可读取的工作表内容")

    detail_header_index = _find_detail_header_row(rows)
    if detail_header_index is None:
        raise ValueError("Excel 未识别到啤办明细表头")

    metadata_rows = rows[:detail_header_index] + [
        row for row in rows[detail_header_index + 1 :] if _row_contains_order_metadata(row)
    ]
    order_data = _parse_order_metadata(metadata_rows)
    if factory_id_override:
        order_data["factory_id"] = factory_id_override
    if order_id_override:
        order_data["id"] = order_id_override

    order_id = str(order_data.get("id") or "").strip()
    if not order_id:
        order_id = f"BP-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        order_data["id"] = order_id

    if not str(order_data.get("product_name") or "").strip():
        raise ValueError("Excel 缺少产品名称")
    if not str(order_data.get("date") or "").strip():
        order_data["date"] = datetime.now().strftime("%Y-%m-%d")

    headers = [str(value or "").strip() for value in rows[detail_header_index]]
    uses_current_engineering_detail_contract = any(
        _normalize_header(header) == _normalize_header("模具状态（是否在厂）")
        for header in headers
    )
    field_by_index = {
        index: field
        for index, header in enumerate(headers)
        if (field := _item_field_for_header(header))
    }
    items: list[MoldingSampleItemIn] = []
    for excel_row_number, row in enumerate(
        rows[detail_header_index + 1 :],
        start=detail_header_index + 2,
    ):
        if not any(str(value or "").strip() for value in row):
            continue
        if _row_contains_order_metadata(row):
            continue
        if _row_contains_export_summary(row):
            continue

        item_data: dict[str, object] = {}
        pms = ""
        required_date = ""
        note_parts: list[str] = []
        for index, field in field_by_index.items():
            value = row[index] if index < len(row) else ""
            if field == "pms":
                pms = str(value or "").strip()
            elif field == "required_date":
                required_date = _normalize_date_text(value)
            elif field == "quote_cycle":
                quote_cycle = str(value or "").strip()
                if quote_cycle:
                    note_parts.append(f"报价周期：{quote_cycle}")
            elif field == "requirement":
                requirement = str(value or "").strip()
                if requirement:
                    note_parts.append(f"要求：{requirement}")
            elif field == "mold_presence_status":
                item_data[field] = _normalize_mold_presence_status(value)
            elif field == "material_usage_type":
                item_data[field] = _normalize_material_usage_type(value)
            elif field in NUMERIC_ITEM_FIELDS:
                item_data[field] = _parse_optional_float(value)
            elif field in {"sort_order", "shoot_qty"}:
                item_data[field] = _parse_int(value)
            else:
                item_data[field] = str(value or "").strip()

        item_number = len(items) + 1
        if pms:
            item_data["color"] = _format_color_pms(str(item_data.get("color") or ""), pms)
        if required_date:
            if not uses_current_engineering_detail_contract:
                item_data["mold_return_time"] = str(item_data.get("mold_return_time") or "") or required_date
            item_data["completion_time"] = str(item_data.get("completion_time") or "") or required_date
        existing_notes = str(item_data.get("notes") or "").strip()
        if existing_notes and note_parts:
            note_parts.append(f"备注：{existing_notes}")
        elif existing_notes:
            item_data["notes"] = existing_notes
        if note_parts:
            item_data["notes"] = "；".join(note_parts)

        material = str(item_data.get("material") or "").strip()
        material, material_components = _parse_import_material_components(
            material,
            excel_row_number=excel_row_number,
            strict=uses_current_engineering_detail_contract,
        )
        item_data["material"] = material
        item_data["material_components"] = material_components

        if order_id_override or not str(item_data.get("id") or "").strip():
            item_data["id"] = f"{order_id}-{item_number:03d}"
        if _parse_int(item_data.get("sort_order", "")) <= 0:
            item_data["sort_order"] = item_number
        items.append(MoldingSampleItemIn(**item_data))

    if not items:
        raise ValueError("Excel 未识别到啤办明细行")

    return MoldingSampleCreateRequest(order=MoldingSampleOrderIn(**order_data), items=items)


def _parse_import_material_components(
    material: str,
    *,
    excel_row_number: int,
    strict: bool,
) -> tuple[str, list[dict[str, object]]]:
    """Normalize the one-cell engineering material contract into components.

    Current engineering workbooks fail fast when a value visibly attempts the
    percentage composition syntax but cannot be parsed.  A plus sign without a
    percentage can be part of a single material name (for example ``PC+ABS``).
    Formal legacy exports keep their historical permissive behavior so old
    round trips are still accepted.
    """

    normalized_material = material.strip()
    if not normalized_material:
        return "", []

    parsed_components = parse_legacy_material_components(normalized_material)
    if parsed_components:
        return canonical_material_display(parsed_components), parsed_components

    has_composition_marker = bool(
        re.match(r"^\s*\d+(?:\.\d+)?\s*[%％]", normalized_material)
    )
    if has_composition_marker:
        if strict:
            raise ValueError(
                f"Excel 第 {excel_row_number} 行“所需用料”格式错误："
                "每段须按“比例%原料”填写并用 + 分隔，比例合计必须为 100%"
            )
        return normalized_material, []

    return normalized_material, [
        {
            "material": normalized_material,
            "ratio_percent": 100.0,
            "source_type": "virgin",
        }
    ]


def _read_first_sheet_rows(workbook_bytes: bytes) -> list[list[str]]:
    with ZipFile(BytesIO(workbook_bytes)) as workbook:
        shared_strings = _read_shared_strings(workbook)
        sheet_name = "xl/worksheets/sheet1.xml"
        if sheet_name not in workbook.namelist():
            sheet_name = next((name for name in workbook.namelist() if name.startswith("xl/worksheets/sheet")), "")
        if not sheet_name:
            raise ValueError("Excel 文件缺少工作表")

        root = ElementTree.fromstring(workbook.read(sheet_name))

    parsed_rows: list[list[str]] = []
    for row in root.findall(".//main:sheetData/main:row", NS):
        values: list[str] = []
        for cell in row.findall("main:c", NS):
            cell_ref = cell.attrib.get("r", "")
            cell_index = _column_index("".join(char for char in cell_ref if char.isalpha())) if cell_ref else len(values)
            while len(values) <= cell_index:
                values.append("")
            values[cell_index] = _read_cell_value(cell, shared_strings)
        parsed_rows.append(values)

    return parsed_rows


def _read_shared_strings(workbook: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in workbook.namelist():
        return []

    root = ElementTree.fromstring(workbook.read("xl/sharedStrings.xml"))
    strings: list[str] = []
    for item in root.findall("main:si", NS):
        parts = [text.text or "" for text in item.findall(".//main:t", NS)]
        strings.append("".join(parts))
    return strings


def _read_cell_value(cell: ElementTree.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t", "")
    if cell_type == "inlineStr":
        text = cell.find("main:is/main:t", NS)
        return text.text if text is not None and text.text is not None else ""

    value = cell.find("main:v", NS)
    raw = value.text if value is not None and value.text is not None else ""
    if cell_type == "s":
        try:
            return shared_strings[int(raw)]
        except (ValueError, IndexError):
            return ""
    return raw


def _find_detail_header_row(rows: list[list[str]]) -> int | None:
    for index, row in enumerate(rows):
        normalized = {str(value or "").strip() for value in row}
        has_mold_header = bool({"模具编号", "客模具编号"} & normalized)
        has_material_header = bool({"原料", "用料", "所需用料"} & normalized)
        if "明细ID" in normalized or (has_mold_header and has_material_header):
            return index
    return None


def _parse_order_metadata(rows: list[list[str]]) -> dict[str, str]:
    parsed: dict[str, str] = {
        "factory_id": "huakang-a",
        "order_type": "啤办",
        "workshop": "A车间",
    }

    if _looks_like_engineering_molding_sample_template(rows):
        parsed.update(
            {
                "stage": "T0",
                "workshop": "工程部",
                "reason": "工程部啤办通知单导入",
            }
        )

    for row in rows:
        for index, cell_value in enumerate(row):
            label, inline_value = _split_label_value(cell_value)
            value = inline_value or (str(row[index + 1] or "").strip() if index + 1 < len(row) else "")
            if _parse_composite_order_metadata(parsed, label, value):
                continue
            field = ORDER_ALIASES.get(label)
            if field and value:
                parsed[field] = _normalize_order_value(field, value)
    return parsed


def _parse_composite_order_metadata(parsed: dict[str, str], label: str, value: object) -> bool:
    normalized_label = label.replace(" ", "")
    text = str(value or "").strip()
    if not text:
        return False

    if normalized_label == "产品/客户":
        product_name, client_name = _split_pair_value(text)
        if product_name:
            parsed["product_name"] = product_name
        if client_name:
            parsed["client_name"] = client_name
        return True

    if normalized_label == "阶段/车间":
        stage, workshop_text = _split_pair_value(text)
        workshop, send_to = _split_parenthesized_value(workshop_text)
        if stage:
            parsed["stage"] = stage
        if workshop:
            parsed["workshop"] = workshop
        if send_to:
            parsed["send_to"] = send_to
        return True

    if normalized_label == "工程/主管":
        engineer, supervisor = _split_pair_value(text)
        if engineer:
            parsed["eng_name"] = engineer
        if supervisor:
            parsed["supervisor"] = supervisor
        return True

    return False


def _split_pair_value(value: str) -> tuple[str, str]:
    parts = [part.strip() for part in re.split(r"\s*/\s*", value, maxsplit=1)]
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]


def _split_parenthesized_value(value: str) -> tuple[str, str]:
    text = value.strip()
    match = re.match(r"^(.*?)\s*[（(](.*?)[）)]\s*$", text)
    if not match:
        return text, ""
    return match.group(1).strip(), match.group(2).strip()


def _looks_like_engineering_molding_sample_template(rows: list[list[str]]) -> bool:
    flat_values = [str(value or "").strip() for row in rows for value in row if str(value or "").strip()]

    return any("啤办通知单" in value for value in flat_values)


def _split_label_value(value: object) -> tuple[str, str]:
    text = str(value or "").strip()
    if not text:
        return "", ""

    match = re.match(r"^([^:：]+)\s*[:：]\s*(.*)$", text)
    if match:
        return _normalize_label(match.group(1)), match.group(2).strip()

    return _normalize_label(text), ""


def _normalize_label(value: str) -> str:
    return value.strip().rstrip(":：").strip()


def _normalize_order_value(field: str, value: object) -> str:
    text = str(value or "").strip()
    if field == "date":
        return _normalize_date_text(text)
    if field == "doc_number":
        return _extract_document_number(text)
    return text


def _extract_document_number(value: str) -> str:
    text = value.strip()
    if not text:
        return ""

    return re.split(r"\s*版本\s*[:：]|\s*修订\s*[:：]", text, maxsplit=1)[0].strip()


def _item_field_for_header(header: str) -> str | None:
    if header in ITEM_ALIASES:
        return ITEM_ALIASES[header]

    normalized_header = _normalize_header(header)
    for label, field in ITEM_ALIASES.items():
        if _normalize_header(label) == normalized_header:
            return field
    return None


def _normalize_header(value: str) -> str:
    return (
        str(value or "")
        .strip()
        .replace("（", "(")
        .replace("）", ")")
        .replace(" ", "")
        .upper()
    )


def _row_contains_order_metadata(row: list[str]) -> bool:
    metadata_labels = {"客户", "产品编号", "产品名称", "文件编号", "落单人", "落单日期"}
    for value in row:
        label, inline_value = _split_label_value(value)
        if inline_value and label in metadata_labels:
            return True
    return False


def _row_contains_export_summary(row: list[str]) -> bool:
    first_value = str(row[0] if row else "").strip()
    return first_value.startswith("原料小计") or first_value.startswith("总计")


def _format_color_pms(color: str, pms: str) -> str:
    normalized_color = color.strip()
    normalized_pms = pms.strip()
    if normalized_pms and not normalized_pms.upper().startswith("PMS "):
        normalized_pms = f"PMS {normalized_pms}"
    return " / ".join(part for part in [normalized_color, normalized_pms] if part)


def _normalize_date_text(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""

    date_match = re.search(r"(\d{4})[./-](\d{1,2})[./-](\d{1,2})", text)
    if date_match:
        year, month, day = (int(part) for part in date_match.groups())
        return f"{year:04d}-{month:02d}-{day:02d}"

    try:
        serial = float(text)
    except ValueError:
        return text

    if 20000 <= serial <= 60000:
        return (datetime(1899, 12, 30) + timedelta(days=int(serial))).strftime("%Y-%m-%d")

    return text


def _parse_optional_float(value: object) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _parse_int(value: object) -> int:
    text = str(value or "").strip()
    if not text:
        return 0
    try:
        return int(float(text))
    except ValueError:
        return 0


def _sheet_xml(
    rows: list[list[object | None]],
    column_widths: list[int] | None = None,
    header_row_index: int = DETAIL_HEADER_ROW_INDEX,
    style_matrix: dict[tuple[int, int], int] | None = None,
    merge_ranges: list[str] | None = None,
    data_validations: list[tuple[str, list[str], str]] | None = None,
) -> str:
    widths = column_widths or ITEM_COLUMN_WIDTHS
    row_xml = []
    for row_index, row in enumerate(rows, start=1):
        cells = [
            _cell_xml(
                _column_name(col_index),
                row_index,
                value,
                style_id=_style_for_cell(row_index, col_index, header_row_index, style_matrix),
            )
            for col_index, value in enumerate(row, start=1)
        ]
        row_xml.append(f'<row {_row_attributes(row_index, header_row_index)}>{"".join(cells)}</row>')

    last_column = _column_name(max(len(widths), max((len(row) for row in rows), default=1)))
    last_row = max(len(rows), 1)
    top_left_row = header_row_index + 1
    resolved_merge_ranges = merge_ranges if merge_ranges is not None else [f"A1:{last_column}1"]
    merge_cells_xml = ""
    if resolved_merge_ranges:
        merge_cells_xml = (
            f'<mergeCells count="{len(resolved_merge_ranges)}">'
            + "".join(f'<mergeCell ref="{merge_range}"/>' for merge_range in resolved_merge_ranges)
            + "</mergeCells>"
        )

    data_validations_xml = ""
    if data_validations:
        validation_entries: list[str] = []
        for cell_range, options, prompt in data_validations:
            option_list = f'"{_escape_xml(",".join(options))}"'
            validation_entries.append(
                '<dataValidation type="list" allowBlank="1" showInputMessage="1" '
                'showErrorMessage="1" errorStyle="stop" '
                f'sqref="{_escape_xml(cell_range)}" promptTitle="填写提示" '
                f'prompt="{_escape_xml(prompt)}" errorTitle="填写错误" '
                f'error="{_escape_xml(prompt)}"><formula1>{option_list}</formula1></dataValidation>'
            )
        data_validations_xml = (
            f'<dataValidations count="{len(validation_entries)}">'
            + "".join(validation_entries)
            + "</dataValidations>"
        )

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<dimension ref="A1:{last_column}{last_row}"/>'
        '<sheetViews><sheetView workbookViewId="0">'
        f'<pane ySplit="{header_row_index}" topLeftCell="A{top_left_row}" activePane="bottomLeft" state="frozen"/>'
        f'<selection pane="bottomLeft" activeCell="A{top_left_row}" sqref="A{top_left_row}"/>'
        '</sheetView></sheetViews>'
        '<sheetFormatPr defaultRowHeight="18"/>'
        f"{_columns_xml(widths)}"
        f"<sheetData>{''.join(row_xml)}</sheetData>"
        f'<autoFilter ref="A{header_row_index}:{last_column}{header_row_index}"/>'
        f"{merge_cells_xml}"
        f"{data_validations_xml}"
        '<pageMargins left="0.35" right="0.35" top="0.55" bottom="0.55" header="0.2" footer="0.2"/>'
        '<pageSetup orientation="landscape" paperSize="9" fitToWidth="1" fitToHeight="0"/>'
        "</worksheet>"
    )


def _row_attributes(row_index: int, header_row_index: int = DETAIL_HEADER_ROW_INDEX) -> str:
    if row_index == 1:
        return f'r="{row_index}" ht="32" customHeight="1"'
    if 2 <= row_index < header_row_index:
        return f'r="{row_index}" ht="22" customHeight="1"'
    if row_index == header_row_index:
        return f'r="{row_index}" ht="24" customHeight="1"'
    return f'r="{row_index}"'


def _columns_xml(widths: list[int] | None = None) -> str:
    column_widths = widths or ITEM_COLUMN_WIDTHS
    columns = [
        f'<col min="{index}" max="{index}" width="{width}" customWidth="1"/>'
        for index, width in enumerate(column_widths, start=1)
    ]
    return f"<cols>{''.join(columns)}</cols>"


def _style_for_cell(
    row_index: int,
    col_index: int,
    header_row_index: int = DETAIL_HEADER_ROW_INDEX,
    style_matrix: dict[tuple[int, int], int] | None = None,
) -> int | None:
    if style_matrix and (row_index, col_index) in style_matrix:
        return style_matrix[(row_index, col_index)]
    if row_index == 1 and col_index == 1:
        return TITLE_STYLE_ID
    if 2 <= row_index < header_row_index:
        if col_index in {1, 3, 5}:
            return ORDER_LABEL_STYLE_ID
        if col_index in {2, 4, 6}:
            return ORDER_VALUE_STYLE_ID
    if row_index == header_row_index:
        return DETAIL_HEADER_STYLE_ID
    if row_index > header_row_index:
        return DETAIL_BODY_STYLE_ID
    return None


def _cell_xml(column_name: str, row_index: int, value: object | None, style_id: int | None = None) -> str:
    cell_ref = f"{column_name}{row_index}"
    style_attr = f' s="{style_id}"' if style_id is not None else ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f'<c r="{cell_ref}"{style_attr}><v>{value}</v></c>'

    text = _escape_xml("" if value is None else str(value))
    return f'<c r="{cell_ref}"{style_attr} t="inlineStr"><is><t>{text}</t></is></c>'


def _column_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _column_index(name: str) -> int:
    value = 0
    for char in name.upper():
        value = value * 26 + ord(char) - 64
    return max(value - 1, 0)


def _escape_xml(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _content_types_xml(sheet_count: int = 1) -> str:
    worksheet_overrides = "".join(
        f'<Override PartName="/xl/worksheets/sheet{sheet_index}.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for sheet_index in range(1, sheet_count + 1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        f"{worksheet_overrides}"
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        "</Types>"
    )


def _root_rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
        "</Relationships>"
    )


def _workbook_xml(sheet_names: list[str] | None = None) -> str:
    resolved_sheet_names = sheet_names or [SHEET_NAME]
    sheets_xml = "".join(
        f'<sheet name="{_escape_xml(sheet_name)}" sheetId="{sheet_index}" r:id="rId{sheet_index}"/>'
        for sheet_index, sheet_name in enumerate(resolved_sheet_names, start=1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets>{sheets_xml}</sheets>"
        "</workbook>"
    )


def _workbook_rels_xml(sheet_count: int = 1) -> str:
    worksheet_relationships = "".join(
        f'<Relationship Id="rId{sheet_index}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        f'Target="worksheets/sheet{sheet_index}.xml"/>'
        for sheet_index in range(1, sheet_count + 1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f"{worksheet_relationships}"
        f'<Relationship Id="rId{sheet_count + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        "</Relationships>"
    )


def _styles_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="7">'
        '<font><sz val="11"/><name val="Calibri"/></font>'
        '<font><b/><sz val="18"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>'
        '<font><b/><sz val="11"/><color rgb="FF475569"/><name val="Calibri"/></font>'
        '<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>'
        '<font><b/><sz val="11"/><color rgb="FFB91C1C"/><name val="Calibri"/></font>'
        '<font><b/><sz val="11"/><color rgb="FF92400E"/><name val="Calibri"/></font>'
        '<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>'
        '</fonts>'
        '<fills count="12">'
        '<fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FF0F172A"/><bgColor indexed="64"/></patternFill></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FFE2E8F0"/><bgColor indexed="64"/></patternFill></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FFECFDF5"/><bgColor indexed="64"/></patternFill></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FFFEF2F2"/><bgColor indexed="64"/></patternFill></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FFFFFBEB"/><bgColor indexed="64"/></patternFill></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FF0F766E"/><bgColor indexed="64"/></patternFill></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FF1E293B"/><bgColor indexed="64"/></patternFill></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FF0F766E"/><bgColor indexed="64"/></patternFill></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FFEFF6FF"/><bgColor indexed="64"/></patternFill></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FFF0FDF4"/><bgColor indexed="64"/></patternFill></fill>'
        '</fills>'
        '<borders count="2">'
        '<border><left/><right/><top/><bottom/><diagonal/></border>'
        '<border>'
        '<left style="thin"><color rgb="FFCBD5E1"/></left>'
        '<right style="thin"><color rgb="FFCBD5E1"/></right>'
        '<top style="thin"><color rgb="FFCBD5E1"/></top>'
        '<bottom style="thin"><color rgb="FFCBD5E1"/></bottom>'
        '<diagonal/>'
        '</border>'
        '</borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="13">'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1">'
        '<alignment horizontal="center" vertical="center"/>'
        '</xf>'
        '<xf numFmtId="0" fontId="2" fillId="3" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">'
        '<alignment horizontal="right" vertical="center"/>'
        '</xf>'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1">'
        '<alignment horizontal="left" vertical="center" wrapText="1"/>'
        '</xf>'
        '<xf numFmtId="0" fontId="3" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">'
        '<alignment horizontal="center" vertical="center" wrapText="1"/>'
        '</xf>'
        '<xf numFmtId="0" fontId="0" fillId="4" borderId="1" xfId="0" applyFill="1" applyBorder="1" applyAlignment="1">'
        '<alignment horizontal="left" vertical="center" wrapText="1"/>'
        '</xf>'
        '<xf numFmtId="0" fontId="4" fillId="5" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">'
        '<alignment horizontal="center" vertical="center" wrapText="1"/>'
        '</xf>'
        '<xf numFmtId="0" fontId="5" fillId="6" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">'
        '<alignment horizontal="right" vertical="center" wrapText="1"/>'
        '</xf>'
        '<xf numFmtId="0" fontId="6" fillId="7" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">'
        '<alignment horizontal="right" vertical="center" wrapText="1"/>'
        '</xf>'
        '<xf numFmtId="0" fontId="3" fillId="8" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">'
        '<alignment horizontal="center" vertical="center" wrapText="1"/>'
        '</xf>'
        '<xf numFmtId="0" fontId="3" fillId="9" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">'
        '<alignment horizontal="center" vertical="center" wrapText="1"/>'
        '</xf>'
        '<xf numFmtId="0" fontId="0" fillId="10" borderId="1" xfId="0" applyFill="1" applyBorder="1" applyAlignment="1">'
        '<alignment horizontal="left" vertical="center" wrapText="1"/>'
        '</xf>'
        '<xf numFmtId="0" fontId="0" fillId="11" borderId="1" xfId="0" applyFill="1" applyBorder="1" applyAlignment="1">'
        '<alignment horizontal="left" vertical="center" wrapText="1"/>'
        '</xf>'
        '</cellXfs>'
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        "</styleSheet>"
    )


def _app_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        "<Application>Royal Regent Nexus</Application></Properties>"
    )


def _core_xml() -> str:
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        "<dc:creator>Royal Regent Nexus</dc:creator>"
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>'
        f'<dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified>'
        "</cp:coreProperties>"
    )
