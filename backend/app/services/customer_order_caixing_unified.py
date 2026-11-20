"""Caixing MIX groups, seasonal PO prices and explicit instruction clauses."""
import re
from decimal import Decimal, InvalidOperation
from copy import copy
from openpyxl.styles import PatternFill


def prepare(row, parsed):
    row['caixing_mix_no'] = parsed.mix_no
    row['source_unit_price_hkd'] = str(parsed.raw_unit_price_hkd) if parsed.raw_unit_price_hkd is not None else ''
    row['price_factor'] = str(parsed.price_factor) if parsed.price_factor is not None else ''
    row['price_basis'] = 'po-seasonal' if parsed.price_factor is not None else 'incomplete'
    row['lineage']['unit_price_hkd'] = f'PO原价 × {row["price_factor"] or "待定"}；按PO Delivery Date月份，11月至3月0.915，其余0.955'
    if not parsed.price_factor:
        row['issues'].append(dict(severity='warning',code='caixing_price_date_pending',field='requested_ship_date',message='未提供有效Delivery Date，季节折扣未确定，单价留空。',can_skip=False))
    text = re.sub(r'\s+', ' ', parsed.source_remarks.upper())
    if 'FRENCH + GP I/S' in text:
        row['manual'] = '法文＋GP说明书'
    elif re.search(r'(?:CUSTOMER|CUSOMER) INSTRUCTION', text):
        row['manual'] = '客版说明书'
    elif re.search(r'US STANDARD (?:INSTRUCTION|I/S)', text):
        row['manual'] = '美版说明书'
    product = re.match(r'\d+', str(row.get('product_no') or ''))
    product = product.group() if product else ''
    eu_clause = re.search(r'FOR ([\d, AND]+), EU MULTI-LINGUAL PACKAGING', text)
    if eu_clause and product in re.findall(r'\d+', eu_clause.group(1)):
        row['packaging'] = 'EU多语言包装'
        row['standard'] = '欧版'
        row['lineage']['standard'] = 'PO REMARKS · 当前货号的EU例外条款'
    if 'GP FRANCE IMPORTER & BARCODE INFO PRINTED OR LABEL ON PACKAGING' in text:
        row['label'] = 'GP法国进口商及条码信息（印刷或贴纸）'
    elif 'DISTRIBUTOR LABEL IS NOT REQUIRED' in text:
        row['label'] = '不需分销商贴纸'
    elif 'DISTRIBUTOR LABEL REQUIRED TO AFFIX' in text:
        row['label'] = '客分销商贴纸（贴包装盒）'
    labels = [row['label']] if row.get('label') else []
    if 'RFID LABEL REQUIRED FOR WALMART U.S. STORES' in text:
        labels.append('Walmart美国门店RFID标签')
    battery_items = re.findall(r'(?:MMPR )?ITEM:\s*([\d, ]+)', text)
    if 'BUTTON CELL WARNING LABEL' in text and any(product and product in re.findall(r'\d+', items) for items in battery_items):
        labels.append('客供纽扣电池警示标签及QR码警示标签（包装、产品及说明书；位置见原单）')
    row['label'] = '；'.join(labels)
    if 'USE CUSTOMER SHIP MARK' in text:
        row['carton_mark'] = '客版箱唛'
    elif 'USE PLAYMATES STANDARD SHIP MARK BUT WITH CUSTOMER' in text:
        row['carton_mark'] = 'Playmates标准箱唛＋客户资料；详见原单备注'
    elif 'SHIPPING MARK AS PER ATTACHMENT' in text:
        row['carton_mark'] = '按原单附件箱唛'
    # Preserve source clauses and their per-product conditions as evidence. Do
    # not make every item inherit warnings meant only for button-cell products.
    remarks = []
    for match in re.finditer(r'(?:^|\n)\s*REMARKS\s*:', parsed.source_remarks, re.I):
        block = parsed.source_remarks[match.end():]
        end = re.search(r'SHIPPING MARKS:|VENDOR CONF', block, re.I)
        block = block[:end.start()] if end else block
        remarks.append(re.sub(r'[ \t]+', ' ', block).strip())
    row['remarks'] = '\n'.join(dict.fromkeys(remarks))
    for field in ('manual','label','carton_mark','remarks'):
        if row.get(field): row['lineage'][field] = f'{row["source_po_file_name"]} · 原单REMARKS/SHIPPING MARKS，含原适用条件'
    return row


def recalculate(row):
    if row.get('_huaxing_customer') != 'caixing' or row.get('row_role') == 'parent' or row.get('_caixing_manual_price'):
        return
    from .customer_order_unified import _number, _number_text
    source = _number(row.get('source_unit_price_hkd'))
    try: month = int(str(row.get('requested_ship_date') or '').split('-')[1])
    except (ValueError, IndexError): month = 0
    factor = Decimal('0.915') if month in {11,12,1,2,3} else Decimal('0.955') if 1 <= month <= 12 else None
    row['price_factor'] = str(factor) if factor is not None else ''
    row['unit_price_hkd'] = _number_text(source * factor) if source is not None and factor is not None else ''
    row['lineage']['unit_price_hkd'] = f'PO原价 × {row["price_factor"] or "待定"}；按当前Delivery Date月份'


def write_group_and_prices(workbook, row, item_row, order_row, review_row):
    from .customer_order_unified import _number
    from .customer_order_unified import _excel_value
    if row.get('row_role') != 'parent':
        order, review = workbook['接单表'], workbook['正单评审表']
        price = _number(row.get('unit_price_hkd'))
        order.cell(order_row,14).value = _excel_value(price)
        order.cell(order_row,15).value = f'=IF(OR(J{order_row}="",N{order_row}=""),"",ROUND(J{order_row}*N{order_row},2))'
        # This customer's supplied template owns the exchange rate in P1.
        # Reuse it only when present; never invent a currency conversion rate.
        rate = order.cell(1,16)
        if rate.data_type == 'f' or (_number(rate.value) is not None and _number(rate.value) > 0):
            order.cell(order_row,16).value = f'=IF(OR(N{order_row}="",$P$1="",$P$1=0),"",ROUND(N{order_row}/$P$1,2))'
        else:
            order.cell(order_row,16).value = None
        order.cell(order_row,17).value = f'=IF(OR(J{order_row}="",P{order_row}=""),"",ROUND(J{order_row}*P{order_row},2))'
        for col, letter in ((14,'N'),(15,'O'),(16,'P'),(17,'Q')):
            review.cell(review_row,col).value = f"=IF('接单表'!{letter}{order_row}=\"\",\"\",'接单表'!{letter}{order_row})"
        for sheet, r in ((order,order_row),(review,review_row)):
            sheet.cell(r,14).number_format='0.00#####'
            sheet.cell(r,16).number_format='0.00#####'
            for col in (15,17): sheet.cell(r,col).number_format='0.00'
        return
    # A MIX heading is a label, never a second order quantity/amount.
    for name, r in (('ITEM表',item_row),('接单表',order_row),('正单评审表',review_row)):
        sheet=workbook[name]
        numeric = (11,12,13) if name=='ITEM表' else (10,11,12,14,15,16,17)
        for col in numeric: sheet.cell(r,col).value=None
        for col in range(1,29 if name=='ITEM表' else 20):
            cell=sheet.cell(r,col);cell.fill=PatternFill('solid',fgColor='DDEBF7');font=copy(cell.font);font.bold=True;cell.font=font
        sheet.cell(r,2).value='混装组头'
