"""Build synthetic examples from the same public fixtures used by API regression."""
from __future__ import annotations
import argparse
import ast
from io import BytesIO
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]


def build(destination, factory):
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

    if factory == 'huakang-a':
        fixture = fixtures('test_green_toys_po_integrity.py', {'LINES', 'html_po', 'recovery_template'}, mapping=a_mapping)
        customer = 'Green Toys'
        files = [('DEMO_GreenToys.html', fixture['html_po']())]
        content, rows = fixture['recovery_template'](), 8
    elif factory == 'huadeng':
        fixture = fixtures('test_customer_order_goliath.py', {'po', '_pdf_document', 'template'})
        customer = 'Goliath'
        files = [('DEMO_Goliath.pdf', fixture['po']())]
        content, rows = fixture['template'](), 1
    else:
        template = fixtures('test_customer_order_huaxing_unified.py', {'template', 'data'}, mapping=hx_mapping)
        fixture = fixtures('test_customer_order_disney_factory.py', {'disney_po', 'arguments'},
            template=template['template'], data=template['data'])
        args = fixture['arguments'](factory, fixture['disney_po']())
        customer = '迪士尼 / Disney'
        files, content, rows = args['po_files'], args['schedule_content'], 1
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
        '2. 在“客户原始 PO”上传同目录 DEMO 开头的 PDF 或 HTML 文件；在“客户现有排期”上传 DEMO_统一排期.xlsx。\n'
        '3. 来单日期选择 2026-11-09，点击“解析并进入预览”。\n'
        f'4. 应得到 {rows} 条明细。{reminder}核对表中货号、数量和交期后继续，不需要填写人工处理原因。\n'
        '5. 点击“确认并保存订单”，再到“订单台账与走货”查看保存的明细。重复保存相同资料不会重复新增。\n'
        '6. 回到导入预览，点击“确认警告并生成客户排期”下载新文件；也可到“排期文件历史”重新下载。原始演示文件保持不变。\n'
        '7. 在台账打开一条订单，发送给 PMC；到“本机部门收件”选择 PMC 并签收该版本。这些记录只在当前电脑，不会通知线上员工。\n'
        '8. 回到该订单登记一笔演示走货：数量 1、实际走货日期选当天或之前、出货单号 DEMO-SHIP-001；确认后查看走货记录及剩余数量，也可按界面填写原因试用冲销。\n'
        '9. 演示记录保留在本机 data 中。开始真实资料试用请另用一份从 ZIP 全新解压的包，避免与演示记录混在一起。\n', encoding='utf-8-sig')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('destination', type=Path)
    parser.add_argument('--factory', required=True, choices=['huakang-a', 'huakang-d', 'huaxing', 'huadeng'])
    args = parser.parse_args()
    build(args.destination, args.factory)
