"""Bounded, non-executable PDF/XLSX exports of private saved artifacts."""
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
import re
from xml.sax.saxutils import escape

from . import artifact_data
from .errors import AssistantError

MAX_BYTES = 20 * 1024 * 1024


def render(content, kind, title, refs, format, datasets=()):
    from .artifacts import source_lines
    from reportlab.platypus.doctemplate import LayoutError
    sources = source_lines(refs)
    try:
        value = workbook(content, title, sources, datasets) if format == 'xlsx' else pdf(content, title, sources, datasets, kind)
    except (ValueError, OverflowError, LayoutError) as exc:
        raise AssistantError('export_failed', '导出内容无法排版，已保留成果；请检查长表或正文后重试。', 422) from exc
    if len(value) > MAX_BYTES:
        raise AssistantError('export_size_limit', '导出超过20MB，成果已保留；请缩小成果内容。', 413)
    return value, ('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' if format == 'xlsx' else 'application/pdf')


def workbook(content, title, sources, datasets):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.chart import BarChart, Reference
    book = Workbook()
    notes = book.active
    notes.title = '成果'

    def row(sheet, values, header=False):
        number = sheet.max_row + 1 if sheet.max_row > 1 or sheet.cell(1, 1).value is not None else 1
        for column, value in enumerate(values, 1):
            # Explicit string type prevents formulas, DDE and external-link cells.
            target = sheet.cell(number, column, artifact_data.cell(value))
            target.data_type = 's'
            target.number_format = '@'
            target.alignment = Alignment(vertical='top', wrap_text=True)
            if header:
                target.fill = PatternFill('solid', fgColor='185448')
                target.font = Font(name='Microsoft YaHei', color='FFFFFF', bold=True)
            else:
                target.font = Font(name='Microsoft YaHei', color='183E35', size=11)
        sheet.row_dimensions[number].height = 30 if header else 32
        return number

    row(notes, [title], True)
    row(notes, ['说明正文（可人工编辑）；业务数值以原查询数据表为准。'])
    for line in content.splitlines() or ['']:
        for start in range(0, max(1, len(line)), 30000):
            row(notes, [line[start:start + 30000]])
    notes.column_dimensions['A'].width = 110
    for index, dataset in enumerate(datasets, 1):
        sheet = book.create_sheet('数据' + str(index))
        row(sheet, [dataset['title']], True)
        for line in artifact_data.scope_lines(dataset):
            row(sheet, [line])
        row(sheet, ['指标', '原值', '单位', '口径'], True)
        numeric_rows = {}
        for metric in dataset['metrics']:
            number = row(sheet, [metric['label'], metric['value'], metric['unit'],
                dataset['definitions'].get(metric['definition_id'], metric['definition_id'])])
            try:
                value = Decimal(str(metric['value']))
                if metric['status'] == 'known' and value.is_finite() and len(value.as_tuple().digits) <= 15:
                    numeric_rows[metric['key']] = float(value)
            except (InvalidOperation, ValueError, TypeError):
                pass
        # One bounded, unit-consistent chart; exact values remain in the literal original-value column.
        group = next((g for g in dataset['charts'] if g['metric_keys'] and all(k in numeric_rows for k in g['metric_keys'])), None)
        if group:
            chart = BarChart()
            chart.title = dataset['title'] + '（' + group['unit'] + '）'
            chart.y_axis.title = group['unit']
            chart.height, chart.width = 8, 16
            names = {metric['key']: metric['label'] for metric in dataset['metrics']}
            for number, key in enumerate(group['metric_keys'], 2):
                sheet.cell(number, 6, names[key]).data_type = 's'
                sheet.cell(number, 7, numeric_rows[key])
            chart.add_data(Reference(sheet, min_col=7, min_row=2, max_row=1 + len(group['metric_keys'])))
            chart.set_categories(Reference(sheet, min_col=6, min_row=2, max_row=1 + len(group['metric_keys'])))
            chart.legend = None
            chart.visible_cells_only = False  # The numeric helper columns are intentionally hidden.
            sheet.add_chart(chart, 'H2')
        row(sheet, ['明细：仅含当时实际返回的记录'], True)
        row(sheet, [column['label'] for column in dataset['columns']], True)
        for record in dataset['rows']:
            row(sheet, [artifact_data.display(dataset, column['key'], record.get(column['key'])) for column in dataset['columns']])
        for unknown in dataset['unknown_fields']:
            row(sheet, ['待核对', unknown['field'], unknown['reason']])
        for letter in ('A', 'B', 'C'):
            sheet.column_dimensions[letter].width = 24
        sheet.column_dimensions['D'].width = 65
        sheet.column_dimensions['F'].hidden = True
        sheet.column_dimensions['G'].hidden = True
        sheet.freeze_panes = 'A7'
        sheet.sheet_view.showGridLines = False
        sheet.print_options.horizontalCentered = True
        sheet.page_setup.orientation = 'landscape'
        sheet.page_setup.fitToWidth = 1
        sheet.sheet_properties.pageSetUpPr.fitToPage = True
    source_sheet = book.create_sheet('来源')
    row(source_sheet, ['来源与复核边界'], True)
    for line in sources.splitlines() or ['没有登记来源；不能据此声称已经核实。']:
        row(source_sheet, [line])
    source_sheet.column_dimensions['A'].width = 110
    for sheet in book:
        sheet.sheet_view.showGridLines = False
    stream = BytesIO()
    book.save(stream)
    return stream.getvalue()


def font_name():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfbase.ttfonts import TTFont
    for candidate in (Path('C:/Windows/Fonts/simhei.ttf'),
                      Path('/usr/share/fonts/truetype/noto/NotoSansSC-Regular.ttf')):
        if candidate.is_file():
            name = 'YaolingArtifactCJK'
            if name not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(name, str(candidate)))
            return name
    name = 'STSong-Light'
    if name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont(name))
    return name


def pdf(content, title, sources, datasets, kind):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, LongTable, TableStyle
    from reportlab.graphics.shapes import Drawing, Rect, String, Line
    font = font_name()
    stream = BytesIO()
    document = SimpleDocTemplate(stream, pagesize=A4, rightMargin=36, leftMargin=36,
        topMargin=42, bottomMargin=42, title=title, author='Royal Regent Nexus')
    normal = ParagraphStyle('YLBody', fontName=font, fontSize=9, leading=15,
        textColor=colors.HexColor('#183E35'), wordWrap='CJK', spaceAfter=6)
    heading = ParagraphStyle('YLHeading', parent=normal, fontSize=13, leading=19, spaceBefore=12)
    story = []

    def paragraph(value, style=normal):
        return Paragraph(escape(str(value)).replace('\n', '<br/>'), style)

    def prose(value):
        # The CJK font does not contain color emoji. Omit decorative Markdown
        # emoji instead of exporting missing-glyph boxes; data cells stay exact.
        value = str(value).translate(str.maketrans({'➕': '+', '➖': '-', '✖': '×', '➗': '÷', '➡': '→', '☑': '[已完成]', '☐': '[待处理]'}))
        return re.sub(r'[\U0001F000-\U0001FAFF\u2600-\u27BF]', '', value).replace('**', '').replace('`', '')

    def table(rows, markdown_cells=False):
        if not rows:
            return
        width = max(len(row) for row in rows)
        if width > 6:
            for start in range(1, width, 5):
                table([[row[index] if index < len(row) else '' for index in [0, *range(start, min(width, start + 5))]] for row in rows], markdown_cells)
            return
        entries = [[paragraph(prose(artifact_data.cell(v)) if markdown_cells else artifact_data.cell(v)) for v in row] + [paragraph('')] * (width - len(row)) for row in rows]
        value = LongTable(entries, colWidths=[document.width / width] * width, repeatRows=1, splitInRow=1, hAlign='LEFT')
        value.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E6EEE8')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('GRID', (0, 0), (-1, -1), .3, colors.HexColor('#CAD8CF')),
            ('LEFTPADDING', (0, 0), (-1, -1), 5), ('RIGHTPADDING', (0, 0), (-1, -1), 5)]))
        story.extend([value, Spacer(1, 10)])

    story.append(paragraph(title, heading))
    story.append(paragraph('说明正文（可人工编辑）；下方原查询数据保留其原始范围和时间。'))
    # Saved prose is text, never an HTML document or executable model output.
    from .artifacts import table_cells
    lines, index, fenced = content.splitlines(), 0, False
    while index < len(lines):
        line = lines[index]
        if re.match(r'^\s*(`{3,}|~{3,})', line):
            fenced = not fenced
            index += 1
            continue
        if not fenced and index + 1 < len(lines) and '|' in line:
            header, separator = table_cells(line), table_cells(lines[index + 1])
            if header and len(header) == len(separator) and all(re.fullmatch(r':?-+:?', v) for v in separator):
                values = [header]
                index += 2
                while index < len(lines) and lines[index].strip() and '|' in lines[index]:
                    values.append((table_cells(lines[index]) + [''] * len(header))[:len(header)])
                    index += 1
                table(values, True)
                continue
        clean = prose(line).strip()
        if clean:
            story.append(paragraph(clean.lstrip('#').strip(), heading if clean.startswith('#') else normal))
        index += 1
    for dataset in datasets:
        story.append(paragraph('原查询数据 · ' + dataset['title'], heading))
        for line in artifact_data.scope_lines(dataset):
            story.append(paragraph(line))
        table([['指标', '原值', '单位', '口径']] + [[m['label'], m['value'], m['unit'],
            dataset['definitions'].get(m['definition_id'], m['definition_id'])] for m in dataset['metrics']])
        if kind == 'chart' and dataset['charts']:
            group = dataset['charts'][0]
            metrics = [m for m in dataset['metrics'] if m['key'] in group['metric_keys']][:16]
            scale = max((abs(float(m['value'])) for m in metrics), default=1) or 1
            drawing = Drawing(document.width, 28 * len(metrics) + 25)
            drawing.add(String(0, drawing.height - 10, '单位：' + group['unit'], fontName=font, fontSize=9))
            for index, metric in enumerate(metrics):
                y = drawing.height - 35 - index * 28
                value = float(metric['value'])
                drawing.add(String(0, y, metric['label'], fontName=font, fontSize=8))
                drawing.add(Line(245, y - 3, 245, y + 12, strokeColor=colors.grey))
                length = 90 * abs(value) / scale
                drawing.add(Rect(245 if value >= 0 else 245 - length, y - 2, length, 12,
                    fillColor=colors.HexColor('#397765'), strokeColor=None))
                drawing.add(String(350, y, artifact_data.cell(metric['value']), fontName=font, fontSize=8))
            story.append(drawing)
        columns = dataset['columns']
        for start in range(1, max(2, len(columns)), 5):
            group = columns[:1] + columns[start:start + 5]
            if group:
                table([[c['label'] for c in group]] + [[artifact_data.display(dataset,c['key'],record.get(c['key'])) for c in group] for record in dataset['rows']])
        for unknown in dataset['unknown_fields']:
            story.append(paragraph('待核对：' + unknown['field'] + ' — ' + unknown['reason']))
    story.append(paragraph('来源与复核边界', heading))
    for line in sources.splitlines() or ['没有登记来源；不能据此声称已经核实。']:
        story.append(paragraph(line))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(font, 8)
        canvas.setFillColor(colors.HexColor('#526E61'))
        canvas.drawString(36, 24, 'Royal Regent Nexus · 曜灵')
        canvas.drawRightString(A4[0] - 36, 24, str(doc.page))
        canvas.restoreState()
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return stream.getvalue()
