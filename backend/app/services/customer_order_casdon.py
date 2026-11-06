"""Casdon-only unified placement, price display and explicit Excel filing.

This module never writes ledger shipment facts or overwrites uploaded bytes.
"""
from collections import defaultdict
from copy import copy
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import re
from zipfile import ZipFile, BadZipFile

from openpyxl.formula.translate import Translator
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.cell_range import MultiCellRange, CellRange

SHEETS = ('ITEM表', '接单表', '正单评审表')
MONEY = ('单价HK', '金额HK', '单价USD', '总金额USD')
VERSION = 'casdon-workbook-v1'


def error(message):
    from .customer_order_unified import CustomerOrderUnifiedError
    raise CustomerOrderUnifiedError('Casdon 排期：' + message)


def text(value):
    return '' if value is None else str(value).strip()


def key(value):
    # Full article identity: never discard seasonal/customer suffixes.
    return re.sub(r'\s+', '', text(value)).replace('（', '(').replace('）', ')').upper()


def value(sheet, row, col):
    cell = sheet._cells.get((row, col))
    return cell.value if cell is not None and cell.data_type != 'f' else None


def identity(sheet, row):
    ref, product = (5, 8) if sheet.title == 'ITEM表' else (4, 7)
    return key(value(sheet, row, ref)), key(value(sheet, row, product))


def sections(sheet):
    labels = {'取消单': 'cancelled', '已走货订单': 'shipped', '已走货': 'shipped',
              '已完成': 'other', '已完成订单': 'other', '备料单': 'other'}
    found = []
    for (r, c), cell in sorted(sheet._cells.items()):
        label = key(cell.value) if cell.data_type != 'f' else ''
        if r >= 4 and c <= 2 and label in labels and not any(identity(sheet, r)):
            found.append((r, labels[label]))
    return found


def active_end(sheet):
    return min((r for r, _ in sections(sheet)), default=sheet.max_row + 1)


def order_rows(sheet):
    result = []
    state, banners = 'active', dict(sections(sheet))
    for r in sorted({r for r, _ in sheet._cells}):
        if r < 4:
            continue
        state = banners.get(r, state)
        ref, product = identity(sheet, r)
        if ref and product and ref not in {'SO#/REFERENCE', 'SO#REFERENCE'} and product != '产品编号':
            result.append((r, state))
    return result


def insertion_row(sheet, product):
    end = active_end(sheet)
    pcol = 8 if sheet.title == 'ITEM表' else 7
    matches = [r for r, state in order_rows(sheet)
               if state == 'active' and key(value(sheet, r, pcol)) == key(product)]
    if matches:
        return matches[-1] + 1, matches[-1]
    # Product-only/stock group: insert before it, never after its subtotal.
    group = sorted(r for (r, c), cell in sheet._cells.items()
                   if c == pcol and 4 <= r < end and cell.data_type != 'f' and key(cell.value) == key(product))
    if group:
        return group[0], max(4, group[0] - 1)
    occupied = [c.row for c in sheet._cells.values()
                if 4 <= c.row < end and c.value not in (None, '') and c.data_type != 'f']
    return max(occupied, default=3) + 1, max(occupied, default=4)


def copy_blank_row(sheet, source, target):
    from .customer_order_360_manual_column import manual_value_columns
    manual_columns = manual_value_columns(sheet)
    sheet.row_dimensions[target].height = sheet.row_dimensions[source].height
    for cell in list(sheet._cells.values()):
        if cell.row != source:
            continue
        out = sheet.cell(target, cell.column)
        out._style = copy(cell._style)
        if cell.column not in manual_columns and cell.data_type == 'f' and isinstance(cell.value, str):
            out.value = Translator(cell.value, origin=cell.coordinate).translate_formula(out.coordinate)
        for dv in sheet.data_validations.dataValidation:
            if cell.coordinate in dv.cells:
                dv.add(out.coordinate)


def grouped_slots(workbook, rows):
    from .huaxing_order_legacy.edu_grouped_export import _insert as insert_rows
    slots = {name: [] for name in SHEETS}
    for row in rows:
        for name in SHEETS:
            sheet = workbook[name]
            pos, source = insertion_row(sheet, row['product_no'])
            insert_rows(workbook, sheet, pos, 1)
            source += source >= pos
            copy_blank_row(sheet, source, pos)
            slots[name] = [r + (r >= pos) for r in slots[name]] + [pos]
            cols = (4, 5, 6, 7, 8) if name == 'ITEM表' else (3, 4, 5, 6, 7)
            for col, field in zip(cols, ('contract_no', 'reference_no', 'po_no', 'customer_name', 'product_no')):
                sheet.cell(pos, col).value = row.get(field, '')
    return slots


def money_columns(workbook):
    from .customer_order_360_manual_column import ensure_manual_columns
    sheet = workbook['ITEM表']
    result = []
    for label in MONEY:
        found = [c.column for c in sheet._cells.values() if c.row == 3 and key(c.value) == key(label)]
        if len(found) > 1 or any(c <= 28 for c in found):
            error(f'金额表头 {label} 重复或覆盖公共字段，请先核对')
        if found:
            col = found[0]
        else:
            report = ensure_manual_columns(workbook, factory_id='huadeng', customer_code='casdon',
                label=label, aliases={label}, scopes=(('huadeng', 'casdon'),), sheets=('ITEM表',))
            from openpyxl.utils.cell import column_index_from_string
            col = column_index_from_string(report['columns']['ITEM表'][0])
        result.append(col)
    if sheet.print_area:
        areas = []
        for raw in sheet._print_area.ranges:
            area = CellRange(str(raw)); area.max_col = max(area.max_col, max(result))
            areas.append(str(area))
        sheet.print_area = areas
    return result


def prepare_money(workbook):
    columns = money_columns(workbook)
    fixed = 0
    for name in SHEETS[1:]:
        sheet = workbook[name]
        for r, _ in order_rows(sheet):
            cell = sheet.cell(r, 16)
            # Fix only the demonstrated template's early rounding; preserve custom pricing.
            if cell.data_type == 'f' and isinstance(cell.value, str):
                pattern = rf'ROUND\((\$?N\$?{r}/\$P\$1),\s*2\)'
                updated, count = re.subn(pattern, r'\1', cell.value, flags=re.I)
                if count:
                    cell.value = updated
                    cell.number_format = '0.000###'
                    fixed += 1
    by_key = defaultdict(list)
    for r, _ in order_rows(workbook['接单表']):
        by_key[identity(workbook['接单表'], r)].append(r)
    warnings = []
    for r, _ in order_rows(workbook['ITEM表']):
        matched = by_key[identity(workbook['ITEM表'], r)]
        if len(matched) == 1:
            link_money(workbook, r, matched[0], columns, blanks_only=True)
        elif any(value(workbook['ITEM表'], r, c) is None for c in columns):
            warnings.append(f'ITEM表第{r}行：接单表没有唯一的同 SO/货号价格，金额未自动补填')
    return {'precision_formulas_fixed': fixed, 'money_columns': columns, 'warnings': warnings}


def link_money(workbook, item_row, order_row, columns=None, *, blanks_only=False):
    columns = columns or money_columns(workbook)
    sheet = workbook['ITEM表']
    for col, source in zip(columns, ('N', 'O', 'P', 'Q')):
        cell = sheet.cell(item_row, col)
        if blanks_only and cell.value not in (None, ''):
            continue
        ref = f"'接单表'!{source}{order_row}"
        cell.value = f'=IF(LEN({ref})=0,"",{ref})'
        cell.number_format = '0.000###' if source in ('N', 'P') else '#,##0.00'
        cell._style = copy(sheet.cell(item_row, 11)._style)
        cell.number_format = '0.000###' if source in ('N', 'P') else '#,##0.00'


def write_prices(workbook, row, item_row, order_row, review_row):
    from .customer_order_unified import _number, _excel_value
    for name, r in (('接单表', order_row), ('正单评审表', review_row)):
        sheet = workbook[name]
        sheet.cell(r, 14).value = (_excel_value(_number(row.get('unit_price_hkd')))
            if name == '接单表' else f'=IF(LEN(\'接单表\'!N{order_row})=0,"",\'接单表\'!N{order_row})')
        amount = _number(row.get('amount_hkd'))
        if _number(row.get('quantity')) is None and amount is not None:
            # Freight/charges have an explicit total but no product quantity.
            sheet.cell(r, 15).value = (_excel_value(amount) if name == '接单表'
                else f'=IF(LEN(\'接单表\'!O{order_row})=0,"",\'接单表\'!O{order_row})')
        else:
            sheet.cell(r, 15).value = f'=IF(OR(LEN(J{r})=0,LEN(N{r})=0),"",ROUND(J{r}*N{r},2))'
        sheet.cell(r, 16).value = f'=IF(OR(LEN(N{r})=0,NOT(ISNUMBER($P$1)),$P$1<=0),"",N{r}/$P$1)'
        sheet.cell(r, 17).value = (f'=IF(OR(LEN(O{r})=0,NOT(ISNUMBER($P$1)),$P$1<=0),"",ROUND(O{r}/$P$1,2))'
            if _number(row.get('quantity')) is None else f'=IF(OR(LEN(J{r})=0,LEN(P{r})=0),"",ROUND(J{r}*P{r},2))')
        for c in range(14, 18):
            sheet.cell(r, c).number_format = '0.000###' if c in (14, 16) else '#,##0.00'
    link_money(workbook, item_row, order_row)


def load(file_name, content):
    from . import customer_order_unified as unified
    if not content or len(content) > 35 * 1024**2:
        error('客户排期为空或超过35MB限制')
    if not content.startswith(b'PK'):
        error('请上传未加密的统一排期 .xlsx')
    try:
        with ZipFile(BytesIO(content)) as archive:
            if sum(i.file_size for i in archive.infolist()) > 200 * 1024**2:
                error('排期解压后过大')
    except BadZipFile as exc:
        error(f'无法打开排期：{exc}')
    unified.ensure_unified_schedule(file_name, content, factory_id='huadeng', customer_code='casdon')
    return unified._load_workbook(content)


def fingerprint(content):
    return sha256(VERSION.encode() + content).hexdigest()


def _casdon_preview(file_name, content):
    workbook = load(file_name, content)
    try:
        sheet = workbook['ITEM表']
        rows = []
        for r, state in order_rows(sheet):
            if state not in ('active', 'shipped'):
                continue
            rows.append(dict(id=str(r), row=r, section=state,
                contract=text(value(sheet,r,4)), reference=text(value(sheet,r,5)),
                product=text(value(sheet,r,8)), customer=text(value(sheet,r,7)),
                quantity=text(value(sheet,r,11))))
        if len(rows) > 10000:
            error('订单超过10000行，请拆分后整理')
        return dict(factory_id='huadeng', customer_code='casdon', fingerprint=fingerprint(content), rows=rows)
    finally:
        workbook.close()


def apply_permutation(workbook, mapping):
    from .huakang_a_order_legacy.inspection_archive import _prepare_structures
    # Casdon has product subtotals such as SUM(K20:K21). A moved member can
    # become disjoint; SUM's union syntax preserves the exact original set.
    # Do not broaden ranges or reinterpret arbitrary lookup/array formulas.
    from .huakang_a_order_legacy.inspection_archive import CELL_REF, _segments, _range_bounds
    for sheet in workbook:
        for cell in sheet._cells.values():
            if cell.data_type != 'f' or not isinstance(cell.value, str):
                continue
            match = re.fullmatch(r'=SUM\(([^(),]+)\)', cell.value, re.I)
            ref = CELL_REF.fullmatch(match[1]) if match else None
            if not ref or not ref.group('r2'):
                continue
            name = (ref.group('sheet') or sheet.title).strip("'").replace("''", "'")
            if name != 'ITEM表':
                continue
            first, last = int(ref['r1'].replace('$','')), int(ref['r2'].replace('$',''))
            try:
                _range_bounds(first, last, mapping)
                continue
            except ValueError:
                pass
            # Split source ranges now; the shared remapper moves each segment.
            prefix = ref['sheet'] + '!' if ref['sheet'] else ''
            parts = [f"{prefix}{ref['c1']}{lo}" if lo == hi and ref['c1'] == ref['c2']
                     else f"{prefix}{ref['c1']}{lo}:{ref['c2']}{hi}"
                     for lo, hi, _ in _segments(first, last, mapping)]
            cell.value = '=SUM(' + ','.join(parts) + ')'
    maps = {'ITEM表': mapping}
    try:
        formulas, structures, names = _prepare_structures(workbook, maps)
    except ValueError as exc:
        error(str(exc).replace('360 验货日期整理：', ''))
    for sheet in workbook:
        move = maps.get(sheet.title, {})
        cells = {(move.get(r,r),c): cell for (r,c),cell in sheet._cells.items()}
        for (r,c), cell in cells.items():
            cell.row = r
            if cell.hyperlink:
                cell.hyperlink.ref = cell.coordinate
        sheet._cells = cells
        dimensions = {move.get(r,r): copy(v) for r,v in sheet.row_dimensions.items()}
        sheet.row_dimensions.clear()
        for r, dim in dimensions.items():
            dim.index = r
            sheet.row_dimensions[r] = dim
        merges, conditional, validations = structures[sheet.title]
        sheet.merged_cells = MultiCellRange(merges)
        sheet.conditional_formatting = conditional
        sheet.data_validations.dataValidation = validations
        if move and sheet.print_area:
            areas = []
            for raw in sheet._print_area.ranges:
                area = CellRange(str(raw)); area.max_row = max(area.max_row, max(move.values()))
                areas.append(str(area))
            sheet.print_area = areas
        sheet._current_row = sheet.max_row
    for name,r,c,v in formulas:
        workbook[name].cell(r,c).value = v
    for name,v in names:
        name.attr_text = v


def _casdon_export(file_name, content, expected, action, selections):
    if expected != fingerprint(content):
        error('源文件已变化，请重新预览')
    if action not in ('prepare', 'ship', 'restore'):
        error('不支持的整理操作')
    if not isinstance(selections, list) or len(selections) > 200 or any(not isinstance(s,str) for s in selections):
        error('每次最多选择200行')
    if len(set(selections)) != len(selections) or (action != 'prepare' and not selections) or (action == 'prepare' and selections):
        error('请选择本次需要操作的订单行')
    preview = _casdon_preview(file_name,content)
    indexed = {r['id']:r for r in preview['rows']}
    selected = []
    for ident in selections:
        row = indexed.get(ident)
        if not row or row['section'] != ('active' if action == 'ship' else 'shipped'):
            error('所选行已不在对应区域，请重新预览')
        selected.append(row)
    workbook = load(file_name,content)
    try:
        report = {'action': action, 'moves': [], **prepare_money(workbook)}
        sheet = workbook['ITEM表']
        from .huaxing_order_legacy.edu_grouped_export import _insert as insert_rows
        for entry in selected:
            # Track exact source rows through earlier restoration insertions.
            old = entry['row']
            if action == 'ship':
                banners = [r for r,s in sections(sheet) if s == 'shipped']
                if len(banners) > 1:
                    error('存在多个已走货区域，请先核对')
                if not banners:
                    banner = max(c.row for c in sheet._cells.values() if c.value is not None) + 2
                    sheet.cell(banner,1,'已走货订单')._style = copy(sheet.cell(3,1)._style)
                else:
                    banner = banners[0]
                stop = min((r for r,_ in sections(sheet) if r>banner), default=1048577)
                target = max([banner, *(c.row for c in sheet._cells.values() if banner<c.row<stop and c.value is not None)])+1
                if target >= stop:
                    error('已走货区域空间不足，请先在下一区域前增加空行')
            else:
                target, _ = insertion_row(sheet,entry['product'])
                insert_rows(workbook,sheet,target,1)
                for pending in selected:
                    if pending['row']>=target:
                        pending['row']+=1
                old=entry['row']
            apply_permutation(workbook,{old:target,target:old})
            report['moves'].append({**entry,'original_row':int(entry['id']), 'from_row':old,'to_row':target})
        if workbook.calculation is None:
            from openpyxl.workbook.properties import CalcProperties
            workbook.calculation = CalcProperties()
        workbook.calculation.calcMode='auto'
        workbook.calculation.fullCalcOnLoad=True
        workbook.calculation.forceFullCalc=True
        output=BytesIO();workbook.save(output)
        stem=re.sub(r'[\\/:*?"<>|]+','_',Path(file_name).stem)[:130]
        return output.getvalue(),f'{stem}_Casdon整理.xlsx',report,sha256(content).hexdigest()
    finally:
        workbook.close()
