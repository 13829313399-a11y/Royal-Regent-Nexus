"""Read once, review in the page, render repeatedly without another paid call."""
import hashlib
import hmac
import json
import re
import secrets
import time

from fastapi import HTTPException

from app.services import carton_mark_flexible as flow
from app.services import carton_mark_images
from app.services import carton_mark_compact_plan as compact
from app.services import carton_mark_source_cache as source_cache
from app.services import carton_mark_reading as reading
from app.services import carton_mark_confirmed_template as confirmed
from app.services import carton_supplier_mark_ai as ai

_KEY=secrets.token_bytes(32)
VERSION="carton-review-v1"


def _sign(payload,owner):
    return hmac.new(_KEY,(owner+"\0"+payload).encode(),hashlib.sha256).hexdigest()


def _source(original):
    return source_cache.source(original["excel_file_name"],original["excel_bytes"],original.get("worksheets"))


def inspect(original):
    from collections import defaultdict
    from app.services.carton_mark import CartonMarkDocumentError
    try:doc=source_cache.document(original["excel_file_name"],original["excel_bytes"])
    except CartonMarkDocumentError as exc:raise HTTPException(422,str(exc)) from None
    counts=defaultdict(lambda:dict(cells=0,chars=0))
    for cell in doc.items:
        values=counts[cell.location.rsplit("!",1)[0]];values["cells"]+=1;values["chars"]+=len(cell.text)
    sheets=[dict(name=name,**values) for name,values in counts.items()]
    default=[s["name"] for s in sheets]
    if sum(s["cells"] for s in sheets)>2500 or sum(s["chars"] for s in sheets)>120000:
        default=[next((s["name"] for s in sheets if s["cells"]<=2500 and s["chars"]<=120000),sheets[0]["name"])] if sheets else []
    result=dict(worksheets=sheets,selected=default)
    try:
        candidate=confirmed.match(_source({**original,'worksheets':default}))
        if candidate:result['confirmed_template']=confirmed.metadata()
    except ai.pilot.PilotError:
        pass  # Inspection remains available for oversized/incomplete originals.
    return result


def read(original,owner,ai_consent=True):
    if not ai._SLOTS.acquire(blocking=False):raise HTTPException(429,"正在读取其他原稿，请稍后重试")
    try:
        source=_source(original)
        matched=confirmed.match(source)
        if matched:
            image_notes,images,warnings=[],[],[]
        else:
            if not ai_consent:raise HTTPException(422,'当前原稿未匹配确认版式；请明确同意后再发送必要文字给DeepSeek')
            connection,_,_,signature=ai.configuration()
            image_notes,images,warnings=carton_mark_images.collect(original["excel_file_name"],original["excel_bytes"],worksheets=original.get("worksheets"))
        image_warnings=list(warnings)
        source["notes"]+=image_notes
        from app.services.carton_mark_bound_sources import linked,table_template
        native_layout=linked(source) or table_template(source)
        mode="ai";questions=[];question_notes=[]
        try:
            if matched:
                plan,bindings=matched;mode='confirmed_template';signature=confirmed.signature()
            else:
                plan,mode,questions,question_notes=_ai_plan(source,connection,native_layout)
        except (ai.pilot.PilotError,ValueError,KeyError,TypeError) as exc:
            from app.services.carton_mark_native_plan import build
            from app.services.carton_mark_bound_sources import build as bound_sources
            reason=str(exc)[:400] if isinstance(exc,ai.pilot.PilotError) else "返回格式不完整，未采用未经核实的排版内容"
            plan=native_layout or bound_sources(source)
            if plan is not None:mode='native_layout'
            else:mode="needs_mapping";plan=build(source,reason)
        warnings+=plan._warnings
        payload=json.dumps(dict(version=VERSION,sha256=hashlib.sha256(original["excel_bytes"]).hexdigest(),
            filename=original["excel_file_name"],worksheets=original.get("worksheets",[]),provider_signature=signature,expires=int(time.time())+3600,
            mode=mode,confirmed_bindings=bindings if matched else None,plan=plan.model_dump(),image_notes=[n.model_dump() for n in image_notes],question_notes=[n.model_dump() for n in question_notes],warnings=warnings),ensure_ascii=False,separators=(",",":"))
        cells={c.id:c for c in source["cells"]};po_ids={row["po_id"] for row in source.get("detail_rows",[])}
        records=[]
        for r,record in enumerate(plan.records):
            panels=[]
            for p,panel in enumerate(record.panels):
                fields=[]
                for f,field in enumerate(panel.fields):
                    fields.append(dict(id=f"r{r}p{p}f{f}",label=confirmed.TITLES[confirmed.KEYS[f]] if matched else field.label.value if field.label else "印刷文字",
                        value=flow.field_value(field.parts),
                        sources=[cells[part.source_id].location for part in field.parts],
                        locked=(matched and confirmed.KEYS[f] in {'gtin','vendor_item','item'}) or any(part.source_id in po_ids for part in field.parts) or bool(re.search(r"barcode|gtin|upc|ean",field.label.value if field.label else "",re.I)),placeholder=field.role=="placeholder"))
                panels.append(dict(face=panel.face,copies=panel.copies,fields=fields,logo=panel.logo,symbols=[s.kind for s in panel.symbols],
                    barcodes=[dict(value=b.source.value,kind=b.kind,width_mm=b.width_mm,height_mm=b.height_mm,frame=b.frame) for b in panel.barcodes]))
            selected_ids={part.source_id for p in record.panels for f in p.fields for part in f.parts}
            row=next((row for row in source.get("detail_rows",[]) if row['id']==record.row_id or row["po_id"] in selected_ids),None)
            records.append(dict(panels=panels,title="PO "+cells[row["po_id"]].text if row else ""))
        return dict(payload=payload,signature=_sign(payload,owner),records=records,mode=mode,
            confirmed_template=confirmed.metadata() if matched else None,
            issues=confirmed.issues(records,bindings) if matched else reading.review_issues(records,source,mode,questions,image_warnings),
            notes=[dict(id=n.id,location=n.location,text=n.text,status="needs_confirmation") for n in source["notes"]],
            images=images,warnings=warnings,source_cells=len(cells),paper=plan.paper,orientation=plan.orientation,
            logo_available=flow.constraints(source)["logo"] or any(re.search(r"\bZURU\b",n.text,re.I) for n in source["notes"] if n.kind=="image_reference_text"),
            unselected_cells=[dict(id=i.source_id,location=cells[i.source_id].location,text=cells[i.source_id].text,
                printable=cells[i.source_id].kind!="reference_cell" and cells[i.source_id].location not in {n.location for n in source["notes"]}) for i in plan.ignored_cells])
    except ai.pilot.PilotError as exc:raise HTTPException(422,str(exc)) from None
    finally:ai._SLOTS.release()


def _ai_plan(source,connection,native_layout):
    mode='ai'
    raw,_=ai.pilot.request_plan(reading.provider_evidence(source),flow.TEMPLATE,connection,prompt=compact.PROMPT,max_tokens=16000)
    if native_layout is not None:plan=native_layout;mode='native_layout'
    else:plan=flow.validate(compact.expand(raw,source),source,review_mode=True)
    questions=reading.model_issues(raw,source)
    question_notes=[ai.pilot.Evidence(id=f'Q{i+1}',kind='model_question',location='AI待确认!'+str(i+1),text=q['message']+'\n引用来源：'+'、'.join(q['sources'])) for i,q in enumerate(questions)]
    source['notes']+=question_notes
    plan.notes += [flow.NoteChoice(source_id=n.id,action='needs_confirmation') for n in question_notes]
    if questions:plan._warnings.append(f'模型提出{len(questions)}项需确认内容，详见页面待确认项和完整核对记录；这些问题不是新的业务事实。')
    return plan,mode,questions,question_notes


def render(original,owner,payload,signature,edits,reviewed,paper,orientation,additions=None,omissions=None,graphics=None,include_sources=True):
    if len(payload)>500_000 or not re.fullmatch(r"[0-9a-f]{64}",signature) or not hmac.compare_digest(_sign(payload,owner),signature):
        raise HTTPException(409,"读取结果不属于当前账号或已失效，请重新读取原稿")
    try:
        data=json.loads(payload)
        if (data["version"]!=VERSION or data["expires"]<time.time()
                or data["sha256"]!=hashlib.sha256(original["excel_bytes"]).hexdigest()
                or data["filename"]!=original["excel_file_name"]):raise ValueError()
        is_confirmed=data.get('mode')=='confirmed_template'
        if is_confirmed:provider_signature=confirmed.signature()
        else:_,template,reference,provider_signature=ai.configuration()
        if provider_signature!=data["provider_signature"]:raise ValueError()
    except (KeyError,ValueError,TypeError):raise HTTPException(409,"读取结果已过期、原稿或连接已变化，请重新读取") from None
    try:
        original={**original,"worksheets":data.get("worksheets",[])}
        source=_source(original);source["notes"] += [ai.pilot.Evidence.model_validate(n) for n in data["image_notes"]+data.get('question_notes',[])]
        plan=flow.Plan.model_validate(data['plan']) if is_confirmed else flow.validate(json.dumps(data["plan"],ensure_ascii=False),source,review_mode=True,require_destinations=data.get('mode')!='needs_mapping')
        if paper not in {"A3","A4"} or orientation not in {"portrait","landscape"} or type(include_sources) is not bool:raise ValueError()
        if not isinstance(edits,dict) or len(edits)>150:raise ValueError()
        ids={n.id for n in source["notes"]}
        if not isinstance(reviewed,list) or len(reviewed)>flow.MAX_REVIEW_NOTES or any(not isinstance(n,str) or n not in ids for n in reviewed):raise ValueError()
        po_ids={row["po_id"] for row in source.get("detail_rows",[])};manual=[]
        if additions is None:additions=[]
        if omissions is None:omissions=[]
        if graphics is None:graphics=[]
        if not isinstance(additions,list) or len(additions)>100 or not isinstance(omissions,list) or len(omissions)>150:raise ValueError()
        if not isinstance(graphics,list) or len(graphics)>60:raise ValueError()
        if is_confirmed and (additions or omissions or graphics):
            raise HTTPException(422,'确认版式的箱面结构固定；新增字段、移除字段或图案变化需要另建版式，未忽略修改')
        for key,value in edits.items():
            match=re.fullmatch(r"r(\d+)p(\d+)f(\d+)",key)
            if not match or not isinstance(value,str) or not 1<=len(value.strip())<=2000:raise ValueError()
            r,p,f=map(int,match.groups());field=plan.records[r].panels[p].fields[f]
            if (is_confirmed and confirmed.KEYS[f] in {'gtin','vendor_item','item'}) or any(part.source_id in po_ids for part in field.parts) or (field.label and re.search(r"barcode|gtin|upc|ean",field.label.value,re.I)):
                raise HTTPException(422,"PO身份和条码号码请在原稿中修改后重新读取")
            old=flow.field_value(field.parts)
            if value.strip()==old:continue
            label=field.label.value if field.label else "印刷文字"
            note_id=f"U{len(manual)+1}"
            manual.append(ai.pilot.Evidence(id=note_id,kind="manual_entry",location=f"页面补充!第{r+1}组/{plan.records[r].panels[p].face}/{label}",text=f"原文：{old}\n本次明确补充：{value.strip()}"))
            field.parts=[flow.Selection(source_id=note_id,value=value.strip())]
            field.role="normal" if field.role=="placeholder" else field.role
        if is_confirmed:confirmed.synchronize(plan,edits)
        remove=set()
        for key in omissions:
            if not isinstance(key,str) or not re.fullmatch(r"r\d+p\d+f\d+",key):raise ValueError()
            r,p,f=map(int,re.fullmatch(r"r(\d+)p(\d+)f(\d+)",key).groups())
            field=plan.records[r].panels[p].fields[f]
            if any(part.source_id in po_ids for part in field.parts):raise HTTPException(422,"不能移除当前PO身份")
            remove.add((r,p,f))
        for r,record in enumerate(plan.records):
            for p,panel in enumerate(record.panels):panel.fields=[field for f,field in enumerate(panel.fields) if (r,p,f) not in remove]
        cells={c.id:c for c in source["cells"]};notes_locations={n.location for n in source["notes"]}
        for added in additions:
            if not isinstance(added,dict) or set(added)-{"record","face","label","value","source_id","as_barcode"}:raise ValueError()
            r=added.get("record");face=added.get("face");label=added.get("label","");value=added.get("value","");source_id=added.get("source_id","")
            if type(r) is not int or not 0<=r<len(plan.records) or face not in {"front","side"} or not isinstance(label,str) or len(label)>100:raise ValueError()
            record=plan.records[r]
            panel=next((p for p in record.panels if p.face==face),None)
            if source_id:
                cell=cells.get(source_id)
                if not cell or cell.kind=="reference_cell" or cell.location in notes_locations:raise HTTPException(422,"只能添加本次原生印刷字段，参考图和备注不能放入箱面")
                bound={part.source_id for p in record.panels for f in p.fields for part in f.parts}
                current=next((row for row in source.get("detail_rows",[]) if row["po_id"] in bound),None)
                other=next((row for row in source.get("detail_rows",[]) if source_id in row["cell_ids"]),None)
                if current and other and current["id"]!=other["id"]:raise HTTPException(422,"不能把另一PO的数据添加到本组箱唛")
                part=flow.Selection(source_id=cell.id,value=cell.text);value=cell.text;label=""
            else:
                if not isinstance(value,str) or not 1<=len(value.strip())<=2000:raise ValueError()
                part=flow.Selection(source_id=f"U{len(manual)+1}",value=(label+" "+value).strip())
            manual.append(ai.pilot.Evidence(id=f"U{len(manual)+1}",kind="manual_entry",location=f"页面补充!第{r+1}组/{face}/新增字段",text=f"本次明确新增：{part.value}"+(f"\n来源：{cells[source_id].location}" if source_id else "（用户填写）")))
            as_barcode=added.get("as_barcode",False)
            if type(as_barcode) is not bool:raise ValueError()
            if as_barcode:
                if not source_id:raise HTTPException(422,"条码只能选用本次原稿单元格，不能以自由补充代替原号码")
                kind={12:"UPCA",13:"EAN13",14:"ITF14"}.get(len(part.value))
                if not kind:raise HTTPException(422,"请选择原稿中明确的12/13/14位条码号码")
                from app.services.carton_mark_hyvee import validate_gtin
                validate_gtin(part.value,len(part.value))
                limits=flow.constraints(source)
                bar=flow.Barcode(source=part,kind=kind,width_mm=limits["width"],height_mm=limits["height"],frame="box" if limits["frame"] else "none",note_ids=[])
                if panel is None:
                    panel=flow.Panel(face=face,copies=2,logo=False,fields=[],barcodes=[bar],symbols=[]);record.panels.append(panel)
                else:panel.barcodes.append(bar)
                manual[-1]=manual[-1].model_copy(update={"text":manual[-1].text+"\n按原号码重新生成条码图，尺寸取原稿明确要求。"})
                continue
            field=flow.TextField(label=None,parts=[part],role="normal")
            if panel is None:
                panel=flow.Panel(face=face,copies=2,logo=False,fields=[field],barcodes=[],symbols=[]);record.panels.append(panel)
            else:panel.fields.append(field)
        logo_available=flow.constraints(source)["logo"] or any(re.search(r"\bZURU\b",n.text,re.I) for n in source["notes"] if n.kind=="image_reference_text")
        names=dict(fragile="易碎",this_side_up="向上",keep_dry="防潮")
        for setting in graphics:
            if not isinstance(setting,dict) or set(setting)!={"record","face","logo","symbols"}:raise ValueError()
            r,face,show_logo,kinds=(setting[k] for k in ("record","face","logo","symbols"))
            if type(r) is not int or not 0<=r<len(plan.records) or face not in {"front","side"} or type(show_logo) is not bool:raise ValueError()
            if not isinstance(kinds,list) or len(kinds)>3 or any(not isinstance(k,str) or k not in names for k in kinds):raise ValueError()
            if show_logo and not logo_available:raise HTTPException(422,"原稿未提供可核实的ZURU品牌依据，请对照素材后再处理")
            record=plan.records[r];panel=next((p for p in record.panels if p.face==face),None)
            if panel is None:
                if not show_logo and not kinds:continue
                panel=flow.Panel(face=face,copies=2,logo=False,fields=[],barcodes=[],symbols=[]);record.panels.append(panel)
            if panel.logo==show_logo and {s.kind for s in panel.symbols}==set(kinds):continue
            note_id=f"U{len(manual)+1}"
            manual.append(ai.pilot.Evidence(id=note_id,kind="manual_entry",location=f"页面补充!第{r+1}组/{face}/图案",text=f"用户明确选择：ZURU标志{'使用' if show_logo else '不使用'}；搬运标识："+("、".join(names[k] for k in kinds) or "无")+"。请与原稿要求及实际箱体核对。"))
            panel.logo=show_logo;panel.symbols=[flow.Symbol(kind=k,note_ids=[note_id]) for k in dict.fromkeys(kinds)]
        if any(not (p.fields or p.barcodes or p.symbols or p.logo) for r in plan.records for p in r.panels):raise HTTPException(422,"每个箱面请至少保留一个印刷字段或图案")
        source["notes"]+=manual
        plan.notes += [flow.NoteChoice(source_id=n.id,action="needs_confirmation") for n in manual]
        plan._reviewed_notes=set(reviewed)
        plan._warnings=list(dict.fromkeys(data["warnings"]+plan._warnings))
        if remove:plan._warnings.append(f"本次明确移除{len(remove)}项箱面字段，原文保留在未选入清单。")
        used={part.source_id for r in plan.records for p in r.panels for f in p.fields for part in f.parts}
        used.update(f.label.source_id for r in plan.records for p in r.panels for f in p.fields if f.label)
        used.update(b.source.source_id for r in plan.records for p in r.panels for b in p.barcodes)
        plan.ignored_cells=[flow.Ignored(source_id=key,reason="unused") for key in cells if key not in used]
        if manual:plan._warnings.append(f"有{len(manual)}项本次人工补充，已与原文一并留在来源页；未修改Excel或其他订单。")
        plan.paper=paper;plan.orientation=orientation
        if is_confirmed:
            pdf,pages,warnings=confirmed.render(plan,source,data['confirmed_bindings'],confirmed.logo_bytes(),include_sources=include_sources)
            if pages>100 or len(pdf)>20*1024*1024:raise HTTPException(422,'结果超过100页/20MB，请拆分原稿')
            return pdf,pages,warnings
        logo=None
        if any(p.logo for r in plan.records for p in r.panels):
            x,y,w,h=template["logo_crop_mm"]
            logo=flow.crop_reference(reference,template["reference_page"],dict(x=x,y=y,width=w,height=h))
        try:pdf,pages,warnings=flow.render(plan,source,logo,include_sources=include_sources)
        except ai.pilot.PilotError as exc:
            if "无法完整放入版面" not in str(exc) or (paper=="A3" and orientation=="portrait"):raise
            plan.paper="A3";plan.orientation="portrait";pdf,pages,warnings=flow.render(plan,source,logo,include_sources=include_sources)
            warnings.insert(0,"已按内容改为A3竖向；没有缩小条码，也没有再次调用API。")
        if pages>100 or len(pdf)>20*1024*1024:raise HTTPException(422,"结果超过100页/20MB，请拆分原稿")
        return pdf,pages,warnings
    except (ValueError,KeyError,IndexError,TypeError) as exc:
        if isinstance(exc,ai.pilot.PilotError):raise HTTPException(422,str(exc)) from None
        raise HTTPException(422,"核对内容格式无效，请刷新后重新读取") from None
