"""Context-preserving OOXML style mapping and evidence-based legacy fill repair."""
from copy import deepcopy
from hashlib import sha256
import json
import xlrd
from lxml import etree as E
from app.services import qc_workbook_xml as w
from openpyxl.utils import get_column_letter

def key(node):
    if node is None:return None
    return (node.tag,tuple(sorted(node.attrib.items())),node.text or '',tuple(key(c) for c in node))

def intern(root,container,node):
    target=root.find(w.tag(container))
    if target is None:
        target=E.Element(w.tag(container));root.insert(0,target)
    wanted=key(node)
    for i,old in enumerate(target):
        if key(old)==wanted:return i
    target.append(deepcopy(node));target.set('count',str(len(target)));return len(target)-1

def black(fill):
    p=fill.find(w.tag('patternFill'))
    if p is None or p.get('patternType')!='solid':return False
    fg=p.find(w.tag('fgColor'))
    return fg is not None and fg.get('rgb','').upper() in ('FF000000','000000')

def signature(p,xf):
    return (key(p.styles.find(w.tag('fonts'))[int(xf.get('fontId','0'))]),key(p.styles.find(w.tag('borders'))[int(xf.get('borderId','0'))]),xf.get('numFmtId','0'))

def repair_fills(content,corrected_baseline,original,metadata=None):
    """Only an exact, trusted source lineage can call this; never infer damage from black alone."""
    p=w.Package(content);base=w.Package(corrected_baseline);xls=xlrd.open_workbook(file_contents=original,formatting_info=True,ragged_rows=True)
    xfs=p.styles.find(w.tag('cellXfs'));fills=p.styles.find(w.tag('fills'));bxfs=base.styles.find(w.tag('cellXfs'));bfills=base.styles.find(w.tag('fills'))
    changes=[];touched=set();replacements={}
    for src in xls.sheets():
        if src.name not in p.names() or src.name not in base.names():continue
        cells={c.get('r'):c for row in p.rows(src.name) for c in row}
        clean={c.get('r'):c for row in base.rows(src.name) for c in row}
        for ri in range(src.nrows):
            for ci in range(src.row_len(ri)):
                xf=xls.xf_list[src.cell_xf_index(ri,ci)];bg=xf.background
                # This exact automatic foreground/background context was wrongly forced to RGB black.
                if (bg.fill_pattern,bg.pattern_colour_index,bg.background_colour_index)!=(1,64,65):continue
                ref=get_column_letter(ci+1)+str(ri+1);cell=cells.get(ref);good=clean.get(ref)
                if cell is None or good is None:continue
                old=xfs[int(cell.get('s','0'))];expected=bxfs[int(good.get('s','0'))];fill=fills[int(old.get('fillId','0'))];correct=bfills[int(expected.get('fillId','0'))]
                if not black(fill) or black(correct) or signature(p,old)!=signature(base,expected):continue
                updated=deepcopy(old);updated.set('fillId',str(intern(p.styles,'fills',correct)))
                new_id=str(intern(p.styles,'cellXfs',updated));old_id=cell.get('s','0');cell.set('s',new_id)
                changes.append({'sheet':src.name,'cell':ref,'oldStyle':old_id,'newStyle':new_id,'sourceXF':src.cell_xf_index(ri,ci),'evidence':'solid/auto foreground 64/background 65; exact source lineage; font/border/number style match'})
                touched.add(src.name);replacements[(src.name,ref)]=new_id
    if metadata:
        for binding in metadata.get('bindings',{}).values():
            if binding.get('original'):
                row=E.fromstring(binding['original'])
                for cell in row:
                    target=replacements.get((binding['sheet'],cell.get('r')))
                    if target:cell.set('s',target)
                binding['original']=E.tostring(row,encoding='unicode')
    p.loaded={n:root for n,root in p.loaded.items() if n in touched}
    receipt={'version':1,'sourceSha256':sha256(original).hexdigest(),'cells':changes,'count':len(changes)}
    return (p.finish() if changes else content),receipt

def unresolved_black(content):
    p=w.Package(content);fills=p.styles.find(w.tag('fills'));fonts=p.styles.find(w.tag('fonts'));xfs=p.styles.find(w.tag('cellXfs'));found={}
    for name in p.names():
        refs=[]
        for row in p.rows(name):
            for cell in row:
                xf=xfs[int(cell.get('s','0'))]
                if not black(fills[int(xf.get('fillId','0'))]):continue
                color=fonts[int(xf.get('fontId','0'))].find(w.tag('color'))
                if color is not None and (color.get('rgb','').upper().endswith('FFFFFF') or color.get('theme')=='0'):continue
                refs.append(cell.get('r'))
        if refs:found[name]=refs
    return found

def copy_detail_sheet(p,content,name):
    """Map all style references by content, not source-local numeric identifiers."""
    source=w.Package(content);num_map={}
    source_nums=source.styles.find(w.tag('numFmts'));target_nums=p.styles.find(w.tag('numFmts'))
    if target_nums is None:target_nums=E.Element(w.tag('numFmts'));p.styles.insert(0,target_nums)
    for fmt in source_nums if source_nums is not None else []:
        match=next((f for f in target_nums if f.get('formatCode')==fmt.get('formatCode')),None)
        if match is None:
            number=max([163]+[int(f.get('numFmtId')) for f in target_nums])+1;match=deepcopy(fmt);match.set('numFmtId',str(number));target_nums.append(match)
        num_map[fmt.get('numFmtId')]=match.get('numFmtId')
    target_nums.set('count',str(len(target_nums)))
    maps={}
    for container in ('fonts','fills','borders'):
        maps[container]={i:intern(p.styles,container,node) for i,node in enumerate(source.styles.find(w.tag(container)))}
    for container in ('cellStyleXfs','cellXfs'):
        maps[container]={}
        for i,node in enumerate(source.styles.find(w.tag(container))):
            node=deepcopy(node)
            for attr,part in [('fontId','fonts'),('fillId','fills'),('borderId','borders')]:node.set(attr,str(maps[part][int(node.get(attr,'0'))]))
            if node.get('numFmtId') in num_map:node.set('numFmtId',num_map[node.get('numFmtId')])
            if node.get('xfId') is not None:node.set('xfId',str(maps['cellStyleXfs'][int(node.get('xfId'))]))
            maps[container][i]=intern(p.styles,container,node)
    root=deepcopy(source.sheet(source.names()[0]));p.add(name);p.loaded[name]=root
    for cell in root.findall('.//'+w.tag('sheetData')+'/'+w.tag('row')+'/'+w.tag('c')):
        cell.set('s',str(maps['cellXfs'][int(cell.get('s','0'))]))
        if cell.get('t')=='s':
            text=source.shared[int(cell.find(w.tag('v')).text)];cell[:]=[];cell.set('t','inlineStr');E.SubElement(E.SubElement(cell,w.tag('is')),w.tag('t')).text=text
    p.generated_names=getattr(p,'generated_names',[])
    for defined in source.book.findall(w.tag('definedNames')+'/'+w.tag('definedName')):
        copied=deepcopy(defined);copied.text=(copied.text or '').replace("'"+source.names()[0]+"'!","'"+name.replace("'","''")+"'!")
        p.generated_names.append((name,copied))
