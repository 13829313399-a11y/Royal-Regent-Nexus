"""Original XLS template styles, current weekly data and scoped Excel downloads."""
from copy import deepcopy
from datetime import date
from hashlib import sha256
import hmac
from io import BytesIO
import json
import math
import os
from pathlib import Path
import re
import secrets
import struct
import time
import unicodedata

from fastapi import HTTPException
import xlrd
import xlwt
from xlwt.Cell import FormulaCell
from xlwt.UnicodeUtils import upack2
from xlutils.filter import XLWTWriter
from app.core.config import settings
from app.services import qc_weekly_templates as weekly

MIME = 'application/vnd.ms-excel'
TTL, MAX_BYTES = 600, 32 * 1024 * 1024
TEMPLATE_DIR = Path(__file__).resolve().parents[1] / 'templates/qc-weekly'
ASSETS = json.loads((TEMPLATE_DIR/'export-templates.json').read_text())
FOOTER_COLUMNS = [0, 1, 3, 5, 7, 10, 14, 15, 16]
FOOTER_SPANS = [(0,0),(1,2),(3,4),(5,6),(7,9),(10,13),(14,14),(15,15),(16,17)]


def versions(data):
    return {key: {field: cell['version'] for field, cell in cells.items()}
            for key, cells in data['fields'].items()}


class CachedFormulaCell(FormulaCell):
    """BIFF8 cached result: previews match the snapshot; Excel still recalculates edits."""
    def __init__(self, row, col, style, formula, value):
        super().__init__(row, col, style, formula, calc_flags=3)
        self.value = value

    def get_biff_data(self):
        record = super().get_biff_data()
        if isinstance(self.value, (int, float)):
            return record[:10] + struct.pack('<d', self.value) + record[18:]
        if self.value == '':
            return record
        payload = upack2(str(self.value))
        return (record[:10] + b'\x00\x00\x00\x00\x00\x00\xff\xff' + record[18:]
                + struct.pack('<HH', 0x0207, len(payload)) + payload)


def render(data, kind):
    if kind not in ASSETS:
        raise HTTPException(422, '请选择有效的周报模板')
    if not data['total']:
        raise HTTPException(409, '当前筛选没有验货记录，无法导出空白 Excel')
    asset = ASSETS[kind]
    try:
        raw = (TEMPLATE_DIR/asset['file']).read_bytes()
    except OSError as exc:
        raise HTTPException(503, '原始周报导出模板不可用') from exc
    if sha256(raw).hexdigest() != asset['sha256']:
        raise HTTPException(503, '原始周报模板校验失败，请核对模板文件')
    spec = next(t for t in weekly.TEMPLATES if t['id'] == kind)
    source = xlrd.open_workbook(file_contents=raw, formatting_info=True)
    sheet = source.sheet_by_index(0)
    if sheet.row_values(1) != spec['headers']:
        raise HTTPException(503, '原始周报模板字段不匹配')
    if kind == 'detail' and [sheet.cell_value(131,c) for c in FOOTER_COLUMNS] != spec['summaryHeaders']:
        raise HTTPException(503, '原始客户汇总模板字段不匹配')
    rows = data['tables'][kind]
    if len(rows) + (len(data['tables']['footer']) if kind == 'detail' else 0) + 8 > 65536:
        raise HTTPException(422, '当前记录超过原始 XLS 行数上限，请缩小日期或客户范围')
    writer = XLWTWriter(); writer.workbook(source, 'weekly.xls')
    writer.sheet(sheet, data['dateFrom'][5:].replace('-','.')+'-'+data['dateTo'][5:].replace('-','.'))
    book, target = writer.wtbook, writer.wtsheet
    target.first_visible_row = target.first_visible_col = 0
    target.panes_frozen = True; target.horz_split_pos = 2; target.horz_split_first_visible = 2
    target.vert_split_pos = 0; target.split_position_units_are_twips = False
    for index, rgb in source.colour_map.items():
        if 8 <= index <= 63 and rgb: book.set_colour_RGB(index, *rgb)
    for col in range(sheet.ncols):
        target.col(col).width = sheet.colinfo_map[col].width
    def style(row, col, fmt=None):
        item = deepcopy(writer.style_list[sheet.cell_xf_index(row,col)])
        item.alignment.wrap = 1
        if row in (3, 133):
            for edge in ('top', 'bottom', 'left', 'right'):
                if not getattr(item.borders, edge):
                    setattr(item.borders, edge, xlwt.Borders.THIN)
        if fmt: item.num_format_str = fmt
        return item
    def formula(row, col, expression, value, cell_style):
        parsed = xlwt.Formula(expression)
        target.write(row,col,parsed,cell_style)
        target.row(row).insert_cell(col,CachedFormulaCell(row,col,book.add_style(cell_style),parsed,value))
    def height(row, source_row, values, columns, spans=None):
        writer.row(source_row,row)
        estimate = target.row(row).height
        for i,(col,value) in enumerate(zip(columns,values)):
            if value in ('',None): continue
            start,end = spans[i] if spans else (col,col)
            width = max(2,sum(target.col(c).width/256 for c in range(start,end+1))-1)
            lines = sum(max(1,math.ceil(sum(2 if unicodedata.east_asian_width(ch) in 'WF' else 1 for ch in line)/width)) for line in str(value).split('\n'))
            font_size = style(source_row,col).font.height
            estimate = max(estimate,round(lines*font_size*1.2+80))
        target.row(row).height = min(8190,estimate); target.row(row).height_mismatch = True
    def block_row(row, source_row, values, columns, spans=None):
        height(row,source_row,values,columns,spans)
        for i,(col,value) in enumerate(zip(columns,values)):
            if isinstance(value,str) and len(value.encode('utf-16-le'))//2 > 32767:
                raise HTTPException(422, '单元格内容超过原始 Excel 长度上限，请核对内容')
            cell_style = style(source_row,col)
            if spans and spans[i][1]>col:
                target.write_merge(row,row,col,spans[i][1],value,cell_style)
            else: target.write(row,col,value,cell_style)
    def title(row, source_row, text, span_rows=1):
        for r in range(span_rows):writer.row(source_row+r,row+r)
        target.write_merge(row,row+span_rows-1,0,sheet.ncols-1,text,style(source_row,0))
    period = data['dateFrom']+' 至 '+data['dateTo']
    selected = next((c['label'] for c in data['customers'] if c['key']==data['customer']), '')
    title(0,0,spec['title']+'（'+period+'）'+(' '+selected if selected else ''))
    block_row(1,1,spec['headers'],list(range(sheet.ncols)))
    def summary(start, entries, headers, columns, spans, source_row, total_source, internal=False):
        ci,ri,pi = (1,2,3) if internal else (2,3,4)
        for index,entry in enumerate(entries):
            row = start+index; values=list(entry['values'])
            values[ri] = int(values[ri]) if values[ri] != '' else ''
            block_row(row,source_row,values,columns,spans)
            count_ref=xlwt.Utils.rowcol_to_cell(row,columns[ci]);return_ref=xlwt.Utils.rowcol_to_cell(row,columns[ri])
            value = (1-values[ri]/values[ci] if internal else values[ri]/values[ci]) if values[ri]!='' and values[ci] else ''
            formula(row,columns[pi],f'IF(OR({count_ref}=0,{return_ref}=""),"",'+('1-' if internal else '')+f'{return_ref}/{count_ref})',value,style(source_row,columns[pi],'0.0%'))
        total_row=start+len(entries)
        total=weekly._totals(headers,entries)
        block_row(total_row,total_source,total,columns,spans)
        for index in [ci,ri]:
            col=columns[index];a=xlwt.Utils.rowcol_to_cell(start,col);b=xlwt.Utils.rowcol_to_cell(total_row-1,col)
            expr=f'SUM({a}:{b})' if index==ci else f'IF(COUNT({a}:{b})<{len(entries)},"待补全",SUM({a}:{b}))'
            formula(total_row,col,expr,total[index],style(total_source,col))
        a=xlwt.Utils.rowcol_to_cell(total_row,columns[ci]);b=xlwt.Utils.rowcol_to_cell(total_row,columns[ri])
        value=(1-total[ri]/total[ci] if internal else total[ri]/total[ci]) if isinstance(total[ri],int) and total[ci] else ''
        formula(total_row,columns[pi],f'IF(OR({a}=0,NOT(ISNUMBER({b}))),"",'+('1-' if internal else '')+f'{b}/{a})',value,style(total_source,columns[pi],'0.0%'))
    if kind == 'detail':
        for index,entry in enumerate(rows,2):
            values=list(entry['values']);values[1]=date.fromisoformat(values[1])
            block_row(index,3,values,list(range(18)))
            target.write(index,1,values[1],style(3,1,'m.d'))
        footer_title=len(rows)+2
        title(footer_title,128,'华兴客户周验货汇总（'+period+'）',3)
        block_row(footer_title+3,131,spec['summaryHeaders'],FOOTER_COLUMNS,FOOTER_SPANS)
        summary(footer_title+4,data['tables']['footer'],spec['summaryHeaders'],FOOTER_COLUMNS,FOOTER_SPANS,133,142)
    else:
        summary(2,rows,spec['headers'],list(range(8)),None,3,15,kind=='internal')
    stream=BytesIO();book.save(stream);content=stream.getvalue()
    if len(content)>MAX_BYTES:raise HTTPException(422,'Excel 文件过大，请缩小筛选范围')
    return content


def _folder():
    return Path(settings.qc_department_data_dir).resolve() / '_weekly_excel_exports'


def _signature(owner, value):
    key = settings.qc_department_gateway_token.get_secret_value()
    if not key:
        raise HTTPException(503, '下载服务尚未配置')
    return hmac.new(key.encode(), ('qc-weekly-excel:'+owner+':'+value).encode(), sha256).hexdigest()


def _clean():
    files = []
    for path in _folder().glob('*.xls'):
        if not re.fullmatch(r'[a-f0-9]{32}\.xls', path.name):
            continue
        try:
            stat = path.stat()
            if stat.st_mtime < time.time()-TTL:
                path.unlink(missing_ok=True)
            else:
                files.append(stat.st_size)
        except FileNotFoundError:
            pass
    return files


def prepare(factory, owner, body):
    keys = {'date', 'customer', 'template', 'sourceRevision', 'versions'}
    if not isinstance(body, dict) or set(body) != keys or any(not isinstance(body[k], str) for k in keys-{'versions'}):
        raise HTTPException(422, 'Excel 导出参数不正确')
    if body['template'] not in {'detail', 'group', 'internal'}:
        raise HTTPException(422, '请选择有效的模板')
    data = weekly.query(factory, body['date'], body['customer'])
    # Compare both source records and all visible saved supplement versions.
    if body['sourceRevision'] != data['sourceRevision'] or body['versions'] != versions(data):
        raise HTTPException(409, '验货记录或周报补充内容已变化，请刷新核对后再导出 Excel')
    content = render(data, body['template'])
    template = next(t for t in data['templates'] if t['id'] == body['template'])
    filename = template['title']+'_'+data['dateFrom']+'_'+data['dateTo']+'.xls'
    nonce = secrets.token_hex(16)
    value = f"{nonce}.{int(time.time())+TTL}.{body['template']}.{data['dateFrom']}.{data['dateTo']}"
    token = value+'.'+_signature(owner, value)
    try:
        _folder().mkdir(parents=True, exist_ok=True)
        files = _clean()
        if len(files) >= 64 or sum(files)+len(content) > 128*1024*1024:
            raise HTTPException(429, 'Excel 下载任务较多，请稍后重试')
        with os.fdopen(os.open(_folder()/(nonce+'.xls'), os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600), 'wb') as stream:
            stream.write(content)
    except OSError:
        raise HTTPException(503, 'Excel 下载文件暂时无法保存，请重试') from None
    return dict(url='api/weekly-templates/excel/'+token, filename=filename)


def download(owner, token):
    match = re.fullmatch(r'([a-f0-9]{32})\.(\d{10})\.(detail|group|internal)\.(\d{4}-\d{2}-\d{2})\.(\d{4}-\d{2}-\d{2})\.([a-f0-9]{64})', token)
    if not match or not hmac.compare_digest(_signature(owner, token.rsplit('.', 1)[0]), match[6]):
        raise HTTPException(404, 'Excel 下载不存在')
    if int(match[2]) < time.time():
        _clean(); raise HTTPException(410, 'Excel 下载已过期，请重新导出')
    try:
        content = (_folder()/(match[1]+'.xls')).read_bytes()
    except OSError:
        raise HTTPException(410, 'Excel 下载已过期，请重新导出') from None
    title = next(t['title'] for t in weekly.TEMPLATES if t['id'] == match[3])
    return content, f'{title}_{match[4]}_{match[5]}.xls'
