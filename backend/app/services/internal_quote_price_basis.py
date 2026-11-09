"""Human-readable frozen prices and per-carton selection in exported quotations."""
import json
from math import ceil
from openpyxl.styles import Font, PatternFill, Alignment
from app.services.internal_quote_paper import paper_reference


def append_price_basis(workbook, quote, sections, snapshot):
    sheet = workbook.create_sheet("采用价目表")
    sheet.sheet_state = "visible"
    widths = {"A":28,"B":42,"C":34,"D":28}
    def row(values):
        sheet.append(values)
        lines = max(ceil(sum(2 if ord(c) > 127 else 1 for c in str(value)) / width) for value, width in zip(values, widths.values()))
        sheet.row_dimensions[sheet.max_row].height = min(409, max(24, lines * 16))
        for cell in sheet[sheet.max_row]:
            if isinstance(cell.value, str):
                cell.data_type = "s"  # User labels never become executable formulas.
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    row(["本报价采用价目表", getattr(quote, "quote_no", ""), getattr(quote, "product_name", ""), getattr(quote, "version_label", "")])
    row(["范围", "本款冻结价目；基础价目更新不自动覆盖本款", "基础价目版本", snapshot.get("pricing_baseline_revision", "未记录")])
    row(["材料", "具体料型", "HKD/lb", "来源"])
    for key, price in snapshot.get("material_prices", {}).items():
        material, _, grade = key.partition("|")
        row([material, grade, float(price), "本报价价格快照"])
    row(["机型范围", "机型", "HKD/班", "来源"])
    for machine in snapshot.get("machine_prices", []):
        row([machine.get("range", ""), machine.get("machine", ""), float(machine.get("shift_price_hkd", 0)), "本报价价格快照"])
    row(["纸材目录", "系数 HKD", "来源／适用说明", ""])
    for paper in snapshot.get("paper_prices", []):
        row([paper.get("name", ""), float(paper.get("price_factor_hkd", 0)), paper.get("remark", ""), "本报价价格快照"])
    row(["纸价口径", "尺寸以英寸计算，展开面积÷1000×HKD系数。税项沿用原规则。", "", ""])
    row(["使用项目", "采用纸材", "采用系数 HKD", "每箱数量／平卡用量"])
    sales = next((s for s in sections if s.department == "sales" and getattr(s, "is_required", True)), None)
    payload = json.loads(sales.payload_json or "{}") if sales else {}
    main = payload.get("paper_price_factor", snapshot.get("paper_price_factor", "2.75"))
    for i, carton in enumerate(payload.get("cartons", [])):
        factor, name = paper_reference(carton, snapshot, main if i == 0 else payload.get("inner_paper_price_factor", main), strict=False)
        row([carton.get("item", "纸箱"), name, float(factor), carton.get("qty_per_carton", "")])
        for flat in carton.get("flat_cards", []):
            factor, name = paper_reference(flat, snapshot, payload.get("flat_card_price_factor", main), strict=False)
            row([str(carton.get("item", "纸箱")) + " / " + str(flat.get("name", "平卡")), name, float(factor), flat.get("quantity", 1)])
    row(["箱价公式", "(长+宽+2)×(宽+高+1)×2×采用系数÷1000；每件成本再除每箱数量。", "", ""])
    row(["平卡公式", "长×宽×用量×采用系数÷1000；有人工调价时以报价采用金额为准。", "", ""])
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="006559")
    for column, width in widths.items():
        sheet.column_dimensions[column].width = width
    sheet.freeze_panes = "A3"
