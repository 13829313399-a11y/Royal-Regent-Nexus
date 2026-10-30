"""Database-free layout cases; never evidence for a real order or payable."""
from copy import deepcopy
from decimal import Decimal

LONG_EVIDENCE = '合成凭据段落：核对数量、币种与原始单据；' * 40 + 'END-PRINT-EVIDENCE'


def print_cases():
    common = dict(month='2026-09', captured_at='2026-10-27T00:00:00+08:00',
                  metadata=[['使用状态', '合成排版样本，不是业务冻结依据'],
                            ['样本范围', '只核对文件与分页，不生成库存、应付或付款']])
    period = dict(name='费用汇总', headers=['币种', '本期正常费用', '本期损耗费用', '期末在制费用'],
                  rows=[['CNY', '10.00', '0.00', '2.00'], ['HKD', '0.00', '0.00', '0.00'],
                        ['USD', '0.01', '0.00', '0.01']])
    differences = dict(name='同源版本差异', headers=['原实发ID', '币种', '原版本金额', '新版本金额', '差额', '核对依据'],
                       rows=[['SYNTH-ISSUE-CNY', 'CNY', '15.00', '10.00', '-5.00', '合成正常费用版本差异，非负付款'],
                             ['SYNTH-ISSUE-USD', 'USD', '0.02', '0.01', '-0.01', '原实发、同币种比较']])
    for row in differences['rows']:
        assert Decimal(row[3])-Decimal(row[2]) == Decimal(row[4])
    cases = {
        'period-currencies': dict(common, kind='period', sheets=[period, differences]),
        'payments-zero': dict(common, kind='payments', sheets=[dict(name='当前全期余额汇总',
            headers=['币种', '有效应付', '已付核销', '未付余额', '待复核占用', '可继续核销'],
            rows=[['CNY', '12.00', '5.00', '7.00', '0.00', '7.00'],
                  ['HKD', '0.00', '0.00', '0.00', '0.00', '0.00'],
                  ['USD', '9999999999.99', '0.00', '9999999999.99', '0.00', '9999999999.99']])]),
        'settlement-zero': dict(common, kind='settlement', sheets=[dict(name='结算汇总',
            headers=['加工厂', '结算月份', '统计截止日期', '验收结算套数', '币种', '含税应付金额', '外厂确认凭据'],
            rows=[['合成加工厂：'+'长中文名称与English-Factory-'*5, '2026-09', '2026-09-30', 7, 'HKD', '0.00', LONG_EVIDENCE]])]),
        'wide-history': dict(common, kind='period', metadata=[['使用状态', '合成历史失效样本，仅供排版验证'],
            ['长凭据规则', '电子文件保留全文，纸面按既有行高上限显示；不能把截取部分当作完整凭据']],
            sheets=[period, dict(name='冻结来源索引',
                headers=['来源ID', '客户', '订单号', '货号', '货名', '来源事件ID', '业务日期', '币种', '原版本金额', '差额', '完整凭据'],
                rows=[[f'SYNTH-{i:04}', '合成客户：非真实业务', f'ORDER-{i:04}', f'0000{i:04}',
                       '合成超长货名／Long product name '*3, f'event-{i:04}-'+'a'*40, '2026-09-30',
                       'CNY', '10.00', '-0.01', LONG_EVIDENCE if i==0 else '=literal-evidence' if i==1 else f'合成分页依据 {i}']
                      for i in range(72)])]),
    }
    for label, report in cases.items():
        report['token'] = 'synthetic-print-'+label
    # Cases cannot share mutable sheet/metadata objects with each other.
    return {label:deepcopy(report) for label,report in cases.items()}
