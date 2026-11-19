"""Native Excel export for the accepted two-sheet monthly reading layout."""
from datetime import date
from io import BytesIO
from math import ceil
from zipfile import ZipFile, ZIP_DEFLATED
from xml.etree import ElementTree as ET
import openpyxl
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.pagebreak import Break
from fastapi import HTTPException

def render(data):
    report=data['overview'];book=openpyxl.Workbook();summary=book.active;summary.title='月度汇总';detail=book.create_sheet('验货明细');cache={}
    period=data['dateFrom'][:7];edge=Side(style='thin',color='E3E8EB')
    def write(s,r,c,value='',heading=False):
        if isinstance(value,str) and (len(value)>32767 or any(ord(ch)<32 and ch not in '\n\r\t' for ch in value)):
            raise HTTPException(422,'月报单元格文字超长或包含非法字符，未截断原文')
        cell=s.cell(r,c,value);cell.font=Font(name='Arial',size=11,color='263238',bold=heading)
        if isinstance(value,str):cell.data_type='s'
        cell.alignment=Alignment(horizontal='center',vertical='center',wrap_text=True)
        cell.fill=PatternFill('solid',fgColor='F0F3F5' if heading else 'FFFFFF');cell.border=Border(bottom=edge)
        return cell
    def merge(s,r,a,b,value='',heading=False):
        for c in range(a,b+1):write(s,r,c,'',heading)
        if a!=b:s.merge_cells(start_row=r,start_column=a,end_row=r,end_column=b)
        return write(s,r,a,value,heading)
    def formula(s,r,c,expr,value):
        s.cell(r,c,expr);cache[(s.title,f'{get_column_letter(c)}{r}')]=value
        s.cell(r,c).number_format='0.00%' if c in (7,9) and s==summary else 'General'
    def header(s,r,headers):
        for c,value in enumerate(headers,1):write(s,r,c,value,True)
        s.row_dimensions[r].height=30
    for s in book:
        s.sheet_view.showGridLines=False;s.sheet_view.zoomScale=90
        s.page_margins=openpyxl.worksheet.page.PageMargins(left=.25,right=.25,top=.25,bottom=.25,header=0,footer=0)
    for c in range(1,13):summary.column_dimensions[get_column_letter(c)].width=11
    company=merge(summary,1,3,10,'华兴玩具制品（河源）有限公司');company.border=Border();summary.row_dimensions[1].height=22
    title=merge(summary,2,3,10,period+' 客户验货总结');title.font=Font(name='Arial',size=16,bold=True,color='263238');title.border=Border();summary.row_dimensions[2].height=34
    spans=[(1,2),(3,4),(5,5),(6,6),(7,8),(9,10),(11,12)]
    for i,label in enumerate(report['headers']):merge(summary,3,*spans[i],label,True)
    summary.row_dimensions[3].height=29
    for r,row in enumerate(report['rows'],4):
        v=row['values']
        for i,value in enumerate(v):merge(summary,r,*spans[i],int(value) if i==3 and value!='' else value)
        formula(summary,r,7,f'=IF(C{r}=0,"",E{r}/C{r})',v[4])
        formula(summary,r,9,f'=IF(OR(C{r}=0,F{r}=""),"",F{r}/C{r})',v[5])
        summary.row_dimensions[r].height=max(26,ceil(len(str(v[6]))/18)*15+8)
    total=4+len(report['rows']);count=sum(r['values'][1] for r in report['rows']);passed=sum(r['values'][2] for r in report['rows'])
    returns=sum(int(r['values'][3]) for r in report['rows']) if all(r['values'][3]!='' for r in report['rows']) else ''
    vals=['合计',count,passed,returns,passed/count if count else '',returns/count if returns!='' and count else '','']
    for i,value in enumerate(vals):merge(summary,total,*spans[i],value,True)
    for c,val in [(3,count),(5,passed)]:formula(summary,total,c,f'=SUM({get_column_letter(c)}4:{get_column_letter(c)}{total-1})',val)
    formula(summary,total,6,f'=IF(COUNT(F4:F{total-1})=ROWS(F4:F{total-1}),SUM(F4:F{total-1}),"")',returns)
    formula(summary,total,7,f'=IF(C{total}=0,"",E{total}/C{total})',vals[4])
    formula(summary,total,9,f'=IF(OR(C{total}=0,F{total}=""),"",F{total}/C{total})',vals[5]);summary.row_dimensions[total].height=28
    top=total+3
    for c,label in [(1,'月份'),(2,'合格率'),(9,'批次'),(10,'比率')]:write(summary,top,c,label,True)
    merge(summary,top,11,12,'不合格品分布',True);summary.row_dimensions[top].height=28
    for i,month in enumerate(report['months'],top+1):
        write(summary,i,1,f'{month["month"]}月');write(summary,i,2,month['rate']).number_format='0.00%';summary.row_dimensions[i].height=20
    distributions=[r for r in report['distribution'] if any(v!='' for v in r['values'])]
    for i in range(max(12,len(distributions))):
        v=distributions[i]['values'] if i<len(distributions) else ['','','']
        write(summary,top+1+i,9,v[0]);write(summary,top+1+i,10,v[1]);merge(summary,top+1+i,11,12,v[2])
        if i<len(distributions):summary.row_dimensions[top+1+i].height=max(20,ceil(len(str(v[2]))/18)*15+8)
    chart=BarChart();chart.type='col';chart.title='月份合格率对比';chart.y_axis.numFmt='0%';chart.y_axis.scaling.min=0;chart.y_axis.scaling.max=1;chart.y_axis.majorUnit=.2
    chart.add_data(Reference(summary,min_col=2,min_row=top,max_row=top+12),titles_from_data=True);chart.set_categories(Reference(summary,min_col=1,min_row=top+1,max_row=top+12));chart.legend=None;chart.width=12.2;chart.height=9.6
    chart.series[0].graphicalProperties.solidFill='BCCBD5';chart.series[0].graphicalProperties.line.noFill=True;summary.add_chart(chart,f'C{top}')
    footer=top+max(12,len(distributions))+3
    merge(summary,footer,1,12,'不合格退货问题分析及纠正预防措施处理报告').font=Font(name='Arial',size=11,bold=True,color='263238');summary.row_dimensions[footer].height=28
    issue_spans=[(1,1),(2,3),(4,6),(7,9),(10,11),(12,12)]
    for i,label in enumerate(report['issueHeaders']):merge(summary,footer+1,*issue_spans[i],label,True)
    issues=[r for r in report['issues'] if r.get('context') or any(v!='' for v in r['values'][1:])]
    for r,row in enumerate(issues or [{'values':['']*6}],footer+2):
        for i,value in enumerate(row['values']):
            if i==1 and row.get('context'):value=row['context']+'\n'+str(value)
            merge(summary,r,*issue_spans[i],value)
        summary.row_dimensions[r].height=max(45,max(ceil(len(str(v))/max(8,(b-a+1)*9)) for v,(a,b) in zip(row['values'],issue_spans))*15+22)
    sign=footer+3+max(1,len(issues));signature=report['signatures']['values']
    for a,b,label,value in [(1,4,'制表',signature[0]),(5,8,'日期',signature[1]),(9,12,'审核',signature[2])]:merge(summary,sign,a,b,label+'：'+value)
    summary.print_area=f'A1:L{sign}';summary.page_setup.orientation='portrait';summary.page_setup.paperSize=summary.PAPERSIZE_A4;summary.page_setup.fitToWidth=1;summary.page_setup.fitToHeight=0;summary.sheet_properties.pageSetUpPr.fitToPage=True
    widths=[15,15,15,19,25,20,12,10,12,10,10,13,23]
    for c,width in enumerate(widths,1):detail.column_dimensions[get_column_letter(c)].width=width
    title=merge(detail,1,4,9,period+' 客户验货明细');title.font=Font(name='Arial',size=16,bold=True,color='263238');title.border=Border();detail.row_dimensions[1].height=32;detail.row_dimensions[2].height=9
    header(detail,3,report['detailHeaders'])
    for r,row in enumerate(report['details'],4):
        for c,value in enumerate(row['values'],1):
            if c==2:value=date.fromisoformat(value)
            elif c in (7,8,9) and isinstance(value,str) and re_number(value):value=float(value)
            target=write(detail,r,c,value)
            if c==2:target.number_format='yyyy-mm-dd'
            if c in (7,8,9):target.number_format='#,##0' if isinstance(value,(int,float)) and float(value).is_integer() else '#,##0.####'
            if r%2:target.fill=PatternFill('solid',fgColor='FAFBFC')
        # Original supplied carton counts remain authoritative. Calculate only a missing count.
        qty,pack=row['values'][6:8]
        if row['values'][8]=='' and re_number(qty) and re_number(pack) and float(pack)>0:
            formula(detail,r,9,f'=G{r}/H{r}',float(qty)/float(pack))
        detail.row_dimensions[r].height=max(26,max(ceil(sum(2 if ord(ch)>255 else 1 for ch in str(v))/max(5,widths[i]-2)) for i,v in enumerate(row['values']))*14+8)
        if r>4 and (r-4)%22==0:detail.row_breaks.append(Break(id=r-1))
    detail.freeze_panes='A4';detail.print_title_rows='1:3';detail.print_area=f'A1:M{detail.max_row}';detail.page_setup.orientation='landscape';detail.page_setup.paperSize=detail.PAPERSIZE_A3;detail.page_setup.fitToWidth=1;detail.page_setup.fitToHeight=0;detail.sheet_properties.pageSetUpPr.fitToPage=True
    return save_cached(book,cache)


def save_cached(book,cache):
    stream=BytesIO();book.save(stream)
    # Write cached formula results for preview engines that do not recalculate on open.
    ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main';ET.register_namespace('',ns)
    with ZipFile(BytesIO(stream.getvalue())) as z:parts={name:z.read(name) for name in z.namelist()}
    for index,s in enumerate(book,1):
        path=f'xl/worksheets/sheet{index}.xml';root=ET.fromstring(parts[path])
        for cell in root.findall('.//{'+ns+'}c'):
            key=(s.title,cell.get('r'))
            if key not in cache:continue
            value=cache[key];v=cell.find('{'+ns+'}v')
            if v is None:v=ET.SubElement(cell,'{'+ns+'}v')
            if isinstance(value,str):cell.set('t','str');v.text=value
            else:cell.attrib.pop('t',None);v.text=str(value)
        parts[path]=ET.tostring(root,encoding='utf-8',xml_declaration=True)
    output=BytesIO()
    with ZipFile(output,'w',ZIP_DEFLATED) as z:
        for name,value in parts.items():z.writestr(name,value)
    return output.getvalue()

def re_number(value):
    import re
    return bool(re.fullmatch(r'[0-9]{1,15}(?:\.[0-9]{1,4})?',str(value)))
