import copy
import io
import json

import pytest
from openpyxl import Workbook
from openpyxl.comments import Comment
from PIL import Image
from pypdf import PdfReader

from app.services import carton_mark_flexible as flexible
from app.services import carton_mark_ai_pilot as pilot


def workbook():
    b=Workbook();s=b.active;s.title="Unfamiliar"
    values={"B1":"Main mark (two sides)","F1":"Side mark (two sides)",
        "B3":"DEMO RECIPIENT","C3":"08","F3":"DEMO RECIPIENT","G3":"08",
        "B5":"SUBCATEGORY:","C5":"SYNTH-01","F5":"SUBCATEGORY:","G5":"SYNTH-01",
        "B6":"ORDER NUMBER:","C6":"PO-DEMO-0001","F6":"ORDER NUMBER:","G6":"PO-DEMO-0001",
        "B7":"ITEM NO:","C7":"000123","F7":"ITEM NO:","G7":"000123",
        "B8":"DESCRIPTION:","C8":"SYNTHETIC PRODUCT","F8":"DESCRIPTION:","G8":"SYNTHETIC PRODUCT",
        "B9":"QTY:","C9":"6","D9":"PCS/CTN","F9":"QTY:","G9":"6PCS/CTN",
        "B10":"CARTON NO:","C10":"OF","D10":"20","F10":"NW:","G10":"（印刷外箱净重） KGS",
        "B11":"BARCODE:","C11":"4006381333931","F11":"GW:","G11":"（印刷外箱总重） KGS",
        "C12":"DEMO ADDRESS 1 Example Road; demo@example.com","F12":"BARCODE:","G12":"4006381333931",
        "B13":"1. “08”两个字要比其他字体大","B14":"2. 纸箱要求5层和150克牛皮纸",
        "B15":"3. 毛净重按实际填写再印刷，确保条码扫描","B16":"4. 四面黑色ZURU LOGO，尺寸根据纸箱大小变化",
        "B17":"5. 增加易碎品朝上警告标识"}
    for key,value in values.items():s[key]=value
    s["C12"].comment=Comment("大写和小写字母高度均至少1.6mm","fixture")
    s["G12"].comment=Comment("条码印刷 minimum 60mm height x 80mm length","fixture")
    out=io.BytesIO();b.save(out);b.close();return out.getvalue()


def plan(source):
    by_coord={e.location.split("!")[1]:e for e in source["cells"]}
    noteids=[n.id for n in source["notes"]]
    def select(coord):
        e=by_coord[coord];return dict(source_id=e.id,value=e.text)
    def field(label,coords,role="normal"):
        return dict(label=select(label) if label else None,parts=[select(c) for c in coords],role=role)
    front=[field(None,["B3"]),field(None,["C3"],"emphasis")]+[
        field(f"B{r}",[f"C{r}"]) for r in (5,6,7,8)]
    front += [field("B9",["C9","D9"]),field("B10",["C10","D10"]),field(None,["C12"],"address")]
    side=[field(None,["F3"]),field(None,["G3"],"emphasis")]+[
        field(f"F{r}",[f"G{r}"]) for r in (5,6,7,8,9)]
    side += [field("F10",["G10"],"placeholder"),field("F11",["G11"],"placeholder")]
    panels=[]
    for face,fields,code in (("front",front,"C11"),("side",side,"G12")):
        panels.append(dict(face=face,copies=2,logo=True,fields=fields,
            barcodes=[dict(source=select(code),kind="EAN13",width_mm=80,height_mm=60,note_ids=noteids)],
            symbols=[dict(kind=k,note_ids=noteids) for k in ("fragile","this_side_up")]))
    used={v["source_id"] for p in panels for f in p["fields"] for v in ([f["label"]] if f["label"] else [])+f["parts"]}
    used.update(p["barcodes"][0]["source"]["source_id"] for p in panels)
    return dict(template_id="source-flow-v1",paper="A3",orientation="landscape",records=[dict(panels=panels)],
        notes=[dict(source_id=n.id,action="needs_confirmation") for n in source["notes"]],
        ignored_cells=[dict(source_id=e.id,reason="note" if e.location.split("!")[1].startswith("B1") and e.location.split("!")[1]!="B1" else "heading") for e in source["cells"] if e.id not in used])


def test_unfamiliar_labels_and_visible_cell_comments_are_sent_without_a_customer_name_gate():
    source=flexible.read("unknown.xlsx",workbook())
    assert any("000123"==e.text for e in source["cells"])
    assert any(n.location.endswith("G12/comment") for n in source["notes"])
    assert any("08" in n.text for n in source["notes"])
    assert not any(n.location.endswith(("G10","G11")) for n in source["notes"])
    limits=flexible.constraints(source)
    assert limits["width"]==80 and limits["height"]==60 and "08" in limits["emphasis"]
    flexible.validate(json.dumps(plan(source)),source)


def test_rejects_rewritten_numbers_wrong_faces_and_missing_required_print_symbols():
    source=flexible.read("unknown.xlsx",workbook())
    for change in ("number","leading_zero","barcode_face","emphasis","symbols"):
        result=copy.deepcopy(plan(source));p=result["records"][0]["panels"][0]
        if change=="number":p["fields"][3]["parts"][0]["value"]="FORGED"
        if change=="leading_zero":p["fields"][4]["parts"][0]["value"]="123"
        if change=="barcode_face":p["barcodes"][0]["source"]=result["records"][0]["panels"][1]["barcodes"][0]["source"]
        if change=="emphasis":p["fields"][1]["role"]="normal"
        if change=="symbols":
            for panel in result["records"][0]["panels"]:panel["symbols"]=[]
        with pytest.raises(pilot.PilotError):flexible.validate(json.dumps(result),source)


@pytest.mark.parametrize("mode",["missing","duplicate","unknown","malformed","bad_action","absent","cell_alias"])
def test_original_note_ledger_survives_incomplete_duplicate_or_malformed_model_receipts(mode):
    source=flexible.read("unknown.xlsx",workbook());result=plan(source)
    last=source["notes"][-1].id
    if mode=="missing":result["notes"].pop()
    if mode=="duplicate":result["notes"].append(dict(source_id=last,action="applied"))
    if mode=="unknown":result["notes"]=[dict(source_id="N999",action="applied")]
    if mode=="malformed":result["notes"]={"irrelevant":"not a receipt"}
    if mode=="bad_action":result["notes"][0]["action"]={"invalid":"metadata"}
    if mode=="absent":result.pop("notes")
    if mode=="cell_alias":
        note=source["notes"][0]
        result["notes"][0]["source_id"]=next(e.id for e in source["cells"] if e.location==note.location)
    valid=flexible.validate(json.dumps(result),source)
    assert [n.source_id for n in valid.notes]==[n.id for n in source["notes"]]
    assert all(n.action=="needs_confirmation" for n in valid.notes)
    if mode!="cell_alias":assert any("备注回执" in w for w in valid._warnings)


def test_invalid_review_only_classification_cannot_delete_original_cells_or_introduce_print_values():
    source=flexible.read("unknown.xlsx",workbook());result=plan(source)
    result["ignored_cells"]=[dict(source_id="E999",reason="heading"),dict(source_id="E1",reason=["invalid"])]
    valid=flexible.validate(json.dumps(result),source)
    assert all(i.source_id in {e.id for e in source["cells"]} for i in valid.ignored_cells)
    assert any(i.source_id=="E1" and i.reason=="unused" for i in valid.ignored_cells)
    assert any("重新建立" in w for w in valid._warnings)


def test_unlisted_cells_remain_in_review_and_barcode_minimums_are_applied_locally():
    source=flexible.read("unknown.xlsx",workbook());result=plan(source)
    result["notes"]=[];result["ignored_cells"]=[]
    result["records"][0]["panels"][0]["barcodes"][0].update(width_mm=35,height_mm=15)
    valid=flexible.validate(json.dumps(result),source)
    bar=valid.records[0].panels[0].barcodes[0]
    assert bar.width_mm==80 and bar.height_mm==60
    assert valid.ignored_cells and any("待核对页" in w for w in valid._warnings)
    image=io.BytesIO();Image.new("RGB",(200,100),"black").save(image,format="PNG")
    pdf,_,warnings=flexible.render(valid,source,image.getvalue())
    text="\n".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)
    assert all(n.location in text for n in source["notes"])
    assert "minimum 60mm" in text and "待核对" in text
    assert any("备注回执" in w for w in warnings)


def table_workbook():
    from openpyxl import load_workbook
    book=load_workbook(io.BytesIO(workbook()));s=book.active
    s["G12"].comment=Comment("条码高度不能低于32mm","fixture")
    s["D18"]="条码必须可扫描，条码高度不能低于32mm；条码外围需要加粗体黑框"
    s["D19"]="条码下需要加上地址及邮箱信息: "+s["C12"].value
    for col,name in enumerate(("Customer PO","Customer SKU","Description","Case Pack","CTN","GTIN"),1):s.cell(23,col,name)
    for row,po,count in ((24,"PO-SYNTHETIC-A","20"),(25,"PO-SYNTHETIC-B","30")):
        for col,value in enumerate((po,"000123","SYNTHETIC PRODUCT","6",count,"4006381333931"),1):s.cell(row,col,value)
    ref=book.create_sheet("排版参考");ref["A1"]="参考旧PO，不能当成本次业务数据"
    ref["A2"]="侧唛内容尽量保持居中"
    out=io.BytesIO();book.save(out);book.close();return out.getvalue()


def table_plan(source):
    result=plan(source);by_coord={e.location.split("!")[1]:e for e in source["cells"] if e.kind!="reference_cell"}
    first=result["records"][0];result["records"]=[]
    for row in (24,25):
        record=copy.deepcopy(first)
        remap={"C6":f"A{row}","G6":f"A{row}","C7":f"B{row}","G7":f"B{row}",
               "C8":f"C{row}","G8":f"C{row}","C9":f"D{row}","G9":f"D{row}","D10":f"E{row}"}
        for panel in record["panels"]:
            for field in panel["fields"]:
                for part in field["parts"]:
                    cell=next(c for c in source["cells"] if c.id==part["source_id"])
                    target=by_coord.get(remap.get(cell.location.split("!")[1],""))
                    if target:part.update(source_id=target.id,value=target.text)
            barcode=panel["barcodes"][0];target=by_coord[f"F{row}"]
            barcode.update(source=dict(source_id=target.id,value=target.text),width_mm=35,height_mm=15)
        result["records"].append(record)
    result["notes"]=[];result["ignored_cells"]=[]
    return result


def test_po_tables_are_separate_from_mark_column_ownership_and_each_po_must_be_kept_separate():
    source=flexible.read("new-layout.xlsx",table_workbook())
    assert len(source["detail_rows"])==2
    assert not any(key in source["ownership"] for r in source["detail_rows"] for key in r["cell_ids"])
    result=table_plan(source);valid=flexible.validate(json.dumps(result),source)
    assert len(valid.records)==2
    assert all(bar.height_mm==32 and bar.frame=="box" for r in valid.records for p in r.panels for bar in p.barcodes)
    assert any(f.position=="after_barcode" for f in valid.records[0].panels[0].fields)
    for mode in ("missing","mixed","reference"):
        bad=copy.deepcopy(result)
        if mode=="missing":bad["records"].pop()
        if mode=="mixed":bad["records"][0]["panels"][1]["fields"]=bad["records"][1]["panels"][1]["fields"]
        if mode=="reference":
            ref=next(c for c in source["cells"] if c.kind=="reference_cell")
            bad["records"][0]["panels"][0]["fields"][0]["parts"]=[dict(source_id=ref.id,value=ref.text)]
        with pytest.raises(pilot.PilotError):flexible.validate(json.dumps(bad),source)


def test_table_reconciliation_excludes_extra_examples_and_only_rebinds_identical_same_column_values():
    source=flexible.read("new-layout.xlsx",table_workbook());result=table_plan(source)
    example=plan(source)["records"][0];result["records"].insert(0,example)
    # The second row has identical item text, but a different carton count.
    first=result["records"][1]["panels"][1];second=result["records"][2]["panels"][1]
    first["fields"][4]["parts"]=copy.deepcopy(second["fields"][4]["parts"])
    for record in result["records"]:
        for panel in record["panels"]:
            for field in panel["fields"]:
                if field["label"]:field["label"]=field["label"]["value"]
    valid=flexible.validate(json.dumps(result),source)
    assert len(valid.records)==2 and any("示例" in w for w in valid._warnings)
    assert any("相同值" in w for w in valid._warnings)
    coords={c.id:c.location for c in source["cells"]}
    assert all(not coords[v.source_id].endswith("25") for p in valid.records[0].panels for f in p.fields for v in f.parts)
    bad=table_plan(source)
    bad["records"][0]["panels"][0]["fields"][-2]["parts"][-1]=copy.deepcopy(bad["records"][1]["panels"][0]["fields"][-2]["parts"][-1])
    with pytest.raises(pilot.PilotError,match="不同数值"):flexible.validate(json.dumps(bad),source)


def test_flow_renderer_preserves_front_side_differences_emphasis_placeholders_and_notes():
    source=flexible.read("unknown.xlsx",workbook());valid=flexible.validate(json.dumps(plan(source)),source)
    picture=io.BytesIO();Image.new("RGB",(200,100),"black").save(picture,format="PNG")
    pdf,pages,warnings=flexible.render(valid,source,picture.getvalue())
    reader=PdfReader(io.BytesIO(pdf));text=reader.pages[0].extract_text()
    assert pages>=2 and "PO-DEMO-0001" in text and "000123" in text and "demo@example.com" in text
    assert "印刷外箱净重" in text and any("重量" in w for w in warnings)
    assert any("minimum 60mm" in p.extract_text() for p in reader.pages[1:])
    sizes=[]
    reader.pages[0].extract_text(visitor_text=lambda text,cm,tm,font,size:sizes.append((text.strip(),size)))
    assert any(text=="08" and size==32 for text,size in sizes)


def test_barcode_minimum_width_excludes_quiet_zones():
    from reportlab.lib.units import mm
    source=flexible.read("unknown.xlsx",workbook())
    valid=flexible.validate(json.dumps(plan(source)),source)
    bar=valid.records[0].panels[0].barcodes[0]
    drawing=flexible._barcode(bar)
    # EAN-13 has 95 encoded modules; ReportLab adds nine quiet modules per side.
    assert drawing.width==pytest.approx(80*mm*113/95)
    assert drawing.height==pytest.approx(60*mm)


def test_literal_labels_are_resolved_to_native_cells_and_cross_face_duplicates_return_to_the_source_face():
    source=flexible.read("unknown.xlsx",workbook());result=copy.deepcopy(plan(source))
    front,side=result["records"][0]["panels"]
    front["fields"].append(copy.deepcopy(side["fields"][-1]))
    for panel in (front,side):
        for field in panel["fields"]:
            if field["label"]:field["label"]=field["label"]["value"]
    valid=flexible.validate(json.dumps(result),source)
    assert not any(f.label and f.label.value=="GW:" for f in valid.records[0].panels[0].fields)
    assert any(f.label and f.label.value=="GW:" for f in valid.records[0].panels[1].fields)
    assert all(not isinstance(f.label,str) for p in valid.records[0].panels for f in p.fields)
    result["records"][0]["panels"][0]["fields"][2]["label"]="INVENTED LABEL"
    with pytest.raises(pilot.PilotError):flexible.validate(json.dumps(result),source)


def test_unrecognized_structure_enters_flexible_path_before_any_provider_request(monkeypatch):
    from app.services import carton_supplier_mark_draft as draft
    from app.services import carton_supplier_mark_ai as ai
    monkeypatch.setattr(ai,"configuration",lambda:({},pilot.load_template(),b"reference","signature"))
    monkeypatch.setattr(pilot,"request_plan",lambda *a,**k:pytest.fail("no provider call while reading"))
    original=draft.original("unknown.xlsx",workbook(),"deepseek_zumiez",True,{})
    assert original["ai_profile"]=="flexible"
    assert len(original["flexible_source"]["cells"])>20
    monkeypatch.setattr(flexible,"prepare",lambda original:(b"pdf",2,[]))
    assert draft.prepare(original,"deepseek_zumiez")== (b"pdf",2,[])
