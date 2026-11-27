"""Read the two workbench templates and append checked rows to the journal."""
from collections import defaultdict
from contextlib import closing
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
import json
import re
import sqlite3
from uuid import uuid4
from zipfile import ZipFile

from fastapi import HTTPException
from openpyxl import load_workbook
import xlrd

from app.services import qc_inspection_sheet as journal, qc_photo_assets, qc_workflow as wf
from app.services.qc_inspection_print import HEADERS as LEGACY_HEADERS, export_photo
from app.services.qc_inspection_schedule_excel import ORDER_FIELDS, photo_group_digest, photo_source_proofs

MAX_BYTES = 35 * 1024 * 1024
MAX_ROWS = 500
DESK_SHEET = '客户验货排期'
LEGACY_SHEET = '各客验货排期 (2)'
DESK_HEADERS = ('验货日期', *LEGACY_HEADERS[1:12], '验货结果', '抽查数量', '验货问题', '备注', '照片', '检验人员')
DESK_FIELDS = ('dateFrom', *ORDER_FIELDS, 'result', 'sampleQuantity', 'inspectionProblem', 'remark', 'photos', 'inspector')
LEGACY_FIELDS = ('dateFrom', *ORDER_FIELDS, 'completion', 'remark')
MANUAL_FIELDS = {'dateFrom', 'dateTo', *ORDER_FIELDS, 'remark'}
COMPARE_FIELDS = ('dateFrom', 'dateTo', *ORDER_FIELDS, 'result', 'sampleQuantity', 'inspectionProblem', 'remark', 'inspector')
NUMERIC_FIELDS = {'quantity', 'unitsPerCarton', 'cartonCount', 'sampleQuantity'}
CELL_ERROR = object()


def clean_fields(raw, manual=False):
    fields = {}
    for key, value in raw.items():
        if value is None:
            value = ''
        elif type(value) in (int, float):
            value = str(int(value)) if value == int(value) else str(value)
        limit = 20000 if key in {'remark', 'inspectionProblem'} else 255 if key == 'inspector' else 300
        fields[key] = wf.text(value, limit)
        if any(ord(c) < 32 and c not in '\n\r\t' for c in fields[key]):
            raise HTTPException(422, '文字包含无效字符')
    if not fields.get('customer') or not fields.get('productNo'):
        raise HTTPException(422, '请填写客户及货号')
    start = wf.day(fields.get('dateFrom'), True)
    end = wf.day(fields.get('dateTo') or start, True)
    if end < start:
        raise HTTPException(422, '结束日期不能早于开始日期')
    fields.update(dateFrom=start, dateTo=end)
    for key, label in (('quantity', '数量'), ('cartonCount', '箱数'), ('sampleQuantity', '抽查数量')):
        if key in fields:
            try:
                fields[key] = wf.number(fields[key], positive=manual and key == 'quantity',
                                        optional=not (manual and key == 'quantity')) or ''
            except HTTPException as error:
                raise HTTPException(422, f'{label}：{error.detail}') from error
    if manual and fields.get('agency') not in wf.METHODS.values():
        raise HTTPException(422, '机构请选择行验或客验')
    if fields.get('result', '') not in ('', *journal.RESULTS):
        raise HTTPException(422, '验货结果不在系统支持范围内')
    if fields.get('photos'):
        raise HTTPException(422, '请把图片嵌入照片列，或导入后在验货台上传')
    return fields


def dates(value, year=None, span=None):
    if isinstance(value, date):
        if isinstance(value, datetime):
            value = value.date()
        return value.isoformat(), value.isoformat()
    value = str(value or '').strip()
    full = r'(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})日?'
    match = re.fullmatch(fr'{full}(?:\s*(?:至|~|～|—|–|-)\s*{full})?', value)
    if match:
        a, b, c, x, y, z = match.groups()
        start = date(int(a), int(b), int(c)).isoformat()
        end = date(int(x), int(y), int(z)).isoformat() if x else start
        return start, end
    match = re.fullmatch(r'(\d{1,2})月(\d{1,2})日(?:\s*[-至~～—–]\s*(?:(\d{1,2})月)?(\d{1,2})日)?', value)
    if match:
        a, b, x, y = match.groups()
        month, day, last_month, last_day = int(a), int(b), int(x or a), int(y or b)
        candidates = []
        for origin in (range(span[0].year, span[1].year + 1) if span else [year] if year else []):
            try:
                start = date(origin, month, day)
                end = date(origin + (last_month < month), last_month, last_day)
            except ValueError:
                continue
            if not span or span[0] <= start <= end <= span[1]:
                candidates.append((start.isoformat(), end.isoformat()))
        if len(candidates) == 1:
            return candidates[0]
    raise ValueError('请填写完整的验货日期，或核对模板日期栏中的年份')


def cell_value(value, number_format):
    # Preserve zero-padded codes displayed by Excel.
    if type(value) in (int, float) and re.fullmatch(r'0+', number_format or '') and value >= 0 and int(value) == value:
        return str(int(value)).zfill(len(number_format))
    return value


def read_xls(content):
    book = xlrd.open_workbook(file_contents=content, on_demand=True, formatting_info=True)
    try:
        names = [name for name in book.sheet_names() if re.sub(r'\s+', '', name.translate(str.maketrans('（）', '()'))) == '各客验货排期(2)']
        if len(names) != 1:
            raise HTTPException(422, '旧模板须包含「各客验货排期 (2)」工作表')
        sheet = book.sheet_by_name(names[0])
        if sheet.nrows > 5000 or sheet.ncols < len(LEGACY_HEADERS):
            raise ValueError()
        rows = []
        for n in range(sheet.nrows):
            values = []
            for i, cell in enumerate(sheet.row(n)[:len(LEGACY_HEADERS)]):
                value = cell.value
                if cell.ctype == xlrd.XL_CELL_DATE:
                    value = xlrd.xldate_as_datetime(value, book.datemode)
                elif cell.ctype == xlrd.XL_CELL_ERROR:
                    value = CELL_ERROR
                elif i in (2, 4, 11) and cell.ctype == xlrd.XL_CELL_NUMBER:
                    fmt = book.format_map[book.xf_list[cell.xf_index].format_key].format_str
                    value = cell_value(value, fmt)
                values.append(value)
            rows.append(values)
        return rows, {}
    finally:
        book.release_resources()


def read_xlsx(content, factory):
    with ZipFile(BytesIO(content)) as archive:
        members = archive.infolist()
        if (len(members) > 2000 or sum(item.file_size for item in members) > 80 * 1024 * 1024
                or len(set(archive.namelist())) != len(members) or any(item.flag_bits & 1 for item in members)
                or any(name.startswith('xl/vbaProject') for name in archive.namelist())):
            raise ValueError()
    book = load_workbook(BytesIO(content), keep_links=False)
    try:
        if DESK_SHEET not in book:
            raise HTTPException(422, '请使用验货台导出的「客户验货排期」工作表')
        sheet = book[DESK_SHEET]
        if sheet.max_row > 5000 or sheet.max_column > 100:
            raise ValueError()
        rows = []
        for n, cells in enumerate(sheet.iter_rows(max_col=len(DESK_HEADERS)), 1):
            values = []
            for i, cell in enumerate(cells):
                value = cell.value
                if cell.data_type == 'f' and i == 8 and value == f'=G{n}/H{n}':
                    quantity, pack = cells[6].value, cells[7].value
                    if type(quantity) in (int, float) and type(pack) in (int, float) and pack > 0:
                        value = quantity / pack
                        if abs(round(value, 4) - value) < 1e-10:
                            value = round(value, 4)
                if cell.data_type == 'e' or (cell.data_type == 'f' and type(value) not in (int, float)):
                    raise HTTPException(422, f'第 {n} 行含公式或错误值，请填写实际数值')
                if i in (2, 4, 11):
                    value = cell_value(value, cell.number_format)
                values.append(value)
            rows.append(values)
        photos = defaultdict(list)
        for image in sheet._images:
            anchor = getattr(image.anchor, '_from', None)
            if anchor is None or anchor.col != 16 or anchor.row < 6:
                raise HTTPException(422, '请将验货照片放在对应记录的照片列内')
            n = anchor.row + 1
            if len(photos[n]) >= 50:
                raise HTTPException(422, f'第 {n} 行最多支持 50 张照片')
            raw = image._data()
            photos[n].append((raw, qc_photo_assets.inspect(raw)))
        return rows, photos, photo_source_proofs(book, factory)
    finally:
        book.close()


def parse(content, *, factory=None):
    if not content or len(content) > MAX_BYTES:
        raise HTTPException(422, '请选择 35 MB 以内的 Excel 文件')
    legacy = content.startswith(bytes.fromhex('d0cf11e0a1b11ae1'))
    try:
        if legacy:
            rows, photos = read_xls(content)
            proofs = {}
        else:
            rows, photos, proofs = read_xlsx(content, factory)
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(422, '无法读取工作簿，请使用完整的 XLS 或 XLSX 模板文件') from error
    headers, keys = (LEGACY_HEADERS, LEGACY_FIELDS) if legacy else (DESK_HEADERS, DESK_FIELDS)
    header = 2 if legacy else 5
    if len(rows) <= header or tuple(str(v or '').strip() for v in rows[header]) != headers:
        raise HTTPException(422, 'Excel 表头与验货台模板不一致，请保留原表头')
    year, span = None, None
    if not legacy:
        try:
            title = rows[2][0]
            if isinstance(title, str):
                first, _, last = title.partition(' 至 ')
                start = date.fromisoformat(dates(first)[0])
                end = date.fromisoformat(dates(last, start.year)[1]) if last else start
            else:
                start, end = (date.fromisoformat(v) for v in dates(title))
            if start.year != end.year and start <= end and end.year - start.year <= 10:
                span = (start, end)
            year = start.year
        except ValueError:
            pass
    elif isinstance(rows[1][0], date):
        year = rows[1][0].year
    result = []
    for n, values in enumerate(rows[header + 1:], header + 2):
        if not any(v is not None and str(v).strip() for v in values):
            continue
        if legacy:
            if tuple(str(v or '').strip() for v in values) == headers:
                continue
            present = {i for i, value in enumerate(values) if value is not None and str(value).strip()}
            if present == {0} and isinstance(values[0], date):
                year = values[0].year
                continue
            is_total = values[5] == '总数量' and present <= {5, 6}
            is_ratio = present == {5, 6, 8, 10} and all(type(values[i]) in (int, float) for i in present)
            if is_total or is_ratio:
                continue
        try:
            if CELL_ERROR in values:
                raise ValueError('含 Excel 错误值，请核对单元格')
            start, end = dates(values[0], year, span)
            fields = clean_fields({**dict(zip(keys, values)), 'dateFrom': start, 'dateTo': end})
        except (ValueError, HTTPException, OverflowError) as error:
            message = error.detail if isinstance(error, HTTPException) else str(error)
            raise HTTPException(422, f'第 {n} 行：{message}') from error
        row_photos = photos.pop(n, [])
        row = {'line': n, 'fields': fields, 'photos': row_photos}
        if proofs and row_photos:
            rendered = photo_group_digest(meta['sha256'] for _, meta in row_photos)
            if sources := proofs.get(rendered):
                row['verifiedPhotoSources'] = sources
        result.append(row)
    if photos:
        raise HTTPException(422, f'第 {min(photos)} 行的照片没有对应验货记录')
    if not 1 <= len(result) <= MAX_ROWS:
        raise HTTPException(422, f'每次请选择含 1 至 {MAX_ROWS} 条验货记录的模板')
    return LEGACY_SHEET if legacy else DESK_SHEET, result


def comparable_fields(fields, legacy):
    keys = (*COMPARE_FIELDS, 'completion') if legacy else COMPARE_FIELDS
    values = []
    for key in keys:
        value = fields.get(key)
        if key == 'dateTo' and not value:
            value = fields.get('dateFrom')
        text = journal.scalar(value).strip().replace('\r\n', '\n').replace('\r', '\n')
        # Quantities are numeric when possible; IDs and free-text packing stay literal.
        values.append(Decimal(text) if key in NUMERIC_FIELDS and re.fullmatch(r'[+-]?\d+(?:\.\d+)?', text) else text)
    return tuple(values)


def batch_record(conn, factory, batch):
    # A partially skipped file may have been saved starting after its first Excel row.
    prefix = 'desk:' + batch + ':'
    return conn.execute('SELECT base FROM entries WHERE factory=? AND source_key>=? AND source_key<? LIMIT 1',
                        (factory, prefix, prefix + '~')).fetchone()


def stored_candidates(conn, factory, wanted, legacy):
    columns = {row['name'] for row in conn.execute('PRAGMA table_info(entry_details)')}
    problem = 'd.inspection_problem' if 'inspection_problem' in columns else 'NULL'
    execution = 'd.review_execution' if 'review_execution' in columns else 'NULL'
    join = 'LEFT JOIN entry_details d ON d.entry_id=e.id' if columns else ''
    sql = f'''SELECT e.id,e.base,e.result,e.remark,{problem} AS problem,{execution} AS execution
             FROM entries e {join} WHERE e.factory=? AND e.source_key NOT LIKE 'source:%' '''
    result = defaultdict(list)
    for row in conn.execute(sql, (factory,)):
        base = json.loads(row['base'])
        if base.get('referenceData'):
            continue
        execution = {**(base.get('inspectionExecution') or {}), **json.loads(row['execution'] or '{}')}
        fields = {**base, 'result': row['result'], 'remark': row['remark']}
        if row['problem'] is not None:
            fields['inspectionProblem'] = row['problem']
        for key in ('sampleQuantity', 'inspector'):
            if execution.get(key) is not None:
                fields[key] = execution[key]
        signature = comparable_fields(fields, legacy)
        if signature in wanted:
            result[signature].append(row['id'])
    return result


def photos_match(conn, entry_id, expected, verified_sources=()):
    photos = list(conn.execute('SELECT id,digest FROM photos WHERE entry_id=? AND removed=0', (entry_id,)))
    if len(photos) != len(expected):
        return False
    digests = tuple(sorted(photo['digest'] for photo in photos))
    if digests == expected or (verified_sources and photo_group_digest(digests) in verified_sources):
        return True
    # A workbench re-export embeds rendered JPEGs, not the uploaded original.
    # Compare exact bytes of that known rendition too; never compare by count alone.
    try:
        plain, annotated = {}, {}
        photos_sql = qc_photo_assets.entry_photos_sql(conn)
        for photo in conn.execute(photos_sql, (entry_id,)):
            raw, _ = qc_photo_assets.read(conn, photo, 'preview')
            plain[photo['id']] = sha256(export_photo(raw)).hexdigest()
            marks = qc_photo_assets.decode_annotations(photo['annotations'])
            if marks:
                annotated[photo['id']] = marks
        if tuple(sorted(plain.values())) == expected:
            return True
        if annotated:
            for photo in conn.execute(photos_sql, (entry_id,)):
                if marks := annotated.get(photo['id']):
                    raw, _ = qc_photo_assets.read(conn, photo, 'preview')
                    plain[photo['id']] = sha256(export_photo(raw, marks)).hexdigest()
            return tuple(sorted(plain.values())) == expected
        return False
    except HTTPException as error:
        if error.status_code == 429:
            raise
        return False
    except (OSError, ValueError):
        return False


def duplicate_lines(conn, factory, rows, legacy):
    signatures = [(comparable_fields(row['fields'], legacy),
                   tuple(sorted(meta['sha256'] for _, meta in row['photos']))) for row in rows]
    candidates = stored_candidates(conn, factory, {fields for fields, _ in signatures}, legacy) if conn is not None else {}
    duplicates, seen = set(), set()
    for row, signature in zip(rows, signatures):
        fields, photos = signature
        verified_sources = row.get('verifiedPhotoSources', ())
        if signature in seen or any(photos_match(conn, entry_id, photos, verified_sources)
                                    for entry_id in candidates.get(fields, ())):
            duplicates.add(row['line'])
        seen.add(signature)
    return duplicates


def preview_duplicates(factory, batch, rows, legacy):
    path = journal.database_path()
    if not path.is_file():
        return duplicate_lines(None, factory, rows, legacy)
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=5)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute('BEGIN')
        # Keep preview read-only even when the journal has never been initialized.
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='entries'").fetchone():
            return duplicate_lines(None, factory, rows, legacy)
        if batch_record(conn, factory, batch):
            return {row['line'] for row in rows}
        return duplicate_lines(conn, factory, rows, legacy)


def workbook(factory, actor, content, confirmed_digest=None):
    digest = sha256(content).hexdigest()
    if confirmed_digest is not None and confirmed_digest != digest:
        raise HTTPException(409, '文件已变化，请重新核对预览')
    name, rows = parse(content, factory=factory)
    batch = 'excel:' + digest
    legacy = name == LEGACY_SHEET
    if confirmed_digest is None:
        duplicates = preview_duplicates(factory, batch, rows, legacy)
        return {'digest': digest, 'sheet': name, 'count': len(rows) - len(duplicates), 'existing': len(duplicates),
                'rows': [{'line': row['line'], **row['fields'], 'photos': len(row['photos']),
                          'duplicate': row['line'] in duplicates} for row in rows]}
    return append(factory, actor, batch, digest, rows, legacy=legacy)


def manual(factory, actor, body):
    if (set(body) != {'requestKey', 'row'} or not isinstance(body['row'], dict)
            or set(body['row']) != MANUAL_FIELDS or not isinstance(body['requestKey'], str)
            or not re.fullmatch(r'[\da-f-]{36}', body['requestKey'])):
        raise HTTPException(422, '手动录入字段不正确')
    fields = clean_fields(body['row'], manual=True)
    key = sha256((actor['id'] + ':' + body['requestKey']).encode()).hexdigest()
    digest = sha256(wf.dump(fields).encode()).hexdigest()
    return append(factory, actor, 'manual:' + key, digest, [{'line': 1, 'fields': fields, 'photos': []}])


def append(factory, actor, batch, digest, rows, *, legacy=False):
    prefix = 'desk:' + batch + ':'
    is_excel = batch.startswith('excel:')
    action = 'template-import' if is_excel else 'manual-create'
    with journal.store(True) as conn:
        prior = batch_record(conn, factory, batch)
        if prior:
            if json.loads(prior['base']).get('creationDigest') != digest:
                raise HTTPException(409, '本次录入已保存，请重新打开新增窗口')
            return {'count': 0, 'existing': len(rows)}
        # Validate against current rows inside the same write lock as the append.
        duplicates = duplicate_lines(conn, factory, rows, legacy) if is_excel else set()
        for row in rows:
            if row['line'] in duplicates:
                continue
            fields = row['fields']
            key = prefix + str(row['line'])
            identity = sha256((factory + '\0' + key).encode()).hexdigest()[:32]
            base = journal.base_fields(fields)
            base.update(creationDigest=digest, sourceResult=fields.get('result', ''), resultOverride=False)
            stamp = wf.now()
            conn.execute('INSERT INTO entries VALUES(?,?,?,?,?,?,0,0,?)',
                         (identity, factory, key, wf.dump(base), fields.get('result', ''), fields['remark'], stamp))
            execution = journal.clean_review_execution({k: fields[k] for k in ('sampleQuantity', 'inspector') if k in fields})
            conn.execute('INSERT INTO entry_details(entry_id,flow_version,review_execution) VALUES(?,2,?)',
                         (identity, wf.dump(execution)))
            for n, (raw, meta) in enumerate(row['photos'], 1):
                photo_id = uuid4().hex
                name = f'Excel 照片 {n}.{meta["format"].lower()}'
                conn.execute('INSERT INTO photos VALUES(?,?,?,?,?,?,0,?)',
                             (photo_id, identity, name, b'', meta['sha256'], f'excel:{n}', stamp))
                qc_photo_assets.save(conn, photo_id, raw, 'preview-only', details=meta)
            entry = journal.get(conn, factory, identity)
            journal.changed(conn, entry, action, actor)
    return {'count': len(rows) - len(duplicates), 'existing': len(duplicates)}
