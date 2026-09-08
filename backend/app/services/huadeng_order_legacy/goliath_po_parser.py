"""Goliath Far East purchase orders with column-aware decimal extraction."""
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO
import re

import pdfplumber


def _date(text):
    text=re.sub(r'[-/]', ' ', text.strip())
    for fmt in ('%d %B %Y','%d %b %Y'):
        try:return datetime.strptime(text,fmt).date().isoformat()
        except ValueError:pass
    raise ValueError(f'Goliath 日期无法识别：{text}')


def _decimal(text, field):
    try:return Decimal(re.sub(r'[,\s]', '', text))
    except InvalidOperation as exc:raise ValueError(f'Goliath {field}无法识别：{text}') from exc


def parse_po(content: bytes, filename: str):
    records=[]
    with pdfplumber.open(BytesIO(content)) as pdf:
        texts=[p.extract_text(x_tolerance=2,y_tolerance=3) or '' for p in pdf.pages]
        text='\n'.join(texts)
        if not re.search(r'Goliath\s+Far\s+East',text,re.I) or 'Purchase Order' not in text:
            raise ValueError('不是可识别的 Goliath Far East 正式 PO（需 PDF 文字层）')
        orders=set(re.findall(r'Order\s*#\s*(T_\d+\s*-\s*P[A-Z]{2}\d+_\d+)',text,re.I))
        orders={re.sub(r'\s+','',v) for v in orders}
        if len(orders)!=1:raise ValueError('Goliath PO 订单号缺失或存在多个不同订单号')
        order=orders.pop()
        order_date=re.search(r'Order date\s+(\d{1,2}\s+\w+\s+\d{4})',text,re.I)
        cargo=re.findall(r'CARGO READY DATE:\s*(\d{1,2}[ -]+[A-Z]+[ -]+\d{4})',text,re.I)
        po_refs=set(re.findall(r'(?:US|UK|EU)\s+PO\s+NO\.?\s*:?\s*(P[A-Z]{2}\d+_\d+)',text,re.I))
        if len(set(cargo))>1 or len(po_refs)>1:
            raise ValueError('Goliath PO 含多个交期或客户 PO，请按对应明细核对后导入')
        customer_po=next(iter(po_refs),'')
        ship_date=_date(cargo[0]) if cargo else ''
        ship=re.search(r'(?<!BEFORE )SHIP DATE\s*:\s*(\d{1,2}[ -]+[A-Z]+[ -]+\d{4})',text,re.I)
        if ship:ship_date=_date(ship[1])
        inspection=re.search(r'(?<!BV )INSPECTION DATE\s*:\s*(\d{1,2}[ -]+[A-Z]+[ -]+\d{4})',text,re.I)
        bv=re.search(r'BV INSPECTION DATE\s*:\s*(\d{1,2}[ -]+[A-Z]+[ -]+\d{4})',text,re.I)
        inspection_date=_date(inspection[1]) if inspection else ''
        ship_date_derived = not ship_date and bool(inspection_date)
        if not ship_date and inspection_date:
            derived=datetime.fromisoformat(inspection_date).date()+timedelta(days=3)
            while derived.weekday()>=5:derived-=timedelta(days=1)
            ship_date=derived.isoformat()
        first_words=pdf.pages[0].extract_words()
        deliver=next((w for w in first_words if w['text']=='Deliver'),None)
        customer='Goliath'
        if deliver:
            right=[w for w in first_words if w['x0']>=deliver['x0']-2 and w['top']>deliver['bottom'] and w['top']<deliver['bottom']+25]
            if right:
                y=min(w['top'] for w in right)
                customer=' '.join(w['text'] for w in sorted(right,key=lambda w:w['x0']) if abs(w['top']-y)<3)
        for page_number,page in enumerate(pdf.pages,1):
            words=page.extract_words(x_tolerance=2,y_tolerance=3)
            header=next((w for w in words if w['text']=='ITF14'),None)
            if header is None:
                if re.search(r'(?m)^\s*\d{5,}\.[A-Z0-9]{3,}\s',texts[page_number-1]):
                    raise ValueError('Goliath 续页存在未识别商品表格，未生成不完整订单')
                continue  # legal-terms page is not an order line
            headers=[w for w in words if abs(w['top']-header['top'])<3]
            by_name={w['text']:w for w in headers}
            if not {'Description','Barcode','No.','Qty','price','Amount'} <= by_name.keys():
                raise ValueError('Goliath 明细列布局不匹配，未导入未知格式')
            edges=[0,by_name['Description']['x0']-5,header['x0']-16,
                   by_name['Barcode']['x1']+6,by_name['No.']['x1']+4,
                   by_name['Qty']['x1']+4,by_name['price']['x1']+5,page.width]
            items=[w for w in words if w['top']>header['top']+8 and w['x0']<edges[1] and re.fullmatch(r'\d{5,}\.[A-Z0-9]{3,}',w['text'])]
            for i,item in enumerate(items):
                top=item['top']-1
                end=items[i+1]['top']-1 if i+1<len(items) else page.height
                stops=[w['top']-1 for w in words if w['top']>top+3 and (
                    (w['x0']<edges[1] and re.match(r'(?:US|UK|EU)DOMPO',w['text'])) or
                    (edges[1]<=w['x0']<edges[2] and w['text']=='CARGO') or
                    (w['text']=='Total' and w['x0']>edges[3]))]
                end=min([end,*stops])
                def column(n):
                    return (page.crop((edges[n],top,edges[n+1],end)).extract_text(x_tolerance=2,y_tolerance=3) or '').strip()
                qty=_decimal(column(4),'数量')
                price=_decimal(column(5),'USD 单价')
                amount=_decimal(column(6),'USD 金额')
                flags=[]
                if ship_date_derived:
                    flags.append({'level':'warning','code':'ship_holiday_review','field':'requested_ship_date','text':'走货期按验货期后3天并避开周末推算，节假日待复核。'})
                if qty<=0 or qty!=qty.to_integral_value():
                    flags.append({'level':'high','code':'invalid_quantity','field':'quantity','text':'Goliath 数量须为正整数件数'})
                if abs(qty*price-amount)>Decimal('0.01'):
                    flags.append({'level':'high','code':'price_amount_conflict','field':'unit_price_usd','text':'Goliath 数量×单价与 PO 金额不一致，请核对单价末位及换行'})
                records.append({'contract_no':order,'customer_po':customer_po,
                    'customer':customer,
                    'item_no':item['text'],'english_name':' '.join(column(1).split()),
                    'quantity':str(qty),'unit_price_usd':str(price),'amount_usd':str(amount),
                    'barcode':re.sub(r'\s+','',column(2)),
                    'ship_date':ship_date,'inspection_date':inspection_date,'customer_inspection_date':_date(bv[1]) if bv else '',
                    'remarks':'SAFETY NETTING IS REQUIRED FOR ALL CONTAINERS.' if re.search(r'SAFETY NETTING IS REQUIRED FOR\s+ALL\s+CONTAINERS',text,re.I) else '',
                    'customer_label':'LABEL REQUIRED' if re.search(r'REMARKS\s*[.:]+\s*LABEL REQUIRED',text,re.I) else '',
                    'po_order_date':_date(order_date[1]) if order_date else '',
                    'source_file':filename,'source_sheet':f'PDF 第{page_number}页','source_row':i+1,
                    'flags':flags})
        if not records:raise ValueError('Goliath PO 未识别到产品明细')
        totals=set(re.findall(r'Total USD Excl\. VAT\s+([\d,]+\.\d+)',text))
        if len(totals)!=1:
            raise ValueError('Goliath PO 缺少唯一可核对的 USD 总金额')
        if abs(sum(Decimal(r['amount_usd']) for r in records)-_decimal(totals.pop(),'总金额'))>Decimal('0.01'):
            raise ValueError('Goliath 已识别明细金额与 PO 总金额不一致，可能存在未识别的明细')
    return records
