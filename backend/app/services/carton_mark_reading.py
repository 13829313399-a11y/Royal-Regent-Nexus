"""Native structure hints and focused review issues; never new print values."""
import json
import re
from collections import defaultdict
from openpyxl.utils.cell import coordinate_to_tuple

from app.services.carton_mark_ai_pilot import Evidence


def structure(source):
    cells={c.id:c for c in source['cells']}
    by_location={c.location:c for c in source['cells']}
    sheets={}
    for cell in source['cells']:
        name=cell.location.rsplit('!',1)[0]
        if name not in sheets:
            role=('reference' if cell.kind=='reference_cell' or re.search(r'翻译|translation|旧稿|历史|example|catalog',name,re.I)
                  else 'support_data' if re.search(r'数据|data|UPC|GTIN|条码目录',name,re.I) else 'print_source')
            sheets[name]=dict(name=name,role_hint=role,face_copies=source.get('face_copies',{}).get(name,{}),cell_ids=[],front_ids=[],side_ids=[])
        sheet=sheets[name];sheet['cell_ids'].append(cell.id)
        face=source.get('ownership',{}).get(cell.id)
        if face:sheet[face+'_ids'].append(cell.id)
    repeated=defaultdict(list)
    for note in source['notes']:
        if note.kind=='current_note':repeated[note.text].append(note.id)
    rows=[]
    for row in source.get('detail_rows',[]):
        columns=[]
        for key in sorted(row['cell_ids']):
            cell=cells[key];sheet,coord=cell.location.rsplit('!',1);_,col=coordinate_to_tuple(coord)
            from openpyxl.utils import get_column_letter
            label=by_location.get(f"{sheet}!{get_column_letter(col)}{row['header_row']}")
            if label:columns.append(dict(label_id=label.id,label=label.text,value_id=cell.id,native_value=cell.text))
        rows.append(dict(id=row['id'],required_po_id=row['po_id'],columns=columns))
    return dict(current_detail_rows=rows,worksheets=list(sheets.values()),face_blocks=source.get('blocks',[]),native_display_links=source.get('native_links',{}),
                repeated_note_ids=[ids for ids in repeated.values() if len(ids)>1],
                instruction='这是本地原生结构提示，不是最终结论。先分清当前印刷、辅助明细、历史示例和共用要求，再排箱面。辅助表可提供本单数据，但需能与当前原稿明确对应；不得凭相同值拼接不同订单。参考表仅提供制版参考。')


def evidence(source):
    return Evidence(id='S1',kind='source_structure',location='本地原稿结构',text=json.dumps(structure(source),ensure_ascii=False,separators=(',',':')))


def provider_evidence(source):
    """Current rows first; hide variable example values when detail rows exist.

    The authoritative source is untouched and still drives validation/provenance.
    Only obvious adjacent variable labels inside an explicit front/side template
    qualify; addresses, company names, requirements and units remain visible.
    """
    rows=source.get('detail_rows',[]);current={key for row in rows for key in row['cell_ids']}
    template_values=set()
    if rows:
        grid={}
        for cell in source['cells']:
            sheet,coord=cell.location.rsplit('!',1);r,col=coordinate_to_tuple(coord)
            grid.setdefault((sheet,r),[]).append((col,cell))
        variable=r'^(?:customerpo|purchaseorder(?:no)?|ordernumber|orderno|pono|itemno|itemnumber|supplieritemno|customeritemno|customersku|sku|description|itemdescription|qty|quantity|cartonno|cartonnumber|ctnno|barcode|gtin|upc|ean)$'
        for entries in grid.values():
            entries.sort(key=lambda item:item[0])
            for i,(_,label) in enumerate(entries[:-1]):
                if not re.fullmatch(variable,re.sub(r'[^a-z0-9]','',label.text.lower())):continue
                for _,cell in entries[i+1:]:
                    if source.get('ownership',{}).get(cell.id)!=source.get('ownership',{}).get(label.id):break
                    if re.search(r'[:：]\s*$',cell.text):break
                    if re.fullmatch(r'PCS(?:/CTN)?|KGS?|LBS|CM|MM|OF|/',cell.text.strip(),re.I):continue
                    if cell.id in source.get('ownership',{}):template_values.add(cell.id)
                    else:break
    candidates=[c.model_copy(update=dict(kind='template_example_value',text='示例占位；当前业务值必须选S1列出的本次明细value_id')) if c.id in template_values else c for c in source['cells']]
    candidates.sort(key=lambda c:0 if c.id in current else 1)
    return [evidence(source)]+candidates+source['notes']


def model_issues(raw,source):
    """Only source-cited questions are retained; questions cannot alter facts."""
    try:
        data=json.loads(raw);items=data.get('uncertainties',[])
    except (ValueError,TypeError,AttributeError):return []
    if not isinstance(items,list):return []
    known={e.id:e for e in source['cells']+source['notes']};result=[]
    for item in items[:20]:
        if not isinstance(item,dict):continue
        ids=item.get('source_ids');message=item.get('message')
        if (not isinstance(ids,list) or not 1<=len(ids)<=20 or any(not isinstance(k,str) or k not in known for k in ids)
                or not isinstance(message,str) or not 1<=len(message.strip())<=300):continue
        result.append(dict(kind='question',message=message.strip(),field_ids=[],sources=list(dict.fromkeys(known[k].location for k in ids))))
    return result


def review_issues(records,source,mode,questions,image_warnings=()):
    result=[]
    if mode=='needs_mapping':
        result.append(dict(kind='layout',message='AI 排版未通过校验。当前预览仅按原稿文字整理，需要在高级调整中核实箱面和字段位置。',field_ids=[],sources=[]))
    for r,record in enumerate(records):
        for panel in record['panels']:
            for field in panel['fields']:
                if field['placeholder']:
                    result.append(dict(kind='missing_value',message=f"第{r+1}组{'正唛' if panel['face']=='front' else '侧唛'}：请补充或核实 {field['label']}",field_ids=[field['id']],sources=field['sources']))
            if len(panel['barcodes'])>1:
                result.append(dict(kind='barcode_mapping',message=f"第{r+1}组{'正唛' if panel['face']=='front' else '侧唛'}包含{len(panel['barcodes'])}个条码，请核实是否同面印刷及其商品对应关系。",field_ids=[],sources=[]))
    for note in source['notes']:
        if note.id.startswith('F'):
            result.append(dict(kind='formula',message='该公式未保存显示结果，请在高级调整中补充确定值，或在原稿重新计算并保存。',field_ids=[],sources=[note.location]))
    if mode=='ai':
        from app.services.carton_mark_flexible import constraints
        limits=constraints(source);missing=set()
        for record in records:
            present={kind for panel in record['panels'] for kind in panel.get('symbols',[])}
            for key,kind,name in [('fragile','fragile','易碎'),('up','this_side_up','朝上'),('dry','keep_dry','防潮')]:
                if limits[key] and kind not in present:missing.add(name)
        if missing:result.append(dict(kind='graphics',message='原稿涉及'+ '、'.join(sorted(missing))+'标识，当前预览未放入；请对照原稿确认是否需要及印刷位置。',field_ids=[],sources=[]))
    if image_warnings:
        result.append(dict(kind='images',message='部分图片参考未完整读取，图案和图内要求仍需对照原稿；可在高级记录中查看已有参考图及读取提示。',field_ids=[],sources=[]))
    result+=questions
    seen=set();unique=[]
    for item in result:
        key=(item['message'],tuple(item['field_ids']),tuple(item['sources']))
        if key not in seen:seen.add(key);unique.append(item)
    return unique
