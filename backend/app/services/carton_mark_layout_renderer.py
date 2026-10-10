"""Deterministic customer layout: fresh Excel fields, frozen customer artwork."""
import io
import re
from pathlib import Path
from collections import defaultdict
from xml.sax.saxutils import escape

from fastapi import HTTPException
from reportlab.lib.pagesizes import A4, A3, landscape
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.graphics.barcode import createBarcodeDrawing

from app.services.carton_mark import extract_excel_document_items, CartonMarkDocumentError
from app.services.carton_supplier_mark_layout import crop_reference, validate_reference
from app.schemas.carton_supplier_portal import MarkLayoutConfig

ALIASES = {
    "item": ("item", "item no", "item number", "货号"),
    "vendor": ("vendor name", "vendor", "厂商"),
    "product": ("product name", "product", "description", "品名"),
    "content": ("content", "装箱数"),
    "gtin": ("gtin", "ean", "upc"),
    "vendor_item": ("vendor product number", "vendor item", "厂家货号"),
    "dimensions": ("width/length/height", "length/width/height", "dimensions", "尺寸"),
    "gross_weight": ("grossweight", "gross weight", "g.w.", "毛重"),
}


def label(text):
    for key, aliases in ALIASES.items():
        for alias in aliases:
            match = re.match(r"^\s*" + re.escape(alias) + r"\s*(?::|：|$)\s*(.*)$", text, re.I)
            if match:
                return key, match[1].strip()
    return None, ""


def extract_fields(filename, content, mapping):
    try:
        extracted = extract_excel_document_items(filename, content)
    except CartonMarkDocumentError as exc:
        raise HTTPException(422, str(exc)) from exc
    if extracted.reviews:
        raise HTTPException(422, "Excel 有公式未保存计算结果，请重新计算并保存后生成")
    sheets = defaultdict(dict)
    from openpyxl.utils.cell import coordinate_to_tuple
    for item in extracted.items:
        sheet, coordinate = item.location.rsplit("!", 1)
        sheets[sheet][coordinate_to_tuple(coordinate)] = item.text
    records = []
    for sheet, cells in sheets.items():
        candidates = defaultdict(list)
        for (row, col), text in cells.items():
            key, inline = label(text)
            if not key:
                continue
            value = inline
            if not value:
                nearby = sorted((c, t) for (r, c), t in cells.items() if r == row and col < c < col + 5)
                for _, text_right in nearby:
                    if label(text_right)[0]:
                        break
                    value += (" " if value else "") + text_right
                if not value:
                    next_label = min((c for (r, c), t in cells.items() if r == row and c > col and label(t)[0]), default=col + 5)
                    value = " ".join(t for (r, c), t in sorted(cells.items()) if r == row + 1 and col <= c < next_label)
            if key in {"dimensions", "gross_weight"} and not re.search(r"\d", value):
                value = ""
            if value:
                candidates[key].append(value.strip())
        fields = {}
        for key in ALIASES:
            if mapping.get(key):
                value = cells.get(coordinate_to_tuple(mapping[key].upper()), "")
                if not value and key not in {"dimensions", "gross_weight"}:
                    raise HTTPException(422, f"{sheet}!{mapping[key]} 缺少 {key} 内容，请检查客户字段位置")
                fields[key] = label(value)[1] if label(value)[0] == key else value
            else:
                values = list(dict.fromkeys(candidates[key]))
                if len(values) > 1:
                    raise HTTPException(422, f"{sheet} 的 {key} 有多个不同内容，请在客户模板固定字段位置")
                fields[key] = values[0] if values else ""
        if any(fields.values()):
            if not fields["item"] or not fields["product"]:
                raise HTTPException(422, f"{sheet} 未识别货号或品名，请在客户模板固定 Excel 字段位置")
            records.append((sheet, fields))
    if not records or len(records) > 50:
        raise HTTPException(422, "Excel 须包含 1–50 张可识别货号、品名的可见工作表")
    return records


def excel_logo(filename, content, selected_sheets):
    if not filename.lower().endswith(".xlsx"):
        return None
    from openpyxl import load_workbook
    book = load_workbook(io.BytesIO(content), keep_links=False)
    try:
        candidates = []
        for sheet in book.worksheets:
            if sheet.sheet_state != "visible" or sheet.title not in selected_sheets:
                continue
            vendor_rows = [cell.row for row in sheet for cell in row if cell.value and label(str(cell.value))[0] == "vendor"]
            if not vendor_rows:
                continue
            for image in sheet._images:
                anchor = getattr(image.anchor, "_from", None)
                if anchor and anchor.row + 1 < min(vendor_rows):
                    candidates.append(image._data())
        unique = list(dict.fromkeys(candidates))
        return unique[0] if len(unique) == 1 else None
    finally:
        book.close()


def render(original):
    config = MarkLayoutConfig.model_validate(original["layout"]["config"])
    reference = original["layout"]["reference_bytes"]
    validate_reference(reference, config)
    records = extract_fields(original["excel_file_name"], original["excel_bytes"], config.field_cells)
    skipped_sheets = 0
    if len(records) > 1:
        matching = [(sheet, fields) for sheet, fields in records if fields["item"].strip().casefold() == original["item_no"].strip().casefold()]
        if not matching:
            raise HTTPException(422, "Excel 包含多个货号，但没有工作表匹配所选订单 ITEM，请选择正确订单或单货号原稿")
        skipped_sheets = len(records) - len(matching)
        records = matching
    logo = crop_reference(reference, config.reference_page, config.logo_region.model_dump()) if config.logo_region else excel_logo(original["excel_file_name"], original["excel_bytes"], {sheet for sheet, _ in records})
    stamp = crop_reference(reference, config.reference_page, config.stamp_region.model_dump()) if config.stamp_region else None
    warnings = []
    if skipped_sheets:
        warnings.append(f"仅生成所选订单 ITEM，已跳过 {skipped_sheets} 张其他货号工作表")
    if not logo:
        warnings.append("未找到唯一 LOGO，请在客户历史稿中选取 LOGO 区域后保存新版模板")
    for sheet, fields in records:
        missing = [key for key in ("vendor", "content", "gtin", "vendor_item", "dimensions", "gross_weight") if not fields[key]]
        if missing:
            titles = dict(vendor="厂商", content="装箱数", gtin="GTIN", vendor_item="厂家货号", dimensions="尺寸", gross_weight="毛重")
            warnings.append(f"{sheet} 缺少{'、'.join(titles[key] for key in missing)}，PDF 标记为待补，请补齐后再审核")
        if fields["item"] != original["item_no"]:
            warnings.append(f"{sheet} 的 Excel 货号与采购订单 ITEM 不一致，请核实")
    cjk_font = "STSong-Light"
    cjk_path = Path("C:/Windows/Fonts/simhei.ttf")
    if cjk_path.exists():
        cjk_font = "MarkCJK"
        if cjk_font not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(cjk_font, str(cjk_path)))
    else:
        pdfmetrics.registerFont(UnicodeCIDFont(cjk_font))
    size = A3 if config.paper == "A3" else A4
    if config.mode == "front_side":
        size = landscape(size)
    stream = io.BytesIO()
    canvas = Canvas(stream, pagesize=size, pageCompression=1)
    canvas.setTitle(f"{original['layout']['name']} V{original['layout']['version']} - {original['contract_no']}")
    width, height = size

    def text_box(text, x, top, w, h, *, size=None, bold=False, centered=False):
        font = config.font
        if bold and font == "Helvetica":
            font = "Helvetica-Bold"
        for fontsize in range(round(size or config.font_size), 6, -1):
            formatted = re.sub(r"[^\x00-\x7f]+", lambda match: f'<font name="{cjk_font}">{match[0]}</font>', escape(text)).replace("\n", "<br/>")
            paragraph = Paragraph(formatted, ParagraphStyle("mark", fontName=font,
                fontSize=fontsize, leading=fontsize * 1.2, alignment=1 if centered else 0, splitLongWords=True))
            _, needed = paragraph.wrap(w, h)
            if needed <= h:
                paragraph.drawOn(canvas, x, top - needed)
                return
        raise HTTPException(422, "内容过长，无法完整放入客户模板，请增大纸张或调整版式")

    def artwork(content, x, top, w, h):
        if content:
            canvas.drawImage(ImageReader(io.BytesIO(content)), x, top - h, width=w, height=h,
                preserveAspectRatio=True, anchor="c", mask="auto")

    def panel(fields, x, top, w, h, side):
        original_frame = config.frame_style == "original_red"
        footer_height = 20 * mm if original_frame else 0
        canvas.saveState()
        canvas.setLineWidth(1.1 if original_frame else .8)
        if original_frame:
            canvas.setStrokeColorRGB(.94, .23, .14)
        canvas.rect(x, top - h, w, h)
        if original_frame:
            header_y, footer_y = top - 21 * mm, top - h + footer_height
            canvas.line(x, header_y, x + w, header_y)
            canvas.line(x, footer_y, x + w, footer_y)
            if not side:
                fold = canvas.beginPath()
                fold.moveTo(x, header_y); fold.lineTo(x - 8 * mm, header_y - 10 * mm)
                fold.lineTo(x - 8 * mm, footer_y + 10 * mm); fold.lineTo(x, footer_y)
                canvas.drawPath(fold)
        canvas.restoreState()
        canvas.setLineWidth(.8)
        padding = 5 * mm; inner = w - padding * 2
        text_box(("侧唛" if side else "正唛") + f" x {config.side_copies if side else config.front_copies}", x + padding, top - (7 * mm if original_frame else padding), inner, 8 * mm, size=13, centered=True)
        if original_frame:
            compact = h < 160 * mm
            artwork(logo, x + padding, top - 25 * mm, inner, (15 if compact else 18) * mm)
            y = top - (43 if compact else 46) * mm
            row_h = (8 if compact else 10) * mm
            for title, value in (("Vendor name", fields["vendor"]), ("Product name", fields["product"]), ("Content", fields["content"])):
                canvas.rect(x + padding, y - row_h, inner, row_h)
                text_box(f"{title}: {value or '待补'}", x + padding + 2 * mm, y - 2 * mm, inner - 4 * mm, row_h - 4 * mm)
                y -= row_h
            double_h = (13 if compact else 16) * mm
            for pair in ((("GTIN", fields["gtin"]), ("Vendor product number", fields["vendor_item"])),
                    (("Width / Length / Height", fields["dimensions"]), ("Gross weight", fields["gross_weight"]))):
                canvas.rect(x + padding, y - double_h, inner, double_h)
                canvas.line(x + padding + inner / 2, y, x + padding + inner / 2, y - double_h)
                for column, (title, value) in enumerate(pair):
                    column_x = x + padding + column * inner / 2 + 2 * mm
                    text_box(title + ":", column_x, y - 2 * mm, inner / 2 - 4 * mm, double_h / 2 - 2 * mm, size=min(config.font_size, 10))
                    text_box(value or "待补", column_x, y - double_h / 2 - 1 * mm, inner / 2 - 4 * mm, double_h / 2 - 2 * mm)
                y -= double_h
            canvas.rect(x + padding, y - 21 * mm, inner, 21 * mm)
            barcode_top = y - 1 * mm
            lower_top = y - 25 * mm
        else:
            artwork(logo, x + padding, top - 15 * mm, inner, 23 * mm)
            table_top = top - 43 * mm
            rows_data = [("Vendor name", fields["vendor"]), ("Product name", fields["product"]),
                ("Content", fields["content"]), ("GTIN", fields["gtin"]),
                ("Vendor product number", fields["vendor_item"]), ("Width / Length / Height", fields["dimensions"]),
                ("Gross weight", fields["gross_weight"])]
            row_h = 12 * mm if h < 210 * mm else 16 * mm
            label_w = min(inner * .43, 51 * mm)
            for index, (title, value) in enumerate(rows_data):
                y = table_top - index * row_h
                canvas.rect(x + padding, y - row_h, inner, row_h)
                canvas.line(x + padding + label_w, y, x + padding + label_w, y - row_h)
                text_box(title, x + padding + 2 * mm, y - 2 * mm, label_w - 4 * mm, row_h - 4 * mm, size=min(config.font_size, 10))
                text_box(value or "待补", x + padding + label_w + 2 * mm, y - 2 * mm, inner - label_w - 4 * mm, row_h - 4 * mm)
            barcode_top = table_top - 7 * row_h - 4 * mm
            lower_top = barcode_top - 23 * mm
        if config.barcode != "none" and fields["gtin"]:
            value = fields["gtin"].strip()
            if config.barcode == "ITF14" and not re.fullmatch(r"\d{14}", value):
                raise HTTPException(422, "客户模板使用 ITF14，Excel GTIN 必须为完整 14 位数字")
            if not re.fullmatch(r"[\x20-\x7e]{1,80}", value):
                raise HTTPException(422, "条码号码包含不支持的字符或过长，请核实 Excel GTIN")
            drawing = createBarcodeDrawing("I2of5" if config.barcode == "ITF14" else "Code128", value=value,
                checksum=False, barWidth=.35 * mm, barHeight=13 * mm, humanReadable=False)
            scale = min(1, inner / drawing.width)
            if .35 * scale < .2:
                raise HTTPException(422, "条码过宽，缩小后无法可靠识读，请增大纸张或改为分别一页")
            canvas.saveState(); canvas.translate(x + padding + (inner - drawing.width * scale) / 2, barcode_top - 13 * mm)
            canvas.scale(scale, 1); drawing.drawOn(canvas, 0, 0); canvas.restoreState()
            text_box(value, x + padding, barcode_top - 14 * mm, inner, 6 * mm, size=10, centered=True)
        if side and config.side_address:
            available = lower_top - (top - h + footer_height + (2 * mm if original_frame else padding))
            text_box(config.side_address, x + padding, lower_top, inner, available, size=9)
        elif not side and stamp:
            if original_frame:
                artwork(stamp, x + padding, top - h + footer_height - 1 * mm, inner, footer_height - 2 * mm)
            else:
                artwork(stamp, x + padding, lower_top, inner, min(22 * mm, lower_top - (top - h + padding)))

    for _, fields in records:
        pages = [False, True] if config.mode == "separate_pages" else [False]
        for side in pages:
            text_box(f"{original['contract_no']}   ITEM: {fields['item']}", 10 * mm, height - 8 * mm, width - 20 * mm, 10 * mm, size=14, bold=True)
            top, panel_height = height - 24 * mm, height - 37 * mm - (10 * mm if config.instructions else 0)
            if config.mode == "front_side":
                usable = width - 20 * mm; front = usable * config.front_percent / 100
                panel(fields, 10 * mm, top, front, panel_height, False)
                panel(fields, 10 * mm + front, top, usable - front, panel_height, True)
            else:
                panel(fields, 10 * mm, top, width - 20 * mm, panel_height, side)
            if config.instructions:
                text_box(config.instructions, 10 * mm, 21 * mm, width - 20 * mm, 9 * mm, size=8)
            text_box(f"{original['layout']['name']} V{original['layout']['version']}  /  待核对、审核", 10 * mm, 9 * mm, width - 20 * mm, 6 * mm, size=7)
            canvas.showPage()
    canvas.save()
    content = stream.getvalue()
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(413, "生成 PDF 超过 20 MB，请缩小客户素材后重试")
    if config.barcode != "none":
        warnings.append("条码已按 Excel GTIN 重新生成，请用实际打印件扫码验证")
    return content, len(records) * (2 if config.mode == "separate_pages" else 1), list(dict.fromkeys(warnings))
