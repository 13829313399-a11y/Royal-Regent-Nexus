"""ZURU layouts: current worksheet values and explicitly frozen static artwork."""
import io
import re
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from xml.sax.saxutils import escape

from fastapi import HTTPException
from openpyxl.utils.cell import coordinate_to_tuple
from reportlab.lib.pagesizes import A4, A3, landscape
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph

from app.services.carton_mark import extract_excel_document_items, CartonMarkDocumentError
from app.services.carton_supplier_mark_layout import validate_reference, crop_reference

FIELDS = {
    "item": r"item(?:\s*no\.?)?",
    "product": r"description|product description|item description",
    "article": r"article number|zumiez item no\.?",
    "quantity": r"article\s*-\s*quantity|qty/ctn|quantity",
    "carton_total": r"carton number|ctn qty",
    "gtin": r"barcode(?: number)?",
    "dimensions": r"measurement|carton size\(cm\)",
    "gross_weight": r"gross weight|carton gross weight",
    "net_weight": r"carton net weight",
    "brand": r"brand",
    "cbm": r"carton cbm",
    "invoice": r"pi\s*no\.?",
    "customer_po": r"po number",
    "country": r"country of origin",
}
TITLES = dict(item="货号", product="品名", article="客户货号", quantity="每箱数量", carton_total="总箱数",
    gtin="条码号码", dimensions="长宽高", gross_weight="每箱毛重", net_weight="每箱净重",
    brand="品牌", cbm="每箱体积", invoice="发票号", customer_po="客户 PO", country="产地")
FORMULA_ERRORS = ("#N/A", "#REF!", "#VALUE!", "#DIV/0!", "#NAME?", "#NUM!", "#NULL!", "#SPILL!", "#CALC!")


def identify(text):
    for key, pattern in FIELDS.items():
        match = re.fullmatch(r"\s*(?:" + pattern + r")\s*(?::|：|$)\s*(.*)", text, re.I)
        if match:
            return key, match[1].strip()
    return None, ""


def source_cells(filename, content):
    try:
        extracted = extract_excel_document_items(filename, content)
    except CartonMarkDocumentError as exc:
        raise HTTPException(422, str(exc)) from exc
    if extracted.reviews:
        raise HTTPException(422, "Excel 有公式未保存计算结果，请重新计算并保存后生成")
    sheets = defaultdict(dict)
    for cell in extracted.items:
        sheet, coordinate = cell.location.rsplit("!", 1)
        sheets[sheet][coordinate_to_tuple(coordinate)] = cell.text
    return sheets


def extract_archibrand(sheet, cells):
    """Pair explicitly labelled faces; never merge unrelated repeated SKUs."""
    starts = sorted(row for (row, _), text in cells.items() if text.strip().upper() == "FRONT MARK:")
    records = []
    for index, start in enumerate(starts):
        end = starts[index+1] if index+1 < len(starts) else max(row for row, _ in cells)+1
        block = {(r,c):t for (r,c),t in cells.items() if start <= r < end}
        if not any(t.strip().upper() == "SIDE MARK:" for t in block.values()):
            raise HTTPException(422, f"{sheet} 第{start}行缺少明确的正侧唛配对")
        found = defaultdict(list)
        for (row,col), content in block.items():
            if content.strip().upper().startswith("ARCHIBRAND,"):
                found["recipient"].append(content.strip())
            if content.strip().upper() == "MADE IN CHINA":
                found["country"].append("CHINA")
            for key, pattern in (("item",r"ITEM NO\.?"),("product",r"ITEM DESCRIPTION"),
                    ("quantity",r"CTN QTY"),("carton_total",r"CTN NUMBER")):
                match = re.fullmatch(r"\s*"+pattern+r"\s*:\s*(.*?)\s*",content,re.I)
                if not match:
                    continue
                value = match[1].strip().strip("/").strip()
                for other_col, nearby in sorted((c,t) for (r,c),t in block.items() if r==row and col<c<=col+10):
                    if identify(nearby)[0]:
                        break
                    value += (" " if value else "")+nearby
                if value:
                    found[key].append(value.strip())
        fields = {}
        for key, candidates in found.items():
            values = list(dict.fromkeys(candidates))
            if len(values)!=1:
                raise HTTPException(422,f"{sheet} 第{start}行的{TITLES.get(key,key)}正侧唛内容冲突，请核实原稿")
            fields[key]=values[0]
        if any(value.startswith(FORMULA_ERRORS) for value in fields.values()):
            raise HTTPException(422,f"{sheet} 第{start}行箱唛有公式错误，请核实并保存原稿")
        if not fields.get("item") or not fields.get("product") or not fields.get("recipient"):
            raise HTTPException(422,f"{sheet} 第{start}行缺少货号、品名或收货方")
        records.append(dict(sheet=sheet,row=start,profile="archibrand",fields=fields))
    return records


def extract_anko(sheet, cells):
    main = {r:t for (r,c),t in cells.items() if c==1}
    side = {r:t for (r,c),t in cells.items() if c==2}
    if not any("OUTER CARTON MAIN MARK" in t.upper() for t in main.values()) or not any("OUTER CARTON SIDE MARK" in t.upper() for t in side.values()):
        raise HTTPException(422,"ANKO 原稿缺少正侧唛列标题，请核实版式")
    patterns = dict(item=r"ITEM#\s*(.+)", department=r"Dept No\.\s*(.+)",
        customer_po=r"Order No\.\s*(.+)", keycode=r"\*Keycode\s+(.+)", product=r"Description\s+(.+)",
        issue_pack=r"Qty Issue Pack\s+(.+)", quantity=r"Qty Shipper Pack\s+(.+)",
        carton_total=r"Carton No\.\s*(?:of\s+)?(.+)")
    fields = {}
    for key,pattern in patterns.items():
        candidates = [m[1].strip() for t in main.values() if (m:=re.fullmatch(pattern,t.strip(),re.I))]
        if len(candidates)!=1:
            raise HTTPException(422,f"ANKO 原稿的{TITLES.get(key,key)}缺少或不唯一，请核实")
        fields[key]=candidates[0]
    countries=[t.strip() for t in main.values() if re.fullmatch(r"NZ|AU",t.strip(),re.I)]
    if len(countries)!=1:
        raise HTTPException(422,"ANKO 原稿目的地缺少或不唯一，请核实")
    fields["destination"]=countries[0]
    for key,pattern in (("gross_weight",r"GRS\.WT\s+(.+)"),("dimensions",r"D:\s*(.+)")):
        candidates=[m[1].strip() for t in side.values() if (m:=re.fullmatch(pattern,t.strip(),re.I))]
        if len(candidates)!=1:
            raise HTTPException(422,f"ANKO 侧唛的{TITLES[key]}缺少或不唯一，请核实")
        fields[key]=candidates[0]
    if not any(t.strip().casefold()=="made in china" for t in side.values()):
        raise HTTPException(422,"ANKO 侧唛缺少明确产地，请核实")
    fields["country"]="CHINA"
    if any(value.startswith(FORMULA_ERRORS) for value in fields.values()):
        raise HTTPException(422,"ANKO 原稿有公式错误，请核实并保存")
    # These originals include conditional handling logos, whose artwork was
    # not supplied. Do not silently issue a seemingly complete heavier case.
    number=r"\d+(?:\.\d+)?"
    dims=re.fullmatch(r"("+number+r")\s*[x×]\s*("+number+r")\s*[x×]\s*("+number+r")\s*CMS?",fields["dimensions"],re.I)
    weight=re.fullmatch(r"("+number+r")\s*KGS?",fields["gross_weight"],re.I)
    if not dims or not weight or any(Decimal(v)<=0 for v in dims.groups()) or Decimal(weight[1])<0:
        raise HTTPException(422,"ANKO 尺寸或毛重单位无法确认，请核实原稿")
    volume=Decimal(1)
    for number in dims.groups():volume*=Decimal(number)/100
    if volume>Decimal("0.13") or Decimal(weight[1])>Decimal("9.5"):
        raise HTTPException(422,"ANKO 此箱体积或毛重涉及客户搬运标识，请补齐已确认图案并配置版式后生成")
    return [dict(sheet=sheet,row=2,profile="anko",fields=fields)]


def extract_zuru(filename, content):
    sheets = source_cells(filename, content)
    from app.services.carton_mark_hyvee import extract_hyvee
    hyvee=extract_hyvee(sheets)
    if hyvee is not None:return hyvee
    records = []
    for sheet, cells in sheets.items():
        if any(t.strip().upper().startswith("ARCHIBRAND,") for t in cells.values()):
            records.extend(extract_archibrand(sheet,cells));continue
        if any(t.strip().upper()=="ANKO" for t in cells.values()):
            records.extend(extract_anko(sheet,cells));continue
        # Shipping-mark blocks have colon labels; raw data tables have column
        # headings and are not enrolled as additional printing records.
        starts = sorted(row for (row, _), text in cells.items() if identify(text)[0] == "item" and ":" in text)
        is_zumiez = any("ZUMIEZ INC" in text.upper() for text in cells.values())
        if is_zumiez:
            starts = [min(row for (row, _), text in cells.items() if "ZUMIEZ INC" in text.upper())]
        for index, start in enumerate(starts):
            end = starts[index + 1] if index + 1 < len(starts) else max(row for row, _ in cells) + 1
            block = {(row, col): text for (row, col), text in cells.items() if start <= row < end}
            found = defaultdict(list)
            for (row, col), text in block.items():
                key, value = identify(text)
                if not key:
                    continue
                if not value:
                    for other_col, nearby in sorted((c, t) for (r, c), t in block.items() if r == row and col < c <= col + 10):
                        if identify(nearby)[0]:
                            break
                        value += (" " if value else "") + nearby
                if (key in {"quantity", "carton_total", "dimensions", "gross_weight", "net_weight", "cbm"}
                        and not re.search(r"\d", value) and not value.startswith(FORMULA_ERRORS)):
                    value = ""
                if value:
                    found[key].append(value.strip())
            fields = {}
            for key, candidates in found.items():
                candidates = list(dict.fromkeys(candidates))
                if len(candidates) != 1:
                    raise HTTPException(422, f"{sheet} 第{start}行的{TITLES.get(key,key)}正侧唛内容冲突，请核实原稿")
                fields[key] = candidates[0]
            # Customer workbooks preallocate unused VLOOKUP blocks. Only the
            # pair of empty-lookup ITEM/description results marks such a block.
            if fields.get("item") == "#N/A" and fields.get("product") == "#N/A":
                continue
            if any(value.startswith(FORMULA_ERRORS) for value in fields.values()):
                raise HTTPException(422, f"{sheet} 第{start}行箱唛有公式错误，请核实并保存原稿")
            if is_zumiez:
                profile = "zumiez"
                fields["item"] = fields.get("article", "")
            elif fields.get("article") and any("FTC" == text.upper() for text in block.values()) and any("Farmers" == text for text in cells.values()):
                profile = "ftc"
                header_row = next((row for (row, _), text in block.items() if "Dept #" in text), None)
                if header_row is not None:
                    values = [text for (row, col), text in sorted(block.items()) if row == header_row + 1 and col < 8]
                    fields["department_order"] = " ".join(values)
            elif fields.get("brand") and "invoice" in fields:
                profile = "esal"
            else:
                continue
            if not fields.get("item") or not fields.get("product"):
                raise HTTPException(422, f"{sheet} 第{start}行缺少货号或品名")
            records.append(dict(sheet=sheet, row=start, profile=profile, fields=fields))
    if not 1 <= len(records) <= 50:
        raise HTTPException(422, "未识别支持的 ZURU 箱唛块（FTC、Zumiez、ESAL、ARCHIBRAND、ANKO、Hy-Vee），请核实客户资料版式")
    return records


def prepare_records(original):
    records = extract_zuru(original["excel_file_name"], original["excel_bytes"])
    item = str(original.get("source_item") or original["item_no"]).strip().casefold()
    matching = [record for record in records if record["fields"]["item"].strip().casefold() == item]
    warnings = []
    if matching:
        if len(matching) != 1:
            raise HTTPException(422, "Excel 同一货号有多个箱唛块，请提供已确认的单一版本")
        chosen = matching
        if original.get("source_item") and original["source_item"].casefold() != original["item_no"].casefold():
            warnings.append(f"按明确指定的 Excel 货号 {original['source_item']} 生成；关联订单 ITEM 为 {original['item_no']}，请审核对应关系")
    elif original.get("source_item"):
        raise HTTPException(422, "指定的 Excel 箱唛货号不存在或不唯一，请核实原稿")
    elif len(records) == 1 and records[0]["profile"] == "zumiez":
        # This customer's XLS contains only its retail article number. The
        # internal ITEM is supplied by the already-authorized issued order.
        chosen = records
        warnings.append("Excel 仅有 Zumiez 客户货号，页头内部 ITEM 使用关联采购订单，请核实")
    else:
        raise HTTPException(422, "Excel 箱唛块没有匹配所选订单 ITEM，请选择正确货号")
    if len(records) > len(chosen):
        warnings.append(f"仅生成所选订单 ITEM，已跳过 {len(records) - 1} 个其他货号箱唛块")
    fields = chosen[0]["fields"]
    if chosen[0]["profile"]=="hyvee":
        if fields["factory_po"].casefold()!=original["contract_no"].strip().casefold():
            raise HTTPException(422,"Hy-Vee 所选货号的 Factory PO 与关联订单合同不一致，请核实")
        warnings.append("Hy-Vee 使用外箱数据表重新排版；示例区及内嵌旧条码图片不作数据来源，请审核")
        warnings.append("Hy-Vee 外箱 ITF-14、单品 UPC-A 已按数据表重新生成并校验号码，请用实际打印件扫码验证")
    for key, value in original.get("supplements", {}).items():
        if fields.get(key) and fields[key] != value.strip():
            raise HTTPException(422, f"Excel 已填写{TITLES.get(key,key)}，本单补齐不能覆盖原稿；请先核实资料版本")
        if not fields.get(key):
            fields[key] = value.strip()
            warnings.append(f"{TITLES.get(key,key)}使用本次明确补齐的内容，请审核")
    for key, value in original.get("order_fields", {}).items():
        if value and not fields.get(key):
            fields[key] = value
            warnings.append(f"{TITLES.get(key,key)}从关联采购单的外箱明细补齐，请核实")
    required = dict(ftc=("article", "quantity", "carton_total", "dimensions", "gross_weight", "gtin"),
        zumiez=("article", "quantity", "carton_total", "customer_po", "country"),
        archibrand=("quantity", "carton_total", "country"), anko=("quantity", "carton_total", "dimensions", "gross_weight"),
        hyvee=("quantity","gtin","customer_po","country"),
        esal=("quantity", "brand", "dimensions", "net_weight", "gross_weight", "gtin", "cbm", "invoice"))
    missing = [key for key in required[chosen[0]["profile"]] if not fields.get(key)]
    if missing:
        warnings.append("原稿缺少" + "、".join(TITLES[key] for key in missing) + "，审阅稿显示待补")
    if chosen[0]["profile"]=="anko":
        warnings.append("ANKO 正唛保留 SSCC LABEL 4×4inch 预留示意；生产需离箱边至少2cm，待实际印刷尺寸校验")
    return chosen[0], warnings


def render_zuru(original, config):
    reference = original["layout"]["reference_bytes"]
    validate_reference(reference, config)
    record, warnings = prepare_records(original)
    fields, profile = record["fields"], record["profile"]
    artwork = {}
    for key in ("logo", "stamp", "front_artwork", "side_artwork", "origin_artwork"):
        region = getattr(config, key + "_region")
        if region:
            artwork[key] = crop_reference(reference, config.reference_page, region.model_dump())
    if "logo" not in artwork:
        raise HTTPException(422, "ZURU 模板需要从已确认历史 PDF 选取 ZURU LOGO")
    if profile == "esal" and any(key not in artwork for key in ("front_artwork", "side_artwork", "origin_artwork")):
        raise HTTPException(422, "ESAL 版式须选取正唛固定素材、侧唛图案和阿拉伯产地文字，再保存客户模板")
    font = config.font
    if font.startswith("ArialNarrow"):
        path = Path("C:/Windows/Fonts/ARIALNB.TTF" if font.endswith("Bold") else "C:/Windows/Fonts/ARIALN.TTF")
        if not path.exists():
            raise HTTPException(422, "服务器未安装客户选定的 Arial Narrow 字体，请安装或调整客户模板")
        if font not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(font, str(path)))
    cjk = "STSong-Light"
    cjk_path = Path("C:/Windows/Fonts/simhei.ttf")
    if cjk_path.exists():
        cjk = "MarkCJK"
        if cjk not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(cjk, str(cjk_path)))
    else:
        pdfmetrics.registerFont(UnicodeCIDFont(cjk))
    size = A3 if config.paper == "A3" else A4
    if config.mode == "front_side":
        size = landscape(size)
    width, height = size
    output = io.BytesIO(); canvas = Canvas(output, pagesize=size, pageCompression=1)
    canvas.setTitle(f"{original['contract_no']} {original['item_no']} - ZURU {profile}")

    def text(value, x, top, w, h, size=11, centered=False):
        value = value or "待补"
        for fontsize in range(round(size), 6, -1):
            formatted = re.sub(r"[^\x00-\x7f]+", lambda m: f'<font name="{cjk}">{m[0]}</font>', escape(value)).replace("\n", "<br/>")
            paragraph = Paragraph(formatted, ParagraphStyle("zuru", fontName=font, fontSize=fontsize,
                leading=fontsize * 1.2, alignment=1 if centered else 0))
            _, actual = paragraph.wrap(w, h)
            if actual <= h:
                paragraph.drawOn(canvas, x, top - actual); return
        raise HTTPException(422, "ZURU 内容过长，无法完整放入模板，请增大纸张或调整版式")

    def picture(key, x, top, w, h):
        if key in artwork:
            canvas.drawImage(ImageReader(io.BytesIO(artwork[key])), x, top-h, w, h, preserveAspectRatio=True, anchor="c", mask="auto")

    def value(key, unit=""):
        content = fields.get(key, "")
        if not content:
            return "待补"
        return content + (" " + unit if unit and not re.search(r"\b" + re.escape(unit) + r"\b", content, re.I) else "")

    def triangle(x, top, w):
        h = w * .93; path = canvas.beginPath()
        path.moveTo(x+w/2, top); path.lineTo(x, top-h); path.lineTo(x+w, top-h); path.close()
        canvas.drawPath(path)
        for fraction in (.35, .65):
            canvas.line(x+w*(1-fraction)/2, top-h*fraction, x+w*(1+fraction)/2, top-h*fraction)
        text("FTC", x, top-h*.4, w, h*.21, size=12, centered=True)
        text("New Zealand", x, top-h*.74, w, h*.23, size=9, centered=True)

    def panel(x, top, w, h, side):
        canvas.saveState(); canvas.setStrokeColorRGB(.94,.23,.14) if config.frame_style == "original_red" else canvas.setStrokeColorRGB(0,0,0)
        canvas.setLineWidth(1)
        canvas.rect(x,top-h,w,h)
        header_y,footer_y = top-21*mm,top-h+20*mm
        canvas.line(x,header_y,x+w,header_y); canvas.line(x,footer_y,x+w,footer_y)
        if not side and config.frame_style == "original_red":
            fold=canvas.beginPath();fold.moveTo(x,header_y);fold.lineTo(x-8*mm,header_y-10*mm)
            fold.lineTo(x-8*mm,footer_y+10*mm);fold.lineTo(x,footer_y);canvas.drawPath(fold)
        canvas.restoreState(); canvas.setLineWidth(.8)
        text(("侧唛" if side else "正唛")+f" X {config.side_copies if side else config.front_copies}",x+5*mm,top-7*mm,w-10*mm,9*mm,13,True)
        picture("logo",x+5*mm,top-26*mm,w-10*mm,19*mm)
        left=x+w*.22 if not side else x+w*.18
        usable=x+w-5*mm-left
        if profile == "ftc":
            triangle(left,top-52*mm,min(28*mm,usable*.4))
            lines = [("ARTICLE Number",value("article")),("ARTICLE - Quantity",value("quantity","PCS"))]
            if side:
                lines += [("Gross Weight",value("gross_weight","KGS")),("Measurement",value("dimensions")),("Barcode Number",value("gtin"))]
            else:
                text("FTC       / Dept # / LOI #       / Order #",left,top-86*mm,usable,6*mm,config.font_size)
                text(fields.get("department_order", "待补"),left,top-92*mm,usable,6*mm,config.font_size)
                lines += [("Carton number",value("carton_total")),("Description",value("product"))]
            y=top-(86 if side else 98)*mm
            for label, content in lines:
                text(label+":  "+content,left,y,usable,(18 if label=="Description" else 6.5)*mm,config.font_size);y-=7*mm
        elif profile == "zumiez":
            lines=["ZUMIEZ INC.","PO NUMBER: "+value("customer_po"),"ZUMIEZ ITEM NO.: "+value("article"),
                "ITEM DESCRIPTION: "+value("product"),"QUANTITY: "+value("quantity","PCS"),
                "CTN QTY:       / "+value("carton_total","CTNS"),"COUNTRY OF ORIGIN: "+value("country")]
            for index, line in enumerate(lines):
                text(line,left,top-(69+7*index)*mm,usable,6.5*mm,config.font_size)
        elif profile == "archibrand":
            y=top-69*mm
            text(fields["recipient"],left,y,usable,7*mm,config.font_size);y-=8*mm
            text("ITEM NO.: "+fields["item"],left,y,usable,7*mm,config.font_size);y-=8*mm
            text("ITEM DESCRIPTION: "+fields["product"],left,y,usable,24*mm,config.font_size);y-=25*mm
            text("CTN QTY: "+value("quantity"),left,y,usable,7*mm,config.font_size);y-=8*mm
            text("CTN NUMBER:       / "+value("carton_total"),left,y,usable,7*mm,config.font_size);y-=8*mm
            if not side:
                text("MADE IN "+value("country"),left,y,usable,7*mm,config.font_size)
        elif profile == "anko":
            if side:
                for index,line in enumerate(("Made in China","GRS.WT  "+value("gross_weight"),"D:  "+value("dimensions"))):
                    text(line,left,top-(80+8*index)*mm,usable,7.5*mm,config.font_size)
            else:
                # The review page is deliberately not a production-scale
                # drawing: name the real required size without claiming it.
                box_w=min(26*mm,w*.2);box_x=x+w-8*mm-box_w;box_top=top-52*mm
                canvas.saveState();canvas.setStrokeColorRGB(.94,.23,.14)
                canvas.rect(box_x,box_top-box_w,box_w,box_w);canvas.restoreState()
                text("SSCC LABEL\n4 x 4 inch",box_x+1*mm,box_top-5*mm,box_w-2*mm,16*mm,8,True)
                text("预留示意；离箱边≥2cm",box_x-7*mm,box_top-box_w-2*mm,box_w+7*mm,9*mm,7)
                left=x+w*.12;usable=x+w-5*mm-left;y=top-55*mm
                for line in ("ANKO",fields["destination"],"Dept No. "+fields["department"],
                        "Order No. "+fields["customer_po"],"*Keycode "+fields["keycode"]):
                    text(line,left,y,usable*.65,6.5*mm,config.font_size);y-=7*mm
                text("Description "+value("product"),left,y,usable,14*mm,config.font_size);y-=15*mm
                for line in ("Qty Issue Pack "+fields["issue_pack"],"Qty Shipper Pack "+value("quantity"),
                        "Carton No.       of "+value("carton_total")):
                    text(line,left,y,usable,7*mm,config.font_size);y-=8*mm
        elif profile == "hyvee":
            if side:
                text("MADE IN "+fields["country"],left,top-115*mm,usable,8*mm,config.font_size)
            else:
                from app.services.carton_mark_hyvee import draw_hyvee
                draw_hyvee(canvas,fields,x,top,w,h,text,config.font_size)
        elif not side:
            picture("front_artwork",x+8*mm,top-52*mm,w-16*mm,h-74*mm)
        else:
            # Variable rows remain real PDF text. Only approved fixed graphics
            # and Arabic artwork are cropped from the historical reference.
            left=x+w*.15; usable=x+w-5*mm-left; label_w=usable*.42
            entries=[("Item No",fields["item"]),("Product Description",value("product")),("Barcode",value("gtin")),
                ("Brand",value("brand")),("Qty/Ctn",value("quantity","PCS")),("Carton Net Weight",value("net_weight","KGS")),
                ("Carton Gross Weight",value("gross_weight","KGS")),("Carton Size(cm)",value("dimensions")),
                ("Carton CBM",value("cbm","CBM")),("PI No.",value("invoice"))]
            y=top-51*mm
            for key, content in entries:
                row_h=17*mm if key=="Product Description" else 4.6*mm
                text(key+":",left,y,label_w,row_h,size=min(config.font_size,10))
                text(content,left+label_w,y,usable-label_w,row_h,size=min(config.font_size,10))
                y-=row_h
            text("Made in China",left,y,usable*.4,5*mm,10)
            picture("origin_artwork",left+usable*.55,y,usable*.45,5*mm)
            picture("side_artwork",x+10*mm,y-7*mm,w-20*mm,max(10*mm,y-7*mm-footer_y-2*mm))
        if not side:
            picture("stamp",x+5*mm,footer_y-1*mm,w-10*mm,18*mm)

    pages=[False,True] if config.mode=="separate_pages" else [False]
    for side in pages:
        text(original["contract_no"]+"   "+original["item_no"],10*mm,height-8*mm,width-20*mm,11*mm,16)
        if config.instructions:
            text(config.instructions,width*.46,height-5*mm,width*.54-10*mm,27*mm,8)
        top=height-(38 if config.instructions else 25)*mm
        h=top-13*mm
        if config.mode=="front_side":
            usable=width-20*mm;front=usable*config.front_percent/100
            panel(10*mm,top,front,h,False);panel(10*mm+front,top,usable-front,h,True)
        else:
            panel(10*mm,top,width-20*mm,h,side)
        text(f"{original['layout']['name']} V{original['layout']['version']} / {profile} / 待核对、审核",10*mm,8*mm,width-20*mm,5*mm,7)
        canvas.showPage()
    canvas.save(); content=output.getvalue()
    if len(content)>20*1024*1024:
        raise HTTPException(413,"生成 PDF 超过20 MB，请缩小客户素材")
    return content,len(pages),warnings
