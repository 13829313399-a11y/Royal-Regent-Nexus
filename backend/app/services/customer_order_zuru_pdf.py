"""Native ZURU PO grids, extracted by labelled physical columns, never text order.

The normalized cells feed the same strict validation as checked XLSX inputs.
No OCR, inferred line numbers, filename revisions or partial-file success.
"""
from datetime import datetime
from hashlib import sha256
from io import BytesIO
import re

import pdfplumber


def _key(value):
    return re.sub(r'\s+', '', value or '').upper()


FIELDS = ('LINE', 'SKU', 'SKU-SPEC', 'NAME', 'OUTER', 'INDIVIDUALBARCODE',
          'DELIVERYDATE', 'PRICEUSD', 'QTYPCS', 'TOTALUSD', 'TOTALCTNS', 'CUSTOMERPO', 'SHIPTYPE')
LETTERS = {field: chr(65 + i) for i, field in enumerate(FIELDS)}


class PdfSourceBook:
    """SourceBook-compatible readonly native PDF view."""
    epoch = datetime(1899, 12, 30)
    sheets = ('PDF原生表格',)

    def __init__(self, content, name):
        if not content.startswith(b'%PDF-'):
            raise ValueError(f'{name}：不是有效 PDF 文件')
        self.revision_history = None
        self.page_rows = {}
        try:
            with pdfplumber.open(BytesIO(content)) as pdf:
                if not 1 <= len(pdf.pages) <= 100:
                    raise ValueError('PDF 页数超出范围')
                texts = [p.extract_text() or '' for p in pdf.pages]
                if any(not t.strip() for t in texts):
                    raise ValueError('PDF 含无原生文字的页面，请提供核对后的 XLSX')
                fulltext = '\n'.join(texts)
                self.content_identity = sha256(re.sub(r'\s+', '', fulltext).encode()).hexdigest()
                self.revision_history = _revisions(fulltext)
                self._rows = self._extract(pdf, texts)
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(f'{name}：无法读取 ZURU 原生 PDF 表格，请提供核对后的 XLSX') from exc

    def _extract(self, pdf, texts):
        first = pdf.pages[0]
        tables = first.find_tables()
        candidates = [(t, t.extract()) for t in tables]
        candidates = [(t, rows) for t, rows in candidates if rows and
                      {'LINE', 'SKU', 'SKU-SPEC', 'NAME'} <= {_key(v) for v in rows[0]}]
        if len(candidates) != 1:
            raise ValueError('未找到唯一 ZURU PO 明细网格；箱唛、扫描件及不支持格式不能作为订单')
        table, values = candidates[0]
        title = first.crop((0, 0, first.width, table.bbox[1])).extract_text() or ''
        # Restrict cancellation/document-type checks to the actual PO heading;
        # ordinary contractual footer text discusses cancellation and pallets.
        from .customer_order_zuru import UNSUPPORTED
        if re.search(UNSUPPORTED, title, re.I):
            raise ValueError('PDF 标题为取消/MPO/混装/卡板等未支持类型，不能当普通正单导入')
        if len(values) < 3:
            raise ValueError('ZURU PDF 缺少明细')
        columns = {}
        for i, upper in enumerate(values[0]):
            upper = _key(upper)
            lower = _key(values[1][i])
            label = upper + lower
            if upper in {'LINE', 'SKU', 'SKU-SPEC', 'NAME', 'CUSTOMERPO'}:
                label = upper
            if upper == 'OUTER' and lower == 'PCS':
                label = 'OUTER'
            if label in FIELDS:
                if label in columns:
                    raise ValueError('PDF 关键列重复，不能确定归属')
                cell = table.rows[1].cells[i] if label == 'OUTER' else table.rows[0].cells[i]
                if cell is None:
                    raise ValueError('PDF 列边界不完整')
                columns[label] = cell[0], cell[2]
        required = set(FIELDS) - {'SHIPTYPE', 'INDIVIDUALBARCODE'}
        if not required <= columns.keys():
            raise ValueError('PDF 明细缺少已确认字段：' + ', '.join(sorted(required - columns.keys())))

        # Header labels use their own two-column tables, not adjacent text blobs.
        metadata = {}
        for t in tables:
            if t.bbox[1] >= table.bbox[1]:
                continue
            for cells in t.extract():
                if len(cells) != 2:
                    continue
                label = _key(cells[0]).rstrip(':：')
                if label in {'DATE', 'ZURUINCPO#', 'CUSTOMERNAME', 'SHIPMENTDATE', 'DESTINATIONCOUNTRY'}:
                    value = (cells[1] or '').replace('\n', ' ')
                    if label in metadata and metadata[label] != value:
                        raise ValueError('PDF 基本信息冲突')
                    metadata[label] = value
        all_po = re.findall(r'ZURU\s+Inc\s+PO#\s*(\d{8,14})', '\n'.join(texts), re.I)
        if len(all_po) != 1 or metadata.get('ZURUINCPO#') not in all_po:
            raise ValueError('PDF 必须只包含一张真实 ZURU PO')
        rows = [(1, {'A': 'ZURU PURCHASE ORDER'}, {})]
        for n, (label, value) in enumerate(metadata.items(), 5):
            rows.append((n, {'A': label, 'B': value}, {}))
        rows.append((13, {LETTERS[field]: field for field in columns}, {}))
        source_number, found_total = 14, False
        original_left, original_right = table.bbox[0], table.bbox[2]
        original_width = original_right - original_left
        for page_number, page in enumerate(pdf.pages, 1):
            if abs(page.width - first.width) > 1:
                raise ValueError('PDF 跨页尺寸变化，不能套用前页列映射')
            page_tables = page.find_tables()
            grids = [t for t in page_tables if t.bbox[2] - t.bbox[0] > original_width * .95]
            if page_number == 1:
                grids = [t for t in grids if t.bbox[1] >= table.bbox[1] - 1]
            for grid in grids:
                grid_values = grid.extract()
                scale = (grid.bbox[2] - grid.bbox[0]) / original_width
                if abs(scale - 1) > .015:
                    if found_total:
                        continue
                    raise ValueError('PDF 跨页表格宽度不一致')
                for physical_number, row in enumerate(grid.rows, 1):
                    if page_number == 1 and row.bbox[1] < table.rows[2].bbox[1] - 1:
                        continue
                    cells = {}
                    for field, (x0, x1) in columns.items():
                        left = grid.bbox[0] + (x0 - original_left) * scale
                        right = grid.bbox[0] + (x1 - original_left) * scale
                        # Center membership avoids boundary glyphs from neighbouring columns.
                        chars = page.filter(lambda obj, l=left, r=right, y0=row.bbox[1], y1=row.bbox[3]:
                                            obj.get('object_type') == 'char' and
                                            l <= (obj['x0'] + obj['x1']) / 2 < r and
                                            y0 <= (obj['top'] + obj['bottom']) / 2 < y1)
                        value = chars.extract_text(x_tolerance=1, y_tolerance=2) or ''
                        if field not in {'NAME', 'CUSTOMERPO', 'SHIPTYPE'}:
                            value = re.sub(r'\s+', '', value)
                        if value:
                            cells[LETTERS[field]] = value
                    original_first = _key(grid_values[physical_number - 1][0])
                    if original_first in {'TOTAL', 'TOTALS'}:
                        cells[LETTERS['LINE']] = 'Totals'
                    line_key = _key(cells.get(LETTERS['LINE']))
                    if line_key == 'LINE':
                        if found_total:
                            raise ValueError('PDF 总计后出现新的明细表头，不能输出部分订单')
                        continue
                    if not cells:
                        continue
                    if found_total:
                        sku, spec = _key(cells.get(LETTERS['SKU'])), _key(cells.get(LETTERS['SKU-SPEC']))
                        if line_key.isdigit() and sku and spec.startswith(sku + '-') and cells.get(LETTERS['QTYPCS']):
                            raise ValueError('PDF 总计后仍有订单明细，不能输出部分订单')
                        continue
                    if re.search(r'\bCANCEL(?:LED|ED)?\b|DO\s+NOT\s+SHIP|取消|撤销', ' '.join(cells.values()), re.I):
                        raise ValueError('PDF 明细有取消标记，不能当普通正单导入')
                    description = cells.get(LETTERS['NAME'], '')
                    if re.search(r'\bMIX(?:ED)?\b|\bPALLET\b|混装|卡板', description, re.I):
                        raise ValueError('PDF 明细为混装/卡板，需先核对独立件数与价格口径')
                    location = f'第{page_number}页网格第{physical_number}行'
                    # Native grid boundaries establish a page break in a physical
                    # cell. Only descriptive tails may extend an otherwise complete
                    # previous row. A bare Customer PO can never move this way.
                    if page_number > 1 and physical_number == 1 and rows[-1][0] >= 14:
                        old_n, old, _ = rows[-1]
                        descriptive = {LETTERS['NAME'], LETTERS['SHIPTYPE']}
                        tail_fields = descriptive | {LETTERS['SKU-SPEC']}
                        identity = {LETTERS['LINE'], LETTERS['SKU'], LETTERS['QTYPCS']}
                        if (set(cells) <= tail_fields and cells.get(LETTERS['NAME'])
                                and identity <= old.keys()):
                            if cells.get(LETTERS['SKU-SPEC']):
                                sku = _key(old[LETTERS['SKU']])
                                combined = _key(old.get(LETTERS['SKU-SPEC'])) + _key(cells[LETTERS['SKU-SPEC']])
                                description_key = _key(old.get(LETTERS['NAME'])) + _key(cells[LETTERS['NAME']])
                                suffix = combined[len(sku) + 1:] if combined.startswith(sku + '-') else ''
                                if not suffix or not description_key.startswith(suffix + '-'):
                                    raise ValueError('PDF 跨页 SKU-SPEC 尾缀缺少品名中的完整版本佐证，不能拼接其他货号')
                            for col, value in cells.items():
                                separator = '' if col == LETTERS['SKU-SPEC'] else '\n'
                                old[col] = old.get(col, '') + separator + value
                            self.page_rows[old_n] += ' / ' + location
                            continue
                        # Leading fragments deliberately remain separate: the shared
                        # validator requires barcode evidence excluding the previous
                        # complete row before assigning a Customer PO to the next.
                    rows.append((source_number, cells, {}))
                    self.page_rows[source_number] = location
                    source_number += 1
                    if source_number > 2014:
                        raise ValueError('PDF 明细行数超出范围')
                    if line_key in {'TOTAL', 'TOTALS'}:
                        found_total = True
        if not found_total:
            raise ValueError('PDF 缺少可核对的订单总计')
        return rows

    def rows(self, sheet, max_rows=2000):
        return iter(self._rows)

    def close(self):
        pass


def _revisions(fulltext):
    """Read only the explicitly labelled revision record, not file suffixes."""
    match = re.search(r'Order\s+Modifiable\s+Records(.*?)(?:Special\s+|$)', fulltext, re.I | re.S)
    if not match:
        return None
    history = []
    revision_pattern = r'^\s*(\d+)\s+((?:20\d{2}[-/]\d{1,2}[-/]\d{1,2})|(?:\d{1,2}[-/]\d{1,2}[-/]20\d{2}))\b'
    for line in match[1].splitlines():
        if re.match(r'^\s*\d+\s+', line) and not re.match(revision_pattern, line):
            raise ValueError('原单修订记录日期无法识别，不能确定版本')
    for number, raw in re.findall(revision_pattern, match[1], re.M):
        from .customer_order_zuru import _date
        entry = (int(number), _date(raw, PdfSourceBook.epoch))
        if entry not in history:
            history.append(entry)
    if any(history[i][0] >= history[i+1][0] or history[i][1] > history[i+1][1] for i in range(len(history)-1)):
        raise ValueError('原单修订记录的版本/日期矛盾')
    return history
