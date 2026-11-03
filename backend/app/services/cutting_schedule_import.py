"""Bounded schedule intake: archive evidence, create ledger sources, never post stock."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from io import BytesIO
from pathlib import PurePath
import re
from zipfile import ZipFile

import openpyxl
from fastapi import HTTPException
from pydantic import Field
from sqlalchemy import select
from app.models.customer_order_ledger import OrderLedgerLine as Line, OrderLedgerSource as Source, OrderLedgerLineSource as Link, OrderLedgerDispatch as Dispatch
from app.services import cutting_ops as c, cutting_schemas as s, customer_order_ledger as ledger
from app.services.auth import now_text
from app.services.order_workbook_bounds import worksheet_bounds

MAX_BYTES = 10 * 1024 * 1024
SCHEMA = 'cutting-schedule-v1'
FIELDS = {'客户': 'customer_name', '客名': 'customer_name', '洋行名': 'customer_name',
    '订单号': 'reference_no', '生产单号': 'reference_no', 'so#/reference': 'reference_no',
    '货号': 'product_no', '产品编号': 'product_no', '货名': 'product_name_zh', '产品中文名称': 'product_name_zh',
    '数量': 'quantity', '订单数量': 'quantity', '交期': 'requested_ship_date', '客要求走货期': 'requested_ship_date',
    '单位': 'unit'}
REQUIRED = set(FIELDS.values())
COLUMN_LABELS = {'customer_name': '客户', 'reference_no': '订单号', 'product_no': '货号',
    'product_name_zh': '货名', 'quantity': '数量', 'requested_ship_date': '交期', 'unit': '单位'}
ACTION = 'schedule-import'


class Confirm(s.Command):
    fingerprint: str = Field(pattern=r'^[a-f0-9]{64}$')
    file_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    file_name: str = Field(min_length=1, max_length=255)
    confirmed: bool


class Recover(s.Strict):
    command: Confirm


def filename(value):
    return str(value or '').replace('\\', '/').split('/')[-1][:255]


def text(cell):
    value = cell.value
    if value is None: return ''
    if isinstance(value, (datetime, date)): return value.strftime('%Y-%m-%d')
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        result = str(int(value)) if int(value) == value else str(value)
        if re.fullmatch(r'0+', cell.number_format or ''): result = result.zfill(len(cell.number_format))
        return result
    return str(value).strip()


def parse(content, name):
    c.require(PurePath(name).suffix.lower() == '.xlsx', '请选择 .xlsx 排期文件', 422)
    c.require(0 < len(content) <= MAX_BYTES, '排期文件为空或超过 10 MB', 422)
    try:
        with ZipFile(BytesIO(content)) as z:
            c.require(len(z.infolist()) <= 1500 and sum(i.file_size for i in z.infolist()) <= 50 * 1024 * 1024,
                      '工作簿解压后过大，请拆分', 422)
            c.require(not any('externallinks/' in i.filename.lower() or i.filename.lower().endswith('vbaproject.bin') for i in z.infolist()),
                      '请移除宏或外部链接后导入', 422)
        book = openpyxl.load_workbook(BytesIO(content), read_only=True, data_only=False)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, '无法读取工作簿，请使用标准 .xlsx 模板') from exc
    rows, sheets = [], []
    try:
        c.require(len(book.worksheets) <= 10, '单文件最多 10 个工作表', 422)
        for sheet in book:
            height, width = worksheet_bounds(book, sheet, 2000, 80, '工作表超过 2000 行或 80 列，请按模板整理', 422)
            mapping, header_row, best_fields = None, None, set()
            has_content, start = False, len(rows)
            for n, cells in enumerate(sheet.iter_rows(max_col=width, max_row=height), 1):
                has_content = has_content or any(cell.value is not None and str(cell.value).strip() for cell in cells)
                if mapping is None:
                    # Continue scanning the bounded sheet for nonempty cells;
                    # content below the header search range is not an empty sheet.
                    if n > 20: continue
                    fields = [FIELDS.get(re.sub(r'\s+', '', text(cell)).casefold()) for cell in cells]
                    found = set(fields) - {None}
                    if len(found) > len(best_fields): best_fields = found
                    if not REQUIRED <= set(fields): continue
                    c.require(all(fields.count(k) == 1 for k in REQUIRED), f'{sheet.title} 第 {n} 行关键表头重复', 422)
                    mapping = {i: k for i, k in enumerate(fields) if k}
                    header_row = n
                    continue
                if not any(cells[i].value is not None for i in mapping): continue
                c.require(len(rows) < 500, '单批最多 500 条，请拆分工作簿', 422)
                data = {k: text(cells[i]) for i, k in mapping.items()}
                errors = []
                if any(cells[i].data_type in {'f', 'e'} for i in mapping): errors.append('关键字段不能使用公式或错误值，请粘贴为值')
                if any(not data[k] for k in REQUIRED): errors.append('客户、订单号、货号、货名、数量、交期、单位均须填写')
                if any(len(v) > (120 if k == 'unit' else 255) for k, v in data.items()): errors.append('字段内容过长')
                try:
                    q = Decimal(data['quantity'])
                    if not q.is_finite() or q <= 0 or q >= Decimal('100000000000000') or q.as_tuple().exponent < -4: raise ValueError()
                    data['quantity'] = ledger.decimal_text(q)
                except (InvalidOperation, ValueError): errors.append('数量须为正数，最多四位小数，不含分隔符')
                try:
                    d = date.fromisoformat(data['requested_ship_date'])
                    if not date(2000, 1, 1) <= d <= date(2100, 12, 31): raise ValueError()
                    data['requested_ship_date'] = d.isoformat()
                except ValueError: errors.append('交期须为 Excel 日期或 YYYY-MM-DD')
                rows.append(dict(sheet=sheet.title, row=n, data=data, errors=errors))
            if mapping is not None:
                status, message = 'ready', '已识别七列表头'
            elif has_content:
                missing = '、'.join(label for key, label in COLUMN_LABELS.items() if key not in best_fields)
                status = 'blocked'
                message = f'未在前 20 行找到完整七列表头；缺少：{missing}。请按模板补齐，或移除本批不导入的工作表后重新预览。'
            else:
                status, message = 'empty', '空工作表，无数据'
            sheets.append(dict(sheet=sheet.title, status=status, header_row=header_row, row_count=len(rows)-start, message=message))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, '排期内容损坏或格式不支持，请按模板整理') from exc
    finally: book.close()
    c.require(rows or any(sheet['status'] == 'blocked' for sheet in sheets),
        '没有找到可读取的排期，请使用模板并保留全部七列表头', 422)
    return dict(rows=rows, sheets=sheets)


def customers(db):
    from app.api.customer_order import CUSTOMER_NAMES, CUSTOMER_FACTORY_OPTIONS
    names = {code: CUSTOMER_NAMES[code] for code, factories in CUSTOMER_FACTORY_OPTIONS.items() if c.FACTORY in factories}
    for code, name in db.execute(select(Line.customer_code, Line.customer_name).where(Line.factory_id == c.FACTORY).distinct()):
        names.setdefault(code, name or code)
    lookup = {}
    for code, name in names.items():
        for alias in (code, name): lookup.setdefault(alias.strip().casefold(), set()).add(code)
    return names, lookup


def preview(db, content, name, parsed=None):
    workbook = ledger.json_copy(parsed if parsed is not None else parse(content, name))
    rows, sheets = workbook['rows'], workbook['sheets']
    names, lookup = customers(db); seen = {}
    for row in rows:
        data = row['data']; candidates = lookup.get(data['customer_name'].casefold(), set())
        row.update(status='new', line_id=None)
        if len(candidates) != 1:
            row['errors'].append('客户未唯一匹配华康C客户，请使用本厂客户名称或编码')
            row['status']='invalid'
            continue
        code = next(iter(candidates)); data['customer_code'] = code; data['customer_name'] = names[code]
        if row['errors']:
            row['status'] = 'invalid'
            continue
        identity = ledger.identity_for(data, code); key = (code, identity)
        if key in seen:
            row['errors'].append(f'文件内重复订单：与 {seen[key]} 相同客户、订单号及货号')
        seen[key] = f"{row['sheet']} 第{row['row']}行"
        existing = ledger.resolve_existing_line(db, c.FACTORY, code, data, identity)
        if existing:
            row['line_id'] = existing.id
            same = existing.status == 'active' and all(str(existing.data.get(k, '')) == v for k, v in data.items() if k not in {'customer_name','customer_code','reference_no','product_no','quantity'})
            same = same and existing.quantity is not None and str(existing.reference_no) == data['reference_no'] and str(existing.product_no) == data['product_no'] and Decimal(data['quantity']) == existing.quantity
            if same and existing.data.get('source_kind') == SCHEMA: row['status'] = 'duplicate'
            else:
                row['status'] = 'conflict'
                row['errors'].append('已有订单或业务来源冲突，不会覆盖；请在原订单核对修订')
        if row['errors']: row['status'] = 'invalid' if row['status'] != 'conflict' else 'conflict'
    digest = sha256(content).hexdigest()
    # Pin parsed facts, parser contract and exact upload; database status is rechecked at confirmation.
    fingerprint = ledger.digest([SCHEMA, digest, filename(name)])
    return dict(file_name=filename(name), file_sha256=digest, fingerprint=fingerprint, rows=rows, sheets=sheets,
        can_confirm=bool(rows) and not any(sheet['status'] == 'blocked' for sheet in sheets) and not any(r['errors'] for r in rows),
        new_count=sum(r['status']=='new' for r in rows), duplicate_count=sum(r['status']=='duplicate' for r in rows))


def confirm(db, user, body, content, parsed):
    c.require(body.confirmed and len(body.reason) >= 4 and body.expected_version == 0, '请明确确认来源并填写至少四字核对说明', 422)
    fresh = preview(db, content, body.file_name, parsed)
    c.require(body.fingerprint == fresh['fingerprint'] and body.file_sha256 == fresh['file_sha256'], '文件或预览已变化，请重新预览', 409)
    c.require(not any(sheet['status'] == 'blocked' for sheet in fresh['sheets']),
        '存在未识别的非空工作表，请按工作表核对结果修正并重新预览；本批未写入', 409)
    c.require(fresh['can_confirm'], '存在错误或已有订单冲突，请重新预览核对；本批未写入', 409)
    result = dict(batch_id=body.operation_id, file_name=body.file_name, file_sha256=body.file_sha256, created=0, skipped=0, rows=[])
    for row in fresh['rows']:
        data = row['data']; code = data['customer_code']
        source = db.scalar(select(Source).where(Source.factory_id==c.FACTORY, Source.customer_code==code, Source.sha256==body.file_sha256, Source.kind==SCHEMA))
        if source is None:
            source = Source(id=ledger.uid(), factory_id=c.FACTORY, customer_code=code, sha256=body.file_sha256, file_name=body.file_name, kind=SCHEMA, content=content)
            db.add(source); db.flush()
        line = db.get(Line, row['line_id']) if row['line_id'] else None
        if line is None:
            evidence = dict(source_id=source.id, file_name=body.file_name, sha256=body.file_sha256, sheet=row['sheet'], row=row['row'], batch_id=body.operation_id, actor_id=user.id)
            line = Line(id=ledger.uid(), factory_id=c.FACTORY, customer_code=code, customer_name=data['customer_name'], identity_key=ledger.identity_for(data, code), reference_no=data['reference_no'], product_no=data['product_no'], quantity=Decimal(data['quantity']), shipped_quantity=0, status='active', version=1, revision=1,
                data={**data, 'source_kind':SCHEMA, 'source_import':evidence}, created_at=now_text(), updated_at=now_text())
            db.add(line); db.flush(); ledger.record_version(db,line,body.reason,ledger.actor_name(user))
            # Snapshot immutability triggers are present in existing databases.
            # Include the narrow source evidence in the initial INSERT, never
            # flush a generic dispatch and then UPDATE its frozen payload.
            snapshot={k:line.data.get(k,'') for k in ledger.PUBLIC_FIELDS}
            snapshot.update(factory_id=c.FACTORY,customer_code=code,customer_name=line.customer_name,reference_no=line.reference_no,
                product_no=line.product_no,quantity=ledger.decimal_text(line.quantity),status='active',version=1,change_reason=body.reason,
                shipped_quantity='0',remaining_quantity=ledger.decimal_text(line.quantity),history_cutoff_date='',
                intake_kind=SCHEMA,intake_file_name=body.file_name,intake_sheet=row['sheet'],intake_row=row['row'],
                intake_batch=body.operation_id,intake_sha256=body.file_sha256,order_unit=data['unit'])
            db.add(Dispatch(id=ledger.uid(),line_id=line.id,factory_id=c.FACTORY,recipient='cutting',version=1,
                snapshot=snapshot,actor=ledger.actor_name(user),created_at=now_text(),received_at='',received_by=''))
            result['created'] += 1
        else: result['skipped'] += 1
        if db.get(Link,(line.id,source.id)) is None: db.add(Link(line_id=line.id,source_id=source.id))
        result['rows'].append(dict(line_id=line.id, sheet=row['sheet'], row=row['row'], reference_no=line.reference_no, product_no=line.product_no, status=row['status'], version=line.version))
    db.flush()
    return result


def template():
    book=openpyxl.Workbook();sheet=book.active;sheet.title='裁床排期'
    sheet.append(['客户','订单号','货号','货名','数量','交期','单位'])
    sheet.freeze_panes='A2'
    for col in 'ABCDEFG': sheet.column_dimensions[col].width=22
    output=BytesIO();book.save(output);book.close();return output.getvalue()
