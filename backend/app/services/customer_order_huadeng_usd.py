"""Goliath/Jakks source USD prices with the user's workbook exchange rate."""
from copy import copy
from decimal import Decimal, ROUND_HALF_UP
from openpyxl.styles import PatternFill


def apply_preview(workbook, rows):
    from .customer_order_unified import _number, _number_text
    rate = _number(workbook['接单表'].cell(1,16).value)
    for row in rows:
        usd = _number(row.get('unit_price_usd'))
        if usd is not None and _number(row.get('quantity')) is not None and set(row.get('_regional_manual_fields', [])) & {'unit_price_usd','quantity'}:
            row['amount_usd'] = _number_text((usd*_number(row['quantity'])).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP),2)
        row['unit_price_hkd'] = _number_text(usd*rate) if usd is not None and rate is not None and rate > 0 else ''
        qty = _number(row.get('quantity'))
        row['amount_hkd'] = _number_text((qty*usd*rate).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP),2) if qty is not None and usd is not None and rate is not None and rate > 0 else ''
        row.setdefault('lineage',{})['unit_price_hkd'] = '原单美元单价 × 接单表P1汇率；保留单价精度'
        if (rate is None or rate <= 0) and not any(i.get('code')=='usd_exchange_rate_missing' for i in row.get('issues',[])):
            row.setdefault('issues',[]).append(dict(severity='warning',code='usd_exchange_rate_missing',field='exchange_rate',message='接单表P1没有有效汇率；美元原价保留，港币留空。请在排期Excel的接单表P1填写汇率后重新上传。',can_skip=False))


def write_prices(workbook, row, order_row, review_row, *, preserve_amount_formulas=False):
    from .customer_order_unified import _number, _excel_value
    order,review=workbook['接单表'],workbook['正单评审表']
    order['A2']='新订单：P列录入原单美元单价，N列按P1汇率换算港币；金额按数量计算。旧历史价格保持原样。'
    review['A2']='新订单：价格及金额从接单表对应订单同步；美元原价优先，港币按接单表P1汇率换算。'
    if _number(row.get('unit_price_usd')) is None:
        for sheet, r in ((order,order_row),(review,review_row)):
            for col in (14,15,16): sheet.cell(r,col).value=None
            sheet.cell(r,17).value=_excel_value(_number(row.get('amount_usd')))
        return
    order.cell(order_row,16).value=_excel_value(_number(row.get('unit_price_usd')))
    order.cell(order_row,14).value=f'=IF(OR(LEN(P{order_row})=0,NOT(ISNUMBER($P$1)),$P$1<=0),"",P{order_row}*$P$1)'
    for col,letter in ((15,'N'),(17,'P')):
        if not (preserve_amount_formulas and order.cell(order_row,col).data_type=='f'):
            order.cell(order_row,col).value=f'=IF(OR(LEN(J{order_row})=0,LEN({letter}{order_row})=0),"",ROUND(J{order_row}*{letter}{order_row},2))'
    for col,letter in ((14,'N'),(15,'O'),(16,'P'),(17,'Q')):
        if not (preserve_amount_formulas and col in (15,17) and review.cell(review_row,col).data_type=='f'):
            review.cell(review_row,col).value=f'=IF(LEN(\'接单表\'!{letter}{order_row})=0,"",\'接单表\'!{letter}{order_row})'
    for sheet,r in ((order,order_row),(review,review_row)):
        for col in range(14,18):
            sheet.cell(r,col).number_format='0.00######' if col in (14,16) else '#,##0.00'
            sheet.cell(r,col).fill=PatternFill('solid',fgColor='FFF2CC' if sheet is order and col==16 else 'E2F0D9')
