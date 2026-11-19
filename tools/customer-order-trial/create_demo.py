"""Build synthetic examples from the same public fixtures used by API regression."""
from __future__ import annotations
import argparse
import ast
from io import BytesIO
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]


def build(destination, factory, green_toys_only=False, huaxing_customer=None, single_customer=None):
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(destination.parent / 'backend'))
    import openpyxl
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    from app.services import customer_order_unified as service
    from app.services import customer_order_huaxing_unified as hx_mapping
    from app.services.huakang_a_order_legacy import unified_schedule as a_mapping

    def fixtures(filename, names, **values):
        source = ROOT / 'backend' / 'tests' / filename
        tree = ast.parse(source.read_text(encoding='utf-8'))
        nodes = []
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name in names:
                node.decorator_list = []
                nodes.append(node)
            elif isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id in names for target in node.targets):
                nodes.append(node)
        namespace = dict(BytesIO=BytesIO, openpyxl=openpyxl, service=service, PdfWriter=PdfWriter,
            DictionaryObject=DictionaryObject, NameObject=NameObject, DecodedStreamObject=DecodedStreamObject, **values)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), namespace)
        if not names.issubset(namespace):
            raise RuntimeError(f'Demo fixture changed: {filename}')
        return namespace

    if single_customer in {'spin', 'simba'}:
        fixture = fixtures('test_huadeng_trial_inputs.py', {'TRIAL_TEXT', 'converted_po'})
        customer, files, rows = single_customer.title(), [(f'DEMO_{single_customer}.xlsx', fixture['converted_po'](single_customer))], 1
        template = fixtures('test_customer_order_unified.py', {'_template_bytes'}, unified=service)
        content = template['_template_bytes']()
    elif single_customer == 'jakks':
        from reportlab.pdfgen import canvas
        fixture = fixtures('test_jakks_supplementary_contract.py', {'SAMPLES', 'contract_text'})
        stream = BytesIO(); doc = canvas.Canvas(stream, pagesize=(1000,1200))
        doc.setFont('Helvetica', 9)
        for i, line in enumerate(fixture['contract_text'](formal=True).splitlines()):
            doc.drawString(25, 1160-i*14, line)
        doc.save()
        customer, files, rows = 'Jakks', [('DEMO_Jakks.pdf', stream.getvalue())], 1
        template = fixtures('test_customer_order_unified.py', {'_template_bytes'}, unified=service)
        content = template['_template_bytes']()
    elif single_customer == 'casdon':
        pdf = fixtures('test_customer_order_goliath.py', {'_pdf_document'})
        fixture = fixtures('test_casdon_original_sku.py', {'casdon_po'}, _pdf_document=pdf['_pdf_document'])
        customer, files, rows = 'Casdon', [('DEMO_Casdon.pdf', fixture['casdon_po']())], 2
        template = fixtures('test_customer_order_unified.py', {'_template_bytes'}, unified=service)
        content = template['_template_bytes']()
    elif single_customer == 'zuru':
        fixture = fixtures('test_customer_order_zuru_unified.py', {'po_book', 'data'})
        customer, files, rows = 'ZURU', [('DEMO_ZURU_PO.xlsx', fixture['data'](fixture['po_book']()))], 2
        template = fixtures('test_customer_order_unified.py', {'_template_bytes'}, unified=service)
        content = template['_template_bytes']()
    elif factory == 'huakang-a':
        fixture = fixtures('test_green_toys_po_integrity.py', {'LINES', 'html_po', 'recovery_template'}, mapping=a_mapping)
        customer = 'Green Toys'
        files = [('DEMO_GreenToys.html', fixture['html_po']())]
        content, rows = fixture['recovery_template'](), 8
    elif factory == 'huadeng':
        fixture = fixtures('test_customer_order_goliath.py', {'po', '_pdf_document', 'template'})
        customer = 'Goliath'
        files = [('DEMO_Goliath.pdf', fixture['po']())]
        content, rows = fixture['template'](), 1
    elif factory == 'huaxing' and huaxing_customer:
        from reportlab.pdfgen import canvas
        template = fixtures('test_customer_order_huaxing_unified.py', {'template', 'data'}, mapping=hx_mapping)
        content = template['data'](template['template'](huaxing_customer))
        if huaxing_customer == 'edu':
            fixture = fixtures('test_customer_order_edu_pdf.py', {'page'})
            pages, customer, rows = [fixture['page']()], 'EDU', 1
        elif huaxing_customer == 'dickie':
            fixture = fixtures('test_customer_order_dickie.py', {'STANDARD_PAGES'})
            pages, customer, rows = fixture['STANDARD_PAGES'], 'Dickie', 1
        else:
            fixture = fixtures('test_customer_order_caixing.py', {'PLAYMATES_PO_TEXT'})
            pages, customer, rows = [fixture['PLAYMATES_PO_TEXT']], '彩星', 2
        stream = BytesIO()
        doc = canvas.Canvas(stream, pagesize=(1000,1200))
        for page in pages:
            doc.setFont('Helvetica', 9)
            for i,line in enumerate(page.splitlines()): doc.drawString(25,1160-i*14,line)
            doc.showPage()
        doc.save()
        files = [(f'DEMO_{huaxing_customer}.pdf',stream.getvalue())]
    else:
        template = fixtures('test_customer_order_huaxing_unified.py', {'template', 'data'}, mapping=hx_mapping)
        fixture = fixtures('test_customer_order_disney_factory.py', {'disney_po', 'arguments'},
            template=template['template'], data=template['data'])
        args = fixture['arguments'](factory, fixture['disney_po']())
        customer = '迪士尼 / Disney'
        files, content, rows = args['po_files'], args['schedule_content'], 1
    if single_customer:
        book = openpyxl.load_workbook(BytesIO(content))
        for sheet in book:
            sheet.freeze_panes = 'H4'
            for row in sheet.iter_rows(min_row=4):
                for cell in row:
                    if cell.value not in {'取消单', '已走货订单'}: cell.value = None
        stream = BytesIO(); book.save(stream); book.close(); content = stream.getvalue()
    for name, data in files:
        (destination / ('DEMO_' + Path(name).name if not name.startswith('DEMO_') else name)).write_bytes(data)
    (destination / 'DEMO_统一排期.xlsx').write_bytes(content)
    reminder = (
        '会看到“节假日待复核”的日期码提醒；这是提示信息，没有勾选项，本组合成资料无需补录。'
        if factory == 'huadeng' else '本组合成资料无需补录或勾选人工确认项。'
    )
    (destination / '演示操作.txt').write_text(
        '这些文件是自动测试用的合成示例，不是客户真实订单，不能用于生产。\n\n'
        f'1. 在本厂客户中选择 {customer}，台账资料类型保持“正式 PO”。\n'
        '2. 在“客户原始 PO”上传同目录 DEMO 开头的 PDF、Excel 或 HTML 文件；在“客户现有排期”上传 DEMO_统一排期.xlsx。\n'
        '3. 来单日期选择 2026-11-09，点击“解析并进入预览”。\n'
        f'4. 应得到 {rows} 条明细。' + ('彩星另显示1条分组行，不计入上述明细数。' if huaxing_customer == 'caixing' else '') + f'{reminder}核对表中货号、数量和交期后继续，不需要填写人工处理原因。\n'
        '5. 点击“确认并保存订单”，再到“订单台账与走货”查看保存的明细。重复保存相同资料不会重复新增。\n'
        '6. 回到导入预览，点击“确认警告并生成客户排期”下载新文件；也可到“排期文件历史”重新下载。原始演示文件保持不变。\n'
        '7. 在台账打开一条订单，发送给 PMC；到“本机部门收件”选择 PMC 并签收该版本。这些记录只在当前电脑，不会通知线上员工。\n'
        '8. 回到该订单登记一笔演示走货：数量 1、实际走货日期选当天或之前、出货单号 DEMO-SHIP-001；确认后查看走货记录及剩余数量，也可按界面填写原因试用冲销。\n'
        '9. 演示记录保留在本机 data 中。开始真实资料试用请另用一份从 ZIP 全新解压的包，避免与演示记录混在一起。\n', encoding='utf-8-sig')
    if factory == 'huakang-a' and not green_toys_only and not single_customer:
        # ZURU uses the same public three-sheet headers; no private PO/history is
        # copied into delivery. Keep this blank template reusable for first use.
        zuru = destination / 'ZURU'
        zuru.mkdir()
        fixture = fixtures('test_customer_order_zuru_unified.py', {'po_book', 'data'})
        (zuru / 'DEMO_ZURU_PO.xlsx').write_bytes(fixture['data'](fixture['po_book']()))
        template_fixture = fixtures('test_customer_order_unified.py', {'_template_bytes'}, unified=service)
        book = openpyxl.load_workbook(BytesIO(template_fixture['_template_bytes']()))
        for sheet in book:
            sheet.freeze_panes = 'H4'
            for row in sheet.iter_rows(min_row=4):
                for cell in row:
                    if cell.value not in {'取消单', '已走货订单'}:
                        cell.value = None
        book.save(zuru / 'ZURU统一排期空白模板.xlsx')
        book.close()
        (zuru / 'ZURU试用说明.txt').write_text(
            '本目录的DEMO订单是合成测试资料，不是生产订单。\n'
            '选择华康A的ZURU，上传DEMO_ZURU_PO.xlsx及ZURU统一排期空白模板.xlsx。\n'
            '解析应得到2行：9560-S001数量100，9560-S004-MB数量200；美元总额750，港币不自动换算。\n'
            '可直接保存到本机台账或生成排期，不需要勾选核对或填写原因。旧版分类入单功能已由此流程替代。\n'
            '真实试用时上传自己的普通ZURU PDF/Excel PO。首次可使用此空白统一模板；以后上传已保存的统一排期继续追加。\n'
            '原周排期、MA及库存表不是统一模板，不会自动迁入历史订单。\n', encoding='utf-8-sig')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('destination', type=Path)
    parser.add_argument('--factory', required=True, choices=['huakang-a', 'huakang-d', 'huaxing', 'huadeng'])
    parser.add_argument('--green-toys-only', action='store_true')
    parser.add_argument('--single-customer', choices=['casdon','jakks','goliath','simba','spin','zuru'])
    parser.add_argument('--huaxing-customer', choices=['caixing','edu','dickie'])
    args = parser.parse_args()
    build(args.destination, args.factory, args.green_toys_only, args.huaxing_customer, args.single_customer)
