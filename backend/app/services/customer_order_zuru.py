"""Huaxing ZURU native/converted PO adapter for the common three-sheet schedule.

Native weekly schedules are reference material, never a second order source.
Keep this adapter separate from the legacy original-format classifier.
"""
from datetime import date
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
import re

from openpyxl.utils import column_index_from_string, get_column_letter

from .zuru_original import SourceBook, iso_date, key, numeric, text

INPUT_TEMPLATE = 'HUAXING_ZURU_PO_V2'
UNSUPPORTED = r'CANCEL(?:LED|ED|LATION)?|DO\s+NOT\s+SHIP|\bMPO\b|\bRFQ\b|MIXED|PALLET|取消|撤销|混装|卡板'
CRITICAL = {'LINE', 'SKU', 'SKU-SPEC', 'NAME', 'QTYPCS', 'DELIVERYDATE', 'OUTER',
            'INNER', 'PRICEUSD', 'TOTALUSD', 'TOTALCTNS', 'CUSTOMERPO'}


def _date(value, epoch):
    raw = text(value)
    # ZURU's converted files use ISO dates, Excel serials or explicit MM-DD-YYYY.
    match = re.fullmatch(r'(\d{1,2})[-/\s](\d{1,2})[-/\s](20\d{2})', raw)
    if match:
        return date(int(match[3]), int(match[1]), int(match[2])).isoformat()
    match = re.fullmatch(r'(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})', raw)
    if match:
        return date(*(int(v) for v in match.groups())).isoformat()
    return iso_date(raw, epoch)


def _merge_cells(target, extra, columns, *, continuation=False, prefix=False, known_customer_pos=()):
    """Only one physically adjacent logical detail; never forward-fill a PO."""
    descriptive = {columns.get('NAME'), columns.get('SHIPTYPE')}
    for col, value in extra.items():
        old = target.get(col)
        if not text(old):
            target[col] = value
        elif key(old) == key(value):
            continue
        elif continuation and col in descriptive:
            target[col] = f'{text(value)}\n{text(old)}' if prefix else f'{text(old)}\n{text(value)}'
        elif (prefix and col == columns.get('CUSTOMERPO')
              and key(f'{value}{old}') in known_customer_pos):
            # A wrapped textual PO (e.g. order + destination) is joined only
            # when the complete exact value is independently printed in this PO.
            target[col] = f'{text(value)} {text(old)}'
        else:
            raise ValueError('跨页明细的字段相互冲突，请核对转换后的 Excel，不能沿用上一行')


def _details(rows, start, columns):
    """Join a split SKU-SPEC tail or a pre-line fragment with one adjacent line."""
    result, pending, total = [], None, None
    known_customer_pos = {key(c.get(columns.get('CUSTOMERPO'))) for n, c, _ in rows if n > start}
    relevant = {v for k, v in columns.items() if k in CRITICAL | {'INDIVIDUALBARCODE', 'SHIPTYPE'}}
    for n, cells, _ in rows:
        if n <= start:
            continue
        if any(key(v) in {'TOTAL', 'TOTALS'} for v in cells.values()):
            if total is not None or pending:
                raise ValueError('总计重复或跨页行没有归属，不能输出部分订单')
            total = cells
            continue
        if total is not None:
            # Contractual footer prose may occupy former detail columns.
            if (key(cells.get(columns['LINE'])).isdigit() and text(cells.get(columns['QTYPCS']))) or (
                (re.fullmatch(r'\d+[A-Z0-9-]*', key(cells.get(columns['SKU'])))
                 or re.fullmatch(r'[A-Z0-9]+(?:-[A-Z0-9.]+)+', key(cells.get(columns['SKU-SPEC']))))
                and text(cells.get(columns['QTYPCS']))
            ):
                raise ValueError('总计后仍有订单明细，不能输出部分订单')
            continue
        values = {c: v for c, v in cells.items() if c in relevant}
        # WPS can anchor the same merged Name cell one column left on page 2.
        # Only the adjacent, unlabelled column is accepted; no other field moves.
        name_col = columns['NAME']
        left = get_column_letter(column_index_from_string(name_col) - 1)
        if not text(values.get(name_col)) and left not in columns.values() and re.search(r'[A-Za-z]', text(cells.get(left))):
            values[name_col] = cells[left]
        line = key(values.get(columns['LINE']))
        if (not line and result and not key(result[-1][1].get(columns['SKU-SPEC']))
                and not text(values.get(columns['QTYPCS']))):
            _merge_cells(result[-1][1], values, columns, continuation=True)
            result[-1][0].append(n)
            continue
        if line or text(values.get(columns['SKU'])) or text(values.get(columns['QTYPCS'])):
            if not line.isdigit() or int(line) <= 0:
                raise ValueError(f'第{n}行缺少可靠的原单 Line，不能自行编号')
            if pending:
                fragment = pending[1]
                barcode_col = columns.get('INDIVIDUALBARCODE')
                barcode = key(fragment.get(barcode_col))
                previous = result[-1][1] if result else {}
                previous_barcode = key(previous.get(barcode_col))
                # A bare PO between rows has no proven owner. A page-leading
                # name/barcode fragment is accepted only when the preceding
                # complete row demonstrably has a different barcode, and the
                # next row has no competing barcode or identity.
                if not (text(fragment.get(columns['NAME'])) and barcode
                        and previous_barcode and barcode != previous_barcode
                        and key(values.get(barcode_col)) in {'', barcode}
                        and (not text(fragment.get(columns.get('CUSTOMERPO')))
                             or text(previous.get(columns.get('CUSTOMERPO'))))):
                    raise ValueError(f'第{pending[0]}行跨页片段归属不明确，请核对后合并到正确明细行')
                _merge_cells(values, pending[1], columns, continuation=True, prefix=True, known_customer_pos=known_customer_pos)
                source_rows = [pending[0], n]
                pending = None
            else:
                source_rows = [n]
            result.append((source_rows, values))
        elif values:
            # Units sub-header is not a detail. Never consume arbitrary data.
            if all(key(v) in {'PCS', 'SIZE(CM)', 'CBM'} for v in values.values()):
                continue
            if result and not key(result[-1][1].get(columns['SKU-SPEC'])):
                _merge_cells(result[-1][1], values, columns, continuation=True)
                result[-1][0].append(n)
            elif pending is None:
                pending = (n, values)
            else:
                raise ValueError(f'第{n}行存在多个无行号片段，不能猜测第三方PO归属')
    if pending or total is None:
        raise ValueError('PO 缺少总计或跨页片段没有明确归属')
    return result, total


def parse_po(name, content):
    suffix = Path(name).suffix.lower()
    if suffix not in {'.xlsx', '.pdf'}:
        raise ValueError(f'{name}：请上传 ZURU 原生 PDF 或转换并核对后的 .xlsx 订单')
    if re.search(UNSUPPORTED, Path(name).stem, re.I):
        raise ValueError(f'{name}：取消/MPO/混装/卡板文件不能作为普通正单导入')
    if suffix == '.pdf':
        from .customer_order_zuru_pdf import PdfSourceBook
        book = PdfSourceBook(content, name)
    else:
        book = SourceBook(content, name)
    try:
        populated = [(s, list(book.rows(s, max_rows=2000))) for s in book.sheets]
        populated = [(s, rows) for s, rows in populated if rows]
        if len(populated) != 1:
            raise ValueError('请拆分为一份 PO、一个有效工作表')
        sheet, rows = populated[0]
        if any(f for _, _, f in rows):
            raise ValueError('PO 含公式，请提供已核对的数值副本')
        if any(re.fullmatch(r'#(?:REF!|VALUE!|DIV/0!|NAME\?|N/A|NUM!|NULL!)', text(v))
               for _, cells, _ in rows for v in cells.values()):
            raise ValueError('PO 含 Excel 错误值，请核对原件')
        if any(re.search(UNSUPPORTED, text(v), re.I) for n, cells, _ in rows if n <= 4 for v in cells.values()):
            raise ValueError('标题为取消/MPO/混装/卡板等未支持类型')
        if not any('ZURU' in key(v) for n, cells, _ in rows if n <= 12 for v in cells.values()):
            raise ValueError('未识别 ZURU 标识')

        def labelled(labels):
            matches = []
            for n, cells, _ in rows:
                if n > 12:
                    continue
                ordered = sorted(cells, key=column_index_from_string)
                for i, col in enumerate(ordered[:-1]):
                    if key(cells[col]).rstrip(':：') in labels:
                        matches.append(text(cells[ordered[i + 1]]))
            if len({key(v) for v in matches}) > 1:
                raise ValueError('PO 基本信息有冲突，不能任取一处')
            return matches[0] if matches else ''

        po = key(labelled({'ZURUINCPO#', 'PONUMBER', 'PO#'}))
        if not re.fullmatch(r'\d{8,14}', po):
            raise ValueError('未识别真实 PO 号，不能用文件名代替')
        po_date = _date(labelled({'DATE', 'PODATE'}), book.epoch)
        shipment = labelled({'SHIPMENTDATE', 'SHIPDATE'})
        headers = []
        for n, cells, _ in rows:
            labels = [key(v) for v in cells.values()]
            if {'SKU-SPEC', 'QTYPCS'} <= set(labels):
                if any(labels.count(label) > 1 for label in CRITICAL):
                    raise ValueError('关键表头重复，不能猜测字段所在列')
                headers.append((n, {key(v): c for c, v in cells.items()}))
        if len(headers) != 1:
            raise ValueError('未找到唯一的 SKU-SPEC / QTY PCS 明细表头')
        start, columns = headers[0]
        if not {'LINE', 'SKU', 'SKU-SPEC', 'NAME', 'QTYPCS', 'DELIVERYDATE', 'PRICEUSD'} <= columns.keys():
            raise ValueError('PO 明细缺少已确认字段，不能猜测列位置')
        raw_lines, total = _details(rows, start, columns)
        lines, seen = [], set()
        for source_rows, cells in raw_lines:
            def get(field):
                return cells.get(columns.get(field))
            line = key(get('LINE'))
            if line in seen:
                raise ValueError(f'原单 Line {line} 重复，不能合并或重新编号')
            seen.add(line)
            sku, spec = key(get('SKU')), key(get('SKU-SPEC'))
            if not sku or not re.fullmatch(r'[A-Z0-9]+(?:-[A-Z0-9.]+)+', spec) or not spec.startswith(sku + '-'):
                raise ValueError(f'Line {line} SKU 与完整 SKU-SPEC 缺失或不一致')
            qty = numeric(get('QTYPCS'), '数量', integer=True, positive=True)
            outer = numeric(get('OUTER'), '外箱装箱数', integer=True, positive=True, optional=True)
            boxes = numeric(get('TOTALCTNS'), '箱数', integer=True, optional=True)
            warnings = []
            if outer is None and boxes and qty % boxes == 0:
                outer = qty // boxes
                warnings.append('转换表未提供明确 Outer，装箱数由数量÷总箱数核对得出，请复核')
            if outer is not None and boxes is not None and qty != outer * boxes:
                raise ValueError(f'Line {line} 数量与外箱装箱数×箱数不符，须核对混装口径')
            price = numeric(get('PRICEUSD'), 'USD单价', optional=True)
            amount = numeric(get('TOTALUSD'), 'USD金额', optional=True)
            if price is not None and amount is not None:
                delta = abs(Decimal(str(price)) * qty - Decimal(str(amount)))
                if delta > Decimal('.011'):
                    printed = key(get('PRICEUSD')).replace(',', '')
                    digits = len(printed.partition('.')[2])
                    tolerance = Decimal(qty) * Decimal(10) ** -digits / 2 + Decimal('.005')
                    if not 4 <= digits <= 6 or delta > tolerance:
                        raise ValueError(f'Line {line} 数量×单价与金额不符')
                    warnings.append('原单显示单价有舍入差，保留原USD单价和原金额，请复核；不自动换算HKD')
            barcode_columns = [c for c, v in next(c for n, c, _ in rows if n == start).items() if key(v) == 'INDIVIDUALBARCODE']
            barcode = key(cells.get(barcode_columns[0])) if len(barcode_columns) == 1 else ''
            if len(barcode_columns) > 1:
                warnings.append('转换表条码表头重复，条码留空，请复核原件')
            lines.append(dict(line=line, spec=spec, sku=sku, qty=qty, outer=outer, boxes=boxes,
                name=text(get('NAME')), delivery=_date(get('DELIVERYDATE') or shipment, book.epoch),
                price=price, amount=amount, customer_po=' '.join(text(get('CUSTOMERPO')).split()), barcode=barcode,
                warnings=warnings, source_rows=source_rows))
        total_qty = numeric(total.get(columns['QTYPCS']), 'PO总数量', integer=True, positive=True)
        if not lines or sum(r['qty'] for r in lines) != total_qty:
            raise ValueError('明细数量与 PO 总计不一致，不能输出部分订单')
        for field, source, label in [('amount', 'TOTALUSD', '金额'), ('boxes', 'TOTALCTNS', '箱数')]:
            declared = numeric(total.get(columns.get(source)), f'PO总{label}', optional=True)
            if declared is not None and (any(r[field] is None for r in lines) or
                abs(sum(Decimal(str(r[field])) for r in lines) - Decimal(str(declared))) > Decimal('.011')):
                raise ValueError(f'明细{label}与总计不一致')
        return dict(po=po, po_date=po_date, customer=labelled({'CUSTOMERNAME'}),
            country=labelled({'DESTINATIONCOUNTRY'}), lines=lines, sheet=sheet,
            source_digest=sha256(content).hexdigest(),
            content_identity=getattr(book, 'content_identity', sha256(content).hexdigest()),
            revision_history=getattr(book, 'revision_history', None),
            page_rows=getattr(book, 'page_rows', {}))
    except ValueError as exc:
        raise ValueError(f'{name}：{exc}') from exc
    finally:
        book.close()


def select_versions(parsed_files):
    """One complete source per real PO. Only native revision records select versions."""
    selected, notes = {}, []
    for filename, parsed in parsed_files:
        po = parsed['po']
        if po not in selected:
            selected[po] = filename, parsed
            continue
        old_name, old = selected[po]
        if old['source_digest'] == parsed['source_digest']:
            notes.append(f'PO {po}：{filename} 与 {old_name} 内容相同，仅保留一份。')
            continue
        left, right = old['revision_history'], parsed['revision_history']
        if left is None or right is None or left == right:
            raise ValueError(f'PO {po} 存在同版本或版本不明的不同文件：{old_name} / {filename}；请只保留确认版本')
        newer = right if len(right) > len(left) else left
        older = left if newer is right else right
        if newer[:len(older)] != older or not newer:
            raise ValueError(f'PO {po} 的原单修订记录相互冲突，不能按文件名猜测最新版本')
        if newer is right:
            selected[po] = filename, parsed
            notes.append(f'PO {po}：依据原单修订记录 {right[-1][0]} / {right[-1][1]} 使用 {filename}，替代 {old_name}。')
        else:
            notes.append(f'PO {po}：依据原单修订记录 {left[-1][0]} / {left[-1][1]} 保留 {old_name}，忽略旧版 {filename}。')
    return list(selected.values()), notes


def create_rows(po_files, received_date, history):
    parsed_files = [(filename, parse_po(filename, content)) for filename, content in po_files]
    selected, version_notes = select_versions(parsed_files)
    rows = []
    for filename, parsed in selected:
        for line in parsed['lines']:
            locations = parsed.get('page_rows', {})
            location = ' / '.join(locations.get(n, f'第{n}行') for n in line['source_rows'])
            source = f"{filename} · {parsed['sheet']} · {location} · Line {line['line']}"
            row = dict(id=f'huaxing-zuru-{len(rows) + 1}', row_role='detail',
                _huaxing_customer='zuru', _zuru_customer=True, received_date=received_date, order_type='正单',
                production_no='', contract_no=parsed['po'], reference_no=f"{parsed['po']}-{line['line']}",
                po_no=line['customer_po'], customer_name=parsed['customer'] or 'ZURU', country=parsed['country'],
                product_no=line['spec'], product_name_en=line['name'], product_name_zh='',
                quantity=str(line['qty']), units_per_carton=str(line['outer']) if line['outer'] else '',
                carton_count='', standard='', packaging='',
                requested_ship_date=line['delivery'], line_q='', customer_q='',
                unit_price_usd=str(line['price']) if line['price'] is not None else '',
                amount_usd=str(line['amount']) if line['amount'] is not None else '',
                _zuru_source_quantity=str(line['qty']), _zuru_source_price=str(line['price']) if line['price'] is not None else '',
                unit_price_hkd='', amount_hkd='', barcode=line['barcode'],
                input_template=INPUT_TEMPLATE, source_po_file_name=filename,
                lineage={'source': source, 'contract_no': f'{source} · ZURU Inc PO#',
                    'reference_no': f'{source} · PO# + 原单Line；不自行续号',
                    'product_no': f'{source} · 完整SKU-SPEC；基础SKU {line["sku"]}仅作来源',
                    'po_no': f'{source} · 本行Customer PO；不继承上一行',
                    'po_date': f"{source} · 原单日期 {parsed['po_date']}",
                    'unit_price_usd': f'{source} · Price USD（不换算HKD）',
                    'amount_usd': f'{source} · Total USD原金额'}, issues=[])
            for i, message in enumerate(line['warnings']):
                row['issues'].append(dict(severity='warning', code=f'zuru_source_review_{i}',
                    field='row', message=message, can_skip=False, skip_key='', skip_label=''))
            rows.append(row)
    return rows, version_notes + ['ZURU 以 PO号＋原单Line、完整SKU-SPEC分别保留订单与产品身份；仅导入正单，不导入MA/库存。',
                  '原周排期仅作映射参考；本次上传目标为统一ITEM表、接单表、正单评审表。USD与HKD分开，不自动换汇。'], INPUT_TEMPLATE


def finish_row(row):
    from .customer_order_unified import _number, _number_text
    qty, price = _number(row.get('quantity')), _number(row.get('unit_price_usd'))
    if qty != _number(row.get('_zuru_source_quantity')) or price != _number(row.get('_zuru_source_price')):
        row['amount_usd'] = _number_text(qty * price, 2) if qty is not None and price is not None else ''
        row.setdefault('lineage', {})['amount_usd'] = '人工更正后的数量×USD单价；原单金额保留在原始PO'


def write_summary(sheet, number, row):
    """Common summary currency headers are established; no new price columns."""
    from .customer_order_unified import _number, _excel_value
    for column in range(3, 8):
        cell = sheet.cell(number, column)
        if isinstance(cell.value, str):
            cell.data_type = 's'
    # N:O are factory HKD prices, never filled from the PO's USD or history.
    for col in (14, 15):
        sheet.cell(number, col).value = None
    for col, field in ((16, 'unit_price_usd'), (17, 'amount_usd')):
        cell = sheet.cell(number, col)
        cell.value = _excel_value(_number(row.get(field)))
        cell.number_format = '0.0000##' if col == 16 else '0.00'
