"""Keep Shushupapa's sourced USD values separate from manual HKD prices."""
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP


def prepare_row(row, record):
    from app.services.customer_order_unified import _text, _issue, _number

    row['source_order_date'] = _text(record.get('po_date'))
    row['unit_price_usd'] = ''
    row['amount_usd'] = ''
    if record.get('source_currency') == 'USD':
        row['unit_price_usd'] = _text(record.get('unit_price'))
        row['amount_usd'] = _text(record.get('amount'))
        row['_shushupapa_source_amount_usd'] = row['amount_usd']
        row['price_basis'] = 'po_usd'
    # A single product can be sold to different retailers at different prices.
    # The PO's USD price must never become an HKD price or inherit one from history.
    row['unit_price_hkd'] = row['amount_hkd'] = ''
    if not any('\u3400' <= c <= '\u9fff' for c in _text(row.get('product_name_zh'))):
        row['product_name_zh'] = ''
    aliases = {
        'po_date': 'source_order_date', 'customer_po': 'po_no',
        'ship_date': 'requested_ship_date', 'unit_price': 'unit_price_usd',
        'amount': 'amount_usd', 'outer_pack': 'units_per_carton',
        'cartons': 'carton_count', 'customer': 'customer_name',
        'description': 'product_name_en', 'color_box': 'packaging',
        'box_mark': 'carton_mark',
    }
    for field, source in record.get('source_lineage', {}).items():
        if isinstance(source, dict):
            row.setdefault('lineage', {})[aliases.get(field, field)] = (
                f"{source.get('source_file') or row.get('source_po_file_name', '')}"
                f" · 第 {source.get('page', '?')} 页 · {source.get('raw_text', '')}"
            )
    for index, message in enumerate(record.get('source_warnings', [])):
        row['issues'].append(_issue('warning', f'shushupapa_source_{index}', 'source', message))
    for issue in row['issues']:
        if issue.get('field') == 'ship_date':
            issue['field'] = 'requested_ship_date'
            issue['edit_field'] = 'requested_ship_date'
    row['_shushupapa_derived_inspection'] = _text(row.get('customer_q'))
    finish_row(row)
    source_amount, calculated = _number(record.get('amount')), _number(row.get('amount_usd'))
    if source_amount is not None and calculated is not None and abs(source_amount - calculated) > Decimal('0.005'):
        row['issues'].append(_issue('warning', 'shushupapa_amount_mismatch', 'source',
            f"PO 数字金额 USD {source_amount} 与数量×单价 USD {calculated} 不一致；导出金额按数量×单价计算，请核对原单。"))
    return row


def finish_row(row):
    from app.services.customer_order_unified import _number, _number_text, _text

    price, quantity = _number(row.get('unit_price_usd')), _number(row.get('quantity'))
    row['amount_usd'] = _number_text((price * quantity).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)) if price is not None and quantity is not None else ''
    hkd_price = _number(row.get('unit_price_hkd'))
    row['amount_hkd'] = _number_text((hkd_price * quantity).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)) if hkd_price is not None and quantity is not None else ''
    if row['amount_usd']:
        row.setdefault('lineage', {})['amount_usd'] = (
            '当前数量 × PO 美元单价，四舍五入到美分；原 PO 数字金额 USD '
            + _text(row.get('_shushupapa_source_amount_usd'))
        )
    if price is not None:
        row['price_details_text'] = f"PO 单价 USD {_number_text(price)}；金额 USD {row['amount_usd']}"
        if _number(row.get('unit_price_hkd')) is None:
            row['price_details_text'] += '；HKD 待核对汇率后填写'
    derived = row.get('_shushupapa_derived_inspection')
    if derived is not None and not row.get('_shushupapa_inspection_manual') and _text(row.get('customer_q')) == derived:
        try:
            ship = date.fromisoformat(_text(row.get('requested_ship_date')))
        except ValueError:
            calculated = ''
        else:
            calculated = (ship - timedelta(days=7)).isoformat()
        row['customer_q'] = row['_shushupapa_derived_inspection'] = calculated
        if calculated:
            row.setdefault('lineage', {})['customer_q'] = '客户规则：客要求走货期前 7 天（计划验货日期）'
