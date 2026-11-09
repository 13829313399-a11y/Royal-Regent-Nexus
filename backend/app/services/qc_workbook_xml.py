"""Shared OOXML reader and lossless XLS conversion support for summary history import."""
from datetime import date, datetime
from io import BytesIO
import math
import posixpath
import re
import unicodedata
from zipfile import ZipFile, ZIP_DEFLATED
from lxml import etree as E

from fastapi import HTTPException
from openpyxl.utils import get_column_letter, column_index_from_string
from openpyxl.utils.datetime import to_excel

S='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
P='http://schemas.openxmlformats.org/package/2006/relationships'
C='http://schemas.openxmlformats.org/package/2006/content-types'
D='http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing'
A='http://schemas.openxmlformats.org/drawingml/2006/main'
for prefix,ns in [('r',R),('xdr',D),('a',A)]:E.register_namespace(prefix,ns)
def tag(name):return '{'+S+'}'+name
def xml(node):return E.tostring(node,encoding='utf-8',xml_declaration=True)
def text(value):return '' if value is None else str(value)
def normalized(value):
    if isinstance(value,float) and value.is_integer():value=int(value)
    return ' '.join(unicodedata.normalize('NFKC',text(value)).split()).casefold()

CLIENTS=['ZURU','Dickie','EDU','彩星','360','SHUSHUPAPA','MMI','银辉','MAXX','BUZZBEE','SEASONS']
TARGETS={normalized(n):n+('' if n in ('MMI','银辉','MAXX') else '行验货') for n in CLIENTS}
TARGETS['buzz bee']='BUZZBEE行验货'
SECOND={'BUZZBEE行验货','SEASONS行验货'}
PROTECTED={'新明自检','迪奇自检','新明退货','退货未报','Dickie行验货 (2)'}
HEAD1=['客户','合同','出口国','货号','产品名称','数量','装箱','箱数','结果','验货问题','第一责任人','第二责任人','备注']
HEAD2=['Contract No.','客名/國家','產品編號','產品名称','數量','装箱','箱数','结果','工厂','报告','问题','责任人','备注']


class Package:
    def __init__(self,content):
        with ZipFile(BytesIO(content)) as z:self.parts={n:z.read(n) for n in z.namelist()}
        self.book=E.fromstring(self.parts['xl/workbook.xml']);self.sheets=self.book.find(tag('sheets'))
        self.original_order=[s.get('name') for s in self.sheets]
        self.rels=E.fromstring(self.parts['xl/_rels/workbook.xml.rels'])
        self.types=E.fromstring(self.parts['[Content_Types].xml'])
        self.styles=E.fromstring(self.parts['xl/styles.xml'])
        self.shared=[]
        if 'xl/sharedStrings.xml' in self.parts:
            self.shared=[''.join(e.itertext()) for e in E.fromstring(self.parts['xl/sharedStrings.xml'])]
        self.loaded={};self.wrap_styles={}
        props=self.book.find(tag('workbookPr'));self.epoch=datetime(1904,1,1) if props is not None and props.get('date1904') in ('1','true') else datetime(1899,12,30)
    def names(self):return [s.get('name') for s in self.sheets]
    def path(self,name):
        sheet=next(s for s in self.sheets if s.get('name')==name)
        rel=next(r for r in self.rels if r.get('Id')==sheet.get('{'+R+'}id'))
        p=rel.get('Target');return p.lstrip('/') if p.startswith('/') else posixpath.normpath('xl/'+p)
    def sheet(self,name):
        if name not in self.loaded:self.loaded[name]=E.fromstring(self.parts[self.path(name)])
        return self.loaded[name]
    def rows(self,name):return self.sheet(name).find(tag('sheetData'))
    def values(self,row):
        values={}
        for c in row.findall(tag('c')):
            v=c.find(tag('v'));value=v.text if v is not None else ''
            if c.get('t')=='s':value=self.shared[int(value)] if value else ''
            elif c.get('t')=='inlineStr':value=''.join(c.find(tag('is')).itertext()) if c.find(tag('is')) is not None else ''
            elif c.get('t') not in ('str','e','b') and value:
                try:value=float(value)
                except ValueError:pass
            values[column_index_from_string(re.sub(r'\d','',c.get('r')))]=value
        return values
    def cell(self,row,col,value,style='0'):
        if len(text(value))>32767 or any(ord(c)<32 and c not in '\r\n\t' for c in text(value)):
            raise HTTPException(422,'单元格文字超长或含不可显示字符，未截断原文')
        c=E.SubElement(row,tag('c'),{'r':get_column_letter(col)+row.get('r'),'s':str(style)})
        if isinstance(value,date):value=to_excel(value,self.epoch)
        if isinstance(value,(int,float)) and math.isfinite(value):E.SubElement(c,tag('v')).text=str(value)
        else:
            c.set('t','inlineStr');t=E.SubElement(E.SubElement(c,tag('is')),tag('t'))
            t.set('{http://www.w3.org/XML/1998/namespace}space','preserve');t.text=text(value)
        return c

    def second(self,name):
        if name in getattr(self,'layouts',{}):return self.layouts[name]==2
        for row in self.rows(name):
            first=normalized(self.values(row).get(1))
            if first==normalized('Contract No.'):return True
            if first==normalized('客户'):return False
        return name in SECOND
    def client_names(self):
        return [name for name in self.names() if name not in PROTECTED and any(normalized(self.values(row).get(1)) in (normalized('客户'),normalized('Contract No.')) for row in self.rows(name))]
    def profile(self,name):
        second=self.second(name);blocks=[];current=None;latest_date=None
        def styles(row):return {column_index_from_string(re.sub(r'\d','',c.get('r'))):c.get('s','0') for c in row.findall(tag('c'))}
        for row in sorted(self.rows(name),key=lambda r:int(r.get('r'))):
            vals=self.values(row)
            if isinstance(vals.get(1),(int,float)) and vals[1]>30000 and not any(normalized(vals.get(c)) for c in range(2,14)):
                latest_date=row;current=None
            elif normalized(vals.get(1))==normalized('Contract No.' if second else '客户'):
                current={'date':latest_date,'header':row,'data':[]};blocks.append(current)
            elif current is not None and vals.get(1 if second else 2) and vals.get(3 if second else 4):
                current['data'].append(row)
        # A fresh annual template may retain empty formatted rows instead of old orders.
        if not any(block['data'] for block in blocks):
            for block in blocks:
                header=int(block['header'].get('r'))
                blank=next((row for row in self.rows(name) if int(row.get('r'))>header and not any(self.values(row).values()) and row.findall(tag('c'))),None)
                if blank is not None:block['data']=[blank]
        valid=[block for block in blocks if block['data']]
        if not valid:raise HTTPException(422,'客户模板缺少有效表头或样式行：'+name)
        block=valid[-1];body={}
        for row in block['data']:body.update(styles(row))
        widths={i:13 for i in range(1,15)}
        cols=self.sheet(name).find(tag('cols'))
        if cols is not None:
            for col in cols:
                for i in range(int(col.get('min')),min(14,int(col.get('max')))+1):widths[i]=float(col.get('width','13'))
        return {'date':styles(block['date'] if block['date'] is not None else block['header']),
            'header':styles(block['header']),'data':body,'widths':widths,
            'templateRows':{'date':int(block['date'].get('r')) if block['date'] is not None else None,'header':int(block['header'].get('r')),'data':[int(r.get('r')) for r in block['data']]}}
    def finish(self):
        defined=self.book.find(tag('definedNames'))
        if defined is not None:
            for name in defined:
                old=name.get('localSheetId')
                if old is not None and int(old)<len(self.original_order):
                    original=self.original_order[int(old)]
                    if original in self.names():name.set('localSheetId',str(self.names().index(original)))
        for name,node in getattr(self,'generated_names',[]):
            if defined is None:defined=E.SubElement(self.book,tag('definedNames'))
            node.set('localSheetId',str(self.names().index(name)));defined.append(node)
        for name,root in self.loaded.items():
            old=self.parts.get(self.path(name))
            if old and E.tostring(root)==E.tostring(E.fromstring(old)):continue
            rows=root.find(tag('sheetData'));rows[:]=sorted(rows,key=lambda r:int(r.get('r')))
            dim=root.find(tag('dimension'))
            if dim is not None:root.remove(dim) # optional; readers calculate from cells, never trust legacy whole-sheet dimensions
            # Keep OOXML worksheet child order valid after inserting merges and drawings.
            order=['sheetPr','dimension','sheetViews','sheetFormatPr','cols','sheetData','sheetCalcPr','sheetProtection','protectedRanges','scenarios','autoFilter','sortState','dataConsolidate','customSheetViews','mergeCells','phoneticPr','conditionalFormatting','dataValidations','hyperlinks','printOptions','pageMargins','pageSetup','headerFooter','rowBreaks','colBreaks','customProperties','cellWatches','ignoredErrors','smartTags','drawing','legacyDrawing','legacyDrawingHF','picture','oleObjects','controls','webPublishItems','tableParts','extLst']
            root[:]=sorted(root,key=lambda n:order.index(E.QName(n).localname) if E.QName(n).localname in order else len(order))
            self.parts[self.path(name)]=xml(root)
        self.parts['xl/workbook.xml']=xml(self.book);self.parts['xl/_rels/workbook.xml.rels']=xml(self.rels)
        self.parts['xl/styles.xml']=xml(self.styles);self.parts['[Content_Types].xml']=xml(self.types)
        result=BytesIO()
        with ZipFile(result,'w',ZIP_DEFLATED) as z:
            for name,content in self.parts.items():z.writestr(name,content)
        return result.getvalue()
