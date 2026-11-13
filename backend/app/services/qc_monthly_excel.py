"""Original monthly workbook layouts and complete, authenticated photo exports."""
from contextlib import closing
from copy import deepcopy, copy
from datetime import date
from hashlib import sha256
from io import BytesIO
import json, math, re, sqlite3, unicodedata
from pathlib import Path
from threading import BoundedSemaphore
import xlrd, xlwt, openpyxl
from xlutils.filter import XLWTWriter
from openpyxl.drawing.image import Image
from openpyxl.drawing.spreadsheet_drawing import AnchorMarker, OneCellAnchor
from openpyxl.drawing.xdr import XDRPositiveSize2D
from PIL import Image as PILImage
from fastapi import HTTPException
from app.core.config import settings
from app.services import qc_monthly_templates as monthly, qc_weekly_excel as shared, qc_photo_assets as assets

TEMPLATE_DIR=Path(__file__).resolve().parents[1]/'templates/qc-monthly'
ASSETS=json.loads((TEMPLATE_DIR/'templates.json').read_text())
MAX_BYTES=32*1024*1024
PHOTO_GRID_WIDTH=665
PHOTO_GRID_HEIGHT=530
PHOTO_PADDING=8
EMU_PER_PIXEL=9525
export_slots=BoundedSemaphore(2)
EXPORT_NAMES = {'caixing':'彩星汇总_月度验货明细', 'all':'全客明细_月度验货',
                'issues':'问题图文_月度验货', 'customers':'分客明细_月度验货'}

def filename(kind, start, end, quality=None):
    suffix='_预览图' if kind=='issues' and quality=='preview' else ''
    return f'{EXPORT_NAMES[kind]}_{start}_{end}{suffix}'+extension(kind)

def _center_column(widths):
    """Nearest column centre to the table midpoint, without merged cells."""
    midpoint=sum(widths)/2
    return min(range(len(widths)),key=lambda c:abs(sum(widths[:c])+widths[c]/2-midpoint))
versions=shared.versions


def _asset(kind):
    spec=ASSETS[kind]
    try: raw=(TEMPLATE_DIR/spec['file']).read_bytes()
    except OSError as exc: raise HTTPException(503,'月报原模板不可用') from exc
    if sha256(raw).hexdigest()!=spec['sha256']: raise HTTPException(503,'月报模板校验失败')
    return raw,spec


def _photo(factory, entry, photo):
    path=Path(settings.qc_department_data_dir).resolve()/'_inspection_sheet/inspections.sqlite3'
    try:
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as conn:
            conn.row_factory=sqlite3.Row
            row=conn.execute("""SELECT p.* FROM photos p JOIN entries e ON e.id=p.entry_id
                JOIN entry_details d ON d.entry_id=e.id WHERE e.factory=? AND e.id=? AND e.revision=?
                AND d.review_state='approved' AND p.id=? AND p.removed=0""",
                (factory,entry['id'],entry['revision'],photo['id'])).fetchone()
            if row is None:raise HTTPException(409,'验货照片或审核记录已变化，请刷新核对后导出')
            return assets.read(conn,row,'preview')[0]
    except sqlite3.Error as exc:raise HTTPException(503,'验货照片读取失败，请重试') from exc


def _needs_excel_conversion(image_format, orientation):
    return image_format not in {'JPEG','PNG'} or orientation!=1


def _name(name, used):
    name=re.sub(r'[\\/*?:\[\]\x00-\x1f]','_',name).strip().strip("'") or '未填写客户'
    candidate=name[:31];n=1
    while candidate.casefold() in used:
        n+=1;candidate=name[:26]+'_'+str(n)
    used.add(candidate.casefold());return candidate


def _groups(data, kind):
    rows=data['tables'][kind]
    if kind!='customers': return [(None,rows)]
    return [(c,[r for r in rows if r['customerKey']==c['key']]) for c in data['customers'] if any(r['customerKey']==c['key'] for r in rows)]


def _xls(data,kind):
    raw,asset=_asset(kind);source=xlrd.open_workbook(file_contents=raw,formatting_info=True)
    writer=XLWTWriter();writer.workbook(source,'monthly.xls');book=writer.wtbook
    for st in writer.style_list:st.num_format_str=st.num_format_str or 'General'
    for i,rgb in source.colour_map.items():
        if 8<=i<=63 and rgb:book.set_colour_RGB(i,*rgb)
    used=set();period=data['dateFrom'][:7];spec=next(t for t in monthly.TEMPLATES if t['id']==kind)
    for customer,rows in _groups(data,kind):
        if len(rows)>65500: raise HTTPException(422,'记录超过 XLS 行数上限，请按客户筛选')
        sheets={s.name.casefold():s for s in source.sheets()}
        original=sheets.get(customer['name'].casefold(),source.sheet_by_index(0)) if customer else source.sheet_by_index(0)
        writer.sheet(original,_name(customer['name'] if customer else period,used));target=writer.wtsheet
        target.first_visible_row=target.first_visible_col=0;target.panes_frozen=True
        target.horz_split_pos=asset['headerRow']+1;target.vert_split_pos=0;target.active_pane=3;target.split_position_units_are_twips=False
        for c in range(original.ncols):target.col(c).width=original.colinfo_map[c].width if c in original.colinfo_map else 3000
        target.col(0 if kind=='caixing' else 1).width=max(13*256,target.col(0 if kind=='caixing' else 1).width)
        def style(r,c):
            st=deepcopy(writer.style_list[original.cell_xf_index(r,c)]);st.alignment.wrap=1
            for edge in ('top','bottom','left','right'):setattr(st.borders,edge,xlwt.Borders.THIN)
            return st
        def title(r,start,end,label,model,column,height):
            # Ordinary centered text over empty neighbours is displayed by both
            # Excel and ONLYOFFICE; center-across-selection is not portable.
            anchor=start+_center_column([target.col(c).width for c in range(start,end)])
            for c in range(start,end):
                st=style(model,column);st.alignment.wrap=0
                st.alignment.horz=xlwt.Alignment.HORZ_CENTER
                st.alignment.vert=xlwt.Alignment.VERT_CENTER
                st.borders.left=xlwt.Borders.THIN if c==start else xlwt.Borders.NO_LINE
                st.borders.right=xlwt.Borders.THIN if c==end-1 else xlwt.Borders.NO_LINE
                target.write(r,c,label if c==anchor else '',st)
            target.row(r).height=height
        def write(r,values,model,offset=0):
            height=original.rowinfo_map.get(model).height if model in original.rowinfo_map else 400
            for c,v in enumerate(values,offset):
                st=style(model,c)
                if isinstance(v,date):st.num_format_str='yyyy-mm-dd'
                target.write(r,c,v,st)
                # Column widths use default-font character units; account for wide CJK
                # glyphs, explicit newlines and the actual cell font size.
                width=max(1,target.col(c).width/256*10/max(1,st.font.height/20)*0.85)
                lines=sum(max(1,math.ceil(sum(2 if unicodedata.east_asian_width(ch) in ('W','F') else 1 for ch in line)/width)) for line in str(v).split('\n'))
                height=max(height,lines*st.font.height*1.35+120)
            target.row(r).height=min(8180,int(height));target.row(r).height_mismatch=True
        if kind!='caixing':
            label=(customer['name']+' ' if customer else '')+period+' 月度验货明细表'+('（全客户）' if not customer else '')
            title(0,0,len(spec['headers']),label,0,0,540)
        write(asset['headerRow'],spec['headers'],asset['headerRow'])
        for i,row in enumerate(rows,asset['dataRow']):
            values=list(row['values']);di=0 if kind=='caixing' else 1;values[di]=date.fromisoformat(values[di])
            if kind=='customers':values[0]=i-asset['dataRow']+1
            write(i,values,asset['dataRow'])
        if kind=='caixing':
            foot=len(rows)+3
            for summary in data['tables']['summary']:
                customer_info=next(c for c in data['customers'] if c['key']==summary['customerKey'])
                label='彩星 '+period+' 月度验货统计汇总表'
                if len(data['tables']['summary'])>1:label+=' · '+customer_info['label']
                title(foot,1,6,label,20,1,440)
                write(foot+1,data['summaryHeaders'],21,1)
                values=list(summary['values']);values[3]=int(values[3]) if values[3]!='' else ''
                write(foot+2,values,21,1);foot+=4
    stream=BytesIO();book.save(stream);return stream.getvalue()


def _photo_slots(count):
    """Choose the grid with the most space per photo inside one Excel row."""
    def cell_size(columns):
        rows=math.ceil(count/columns)
        return ((PHOTO_GRID_WIDTH-PHOTO_PADDING)/columns-PHOTO_PADDING,
                (PHOTO_GRID_HEIGHT-PHOTO_PADDING)/rows-PHOTO_PADDING)

    columns=max(range(1,count+1),key=lambda c:min(cell_size(c)))
    return columns,*cell_size(columns)


def _xlsx(data,factory):
    raw,_=_asset('issues');book=openpyxl.load_workbook(BytesIO(raw));sheet=book.active
    sheet.title=data['dateFrom'][:7]+'问题记录'
    model=[copy(c._style) for c in sheet[2][:12]]
    model.append(model[-1])
    sheet.delete_rows(2,sheet.max_row)
    header_height=sheet.row_dimensions[1].height or 30
    sheet.insert_rows(1)
    sheet.row_dimensions[1].height=26
    sheet.row_dimensions[2].height=header_height
    sheet.column_dimensions['A'].width=max(13,sheet.column_dimensions['A'].width)
    sheet.column_dimensions['L'].width=28
    sheet.column_dimensions['M'].width=100
    sheet['L2']='照片备注'
    sheet['M2']='照片'
    sheet['M2']._style=copy(sheet['L2']._style)
    widths=[sheet.column_dimensions[openpyxl.utils.get_column_letter(c)].width or 10 for c in range(1,14)]
    anchor=1+_center_column(widths)
    title=sheet.cell(1,anchor,data['dateFrom'][:7]+' 月度验货问题图文记录表')
    title.font=copy(sheet.cell(2,1).font)
    title.alignment=openpyxl.styles.Alignment(horizontal='center',vertical='center')
    sheet.freeze_panes='A3';sheet.print_title_rows='1:2';sheet.sheet_view.topLeftCell='A1'
    photo_bytes=0;embedded_bytes=0
    rows=data['tables']['issues']
    for rownum,entry in enumerate(rows,3):
        values=[*entry['values'],''];values[0]=date.fromisoformat(values[0])
        for c,v in enumerate(values,1):
            cell=sheet.cell(rownum,c,v)
            cell._style=copy(model[c-1])
            cell.alignment=openpyxl.styles.Alignment(
                horizontal='left' if c==12 else 'center',
                vertical='top' if c==12 else 'center',wrap_text=True)
            if isinstance(v,str):cell.data_type='s'
        sheet.cell(rownum,1).number_format='yyyy-mm-dd'
        text_lines=max(sum(max(1,math.ceil(sum(2 if unicodedata.east_asian_width(ch) in ('W','F') else 1
                            for ch in line)/max(4,width/1.5))) for line in str(v).split('\n'))
                       for v,width in zip(values,widths))
        photo_bottom=0
        photos=entry['photos']
        if photos:
            columns,slot_width,slot_height=_photo_slots(len(photos))
            for j,photo in enumerate(photos):
                content=_photo(factory,entry,photo);photo_bytes+=len(content)
                if photo_bytes>MAX_BYTES:raise HTTPException(422,'照片总量过大，请按客户筛选后分别导出')
                try:
                    with PILImage.open(BytesIO(content)) as original:
                        if _needs_excel_conversion(original.format,original.getexif().get(274,1)):
                            content=assets.display_png(content)
                    embedded_bytes+=len(content)
                    if embedded_bytes>MAX_BYTES:raise HTTPException(422,'图片总量过大，请缩小导出范围')
                    image=Image(BytesIO(content));ratio=min(slot_width/image.width,slot_height/image.height,1)
                    image.width*=ratio;image.height*=ratio
                    left=PHOTO_PADDING+(j%columns)*(slot_width+PHOTO_PADDING)+(slot_width-image.width)/2
                    top=PHOTO_PADDING+(j//columns)*(slot_height+PHOTO_PADDING)
                    photo_bottom=max(photo_bottom,top+image.height+PHOTO_PADDING)
                    marker=AnchorMarker(col=12,row=rownum-1,colOff=round(left*EMU_PER_PIXEL),rowOff=round(top*EMU_PER_PIXEL))
                    image.anchor=OneCellAnchor(_from=marker,ext=XDRPositiveSize2D(
                        round(image.width*EMU_PER_PIXEL),round(image.height*EMU_PER_PIXEL)))
                    sheet.add_image(image)
                except (OSError,ValueError) as exc:raise HTTPException(422,'验货照片无法解码，未生成缺图文件') from exc
        sheet.row_dimensions[rownum].height=max(60,min(405,text_lines*15),math.ceil(photo_bottom*0.75))
    sheet.print_area=f'A1:M{len(rows)+2}';sheet.page_setup.orientation='landscape';sheet.page_setup.paperSize=sheet.PAPERSIZE_A3
    stream=BytesIO();book.save(stream);return stream.getvalue()


def render(data,kind,factory='huaxing'):
    if kind not in ASSETS:raise HTTPException(422,'月报模板不正确')
    if not data['tables'][kind]:raise HTTPException(409,'当前模板没有验货记录，无法导出空白文件')
    if not export_slots.acquire(timeout=5):raise HTTPException(429,'Excel 导出繁忙，请稍后重试')
    try:
        content=_xlsx(data,factory) if kind=='issues' else _xls(data,kind)
        if len(content)>MAX_BYTES:raise HTTPException(422,'Excel 文件过大，请按客户筛选后导出')
        return content
    finally:export_slots.release()

import hmac, os, secrets, time
TTL=600
def extension(kind): return '.xlsx' if kind=='issues' else '.xls'

def _folder():
    return Path(settings.qc_department_data_dir).resolve() / '_monthly_excel_exports'


def _signature(owner, value):
    key = settings.qc_department_gateway_token.get_secret_value()
    if not key:
        raise HTTPException(503, '下载服务尚未配置')
    return hmac.new(key.encode(), ('qc-monthly-excel:'+owner+':'+value).encode(), sha256).hexdigest()


def _clean():
    files = []
    for path in _folder().glob('*.xls*'):
        if not re.fullmatch(r'[a-f0-9]{32}\.xlsx?', path.name):
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


def checked_data(factory, body):
    keys = {'date', 'customer', 'template', 'sourceRevision', 'versions'}
    if not isinstance(body, dict) or not keys <= set(body) or set(body)-keys-{'photoQuality','allowPreviewFallback'} or any(not isinstance(body[k], str) for k in keys-{'versions'}):
        raise HTTPException(422, 'Excel 导出参数不正确')
    if body['template'] not in set(ASSETS):
        raise HTTPException(422, '请选择有效的模板')
    # Previously loaded clients can still submit the preview variant explicitly.
    if body.get('photoQuality','preview')!='preview' or body.get('allowPreviewFallback',False) is not False:
        raise HTTPException(422,'报告中心仅支持导出预览图，请刷新页面后重试')
    data = monthly.query(factory, body['date'], body['customer'])
    # Compare both source records and all visible saved supplement versions.
    if body['sourceRevision'] != data['sourceRevision'] or body['versions'] != versions(data):
        raise HTTPException(409, '验货记录或月报补充内容已变化，请刷新核对后再导出 Excel')
    return data


def prepare(factory, owner, body):
    data=checked_data(factory,body)
    kind=body['template']
    content = render(data, kind, factory)
    fresh = monthly.query(factory, body['date'], body['customer'])
    if fresh['sourceRevision'] != data['sourceRevision'] or versions(fresh) != versions(data):
        raise HTTPException(409, '导出期间记录已变化，请刷新后重试')
    photo_quality='preview' if kind=='issues' and any(row['photos'] for row in data['tables']['issues']) else None
    download_name = filename(kind,data['dateFrom'],data['dateTo'],photo_quality)
    nonce = secrets.token_hex(16)
    value = f"{nonce}.{int(time.time())+TTL}.{kind}.{data['dateFrom']}.{data['dateTo']}"
    if photo_quality:
        value+='.'+photo_quality
    token = value+'.'+_signature(owner, value)
    try:
        _folder().mkdir(parents=True, exist_ok=True)
        files = _clean()
        if len(files) >= 64 or sum(files)+len(content) > 128*1024*1024:
            raise HTTPException(429, 'Excel 下载任务较多，请稍后重试')
        with os.fdopen(os.open(_folder()/(nonce+extension(kind)), os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600), 'wb') as stream:
            stream.write(content)
    except OSError:
        raise HTTPException(503, 'Excel 下载文件暂时无法保存，请重试') from None
    return dict(url='api/monthly-templates/excel/'+token, filename=download_name)


def download(owner, token):
    match = re.fullmatch(r'([a-f0-9]{32})\.(\d{10})\.(caixing|all|issues|customers)\.(\d{4}-\d{2}-\d{2})\.(\d{4}-\d{2}-\d{2})(?:\.(preview))?\.([a-f0-9]{64})', token)
    if not match or not hmac.compare_digest(_signature(owner, token.rsplit('.', 1)[0]), match[7]):
        raise HTTPException(404, 'Excel 下载不存在')
    if int(match[2]) < time.time():
        _clean(); raise HTTPException(410, 'Excel 下载已过期，请重新导出')
    try:
        content = (_folder()/(match[1]+extension(match[3]))).read_bytes()
    except OSError:
        raise HTTPException(410, 'Excel 下载已过期，请重新导出') from None
    return content, filename(match[3],match[4],match[5],match[6])
