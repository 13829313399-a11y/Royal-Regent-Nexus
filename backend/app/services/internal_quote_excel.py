from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from app.schemas.internal_quote import InternalQuoteDetailOut


def build_internal_quote_workbook(detail: InternalQuoteDetailOut) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "内部报价明细"
    sheet.freeze_panes = "A7"

    teal = "0F766E"
    pale_teal = "CCFBF1"
    slate = "334155"
    border = Border(*(Side(style="thin", color="CBD5E1") for _ in range(4)))

    sheet.merge_cells("A1:H1")
    sheet["A1"] = f"{detail.quote_no} {detail.product_name} 内部报价明细"
    sheet["A1"].font = Font(name="Microsoft YaHei", bold=True, size=18, color="FFFFFF")
    sheet["A1"].fill = PatternFill("solid", fgColor=teal)
    sheet["A1"].alignment = Alignment(horizontal="center", vertical="center")
    sheet.row_dimensions[1].height = 34

    metadata = (
        ("厂区", detail.factory_id, "车间", detail.workshop_name),
        ("客户", detail.customer, "数量", detail.qty),
        ("版本", detail.version_label, "状态", detail.status),
        ("创建人", detail.created_by_name, "总计 HKD", detail.total_hkd),
    )
    for row_index, values in enumerate(metadata, start=2):
        for column_index, value in enumerate(values, start=1):
            cell = sheet.cell(row_index, column_index, value)
            cell.font = Font(name="Microsoft YaHei", bold=column_index in {1, 3}, color=slate)
            cell.fill = PatternFill("solid", fgColor=pale_teal if column_index in {1, 3} else "FFFFFF")
            cell.border = border
            cell.alignment = Alignment(vertical="center")
        sheet.merge_cells(start_row=row_index, start_column=4, end_row=row_index, end_column=8)

    current_row = 7
    for section in detail.sections:
        sheet.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=8)
        section_cell = sheet.cell(
            current_row,
            1,
            f"{section.department_name} · {section.status} · {section.calculation.formula_version}",
        )
        section_cell.font = Font(name="Microsoft YaHei", bold=True, size=12, color="FFFFFF")
        section_cell.fill = PatternFill("solid", fgColor=teal)
        current_row += 1

        headers = ("类别", "项目", "规格", "数量", "单价 HKD", "金额 HKD", "备注", "审核")
        for column_index, header in enumerate(headers, start=1):
            cell = sheet.cell(current_row, column_index, header)
            cell.font = Font(name="Microsoft YaHei", bold=True, color=slate)
            cell.fill = PatternFill("solid", fgColor=pale_teal)
            cell.border = border
            cell.alignment = Alignment(horizontal="center", vertical="center")
        current_row += 1

        for row in section.payload.rows:
            line_calculation = next(
                (item for item in section.calculation.line_breakdown if item.line_id == row.id),
                None,
            )
            field_summary = " · ".join(
                f"{key}={value}" for key, value in row.fields.items() if value != "" and value is not None
            )
            values = (
                row.category,
                row.item_name,
                " · ".join(value for value in (row.specification, field_summary) if value),
                row.quantity,
                row.unit_price_hkd,
                row.amount_hkd,
                " · ".join(value for value in (
                    row.note,
                    f"公式：{line_calculation.formula}" if line_calculation else "",
                ) if value),
                section.reviewed_by or "—",
            )
            for column_index, value in enumerate(values, start=1):
                cell = sheet.cell(current_row, column_index, value)
                cell.font = Font(name="Microsoft YaHei", color=slate)
                cell.border = border
                cell.alignment = Alignment(vertical="center", wrap_text=True)
                if column_index in {5, 6}:
                    cell.number_format = '"HK$"#,##0.00'
            current_row += 1

        sheet.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=5)
        sheet.cell(
            current_row,
            1,
            f"折合 RMB ¥{section.calculation.total_rmb:.2f} · "
            f"USD ${section.calculation.total_usd:.2f} · 分段合计",
        ).alignment = Alignment(horizontal="right")
        total_cell = sheet.cell(current_row, 6, section.calculation.total_hkd)
        total_cell.number_format = '"HK$"#,##0.00'
        for column_index in range(1, 9):
            cell = sheet.cell(current_row, column_index)
            cell.font = Font(name="Microsoft YaHei", bold=True, color=slate)
            cell.fill = PatternFill("solid", fgColor="F8FAFC")
            cell.border = border
        current_row += 2

    widths = (16, 28, 22, 12, 14, 16, 30, 18)
    for column_index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(column_index)].width = width
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.fitToWidth = 1
    sheet.page_margins.left = 0.25
    sheet.page_margins.right = 0.25

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
