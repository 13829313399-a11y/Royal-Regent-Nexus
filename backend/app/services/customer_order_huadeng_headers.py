"""Huadeng manual extensions. Headers do not imply shipping/QC data imports."""
from copy import copy

from .customer_order_360_manual_column import ensure_manual_columns
from .customer_order_jakks_unified import header_row

CUSTOMERS = ('casdon', 'jakks', 'goliath', 'simba', 'spin')
# Keep distinct business meanings: actual shipment is not planned delivery or
# warehouse handover; container number is not container type; invoice price is
# not the PO price. Existing explicit equivalent headings stay in place.
FIELDS = (
    ('跟单人', ('跟单人', '跟單人')),
    ('国家', ('国家', '國家', '走货国家', '走貨國家')),
    ('版本', ('版本',)),
    ('发票号', ('发票号', '發票號', '发票号码', '發票號碼')),
    ('发票日期', ('发票日期', '發票日期')),
    ('出货日期', ('出货日期', '出貨日期')),
    ('柜号', ('柜号', '櫃號', '柜号/车', '櫃號/車')),
    ('出货方式', ('出货方式', '出貨方式')),
    ('打发票价格', ('打发票价格', '打发票的价格', '打發票價格')),
    ('CO证书', ('CO证书', 'CO證書', 'COO证书', 'COO證書')),
    ('报告编号', ('报告编号', '報告編號', '验货报告编码', '验货报告编号', '驗貨報告編號')),
    ('纸箱复期', ('纸箱复期', '紙箱復期')),
    ('品牌名', ('品牌名', '品牌')),
    ('彩盒条码', ('彩盒条码', '彩盒條碼')),
    ('单价HK', ('单价HK', '港币单价', '港幣單價')),
    ('金额HK', ('金额HK', '港币金额', '港幣金額')),
    ('单价USD', ('单价USD', '美元单价', '美元單價')),
    ('总金额USD', ('总金额USD', '美元金额', '美元總金額')),
)


def ensure_headers(workbook, factory_id, customer_code):
    if factory_id != 'huadeng' or customer_code not in CUSTOMERS:
        return {}
    sheet = workbook['ITEM表']
    row = header_row(sheet)
    original_right = sheet.max_column
    body = [c for c in sheet._cells.values() if c.row > row and c.column == original_right]
    columns = {}
    for label, aliases in FIELDS:
        report = ensure_manual_columns(workbook, factory_id=factory_id,
            customer_code=customer_code, label=label, aliases=aliases,
            scopes=tuple(('huadeng', c) for c in CUSTOMERS), sheets=('ITEM表',))
        letters = report['columns']['ITEM表']
        columns[label] = letters
        if report['added']:
            for source in body:
                target = sheet[f'{letters[0]}{source.row}']
                if target.has_style:
                    continue
                target._style = copy(source._style)
                target.number_format = ('yyyy-mm-dd' if label in {'发票日期', '出货日期', '纸箱复期'}
                    else '0.00######' if label in {'单价HK', '单价USD', '打发票价格'}
                    else '#,##0.00' if label in {'金额HK', '总金额USD'} else '@')
    return columns


def clear_new_manual_fields(sheet, row):
    """A new PO cannot inherit another order's shipping/QC/manual formulas."""
    import re
    manual = {alias for _label, aliases in FIELDS[:-4] for alias in aliases}
    header = header_row(sheet)
    for c in list(sheet._cells.values()):
        if c.row == header and c.column > 28 and re.sub(r'\s+', '', str(c.value or '')) in manual:
            sheet.cell(row, c.column).value = None


def link_new_prices(workbook, columns, item_row, order_row):
    """Link only the exact newly generated row; old prices are never backfilled."""
    for label, source in (('单价HK', 'N'), ('金额HK', 'O'), ('单价USD', 'P'), ('总金额USD', 'Q')):
        targets = columns.get(label, [])
        # Duplicate user columns are ambiguous. Preserve them without picking one.
        if len(targets) == 1:
            cell = workbook['ITEM表'][f'{targets[0]}{item_row}']
            ref = f"'接单表'!{source}{order_row}"
            cell.value = f'=IF(LEN({ref})=0,"",{ref})'
            cell.number_format = '0.00######' if '单价' in label else '#,##0.00'
