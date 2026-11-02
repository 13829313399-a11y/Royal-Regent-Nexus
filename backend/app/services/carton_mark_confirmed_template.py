"""An approved layout is reusable; its historical order values never are.

The 4500222793 profile enrolls only complete native vendor-grid originals.
Other layouts continue through the existing flexible reader. No provider or
Office formula execution is needed to bind an already recognized native grid.
"""
import copy
import hashlib
import io
import json
import re
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from xml.sax.saxutils import escape

from fastapi import HTTPException
from openpyxl.utils.cell import coordinate_to_tuple
from reportlab.lib.pagesizes import A3, A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph

from app.services import carton_mark_flexible as flow
from app.services.carton_mark_layout_renderer import label as identify
from app.services.carton_mark_hyvee import validate_gtin

PROFILE_PATH = Path(__file__).resolve().parents[1] / 'templates/carton_marks/zuru_vendor_grid_v1.json'
KEYS = ('vendor', 'product', 'content', 'gtin', 'vendor_item', 'dimensions', 'gross_weight', 'item')
WEIGHT_PATTERN = r'(?:0*[1-9]\d*(?:\.\d+)?|0*\.\d*[1-9]\d*)\s*KGS?'
TITLES = dict(vendor='Vendor name:', product='Product name:', content='Content:', gtin='GTIN:',
              vendor_item='Vendor product number:', dimensions='Width/Length/Height:', gross_weight='Gross weight:', item='Item:')


def profile():
    return json.loads(PROFILE_PATH.read_text(encoding='utf-8'))


def signature():
    return hashlib.sha256(PROFILE_PATH.read_bytes()).hexdigest()


def metadata():
    p = profile()
    return {key: p[key] for key in ('id', 'name', 'version', 'reference_sha256')}


def logo_bytes():
    data = PROFILE_PATH.with_name('zuru_vendor_grid_logo.png').read_bytes()
    if hashlib.sha256(data).hexdigest() != profile()['logo_sha256']:
        raise HTTPException(503, '确认模板的品牌素材完整性检查失败')
    return data


def match(source):
    """Fail closed for partial grids, conflicts, extra records or other faces."""
    if source.get('detail_rows'):
        return None
    note_locations = {n.location for n in source['notes']}
    sheets = defaultdict(dict)
    for cell in source['cells']:
        if cell.kind != 'current_cell':
            return None
        name, coord = cell.location.rsplit('!', 1)
        sheets[name][coordinate_to_tuple(coord)] = cell
    records, bindings, used = [], [], set()
    for name, cells in sheets.items():
        candidates = defaultdict(list)
        for (row, col), cell in cells.items():
            key, inline = identify(cell.text)
            if not key:
                continue
            right = min((c for (r, c), v in cells.items() if r == row and c > col and identify(v.text)[0]), default=col+10)
            parts = [cell] if inline else [v for (r, c), v in sorted(cells.items()) if r == row and col < c < right and v.location not in note_locations and not re.search(r'根据实际|请.*填写|备注',v.text)]
            if not parts:
                parts = [v for (r, c), v in sorted(cells.items()) if r == row+1 and col <= c < right]
            if parts:
                value = inline or ' '.join(p.text for p in parts)
                candidates[key].append((cell, parts, value, bool(inline)))
        if any(len(candidates[k]) != 1 for k in KEYS):
            return None
        found = {key: candidates[key][0] for key in KEYS}
        if found['vendor'][2].upper() != 'ZURU INC' or not re.fullmatch(r'[1-9]\d*\s*PCS\s*/\s*CTN', found['content'][2], re.I):
            return None
        if found['item'][2] != found['vendor_item'][2] or not re.fullmatch(r'\d{14}', found['gtin'][2]):
            return None
        try:
            validate_gtin(found['gtin'][2], 14)
        except HTTPException:
            return None
        native_text = '\n'.join(c.text for c in cells.values())
        # This profile has equal front/side content plus an optional France
        # footer. It cannot absorb a different explicitly marked panel layout.
        if not re.search(r'四个面|四面|four\s+sides|4\s+sides', native_text, re.I):
            return None
        if any(source.get('ownership', {}).get(c.id) for c in cells.values()):
            return None
        if not re.search(r'\bZURU\b', native_text):
            return None
        if 'width/length/height' not in re.sub(r'\s+', '', found['dimensions'][0].text).lower():
            return None
        # Additional native labels must not disappear inside this fixed grid.
        if re.search(r'net\s*weight|customer\s*po|country\s*of\s*origin|made\s+in|\bDC\s*#', native_text, re.I):
            return None
        if re.search(r'不需.*扫|不可扫|can.?t\s*scan|code\s*128|ean.?13|upc.?a',native_text,re.I):
            return None
        if any(re.search(r'barcode|条码',c.text,re.I) and re.search(r'\d',c.text) and re.search(r'mm|毫米|宽|高|height|width',c.text,re.I) for c in cells.values()):
            return None
        limits=flow.constraints(source)
        if limits['width']>45 or limits['height']>15 or limits['frame']:
            return None  # A different barcode specification needs its own rule.
        wants_france = bool(re.search(r'侧唛[^\n。]*法国地址|side[^\n.]*france\s+address', native_text, re.I))
        if re.search(r'侧唛[^\n。]*(?:不|无需|不要)[^\n。]*法国地址|side[^\n.]*(?:\bno\b|\bnot\b)[^\n.]*france\s+address',native_text,re.I):
            wants_france=False
        address_cells = [c for c in cells.values() if re.search(r'care@|rue\s+Paul|FRANCE[.,]', c.text, re.I)]
        if address_cells:  # An explicit address requires its own reviewed rule.
            return None
        fields = []
        for key in KEYS:
            cell, parts, value, inline = found[key]
            if any('#' in p.text and re.search(r'#N/A|#REF!|#VALUE!', p.text) for p in parts):
                return None
            placeholder = key in {'dimensions', 'gross_weight'} and not re.search(r'\d', value)
            if key=='dimensions' and not placeholder and dimensions(value) is None:
                return None
            if key=='gross_weight' and not placeholder and not re.fullmatch(WEIGHT_PATTERN,value,re.I):
                return None
            fields.append(flow.TextField(label=None if inline else flow.Selection(source_id=cell.id, value=cell.text),
                parts=[flow.Selection(source_id=p.id, value=p.text) for p in parts], role='placeholder' if placeholder else 'normal'))
            used.update(p.id for p in parts); used.add(cell.id)
        for cell in cells.values():
            if cell.id in used or cell.location in note_locations:
                continue
            if cell.text.strip() in {'ZURU',found['gtin'][2],'Barcode'}:
                continue
            if re.search(r'宽\s*[*×x]\s*长\s*[*×x]\s*高|根据实际.*填写',cell.text):
                continue
            return None  # Unknown printable content requires a different layout.
        gtin_cell = found['gtin'][1][0]
        barcode = flow.Barcode(source=flow.Selection(source_id=gtin_cell.id, value=gtin_cell.text), kind='ITF14',
            width_mm=45, height_mm=15, note_ids=[], frame='none')
        panels = [flow.Panel(face=face, copies=2, logo=True, fields=copy.deepcopy(fields), barcodes=[copy.deepcopy(barcode)], symbols=[]) for face in ('front', 'side')]
        records.append(flow.Record(panels=panels))
        bindings.append(dict(sheet=name, france_address=wants_france))
    if not 1 <= len(records) <= 50:
        return None
    plan = flow.Plan(template_id='source-flow-v1', paper='A4', orientation='landscape', records=records,
        notes=[flow.NoteChoice(source_id=n.id, action='needs_confirmation') for n in source['notes']],
        ignored_cells=[flow.Ignored(source_id=c.id, reason='unused') for c in source['cells'] if c.id not in used])
    return plan, bindings


def field_value(field, key):
    value = flow.field_value(field.parts)
    found, inline = identify(value)
    return inline if found == key and inline else value


def dimensions(value):
    found = re.fullmatch(r'\s*(\d+(?:\.\d+)?)\s*[x×*]\s*(\d+(?:\.\d+)?)\s*[x×*]\s*(\d+(?:\.\d+)?)\s*CM\s*', value, re.I)
    if not found:
        return None
    values = tuple(Decimal(v) for v in found.groups())
    return values if all(0 < v <= 1000 for v in values) else None


def logo_rule(value):
    dims = dimensions(value)
    if dims is None:
        return '待补实际宽×长×高（CM），再确定 LOGO 实际印刷宽度。'
    width, _, height = dims
    if width < 30:
        return '纸箱宽度小于30cm，需确认 LOGO 按比例缩放的实际印刷宽度。'
    for rule in profile()['logo_rules']:
        low, high = Decimal(rule['width_min_cm']), rule['width_max_cm']
        if (width >= low if rule['width_min_inclusive'] else width > low) and (high is None or width <= high):
            if height < rule['height_min_cm']:
                return f"箱高低于该档要求的{rule['height_min_cm']}cm，需确认 LOGO 印刷尺寸。"
            return f"按确认稿规则：LOGO 实际印刷宽度 {rule['logo_width_cm']}cm（当前PDF为缩放审阅稿）。"
    raise ValueError('Unknown logo size tier')


def issues(records, bindings):
    result = []
    for r, record in enumerate(records):
        for key in ('dimensions', 'gross_weight'):
            i = KEYS.index(key); field = record['panels'][0]['fields'][i]
            if field['placeholder']:
                result.append(dict(kind='missing_value', message=f"第{r+1}组：请补充实际{'宽×长×高（CM）' if key == 'dimensions' else '毛重（KG）'}，自动同步正侧唛。", field_ids=[field['id']], sources=field['sources']))
        result.append(dict(kind='certification', message=f'第{r+1}组：未沿用历史纸箱认证章，需按本单纸箱强度确认。', field_ids=[], sources=['确认版式：认证章规则']))
    return result


def synchronize(plan, edits):
    """One physical carton has one set of measurements on both printed faces."""
    for r, record in enumerate(plan.records):
        for key in ('dimensions', 'gross_weight'):
            i = KEYS.index(key)
            entered = [edits[f'r{r}p{p}f{i}'].strip() for p in (0, 1) if f'r{r}p{p}f{i}' in edits]
            if not entered:
                continue
            if len(set(entered)) != 1:
                raise HTTPException(422, '同一纸箱的正侧唛尺寸或毛重冲突，请填写相同实际值')
            value = entered[0]
            if key == 'dimensions' and dimensions(value) is None:
                raise HTTPException(422, '请按宽×长×高填写正数尺寸并带 CM，例如 35 x 40 x 25 CM')
            if key == 'gross_weight' and not re.fullmatch(WEIGHT_PATTERN, value, re.I):
                raise HTTPException(422, '请填写实际正数毛重并带 KG，例如 5.5 KG')
            chosen = next(record.panels[p].fields[i] for p in (0, 1) if f'r{r}p{p}f{i}' in edits)
            for panel in record.panels:
                panel.fields[i] = copy.deepcopy(chosen)


def render(plan, source, bindings, logo, include_sources=False):
    """Fresh text and barcode vectors inside a stable, measured review layout."""
    cfg = profile()
    font_path = Path('C:/Windows/Fonts/ARIALNB.TTF')
    if not font_path.is_file():
        raise HTTPException(503, '确认版式需要 Arial Narrow Bold 字体；当前服务器尚未配置，未自动替换')
    font = 'ConfirmedVendorGrid'
    if font not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(font, str(font_path)))
    cjk = 'STSong-Light'
    if cjk not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont(cjk))
    size = A4 if plan.paper == 'A4' else A3
    if plan.orientation == 'landscape':
        size = landscape(size)
    width, height = (n/mm for n in size)
    if width < height:
        raise HTTPException(422, '4500222793 确认版式为正侧唛左右排版，请使用横向纸张')
    out = io.BytesIO(); c = Canvas(out, pagesize=size, pageCompression=1)
    warnings = ['已采用4500222793确认版式；本单值来自当前原稿，嵌入示例条码未复制。', '历史纸箱认证章未沿用，需按本单纸箱强度确认。']
    scale = width/297

    def text(value, x, top, w, h, pt=15, bold=True):
        nonlocal warnings
        family = cjk if re.search(r'[\u2e80-\u9fff]', value) else font
        # Wrapping is bounded by a real box. Never clip or shrink below the
        # profile's readable minimum to make a long new description fit.
        for size_pt in range(round(pt), round(min(pt,cfg['minimum_body_pt']))-1, -1):
            para = Paragraph(escape(value).replace('\n', '<br/>'), ParagraphStyle('confirmed',fontName=family,fontSize=size_pt,leading=size_pt*1.12))
            _, used = para.wrap(w*mm, h*mm)
            if used <= h*mm:
                para.drawOn(c,x*mm,(top-h/2)*mm-used/2); return
        raise HTTPException(422, '本单文字超出确认模板的可读区域，请缩短经确认的印刷文字或使用更大纸张；未裁切')

    for r, record in enumerate(plan.records):
        left, top, total_w, bottom = 9*scale, height-40*scale, width-18*scale, 20*scale
        divide = left+total_w*cfg['front_ratio']
        c.setStrokeColorRGB(.9,.17,.12);c.setLineWidth(.8)
        c.rect(left*mm,bottom*mm,total_w*mm,(top-bottom)*mm)
        c.line(divide*mm,bottom*mm,divide*mm,top*mm)
        header = top-20*scale
        c.line(left*mm,header*mm,(left+total_w)*mm,header*mm)
        item = field_value(record.panels[0].fields[KEYS.index('item')], 'item')
        text('ITEM: '+item,left,height-8*scale,total_w,9*scale,18)
        text(logo_rule(field_value(record.panels[0].fields[KEYS.index('dimensions')], 'dimensions')),left,height-21*scale,total_w,12*scale,12)
        for p, panel in enumerate(record.panels):
            start, end = (left,divide) if p==0 else (divide,left+total_w)
            center = (start+end)/2
            text(('正唛' if panel.face=='front' else '侧唛')+f' × {panel.copies}',start+5*scale,top-4*scale,end-start-10*scale,12*scale,20)
            c.drawImage(ImageReader(io.BytesIO(logo)),(center-22*scale)*mm,(header-24*scale)*mm,44*scale*mm,20*scale*mm,preserveAspectRatio=True,mask='auto')
            x, tw = center-51*scale, 102*scale
            y = header-27*scale
            vals = {key:field_value(panel.fields[i], key) for i,key in enumerate(KEYS)}
            # A longer product takes a taller row; the remaining geometry flows
            # beneath it and is verified against the footer before drawing.
            product_h = (14 if len(vals['product']) > 48 else 10)*scale
            heights = [10*scale,product_h,8*scale,16*scale,16*scale,23*scale]
            table_h = sum(heights)
            if y-table_h < bottom+15*scale:
                raise HTTPException(422,'本单内容超出确认版式，请选择A3横向；未裁切内容')
            c.setStrokeColorRGB(.12,.12,.12);c.setLineWidth(.65)
            c.rect(x*mm,(y-table_h)*mm,tw*mm,table_h*mm)
            rows = [('Vendor name: '+vals['vendor'],heights[0]),('Product name: '+vals['product'],heights[1]),('Content: '+vals['content'],heights[2])]
            cursor=y
            for value,rh in rows:
                text(value,x+1.5*scale,cursor,tw-3*scale,rh,15);cursor-=rh
                c.line(x*mm,cursor*mm,(x+tw)*mm,cursor*mm)
            for a,b,rh in [('gtin','vendor_item',heights[3]),('dimensions','gross_weight',heights[4])]:
                c.line((x+tw*.47)*mm,cursor*mm,(x+tw*.47)*mm,(cursor-rh)*mm)
                for key,xx,ww in [(a,x,tw*.47),(b,x+tw*.47,tw*.53)]:
                    text(TITLES[key],xx+1.5*scale,cursor,ww-3*scale,6.5*scale,14)
                    f=panel.fields[KEYS.index(key)]
                    value=vals[key] if f.role!='placeholder' else ('待补宽×长×高 CM' if key=='dimensions' else '待补 KG')
                    c.setFillColorRGB(*((.7,.12,.09) if f.role=='placeholder' else (0,0,0)))
                    text(value,xx+1.5*scale,cursor-6.5*scale,ww-3*scale,rh-6.5*scale,14)
                    c.setFillColorRGB(0,0,0)
                cursor-=rh;c.line(x*mm,cursor*mm,(x+tw)*mm,cursor*mm)
            validate_gtin(vals['gtin'],14)
            drawing=flow._barcode(flow.Barcode(source=flow.Selection(source_id='T1',value=vals['gtin']),kind=cfg['barcode_kind'],width_mm=cfg['barcode_width_mm']*scale,height_mm=15*scale,note_ids=[],frame='none'))
            drawing.drawOn(c,center*mm-drawing.width/2,(cursor-16*scale)*mm)
            text(vals['gtin'],center-28*scale,cursor-16*scale,56*scale,6*scale,11)
            if panel.face=='side' and bindings[r]['france_address']:
                text(cfg['france_address'],x,y-table_h-3*scale,tw,11*scale,11)
        c.setFont(cjk,8);c.drawString(left*mm,11*scale*mm,'确认版式审阅稿，非1:1生产图；认证章、实际印刷尺寸和实打扫码需核实。')
        warnings.append(f"第{r+1}组："+logo_rule(vals['dimensions']))
        c.showPage()
    if include_sources:
        for r,binding in enumerate(bindings):
            text(f"确认版式 {cfg['id']} V{cfg['version']} · 第{r+1}组",10,height-10,width-20,12,14)
            text('来源工作表：'+binding['sheet']+'\n参考PDF SHA256：'+cfg['reference_sha256']+'\n法国地址：'+('仅按本单明确要求采用确认版式固定地址' if binding['france_address'] else '本单未要求，未添加')+'\n认证章：未继承历史强度声明',10,height-27,width-20,40,12)
            c.showPage()
        # Retain the existing complete source/notes/manual-change ledger.
        record_pdf,_,record_warnings=flow.render(plan,source,logo,include_sources=True,note_origin='template')
        from pypdf import PdfReader, PdfWriter
        c.save(); writer=PdfWriter()
        writer.append(PdfReader(io.BytesIO(out.getvalue())))
        source_reader=PdfReader(io.BytesIO(record_pdf))
        source_start=len(plan.records)
        writer.append(source_reader,pages=(source_start,len(source_reader.pages)))
        final=io.BytesIO();writer.write(final)
        return final.getvalue(),len(writer.pages),list(dict.fromkeys(warnings+record_warnings))
    c.save()
    return out.getvalue(),len(plan.records),list(dict.fromkeys(warnings))
