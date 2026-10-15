"""Hy-Vee data-table profile. Embedded example text/barcodes are never data."""
import re

from fastapi import HTTPException
from reportlab.lib.units import mm
from reportlab.graphics.barcode import createBarcodeDrawing

HEADERS = {
    "hy-vee po#": "customer_po", "factory po": "factory_po", "unit upc": "unit_upc",
    "case upc (ucn)": "gtin", "customer item no.": "article", "amount of inner cases": "inner_count",
    "inner case pack": "inner_pack", "item no.": "item", "vendor code": "vendor_item",
    "product description": "product", "master case pack": "quantity",
}


def normalize(value):
    return re.sub(r"\s+", " ", value.strip().rstrip(":：")).casefold()


def validate_gtin(value, length):
    if not re.fullmatch(r"[0-9]{"+str(length)+r"}", value):
        raise HTTPException(422, f"Hy-Vee 条码必须保留完整 {length} 位数字，请核实数据表")
    total=sum(int(n)*(3 if i%2==0 else 1) for i,n in enumerate(reversed(value[:-1])))
    if int(value[-1]) != (-total)%10:
        raise HTTPException(422, "Hy-Vee 条码校验位错误，请核实数据表；不会自动改写号码")


def extract_hyvee(sheets):
    tables=[]
    for sheet,cells in sheets.items():
        for row in sorted({r for r,_ in cells}):
            labels=[(HEADERS[normalize(t)],c) for (r,c),t in cells.items() if r==row and normalize(t) in HEADERS]
            mapping=dict(labels)
            if set(HEADERS.values()) <= set(mapping):
                if len(labels)!=len(mapping):raise HTTPException(422,"Hy-Vee 数据表列标题重复，请核实明确的单一来源")
                tables.append((sheet,row,cells,mapping))
    if not tables:return None
    if len(tables)!=1:raise HTTPException(422,"Hy-Vee 有多个外箱数据表，请提供单一已确认版本")
    sheet,start,cells,mapping=tables[0]
    vendors={cells2.get((r,c+1),"") for cells2 in sheets.values() for (r,c),t in cells2.items() if normalize(t)=="vendor"}
    vendors.discard("")
    if len(vendors)!=1:raise HTTPException(422,"Hy-Vee 供应商名称缺少或不唯一，请核实")
    countries={match[1].strip().upper() for cells2 in sheets.values() for t in cells2.values()
        if (match:=re.fullmatch(r"MADE IN\s+(.+)",t.strip(),re.I))}
    if len(countries)!=1 or any(t.startswith("#") for t in countries):
        raise HTTPException(422,"Hy-Vee 原稿产地缺少或不唯一，请核实")
    records=[]
    for row in sorted({r for r,_ in cells if r>start}):
        # A real source row has the factory order and complete SKU. The old
        # example panels to the right/below lack those data-table identities.
        item=cells.get((row,mapping["item"]),"");po=cells.get((row,mapping["factory_po"]),"")
        if not item and not po:continue
        fields={key:cells.get((row,col),"").strip() for key,col in mapping.items()}
        if any(not value for value in fields.values()) or any(value.startswith("#") for value in fields.values()):
            raise HTTPException(422,f"{sheet} 第{row}行数据缺少或有公式错误，请核实并保存")
        validate_gtin(fields["gtin"],14);validate_gtin(fields["unit_upc"],12)
        for key in ("quantity","inner_pack","inner_count"):
            if fields[key].upper()=="N/A" and key!="quantity":continue
            if not re.fullmatch(r"[0-9]+",fields[key]) or int(fields[key])<=0:
                raise HTTPException(422,f"Hy-Vee 第{row}行装箱数须为正整数，内盒不适用时请明确填写 N/A")
        missing_inner=[fields[key].upper()=="N/A" for key in ("inner_pack","inner_count")]
        if any(missing_inner) and not all(missing_inner):
            raise HTTPException(422,f"Hy-Vee 第{row}行内盒数量和装箱数须同时填写或同时 N/A")
        if not any(missing_inner) and int(fields["inner_pack"])*int(fields["inner_count"])!=int(fields["quantity"]):
            raise HTTPException(422,f"Hy-Vee 第{row}行内盒数量×内盒装箱数与外箱装箱数不一致，请核实")
        fields.update(vendor=next(iter(vendors)),country=next(iter(countries)))
        records.append(dict(sheet=sheet,row=row,profile="hyvee",fields=fields))
    if not 1<=len(records)<=50:raise HTTPException(422,"Hy-Vee 外箱数据须有1至50条有效商品")
    return records


def draw_hyvee(canvas,fields,x,top,w,h,text,font_size):
    if h < 210*mm:
        raise HTTPException(422,"Hy-Vee 包含外箱及单品两种条码，正侧唛并排请用 A3，或选择 A4 分别两页")
    left=x+w*.14;usable=x+w-8*mm-left
    def line(content,y,height=6*mm):text(content,left,top-y*mm,usable,height,font_size)
    line("Vendor: "+fields["vendor"],52)
    line("Hy-Vee PO#: "+fields["customer_po"],58)
    line("Case UPC (UCN):",64)

    # Explicit quiet zones, full bearer frame, validated source check digit.
    # A3 here remains a review page; actual production surface is separate.
    narrow=.508*mm;bearer=4.83*mm;bar_h=31.75*mm
    drawing=createBarcodeDrawing("I2of5",value=fields["gtin"],checksum=False,bearers=0,
        ratio=2.5,barWidth=narrow,barHeight=bar_h,quiet=True,lquiet=10*narrow,rquiet=10*narrow,humanReadable=False)
    full_w=drawing.width+2*bearer
    if full_w>usable:raise HTTPException(422,"Hy-Vee 条码区域太窄，请增大纸张或调整正侧唛占比；不会压缩条码")
    outer_x=left+(usable-full_w)/2;outer_top=top-71*mm;bottom=outer_top-bar_h-2*bearer
    canvas.saveState()
    canvas.rect(outer_x,bottom,full_w,bearer,fill=1,stroke=0)
    canvas.rect(outer_x,outer_top-bearer,full_w,bearer,fill=1,stroke=0)
    canvas.rect(outer_x,bottom,bearer,bar_h+2*bearer,fill=1,stroke=0)
    canvas.rect(outer_x+full_w-bearer,bottom,bearer,bar_h+2*bearer,fill=1,stroke=0)
    drawing.drawOn(canvas,outer_x+bearer,bottom+bearer)
    canvas.restoreState()
    text(fields["gtin"],left,bottom-1.5*mm,usable,5*mm,font_size,True)

    line("Vendor Code: "+fields["vendor_item"],122)
    line("Hy-Vee product code #: "+fields["article"],128)
    line("Product Description: "+fields["product"],134,14*mm)
    line("Master case pack: "+fields["quantity"]+" PC",150)
    inner=fields["inner_pack"]+(" PC" if fields["inner_pack"].upper()!="N/A" else "")
    line("Inner case pack: "+inner,156)
    line("Amount of Inner cases: "+fields["inner_count"],162)
    line("Unit UPC:",168)
    upc=createBarcodeDrawing("UPCA",value=fields["unit_upc"][:-1],barWidth=.33*mm,barHeight=22.85*mm,
        quiet=True,humanReadable=False)
    if upc.width>usable:raise HTTPException(422,"Hy-Vee 单品条码区域过窄，请调整模板")
    upc.drawOn(canvas,left+(usable-upc.width)/2,top-198*mm)
    text(fields["unit_upc"],left,top-199.5*mm,usable,5*mm,font_size,True)
