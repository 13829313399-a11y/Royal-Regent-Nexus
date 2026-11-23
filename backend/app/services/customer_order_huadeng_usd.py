"""Huadeng source-currency prices, using only the uploaded workbook's P1 rate."""
from decimal import Decimal, ROUND_HALF_UP
from openpyxl.styles import PatternFill


def source_amount(row, suffix, price, qty):
    from .customer_order_unified import _number, _number_text
    amount = _number(row.get('amount_'+suffix))
    manual = set(row.get('_regional_manual_fields', [])) & {'unit_price_'+suffix,'quantity'}
    original = row.get('_huadeng_original_amounts', {})
    if suffix in original and not manual:
        amount = _number(original[suffix])
        row['amount_'+suffix] = _number_text(amount)
    literals = row.setdefault('_huadeng_literal_amounts', [])
    if suffix in literals: literals.remove(suffix)
    if price is None or qty is None:
        return amount
    expected = (price*qty).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)
    if amount is not None and not manual and abs(expected-amount)>Decimal('0.01'):
        literals.append(suffix)
        code='source_price_amount_conflict_'+suffix
        if not any(i.get('code')==code for i in row.get('issues',[])):
            row.setdefault('issues',[]).append(dict(severity='warning',code=code,field='amount_'+suffix,
                message=f'原单{suffix.upper()}数量×单价={expected}，与原金额{amount}不一致；保留原金额，请核对。',can_skip=False))
        return amount
    row['amount_'+suffix]=_number_text(expected,2)
    return expected


def apply_preview(workbook, rows):
    from .customer_order_unified import _number, _number_text
    raw_rate = workbook['接单表'].cell(1,16).value
    # Match Excel ISNUMBER used by the generated formulas; text/bools are not rates.
    rate = _number(raw_rate) if isinstance(raw_rate,(int,float,Decimal)) and not isinstance(raw_rate,bool) else None
    for row in rows:
        currency = row.get('_huadeng_source_currency', 'USD' if row.get('_regional_customer') in {'jakks','goliath'} else '')
        if currency == 'BOTH':
            for source in ('usd','hkd'):
                price,qty = _number(row.get('unit_price_'+source)),_number(row.get('quantity'))
                source_amount(row,source,price,qty)
            continue
        if currency not in {'USD','HKD'}:
            continue
        source, target = currency.lower(), 'hkd' if currency == 'USD' else 'usd'
        price, qty = _number(row.get('unit_price_'+source)), _number(row.get('quantity'))
        amount = source_amount(row,source,price,qty)
        multiplier = (rate if currency == 'USD' else Decimal(1)/rate) if rate is not None and rate > 0 else None
        row['unit_price_'+target] = _number_text(price*multiplier) if price is not None and multiplier is not None else ''
        conversion_amount = price*qty if price is not None and qty is not None else amount if qty is None else None
        if source in row.get('_huadeng_literal_amounts',[]): conversion_amount=amount
        row['amount_'+target] = _number_text((conversion_amount*multiplier).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP),2) if conversion_amount is not None and multiplier is not None else ''
        row.setdefault('lineage',{})['unit_price_'+target] = f'原单{currency}单价按接单表P1汇率换算；保留单价精度'
        if multiplier is None and not any(i.get('code')=='usd_exchange_rate_missing' for i in row.get('issues',[])):
            row.setdefault('issues',[]).append(dict(severity='warning',code='usd_exchange_rate_missing',field='exchange_rate',message=f'接单表P1没有有效汇率；原单{currency}价格保留，换算价格留空。请在排期Excel的接单表P1填写汇率后重新上传。',can_skip=False))


def write_prices(workbook, row, order_row, review_row, *, preserve_amount_formulas=False):
    from .customer_order_unified import _number, _excel_value
    order,review=workbook['接单表'],workbook['正单评审表']
    currency = row.get('_huadeng_source_currency', 'USD')
    order['A2']='新订单：美元原价填P列、港币原价填N列，另一币种按P1汇率计算；缺失价格留空。旧历史保持原样。'
    review['A2']='新订单：价格及金额从接单表对应订单同步；保留原单币种与单价精度，另一币种按接单表P1汇率换算。'
    if currency == 'BOTH':
        for suffix,price_col,total_col in (('hkd',14,15),('usd',16,17)):
            price,qty = _number(row.get('unit_price_'+suffix)),_number(row.get('quantity'))
            letter = 'N' if suffix=='hkd' else 'P'
            order.cell(order_row,price_col).value=_excel_value(price)
            order.cell(order_row,total_col).value=(f'=IF(OR(LEN(J{order_row})=0,LEN({letter}{order_row})=0),"",ROUND(J{order_row}*{letter}{order_row},2))' if price is not None and qty is not None and suffix not in row.get('_huadeng_literal_amounts',[]) else _excel_value(_number(row.get('amount_'+suffix))))
        for col,letter in ((14,'N'),(15,'O'),(16,'P'),(17,'Q')):
            review.cell(review_row,col).value=f'=IF(LEN(\'接单表\'!{letter}{order_row})=0,"",\'接单表\'!{letter}{order_row})'
            for sheet,r in ((order,order_row),(review,review_row)):
                sheet.cell(r,col).number_format='0.00######' if col in (14,16) else '#,##0.00'
        return
    if currency not in {'USD','HKD'}:
        for sheet, r in ((order,order_row),(review,review_row)):
            for col in range(14,18): sheet.cell(r,col).value=None
        return
    suffix=currency.lower()
    source_col, target_col = (16,14) if currency=='USD' else (14,16)
    source_letter, target_letter = ('P','N') if currency=='USD' else ('N','P')
    source_total, target_total = (17,15) if currency=='USD' else (15,17)
    source_total_letter = 'Q' if currency=='USD' else 'O'
    operator = '*' if currency=='USD' else '/'
    price,qty,amount = _number(row.get('unit_price_'+suffix)),_number(row.get('quantity')),_number(row.get('amount_'+suffix))
    if price is None and qty is not None:
        for sheet,r in ((order,order_row),(review,review_row)):
            for col in range(14,18): sheet.cell(r,col).value=None
            sheet.cell(r,source_total).value=_excel_value(amount)
        return
    order.cell(order_row,source_col).value=_excel_value(price)
    order.cell(order_row,target_col).value=(f'=IF(OR(LEN({source_letter}{order_row})=0,NOT(ISNUMBER($P$1)),$P$1<=0),"",{source_letter}{order_row}{operator}$P$1)' if price is not None else None)
    for col,letter in ((source_total,source_letter),(target_total,target_letter)):
        if preserve_amount_formulas and order.cell(order_row,col).data_type=='f':
            continue
        if price is not None and qty is not None and suffix not in row.get('_huadeng_literal_amounts',[]):
            order.cell(order_row,col).value=f'=IF(OR(LEN(J{order_row})=0,LEN({letter}{order_row})=0),"",ROUND(J{order_row}*{letter}{order_row},2))'
        elif col == source_total:
            order.cell(order_row,col).value=_excel_value(amount)
        else:
            order.cell(order_row,col).value=(f'=IF(OR(LEN({source_total_letter}{order_row})=0,NOT(ISNUMBER($P$1)),$P$1<=0),"",ROUND({source_total_letter}{order_row}{operator}$P$1,2))' if amount is not None else None)
    for col,letter in ((14,'N'),(15,'O'),(16,'P'),(17,'Q')):
        if not (preserve_amount_formulas and col in (15,17) and review.cell(review_row,col).data_type=='f'):
            review.cell(review_row,col).value=f'=IF(LEN(\'接单表\'!{letter}{order_row})=0,"",\'接单表\'!{letter}{order_row})' if order.cell(order_row,col).value is not None else None
    for sheet,r in ((order,order_row),(review,review_row)):
        for col in range(14,18):
            sheet.cell(r,col).number_format='0.00######' if col in (14,16) else '#,##0.00'
            sheet.cell(r,col).fill=PatternFill('solid',fgColor='FFF2CC' if sheet is order and col==source_col else 'E2F0D9')
