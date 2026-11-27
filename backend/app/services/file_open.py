"""Open generated shipping files with the host's default application and build sheet previews."""
import io
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from uuid import uuid4


def open_path(path: str) -> str:
    target = str(path)
    try:
        if sys.platform.startswith('win'):
            os.startfile(target)  # type: ignore[attr-defined]
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', target])
        else:
            subprocess.Popen(['xdg-open', target])
    except OSError:
        pass
    return target


def open_bytes(filename: str, content: bytes) -> str:
    safe_name = Path(filename or 'document').name
    stem, suffix = os.path.splitext(safe_name)
    folder = Path(tempfile.gettempdir()) / 'royal-regent-open'
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f'{stem}-{datetime.now().strftime("%Y%m%d%H%M%S")}-{uuid4().hex[:6]}{suffix}'
    target.write_bytes(content)
    try:
        if sys.platform.startswith('win'):
            os.startfile(str(target))  # type: ignore[attr-defined]
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', str(target)])
        else:
            subprocess.Popen(['xdg-open', str(target)])
    except OSError:
        pass
    return str(target)


def _format_cell(value: object, num_fmt: str = '') -> str:
    if value is None:
        return ''
    if isinstance(value, bool):
        return str(value)
    from datetime import date, datetime

    if isinstance(value, (datetime, date)):
        fmt = re.sub(r'\[[^\]]*\]|["\\_;@]', '', str(num_fmt or '')).lower()
        if isinstance(value, datetime) and (value.hour or value.minute or value.second):
            return value.strftime('%Y-%m-%d %H:%M')
        if 'mmm' in fmt and 'd' in fmt:
            return f'{value.day}-{value.strftime("%b")}-{value.strftime("%y")}'
        if 'yyyy' in fmt and '/' in fmt:
            return f'{value.year}/{value.month}/{value.day}'
        if 'm/d' in fmt and 'y' not in fmt:
            return f'{value.month}/{value.day}'
        return f'{value.year:04d}-{value.month:02d}-{value.day:02d}'
    if isinstance(value, (int, float)):
        section = str(num_fmt or '').split(';')[0]
        if '%' in section:
            m_pct = re.search(r'\.(0+)', section)
            dec = len(m_pct.group(1)) if m_pct else 0
            return f'{float(value) * 100:.{dec}f}%'
        cleaned = re.sub(r'"[^"]*"|\\.', '', section)
        m_dec = re.search(r'\.(0+)', cleaned)
        if m_dec:
            dec = len(m_dec.group(1))
            if ',' in cleaned:
                return f'{float(value):,.{dec}f}'
            return f'{float(value):.{dec}f}'
        if isinstance(value, float):
            if value.is_integer():
                return str(int(value))
            return f'{value:.6f}'.rstrip('0').rstrip('.')
        return str(value)
    return str(value)


DEFAULT_XLSX_THEME = [
    'FFFFFF', '000000', 'EEECE1', '1F497D',
    '4F81BD', 'C0504D', '9BBB59', '8064A2', '4BACC6', 'F79646',
]
_BORDER_STYLE_MAP = {
    'thin': '1px solid',
    'hair': '1px solid',
    'medium': '2px solid',
    'thick': '2.5px solid',
    'double': '3px double',
    'dashed': '1px dashed',
    'dotted': '1px dotted',
    'dashDot': '1px dashed',
    'dashDotDot': '1px dashed',
    'mediumDashed': '2px dashed',
    'mediumDashDot': '2px dashed',
    'mediumDashDotDot': '2px dashed',
    'slantDashDot': '1px dashed',
}
_XLS_BORDER_STYLE_MAP = {
    1: '1px solid',
    2: '2px solid',
    3: '1px dashed',
    4: '1px dotted',
    5: '2.5px solid',
    6: '3px double',
    7: '1px solid',
    8: '2px dashed',
    9: '1px dashed',
    10: '2px dashed',
    11: '1px dashed',
    12: '2px dashed',
    13: '1px dashed',
}


def _apply_tint(hex6: str, tint: float) -> str:
    clean = hex6.strip().lstrip('#')
    if len(clean) != 6:
        return '#000000'
    r = int(clean[0:2], 16) / 255.0
    g = int(clean[2:4], 16) / 255.0
    b = int(clean[4:6], 16) / 255.0
    if tint:
        import colorsys
        h, l, s = colorsys.rgb_to_hls(r, g, b)
        if tint < 0:
            l = max(0.0, min(1.0, l * (1.0 + tint)))
        else:
            l = max(0.0, min(1.0, l * (1.0 - tint) + tint))
        r, g, b = colorsys.hls_to_rgb(h, l, s)
    return f'#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}'


def _xlsx_theme_colors(workbook) -> list[str]:
    colors = list(DEFAULT_XLSX_THEME)
    raw_theme = getattr(workbook, 'loaded_theme', None)
    if not raw_theme:
        return colors
    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(raw_theme if isinstance(raw_theme, (bytes, str)) else str(raw_theme))
        ns = {'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'}
        scheme = root.find('.//a:clrScheme', ns)
        if scheme is None:
            return colors
        tags = ['lt1', 'dk1', 'lt2', 'dk2', 'accent1', 'accent2', 'accent3', 'accent4', 'accent5', 'accent6']
        for idx, tag in enumerate(tags):
            node = scheme.find(f'a:{tag}', ns)
            if node is None:
                continue
            srgb = node.find('a:srgbClr', ns)
            sys_clr = node.find('a:sysClr', ns)
            val = (srgb.attrib.get('val') if srgb is not None else None) or (
                sys_clr.attrib.get('lastClr') if sys_clr is not None else None
            )
            if val and len(val) == 6:
                colors[idx] = val.upper()
    except Exception:  # noqa: BLE001 - fall back to default Office theme palette
        pass
    return colors


def _xlsx_color(color, theme_colors: list[str]) -> str | None:
    if color is None:
        return None
    ctype = getattr(color, 'type', None)
    tint = float(getattr(color, 'tint', 0) or 0)
    if ctype == 'rgb':
        rgb = getattr(color, 'rgb', None)
        if not isinstance(rgb, str):
            return None
        if len(rgb) == 8:
            if rgb[:2] == '00':
                return None
            return _apply_tint(rgb[2:], tint)
        if len(rgb) == 6:
            return _apply_tint(rgb, tint)
        return None
    if ctype == 'indexed':
        idx = getattr(color, 'indexed', None)
        if not isinstance(idx, int) or idx < 0 or idx >= 64:
            return None
        from openpyxl.styles.colors import COLOR_INDEX
        if idx >= len(COLOR_INDEX):
            return None
        argb = str(COLOR_INDEX[idx])
        hex6 = argb[2:] if len(argb) == 8 else argb
        return _apply_tint(hex6, tint) if len(hex6) == 6 else None
    if ctype == 'theme':
        idx = getattr(color, 'theme', None)
        if isinstance(idx, int) and 0 <= idx < len(theme_colors):
            return _apply_tint(theme_colors[idx], tint)
    return None


def _is_nonwhite_bg(bg: str | None) -> bool:
    return bool(bg and bg.lower() != '#ffffff')


def _xlsx_border_css(side, theme_colors: list[str]) -> str | None:
    if side is None:
        return None
    style = getattr(side, 'style', None)
    if not style or style not in _BORDER_STYLE_MAP:
        return None
    col = _xlsx_color(getattr(side, 'color', None), theme_colors) or '#000000'
    return f'{_BORDER_STYLE_MAP[style]} {col}'


def _eval_xlsx_formula(expr: str, val_ws, raw_ws, cache: dict, visiting: set) -> object:
    from openpyxl.utils.cell import coordinate_to_tuple

    def cell_num(coord: str) -> float:
        key = coord.replace('$', '').upper()
        if key in cache:
            v = cache[key]
            return float(v) if isinstance(v, (int, float)) else 0.0
        if key in visiting:
            return 0.0
        visiting.add(key)
        try:
            r, c = coordinate_to_tuple(key)
            val = val_ws.cell(r, c).value
            if val is None:
                raw_val = raw_ws.cell(r, c).value
                if isinstance(raw_val, str) and raw_val.startswith('='):
                    val = _eval_xlsx_formula(raw_val[1:], val_ws, raw_ws, cache, visiting)
                else:
                    val = raw_val
            cache[key] = val
            return float(val) if isinstance(val, (int, float)) else 0.0
        except Exception:  # noqa: BLE001
            return 0.0
        finally:
            visiting.discard(key)

    def eval_sum(match) -> str:
        total = 0.0
        for part in match.group(1).split(','):
            token = part.strip().replace('$', '')
            if ':' in token:
                left, right = token.split(':', 1)
                r1, c1 = coordinate_to_tuple(left.upper())
                r2, c2 = coordinate_to_tuple(right.upper())
                for rr in range(min(r1, r2), max(r1, r2) + 1):
                    for cc in range(min(c1, c2), max(c1, c2) + 1):
                        from openpyxl.utils import get_column_letter
                        total += cell_num(f'{get_column_letter(cc)}{rr}')
            elif re.fullmatch(r'[A-Za-z]+\d+', token):
                total += cell_num(token)
            else:
                try:
                    total += float(token)
                except ValueError:
                    pass
        return str(total)

    work = expr.strip()
    if work.startswith('='):
        work = work[1:].strip()
    work = re.sub(r'SUM\(([^)]*)\)', eval_sum, work, flags=re.IGNORECASE)
    work = re.sub(r'\$?[A-Za-z]{1,3}\$?\d+', lambda m: str(cell_num(m.group(0))), work)
    if not re.fullmatch(r'[\d.+\-*/()\s]+', work):
        return None
    try:
        tokens = re.findall(r'\d+(?:\.\d+)?|[+\-*/()]', work)
        return _eval_arithmetic_tokens(tokens)
    except Exception:  # noqa: BLE001
        return None


def _eval_arithmetic_tokens(tokens: list[str]) -> float | None:
    if not tokens:
        return None
    pos = [0]

    def parse_expr() -> float:
        val = parse_term()
        while pos[0] < len(tokens) and tokens[pos[0]] in ('+', '-'):
            op = tokens[pos[0]]
            pos[0] += 1
            rhs = parse_term()
            val = val + rhs if op == '+' else val - rhs
        return val

    def parse_term() -> float:
        val = parse_factor()
        while pos[0] < len(tokens) and tokens[pos[0]] in ('*', '/'):
            op = tokens[pos[0]]
            pos[0] += 1
            rhs = parse_factor()
            if op == '*':
                val *= rhs
            else:
                val = val / rhs if rhs else 0.0
        return val

    def parse_factor() -> float:
        tok = tokens[pos[0]]
        if tok == '(':
            pos[0] += 1
            val = parse_expr()
            if pos[0] < len(tokens) and tokens[pos[0]] == ')':
                pos[0] += 1
            return val
        if tok == '-':
            pos[0] += 1
            return -parse_factor()
        pos[0] += 1
        return float(tok)

    result = parse_expr()
    return result if pos[0] == len(tokens) else None


def _trim_plain_rows(cells: list[list[dict]]) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in cells:
        plain = [str(cell.get('v') or '') for cell in row]
        while plain and not plain[-1]:
            plain.pop()
        if plain:
            rows.append(plain)
    return rows


def _xlsx_preview(content: bytes, max_rows: int, max_cols: int) -> list[dict]:
    import openpyxl
    from openpyxl.utils import get_column_letter

    wb_styles = openpyxl.load_workbook(io.BytesIO(content), data_only=False)
    wb_values = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    theme_colors = _xlsx_theme_colors(wb_styles)
    sheets: list[dict] = []
    try:
        for ws_raw, ws_val in zip(wb_styles.worksheets, wb_values.worksheets):
            merges: dict[tuple[int, int], tuple[int, int, int, int]] = {}
            max_r, max_c = 0, 0
            for rng in ws_raw.merged_cells.ranges:
                box = (rng.min_row, rng.min_col, rng.max_row, rng.max_col)
                for rr in range(rng.min_row, rng.max_row + 1):
                    for cc in range(rng.min_col, rng.max_col + 1):
                        merges[(rr, cc)] = box
                max_r = max(max_r, min(rng.max_row, max_rows))
                max_c = max(max_c, min(rng.max_col, max_cols))

            scan_r = min(ws_raw.max_row or 0, max_rows)
            scan_c = min(ws_raw.max_column or 0, max_cols)
            for rr in range(1, scan_r + 1):
                for cc in range(1, scan_c + 1):
                    raw_c = ws_raw.cell(rr, cc)
                    val_c = ws_val.cell(rr, cc)
                    fill = raw_c.fill
                    bg = None
                    if fill and fill.fill_type == 'solid':
                        bg = _xlsx_color(fill.fgColor, theme_colors)
                    has_b = bool(raw_c.border and any(
                        getattr(raw_c.border, side, None) and getattr(getattr(raw_c.border, side), 'style', None) in _BORDER_STYLE_MAP
                        for side in ('top', 'right', 'bottom', 'left')
                    ))
                    if val_c.value is not None or raw_c.value is not None or _is_nonwhite_bg(bg) or has_b:
                        max_r = max(max_r, rr)
                        max_c = max(max_c, cc)

            if max_r == 0 or max_c == 0:
                sheets.append({'name': ws_raw.title, 'rows': [], 'colWidths': [], 'rowHeights': [], 'cells': []})
                continue

            col_widths = [
                max(36, min(420, round((ws_raw.column_dimensions[get_column_letter(cc)].width or 10.5) * 7.5 + 10)))
                for cc in range(1, max_c + 1)
            ]
            row_heights = [
                round(ws_raw.row_dimensions[rr].height * 1.333) if ws_raw.row_dimensions[rr].height else 22
                for rr in range(1, max_r + 1)
            ]
            formula_cache: dict = {}
            cells: list[list[dict]] = []
            for rr in range(1, max_r + 1):
                row_cells: list[dict] = []
                for cc in range(1, max_c + 1):
                    box = merges.get((rr, cc))
                    if box and (rr != box[0] or cc != box[1]):
                        row_cells.append({'v': '', 'skip': True})
                        continue

                    raw_c = ws_raw.cell(rr, cc)
                    val_c = ws_val.cell(rr, cc)
                    raw_val = val_c.value
                    if raw_val is None and isinstance(raw_c.value, str) and raw_c.value.startswith('='):
                        raw_val = _eval_xlsx_formula(raw_c.value[1:], ws_val, ws_raw, formula_cache, set())
                    elif raw_val is None and not (isinstance(raw_c.value, str) and raw_c.value.startswith('=')):
                        raw_val = raw_c.value

                    text = _format_cell(raw_val, raw_c.number_format)
                    cell_obj: dict = {'v': text}
                    if box:
                        rs = min(box[2], max_r) - box[0] + 1
                        cs = min(box[3], max_c) - box[1] + 1
                        if rs > 1:
                            cell_obj['rs'] = rs
                        if cs > 1:
                            cell_obj['cs'] = cs

                    fill = raw_c.fill
                    if fill and fill.fill_type == 'solid':
                        bg = _xlsx_color(fill.fgColor, theme_colors)
                        if _is_nonwhite_bg(bg):
                            cell_obj['bg'] = bg
                    elif fill and fill.fill_type == 'gray125':
                        cell_obj['bg'] = '#f1f5f9'

                    font = raw_c.font
                    if font:
                        fcol = _xlsx_color(font.color, theme_colors)
                        if fcol and fcol.lower() not in ('#000000', '#111827'):
                            cell_obj['color'] = fcol
                        if font.bold:
                            cell_obj['bold'] = True
                        if font.italic:
                            cell_obj['italic'] = True
                        if font.underline and font.underline != 'none':
                            cell_obj['underline'] = True
                        if font.size:
                            cell_obj['fontSize'] = round(float(font.size), 1)
                        if font.name:
                            cell_obj['fontFamily'] = font.name

                    align = raw_c.alignment
                    horiz = (align.horizontal or '').lower() if align and align.horizontal else ''
                    if horiz in ('left', 'center', 'right'):
                        cell_obj['align'] = horiz
                    elif isinstance(raw_val, (int, float)) and not isinstance(raw_val, bool):
                        cell_obj['align'] = 'right'
                    vert = (align.vertical or '').lower() if align and align.vertical else ''
                    if vert in ('top', 'bottom'):
                        cell_obj['valign'] = vert
                    elif vert in ('center', 'distributed', 'justify'):
                        cell_obj['valign'] = 'middle'
                    if (align and align.wrap_text) or '\n' in text:
                        cell_obj['wrap'] = True

                    r_end = box[2] if box else rr
                    c_end = box[3] if box else cc
                    b_top = _xlsx_border_css(raw_c.border.top if raw_c.border else None, theme_colors)
                    b_left = _xlsx_border_css(raw_c.border.left if raw_c.border else None, theme_colors)
                    b_bot_cell = ws_raw.cell(r_end, cc)
                    b_right_cell = ws_raw.cell(rr, c_end)
                    b_bottom = _xlsx_border_css(b_bot_cell.border.bottom if b_bot_cell.border else None, theme_colors)
                    b_right = _xlsx_border_css(b_right_cell.border.right if b_right_cell.border else None, theme_colors)
                    border = {
                        k: v for k, v in (('t', b_top), ('r', b_right), ('b', b_bottom), ('l', b_left)) if v
                    }
                    if border:
                        cell_obj['border'] = border

                    row_cells.append(cell_obj)
                cells.append(row_cells)

            sheets.append({
                'name': ws_raw.title,
                'rows': _trim_plain_rows(cells),
                'colWidths': col_widths,
                'rowHeights': row_heights,
                'cells': cells,
            })
        return sheets
    finally:
        wb_styles.close()
        wb_values.close()


def _xls_rgb(colour_idx: int | None, colour_map: dict, *, default: str | None = None) -> str | None:
    if colour_idx is None or colour_idx in (64, 65, 32767):
        return default
    rgb = colour_map.get(colour_idx)
    if isinstance(rgb, tuple) and len(rgb) == 3:
        return f'#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}'
    return default


def _xls_border_css(line_style: int, colour_idx: int, colour_map: dict) -> str | None:
    css_style = _XLS_BORDER_STYLE_MAP.get(line_style)
    if not css_style:
        return None
    col = _xls_rgb(colour_idx, colour_map, default='#000000')
    return f'{css_style} {col}'


def _xls_preview(content: bytes, max_rows: int, max_cols: int) -> list[dict]:
    import xlrd

    workbook = xlrd.open_workbook(file_contents=content, formatting_info=True)
    colour_map = workbook.colour_map
    sheets: list[dict] = []
    for sheet in workbook.sheets():
        merges: dict[tuple[int, int], tuple[int, int, int, int]] = {}
        max_r, max_c = 0, 0
        for rlo, rhi, clo, chi in sheet.merged_cells:
            box = (rlo, clo, rhi - 1, chi - 1)
            for rr in range(rlo, rhi):
                for cc in range(clo, chi):
                    merges[(rr, cc)] = box
            max_r = max(max_r, min(rhi, max_rows))
            max_c = max(max_c, min(chi, max_cols))

        scan_r = min(sheet.nrows, max_rows)
        scan_c = min(sheet.ncols, max_cols)
        for rr in range(scan_r):
            for cc in range(scan_c):
                cell = sheet.cell(rr, cc)
                xf = workbook.xf_list[cell.xf_index]
                bg = _xls_rgb(xf.background.pattern_colour_index, colour_map) if xf.background.fill_pattern else None
                has_b = any([
                    xf.border.top_line_style, xf.border.right_line_style,
                    xf.border.bottom_line_style, xf.border.left_line_style,
                ])
                if cell.value not in ('', None) or _is_nonwhite_bg(bg) or has_b:
                    max_r = max(max_r, rr + 1)
                    max_c = max(max_c, cc + 1)

        if max_r == 0 or max_c == 0:
            sheets.append({'name': sheet.name, 'rows': [], 'colWidths': [], 'rowHeights': [], 'cells': []})
            continue

        col_widths = []
        for cc in range(max_c):
            ci = sheet.colinfo_map.get(cc)
            w = round((ci.width / 256.0) * 7.5 + 10) if ci and ci.width else 88
            col_widths.append(max(36, min(420, w)))

        row_heights = []
        for rr in range(max_r):
            ri = sheet.rowinfo_map.get(rr)
            h = round((ri.height / 20.0) * 1.333) if ri and ri.height else 22
            row_heights.append(max(18, h))

        cells: list[list[dict]] = []
        for rr in range(max_r):
            row_cells: list[dict] = []
            for cc in range(max_c):
                box = merges.get((rr, cc))
                if box and (rr != box[0] or cc != box[1]):
                    row_cells.append({'v': '', 'skip': True})
                    continue

                cell = sheet.cell(rr, cc)
                xf = workbook.xf_list[cell.xf_index]
                fmt_obj = workbook.format_map.get(xf.format_key)
                num_fmt = fmt_obj.format_str if fmt_obj else ''
                val = cell.value
                if cell.ctype == xlrd.XL_CELL_DATE and isinstance(val, (int, float)):
                    try:
                        val = xlrd.xldate_as_datetime(val, workbook.datemode)
                    except Exception:  # noqa: BLE001
                        pass
                elif cell.ctype == xlrd.XL_CELL_BOOLEAN:
                    val = bool(val)
                elif cell.ctype == xlrd.XL_CELL_ERROR:
                    val = ''

                text = _format_cell(val, num_fmt)
                cell_obj: dict = {'v': text}
                if box:
                    rs = min(box[2] + 1, max_r) - box[0]
                    cs = min(box[3] + 1, max_c) - box[1]
                    if rs > 1:
                        cell_obj['rs'] = rs
                    if cs > 1:
                        cell_obj['cs'] = cs

                if xf.background.fill_pattern:
                    bg = _xls_rgb(xf.background.pattern_colour_index, colour_map)
                    if _is_nonwhite_bg(bg):
                        cell_obj['bg'] = bg

                font = workbook.font_list[xf.font_index]
                fcol = _xls_rgb(font.colour_index, colour_map)
                if fcol and fcol.lower() not in ('#000000', '#111827'):
                    cell_obj['color'] = fcol
                if font.bold:
                    cell_obj['bold'] = True
                if font.italic:
                    cell_obj['italic'] = True
                if font.underlined:
                    cell_obj['underline'] = True
                if font.height:
                    cell_obj['fontSize'] = round(font.height / 20.0, 1)
                if font.name:
                    cell_obj['fontFamily'] = font.name

                hor_map = {1: 'left', 2: 'center', 3: 'right'}
                vert_map = {0: 'top', 1: 'middle', 2: 'bottom'}
                horiz = hor_map.get(xf.alignment.hor_align)
                if horiz:
                    cell_obj['align'] = horiz
                elif isinstance(val, (int, float)) and not isinstance(val, bool):
                    cell_obj['align'] = 'right'
                vert = vert_map.get(xf.alignment.vert_align)
                if vert:
                    cell_obj['valign'] = vert
                if xf.alignment.text_wrapped or '\n' in text:
                    cell_obj['wrap'] = True

                r_end = box[2] if box else rr
                c_end = box[3] if box else cc
                b_bot_xf = workbook.xf_list[sheet.cell_xf_index(r_end, cc)]
                b_right_xf = workbook.xf_list[sheet.cell_xf_index(rr, c_end)]
                b_top = _xls_border_css(xf.border.top_line_style, xf.border.top_colour_index, colour_map)
                b_left = _xls_border_css(xf.border.left_line_style, xf.border.left_colour_index, colour_map)
                b_bottom = _xls_border_css(
                    b_bot_xf.border.bottom_line_style, b_bot_xf.border.bottom_colour_index, colour_map,
                )
                b_right = _xls_border_css(
                    b_right_xf.border.right_line_style, b_right_xf.border.right_colour_index, colour_map,
                )
                border = {
                    k: v for k, v in (('t', b_top), ('r', b_right), ('b', b_bottom), ('l', b_left)) if v
                }
                if border:
                    cell_obj['border'] = border

                row_cells.append(cell_obj)
            cells.append(row_cells)

        sheets.append({
            'name': sheet.name,
            'rows': _trim_plain_rows(cells),
            'colWidths': col_widths,
            'rowHeights': row_heights,
            'cells': cells,
        })
    return sheets


def workbook_preview(filename: str, content: bytes, max_rows: int = 120, max_cols: int = 30) -> list[dict]:
    """Return sheet names, styled cell grids, merges, dimensions, and plain rows for in-browser viewing."""
    suffix = Path(filename or '').suffix.lower()
    is_xls = content[:4] == b'\xd0\xcf\x11\xe0' or (content[:2] != b'PK' and suffix == '.xls')
    if is_xls:
        return _xls_preview(content, max_rows, max_cols)
    if content[:2] == b'PK' or suffix in ('.xlsx', '.xlsm'):
        return _xlsx_preview(content, max_rows, max_cols)
    return []


def save_to_downloads(filename: str, content: bytes) -> str:
    """Save a copy under the host user's Downloads folder and return its path."""
    folder = Path.home() / 'Downloads'
    folder.mkdir(parents=True, exist_ok=True)
    safe_name = Path(filename or 'document').name
    stem, suffix = os.path.splitext(safe_name)
    target = folder / safe_name
    if target.exists():
        target = folder / f'{stem}-{datetime.now().strftime("%Y%m%d%H%M%S")}{suffix}'
    target.write_bytes(content)
    return str(target)
