"""Immutable customer artwork/layout; source-bound, request-local exceptions.

No customer is inferred from a recipient/brand printed in a workbook. The
operator explicitly selects this layout. Neither read nor render writes it.
"""
import base64
import hashlib
import io
import json
import re
from pathlib import Path
from typing import Literal
from xml.sax.saxutils import escape

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
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
from app.services.carton_supplier_mark_layout import serialized_pdf

PROFILE = Path(__file__).resolve().parents[1] / 'templates/carton_marks/zuru_front_side_v1.json'
ID = 'zuru-front-side-v1'


def profile(identifier=ID):
    if identifier != ID:
        raise HTTPException(422, '客户模板不存在，请重新选择')
    return json.loads(PROFILE.read_text(encoding='utf-8'))


def metadata():
    cfg = profile()
    return {key: cfg[key] for key in ('id', 'name', 'version', 'reference_sha256')}


def signature():
    return hashlib.sha256(PROFILE.read_bytes()).hexdigest()


def asset(name, expected):
    data = PROFILE.with_name(name).read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise HTTPException(503, '客户模板素材完整性校验失败')
    return data


def logo_bytes():
    return asset('zuru_front_side_logo.png', profile()['logo_sha256'])


def reference_image():
    data = asset('zuru_front_side_reference.jpg', profile()['preview_sha256'])
    return dict(id='T1', location='客户通用模板（空白字段，无历史订单数据）', data=base64.b64encode(data).decode())


def prompt():
    return '\n' + """本次明确选择4500227434正侧唛客户模板。T1是空白版式，不是订单来源。
模板为红框、正侧唛左右各2面、两面ZURU标志和向上标识。订单号、货号、品名、地址、数量、条码、重量只能选本次E原生字段；参考图中的示例和旧数字一律不能使用。不要补造本单没有的地址。每条当前订单独立一组，正侧唛字段各归其面。
按模板基础版式整理fields。图片可解释图形/位置/备注，不能用于本单业务数字。条码规格按原文，未写尺寸时宽50mm高15mm；原文有更大要求必须保留。
额外输出template_changes数组，每项为：{"record":0,"face":"front","note_ids":["N1"],"summary":"本单备注要求正文居中","align":"center"}。
只对原稿明确提出的特殊修改列项，record为0起始记录序号，face为front/side，note_ids必须引用本次N备注或I图片。可选修改键只有font_pt(8到20)、align(left/center/right)、logo_visible(bool)、symbols(this_side_up/fragile/keep_dry数组)、barcode_position(left/right)。font_pt为该面正文审阅字号。不要输出其他键或修改业务值。无法用这些参数准确落实的尺寸、复杂图形、指定字体或字段移动必须放入有来源的uncertainties，不能声称已落实。每条备注必须出现在template_changes或uncertainties的来源中；重复的已知模板规则也说明仍需核对实际印刷尺寸。
全部修改只针对本单，绝不能更新通用模板。"""


class OrderChange(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)
    record: int = Field(ge=0, le=99)
    face: Literal['front', 'side']
    note_ids: list[str] = Field(min_length=1, max_length=20)
    summary: str = Field(min_length=1, max_length=400)
    font_pt: float | None = Field(default=None, ge=8, le=20)
    align: Literal['left', 'center', 'right'] | None = None
    logo_visible: bool | None = None
    symbols: list[Literal['this_side_up', 'fragile', 'keep_dry']] | None = Field(default=None, max_length=3)
    barcode_position: Literal['left', 'right'] | None = None


def changes(raw, plan, source):
    data = json.loads(raw, object_pairs_hook=flow.pilot._unique_object)
    entries = data.get('template_changes', [])
    if not isinstance(entries, list) or len(entries) > 100:
        raise flow.pilot.PilotError('本单修改方案格式或数量无效')
    notes = {n.id for n in source['notes'] if n.kind in {'current_note', 'image_reference_text'}}
    result, seen = [], set()
    for entry in entries:
        try:
            change = OrderChange.model_validate(entry)
        except ValueError:
            raise flow.pilot.PilotError('本单修改超出模板支持范围，请核对备注') from None
        if change.record >= len(plan.records) or change.face not in {p.face for p in plan.records[change.record].panels} or any(n not in notes for n in change.note_ids):
            raise flow.pilot.PilotError('本单修改没有有效的箱面或备注来源')
        values = change.model_dump(exclude_none=True)
        options = set(values) - {'record', 'face', 'note_ids', 'summary'}
        if not options:
            raise flow.pilot.PilotError('本单修改没有可执行参数，须标记为待确认')
        for key in options:
            identity = (change.record, change.face, key)
            if identity in seen:
                raise flow.pilot.PilotError('同一箱面的备注修改相互重叠，请先确认')
            seen.add(identity)
        result.append(values)
    return result


def note_issues(source, changes):
    covered = {n for c in changes for n in c['note_ids']}
    return [dict(kind='template_note', message='尚未自动落实：' + n.text[:300], field_ids=[], sources=[n.location])
            for n in source['notes'] if n.kind in {'current_note', 'image_reference_text'} and n.id not in covered]


def apply_base(plan):
    for record in plan.records:
        for panel in record.panels:
            panel.logo = True
            existing = {s.kind for s in panel.symbols}
            if 'this_side_up' not in existing:
                panel.symbols.append(flow.Symbol(kind='this_side_up', note_ids=['T1']))


def identity(field):
    label=field.label.value if field.label else ''
    return bool(re.search(r'\b(?:P\.?O\.?\b|ORDER\s*(?:NO|NUMBER|#)|ITEM\s*(?:NO|NUMBER|#)|BARCODE|GTIN|UPC|EAN)',label,re.I))


def display_changes(records, changes):
    for change in changes:
        panel=next(p for p in records[change['record']]['panels'] if p['face']==change['face'])
        if 'logo_visible' in change:panel['logo']=change['logo_visible']
        if 'symbols' in change:panel['symbols']=change['symbols']


def change_notes(changes):
    return [flow.pilot.Evidence(id=f'C{i+1}',kind='template_change',location=f"本单修改!第{c['record']+1}组/{c['face']}",
            text=c['summary']+'；来源：'+','.join(c['note_ids'])+'；仅本单参数：'+json.dumps(c,ensure_ascii=False))
            for i,c in enumerate(changes)]


def _fonts():
    # Match the source's narrow Latin type without silently substituting it.
    from app.core.config import settings
    path = Path(settings.carton_mark_template_font_file or 'C:/Windows/Fonts/ARIALNB.TTF')
    if not path.is_file():
        raise HTTPException(503, '客户模板需要 Arial Narrow Bold 字体，请配置后生成')
    if 'CustomerCartonNarrow' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('CustomerCartonNarrow', str(path)))
    chinese=Path('C:/Windows/Fonts/simhei.ttf')
    cjk='CustomerCartonCJK' if chinese.is_file() else 'STSong-Light'
    if cjk not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(cjk,str(chinese)) if chinese.is_file() else UnicodeCIDFont(cjk))
    return 'CustomerCartonNarrow', cjk


@serialized_pdf
def render(plan, source, order_changes, *, include_sources=False, graphic_overrides=()):
    cfg = profile()
    if plan.orientation != 'landscape':
        raise HTTPException(422, '客户模板为左右正侧唛，请使用横向纸张')
    latin, cjk = _fonts()
    size = landscape(A4 if plan.paper == 'A4' else A3)
    width, height = (v/mm for v in size)
    scale = width/297
    output = io.BytesIO()
    c = Canvas(output, pagesize=size, pageCompression=1)
    logo = logo_bytes()
    warnings = ['采用4500227434客户模板；特殊修改仅作用于本单，未改写通用模板。',
                '缩放审阅稿，非1:1制版图；实际LOGO尺寸、条码尺寸和实打扫码仍需核实。']

    def paragraph(value, x, top, w, pt, *, align='left', bottom=20):
        family = cjk if re.search(r'[\u2e80-\u9fff]', value) else latin
        p = Paragraph(escape(value).replace('\n', '<br/>'), ParagraphStyle('customer', fontName=family,
                      fontSize=pt*scale, leading=pt*1.15*scale, alignment={'left': 0, 'center': 1, 'right': 2}[align]))
        _, used = p.wrap(w*mm, height*mm)
        if top-used/mm < bottom:
            raise HTTPException(422, '本单内容超出客户模板区域，请核对字段或选择A3；未裁切文字或缩小条码')
        p.drawOn(c, x*mm, (top-used/mm)*mm)
        return used/mm

    for r, record in enumerate(plan.records):
        if {p.face for p in record.panels} != {'front', 'side'}:
            raise HTTPException(422, f'第{r+1}组缺少正唛或侧唛，请核对原稿；未用旧稿补造')
        left, right, top, bottom = 9*scale, width-2*scale, height-40*scale, 21*scale
        split = left+(right-left)*cfg['front_percent']/100
        c.setStrokeColorRGB(.93,.2,.14); c.setLineWidth(.7)
        c.rect(left*mm, 1.5*scale*mm, (right-left)*mm, (top-1.5*scale)*mm)
        for y in (top-21*scale, bottom): c.line(left*mm,y*mm,right*mm,y*mm)
        c.line(split*mm,1.5*scale*mm,split*mm,top*mm)
        fold=c.beginPath();fold.moveTo(left*mm,(top-21*scale)*mm);fold.lineTo((left-8*scale)*mm,(top-31*scale)*mm)
        fold.lineTo((left-8*scale)*mm,(bottom+10*scale)*mm);fold.lineTo(left*mm,bottom*mm);c.drawPath(fold)
        paragraph('客户箱唛 · 第'+str(r+1)+'组',left,height-7*scale,65*scale,15)
        paragraph('30≤箱宽≤40cm、箱高≥23cm：LOGO实际宽18cm。\n40<箱宽≤50cm、箱高≥33cm：LOGO实际宽25cm。\n箱宽>50cm、箱高≥42cm：LOGO实际宽32cm。\n箱宽小于30cm按确认比例；实际印刷尺寸须核实。',140*scale,height-7*scale,width-144*scale,9)
        for panel in sorted(record.panels, key=lambda p: p.face != 'front'):
            face = panel.face
            x1,x2 = (left,split) if face=='front' else (split,right)
            opts = dict(font_pt=cfg[face+'_font_pt'],align='left',logo_visible=panel.logo,
                        symbols=[s.kind for s in panel.symbols],barcode_position='right')
            for change in order_changes:
                if change['record']==r and change['face']==face:
                    opts.update({k:v for k,v in change.items() if k not in {'record','face','note_ids','summary'}})
            for override in graphic_overrides:
                if override['record']==r and override['face']==face:
                    opts.update(logo_visible=override['logo'],symbols=override['symbols'])
            paragraph(('正唛' if face=='front' else '侧唛')+f' × {panel.copies}',x1,top-5*scale,x2-x1,20,align='center')
            if opts['logo_visible']:
                c.drawImage(ImageReader(io.BytesIO(logo)), ((x1+x2)/2-22.5*scale)*mm,
                            (top-47*scale)*mm,45*scale*mm,21*scale*mm,preserveAspectRatio=True,mask='auto')
            text_x = x1+(30 if face=='front' else 40)*scale
            text_w = x2-text_x-9*scale
            cursor = top-(55 if face=='front' else 76)*scale
            before = [f for f in panel.fields if f.position!='after_barcode']
            after = [f for f in panel.fields if f.position=='after_barcode']
            bar_h = sum(b.height_mm+9 for b in panel.barcodes)
            min_bottom = bottom+max(26*scale,bar_h+15*scale)
            for field in before:
                label = field.label.value if field.label else ''
                value = flow.field_value(field.parts)
                text = (label+' ' if label else '')+value
                cursor -= paragraph(text,text_x,cursor,text_w,opts['font_pt'] if field.role!='emphasis' else min(20,opts['font_pt']+4),align=opts['align'],bottom=min_bottom)+.8*scale
            barcode_top = min(cursor-2*scale, bottom+bar_h+13*scale)
            for bar in panel.barcodes:
                drawing = flow._barcode(bar)
                barcode_right=x2-(38 if opts['symbols'] else 8)*scale
                available = barcode_right-x1-8*scale
                if drawing.width/mm > available:
                    raise HTTPException(422,'条码及静区超出客户模板宽度，请使用A3或另行确认版式；未缩小条码')
                bx = x1+8*scale if opts['barcode_position']=='left' else barcode_right-drawing.width/mm
                by = barcode_top-bar.height_mm
                if by<bottom+12*scale: raise HTTPException(422,'条码超出客户模板高度，请核对尺寸或使用A3')
                drawing.drawOn(c,bx*mm,by*mm)
                if bar.frame=='box' or cfg.get('barcode_frame',True):
                    c.setStrokeColorRGB(0,0,0);c.setLineWidth(2);c.rect(bx*mm-1,by*mm-1,drawing.width+2,bar.height_mm*mm+2)
                paragraph(bar.source.value,bx,by-1,drawing.width/mm,8,align='center',bottom=bottom+4*scale)
                barcode_top=by-9
            for index,kind in enumerate(opts['symbols']):
                # Keep handling symbols away from the complete barcode and quiet zones.
                sx=x2-(24+index*24)*scale
                if panel.barcodes:
                    occupied = (bx, bx+drawing.width/mm)
                    if sx-3*scale < occupied[1] and sx+18*scale > occupied[0]:
                        warnings.append(f'第{r+1}组{face}：搬运标识与条码位置冲突，需确认更大版面。')
                        raise HTTPException(422,'搬运标识与条码位置冲突，请使用A3或调整本单条码位置')
                c.saveState();c.translate(sx*mm,(bottom+25*scale)*mm);c.scale(scale,scale)
                if kind=='this_side_up':
                    c.scale(mm,mm);c.setFillColorRGB(0,0,0)
                    for offset in (0,12):
                        path=c.beginPath();path.moveTo(offset,0);path.lineTo(offset+2,0);path.lineTo(offset+2,12)
                        path.lineTo(offset+5,12);path.lineTo(offset+1,17);path.lineTo(offset-3,12);path.lineTo(offset,12);path.close();c.drawPath(path,stroke=0,fill=1)
                    c.setStrokeColorRGB(0,0,0);c.setLineWidth(.8);c.line(-3,-1,17,-1)
                else:flow._symbol(c,kind,0,0)
                c.restoreState()
                if kind=='this_side_up':paragraph('THIS WAY UP',sx-4*scale,bottom+22*scale,25*scale,7,align='center')
            footer_top=bottom+7*scale
            for field in after:
                text=(field.label.value+' ' if field.label else '')+flow.field_value(field.parts)
                footer_top-=paragraph(text,x1+8*scale,footer_top,x2-x1-16*scale,8,bottom=bottom+1*scale)
        paragraph('审阅稿 · 本单修改不覆盖客户模板 · 实际印刷尺寸与扫码需核实',left,15*scale,right-left,8,bottom=2*scale)
        c.showPage()
    c.save()
    if not include_sources:
        return output.getvalue(),len(plan.records),warnings
    # Reuse the source ledger while keeping its flow-layout pages out of this PDF.
    from pypdf import PdfReader, PdfWriter
    full,count,extra=flow.render(plan,source,logo,include_sources=True,sources_only=True,note_origin='vision')
    writer=PdfWriter();writer.append(PdfReader(io.BytesIO(output.getvalue())))
    writer.append(PdfReader(io.BytesIO(full)))
    dest=io.BytesIO();writer.write(dest)
    return dest.getvalue(),len(writer.pages),list(dict.fromkeys(warnings+extra))
