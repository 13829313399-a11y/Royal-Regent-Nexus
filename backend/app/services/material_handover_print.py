"""A static original-document print copy with an opaque handover QR in a reserved corner."""
import io
from pathlib import Path
from xml.sax.saxutils import escape

from app.schemas.material_handover import HandoverData
from app.services.document_tools.document_ir import ToolError
from app.services.material_handover_parser import validate_file

MAX_PAGES = 20
MAX_PDF_BYTES = 50 * 1024 * 1024
PAGE_MARGIN = 20
HEADER_TOP = 14
HEADER_GAP = 7
QR_SIZE = 58


def corrected(data, extraction):
    original = HandoverData.model_validate(extraction.get('data', {})).model_dump(mode='json')
    current = HandoverData.model_validate(data).model_dump(mode='json')
    headers = ('kind', 'source_no', 'document_date', 'purchase_order_no', 'contract_no', 'production_no', 'product_no', 'note')
    def lines(body):
        return [{k: v for k, v in line.items() if k not in ('id', 'source_line', 'purchase_detail_id')} for line in body['lines']]
    return any(current[k] != original[k] for k in headers) or lines(current) != lines(original)


def font_name():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfbase.ttfonts import TTFont
    candidate = Path('C:/Windows/Fonts/simhei.ttf')
    if candidate.is_file():
        name = 'HandoverPrintCJK'
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(candidate)))
        return name
    name = 'STSong-Light'
    if name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont(name))
    return name


def page_heading(width, font, corner, code, title, reference, note):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT, TA_RIGHT
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Drawing
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, Table, TableStyle

    left = corner == 'left'
    style = ParagraphStyle('print-heading', fontName=font, fontSize=10, leading=13,
        alignment=TA_LEFT if left else TA_RIGHT, wordWrap='CJK')
    heading = [
        Paragraph(escape(title), ParagraphStyle('print-title', parent=style, fontSize=14, leading=18)),
        Paragraph(escape(reference), style),
        Paragraph(escape(note), ParagraphStyle('print-note', parent=style, fontSize=8.5, leading=11)),
        Paragraph(escape(code), ParagraphStyle('print-code', parent=style, fontName='Helvetica', fontSize=7, leading=9)),
    ]
    # The widget includes a four-module quiet zone inside the white header.
    qr = Drawing(QR_SIZE, QR_SIZE)
    qr.add(QrCodeWidget(code, barWidth=QR_SIZE, barHeight=QR_SIZE, barLevel='M'))
    label_width = width - 2 * PAGE_MARGIN - QR_SIZE
    cells, widths = ([qr, heading], [QR_SIZE, label_width]) if left else ([heading, qr], [label_width, QR_SIZE])
    label_column = 1 if left else 0
    table = Table([cells], colWidths=widths)
    table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('LEFTPADDING' if left else 'RIGHTPADDING', (label_column, 0), (label_column, 0), 7),
        ('LINEBELOW', (0, 0), (-1, -1), .5, colors.HexColor('#77847f')),
    ]))
    return table


def draw_original_body(canvas, picture, width, height, top):
    from PIL import ImageChops
    from reportlab.lib.utils import ImageReader

    # Reclaim only pure-white outer rows. Marks, tinted scans and spacing between
    # original fields remain part of the same proportionally scaled image.
    with ImageChops.invert(picture) as inverted:
        ink = inverted.getbbox()
    padding = round(3 * picture.height / height)
    first = max(0, ink[1] - padding) if ink else 0
    last = min(picture.height, ink[3] + padding) if ink else picture.height
    source_height = height * (last - first) / picture.height
    scale = min((width - 16) / width, (top - 10) / source_height)
    print_width, print_height = width * scale, source_height * scale
    with picture.crop((0, first, picture.width, last)) as trimmed:
        canvas.drawImage(ImageReader(trimmed), (width - print_width) / 2, top - print_height,
                         width=print_width, height=print_height)


def source_pdf(name, content, folder, cancelled):
    import pypdfium2 as pdfium
    suffix = Path(name).suffix.lower()
    if suffix == '.pdf':
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted:
            raise ToolError('PRINT_ENCRYPTED', '加密 PDF 无法自动加码，请上传未加密打印副本')
        if any(field.get('/FT') == '/Sig' and field.get('/V') for field in (reader.get_fields() or {}).values()) or reader.trailer['/Root'].get('/Perms'):
            raise ToolError('PRINT_SIGNED', '数字签名 PDF 不自动改版，请上传未签名打印副本，原签名文件仍保留')
        for page in reader.pages:
            for annotation in page.get('/Annots', []):
                widget = annotation.get_object()
                parent = widget.get('/Parent', widget).get_object()
                if (widget.get('/FT') or parent.get('/FT')) == '/Sig' and (widget.get('/V') or parent.get('/V')):
                    raise ToolError('PRINT_SIGNED', '数字签名 PDF 不自动改版，请上传未签名打印副本')
        return pdfium.PdfDocument(content)
    if suffix in ('.xlsx', '.xls', '.docx'):
        from app.services.document_tools.office_engine import render_office
        if suffix != '.xls':
            from zipfile import ZipFile
            from xml.etree import ElementTree
            with ZipFile(io.BytesIO(content)) as archive:
                for member in archive.infolist():
                    if not member.filename.lower().endswith('.rels'):
                        continue
                    xml = archive.read(member)
                    if b'<!DOCTYPE' in xml.upper() or b'<!ENTITY' in xml.upper():
                        raise ToolError('PRINT_EXTERNAL', '原文包含不支持的外部定义，请导出 PDF 打印副本')
                    for relationship in ElementTree.fromstring(xml):
                        if relationship.get('TargetMode') == 'External' and not relationship.get('Type', '').endswith('/hyperlink'):
                            raise ToolError('PRINT_EXTERNAL', '原文引用外部图片或工作簿，请先嵌入内容或导出 PDF 后加码')
        path = folder / ('original' + suffix)
        path.write_bytes(content)
        output = folder / 'original.pdf'
        options = {'secure_load': True, 'print_mode': 'original', 'recalculate': False}
        if suffix == '.xlsx':
            from app.services.material_handover_template import print_options
            options.update(print_options(content))
        render_office(path, output, options, folder, cancelled)
        if output.stat().st_size > MAX_PDF_BYTES:
            raise ToolError('PRINT_SIZE', '原单打印文件过大，请调整打印区域或拆分文档')
        return pdfium.PdfDocument(str(output))
    from PIL import Image, ImageOps
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.lib.utils import ImageReader
    from reportlab.lib.pagesizes import A4, landscape
    with Image.open(io.BytesIO(content)) as raw:
        if raw.width * raw.height > 40_000_000 or getattr(raw, 'n_frames', 1) != 1:
            raise ToolError('PRINT_IMAGE', '请使用不超过 4000 万像素的静态图片')
        picture = ImageOps.exif_transpose(raw).convert('RGB')
        width, height = landscape(A4) if picture.width > picture.height else A4
        scale = min((width-24)/picture.width, (height-24)/picture.height)
        stream = io.BytesIO(); canvas = Canvas(stream, pagesize=(width, height))
        canvas.drawImage(ImageReader(picture), (width-picture.width*scale)/2, (height-picture.height*scale)/2,
                         width=picture.width*scale, height=picture.height*scale)
        canvas.save(); picture.close()
    return pdfium.PdfDocument(stream.getvalue())


def confirmation_pages(data, code, corner, font):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
    stream = io.BytesIO()
    width, height = landscape(A4)
    style = ParagraphStyle('confirm', fontName=font, fontSize=9.5, leading=13, wordWrap='CJK')
    emphasis = ParagraphStyle('confirm-emphasis', parent=style, fontSize=11, leading=14)
    def p(value, text_style=style): return Paragraph(escape(str(value or '')).replace('\n', '<br/>'), text_style)
    heading = page_heading(width, font, corner, code, '系统确认明细（核对附页）',
        f"原单号 {data['source_no']}", '仅供交接核对，不代表实际入库或发料')
    _, heading_height = heading.wrap(width, height)
    content = [p(f"{data['counterparty']} / {data.get('document_date') or ''}"), Spacer(1, 5)]
    content += [p(f"合同：{data.get('contract_no') or '未注明'} / 生产单：{data.get('production_no') or '未注明'} / 货号：{data.get('product_no') or '未注明'}"), p(data.get('note', '')), Spacer(1, 8)]
    if data.get('purchase_order_no'):
        content.append(p(f"采购订单号 {data['purchase_order_no']}"))
    rows = [[p(v) for v in ('物料编码', '名称 / 规格 / 颜色', '确认数量 / 单位', '缸号 / 卷号', '参考单价 / 计价单位 / 币种', '生产关联 / 说明')]]
    for line in data['lines']:
        category = {'FABRIC': '布料', 'ACCESSORY': '辅料', 'THREAD': '线'}.get(line.get('material_category'), '')
        references = [f'{label} {line[key]}' for key, label in (('purchase_order_no', '采购单'),
            ('contract_no', '合同'), ('production_no', '生产单'), ('plan_no', '跟踪号'), ('product_no', '货号')) if line.get(key)]
        if line.get('ordered_quantity'):
            references.append(f"下单 {line['ordered_quantity']} {line['unit']}")
        rows.append([p(line['item_code']), p('\n'.join(filter(None, (line['item_name'], category, line.get('specification'), line.get('color')))), emphasis),
            p(f"{line['quantity']} {line['unit']}", emphasis), p('\n'.join(filter(None, (line.get('lot'), line.get('roll_no'), line.get('roll_quantities'))))),
            p(f"{line.get('unit_price') or '未记录'} / {line.get('price_unit') or '未注明'} / {line.get('currency') or '未注明'}\n{line.get('price_note') or ''}"),
            p('\n'.join(filter(None, [*references, line.get('note')])))])
    table = Table(rows, colWidths=[105, 201, 104, 116, 114, width - 2 * PAGE_MARGIN - 640],
                  repeatRows=1, splitInRow=1)
    table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#eef5f1')),
        ('GRID', (0,0), (-1,-1), .3, colors.HexColor('#cbd9d2')), ('LEFTPADDING',(0,0),(-1,-1),6), ('RIGHTPADDING',(0,0),(-1,-1),6)]))
    content.append(table)
    def header(canvas, doc):
        heading.drawOn(canvas, PAGE_MARGIN, height - HEADER_TOP - heading_height)
    # A SimpleDocTemplate frame adds 6pt of its own padding.
    SimpleDocTemplate(stream, pagesize=(width, height), leftMargin=PAGE_MARGIN - 6,
        rightMargin=PAGE_MARGIN - 6, topMargin=HEADER_TOP + heading_height + HEADER_GAP - 6,
        bottomMargin=24).build(content, onFirstPage=header, onLaterPages=header)
    return stream.getvalue()


def render(name, content, data, extraction, code, corner, folder, cancelled=lambda: False):
    from pypdf import PdfReader, PdfWriter
    from reportlab.pdfgen.canvas import Canvas
    name = validate_file(name, content)
    if corner not in ('left', 'right'):
        raise ToolError('PRINT_CORNER', '二维码位置须为左上角或右上角')
    font = font_name(); stream = io.BytesIO()
    canvas = Canvas(stream, pageCompression=1)
    canvas.setTitle('原单加码打印副本')
    has_changes = corrected(data, extraction)
    pixel_count = 0
    with source_pdf(name, content, folder, cancelled) as original:
        count = len(original)
        if not 1 <= count <= MAX_PAGES:
            raise ToolError('PRINT_PAGES', '原单打印页数须为 1 至 20 页，请调整 Excel 打印区域或拆分后上传')
        for index in range(count):
            if cancelled(): raise ToolError('PRINT_CANCELLED', '原单加码准备已停止')
            page = original[index]
            width, height = page.get_size()
            if not 200 <= width <= 1600 or not 240 <= height <= 2000:
                raise ToolError('PRINT_PAGE_SIZE', '原单纸张大小超出打印范围，请导出常规纸张 PDF')
            canvas.setPageSize((width, height))
            title = '送货单原件 · 扫码交接' if data['kind'] == 'DELIVERY' else '领料单原件 · 扫码交接'
            note = f'第 {index + 1}/{count} 页'
            if has_changes:
                note += ' · 系统确认内容见附页'
            heading = page_heading(width, font, corner, code, title, f"原单号 {data['source_no']}", note)
            _, heading_height = heading.wrap(width, height)
            heading_bottom = height - HEADER_TOP - heading_height
            if height - heading_bottom >= height * .4:
                raise ToolError('PRINT_HEADER_SIZE', '原单号过长或纸张过小，请使用常规打印版式')
            pixel_count += width*height*2.4**2
            if pixel_count > 90_000_000:
                raise ToolError('PRINT_SIZE', '原单页面过大，请拆分后准备加码打印')
            bitmap = page.render(scale=2.4, draw_annots=True)
            try:
                with bitmap.to_pil().convert('RGB') as picture:
                    draw_original_body(canvas, picture, width, height, heading_bottom - HEADER_GAP)
            finally:
                bitmap.close()
                page.close()
            heading.drawOn(canvas, PAGE_MARGIN, heading_bottom)
            canvas.showPage()
        canvas.save()
    output = PdfWriter()
    output.append_pages_from_reader(PdfReader(io.BytesIO(stream.getvalue())))
    if has_changes:
        output.append_pages_from_reader(PdfReader(io.BytesIO(confirmation_pages(data, code, corner, font))))
    if len(output.pages) > 40:
        raise ToolError('PRINT_PAGES', '确认明细过长，请拆分文档后打印')
    final = io.BytesIO(); output.write(final); result = final.getvalue()
    if len(result) > MAX_PDF_BYTES:
        raise ToolError('PRINT_SIZE', '加码打印文件过大，请拆分文档后重试')
    return result
