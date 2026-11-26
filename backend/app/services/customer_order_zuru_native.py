"""ZURU original weekly references → copy-ready new orders; never edit a source book."""

from app.services.customer_order_ai import reviewed as ai_reviewed
from copy import copy
from datetime import date
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from io import BytesIO
import json
import re
from zipfile import ZipFile, ZIP_STORED, ZipInfo

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import column_index_from_string, get_column_letter

from .zuru_original import SourceBook, key, text, iso_date, xml_bytes, NS, XML

MAX_FILES = 10
MAX_BYTES = 35 * 1024**2  # aggregate references, not per-file allowance
BUNDLE_MARKER = 'zuru-references-v1.json'
SCHEMA = 'zuru-original-summary-v1'
SUMMARY = [
    ('source_order_date', '接单期'), ('customer_name', '第三方客户名称'), ('country', '走货国家'),
    ('contract_no', 'PO号'), ('po_no', '客PO'), ('reference_no', 'SKU'),
    ('product_no', '货号#'), ('product_name_zh', '中文名'), ('quantity', 'PO数量(pcs)'),
    ('inner_pack', '内箱装箱数量(pcs)'), ('units_per_carton', '外箱装箱数量(pcs)'),
    ('carton_count', '总箱数'), ('requested_ship_date', 'ZURU订单走货日期'),
    ('inspection_date', 'ZURU验货日期'), ('source_notes', '备注'), ('merchandiser', 'ZURU跟单员'),
    ('unit_price_usd', '单价USD'), ('amount_usd', '金额USD'),
]
ALIASES = {
    'source_order_date': ['香港接单日期', '来单日期', '接单期'],
    'customer_name': ['第三方客户名称', '客户名称'],
    'country': ['走货国家', '走货国家/规格'],
    'contract_no': ['ZURU PO NO#', '正单合同号', 'PO号'],
    'po_no': ['第三方客户 PO NO#', '客PO'],
    'reference_no': ['SKU'], 'product_no': ['ITEM#(货号)', 'ITEM#', '产品货号', '货号#'],
    'product_name_zh': ['货品名称', '产品名称', '中文名'],
    'quantity': ['PO数量(只)', 'PO数量', 'PO数量(pcs)'],
    'inner_pack': ['内箱装箱数量(只)', '内箱装箱数量(pcs)'],
    'units_per_carton': ['外箱装箱数量(只)', '外箱装箱数量(pcs)', '外箱装箱数'],
    'carton_count': ['总箱数'], 'requested_ship_date': ['CRD', 'ZURU订单走货日期'],
    'inspection_date': ['计划验货期', '验货日期', 'ZURU验货日期'],
    'source_notes': ['备注'], 'merchandiser': ['ZURU跟单组员', 'ZURU 跟单'],
    'unit_price_usd': ['单价USD'], 'amount_usd': ['金额USD'],
}
NUMBERS = {'quantity', 'inner_pack', 'units_per_carton', 'carton_count', 'unit_price_usd', 'amount_usd'}
DATES = {'source_order_date', 'requested_ship_date', 'inspection_date'}


def pack_references(files):
    if not 1 <= len(files) <= MAX_FILES or sum(len(b) for _, b in files) > MAX_BYTES:
        raise ValueError('ZURU 参照排期最多10份，合计不超过35MB')
    if any(not b or not n.lower().endswith('.xlsx') for n, b in files):
        raise ValueError('ZURU 参照排期必须是非空 XLSX 文件')
    if len(files) == 1:
        return files[0]
    output = BytesIO()
    entries = []
    with ZipFile(output, 'w', compression=ZIP_STORED) as archive:
        for i, (name, content) in enumerate(files):
            path = f'reference-{i:02d}.xlsx'
            archive.writestr(ZipInfo(path, (1980, 1, 1, 0, 0, 0)), content)
            entries.append({'path': path, 'name': name, 'sha256': sha256(content).hexdigest()})
        archive.writestr(ZipInfo(BUNDLE_MARKER, (1980, 1, 1, 0, 0, 0)),
                         json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(',', ':')))
    return 'ZURU多份参照排期.zip', output.getvalue()


def unpack_references(name, content):
    if len(content) > MAX_BYTES + 65536:
        raise ValueError('ZURU 参照排期超过35MB')
    with ZipFile(BytesIO(content)) as archive:
        if BUNDLE_MARKER not in archive.namelist():
            return [(name, content)]
        infos = archive.infolist()
        if len(infos) > MAX_FILES + 1 or len({i.filename for i in infos}) != len(infos) or any(i.flag_bits & 1 for i in infos):
            raise ValueError('ZURU 参照文件包无效')
        if sum(i.file_size for i in infos) > MAX_BYTES + 65536 or archive.getinfo(BUNDLE_MARKER).file_size > 32768:
            raise ValueError('ZURU 参照文件包过大')
        entries = json.loads(archive.read(BUNDLE_MARKER))
        if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_FILES or len(infos) != len(entries) + 1:
            raise ValueError('ZURU 参照文件清单无效')
        files = []
        for i, entry in enumerate(entries):
            if entry.get('path') != f'reference-{i:02d}.xlsx' or not entry.get('name', '').lower().endswith('.xlsx'):
                raise ValueError('ZURU 参照文件路径无效')
            data = archive.read(entry['path'])
            if sha256(data).hexdigest() != entry['sha256']:
                raise ValueError('ZURU 参照文件校验失败')
            files.append((entry['name'], data))
        return files


async def read_uploads(customer, first, extra=()):
    from fastapi import HTTPException
    if extra and customer != 'zuru':
        raise HTTPException(400, '只有 ZURU 支持多份参照排期')
    uploads = [first, *(extra or [])]
    if len(uploads) > MAX_FILES:
        raise HTTPException(400, 'ZURU 参照排期最多10份')
    files, total = [], 0
    for upload in uploads:
        name = (upload.filename or '').replace('\\', '/').rsplit('/', 1)[-1]
        if not name.lower().endswith('.xlsx') or name.startswith('._'):
            raise HTTPException(400, '客户排期只支持真实的 XLSX 文件')
        content = await upload.read(MAX_BYTES + 1)
        total += len(content)
        if not content or total > MAX_BYTES:
            raise HTTPException(400, '客户排期为空或合计超过35MB')
        files.append((name, content))
    return pack_references(files)


def family(value):
    match = re.match(r'^(\d{4,5})(?:[A-Z]|-|$)', key(value))
    return match.group(1) if match else ''


def uses_original(name, content):
    files = unpack_references(name, content)
    if len(files) > 1:
        return True
    book = SourceBook(files[0][1], files[0][0])
    try:
        # Retain old immutable uniform imports/replays. New original weekly
        # schedules never go through the three-sheet validator.
        return not {'接单表', '正单评审表', 'ITEM表'} <= set(book.sheets)
    finally:
        book.close()


def references(name, content):
    files = unpack_references(name, content)
    layouts, history = [], []
    for file_index, (filename, data) in enumerate(files):
        book = SourceBook(data, filename)
        found = False
        try:
            for sheet in book.sheets:
                header, fields, labels = 0, {}, {}
                records = []
                for number, values, formulas in book.rows(sheet):
                    if not header and number <= 20:
                        mapping = {field: col for field, aliases in ALIASES.items() for col, v in values.items() if key(v) in {key(a) for a in aliases}}
                        if {'contract_no', 'product_no', 'quantity'} <= mapping.keys() and ('requested_ship_date' in mapping or 'reference_no' in mapping):
                            header, fields = number, mapping
                            labels = {column_index_from_string(c): v for c, v in values.items()}
                            if max(labels) > 256:
                                raise ValueError(f'{filename}/{sheet}有效表头超过256列')
                        continue
                    if header and number > header:
                        record = {field: values.get(col, '') for field, col in fields.items()}
                        if re.fullmatch(r'\d{8,14}', key(record.get('contract_no'))) and text(record.get('product_no')):
                            for field in DATES & record.keys():
                                if record[field]:
                                    try: record[field] = iso_date(record[field], book.epoch)
                                    except ValueError: pass
                            record.update(file=filename, sheet=sheet, source_row=number)
                            records.append(record)
                if not header:
                    continue
                found = True
                history.extend(records)
                if re.search(r'已完成|已走货|已出货|已完货|完成订单|取消|库存|贴纸|备料|半成品|包材|包装MA|车缝MA|(?:^|[^A-Z])MA(?:$|[^A-Z])', sheet, re.I):
                    continue
                role = 'item' if re.search('ite[am]+m?|item', sheet, re.I) else 'orders'
                widths = {}
                root = XML.fromstring(xml_bytes(book.archive, book.sheets[sheet]))
                for col in root.findall(f'{NS}cols/{NS}col'):
                    for c in range(max(1,int(col.get('min','1'))), min(max(labels),int(col.get('max','1'))) + 1):
                        widths[c] = min(80, max(5, float(col.get('width','16'))))
                layouts.append(dict(widths=widths, data_row=records[0]['source_row'] if records else header+1, file_index=file_index, name=filename, sheet=sheet, header=header,
                    fields=fields, labels=labels, role=role,
                    families=sorted(({family(r['product_no']) for r in records} | ({family(sheet)} if not records else set())) - {''}), records=records))
            if not found:
                raise ValueError(f'{filename}：未找到 ZURU 原排期的 PO、货号、数量及 CRD/SKU 表头')
        finally:
            book.close()
    if not layouts:
        raise ValueError('参照排期没有可用的未完成订单页')
    return files, layouts, history


def warning(row, code, message, field='row'):
    row['issues'].append(dict(severity='warning', code=code, field=field, message=message,
                              can_skip=False, skip_key='', skip_label=''))


def resolve(rows, layouts, history, edited=()):
    seen = set()
    for row in rows:
        row['issues'] = [i for i in row['issues'] if not i['code'].startswith('zuru_reference_')]
        row['_zuru_targets'] = []
        candidates = [h for h in history if key(h['product_no']) == key(row['product_no'])]
        if 'product_name_zh' not in edited:
            names = {text(h.get('product_name_zh')) for h in candidates if text(h.get('product_name_zh'))}
            row['product_name_zh'] = next(iter(names)) if len(names) == 1 else ''
        same = [h for h in candidates if key(h['contract_no']) == key(row['contract_no'])
                and h.get('reference_no') and key(h['reference_no']) == key(row['reference_no'])]
        if not same and any(key(h['contract_no']) == key(row['contract_no']) for h in candidates):
            warning(row, 'zuru_reference_candidate', '历史同PO同货号但未找到相同原行号；本行仍列入新单，请核对是否分批或已手工录入。')
        identity = (key(row['contract_no']), key(row['reference_no']), key(row['product_no']))
        row['_zuru_existing'] = bool(same) or identity in seen
        if row['_zuru_existing']:
            warning(row, 'zuru_reference_existing', '排期或本批已有同 PO / 原行号 / 货号，列入“已有订单参考”，不重复列入可复制新单页。')
            for old in same:
                differences = []
                for field, label in [('quantity', '数量'), ('requested_ship_date', '货期'), ('po_no', '客PO')]:
                    if text(old.get(field)) and key(old[field]) != key(row.get(field)):
                        differences.append(f'{label}：原表 {old[field]} → 本单 {row.get(field) or "空白"}')
                if differences:
                    warning(row, 'zuru_reference_difference', f'{old["file"]}/{old["sheet"]}第{old["source_row"]}行存在差异：' + '；'.join(differences) + '。请在原表人工修改。')

        seen.add(identity)
        matches = [layout for layout in layouts if family(row['product_no']) in layout['families']]
        for role in ('orders', 'item'):
            targets = [l for l in matches if l['role'] == role]
            # Copies of the same layout in multiple reference books are one target.
            unique = {}
            for l in targets:
                signature = tuple(sorted(l['labels'].items()))
                unique.setdefault(signature, l)
            if len(unique) == 1:
                target = next(iter(unique.values()))
                row['_zuru_targets'].append((target['file_index'], target['sheet']))
            elif len(unique) > 1:
                warning(row, 'zuru_reference_ambiguous_' + role, '同系列匹配多种原排期列结构；明细保留在新单汇总，请自行选择复制位置。')
        if not row['_zuru_targets']:
            warning(row, 'zuru_reference_unmapped', '参照排期未找到唯一对应产品页；明细保留在新单汇总。')
        for field, label in [('requested_ship_date', '走货期'), ('product_name_zh', '中文品名'), ('unit_price_usd', '美元单价')]:
            if not row.get(field):
                warning(row, 'zuru_reference_missing_' + field, f'{label}暂无可靠来源，留空，可直接生成后补填。', field)
        try:
            q, pack = Decimal(text(row['quantity'])), Decimal(text(row['units_per_carton']))
            row['carton_count'] = str(q / pack) if pack > 0 else ''
        except (InvalidOperation, ZeroDivisionError):
            row['carton_count'] = ''
        row['target_template'] = 'ZURU_ORIGINAL_NEW_ORDER_SUMMARY_V1'
        row['item_sheet_name'] = '新单数据'
        row['customer_country'] = ' / '.join(filter(None, [row['customer_name'], row['country']]))
        row['status'] = 'warning' if row['issues'] else 'valid'
        row['status_label'] = '有提醒' if row['issues'] else '可生成'


@ai_reviewed
def preview(*, factory_id, received_date, po_files, schedule_file_name, schedule_content, **kwargs):
    from .customer_order_zuru import create_rows
    from .customer_order_manual import decorate_manual_resolution_policy
    from .customer_order_unified import _combined_hash
    if factory_id not in {'huakang-a', 'huaxing'}:
        raise ValueError('ZURU 只支持华康A、华兴独立入口')
    date.fromisoformat(received_date)
    _, layouts, history = references(schedule_file_name, schedule_content)
    rows, notes, input_template = create_rows(po_files, received_date, [], factory_id=factory_id)
    resolve(rows, layouts, history)
    names = [n for n, _ in po_files]
    hashes = [sha256(b).hexdigest() for _, b in po_files]
    result = dict(preview_schema_version=SCHEMA, factory_id=factory_id, customer_code='zuru',
        customer_name='ZURU', po_file_name=names[0] if len(names) == 1 else f'{len(names)}个文件',
        po_file_names=names, po_file_count=len(names), source_po_sha256s=hashes,
        source_po_sha256=_combined_hash(names, hashes), schedule_file_name=schedule_file_name,
        source_schedule_sha256=sha256(schedule_content).hexdigest(), input_template=input_template,
        target_template='ZURU_ORIGINAL_NEW_ORDER_SUMMARY_V1',
        output_file_name=f'{"华康A" if factory_id == "huakang-a" else "华兴"}_ZURU新单汇总_{received_date}.xlsx',
        rows=rows, warnings=[*notes[:-1], '多份原排期仅作查重及格式参照；生成独立新单汇总，原文件不修改。',
        '新单数据沿用原入总排期18列顺序；对应页按原排期列顺序提供可复制数值。',
        '验货期、生产进度、MA、港币价等没有本单可靠来源的字段留空，不继承历史订单状态。'],
        summary=dict(total=len(rows), valid=sum(not r['issues'] for r in rows), warning=sum(bool(r['issues']) for r in rows), blocked=0))
    return decorate_manual_resolution_policy(result)


def write_value(cell, value, field):
    if value is None or value == '':
        return
    if field in NUMBERS:
        try:
            number = Decimal(str(value))
            if number.is_finite():
                cell.value = float(number)
                cell.number_format = '0.########' if field in {'unit_price_usd', 'amount_usd'} else '0.########'
        except InvalidOperation:
            pass
    elif field in DATES:
        cell.value = date.fromisoformat(str(value)[:10])
        cell.number_format = 'yyyy-mm-dd'
    else:
        cell.value = str(value)
        cell.data_type = 's'  # No formula interpretation of PO supplied text.
        cell.number_format = '@'


def export(*, manual_overrides=None, skipped_issue_keys=None, **args):
    from .customer_order_manual import apply_overrides_to_preview, coerce_manual_value
    from .customer_order_zuru import finish_row
    result = preview(**args)
    for override in manual_overrides or []:
        coerce_manual_value(override['field'], override['value'])
    apply_overrides_to_preview(result, manual_overrides or [])
    for override in manual_overrides or []:
        if override['field'] == 'unit_price_usd':
            for row in result['rows']:
                if row['id'] == override['row_id']: row['unit_price_usd'] = override['value']
    applied_issues = {r['id']: list(r['issues']) for r in result['rows']}
    files, layouts, history = references(args['schedule_file_name'], args['schedule_content'])
    for row in result['rows']:
        edited = {o['field'] for o in manual_overrides or [] if o['row_id'] == row['id']}
        resolve([row], layouts, history, edited)
        submitted = {o['issue_key'] for o in manual_overrides or [] if o['row_id'] == row['id']}
        current_keys = {i.get('skip_key') for i in row['issues']}
        row['issues'].extend(i for i in applied_issues[row['id']] if i.get('skip_key') in submitted and i.get('skip_key') not in current_keys)
        finish_row(row)
    # Reapply batch duplicate classification after edits (same row must not be copied twice).
    seen = set()
    for row in result['rows']:
        identity = tuple(key(row[k]) for k in ('contract_no', 'reference_no', 'product_no'))
        if identity in seen: row['_zuru_existing'] = True
        seen.add(identity)
    wb = Workbook(); wb.remove(wb.active)
    blue = Font(name='宋体', size=11, color='0000FF')
    head = PatternFill('solid', fgColor='0B5360')
    border = Border(*(Side(style='thin', color='BDD7D4') for _ in range(4)))
    def standard_sheet(name, rows):
        ws = wb.create_sheet(name); ws.freeze_panes = 'A2'
        for c, (field, label) in enumerate(SUMMARY, 1):
            cell = ws.cell(1, c, label); cell.font = Font(name='宋体', size=11, bold=True, color='FFFFFF'); cell.fill = head
            cell.alignment = Alignment(wrap_text=True, vertical='center')
            ws.column_dimensions[get_column_letter(c)].width = 40 if field == 'source_notes' else 22 if field in {'customer_name','product_no','reference_no'} else 16
        for n, row in enumerate(rows, 2):
            for c, (field, _) in enumerate(SUMMARY, 1):
                cell = ws.cell(n, c); write_value(cell, row.get(field), field); cell.font = blue; cell.border = border
                cell.alignment = Alignment(vertical='center', wrap_text=True)
            ws.row_dimensions[n].height = 40
        ws.auto_filter.ref = f'A1:R{max(1,len(rows)+1)}'
    new = [r for r in result['rows'] if not r['_zuru_existing']]
    standard_sheet('新单数据', new)
    existing = [r for r in result['rows'] if r['_zuru_existing']]
    if existing: standard_sheet('已有订单参考', existing)
    source_books = {}
    try:
        for layout in layouts:
            rows = [r for r in new if (layout['file_index'], layout['sheet']) in r['_zuru_targets']]
            if not rows: continue
            idx = layout['file_index']
            if idx not in source_books: source_books[idx] = load_workbook(BytesIO(files[idx][1]), read_only=True)
            source = source_books[idx][layout['sheet']]
            title = re.sub(r'[\[\]:*?/\\]', '_', layout['sheet']).strip()[:26] + '_新单'
            if title in wb.sheetnames: title = title[:27] + f'_{idx+1}'
            ws = wb.create_sheet(title); ws.freeze_panes = 'A2'
            max_col = max(layout['labels'])
            header_cells = next(source.iter_rows(min_row=layout['header'], max_row=layout['header'], max_col=max_col))
            sample_cells = next(source.iter_rows(min_row=layout['data_row'], max_row=layout['data_row'], max_col=max_col))
            for c in range(1, max_col + 1):
                old = header_cells[c-1]; cell = ws.cell(1, c)
                if c in layout['labels']: cell.value = layout['labels'][c]; cell.data_type='s'
                cell.font=copy(old.font); cell.fill=copy(old.fill); cell.border=copy(old.border); cell.alignment=copy(old.alignment)
                ws.column_dimensions[get_column_letter(c)].width = layout['widths'].get(c, 16)
            for n, row in enumerate(rows, 2):
                for c in range(1,max_col+1):
                    cell=ws.cell(n,c); old=sample_cells[c-1]; new_font=copy(old.font or blue); new_font.color='0000FF'; cell.font=new_font; cell.border=copy(old.border or border); cell.alignment=copy(old.alignment or Alignment(vertical='center')); cell.number_format=old.number_format or 'General'
                for field,col in layout['fields'].items():
                    write_value(ws[f'{col}{n}'], row.get(field), field)
                ws.row_dimensions[n].height=40
        notes=wb.create_sheet('复制说明')
        for line in ['先在“新单数据”查看全部新单；按对应“_新单”页复制数据行（不含表头），粘贴值到原排期。',
            '已有订单及本批重复列入“已有订单参考”，不重复加入新单；差异请在原表人工处理。',
            '原格式页保留列顺序，后续人工进度/验货/MA/港币价留空；美元单价金额在新单数据页。',
            '可复制页均为数值或文本，不带依赖其他工作簿行号的公式。', *result['warnings']]: notes.append([line])
        for r in result['rows']:
            for issue in r['issues']: notes.append([r['reference_no']+' / '+r['product_no']+'：'+issue['message']])
        notes.column_dimensions['A'].width=100
        for row in notes:
            row[0].data_type='s'; row[0].alignment=Alignment(wrap_text=True,vertical='center')
        result['summary']['new_rows']=len(new)
        stream=BytesIO(); wb.save(stream)
        return stream.getvalue(), result['output_file_name'], result
    finally:
        for book in source_books.values(): book.close()
        wb.close()
