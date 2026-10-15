"""Receipt amount evidence; no inventory valuation or payment approval."""
import re
from decimal import Decimal, ROUND_HALF_UP, localcontext
from fastapi import HTTPException

PRICE_FIELDS = ('unit_price', 'price_unit', 'currency')


def omit_empty_prices(body):
    # New optional defaults must not change exact retries of old stock requests.
    for item in body.get('items', [body]):
        for field in PRICE_FIELDS:
            if not item.get(field):
                item.pop(field, None)
    return body


def evidence(total, unit, body):
    price = body.get('unit_price', '').strip()
    price_unit = body.get('price_unit', '').strip()
    currency = body.get('currency', '')
    if not price:
        return {**{k: body[k] for k in PRICE_FIELDS if body.get(k)}, 'amount': ''} if price_unit or currency else {}
    if not re.fullmatch(r'[0-9]{1,12}(?:\.[0-9]{1,6})?', price) or Decimal(price) >= Decimal('1e12'):
        raise HTTPException(422, '入库单价须为非负数字，小于一万亿且最多六位小数')
    if not currency:
        raise HTTPException(422, '填写入库单价时请选择币种')
    if price_unit != unit:
        raise HTTPException(422, '入库单价必须按本次实收单位填写，不能自动换算计价单位')
    with localcontext() as context:
        context.prec = 50
        amount = (Decimal(total) * Decimal(price)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return dict(unit_price=price, price_unit=price_unit, currency=currency, amount=format(amount, '.2f'),
                price_basis='本次入库录入；实收总量乘单价，整单四舍五入至两位小数')
