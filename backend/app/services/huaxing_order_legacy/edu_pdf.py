"""EDU-SCIENCE purchase orders, with page evidence and bounded scanned-PDF OCR."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import re

from .edu_schedule import add_derived_fields
from .multi_po_parser import read_pdf_pages

ITEM = re.compile(r'(?m)^[ \t|│]*(?:\d+[ \t]+)?(F\d{2}-[A-Z0-9]+-[A-Z0-9]+)\b', re.I)
NUMBER = r'\d[\d,]*(?:\.\d+)?'
DATE = r'20\d{2}[-/]\d{1,2}[-/]\d{1,2}'
MONEY = re.compile(rf'({NUMBER})[ \t]*/[ \t]*(?:SET|PCS?|EA|PAIR|UNIT)S?\b\s+({NUMBER})\s+({NUMBER})', re.I)
DELIVERY = re.compile(rf'\bDelivery\s*[:：]?\s*({DATE})\s+Qty\s*[:：]?\s*({NUMBER})', re.I)


def decimal(value):
    try:
        result = Decimal(str(value).replace(',', ''))
        return result if result.is_finite() else None
    except InvalidOperation:
        return None


def iso_date(value):
    if not value:
        return None
    try:
        return date(*(int(part) for part in re.split(r'[-/]', value))).isoformat()
    except ValueError:
        return None


def find(pattern, text):
    match = re.search(pattern, text, re.I | re.M)
    return match.group(1).strip() if match else ''


def parse_pages(pages, filename, used_ocr=False):
    rows, warnings = [], []
    for page_number, text in enumerate(pages, 1):
        if not re.search(r'EDU[\s-]*SCIENCE', text, re.I) or not re.search(r'PURCHASE\s+ORDER', text, re.I):
            raise ValueError(f'第 {page_number} 页不是已支持的 EDU-SCIENCE 采购单；未忽略该页。')
        # The shared OCR reader appends a sparse second reading after the page.
        # Only the primary table above its first Total is a source of order lines.
        end = re.search(r'^\s*Total\s*:', text, re.I | re.M)
        if not end:
            raise ValueError(f'EDU PDF 第 {page_number} 页未找到明细合计边界，请核对原件。')
        table = text[:end.start()]
        matches = list(ITEM.finditer(table))
        candidates = list(re.finditer(r'(?m)^[ \t|│]*(?:\d+[ \t]+)?F\d{2}[- ]', table, re.I))
        if not matches or len(matches) != len(candidates):
            raise ValueError(f'EDU PDF 第 {page_number} 页存在无法识别的商品明细；未只导出部分商品。')
        header = table[:matches[0].start()]
        po = find(r'\bP[.\s]*O[.\s]*[:#]\s*(\d{6,})\b', header)
        currency = find(r'\bCurrency\s*[:：]?\s*([A-Z]{3})\b', header).upper()
        order_date = iso_date(find(rf'\bDate\s*[:：]?\s*({DATE})', header))
        # SO is separately labelled in EDU's source and is not a Contract/S/C.
        so = find(r'\b(SO\s*\d{5,})\b', text[end.start():])
        contract = find(r'(?:Contract(?:\s+No\.?)?|S/C(?:\s+No\.?)?)\s*[:：#]\s*([^\s]+)', header)
        page_amounts = []
        for index, item in enumerate(matches):
            block = table[item.start():matches[index + 1].start() if index + 1 < len(matches) else len(table)]
            money = MONEY.search(block)
            deliveries = list(dict.fromkeys(DELIVERY.findall(block)))
            if len(deliveries) > 1:
                raise ValueError(f'{item[1]}：同一商品包含多个 Delivery 批次，当前 PDF 版式需拆分或使用 Excel 原单。')
            if not money and not deliveries:
                raise ValueError(f'{item[1]}：未识别到数量所在的明细列或 Delivery 行；未只导出部分商品。')
            price = decimal(money[1]) if money else None
            printed_qty = decimal(money[2]) if money else None
            amount = decimal(money[3]) if money else None
            delivery_qty = decimal(deliveries[0][1]) if deliveries else None
            candidates_qty = {q for q in (printed_qty, delivery_qty) if q is not None and q > 0 and q == q.to_integral_value()}
            notices = []
            quantity = next(iter(candidates_qty)) if len(candidates_qty) == 1 else None
            if len(candidates_qty) > 1:
                reconciled = {q for q in candidates_qty if price is not None and amount is not None
                              and abs(q * price - amount) <= Decimal('0.01')}
                quantity = next(iter(reconciled)) if len(reconciled) == 1 else None
            if printed_qty is not None and delivery_qty is not None and printed_qty != delivery_qty:
                if quantity is not None and price is not None and amount is not None and abs(quantity * price - amount) <= Decimal('0.01'):
                    notices.append(f'原表数量读数 {money[2]}，Delivery Qty {deliveries[0][1]}；结合单价与金额取 {quantity}，请对照原件核对。')
                else:
                    quantity = None
                    notices.append(f'原表数量与 Delivery Qty 不一致（{money[2]} / {deliveries[0][1]}），数量留空待补。')
            if quantity is not None and price is not None and amount is not None and abs(quantity * price - amount) > Decimal('0.01'):
                notices.append('数量×单价与原单金额不一致，保留原单各项读数，请核对。')
            if currency != 'HKD':
                notices.append(f'原单币种为 {currency or "未识别"}，港币单价及金额留空，不自动换算或继承历史价格。')
            if used_ocr:
                notices.append('扫描 PDF 已使用 OCR，识别结果请对照原件查看；此提示不阻断生成。')
            description_end = min([m.start() for m in (money, DELIVERY.search(block)) if m] or [len(block)])
            description = ' '.join(block[len(item[0]):description_end].split())
            # Descriptions wrap below the numeric columns. Preserve those lines,
            # but never use a warehouse number as carton packing.
            if money:
                tail = block[money.end():DELIVERY.search(block).start() if deliveries else len(block)]
                description = ' '.join(filter(None, [description, re.split(r'(?:仓|倉)\s*[:：]', tail)[0].strip()]))
            customer = find(r'/\s*([^/{\n]+?)\s*[{｛]', description)
            ship_date = iso_date(deliveries[0][0]) if deliveries else None
            notes = '; '.join(filter(None, [so, *notices]))
            row = dict(customer_type='EDU', customer_po=po, contract_no=contract, so_no=so,
                customer=customer, country='', item_no=item[1].upper(), product_name=description,
                order_date=order_date, ship_date=ship_date, quantity=float(quantity) if quantity is not None else None,
                case_pack=None, unit_price=float(price) if price is not None and currency == 'HKD' else None,
                amount=float(amount) if amount is not None and currency == 'HKD' else None,
                notes=notes, remarks=notes, source_page=page_number, source_row=index + 1,
                source_sheet='PDF OCR' if used_ocr else 'PDF', source_pdf=True, source_currency=currency,
                source_unit_price=str(price) if price is not None else '', source_amount=str(amount) if amount is not None else '',
                source_quantity=money[2] if money else '', source_delivery_quantity=deliveries[0][1] if deliveries else '',
                source_text=block, source_notices=notices)
            add_derived_fields(row)
            rows.append(row)
            if amount is not None:
                page_amounts.append(amount)
            warnings.extend(f'第 {page_number} 页 {item[1]}：{notice}' for notice in notices)
        total = decimal(find(rf'^\s*Total\s*:\s*({NUMBER})', text[end.start():]))
        if total is not None and len(page_amounts) == len(matches) and abs(sum(page_amounts) - total) > Decimal('0.01'):
            warnings.append(f'第 {page_number} 页明细金额与合计不一致，请核对原单；未用合计改写明细。')
    return dict(filename=filename, type='pdf', customer_type='EDU', document_type='purchase_order',
        meta={'pages': len(pages), 'used_ocr': used_ocr, 'row_count': len(rows)}, rows=rows,
        warnings=list(dict.fromkeys(warnings)), text_preview='\n'.join(pages)[:1600])


def parse_pdf(source, filename):
    from .edu_po_parser import _read_bytes
    content = _read_bytes(source)
    pages, used_ocr = read_pdf_pages(content, max_pages=20)
    # The shared native-text threshold is averaged. A mixed scanned/text file
    # must not silently lose a blank native page.
    if not used_ocr and any(not text.strip() for text in pages):
        from app.services.customer_order_ocr import read_scanned_order_pdf
        pages, used_ocr = read_scanned_order_pdf(content, len(pages)), True
    return parse_pages(pages, filename, used_ocr)
