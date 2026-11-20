"""Fill the approved, data-free monthly layout with the selected archive scope."""
from datetime import date
from io import BytesIO
from math import ceil
from fastapi import HTTPException
from openpyxl import load_workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.chart import BarChart, Reference
from openpyxl.drawing.image import Image
from openpyxl.drawing.spreadsheet_drawing import AnchorMarker, OneCellAnchor
from openpyxl.drawing.xdr import XDRPositiveSize2D
from openpyxl.utils import get_column_letter as letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.table import Table, TableStyleInfo
from PIL import Image as PILImage

from app.services import qc_monthly_excel as legacy
from app.services.qc_monthly_overview_excel import re_number, save_cached


def put(cell, value):
    if isinstance(value, str):
        if len(value)>32767 or ILLEGAL_CHARACTERS_RE.search(value):
            raise HTTPException(422,'单元格文字超长或含非法字符，请核对原记录')
        cell.value=value or None
        if value:cell.data_type='s'
    else:
        cell.value=value


class Sheet:
    def __init__(self, book, title, period, cache):
        self.model=book[title]
        self.model.title='_layout_'+title
        self.sheet=book.create_sheet(title)
        self.cache=cache
        s=self.sheet
        s.sheet_view.showGridLines=False
        for col,dim in self.model.column_dimensions.items():
            s.column_dimensions[col].width=dim.width
        s.page_setup.orientation='landscape'
        s.page_setup.paperSize=s.PAPERSIZE_A3
        s.page_setup.fitToWidth=1
        s.page_setup.fitToHeight=0
        s.sheet_properties.pageSetUpPr.fitToPage=True
        self.merges={}
        for region in self.model.merged_cells.ranges:
            self.merges.setdefault(region.min_row,[]).append((region.min_col,region.max_col))
        self.width=len(self.model.column_dimensions)
        for i in range(1,7):self.row(i,i)
        put(s['A3'],period)

    def row(self, r, model, values=None):
        s=self.sheet
        height = self.model.row_dimensions[model].height or 23
        header_heights = {1: 18 if self.model['A1'].value else 3, 2: 26, 3: 18, 4: 3, 5: 20}
        if model in header_heights:
            height = min(height, header_heights[model])
        elif model in (7, 8, 29):
            height = 21
        s.row_dimensions[r].height = height
        for col in range(1,self.width+1):
            original=self.model.cell(model,col)
            cell=s.cell(r,col)
            cell._style=original._style
            put(cell,values[col-1] if values is not None and col<=len(values) else original.value)
        for a,b in self.merges.get(model,[]):
            s.merge_cells(start_row=r,end_row=r,start_column=a,end_column=b)
        if values:
            lines=max(sum(max(1,ceil(sum(2 if ord(ch)>255 else 1 for ch in line)/max(4,s.column_dimensions[letter(c)].width-1))) for line in str(v).split('\n')) for c,v in enumerate(values,1))
            s.row_dimensions[r].height=min(409,max(s.row_dimensions[r].height,lines*15+5))

    def formula(self,r,c,expr,result):
        cell=self.sheet.cell(r,c)
        cell.value='='+expr
        self.cache[self.sheet.title,cell.coordinate]=result


def details(layout,rows,date_col,numbers):
    s=layout.sheet
    for r,entry in enumerate(rows,7):
        values=list(entry['values'])
        if values[date_col-1]:values[date_col-1]=date.fromisoformat(values[date_col-1])
        for col in numbers:
            v=values[col-1]
            if re_number(v):values[col-1]=float(v)
        layout.row(r,7+(r-7)%2,values)
    s.freeze_panes='A7'
    s.auto_filter.ref=f'A6:{letter(layout.width)}{len(rows)+6}'
    s.print_title_rows='1:6'


def caixing(layout,data):
    rows=data['tables']['caixing']
    details(layout,rows,1,[7,8,9])
    pos=8+len(rows)
    labels={c['key']:c['label'] for c in data['customers']}
    summaries=data['tables']['summary']
    if not summaries:
        layout.row(pos,10)
        layout.row(pos+1,11)
        pos+=4
    for item in summaries:
        layout.row(pos,10)
        if len(summaries)>1:put(layout.sheet.cell(pos,1),'彩星月度统计 · '+labels[item['customerKey']])
        layout.row(pos+1,11)
        r=pos+2
        v=list(item['values'])
        if v[3]!='':v[3]=int(v[3])
        layout.row(r,12,v)
        if len(summaries)==1:
            layout.formula(r,2,f'COUNTA(B7:B{6+len(rows)})',v[1])
            layout.formula(r,3,f'COUNTIF(J7:J{6+len(rows)},"PASS")',v[2])
        layout.formula(r,5,f'IF(OR(B{r}=0,D{r}=""),"",D{r}/B{r})',v[4])
        pos+=4
    layout.row(pos,14)


def tracking(layout,rows,factory,data):
    details(layout,rows,1,[8,9,10])
    s=layout.sheet
    s.row_dimensions[6].height=30
    table=Table(displayName='IssueLog',ref=s.auto_filter.ref)
    table.tableStyleInfo=TableStyleInfo(name='TableStyleLight1',showRowStripes=False,showColumnStripes=False)
    s.auto_filter.ref=None
    s.add_table(table)
    validation=DataValidation(type='list',formula1='"整改中,待复核,已复核"',allow_blank=True)
    s.add_data_validation(validation)
    validation.add(f'S7:S{max(7,6+len(rows))}')
    size=0
    raw_size=0
    width=int(s.column_dimensions['M'].width*7)-5
    for r,entry in enumerate(rows,7):
        photos=entry['photos']
        if not photos:continue
        height=min(530,len(photos)*84)
        s.row_dimensions[r].height=max(68,s.row_dimensions[r].height,height*.75)
        cols,w,h=legacy._photo_slots(len(photos),width,height)
        for i,photo in enumerate(photos):
            content=legacy._photo(factory,entry,photo,data.get('photoQuality','preview'),
                                  data.get('allowPreviewFallback',False),data.get('fallbackPhotos'))
            raw_size+=len(content)
            if raw_size>legacy.MAX_BYTES:raise HTTPException(422,'照片总量过大，请按客户筛选后分别导出')
            try:
                with PILImage.open(BytesIO(content)) as original:
                    if legacy._needs_excel_conversion(original.format,original.getexif().get(274,1)):
                        content=legacy.assets.display_png(content)
                image=Image(BytesIO(content))
            except (OSError,ValueError) as exc:
                raise HTTPException(422,'验货照片无法解码，请核对后重试') from exc
            size+=len(content)
            if size>legacy.MAX_BYTES:raise HTTPException(422,'图片总量过大，请分客户导出')
            scale=min(w/image.width,h/image.height,1)
            iw,ih=image.width*scale,image.height*scale
            x=8+(i%cols)*(w+8)+(w-iw)/2
            y=(s.row_dimensions[r].height/.75-height)/2+8+(i//cols)*(h+8)+(h-ih)/2
            marker=AnchorMarker(col=12,row=r-1,colOff=round(x*9525),rowOff=round(y*9525))
            image.anchor=OneCellAnchor(_from=marker,ext=XDRPositiveSize2D(round(iw*9525),round(ih*9525)))
            s.add_image(image)


def quality(layout,detail,data):
    report=data['overview']
    entries=report['details']
    details(detail,entries,2,[7,8,9])
    for r,entry in enumerate(entries,7):
        qty,pack,boxes=entry['values'][6:9]
        if boxes=='' and re_number(qty) and re_number(pack) and float(pack)>0:
            detail.formula(r,9,f'G{r}/H{r}',float(qty)/float(pack))
    rows=report['rows']
    last=6+len(entries)
    ref="'验货明细与退货原因'!"
    for r,group in enumerate(rows,7):
        v=list(group['values'])
        if v[5]!='':v[5]=int(v[5])
        layout.row(r,7,v)
        # Escape Excel wildcard characters in the customer label for literal matching.
        criterion=f'SUBSTITUTE(SUBSTITUTE(SUBSTITUTE(A{r},"~","~~"),"*","~*"),"?","~?")'
        match=f'{ref}$A$7:$A${last},"="&{criterion}'
        for col,condition in [(2,''),(3,f',{ref}$J$7:$J${last},"PASS"'),(4,f',{ref}$J$7:$J${last},"FAIL"'),(5,f',{ref}$N$7:$N${last},"<>"')]:
            layout.formula(r,col,f'COUNTIFS({match}{condition})',v[col-1])
        rates(layout,r,v)
    total=7+len(rows)
    sums=[sum(row['values'][i] for row in rows) for i in range(1,5)]
    returns=sum(int(row['values'][5]) for row in rows) if all(row['values'][5]!='' for row in rows) else ''
    v=['合计',*sums,returns,sums[1]/sums[0] if sums[0] else '',returns/sums[0] if returns!='' and sums[0] else '','']
    layout.row(total,10,v)
    for col in range(2,6):
        c=letter(col)
        layout.formula(total,col,f'SUM({c}7:{c}{total-1})',v[col-1])
    layout.formula(total,6,f'IF(COUNT(F7:F{total-1})<ROWS(F7:F{total-1}),"",SUM(F7:F{total-1}))',returns)
    rates(layout,total,v)
    layout.row(total+1,11)
    top=total+3
    layout.row(top,13)
    distributions=report['distribution']
    for i in range(max(12,len(distributions))):
        month=report['months'][i] if i<12 else None
        dist=list(distributions[i]['values']) if i<len(distributions) else ['','','']
        if dist[1]!='':dist[1]=float(str(dist[1]).rstrip('%'))/100
        values=[f'{i+1}月' if month else '',month['rate'] if month else '','','','','',*dist]
        layout.row(top+i+1,14,values)
        if i+1==int(data['dateFrom'][5:7]):layout.formula(top+i+1,2,f'G{total}',v[6])
        layout.sheet.cell(top+i+1,8).number_format='0.00%'
    s=layout.sheet
    chart=BarChart();chart.type='col';chart.title='月份合格率对比';chart.legend=None
    chart.add_data(Reference(s,min_col=2,min_row=top,max_row=top+12),titles_from_data=True)
    chart.set_categories(Reference(s,min_col=1,min_row=top+1,max_row=top+12))
    chart.width=8;chart.height=7;chart.y_axis.numFmt='0%';chart.y_axis.scaling.min=0;chart.y_axis.scaling.max=1
    chart.series[0].graphicalProperties.solidFill='BCCBD5'
    s.add_chart(chart,f'C{top}')
    pos=top+max(12,len(distributions))+2
    layout.row(pos,27);layout.row(pos+1,28)
    for pos,row in enumerate(report['issues'],pos+2):
        seq,problem,analysis,action,completion,owner=row['values']
        has_issue=row.get('context') or any(row['values'][1:])
        layout.row(pos,29,[seq if has_issue else '',row.get('context',''),problem,'',analysis,'',completion,owner,action])
    layout.row(pos+2,34)
    who,day,reviewer=report['signatures']['values']
    layout.row(pos+3,35,['制表',who,'','制表日期',day,'','审核',reviewer,''])


def rates(layout,r,v):
    layout.formula(r,7,f'IF(B{r}=0,"",C{r}/B{r})',v[6])
    layout.formula(r,8,f'IF(OR(F{r}="",B{r}=0),"",F{r}/B{r})',v[7])


def render(data,kind,factory):
    book=load_workbook(legacy.TEMPLATE_DIR/'approved-layouts.xlsx')
    models=list(book)
    cache={}
    def layout(name):return Sheet(book,name,data['dateFrom'][:7],cache)
    rows=data['tables'][kind]
    if kind=='orders':
        details(layout('订单查询与对账'),rows,9,[15,16,17])
        caixing(layout('彩星交付样式'),data)
    elif kind=='tracking':
        period_label={'weekly':'周视图','monthly':'月视图','yearly':'年视图'}[data.get('period','monthly')]
        target=Sheet(book,'问题照片与整改进度',period_label+'  '+data['dateFrom']+' 至 '+data['dateTo'],cache)
        tracking(target,rows,factory,data)
    else:
        quality(layout('客户质量汇总与签核'),layout('验货明细与退货原因'),data)
    for model in models:book.remove(model)
    for sheet in book:
        # Rows skipped between populated sections serve only as visual separators.
        for r in range(1, sheet.max_row + 1):
            if r not in sheet.row_dimensions:
                sheet.row_dimensions[r].height = 5
        sheet.print_area = sheet.dimensions
    book.active=0
    return save_cached(book,cache)
