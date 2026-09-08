"""Huaxing September unified schedules; legacy PO engines remain input-only."""
from __future__ import annotations

from collections import Counter
import re

CUSTOMERS = {'buzzbee', 'dickie', 'caixing', 'edu', '360', 'yinhui', 'disney', 'maxx', 'shushupapa', 'barter'}
TARGET_TEMPLATE = 'HEYUAN_BUSINESS_UNIFIED_HUAXING_V2'
BUZZBEE_SHEETS = ('ITEM表-子弹枪', 'ITEM表-水枪', 'ITEM表-套装', 'ITEM表-公仔')
DICKIE_EXTRA = '恐龙蛋口水车Iteam表'


def enabled(factory_id, customer_code):
    return factory_id == 'huaxing' and customer_code in CUSTOMERS


def item_sheets(workbook, customer_code):
    if customer_code == 'buzzbee' and any(name in workbook.sheetnames for name in BUZZBEE_SHEETS):
        return list(BUZZBEE_SHEETS)
    return ['ITEM表'] + ([DICKIE_EXTRA] if customer_code == 'dickie' and DICKIE_EXTRA in workbook.sheetnames else [])


def outer_pack(value):
    from app.services.customer_order_unified import _text, _number, _number_text
    text = _text(value)
    if re.fullmatch(r'\d+\s*/\s*\d+', text):
        text = text.rsplit('/', 1)[1]
    number = _number(text)
    return _number_text(number) if number is not None and number > 0 else ''


def extra_columns(sheet):
    from app.services.customer_order_unified import _normalized_header
    result = {}
    for field, header in (('remarks', '备注'), ('contact', '联系人'), ('pdq', 'PDQ')):
        columns = [cell.column for cell in sheet[3] if cell.column > 28 and _normalized_header(cell.value) == header]
        if len(columns) == 1:
            result[field] = columns[0]
    return result


def read_history(workbook, customer_code):
    from app.services.customer_order_unified import UnifiedHistoryRow, _text
    from app.services.customer_order_regional import history_number
    fields = {1: 'received_date', 2: 'order_type', 3: 'production_no', 4: 'contract_no',
              5: 'reference_no', 6: 'po_no', 7: 'customer_name', 8: 'product_no',
              9: 'product_name_zh', 10: 'product_name_en', 14: 'standard', 20: 'packaging',
              21: 'date_code', 26: 'requested_ship_date'}
    result = []
    for name in item_sheets(workbook, customer_code):
        sheet = workbook[name]
        extras = extra_columns(sheet)
        for r in range(4, sheet.max_row + 1):
            values = {field: _text(sheet.cell(r, col).value) if sheet.cell(r, col).data_type != 'f' else '' for col, field in fields.items()}
            remarks = _text(sheet.cell(r, extras['remarks']).value) if 'remarks' in extras else ''
            reference = values['reference_no'] or values['contract_no'] or values['po_no']
            if not values['product_no'] or values['product_no'] == '产品编号' or '模拟数据' in remarks:
                continue
            values['reference_no'] = reference
            values['quantity'] = history_number(sheet.cell(r, 11), workbook, customer_code)
            values['units_per_carton'] = outer_pack(history_number(sheet.cell(r, 12), workbook, customer_code, pack=True))
            result.append(UnifiedHistoryRow(row=r, source_sheet=name, **values,
                extras={field: _text(sheet.cell(r, col).value) for field, col in extras.items() if sheet.cell(r, col).data_type != 'f'}))
    return result


def map_record(row, record, customer_code):
    from app.services.customer_order_unified import _text
    get = lambda field: _text(record.get(field))
    if customer_code == 'edu':
        row.update(reference_no=get('huaxing_po'), production_no='',
                   contract_no=get('contract_no'), po_no=get('customer_po'))
    elif customer_code == '360':
        row.update(reference_no=get('production_no'), contract_no='',
                   po_no=get('unified_customer_po') or get('customer_po') or get('po_no'), product_no=get('item_full') or row.get('product_no', ''),
                   packaging=get('packaging'), standard=get('standard'))
    elif customer_code == 'yinhui':
        so, po = get('so_no'), get('contract_no')
        row.update(reference_no=re.sub(r'^SO\s*', '', so, flags=re.I), contract_no='',
                   po_no=re.sub(r'^PO\s*', '', po, flags=re.I), packaging=get('packaging'), standard=get('standard'))
    elif customer_code == 'disney':
        row.update(reference_no=get('po_number'), contract_no='', standard=get('standard'))
    elif customer_code in {'maxx', 'shushupapa', 'barter'}:
        row.update(reference_no=get('po_number'), packaging=get('color_box'), standard=get('standard'),
                   units_per_carton=outer_pack(get('outer_pack')))
        if customer_code in {'shushupapa', 'barter'}:
            row['po_no'] = get('customer_po')
    if customer_code in {'360', 'yinhui'} and get('product_name') and not re.search(r'[\u3400-\u9fff]', get('product_name')):
        row['product_name_en'] = get('product_name')
        row['product_name_zh'] = ''
    for field in ('remarks', 'contact', 'pdq'):
        if get(field):
            row[field] = get(field)
    if get('battery'):
        row['remarks'] = '\n'.join(filter(None, [row.get('remarks'), '电池：' + get('battery')]))
    if get('box_mark'):
        row['carton_mark'] = get('box_mark')
    return row


def prepare_row(row, history, customer_code, available_sheets):
    from app.services.customer_order_unified import _key, _text, _issue
    row['_huaxing_customer'] = customer_code
    if customer_code == 'caixing':
        row['reference_no'], row['contract_no'] = row.get('contract_no', ''), ''
    if customer_code == 'dickie':
        row['production_no'], row['contract_no'] = row.get('contract_no', ''), ''
    matches = [h for h in history if _key(h.product_no) == _key(row.get('product_no'))]
    if customer_code == 'buzzbee' and not matches:
        # Latest BuzzBee item suffixes describe schedule variants, not PO line numbers.
        base = _key(row.get('product_no'))
        candidates = [h for h in history if _key(h.product_no.split('-', 1)[0]) == base]
        same_order = [h for h in candidates if h.reference_no and _key(h.reference_no) == _key(row.get('contract_no'))]
        same_customer = [h for h in candidates if _key(h.customer_name) and _key(h.customer_name) == _key(row.get('customer_name'))]
        evidence = same_order or same_customer
        if not evidence and candidates:
            row.setdefault('issues', []).append(_issue('blocked', 'ambiguous_product_variant', 'product_no',
                '基础货号带排期版本后缀，但没有同订单或同客户依据，请核对完整货号'))
        candidates = evidence or candidates
        products = {h.product_no for h in candidates}
        if len(products) == 1 and evidence:
            original = row['product_no']
            row['product_no'] = next(iter(products))
            row.setdefault('lineage', {})['product_no'] = f'PO {original} → 最新排期唯一订单/客户货号 {row["product_no"]}'
            matches = candidates
        elif candidates:
            matches = candidates
        if len(products) > 1 and evidence:
            row.setdefault('issues', []).append(_issue('blocked', 'ambiguous_product_variant', 'product_no',
                '相同基础货号在排期有多个版本，无法根据订单或客户唯一确定'))
    if customer_code == '360':
        full_item = _text(row.get('product_no'))
        if re.fullmatch(r'\d+\.\d+', full_item):
            base_item = full_item.split('.', 1)[0]
            base_matches = [h for h in history if _key(h.product_no) == _key(base_item)]
            if base_matches:
                row['product_no'] = base_item
                matches = base_matches
        reference = _text(row.get('reference_no'))
        same_release = [h for h in matches if re.fullmatch(re.escape(reference) + r'(?:-\d+)?', h.reference_no)]
        po_values = {h.po_no for h in same_release if _key(row.get('po_no')) and _key(h.po_no).endswith(_key(row['po_no']))}
        if len(po_values) == 1:
            row['po_no'] = next(iter(po_values))
        refs = {h.reference_no for h in same_release}
        if len(refs) == 1:
            row['reference_no'] = next(iter(refs))
        elif len(refs) > 1:
            row.setdefault('issues', []).append(_issue('blocked', 'existing_split_release', 'row',
                '该 Release 在最新排期已拆成多个子单，请核对拆单数量后录入'))
    if customer_code == 'edu':
        po_key = lambda value: _key(re.sub(r'^PO\s*#?\s*', '', _text(value), flags=re.I))
        same_order = [h for h in matches if po_key(h.po_no) == po_key(row.get('po_no')) and
                      _key(row.get('contract_no')) in {_key(part) for part in h.contract_no.split('/')}]
        refs = {h.reference_no for h in same_order}
        if len(refs) == 1:
            row['reference_no'] = next(iter(refs))
            contracts = {h.contract_no for h in same_order}
            if len(contracts) == 1:
                row['contract_no'] = next(iter(contracts))
    lanes = {h.source_sheet for h in matches}
    if len(available_sheets) == 1:
        lane = available_sheets[0]
    elif len(lanes) == 1:
        lane = next(iter(lanes))
    else:
        lane = ''
        row.setdefault('issues', []).append(_issue('blocked', 'unmapped_item_sheet', 'item_sheet_name',
            '货号无法唯一匹配最新排期的 ITEM 分类页，请核对分类后再录入'))
    row['item_sheet_name'] = lane
    row['units_per_carton'] = outer_pack(row.get('units_per_carton'))
    row.setdefault('lineage', {})['mapping_rule'] = '华兴最新统一排期：按实际 ITEM 分类页及公共字段写入，摘要关联对应明细行。'
    for field in ('contact', 'pdq'):
        values = {h.extras[field] for h in matches if h.source_sheet == lane and h.extras.get(field)}
        if not _text(row.get(field)) and len(values) == 1:
            row[field] = next(iter(values))


def write_extras(sheet, row_number, row):
    for field, column in extra_columns(sheet).items():
        sheet.cell(row_number, column).value = row.get(field) or None


def validate_edited_identities(preview, original, history, available_sheets, overrides=()):
    from app.services import customer_order_unified as unified
    for row in preview['rows']:
        current = tuple(unified._text(row.get(k)) for k in ('product_no', 'reference_no', 'contract_no', 'po_no'))
        if current == original[row['id']]:
            continue
        explicit = {o['field'] for o in overrides if o['row_id'] == row['id']}
        if current[0] != original[row['id']][0]:
            for field in ('product_name_zh', 'product_name_en', 'units_per_carton', 'standard', 'packaging', 'unit_price_hkd'):
                lineage = str(row.get('lineage', {}).get(field, ''))
                if field not in explicit and ('历史' in lineage or '当前' in lineage and '排期' in lineage):
                    row[field] = unified._unique_history_value(history, row.get('product_no'), field, row.get('customer_name', ''))
                    row['lineage'][field] = '人工更正货号后重新核对最新排期唯一历史值'
        matches = [h for h in history if unified._key(h.product_no) == unified._key(row.get('product_no'))]
        lanes = {h.source_sheet for h in matches}
        if len(available_sheets) == 1:
            row['item_sheet_name'] = available_sheets[0]
        elif len(lanes) == 1:
            row['item_sheet_name'] = next(iter(lanes))
        else:
            raise unified.CustomerOrderUnifiedError('修改后的货号无法唯一确定 ITEM 分类页，请修订 PO 后重新预览')
        same_order = [h for h in matches if h.reference_no and unified._key(h.reference_no) == unified._key(row.get('reference_no'))]
        batch_matches = [other for other in preview['rows'] if other is not row and
                         unified._key(other.get('product_no')) == unified._key(row.get('product_no')) and
                         unified._key(other.get('reference_no')) == unified._key(row.get('reference_no'))]
        if same_order or batch_matches:
            raise unified.CustomerOrderUnifiedError('修改后的订单身份存在重复或数量冲突，原重复确认不适用，请修订 PO 后重新预览')


def export_rows(workbook, rows):
    from app.services import customer_order_unified as unified
    from app.services.huakang_a_order_legacy.unified_schedule import output_slots
    for row in rows:
        if row.get('item_sheet_name') not in item_sheets(workbook, row['_huaxing_customer']):
            raise unified.CustomerOrderUnifiedError('尚未确定产品的 ITEM 分类页，请核对货号及分类后重新预览')
    counts = Counter(row['item_sheet_name'] for row in rows)
    counts.update({'接单表': len(rows), '正单评审表': len(rows)})
    slots = output_slots(workbook, len(rows), sheet_counts=counts)
    used = Counter()
    for index, row in enumerate(rows):
        name = row['item_sheet_name']
        item_row = slots[name][used[name]]
        used[name] += 1
        unified._write_item_row(workbook[name], item_row, row)
        write_extras(workbook[name], item_row, row)
        for summary in ('接单表', '正单评审表'):
            unified._write_summary_row(workbook[summary], slots[summary][index], row,
                                       item_row=item_row, item_sheet=workbook[name])
        # Some supplied EDU reserved rows have a broken price lookup anchor.
        # New paired summary rows can reference their exact order counterpart;
        # the order sheet's manually maintained price remains authoritative.
        review_price = workbook['正单评审表'].cell(slots['正单评审表'][index], 14)
        if isinstance(review_price.value, str) and '#REF!' in review_price.value and '接单表!' in review_price.value:
            ref = f"'接单表'!N{slots['接单表'][index]}"
            review_price.value = f'=IF(LEN({ref})=0,"",{ref})'
