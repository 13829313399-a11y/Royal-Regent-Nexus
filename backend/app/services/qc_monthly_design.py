"""Three monthly workbooks projected from the same versioned monthly records."""
from collections import Counter

ORDERS = '序号 客户 客户分组 PO号 合同号 货号 产品名称 出口国 验货日期 日期来源 验货结果 报告状态 生产部门 验货机构 数量（件） 每箱件数 箱数 验货问题 第一责任人 第二责任人 备注'.split()
TRACKING_TITLE = '验货问题与整改跟踪表'
TRACKING = ['验货日期','客户','PO 号','货号','产品名称','合同号','生产部门','数量（件）','每箱件数','箱数',
            '验货结果','验货问题','现场照片','照片备注','原因分析','改善措施','第一责任人','第二责任人','完成情况']
TRACKING_GROUPS = [(5,'订单与产品'),(5,'合同与装箱'),(4,'验货问题与照片'),(5,'整改跟踪')]
TRACKING_WIDTHS = [108,90,135,96,138,110,96,86,84,72,80,155,145,150,165,178,100,100,96]
ORDERS[3] = 'PO 号'
QUALITY = ['客户分组','验货总单数','PASS 单数','FAIL 单数','有问题单数','实际退货数','合格率','退货率','月度备注']
CATALOG = [
    dict(id='orders',title='月度订单验货与对账明细',headers=ORDERS),
    dict(id='tracking',title=TRACKING_TITLE,headers=TRACKING,groups=TRACKING_GROUPS,widths=TRACKING_WIDTHS),
    dict(id='quality',title='客户月度质量汇总与签核表',headers=QUALITY),
]
NAMES = {spec['id']:spec['title'] for spec in CATALOG}


def project(row, columns, extra):
    return {**row, 'values':[row['values'][i] if isinstance(i,int) else extra[i] for i in columns],
            'editableFields':{j:row['editableFields'][i] for j,i in enumerate(columns) if i in row['editableFields']}}


def tracking_row(row, *, include=False):
    values = row['values']
    if not include and values[10] != 'FAIL' and not any(str(values[i]).strip() for i in (14,18,19)):
        return None
    columns = [1,2,'po',5,6,3,12,7,8,9,10,14,'photo',17,19,18,15,16,23]
    return project(row, columns, {'po':row['poNo'], 'photo':''})


def apply(data, records, kind):
    labels = {c['key']:c['label'] for c in data['customers']}
    table = []
    failures, problems = Counter(), Counter()
    for row, _ in records:
        v = row['values']
        key = row['customerKey']
        extra = dict(group=labels[key], po=row['poNo'], photo='', date='取自排期' if row['dateSource']=='schedule' else '已确认',
                     owner=' / '.join(dict.fromkeys(str(v[i]).strip() for i in (15,16) if str(v[i]).strip())))
        if kind=='orders':
            columns = [0,2,'group','po',3,5,6,4,1,'date',10,11,12,13,7,8,9,14,15,16,17]
        elif kind=='tracking':
            tracking = tracking_row(row)
            if tracking is not None:
                table.append(tracking)
            continue
        else:
            failures[key] += v[10]=='FAIL'
            problems[key] += bool(str(v[14]).strip())
            columns = ['group',1,2,3,21,5,7,8,9,10,12,13,22,14,19,18,23,'owner','po']
        projected=project(row,columns,extra)
        # Whitespace-only problems are blank in both the Excel count and the page.
        if kind=='quality' and not str(projected['values'][13]).strip():
            projected['values'][13]=''
        table.append(projected)
    templates = data['templates']
    data['templates'] = CATALOG
    legacy = data['tables']
    if kind == 'tracking':
        table.sort(key=lambda r:(r['values'][0],r['customerKey'],r['id']))
    data['tables'] = {kind:table}
    if kind=='orders':
        data['caixingHeaders'] = next(t['headers'] for t in templates if t['id']=='caixing')
        data['tables'].update(caixing=legacy['caixing'],summary=legacy['summary'])
    if kind=='quality':
        report=data['overview']
        report.update(headers=QUALITY,details=table,detailHeaders=[*report['detailHeaders'],'验货问题','原因分析','纠正预防措施','完成情况','责任人','PO 号'])
        for row in report['rows']:
            v=row['values']; key=row['customerKey']
            row.update(values=[*v[:3],failures[key],problems[key],*v[3:]],editableFields={5:'returns',8:'overviewRemark'})
    return data
