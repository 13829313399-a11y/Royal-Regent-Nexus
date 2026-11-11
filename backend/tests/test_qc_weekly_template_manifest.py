"""The three explicitly selected workbook layouts must remain independent."""
import json
from pathlib import Path


def test_confirmed_weekly_workbook_contracts():
    source = Path(__file__).resolve().parents[1] / 'app/templates/qc-weekly/templates.json'
    templates = {item['id']: item for item in json.loads(source.read_text())}
    assert set(templates) == {'detail', 'group', 'internal'}
    assert all(item['verifiedSheetCount'] == 42 for item in templates.values())
    assert templates['detail']['headers'] == [
        '序号', '日期', '客户', '合同', '出口国', '货号', '产品名称', '数量', '装箱', '箱数',
        '结果', '报告', '生产部门', '验货机构', '验货问题', '第一责任人', '第二责任人', '备注']
    assert templates['detail']['summaryHeaders'] == [
        '厂区', '客户', '本周验货次数', '退货次数', '退货率', '退货原因', '香港跟客',
        '客人未退货由工厂自行返工&客人A0D单数', '备注']
    assert templates['group']['headers'] == [
        '厂区', '客户', '本周验货次数', '退货次数', '退货率', '退货原因', '香港跟客', '备注']
    assert templates['internal']['headers'] == [
        '客户', '本周验货次数', '退货次数', '合格率', '退货原因', '第一/二责任人', '处理明细', '备注']
    assert templates['group']['totalLabelColumn'] == 1
    assert templates['internal']['totalLabelColumn'] == 0
    assert templates['detail']['sourceSha256'] == 'a81ec70cbdd3ca94ecdd2f7d528342618b53f8be2da80291ed75c90a8bb8483d'
    assert templates['group']['sourceSha256'] == 'd5736ac17ad577c34c4ecdf2f8e4d1144a4763ba6fc6bc5cc1f46fcdae414e0d'
    assert templates['internal']['sourceSha256'] == 'a54a69b382f15d89e2b890f5e10154bbb8712fe22786f0dcc4df9d37513969f7'
