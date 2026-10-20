"""EDU preview controls shared by direct export and ledger import."""
from __future__ import annotations

import re

from app.services.huaxing_order_legacy.edu_schedule import normalize_edu_item
from app.services.huaxing_order_legacy.edu_grouped_export import reservation_candidates


def allocate_references(workbook, rows):
    from app.services.customer_order_huaxing_unified import edu_identity
    maximum = 0
    for name, column in (('ITEM表', 5), ('接单表', 4), ('正单评审表', 4), ('PO订单', 2)):
        if name not in workbook.sheetnames:
            continue
        for (r, c), cell in workbook[name]._cells.items():
            if c != column or cell.data_type == 'f':
                continue
            match = re.fullmatch(r'EDUHX(\d+)(?:-\d+)?', str(cell.value or '').strip(), re.I)
            if match:
                maximum = max(maximum, int(match[1]))
    assigned = {}
    for row in rows:
        key = edu_identity(row.get('contract_no'), row.get('po_no'), row.get('product_no'))
        if key not in assigned:
            maximum += 1
            assigned[key] = f'EDUHX{maximum:05d}'
        row['reference_no'] = assigned[key]


def _editable(row, code, field, message):
    from app.services.customer_order_manual import MANUAL_EDITABLE_FIELDS
    meta = MANUAL_EDITABLE_FIELDS[field]
    return dict(severity='warning', code=code, field=field, message=message,
                can_skip=True, skip_key=f"{row['id']}|{code}|{field}", skip_label='',
                can_edit=True, edit_field=field, edit_label=meta['label'],
                edit_input_type=meta['input_type'])


def prepare_controls(workbook, rows):
    from app.services.customer_order_huaxing_unified import edu_order_key
    from app.services.customer_order_unified import _refresh_status
    for row in rows:
        # Inconsistent source orders cannot use the optional-data confirmation path.
        for issue in row['issues']:
            if issue.get('code') in {'existing_quantity_conflict', 'edu_reference_collision',
                                     'ambiguous_edu_history', 'edu_missing_business_identity'}:
                issue.update(requires_source_correction=True, can_skip=False, can_edit=False)
        raw = row.get('source_product_no') or row.get('product_no', '')
        row.setdefault('lineage', {})['product_no'] = f'原单货号 {raw} → 排期货号 {row["product_no"]}；已识别长码末四位不参与货号匹配'
        repeated = [i for i in row['issues'] if i.get('code') in {'duplicate_existing_order', 'duplicate_batch_order_line'}]
        if repeated:
            for issue in repeated:
                issue['message'] += '；确认后沿用原订单，本次不新增、不再次扣备料。如需修改已录订单，请使用订单修订或修订原排期。'
                issue['skip_label'] = '确认沿用原订单，跳过本次重复行'
            row['_edu_existing_order'] = True
            _refresh_status(row)
            continue
        candidates = reservation_candidates(workbook, row['product_no'])
        po = edu_order_key('', row.get('po_no'))[1]
        exact = [c for c in candidates if po and edu_order_key('', c['po'])[1] == po]
        selected = (exact or candidates)[-1] if candidates else None
        row['edu_reservation_row'] = str(selected['row']) if selected else ''
        row['_edu_skip_reservation'] = not bool(selected)
        if selected:
            reason = ('同扣数 PO 有多条备料，取匹配范围内最后一条绿色行' if len(exact) > 1
                      else '按扣数 PO 匹配' if exact else '扣数 PO 未匹配，按同货号最后一条绿色行')
            options = '；'.join(f"第{c['row']}行 / PO {c['po'] or '未填'} / 余额 {c['quantity']}" for c in candidates)
            row['issues'].append(_editable(row, 'edu_reservation', 'edu_reservation_row',
                f"{reason}：扣原 ITEM表第 {selected['row']} 行。可更正为同货号的其他备料行号。候选：{options}。余额允许负数。"))
        else:
            row['issues'].append(dict(severity='warning', code='edu_no_reservation', field='product_no',
                message='未找到同货号绿色备料行，将按货号分组新增订单，不扣其他货号备料。',
                can_skip=False, skip_key='', skip_label=''))
        row['issues'].append(_editable(row, 'edu_case_pack', 'units_per_carton',
            f"装箱数：{row.get('units_per_carton') or '未识别，箱数暂空'}。可手工更正；原单 1/16 按 16，箱数=数量÷装箱数。"))
        _refresh_status(row)


def validate_controls(workbook, rows, overrides):
    from app.services.customer_order_unified import CustomerOrderUnifiedError, _number, _number_text
    explicit = {(o['row_id'], o['field']) for o in overrides}
    for row in rows:
        if row.get('_edu_existing_order'):
            if any(row_id == row['id'] for row_id, _ in explicit):
                raise CustomerOrderUnifiedError('EDU 重复单沿用原订单，不能通过重复导入修改字段；请修订已有订单或原排期')
            continue
        row['product_no'] = normalize_edu_item(row.get('product_no'))
        pack = _number(row.get('units_per_carton'))
        if (row['id'], 'units_per_carton') in explicit and (pack is None or pack <= 0):
            raise CustomerOrderUnifiedError('EDU 装箱数必须大于 0')
        qty = _number(row.get('quantity'))
        row['carton_count'] = _number_text(qty / pack) if qty is not None and pack is not None and pack > 0 else ''
        candidates = reservation_candidates(workbook, row['product_no'])
        selected = str(row.get('edu_reservation_row') or '').strip()
        if selected and (not selected.isdigit() or int(selected) not in {c['row'] for c in candidates}):
            raise CustomerOrderUnifiedError('EDU 备料行号必须是原 ITEM表中该货号的绿色备料行，请重新核对')
        if candidates and not selected:
            raise CustomerOrderUnifiedError('EDU 必须选择当前货号的备料行，不能跳过扣减')
        row['_edu_skip_reservation'] = not bool(candidates)
