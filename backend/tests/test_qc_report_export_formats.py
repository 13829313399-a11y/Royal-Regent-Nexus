"""Open the actual eight HTTP attachments and check data and preserved layout."""
import base64
from io import BytesIO
import json
import os
from pathlib import Path
import secrets
from uuid import uuid4
from zipfile import ZipFile

from openpyxl import load_workbook
from PIL import Image
import xlrd

import test_molding_sample_api
from test_molding_sample_api import login_as, make_client
from test_qc_daily_report import DAY, isolated_upstream, seed
from test_qc_weekly_excel import records as xls_records


def test_all_eight_report_attachments_keep_their_data_and_design(monkeypatch, tmp_path):
    monkeypatch.setattr(test_molding_sample_api, 'TEST_TMP_DIR', tmp_path/'main')
    monkeypatch.setenv('QC_DEPARTMENT_DATA_DIR', str(tmp_path/'companies'))
    monkeypatch.setenv('QC_DEPARTMENT_GATEWAY_TOKEN', secrets.token_hex(32))
    monkeypatch.setenv('QC_DOSSIER_EMERGENCY_DISABLED', 'true')
    with make_client(monkeypatch) as client:
        from app.services import qc_report_workbook as reports
        monkeypatch.setattr(reports, 'office_executable', lambda: None)
        isolated_upstream(monkeypatch)
        login_as(client, 'qc_inspector')
        frame = client.get('/api/qc-department/huaxing/api/health').json()['frame_url']
        seed(client, frame, [
            ('彩星','SYN-LEAD','合成通过样品','美国','100','PASS','','',''),
            ('合成审核客户','SYN-PHOTO','合成照片样品','英国','200','FAIL','多行原因一\n多行原因二','改完复核','合成责任人'),
        ])

        def post(path, body, params=None):
            response=client.post(frame+'api/'+path, json=body, params=params)
            assert response.status_code==200,(path,response.text)
            return response.json()

        review=client.get(frame+'api/inspection-sheet/review/entries').json()['items']
        bad=next(row for row in review if row['productNo']=='SYN-PHOTO')
        entry={'id':bad['id'],'revision':bad['revision']}
        revoked=post('inspection-sheet/review/revoke', {'entries':[entry],'requestKey':uuid4().hex})
        assert revoked['succeeded']==1
        pending=revoked['results'][0]['item']
        photo=BytesIO()
        Image.new('RGB',(110,70),'#d53936').save(photo,format='PNG')
        attached=post('inspection-sheet/review/entries/'+bad['id']+'/photos',{
            'name':'合成验收图片.png','content':base64.b64encode(photo.getvalue()).decode(),
            'revision':pending['revision'],'requestKey':uuid4().hex})
        assert len(attached['photos'])==1
        assert post('inspection-sheet/review/confirm',{'entries':[{'id':bad['id'],'revision':attached['revision']}],
            'requestKey':uuid4().hex})['succeeded']==1

        specs=[
            ('daily','daily','traderQDate','2026-11-27'),
            ('weekly','detail','weeklyRemark','周报人工备注'),
            ('weekly','issues','analysisReason','周图文原因'),
            ('monthly','orders','remark','订单对账补录'),
            ('monthly','tracking','analysisReason','月度整改原因'),
            ('monthly','quality','overviewRemark','月度签核备注'),
            ('yearly','annual-stats','remark','年报补录备注'),
            ('yearly','annual-issues','correctiveCompletion','已复核'),
        ]
        assert {kind for _,kind,_,_ in specs}==reports.KINDS
        proof={}
        folder=Path(os.environ['QC_REPORT_INTEGRITY_DIR']) if 'QC_REPORT_INTEGRITY_DIR' in os.environ else None
        for period,kind,field,mark in specs:
            day=DAY if period in ('daily','weekly') else DAY[:7]+'-01' if period=='monthly' else DAY[:4]+'-01-01'
            query={'kind':kind,'day':day,'customer':''}
            if kind=='annual-stats':query['result']='ALL'
            endpoint=frame+'api/report-workbook'
            first=client.get(endpoint,params=query).json()
            assert first['sheets']
            cell=next(c for c in first['cells'].values() if c['field'].split(':')[-1]==field)
            common={'customerKey':cell['customerKey'],'field':cell['field'],'baseVersion':cell['version'],
                    'value':mark,'requestKey':uuid4().hex}
            if cell.get('writeRevision'):
                post('report-workbook/save',{**common,'writeRevision':cell['writeRevision']},query)
            else:
                payload={**common,'date':day,'sourceRevision':first['sourceRevision']}
                if kind=='quality':payload.update(template='overview',customer='')
                post(period+'-templates/save',payload)
            fresh=client.get(endpoint,params=query).json()
            assert any(c['value']==mark for c in fresh['cells'].values()),kind
            if kind in ('daily','annual-stats'):
                path='daily-report/export' if kind=='daily' else 'approved-statistics/report/excel'
                filters={'date':day} if kind=='daily' else {'year':day[:4],'result':'ALL'}
                response=client.get(frame+'api/'+path,params={**filters,'customer':'','revision':fresh['sourceRevision']})
            else:
                issues=kind in ('issues','annual-issues')
                payload={'date':day,'customer':'','sourceRevision':fresh['sourceRevision']}
                if issues:payload.update(period=period,photoQuality='preview',allowPreviewFallback=False)
                else:payload.update(template=kind,versions=fresh['versions'])
                handle=post(('issue-reports' if issues else period+'-templates')+'/excel',payload)
                response=client.get(frame+handle['url'])
            assert response.status_code==200,(kind,response.text)
            data=response.content
            assert len(data)>4096 and response.headers['Content-Disposition'].startswith('attachment;')
            assert int(response.headers['Content-Length'])==len(data)
            proof[kind]=_check_workbook(kind,data,mark)
            if folder:
                folder.mkdir(parents=True,exist_ok=True)
                (folder/(kind+('.xls' if kind=='detail' else '.xlsx'))).write_bytes(data)
        if folder:(folder/'formats.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')

        from app.services import qc_monthly_excel, qc_monthly_templates
        long=qc_monthly_templates.query('huaxing',DAY,design_id='quality')
        issue_row=next(row for row in long['overview']['issues'] if row.get('context'))
        long['overview']['issues']=[issue_row]*45
        book=load_workbook(BytesIO(qc_monthly_excel.render(long,'quality','huaxing')))
        try:
            assert book.active.page_setup.fitToHeight==0
        finally:book.close()


def _check_workbook(kind,data,mark):
    if kind=='detail':
        book=xlrd.open_workbook(file_contents=data,formatting_info=True)
        assert book.nsheets==1 and data[:8]==bytes.fromhex('d0cf11e0a1b11ae1')
        sheet=book.sheet_by_index(0)
        assert sheet.ncols==18 and sheet.row_values(1)[:3]==['序号','日期','客户']
        assert sheet.cell_value(2,3) in ('0001','0002') and sheet.cell(2,1).ctype==xlrd.XL_CELL_DATE
        assert sheet.merged_cells and sheet.colinfo_map[14].width>20*256
        fmt=book.xf_list[sheet.cell_xf_index(1,0)]
        assert book.colour_map[fmt.background.pattern_colour_index]==(243,243,243)
        assert any(c.value==mark for row in sheet.get_rows() for c in row)
        assert any(op==6 for op,_ in xls_records(data))
        assert not any(c.ctype==xlrd.XL_CELL_ERROR for row in sheet.get_rows() for c in row)
        return {'format':'XLS','bytes':len(data),'sheets':book.sheet_names(),'visibleDataRows':2}
    with ZipFile(BytesIO(data)) as zip:
        assert zip.testzip() is None
        assert {'xl/workbook.xml','xl/styles.xml','[Content_Types].xml'}<=set(zip.namelist())
    book=load_workbook(BytesIO(data))
    try:
        assert all(s.sheet_state=='visible' for s in book)
        counts={'daily':1,'issues':1,'orders':2,'tracking':1,'quality':2,'annual-stats':1,'annual-issues':1}
        assert len(book.sheetnames)==counts[kind]
        all_cells=[c for sheet in book for row in sheet for c in row]
        assert any(c.value==mark for c in all_cells),(kind,mark)
        assert any(c.value==('合成照片样品' if kind=='annual-stats' else 'SYN-PHOTO') for c in all_cells),kind
        assert not any(c.data_type=='e' for c in all_cells)
        assert all(s.print_area for s in book)
        if kind=='daily':
            assert book.active.freeze_panes=='A4' and len(book.active.merged_cells.ranges)==2
            assert book.active.column_dimensions['A'].width>8 and book.active.print_title_rows=='$1:$3'
        elif kind in ('issues','tracking','annual-issues'):
            s=book.active
            assert s.freeze_panes=='A7' and s.page_setup.fitToWidth==1 and s.row_dimensions[6].height>=26
            assert len(s._images)==1 and s._images[0].anchor._from.col==12
            assert s.data_validations.count==1 and s.tables and s.merged_cells.ranges
        elif kind=='orders':
            assert book.sheetnames==['订单查询与对账','彩星交付样式']
            assert all(s.freeze_panes=='A7' and s.merged_cells.ranges for s in book)
        elif kind=='quality':
            assert book.sheetnames==['客户质量汇总与签核','验货明细与退货原因']
            assert len(book.active._charts)==1 and book.worksheets[1].freeze_panes=='A7'
            assert book.active.page_setup.fitToHeight==1 and book.worksheets[1].page_setup.fitToHeight==0
            assert any(c.data_type=='f' for c in all_cells)
        else:
            assert len(book.active._charts)==1 and len(book.active.merged_cells.ranges)>=4
        return {'format':'XLSX','bytes':len(data),'sheets':book.sheetnames,
                'merged':[len(s.merged_cells.ranges) for s in book],
                'pictures':sum(len(s._images) for s in book),'charts':sum(len(s._charts) for s in book)}
    finally:book.close()
