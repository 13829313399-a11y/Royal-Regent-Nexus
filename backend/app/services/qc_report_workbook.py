"""Render the authorized report projection through the same workbook writer used for export."""
import atexit
import base64
import json
import re
import select
import subprocess
import sys
from collections import OrderedDict
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock

from fastapi import HTTPException
from lxml import html
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
import xlrd

from app.services import qc_daily_report as daily, qc_weekly_templates as weekly, qc_monthly_templates as monthly
from app.services import qc_weekly_excel, qc_monthly_excel, qc_issue_reports
from app.services.qc_approved_statistics import factory_label
from app.services.document_tools.office_engine import office_executable

ANNUAL_KINDS = {'annual-stats', 'annual-issues'}
KINDS = {'daily', 'detail', 'issues', *monthly.design.NAMES, *ANNUAL_KINDS}
_cache = OrderedDict()
_render_lock = Lock()
MAX_CACHE_BYTES = 32 * 1024 * 1024


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


def resident_render(executable, source):
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
            if not select.select([_worker.stdout], [], [], 15)[0] or _worker.stdout.readline().strip() != 'ready':
                stop_worker()
                return False
        except OSError:
            stop_worker()
            return False
    try:
        _worker.stdin.write(json.dumps(str(source))+'\n')
        _worker.stdin.flush()
        if select.select([_worker.stdout], [], [], 45)[0] and _worker.stdout.readline().strip() == 'ok':
            return source.with_suffix('.html').is_file()
    except OSError:
        pass
    stop_worker()
    return False


def projection(factory, kind, day, customer, result='FAIL'):
    if kind in ANNUAL_KINDS:
        factory_label(factory)
        start, _ = qc_issue_reports.bounds(day, 'yearly')
        if kind == 'annual-issues':
            return qc_issue_reports.query(factory, start, 'yearly', customer)
        from app.services import qc_approved_statistics
        return qc_approved_statistics.report(factory, {'year': start[:4], 'customer': customer,
                                                       'result': result}, all_detail_rows=True)
    if kind == 'daily':
        return daily.report(factory, day, 'daily', customer)
    if kind == 'detail':
        return weekly.query(factory, day, customer)
    if kind == 'issues':
        return qc_issue_reports.query(factory, day, 'weekly', customer)
    return monthly.query(factory, day, customer, design_id=kind)


def writable_cells(kind, data):
    result = {}

    def bind(sheet, rows, first, positions=None, step=1, fields=None):
        for n, row in enumerate(rows):
            customer = row.get('customerKey', row['id'])
            for column, field in (fields or row.get('editableFields', {})).items():
                cell = data['fields'][customer][field]
                address = f'{sheet}:{get_column_letter(1 + (positions[column] if positions else column))}{first+n*step}'
                result[address] = dict(customerKey=customer, field=field, value=str(cell['value']),
                                       version=cell['version'], type='completion' if field.endswith(':completion') else 'text')

    if kind in ANNUAL_KINDS or kind in ('daily', 'issues'):
        return result
    rows = data['tables'][kind]
    if kind == 'detail':
        bind(0, rows, 3)
        bind(0, data['tables']['footer'], len(rows)+7, qc_weekly_excel.FOOTER_COLUMNS,
             fields={3:'returns', 5:'returnReason', 6:'hongKongContact', 7:'reworkA0D', 8:'weeklyRemark'})
    elif kind == 'quality':
        overview = data['overview']
        bind(1, rows, 7)
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


def render(factory, kind, data):
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
    if kind == 'detail':
        names = xlrd.open_workbook(file_contents=content).sheet_names()
    else:
        book = load_workbook(BytesIO(content), read_only=True)
        names = book.sheetnames
        book.close()
    executable = office_executable()
    if not executable:
        raise HTTPException(503, '工作簿预览引擎不可用')
    with TemporaryDirectory(prefix='qc-report-') as tmp:
        folder = Path(tmp).resolve()
        source = folder / ('report.xls' if kind == 'detail' else 'report.xlsx')
        source.write_bytes(content)
        profile = folder / 'profile'
        font = Path('/System/Library/Fonts/STHeiti Medium.ttc')
        if font.is_file():
            fonts = profile / 'user/fonts'
            fonts.mkdir(parents=True)
            (fonts / font.name).symlink_to(font)
        try:
            if not resident_render(executable, source):
                subprocess.run([executable,'-env:UserInstallation='+profile.as_uri(),'--headless','--convert-to','html',
                            '--outdir',str(folder),str(source)], check=True, timeout=60, capture_output=True)
            doc = html.fromstring((folder/'report.html').read_bytes(), parser=html.HTMLParser(encoding='utf-8'))
        except (OSError, subprocess.SubprocessError) as exc:
            raise HTTPException(503, '工作簿预览暂时无法生成，请重试') from exc
        tables = doc.xpath('/html/body/table')
        if len(tables) != len(names):
            raise HTTPException(503, '工作表未完整生成，请重试')
        return [dict(name=name, html=sheet_html(table, folder, i)) for i,(name,table) in enumerate(zip(names,tables))]


def preview(factory, kind, day, customer, can_edit, result='FAIL'):
    if kind not in KINDS:
        raise HTTPException(404, '模板不存在')
    data = projection(factory, kind, day, customer, result)
    cells = writable_cells(kind, data) if can_edit else {}
    revision = data.get('sourceRevision') or data.get('revision')
    versions = qc_weekly_excel.versions(data) if 'fields' in data else {}
    key = factory, kind, day, customer, result, revision, sha256(json.dumps(versions, sort_keys=True).encode()).digest()
    with _render_lock:
        if key not in _cache:
            if kind in ANNUAL_KINDS:
                rows = data['totals']['total'] if kind == 'annual-stats' else data['total']
            else:
                rows = data['rows'] if kind == 'daily' else data['tables'][kind]
            sheets = render(factory, kind, data) if rows else []
            size = sum(len(s['html'].encode()) for s in sheets)
            if size <= MAX_CACHE_BYTES:
                _cache[key] = (sheets, size)
                while len(_cache)>18 or sum(x[1] for x in _cache.values())>MAX_CACHE_BYTES:
                    _cache.popitem(last=False)
        else:
            sheets = _cache[key][0]
            _cache.move_to_end(key)
    return dict(sheets=sheets, cells=cells, sourceRevision=revision, versions=versions)
