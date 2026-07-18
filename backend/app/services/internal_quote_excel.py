from __future__ import annotations

import json
from io import BytesIO
from typing import Any, Iterable

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from app.models.internal_quote import InternalQuote, InternalQuoteSection


P3_TEMPLATE_VERSION = "internal-quote-p3-v1"
P4_TEMPLATE_VERSION = "internal-quote-p4-v2"
TEMPLATE_VERSION = P3_TEMPLATE_VERSION
STRUCTURED_DATA_SCHEMA_VERSION = "internal-quote-structured-data-v1"
STRUCTURED_DATA_CHUNK_SIZE = 30000
SECTION_ORDER = (
    "sales",
    "engineering",
    "electronic",
    "molding",
    "painting",
    "slush",
    "sewing",
    "assembly",
)

NAVY = "17324D"
TEAL = "0F766E"
PALE_TEAL = "DFF4F1"
PALE_BLUE = "E8F1F8"
SLATE = "334155"
WHITE = "FFFFFF"
THIN = Side(style="thin", color="CBD5E1")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def _json_object(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _safe_text(value: object) -> str:
    result = "" if value is None else str(value)
    if result.startswith(("=", "+", "-", "@")):
        return f"'{result}"
    return result


def _json_text(value: object) -> str:
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return rendered[:32000]


def _canonical_json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_chunks(value: object) -> list[str]:
    rendered = _canonical_json_text(value)
    return [
        rendered[index:index + STRUCTURED_DATA_CHUNK_SIZE]
        for index in range(0, len(rendered), STRUCTURED_DATA_CHUNK_SIZE)
    ] or [""]


def _number(value: object) -> float | str:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return ""


def _style_title(sheet, title: str, end_column: int) -> None:
    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=end_column)
    cell = sheet.cell(1, 1, title)
    cell.font = Font(name="Microsoft YaHei", size=17, bold=True, color=WHITE)
    cell.fill = PatternFill("solid", fgColor=NAVY)
    cell.alignment = Alignment(horizontal="center", vertical="center")
    sheet.row_dimensions[1].height = 30


def _header_row(sheet, row: int, headers: Iterable[str]) -> None:
    for column, header in enumerate(headers, start=1):
        cell = sheet.cell(row, column, header)
        cell.font = Font(name="Microsoft YaHei", bold=True, color=SLATE)
        cell.fill = PatternFill("solid", fgColor=PALE_TEAL)
        cell.border = BORDER
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _body_row(
    sheet,
    row: int,
    values: Iterable[object],
    *,
    amount_columns: set[int] | None = None,
    text_columns: set[int] | None = None,
) -> None:
    for column, value in enumerate(values, start=1):
        cell = sheet.cell(row, column, value)
        cell.font = Font(name="Microsoft YaHei", color=SLATE)
        cell.border = BORDER
        cell.alignment = Alignment(vertical="top", wrap_text=True)
        if text_columns and column in text_columns:
            cell.data_type = "s"
        if amount_columns and column in amount_columns and isinstance(value, (int, float)):
            cell.number_format = "#,##0.0000"


def _finish_sheet(sheet, widths: tuple[int, ...]) -> None:
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    sheet.freeze_panes = "A4"
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.fitToWidth = 1
    sheet.page_margins.left = 0.25
    sheet.page_margins.right = 0.25


def _line_amount(line: dict[str, Any]) -> float | str:
    for key in (
        "amount_hkd",
        "line_hkd",
        "per_piece_hkd",
        "amount_hkd_pcs",
        "deduction_hkd",
        "total_usd",
    ):
        if key in line and line[key] is not None:
            return _number(line[key])
    return ""


def _build_summary_sheet(workbook: Workbook, quote: InternalQuote, sections: list[InternalQuoteSection]) -> None:
    sheet = workbook.active
    sheet.title = "报价明细"
    _style_title(sheet, "华登集团内部报价明细", 8)
    info = (
        ("报价编号", quote.quote_no, "版本", quote.version_label, "客户", quote.customer, "数量", quote.qty),
        ("产品", quote.product_name, "厂区/车间", f"{quote.factory_id}/{quote.workshop_name}", "公式版本", quote.formula_version, "参考快照", quote.reference_snapshot_id),
        ("客人目标价", quote.target_customer_price, "预计完成日期", quote.target_date, "建单部门", quote.initiator_department, "备注", quote.remark),
    )
    for row_index, values in enumerate(info, start=2):
        _body_row(sheet, row_index, (_safe_text(value) for value in values))

    current_row = 5
    _header_row(sheet, current_row, ("分段", "类型", "项目/产品组", "币种", "金额", "状态", "revision", "计算明细"))
    current_row += 1
    by_code = {section.department: section for section in sections}
    for code in SECTION_ORDER:
        section = by_code.get(code)
        if section is None:
            continue
        calculation = _json_object(section.calculation_json)
        payload = _json_object(section.payload_json)
        breakdown = calculation.get("line_breakdown", [])
        if not isinstance(breakdown, list):
            breakdown = []
        if section.department == "engineering":
            molds = payload.get("molds", [])
            for mold in molds if isinstance(molds, list) else []:
                if not isinstance(mold, dict):
                    continue
                amount = _number(mold.get("cost_rmb"))
                _body_row(
                    sheet,
                    current_row,
                    (
                        _safe_text(section.department_name),
                        "mold",
                        _safe_text(mold.get("item") or mold.get("mold_no", "")),
                        "RMB",
                        amount,
                        section.status,
                        section.revision,
                        _json_text(mold),
                    ),
                    amount_columns={5},
                )
                current_row += 1
        for line in breakdown:
            if not isinstance(line, dict):
                continue
            if section.department == "engineering" and line.get("kind") == "mold_quote":
                # The full mold-detail payload is already emitted above; avoid a
                # second, less-detailed copy of the same quote line.
                continue
            label = line.get("item") or line.get("group") or line.get("name") or ""
            amount = _line_amount(line)
            currency = "USD" if "total_usd" in line else "HKD"
            _body_row(
                sheet,
                current_row,
                (
                    _safe_text(section.department_name),
                    _safe_text(line.get("kind", "")),
                    _safe_text(label),
                    currency,
                    amount,
                    section.status,
                    section.revision,
                    _json_text(line),
                ),
                amount_columns={5},
            )
            current_row += 1
        totals = calculation.get("totals", {})
        total_hkd = totals.get("total_hkd", "") if isinstance(totals, dict) else ""
        _body_row(
            sheet,
            current_row,
            (
                _safe_text(section.department_name),
                "分段合计",
                "",
                "HKD",
                _number(total_hkd),
                section.status,
                section.revision,
                _json_text(totals),
            ),
            amount_columns={5},
        )
        for column in range(1, 9):
            sheet.cell(current_row, column).fill = PatternFill("solid", fgColor=PALE_BLUE)
            sheet.cell(current_row, column).font = Font(name="Microsoft YaHei", bold=True, color=SLATE)
        current_row += 1
    _finish_sheet(sheet, (16, 20, 28, 10, 15, 16, 10, 52))


def _walk_components(rows: list[dict[str, Any]], parent: str = ""):
    for row in rows:
        if not isinstance(row, dict):
            continue
        yield parent, row
        children = row.get("children", [])
        if isinstance(children, list):
            yield from _walk_components(children, str(row.get("item", "")))


def _build_electronic_sheet(workbook: Workbook, section: InternalQuoteSection | None) -> None:
    sheet = workbook.create_sheet("电子明细")
    _style_title(sheet, "电子报价明细", 8)
    _header_row(sheet, 3, ("父项", "零件", "规格", "用量", "单价HKD", "金额HKD", "备注", "来源"))
    row_index = 4
    payload = _json_object(section.payload_json) if section else {}
    components = payload.get("components", [])
    for parent, row in _walk_components(components if isinstance(components, list) else []):
        quantity = _number(row.get("quantity"))
        unit_price = _number(row.get("unit_price_hkd"))
        amount = quantity * unit_price if isinstance(quantity, float) and isinstance(unit_price, float) else ""
        _body_row(
            sheet,
            row_index,
            (
                _safe_text(parent),
                _safe_text(row.get("item", "")),
                _safe_text(row.get("specification", "")),
                quantity,
                unit_price,
                amount,
                _safe_text(row.get("note", "")),
                _safe_text(f"{row.get('source_currency', '')} row {row.get('source_row', '')}"),
            ),
            amount_columns={5, 6},
        )
        row_index += 1
    _finish_sheet(sheet, (20, 28, 28, 12, 15, 15, 28, 20))


def _build_sewing_sheet(workbook: Workbook, section: InternalQuoteSection | None) -> None:
    sheet = workbook.create_sheet("车缝明细")
    _style_title(sheet, "车缝报价明细", 9)
    _header_row(sheet, 3, ("产品组", "分类", "物料", "部位", "供应商", "用量", "RMB单价", "码点", "备注"))
    row_index = 4
    payload = _json_object(section.payload_json) if section else {}
    for group in payload.get("groups", []) if isinstance(payload.get("groups", []), list) else []:
        if not isinstance(group, dict):
            continue
        for row in group.get("materials", []) if isinstance(group.get("materials", []), list) else []:
            if not isinstance(row, dict):
                continue
            _body_row(
                sheet,
                row_index,
                (
                    _safe_text(group.get("name", "")),
                    _safe_text(group.get("category", "")),
                    _safe_text(row.get("item", "")),
                    _safe_text(row.get("part", "")),
                    _safe_text(row.get("supplier", "")),
                    _number(row.get("usage")),
                    _number(row.get("unit_price_rmb")),
                    _number(row.get("markup")),
                    _safe_text(row.get("note", "")),
                ),
            )
            row_index += 1
    _finish_sheet(sheet, (24, 12, 28, 18, 20, 12, 15, 12, 30))


def _build_assembly_sheet(workbook: Workbook, section: InternalQuoteSection | None) -> None:
    sheet = workbook.create_sheet("装配明细")
    _style_title(sheet, "装配排拉工序明细", 8)
    _header_row(sheet, 3, ("产品组", "分类", "工序", "人数", "小组数", "生产量", "备注", "来源行"))
    row_index = 4
    payload = _json_object(section.payload_json) if section else {}
    for group in payload.get("groups", []) if isinstance(payload.get("groups", []), list) else []:
        if not isinstance(group, dict):
            continue
        for process in group.get("processes", []) if isinstance(group.get("processes", []), list) else []:
            if not isinstance(process, dict):
                continue
            _body_row(
                sheet,
                row_index,
                (
                    _safe_text(group.get("name", "")),
                    _safe_text(group.get("category", "")),
                    _safe_text(process.get("name", "")),
                    _number(process.get("persons")),
                    _number(process.get("teams")),
                    _number(process.get("production_qty")),
                    _safe_text(process.get("note", "")),
                    process.get("source_row", ""),
                ),
            )
            row_index += 1
    _finish_sheet(sheet, (24, 14, 30, 12, 12, 15, 32, 12))


def _build_structured_data_sheet(
    workbook: Workbook,
    quote: InternalQuote,
    sections: list[InternalQuoteSection],
    reference_snapshot: dict[str, Any],
) -> None:
    sheet = workbook.create_sheet("结构化数据")
    _style_title(sheet, "P4 客价转换结构化数据", 12)
    _body_row(
        sheet,
        2,
        (
            "结构版本",
            STRUCTURED_DATA_SCHEMA_VERSION,
            "说明",
            "按记录类型、分段和分片序号重组 JSON；禁止从展示明细反推原始参数",
        ),
    )
    _header_row(
        sheet,
        3,
        (
            "记录类型",
            "分段代码",
            "分段名称",
            "状态",
            "revision",
            "计算状态",
            "依赖状态",
            "计算hash",
            "分片序号",
            "分片总数",
            "JSON分片",
            "是否参与",
        ),
    )
    row_index = 4
    snapshot_chunks = _json_chunks(reference_snapshot)
    for chunk_index, chunk in enumerate(snapshot_chunks, start=1):
        _body_row(
            sheet,
            row_index,
            (
                "reference_snapshot",
                "quote",
                "报价参考快照",
                "frozen",
                quote.header_revision,
                "valid",
                "current",
                quote.reference_snapshot_id,
                chunk_index,
                len(snapshot_chunks),
                chunk,
                "是",
            ),
            text_columns={11},
        )
        row_index += 1
    by_code = {section.department: section for section in sections}
    for code in SECTION_ORDER:
        section = by_code.get(code)
        if section is None:
            continue
        records = (
            ("payload", _json_object(section.payload_json)),
            ("calculation", _json_object(section.calculation_json)),
        )
        for record_type, value in records:
            chunks = _json_chunks(value)
            for chunk_index, chunk in enumerate(chunks, start=1):
                _body_row(
                    sheet,
                    row_index,
                    (
                        record_type,
                        section.department,
                        _safe_text(section.department_name),
                        section.status,
                        section.revision,
                        section.calculation_status,
                        section.dependency_status,
                        section.calculation_hash,
                        chunk_index,
                        len(chunks),
                        chunk,
                        "是" if section.is_required else "否",
                    ),
                    text_columns={11},
                )
                row_index += 1
    _finish_sheet(sheet, (16, 16, 20, 18, 10, 16, 16, 66, 10, 10, 76, 12))


def _build_approval_sheet(
    workbook: Workbook,
    quote: InternalQuote,
    sections: list[InternalQuoteSection],
    manifest: dict[str, Any],
) -> None:
    sheet = workbook.create_sheet("审批与版本")
    _style_title(sheet, "审批、公式与版本清单", 8)
    is_final_release = manifest.get("release_stage") == "p4_final_approved"
    template_version = str(manifest.get("template_version") or P3_TEMPLATE_VERSION)
    release_label = "P4 最终业务放行" if is_final_release else "P3 分段审批后内部成本快照"
    boundary_label = (
        "最终业务放行完成，可交接客价转换台"
        if is_final_release
        else "最终业务放行与客价交接在 P4 实施"
    )
    summary = (
        ("模板版本", template_version, "公式版本", quote.formula_version),
        ("参考快照", quote.reference_snapshot_id, "报价头revision", quote.header_revision),
        ("导出阶段", release_label, "清单SHA-256", manifest.get("manifest_sha256", "")),
        ("边界说明", boundary_label, "", ""),
        (
            "最终提交人",
            manifest.get("final_submitted_by_name", ""),
            "最终放行人/时间",
            f"{manifest.get('final_reviewed_by_name', '')} {manifest.get('final_reviewed_at', '')}".strip(),
        ),
    )
    for row_index, values in enumerate(summary, start=2):
        _body_row(sheet, row_index, (_safe_text(value) for value in values))
    _header_row(sheet, 7, ("分段", "是否必需", "状态", "revision", "计算状态", "依赖状态", "审核人", "审核时间"))
    row_index = 8
    by_code = {section.department: section for section in sections}
    for code in SECTION_ORDER:
        section = by_code.get(code)
        if section is None:
            continue
        _body_row(
            sheet,
            row_index,
            (
                _safe_text(section.department_name),
                "是" if section.is_required else "否",
                section.status,
                section.revision,
                section.calculation_status,
                section.dependency_status,
                _safe_text(section.reviewed_by),
                section.reviewed_at,
            ),
        )
        row_index += 1
    row_index += 1
    _header_row(sheet, row_index, ("清单字段", "值"))
    row_index += 1
    for key, value in manifest.items():
        _body_row(sheet, row_index, (_safe_text(key), _safe_text(_json_text(value) if isinstance(value, (dict, list)) else value)))
        row_index += 1
    _finish_sheet(sheet, (24, 24, 20, 16, 18, 18, 20, 22))


def build_internal_quote_workbook(
    quote: InternalQuote,
    sections: list[InternalQuoteSection],
    manifest: dict[str, Any],
    reference_snapshot: dict[str, Any] | None = None,
) -> bytes:
    workbook = Workbook()
    workbook.properties.creator = "Royal Regent Nexus"
    workbook.properties.title = f"{quote.quote_no} 内部报价"
    _build_summary_sheet(workbook, quote, sections)
    by_code = {section.department: section for section in sections}
    _build_electronic_sheet(workbook, by_code.get("electronic"))
    _build_sewing_sheet(workbook, by_code.get("sewing"))
    _build_assembly_sheet(workbook, by_code.get("assembly"))
    if manifest.get("release_stage") == "p4_final_approved":
        _build_structured_data_sheet(workbook, quote, sections, reference_snapshot or {})
    _build_approval_sheet(workbook, quote, sections, manifest)
    buffer = BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()
