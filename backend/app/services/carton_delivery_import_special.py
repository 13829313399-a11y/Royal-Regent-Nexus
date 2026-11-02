"""Typed special-order matching for supplier originals; never fabricate contracts."""
from decimal import Decimal
from app.services.carton_material_identity import material_conflicts
from app.services.carton_procurement_imports import _dongkang_identity


def matches(source, orders):
    number = _dongkang_identity(source.get('contract_no', ''))
    return [order for order in orders if order['kind'] in {'SAMPLE', 'WORKSHOP_MISC'}
            and _dongkang_identity(order['request_no']) == number]


def match_row(item, source, orders, selected):
    item['source_kind'] = 'SPECIAL'
    if len(orders) != 1:
        item['reason'] = '未找到当前厂区可访问的样板或杂单，请核对原订单编号'
        return
    order = orders[0]
    item.update(order_no=order['request_no'], special_request_id=order['id'],
                order_kind='SAMPLE' if order['kind'] == 'SAMPLE' else 'MISC')
    checked = [(paper, material_conflicts(source, paper, dongkang_delivery=True))
               for paper in order['lines'] if Decimal(paper['quantity']) > 0]
    papers = [paper for paper, conflicts in checked if not conflicts]
    item['candidates'] = [dict(source_kind='SPECIAL', special_request_id=order['id'],
        order_kind=item['order_kind'], order_line_id=paper['id'], issue_id=order['current_version_id'],
        order_revision=order['revision'], order_no=order['request_no'], document_no=order['request_no'],
        customer_po='', planned_date=order['required_date'], status=order['status'],
        required_quantity=paper['quantity'], remaining_to_ship=paper['remaining_to_ship'],
        child_no=f"{order['request_no']}/{paper['line_no']:02d}", unit=paper['unit'])
        for paper in papers] if len(papers) > 1 else []
    if selected:
        if (selected.get('source_kind', 'REGULAR') != 'SPECIAL'
                or selected.get('special_request_id') != order['id']
                or selected['issue_id'] != order['current_version_id']
                or selected['order_revision'] != order['revision']):
            item['reason'] = '所选样板或杂单的需求版本已变更，请重新预览'
            return
        papers = [paper for paper in papers if paper['id'] == selected['order_line_id']]
    if len(papers) != 1:
        item['reason'] = ('匹配到多条纸品，请选择对应订单纸品后重新校验' if papers else
                          '原送货单纸品类型、纸质或规格与此样板或杂单不一致，请核对原单')
        return
    paper = papers[0]
    item.update(order_line_id=paper['id'], issue_id=order['current_version_id'],
                order_revision=order['revision'], unit=paper['unit'],
                child_no=f"{order['request_no']}/{paper['line_no']:02d}",
                free_confirmed=bool(selected and selected.get('free_confirmed')))
    if not order['permissions']['can_ship']:
        item['reason'] = '此样板或杂单尚未确认当前版本、已结束或已取消，请先核对接单状态'
    elif Decimal(str(item['delivered_quantity'])) > Decimal(paper['remaining_to_ship']):
        item['reason'] = f"发货数量超过剩余未送 {paper['remaining_to_ship']} {paper['unit']}"
    elif not source.get('unit_price_provided') or item['unit_price'] is None:
        item['reason'] = '原送货单缺少单价，请供应商补齐原单；免费纸品请明确填写零'
    elif Decimal(str(item['unit_price'])) < 0:
        item['reason'] = '原送货单价不能为负数'
    elif Decimal(str(item['unit_price'])) == 0 and not item['free_confirmed']:
        item.update(free_confirmation_required=True, reason='原单价为零，请明确确认本行免费并重新校验')
    else:
        from app.schemas.carton_special_requests import ShipLine
        from pydantic import ValidationError
        try:
            ShipLine(line_id=paper['id'], quantity=item['delivered_quantity'], unit_price=item['unit_price'],
                     free_confirmed=item['free_confirmed'])
        except ValidationError:
            item['reason'] = '原送货数量或单价格式超出范围；数量最多4位小数，单价最多6位小数'
            return
        item.update(status='READY', reason='已匹配样板或杂单')


def dispatch_payload(factory, request_id, group):
    from app.schemas.carton_unified_deliveries import OriginalFileDispatch
    special, formal = {}, []
    for row in group['rows']:
        if row['status'] != 'READY':
            continue
        if row.get('source_kind') == 'SPECIAL':
            entry = special.setdefault(row['special_request_id'], dict(id=row['special_request_id'],
                expected_revision=row['order_revision'], version_id=row['issue_id'], lines=[]))
            entry['lines'].append(dict(line_id=row['order_line_id'], quantity=row['delivered_quantity'],
                unit_price=row['unit_price'], free_confirmed=row.get('free_confirmed', False)))
        else:
            # Formal original-file imports preserve existing missing-price review.
            formal.append(dict(order_line_id=row['order_line_id'], issue_id=row['issue_id'],
                               quantity=row['delivered_quantity']))
    return OriginalFileDispatch(factory_id=factory, request_id=request_id,
        delivery_note_no=group['delivery_note_no'], delivery_date=group['delivery_date'],
        formal_lines=formal, special_requests=list(special.values()))
