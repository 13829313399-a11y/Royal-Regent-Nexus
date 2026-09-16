"""Native-first PDF reconstruction, regional OCR and object-preserving splitting."""
import copy
import io
import math
import re
import time
from pathlib import Path

import pdfplumber
import pypdfium2 as pdfium
from pypdf import PdfWriter
from pypdf.generic import ArrayObject, NameObject, RectangleObject

from .document_ir import Block, Cancelled, Cell, DocumentIR, EngineResult, Issue, Page, SourceAnchor, Table, ToolError, result_file
from .pdf_geometry import geometry, normalize_pdf, open_pdf, parse_page_groups, validate_cuts


def _check(cancelled):
    if cancelled():
        raise Cancelled()


def _anchor(page_index, box, method="native", precision="cell"):
    return SourceAnchor(page_index=page_index, bbox_pt=list(map(float, box)), method=method, anchor_precision=precision)


def _issue(ir, code, message, source=None, target=None, candidates=None):
    ir.issues.append(Issue(id=f"pdf-issue-{len(ir.issues)+1}", code=code, message=message,
                           source=source or SourceAnchor(), target_id=target, candidates=candidates or []))


def _inside(box, outer):
    return outer[0] <= (box[0]+box[2])/2 <= outer[2] and outer[1] <= (box[1]+box[3])/2 <= outer[3]


def _intersects(a, b):
    return min(a[2], b[2]) > max(a[0],b[0]) and min(a[3],b[3]) > max(a[1],b[1])


def _box(obj):
    return [obj["x0"],obj["top"],obj["x1"],obj["bottom"]]


def _table_ir(table, page_index, index, method="native"):
    # Rectangles describe merged cells. Recover elementary grid from ALL edges,
    # not pdfplumber's repeated None placeholders.
    xs = sorted({round(v, 4) for rect in table.cells for v in (rect[0],rect[2])})
    ys = sorted({round(v, 4) for rect in table.cells for v in (rect[1],rect[3])})
    result = Table(id=f"p{page_index}-t{index}", row_count=len(ys)-1, column_count=len(xs)-1,
                   source_pages=[page_index], source=_anchor(page_index,table.bbox,method,"region"), header_rows=[0])
    for rect in sorted(set(table.cells), key=lambda x:(x[1],x[0])):
        x0,y0,x1,y1 = [round(v,4) for v in rect]
        r,c,rs,cs = ys.index(y0),xs.index(x0),ys.index(y1)-ys.index(y0),xs.index(x1)-xs.index(x0)
        text = table.page.filter(lambda obj: obj.get("object_type") == "char" and _inside(_box(obj),rect)).extract_text(x_tolerance=2,y_tolerance=2) or ""
        result.cells.append(Cell(id=f"{result.id}-r{r}c{c}", row=r,column=c,rowspan=rs,colspan=cs,
                                 raw_text=text,display_text=text,value=text,source=_anchor(page_index,rect,method)))
    if getattr(table,"_rr_text_strategy",False):
        nonempty_rows=sorted({c.row for c in result.cells if c.raw_text.strip()})
        result.cells=[c for c in result.cells if c.row in nonempty_rows]
        for cell in result.cells:
            cell.row=nonempty_rows.index(cell.row)
        result.row_count=len(nonempty_rows)
        result.extraction_strategy="text_alignment"
    return result


def _find_tables(page):
    tables = list(page.find_tables())
    # Independent vertically separated groups prevent a single text-strategy
    # table from swallowing an entire page of unrelated prose / multiple tables.
    words = [w for w in page.extract_words() if not any(_inside(_box(w),t.bbox) for t in tables)]
    groups, current, end = [], [], -1e9
    for word in sorted(words,key=lambda w:(w["top"],w["x0"])):
        h = max(4,word["bottom"]-word["top"])
        if current and word["top"] > end + max(28,h*3):
            groups.append(current)
            current=[]
        current.append(word)
        end=max(end,word["bottom"])
    if current:
        groups.append(current)
    for group in groups:
        if len(group)<6:
            continue
        bounds=(max(0,min(w["x0"] for w in group)-2),max(0,min(w["top"] for w in group)-2),
                min(page.width,max(w["x1"] for w in group)+2),min(page.height,max(w["bottom"] for w in group)+2))
        for candidate in page.crop(bounds).find_tables({"vertical_strategy":"text","horizontal_strategy":"text","min_words_vertical":3,"min_words_horizontal":1}):
            rows=candidate.extract()
            nonempty=[row for row in rows if sum(bool(v and v.strip()) for v in row)>=2]
            # Long prose in multiple columns is not a table merely because its
            # left edges align. Keep natural reading blocks in that case.
            prose_columns=sum(sum(len((row[c] or '').strip()) for row in nonempty)/max(1,len(nonempty))>20
                              for c in range(len(candidate.columns)))
            numeric=any(re.search(r"\d",value or "") for row in nonempty for value in row)
            clipped_prose=prose_columns>=1 and bounds[2]-candidate.bbox[2]>max(20,(bounds[2]-bounds[0])*.05)
            if (prose_columns>=2 or clipped_prose) and not numeric:
                continue
            if len(nonempty)>=3 and len(candidate.columns)>=2 and not any(_intersects(candidate.bbox,t.bbox) for t in tables):
                candidate._rr_text_strategy=True
                tables.append(candidate)
    return sorted(tables,key=lambda t:(t.bbox[1],t.bbox[0]))


def _render_region(path,page_index,box,scale=3):
    with pdfium.PdfDocument(str(path)) as doc:
        page=doc[page_index]
        # Crop at render time: bounded memory even for long pages.
        width,height=page.get_size()
        region_w,region_h=box[2]-box[0],box[3]-box[1]
        scale=min(scale,math.sqrt(7_500_000/max(1,region_w*region_h)))
        if scale < 0.6:
            raise ToolError("OCR_REGION_TOO_LARGE","页面过长，请框选较小区域识别")
        bitmap=page.render(scale=scale,crop=(box[0],height-box[3],width-box[2],box[1]))
        image=bitmap.to_pil().copy()
        bitmap.close()
        page.close()
        return image


def _ocr_region(ir,normalized,index,box,options,work_dir,cancelled,prefix):
    from . import local_ocr, qwen_ocr
    from app.core.config import settings
    _check(cancelled)
    image=_render_region(normalized,index,box)
    source=_anchor(index,box,"ocr","region")
    local=[]
    try:
        local=local_ocr.recognize(image,box)
    except ToolError as exc:
        _issue(ir,exc.code,exc.message,source)
    line_groups=[]
    for line in sorted(local,key=lambda item:item["bbox_pt"][1]):
        current=line["bbox_pt"]
        group=next((group for group in line_groups if min(group[0]["bbox_pt"][3],current[3])-max(group[0]["bbox_pt"][1],current[1])>
                    min(group[0]["bbox_pt"][3]-group[0]["bbox_pt"][1],current[3]-current[1])*.5),None)
        if group is None: line_groups.append([line])
        else: group.append(line)
    local=[]
    for group in line_groups:
        reading_y=min(line["bbox_pt"][1] for line in group)
        for line in sorted(group,key=lambda item:item["bbox_pt"][0]):
            line["reading_y"]=reading_y; local.append(line)
    ir.engine_manifest.setdefault("ocr_regions",[]).append({"page_index":index,"bbox_pt":box,
        "image_size_px":[image.width,image.height],"image_to_visible":[(box[2]-box[0])/image.width,0,0,(box[3]-box[1])/image.height,box[0],box[1]],"preprocessing":"render-crop-v1"})
    # Local word boxes are retained independently of Qwen's regional table
    # anchor; never invent per-cell coordinates from HTML without locations.
    ai_tables=[]
    if options.get("ai_mode","auto")!="off" and qwen_ocr.configured(settings):
        data=io.BytesIO(); image.save(data,format="PNG")
        call_started=time.monotonic()
        try:
            response=qwen_ocr.recognize(settings,data.getvalue(),cancelled=cancelled)
            ir.engine_manifest.setdefault("qwen_calls",[]).append({k:v for k,v in response.items() if k!="text"}|{"page_index":index,"bbox_pt":box})
            ai_tables=qwen_ocr.parse_html_tables(response["text"],source.model_copy(update={"method":"qwen"}),prefix)
            if not ai_tables and not local:
                ir.blocks.append(Block(id=f"{prefix}-text",text=response["text"],source=source.model_copy(update={"method":"qwen"})))
            elif not ai_tables:
                _issue(ir,"OCR_TEXT_CANDIDATE","千问返回文字候选但未形成完整表格，请与本地候选核对",source,candidates=[response["text"]])
            if local and ai_tables:
                native_candidate="\n".join(x["text"] for x in local)
                ai_candidate="\n".join(c.raw_text for t in ai_tables for c in t.cells)
                if "".join(native_candidate.split())!="".join(ai_candidate.split()):
                    _issue(ir,"OCR_CANDIDATE_DIFFERENCE","本地 OCR 与千问识别候选不同，请核对原图",source,candidates=[native_candidate,ai_candidate])
        except ToolError as exc:
            if isinstance(exc,Cancelled):
                raise
            ir.engine_manifest.setdefault("qwen_calls",[]).append({"model":settings.document_tools_qwen_ocr_model,
                "protocol":settings.document_tools_qwen_protocol,"page_index":index,"bbox_pt":box,
                "usage":None,"elapsed_seconds":round(time.monotonic()-call_started,3),"error_code":exc.code})
            _issue(ir,exc.code,exc.message,source)
    elif options.get("ai_mode","auto")!="off":
        _issue(ir,"QWEN_NOT_CONFIGURED","千问未配置；当前是本地 OCR 候选",source)
    local_tables=local_ocr.recover_tables(image,local,box,index,prefix)
    recovered_tables=ai_tables or local_tables
    if recovered_tables:
        ir.tables.extend(recovered_tables)
        ir.blocks.extend(Block(id=t.id+"-block",kind="table",table_id=t.id,source=t.source) for t in recovered_tables)
        for table in recovered_tables:
            for cell in table.cells:
                if cell.resolution=="unknown":
                    _issue(ir,"OCR_CELL_UNKNOWN","该单元格存在无法辨认或被遮挡的内容，不能按空白或部分数字处理",cell.source,cell.id,getattr(cell,"candidates",[]))
        if not ai_tables:
            for n,line in enumerate(local):
                if not any(_inside(line["bbox_pt"],t.source.bbox_pt) for t in local_tables):
                    ir.blocks.append(Block(id=f"{prefix}-note{n}",text=line["text"],source=_anchor(index,line["bbox_pt"],"local_ocr","block")))
    else:
        for n,line in enumerate(local):
            ir.blocks.append(Block(id=f"{prefix}-line{n}",text=line["text"],source=_anchor(index,line["bbox_pt"],"local_ocr","block"),
                                   style={"ocr_signal_score":line["signal_score"],"reading_y":line["reading_y"]}))
    if not local and not recovered_tables:
        image_path=work_dir/f"{prefix}-unreadable.png"; image.save(image_path)
        ir.blocks.append(Block(id=f"{prefix}-unreadable",kind="image",source=source,style={"image_path":str(image_path),"width_pt":box[2]-box[0]}))
    elif options.get("_preserve_image") and not recovered_tables:
        image_path=work_dir/f"{prefix}-figure.png"; image.save(image_path)
        ir.blocks.append(Block(id=f"{prefix}-figure",kind="image",source=source,style={"image_path":str(image_path),"width_pt":box[2]-box[0]}))
    _issue(ir,"OCR_REVIEW_REQUIRED","识别内容为候选；请核对编号、数量、金额及表结构",source)
    _check(cancelled)


def inspect_pdf(path,options,work_dir,progress,cancelled):
    return _extract(path,options,Path(work_dir),progress,cancelled,ocr=False)


def _extract(path,options,work_dir,progress,cancelled,ocr=False):
    work_dir.mkdir(parents=True,exist_ok=True)
    normalized=work_dir/"source-preview.pdf"
    progress("inspect",0,None)
    from app.core.config import settings
    if len(open_pdf(path,options.get("password") or options.get("_password")).pages)>getattr(settings,"document_tools_max_pages",200):
        raise ToolError("PDF_PAGE_LIMIT","PDF 页数超过当前处理上限")
    metadata,annotations=normalize_pdf(path,normalized,options.get("password") or options.get("_password"),cancelled)
    selected={n for group in parse_page_groups(options.get("page_selection","all"),len(metadata)) for n in group}
    ir=DocumentIR(source_type="pdf",engine_manifest={"native":"pdfplumber","render":"pdfium","geometry":"pypdf-visible-v1"})
    if annotations:
        _issue(ir,"PDF_ANNOTATIONS_PREVIEW","预览与重建版不保留 PDF 交互注释；原件保持不变")
    with pdfplumber.open(normalized) as pdf:
        for index,page in enumerate(pdf.pages):
            _check(cancelled)
            if index not in selected:
                continue
            page=page.crop((0,0,page.width,page.height))
            original_char_count=len(page.chars)
            page=page.dedupe_chars(tolerance=0.5)
            g=metadata[index]
            chars=[c for c in page.chars if _inside(_box(c),(0,0,page.width,page.height))]
            if original_char_count>len(page.chars):
                _issue(ir,"PDF_DUPLICATE_TEXT_LAYER","发现重复覆盖文字，提取时已按坐标去重",_anchor(index,[0,0,page.width,page.height],precision="page"))
            text="".join(c["text"] for c in chars)
            bad=(text.count("\ufffd")+text.count("(cid:"))>0
            images=[im for im in page.images if (im["x1"]-im["x0"])*(im["bottom"]-im["top"])>400]
            classification="suspect_text" if bad else "mixed" if chars and images else "native" if chars else "scanned" if images else "blank"
            ir.pages.append(Page(page_index=index,display_page_number=index+1,width_pt=g["width_pt"],height_pt=g["height_pt"],rotation=g["rotation"],classification=classification,**{k:v for k,v in g.items() if k not in {"width_pt","height_pt","rotation"}}))
            tables=[] if bad else _find_tables(page)
            for ti,table in enumerate(tables):
                item=_table_ir(table,index,ti)
                ir.tables.append(item)
                ir.blocks.append(Block(id=item.id+"-block",kind="table",table_id=item.id,source=item.source))
            words=[w for w in page.extract_words(extra_attrs=["size","fontname"]) if _inside(_box(w),(0,0,page.width,page.height)) and not any(_inside(_box(w),t.bbox) for t in tables)]
            lines=[]
            for word in sorted(words,key=lambda w:(round(w["top"]/3)*3,w["x0"])):
                if lines and abs(lines[-1][0]["top"]-word["top"])<3 and word["x0"]-lines[-1][-1]["x1"]<=max(35,word["size"]*4):
                    lines[-1].append(word)
                else:
                    lines.append([word])
            for li,line in enumerate(lines):
                if bad and ocr:
                    continue
                bounds=[min(w["x0"] for w in line),min(w["top"] for w in line),max(w["x1"] for w in line),max(w["bottom"] for w in line)]
                ir.blocks.append(Block(id=f"p{index}-line{li}",text=" ".join(w["text"] for w in line),source=_anchor(index,bounds,"native","block"),
                    style={"font_size":max(w["size"] for w in line),"bold":any("Bold" in w["fontname"] for w in line)}))
            if bad:
                _issue(ir,"PDF_UNICODE_MAPPING","原生文字映射可疑，已保留原生候选，请查看视觉识别结果",_anchor(index,[0,0,page.width,page.height],precision="page"),candidates=[text])
            if ocr and classification in {"scanned","suspect_text"}:
                progress("recognize",0,None)
                _ocr_region(ir,normalized,index,[0,0,page.width,page.height],options,work_dir,cancelled,f"p{index}-ocr")
            elif classification=="mixed":
                for ii,im in enumerate(images):
                    box=[max(0,im["x0"]),max(0,im["top"]),min(page.width,im["x1"]),min(page.height,im["bottom"])]
                    if box[2]<=box[0] or box[3]<=box[1]:
                        continue
                    # Ignore scanned backgrounds already covered by a reliable text layer.
                    if sum(_inside(_box(c),box) for c in chars)>10:
                        continue
                    if ocr:
                        progress("recognize",0,None)
                        _ocr_region(ir,normalized,index,box,{**options,"_preserve_image":True},work_dir,cancelled,f"p{index}-image{ii}")
                    else:
                        _issue(ir,"PDF_IMAGE_REGION","图像区域将在转换时识别",_anchor(index,box,"image","region"))
            progress("extract" if ocr else "inspect",index+1,len(metadata))
    ir.blocks.sort(key=lambda b:(b.source.page_index or 0,b.style.get("reading_y",(b.source.bbox_pt or [0,0])[1]),(b.source.bbox_pt or [0,0])[0]))
    # Two separated text columns, where a real gutter and repeated lines exist.
    # Ambiguous multi-column/table mixtures retain geometric order and a review
    # warning instead of inventing a semantic reading sequence.
    for page in ir.pages:
        blocks=[b for b in ir.blocks if b.source.page_index==page.page_index]
        if any(b.kind=="table" for b in blocks):
            continue
        middle=page.width_pt/2
        left=[b for b in blocks if b.source.bbox_pt and b.source.bbox_pt[2]<middle-8]
        right=[b for b in blocks if b.source.bbox_pt and b.source.bbox_pt[0]>middle+8]
        wide=[b for b in blocks if b not in left and b not in right]
        if len(left)>=3 and len(right)>=3 and all(b.source.bbox_pt and (b.source.bbox_pt[3]<min(left[0].source.bbox_pt[1],right[0].source.bbox_pt[1]) or b.source.bbox_pt[1]>max(left[-1].source.bbox_pt[3],right[-1].source.bbox_pt[3])) for b in wide):
            header=[b for b in wide if b.source.bbox_pt[3]<min(left[0].source.bbox_pt[1],right[0].source.bbox_pt[1])]
            footer=[b for b in wide if b not in header]
            first=ir.blocks.index(blocks[0])
            ir.blocks[first:first+len(blocks)]=header+left+right+footer
            _issue(ir,"PDF_COLUMN_ORDER","按可见栏间空白恢复双栏阅读顺序，请查看对照校样",_anchor(page.page_index,[0,0,page.width_pt,page.height_pt],precision="page"))
    return EngineResult(ir,[result_file(normalized,"preview")],{"pages":[p.model_dump() for p in ir.pages],"page_count":len(metadata),
        "tables":len(ir.tables),"supported_operations":["pdf_to_word","pdf_to_excel","pdf_split","pdf_translate"]})


def convert_pdf(path,operation,options,work_dir,progress,cancelled,ir=None):
    work_dir=Path(work_dir); work_dir.mkdir(parents=True,exist_ok=True)
    _check(cancelled)
    if operation=="pdf_split":
        return _split(path,options,work_dir,progress,cancelled)
    if operation not in {"pdf_to_word","pdf_to_excel"}:
        raise ToolError("OPERATION_UNSUPPORTED","不支持该 PDF 操作")
    if ir is None:
        extracted=_extract(path,options,work_dir,progress,cancelled,ocr=True)
        ir=extracted.ir
    else:
        ir=ir.model_copy(deep=True)
        region=options.get("_recognize_region")
        if region:
            normalized=work_dir/"source-preview.pdf"
            normalize_pdf(path,normalized,options.get("password") or options.get("_password"),cancelled)
            page=next((p for p in ir.pages if p.page_index==region["page_index"]),None)
            box=region["bbox_pt"]
            if page is None or len(box)!=4 or not all(math.isfinite(x) for x in box) or not (0<=box[0]<box[2]<=page.width_pt and 0<=box[1]<box[3]<=page.height_pt):
                raise ToolError("OCR_REGION_INVALID","识别区域必须位于可见页面内")
            # Reliable/manual data is not duplicated in formal output merely
            # because its region was recognized again. New candidates remain
            # review evidence; wholly OCR-derived regions may be regenerated.
            progress("recognize",0,None)
            candidate_ir=DocumentIR(source_type="pdf")
            _ocr_region(candidate_ir,normalized,page.page_index,box,options,work_dir,cancelled,f"region-{len(ir.blocks)}")
            overlaps=[c for t in ir.tables for c in t.cells if c.source.page_index==page.page_index and c.source.bbox_pt and _intersects(c.source.bbox_pt,box)]
            protected=any(c.source.method in {"native","manual"} for c in overlaps) or any(b.source.page_index==page.page_index and b.source.bbox_pt and _intersects(b.source.bbox_pt,box) and b.source.method in {"native","manual"} for b in ir.blocks if b.kind!="table")
            if protected:
                values=[c.raw_text for t in candidate_ir.tables for c in t.cells]+[b.text for b in candidate_ir.blocks if b.kind!="table" and b.text]
                _issue(ir,"OCR_REGION_CANDIDATE","已生成局部识别候选；原生及人工确认值保持不变，可选择单元格填写修正值",_anchor(page.page_index,box,"ocr","region"),candidates=values)
                ir.engine_manifest.setdefault("regional_candidates",[]).append(candidate_ir.model_dump())
            else:
                def contained(anchor):
                    return anchor.page_index==page.page_index and anchor.bbox_pt and box[0]<=anchor.bbox_pt[0] and box[1]<=anchor.bbox_pt[1] and box[2]>=anchor.bbox_pt[2] and box[3]>=anchor.bbox_pt[3]
                replaced={t.id for t in ir.tables if contained(t.source) and all(c.source.method not in {"native","manual"} for c in t.cells)}
                ir.tables=[t for t in ir.tables if t.id not in replaced]+candidate_ir.tables
                ir.blocks=[b for b in ir.blocks if b.table_id not in replaced and not (b.kind!="table" and contained(b.source) and b.source.method not in {"native","manual"})]+candidate_ir.blocks
                for issue in candidate_ir.issues:
                    ir.issues.append(issue.model_copy(update={"id":f"pdf-issue-{len(ir.issues)+1}"}))
            for key in ("qwen_calls","ocr_regions"):
                ir.engine_manifest.setdefault(key,[]).extend(candidate_ir.engine_manifest.get(key,[]))
    from .office_engine import write_docx, write_xlsx
    from .pdf_structure import merge_continuations, type_cells
    type_cells(ir,options,_issue)
    if options.get("merge_continuation_tables"):
        merge_continuations(ir,_issue)
    progress("rebuild",0,1)
    target=work_dir/("result.docx" if operation=="pdf_to_word" else "result.xlsx")
    (write_docx if operation=="pdf_to_word" else write_xlsx)(ir,target,{**options,"merge_continuation_tables":False})
    if operation=="pdf_to_excel" and not ir.tables:
        _issue(ir,"NO_TABLE_DETECTED","未恢复可靠表格；识别文字保存在原文说明表，请框选表格重识别")
    if operation=="pdf_to_word":
        _issue(ir,"PDF_LAYOUT_RECONSTRUCTION","PDF 已重建为可编辑对象；复杂多栏、浮动对象及公式版式需查看回渲染校样")
    _check(cancelled)
    progress("rebuild",1,1)
    return EngineResult(ir,[result_file(target)],{"page_count":len(ir.pages),"tables":len(ir.tables)},
                        {"editable_tables":len(ir.tables),"editable_blocks":sum(b.kind!="image" for b in ir.blocks)})


def _split(path,options,work_dir,progress,cancelled):
    reader=open_pdf(path,options.get("password") or options.get("_password"))
    from app.core.config import settings
    if len(reader.pages)>getattr(settings,"document_tools_max_pages",200):
        raise ToolError("PDF_PAGE_LIMIT","PDF 页数超过当前处理上限")
    mode=options.get("split_mode","each")
    ir=DocumentIR(source_type="pdf",engine_manifest={"split":"pypdf","rasterized":False})
    files=[]
    if mode in {"crop","double"}:
        normalized=work_dir/"normalized.pdf"
        metadata,annotations=normalize_pdf(path,normalized,options.get("password") or options.get("_password"),cancelled)
        normalized_reader=open_pdf(normalized)
        selected=[options.get("page_index",0)] if mode=="crop" else [n for g in parse_page_groups(options.get("page_selection","all"),len(reader.pages)) for n in g]
        writer=PdfWriter()
        for index in selected:
            if not 0<=index<len(reader.pages):
                raise ToolError("PAGE_RANGE_INVALID","页面超出文档范围")
            g=metadata[index]; w,h=g["width_pt"],g["height_pt"]
            axis="x" if mode=="double" else options.get("axis","y")
            if axis not in {"x","y"}:
                raise ToolError("PDF_CUT_INVALID","切分方向必须为 x 或 y")
            length=w if axis=="x" else h
            cuts=validate_cuts([length/2] if mode=="double" else options.get("cuts_pt",[]),length)
            for start,end in zip(cuts,cuts[1:]):
                _check(cancelled)
                box=[start,0,end,h] if axis=="x" else [0,start,w,end]
                page=copy.copy(normalized_reader.pages[index])
                pdf_box=RectangleObject([box[0],h-box[3],box[2],h-box[1]])
                page.cropbox=pdf_box; page.mediabox=RectangleObject(pdf_box)
                page.trimbox=RectangleObject(pdf_box)
                writer.add_page(page)
                ir.mappings.append({"output_page_index":len(writer.pages)-1,"source_page_index":index,"bbox_pt":box,
                                    "coordinate_space":"visible-page-top-left-points","hidden_content_removed":False})
            progress("rebuild",selected.index(index)+1,len(selected))
        target=work_dir/"split.pdf"
        with target.open("wb") as stream:
            writer.write(stream)
        files.append(result_file(target))
        _issue(ir,"PDF_CROP_VIEWPORT","裁切分页仅改变可见区域，底层隐藏内容未物理删除；不保留交互注释及原数字签名")
        # Visible-only source index: no off-crop text in provenance exports.
        with pdfplumber.open(normalized) as pdf:
            for mapping in ir.mappings:
                p=pdf.pages[mapping["source_page_index"]]
                mapping["visible_text"]=" ".join(w["text"] for w in p.extract_words() if _inside(_box(w),mapping["bbox_pt"]))
    else:
        all_pages=[n for g in parse_page_groups(options.get("page_selection","all"),len(reader.pages)) for n in g]
        if mode in {"groups","extract"}:
            groups=parse_page_groups(options.get("groups","all"),len(reader.pages),options.get("duplicate_policy","keep"))
            if mode=="extract":
                groups=[[p for group in groups for p in group]]
        elif mode=="each":
            groups=[[p] for p in all_pages]
        elif mode=="every_n":
            n=int(options.get("every_n",1))
            if n<1:
                raise ToolError("PAGE_RANGE_INVALID","每组页数必须大于零")
            groups=[all_pages[i:i+n] for i in range(0,len(all_pages),n)]
        else:
            raise ToolError("PDF_SPLIT_MODE","未知分页模式")
        has_annotations=False
        for gi,group in enumerate(groups):
            _check(cancelled)
            writer=PdfWriter()
            writer.append(reader,pages=group,import_outline=False)
            for out_index,page in enumerate(writer.pages):
                # Preserve external links and ordinary notes; remove internal
                # jumps rather than retaining a destination outside this output.
                annots=[]
                for ref in page.get("/Annots",[]):
                    annot=ref.get_object(); action=annot.get("/A",{})
                    if "/Dest" in annot or action.get("/S") in {"/GoTo","/GoToR"} or annot.get("/Subtype")=="/Widget":
                        has_annotations=True
                        continue
                    annots.append(ref)
                if "/Annots" in page:
                    page[NameObject("/Annots")]=ArrayObject(annots)
                g=geometry(reader.pages[group[out_index]])
                ir.mappings.append({"output_file":gi,"output_page_index":out_index,"source_page_index":group[out_index],"bbox_pt":[0,0,g["width_pt"],g["height_pt"]]})
            target=work_dir/f"split-{gi+1:03}.pdf"
            with target.open("wb") as stream:
                writer.write(stream)
            files.append(result_file(target))
            progress("rebuild",gi+1,len(groups))
        if has_annotations:
            _issue(ir,"PDF_INTERACTIVE_REMOVED","已移除内部跳转和表单控件以避免无效目标；外部链接与普通注释保留")
        if reader.get_fields():
            _issue(ir,"PDF_SIGNATURE_INVALIDATED","重新生成的 PDF 不继承原件数字签名有效性，原件保持不变")
    return EngineResult(ir,files,{"output_files":len(files),"output_pages":len(ir.mappings)}, {"rasterized":False})


def split_suggestions(path,page_index=0,target_height_pt=842,axis="y",password=None):
    import tempfile
    with tempfile.TemporaryDirectory(prefix="rr-pdf-cuts-") as tmp:
        normalized=Path(tmp)/"normalized.pdf"
        metadata,_=normalize_pdf(path,normalized,password)
        if not 0<=page_index<len(metadata) or axis not in {"x","y"}:
            raise ToolError("PDF_CUT_INVALID","页码或切分方向无效")
        g=metadata[page_index]; length=g["height_pt"] if axis=="y" else g["width_pt"]
        target=float(target_height_pt or 842)
        if not math.isfinite(target) or target<10:
            raise ToolError("PDF_CUT_INVALID","目标页面尺寸必须大于 10 pt")
        protected=[]
        with pdfplumber.open(normalized) as pdf:
            page=pdf.pages[page_index]
            for word in page.extract_words():
                protected.append({"kind":"text","bbox_pt":_box(word)})
            for table in page.find_tables():
                for row in table.rows:
                    protected.append({"kind":"table_row","bbox_pt":list(row.bbox)})
            for im in page.images:
                protected.append({"kind":"image","bbox_pt":_box(im)})
        lo,hi=(1,3) if axis=="y" else (0,2)
        cuts=[]; start=0.0
        while start+target<length-10:
            desired=start+target
            candidates=[desired,*[region["bbox_pt"][edge] for region in protected for edge in (lo,hi)]]
            candidates=[c for c in candidates if start+target*.65<c<min(length-10,start+target*1.25)]
            def cost(c):
                crossings=sum(10000 if p["kind"]=="image" else 1000 for p in protected if p["bbox_pt"][lo]+.1<c<p["bbox_pt"][hi]-.1)
                return crossings+abs(c-desired)+(target*.3-(length-c) if length-c<target*.3 else 0)
            cut=min(candidates,key=cost)
            cuts.append(cut); start=cut
        return {"cuts_pt":cuts,"protected_regions":protected,"page":g|{"page_index":page_index}}
