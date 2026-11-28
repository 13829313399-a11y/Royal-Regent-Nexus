"""Render the authorized report projection through the same workbook writer used for export."""
import atexit
import base64
import gzip
import json
import logging
import re
import select
import subprocess
import sys
from collections import OrderedDict
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock, Thread
from time import monotonic
from urllib.parse import urlencode

from fastapi import HTTPException
from starlette.responses import JSONResponse, Response
from lxml import etree, html
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
import xlrd

from app.services import qc_daily_report as daily, qc_weekly_templates as weekly, qc_monthly_templates as monthly
from app.services import qc_weekly_excel, qc_monthly_excel, qc_issue_reports
from app.services.qc_inspection_summary import dump
from app.services.qc_approved_statistics import factory_label
from app.services.document_tools.office_engine import office_executable

ANNUAL_KINDS = {'annual-stats', 'annual-issues'}
KINDS = {'daily', 'detail', 'issues', *monthly.design.NAMES, *ANNUAL_KINDS}
RECORD_KINDS = {'daily', 'issues', *ANNUAL_KINDS}
_cache = OrderedDict()
_render_lock = Lock()
_cache_lock = Lock()
_warm_attempted = False
MAX_CACHE_BYTES = 32 * 1024 * 1024
log = logging.getLogger(__name__)
_try_native_at = 0


# The caller serializes access to Calc. Platforms without the native library
# use the regular command-line converter with an isolated temporary profile.
_worker = None


def stop_worker():
    global _worker
    if _worker is not None:
        process, _worker = _worker, None
        try:
            process.stdin.close()
        except BrokenPipeError:
            pass
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        process.stdout.close()


atexit.register(stop_worker)


def start_worker(executable):
    global _worker
    if sys.platform not in {'darwin','linux'}:
        return False
    program = Path(executable).resolve().parent
    if _worker is None:
        if sys.platform == 'darwin':
            programs = [program, program.parent.parent/'native/libreoffice-headless/libreoffice/LibreOfficeDev.app/Contents/MacOS']
            library = next((p.parent/'Frameworks/libsofficeapp.dylib' for p in programs
                            if (p.parent/'Frameworks/libsofficeapp.dylib').is_file()), None)
            if library:
                program = library.parent.parent/'MacOS'
        else:
            library = program/'libmergedlo.so'
        if not library or not library.is_file():
            return False
        try:
            _worker = subprocess.Popen([sys.executable, '-B', str(Path(__file__).with_name('qc_report_calc_worker.py')),
                                        str(library), str(program)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
            if not select.select([_worker.stdout], [], [], 4)[0] or _worker.stdout.readline().strip() != 'ready':
                stop_worker()
                return False
        except OSError:
            stop_worker()
            return False
    return True


def warm_on_report_visit():
    """Start Calc once while the report summary loads; never wait on the HTTP thread."""
    global _warm_attempted
    if _warm_attempted or not _render_lock.acquire(blocking=False):
        return
    if _warm_attempted:
        _render_lock.release()
        return
    _warm_attempted = True

    def warm():
        try:
            executable = office_executable()
            if executable:
                start_worker(executable)
        finally:
            _render_lock.release()

    try:
        Thread(target=warm, name='qc-preview-warm', daemon=True).start()
    except RuntimeError:
        _render_lock.release()


def resident_render(executable, source):
    if not start_worker(executable):
        return False
    try:
        _worker.stdin.write(json.dumps(str(source))+'\n')
        _worker.stdin.flush()
        if select.select([_worker.stdout], [], [], 8)[0] and _worker.stdout.readline().strip() == 'ok':
            return source.with_suffix('.html').is_file()
    except OSError:
        pass
    stop_worker()
    return False


def projection(factory, kind, day, customer, result='FAIL', *, write_entry=None, end_date=None):
    if kind in ANNUAL_KINDS:
        factory_label(factory)
        start, _ = qc_issue_reports.bounds(day, 'yearly')
        if kind == 'annual-issues':
            return qc_issue_reports.query(factory, start, 'yearly', customer, workbook_preview=True, write_entry=write_entry)
        from app.services import qc_approved_statistics
        return qc_approved_statistics.report(factory, {'year': start[:4], 'customer': customer,
                                                       'result': result}, all_detail_rows=True, workbook_preview=True)
    if kind == 'daily':
        return daily.report(factory, day, 'daily', customer, workbook_preview=True)
    if kind == 'detail':
        return weekly.query(factory, day, customer)
    if kind == 'issues':
        return qc_issue_reports.query(factory, day, 'weekly', customer, workbook_preview=True, write_entry=write_entry, end_date=end_date)
    return monthly.query(factory, day, customer, design_id=kind)


def writable_cells(kind, data):
    result = {}

    def bind(sheet, rows, first, positions=None, step=1, fields=None, computed=None):
        for n, row in enumerate(rows):
            customer = row.get('customerKey', row['id'])
            for column, field in (fields or row.get('editableFields', {})).items():
                if computed and computed(row, column):
                    continue
                cell = data['fields'][customer][field]
                address = f'{sheet}:{get_column_letter(1 + (positions[column] if positions else column))}{first+n*step}'
                result[address] = dict(customerKey=customer, field=field, value=str(cell['value']),
                                        version=cell['version'], type=editor_type(field))

    if kind in RECORD_KINDS:
        if kind == 'daily':
            rows, first = data['rows'], 4
        elif kind == 'annual-stats':
            rows, first = data['details']['items'], 20
        else:
            rows, first = data['tables']['issues'], 7
        for number, row in enumerate(rows, first):
            for col, cell in row['supplementCells'].items():
                result[f'0:{get_column_letter(col+1)}{number}'] = {**cell, 'type': editor_type(cell['field'])}
        return result
    rows = data['tables'][kind]
    if kind == 'detail':
        bind(0, rows, 3)
        bind(0, data['tables']['footer'], len(rows)+7, qc_weekly_excel.FOOTER_COLUMNS,
             fields={3:'returns', 5:'returnReason', 6:'hongKongContact', 7:'reworkA0D', 8:'weeklyRemark'})
    elif kind == 'quality':
        from app.services.qc_report_empty_cols import formula_boxes

        def computed_boxes(row, column):
            return column == 8 and formula_boxes(row['values'])

        overview = data['overview']
        bind(1, rows, 7, computed=computed_boxes)
        bind(0, overview['rows'], 7)
        top = len(overview['rows']) + 10
        bind(0, overview['distribution'], top+1, [6,7,8])
        first = top + max(12, len(overview['distribution'])) + 4
        bind(0, overview['issues'], first, [0,2,4,8,6,7])
        bind(0, [overview['signatures']], first+len(overview['issues'])+2, [1,4,7])
    else:
        bind(0, rows, 7)
        if kind == 'orders':
            caixing = data['tables']['caixing']
            bind(1, caixing, 7)
            bind(1, data['tables']['summary'], len(caixing)+10, step=4)
    return result


def editor_type(field):
    if field.endswith((':completion', ':correctiveCompletion')):
        return 'completion'
    if field.endswith((':traderQDate', ':thirdPartyQDate', ':reportDate')):
        return 'date'
    if field == 'returns' or field.endswith(':count'):
        return 'integer'
    return 'number' if field.endswith(':quantity') else 'text'


def save_record(factory, actor, kind, day, customer, result, body, *, end_date=None):
    """Authorize the current logical cell, never arbitrary spreadsheet coordinates."""
    expected = {'customerKey', 'field', 'value', 'baseVersion', 'writeRevision', 'requestKey'}
    if kind not in RECORD_KINDS or not isinstance(body, dict) or set(body) != expected:
        raise HTTPException(422, '工作簿保存参数不正确')
    patterns = {'customerKey':'[a-f0-9]{64}', 'writeRevision':'[a-f0-9]{64}', 'requestKey':'[A-Za-z0-9-]{16,80}'}
    if (any(not isinstance(body[k], str) or not re.fullmatch(pattern, body[k]) for k,pattern in patterns.items())
            or type(body['baseVersion']) is not int or body['baseVersion'] < 0
            or not isinstance(body['value'], str) or len(body['value']) > 4000
            or re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]', body['value'])):
        raise HTTPException(422, '补录字段、版本或内容不正确')
    field = monthly.DETAIL_FIELD.fullmatch(body['field']) if isinstance(body['field'], str) else None
    if not field:
        raise HTTPException(422, '模板和计算单元格不可补录')
    value = body['value']
    if value:
        if field[2] in ('traderQDate', 'thirdPartyQDate') and not daily.approved._date(value):
            raise HTTPException(422, 'Q 货期请填写 YYYY-MM-DD')
        if field[2] == 'quantity' and not re.fullmatch(r'[0-9]{1,15}(?:\.[0-9]{1,4})?', value):
            raise HTTPException(422, '数量须为空白或非负数字，最多四位小数')
        if field[2] == 'correctiveCompletion' and value not in ('整改中', '待复核', '已复核'):
            raise HTTPException(422, '请选择有效的整改完成情况')
    scope = [kind, day, customer, result, body]
    if end_date is not None:
        scope.append(end_date)
    fingerprint = sha256(dump(scope).encode()).hexdigest()
    actor_id = str(actor['id'])
    data = projection(factory, kind, day, customer, result, write_entry=field[1], end_date=end_date)
    if kind == 'annual-stats' and (data['filters']['year'] != day[:4] or data['filters']['customer'] != customer
                                   or data['excluded'].get('missingProjection') or data['excluded'].get('invalidLineage')):
        raise HTTPException(409, '年报来源或筛选范围已变化，请刷新后补录')
    allowed = next((cell for cell in writable_cells(kind, data).values()
                    if cell['customerKey'] == body['customerKey'] and cell['field'] == body['field']), None)
    with monthly._store() as conn:
        receipt = monthly.write_receipt(conn, factory, actor_id, body, fingerprint)
        if receipt is not None:
            return receipt
        if not allowed or allowed['writeRevision'] != body['writeRevision']:
            raise HTTPException(409, '此格已锁定或审核来源已变化，请刷新后核对；未覆盖原值')
        return monthly.write_cell(conn, factory, allowed['month'], actor_id, body, fingerprint)


def sheet_html(table, folder, sheet):
    # Calc produces a small presentation-only HTML vocabulary. Preserve formatting
    # and locally rendered raster pictures, never workbook links or active content.
    tags = {'table','thead','tbody','tr','td','th','colgroup','col','font','span','p','b','i','u','s','br','img','strong','em','sup','sub'}
    attrs = {'align','valign','rowspan','colspan','span','width','height','bgcolor','color','face','size','border','cellpadding','cellspacing','hspace','vspace','alt'}
    for node in [table, *table.iterdescendants()]:
        if not isinstance(node.tag, str) or node.tag not in tags:
            if hasattr(node, 'drop_tag'):
                node.drop_tag()
            continue
        src = node.get('src', '')
        style = node.get('style', '')
        for key in set(node.attrib) - attrs:
            del node.attrib[key]
        rules = []
        for rule in style.split(';'):
            prop, _, value = rule.partition(':')
            if re.fullmatch(r'(background-color|color|border(?:-(?:top|right|bottom|left|color|style|width))?|font(?:-(?:family|weight|size|style))?|text-align|vertical-align|white-space|padding(?:-left)?|width|height)', prop.strip(), re.I) and re.fullmatch(r'''[\w\s.,#%"'-]+''', value):
                rules.append(rule)
        if rules:
            node.set('style', ';'.join(rules))
        if node.tag == 'img':
            img = (folder / src).resolve()
            mime = {'.png':'png','.jpg':'jpeg','.jpeg':'jpeg','.gif':'gif'}.get(img.suffix.lower())
            if img.parent != folder or not mime or not img.is_file():
                node.drop_tree()
            else:
                node.set('src', f'data:image/{mime};base64,' + base64.b64encode(img.read_bytes()).decode())
    occupied = {}
    width = 0
    for r, tr in enumerate(table.xpath('./tr|./tbody/tr'), 1):
        c = 1
        for td in tr.xpath('./td|./th'):
            while occupied.get(c, 0) >= r:
                c += 1
            count = int(td.get('colspan', 1))
            for index in range(c, c+count):
                occupied[index] = r + int(td.get('rowspan', 1)) - 1
            td.set('data-addr', get_column_letter(c) + str(r))
            c += count
        width = max(width, c-1)
        number = html.Element('th', {'class':'row-num'})
        number.text = str(r)
        tr.insert(0, number)
    table.insert(0, html.Element('colgroup', width='38'))
    heading = html.Element('thead')
    line = html.Element('tr')
    for col in range(width+1):
        cell = html.Element('th', {'class':'col-num'})
        cell.text = get_column_letter(col) if col else ''
        line.append(cell)
    heading.append(line)
    table.insert(len(table.xpath('./colgroup')), heading)
    return html.tostring(table, encoding='unicode')


def attach_preview_photos(sheet, rows):
    table = html.fromstring(sheet['html'])
    cells = {td.get('data-addr'): td for td in table.xpath('.//td[@data-addr]')}
    for r, row in enumerate(rows, 7):
        photos = row['photos']
        if not photos:
            continue
        cell = cells.get(f'M{r}')
        if cell is None:
            raise ValueError('Workbook omitted a report photo cell')
        columns, width, height = qc_monthly_excel._photo_slots(len(photos), monthly.design.TRACKING_WIDTHS[12],
                                                              min(530, len(photos)*84))
        gallery = etree.SubElement(cell, 'span', style=f'display:grid;grid-template-columns:repeat({columns},minmax(0,1fr));justify-items:center')
        for photo in photos:
            query = urlencode({'entry': row['id'], 'revision': row['revision'], 'photo': photo['id']})
            etree.SubElement(gallery, 'img', src='api/report-workbook/photo?' + query, loading='lazy',
                             decoding='async', width=str(max(1,int(width))), height=str(max(1,int(height))),
                             style='object-fit:contain;max-width:100%', alt='现场照片')
    sheet['html'] = html.tostring(table, encoding='unicode')


def render(factory, kind, data):
    from app.services.qc_report_grid import render_grid
    global _try_native_at
    photo_kind = kind in {'tracking', 'issues', 'annual-issues'}
    if photo_kind:
        data = dict(data, deferPreviewPhotos=True)
    if kind == 'annual-stats':
        from app.services.qc_annual_excel import workbook
        content = workbook(data)
    elif kind == 'annual-issues':
        content = qc_monthly_excel.render(dict(data, photoQuality='preview'), 'issues', factory)
    elif kind == 'daily':
        content = daily.workbook(data)
    elif kind == 'detail':
        content = qc_weekly_excel.render(data, kind)
    else:
        content = qc_monthly_excel.render(data, kind, factory)
    executable = office_executable() if monotonic() >= _try_native_at else None
    sheets = None
    if executable:
        try:
            sheets = render_native(executable, content, kind == 'detail')
            rendered = {f'{i}:{addr}' for i,s in enumerate(sheets)
                        for addr in re.findall(r'<td\b[^>]*\bdata-addr="([A-Z]+\d+)"',s['html'])}
            if not set(writable_cells(kind,data)) <= rendered:
                raise ValueError('Calc omitted editable cells')
            if photo_kind and any(row['photos'] and f'0:M{r}' not in rendered for r, row in
                                  enumerate(data['tables']['tracking' if kind == 'tracking' else 'issues'], 7)):
                raise ValueError('Calc omitted a report photo cell')
        except (OSError, ValueError, subprocess.SubprocessError, etree.LxmlError) as exc:
            _try_native_at = monotonic() + 30
            log.warning('QC native workbook preview temporarily unavailable (%s); using the grid', type(exc).__name__)
            sheets = None
    mode = 'calc' if sheets is not None else 'grid'
    if sheets is None:
        sheets = render_grid(content, kind == 'detail')
    if photo_kind:
        attach_preview_photos(sheets[0], data['tables']['tracking' if kind == 'tracking' else 'issues'])
    return sheets, mode


def render_native(executable, content, legacy):
    if legacy:
        names = xlrd.open_workbook(file_contents=content).sheet_names()
    else:
        book = load_workbook(BytesIO(content), read_only=True)
        names = book.sheetnames
        book.close()
    with TemporaryDirectory(prefix='qc-report-') as tmp:
        folder = Path(tmp).resolve()
        source = folder / ('report.xls' if legacy else 'report.xlsx')
        source.write_bytes(content)
        profile = folder / 'profile'
        font = Path('/System/Library/Fonts/STHeiti Medium.ttc')
        if font.is_file():
            fonts = profile / 'user/fonts'
            fonts.mkdir(parents=True)
            (fonts / font.name).symlink_to(font)
        if not resident_render(executable, source):
            subprocess.run([executable,'-env:UserInstallation='+profile.as_uri(),'--headless','--convert-to','html',
                        '--outdir',str(folder),str(source)], check=True, timeout=8, capture_output=True)
        doc = html.fromstring((folder/'report.html').read_bytes(), parser=html.HTMLParser(encoding='utf-8'))
        tables = doc.xpath('/html/body/table')
        if len(tables) != len(names):
            raise ValueError('Calc omitted worksheets')
        return [dict(name=name, html=sheet_html(table, folder, i)) for i,(name,table) in enumerate(zip(names,tables))]


def cached_preview(key):
    with _cache_lock:
        entry = _cache.get(key)
        if entry and (entry[2] != 'grid' or entry[3] > monotonic()):
            _cache.move_to_end(key)
            return entry[0], entry[2]
    return None


def preview(factory, kind, day, customer, can_edit, result='FAIL', *, end_date=None):
    if kind not in KINDS:
        raise HTTPException(404, '模板不存在')
    data = projection(factory, kind, day, customer, result, end_date=end_date)
    writable = writable_cells(kind, data)
    if kind == 'annual-stats' and (data['filters']['year'] != day[:4] or data['filters']['customer'] != customer
                                   or data['excluded'].get('missingProjection') or data['excluded'].get('invalidLineage')):
        can_edit = False
    cells = writable if can_edit else {}
    revision = data.get('sourceRevision') or data.get('revision')
    versions = qc_weekly_excel.versions(data) if 'fields' in data else {}
    stamps = {k:cell['version'] for k,cell in writable.items()} if kind in RECORD_KINDS else versions
    key = factory, kind, day, customer, result, revision, sha256(json.dumps(stamps, sort_keys=True).encode()).digest()
    cached = cached_preview(key)
    if cached is None:
        with _render_lock:
            cached = cached_preview(key)
            if cached is None:
                if kind in ANNUAL_KINDS:
                    rows = data['totals']['total'] if kind == 'annual-stats' else data['total']
                else:
                    rows = data['rows'] if kind == 'daily' else data['tables'][kind]
                cached = render(factory, kind, data) if rows else ([], 'calc')
                sheets, mode = cached
                size = sum(len(s['html'].encode()) for s in sheets)
                if size <= MAX_CACHE_BYTES:
                    with _cache_lock:
                        _cache[key] = (sheets, size, mode, monotonic()+15)
                        _cache.move_to_end(key)
                        while len(_cache)>18 or sum(x[1] for x in _cache.values())>MAX_CACHE_BYTES:
                            _cache.popitem(last=False)
    sheets, mode = cached
    return dict(sheets=sheets, cells=cells, sourceRevision=revision, versions=versions,
                previewMode=mode, workbookSourceRevision=data.get('workbookSourceRevision'))


def preview_response(payload, accept_encoding, headers):
    headers = {**headers, 'Vary': 'Accept-Encoding'}
    response = JSONResponse(payload, headers=headers)
    if len(response.body) >= 2048:
        for item in accept_encoding.lower().split(','):
            match = re.fullmatch(r'\s*gzip\s*(?:;\s*q\s*=\s*(0(?:\.\d{0,3})?|1(?:\.0{0,3})?))?\s*', item)
            if match and float(match[1] or '1') > 0:
                return Response(gzip.compress(response.body, compresslevel=1), media_type='application/json',
                                headers={**headers, 'Content-Encoding': 'gzip'})
    return response
