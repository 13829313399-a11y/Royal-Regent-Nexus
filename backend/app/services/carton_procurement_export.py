from __future__ import annotations

from datetime import datetime
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from app.models.carton_procurement import CartonOrder, CartonOrderLine


XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
FACTORY_NAMES = {
    "huakang-a": "华康 A 厂",
    "huakang-b": "华康 B 厂",
    "huakang-c": "华康 C 厂",
    "huakang-d": "华康 D 厂",
    "huadeng": "华登厂",
    "huaxing": "华兴厂",
}


def build_purchase_order_workbook(
    order: CartonOrder,
    lines: list[CartonOrderLine],
    *,
    generated_at: datetime,
) -> bytes:
    workbook = Workbook()
    workbook.properties.creator = "Royal Regent Nexus"
    workbook.properties.title = f"{order.order_no} 纸箱采购单"
    workbook.calculation.fullCalcOnLoad = True
    workbook.calculation.forceFullCalc = True

    sheet = workbook.active
    sheet.title = "纸箱采购单"
    sheet.sheet_view.showGridLines = False
    sheet.freeze_panes = "A10"

    teal = "087F74"
    teal_dark = "075E57"
    teal_light = "E8F6F4"
    slate = "475569"
    slate_light = "F1F5F9"
    border_color = "CBD5E1"
    white = "FFFFFF"
    thin = Side(style="thin", color=border_color)
    medium = Side(style="medium", color=teal)

    sheet.merge_cells("A1:H1")
    sheet["A1"] = f"Royal Regent Nexus · {FACTORY_NAMES.get(order.factory_id, order.factory_id)}纸箱采购单"
    sheet["A1"].font = Font(name="Microsoft YaHei", size=18, bold=True, color=white)
    sheet["A1"].fill = PatternFill("solid", fgColor=teal_dark)
    sheet["A1"].alignment = Alignment(horizontal="center", vertical="center")
    sheet.row_dimensions[1].height = 34

    sheet.merge_cells("A2:H2")
    sheet["A2"] = "PAPER PACKAGING PURCHASE ORDER"
    sheet["A2"].font = Font(name="Arial", size=9, bold=True, color=teal_dark)
    sheet["A2"].fill = PatternFill("solid", fgColor=teal_light)
    sheet["A2"].alignment = Alignment(horizontal="center", vertical="center")
    sheet.row_dimensions[2].height = 21

    information_rows = [
        (4, (("A4", "采购单号"), ("B4", order.order_no), ("D4", "下单日期"), ("E4", order.order_date), ("F4", "计划交期"), ("G4", order.due_date))),
        (5, (("A5", "采购厂区"), ("B5", FACTORY_NAMES.get(order.factory_id, order.factory_id)), ("D5", "供应商"), ("E5", order.supplier_name_snapshot))),
        (6, (("A6", "客户"), ("B6", order.customer_name), ("D6", "合同号"), ("E6", order.contract_no), ("G6", "货号"), ("H6", order.item_no))),
        (7, (("A7", "产品名称"), ("B7", order.product_name or "—"), ("D7", "产品订单数量"), ("E7", float(order.product_order_quantity)), ("G7", "流程状态"), ("H7", "已下单"))),
    ]
    for _, values in information_rows:
        for cell_ref, value in values:
            sheet[cell_ref] = value

    for merged_range in ("B4:C4", "G4:H4", "B5:C5", "E5:H5", "B6:C6", "E6:F6", "B7:C7", "E7:F7"):
        sheet.merge_cells(merged_range)

    label_cells = ("A4", "D4", "F4", "A5", "D5", "A6", "D6", "G6", "A7", "D7", "G7")
    for cell_ref in label_cells:
        cell = sheet[cell_ref]
        cell.font = Font(name="Microsoft YaHei", size=9, bold=True, color=slate)
        cell.fill = PatternFill("solid", fgColor=slate_light)
        cell.alignment = Alignment(horizontal="left", vertical="center")
    for row in sheet.iter_rows(min_row=4, max_row=7, min_col=1, max_col=8):
        for cell in row:
            cell.border = Border(bottom=thin)
            if cell.coordinate not in label_cells:
                cell.font = Font(name="Microsoft YaHei", size=10, color="0F172A")
                cell.alignment = Alignment(horizontal="left", vertical="center")
    sheet["E7"].number_format = (
        "#,##0" if order.product_order_quantity == order.product_order_quantity.to_integral_value() else "#,##0.######"
    )

    headers = ["序号", "纸品类型", "纸质", "规格", "每箱个数", "产品订单数量", "纸箱数量", "单位"]
    for column, header in enumerate(headers, start=1):
        cell = sheet.cell(row=9, column=column, value=header)
        cell.font = Font(name="Microsoft YaHei", size=9, bold=True, color=white)
        cell.fill = PatternFill("solid", fgColor=teal)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = Border(left=thin, right=thin, top=medium, bottom=medium)
    sheet.row_dimensions[9].height = 28

    first_line_row = 10
    for index, line in enumerate(lines, start=1):
        row = first_line_row + index - 1
        values = [
            index,
            line.packaging_type,
            line.paper_quality,
            f"{line.specification} {line.dimension_unit}".strip(),
            float(line.usage_quantity),
            float(order.product_order_quantity),
            None,
            line.unit,
        ]
        for column, value in enumerate(values, start=1):
            cell = sheet.cell(row=row, column=column, value=value)
            cell.font = Font(name="Microsoft YaHei", size=9, color="0F172A")
            cell.alignment = Alignment(
                horizontal="center" if column in {1, 8} else "right" if column in {5, 6, 7} else "left",
                vertical="center",
                wrap_text=column == 4,
            )
            cell.border = Border(left=thin, right=thin, bottom=thin)
            if index % 2 == 0:
                cell.fill = PatternFill("solid", fgColor="F8FAFC")
        sheet.cell(row=row, column=7, value=f"=ROUNDUP(F{row}/E{row},0)")
        sheet.cell(row=row, column=5).number_format = (
            "#,##0" if line.usage_quantity == line.usage_quantity.to_integral_value() else "#,##0.######"
        )
        sheet.cell(row=row, column=6).number_format = (
            "#,##0" if order.product_order_quantity == order.product_order_quantity.to_integral_value() else "#,##0.######"
        )
        sheet.cell(row=row, column=7).number_format = "#,##0"
        sheet.row_dimensions[row].height = 24

    footer_row = first_line_row + len(lines) + 1
    sheet.merge_cells(start_row=footer_row, start_column=1, end_row=footer_row, end_column=8)
    sheet.cell(row=footer_row, column=1, value=f"备注：{order.note or '无'}")
    sheet.cell(row=footer_row, column=1).font = Font(name="Microsoft YaHei", size=9, color=slate)
    sheet.cell(row=footer_row, column=1).alignment = Alignment(vertical="center", wrap_text=True)
    sheet.cell(row=footer_row, column=1).fill = PatternFill("solid", fgColor=slate_light)
    sheet.row_dimensions[footer_row].height = 30

    generated_row = footer_row + 2
    sheet.merge_cells(start_row=generated_row, start_column=1, end_row=generated_row, end_column=3)
    sheet.cell(row=generated_row, column=1, value=f"制单人：{order.created_by_name}")
    sheet.merge_cells(start_row=generated_row, start_column=4, end_row=generated_row, end_column=8)
    sheet.cell(row=generated_row, column=4, value=f"系统生成时间：{generated_at.strftime('%Y-%m-%d %H:%M')}")
    for cell_ref in (f"A{generated_row}", f"D{generated_row}"):
        sheet[cell_ref].font = Font(name="Microsoft YaHei", size=9, color=slate)

    notice_row = generated_row + 2
    sheet.merge_cells(start_row=notice_row, start_column=1, end_row=notice_row, end_column=8)
    sheet.cell(
        row=notice_row,
        column=1,
        value="本采购单由系统正式订单自动生成，无需供应商回签确认；后续按计划交期进入排期核对、收料和库存流程。",
    )
    sheet.cell(row=notice_row, column=1).font = Font(name="Microsoft YaHei", size=9, bold=True, color=teal_dark)
    sheet.cell(row=notice_row, column=1).fill = PatternFill("solid", fgColor=teal_light)
    sheet.cell(row=notice_row, column=1).alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    sheet.row_dimensions[notice_row].height = 32

    widths = [8, 15, 16, 30, 14, 16, 16, 18]
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width

    sheet.print_area = f"A1:H{notice_row}"
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.paperSize = sheet.PAPERSIZE_A4
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 1
    sheet.page_margins.left = 0.25
    sheet.page_margins.right = 0.25
    sheet.page_margins.top = 0.35
    sheet.page_margins.bottom = 0.35

    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()
