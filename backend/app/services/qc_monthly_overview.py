"""Customer monthly overview: approved facts and explicit monthly supplements."""
from hashlib import sha256
import re
from app.services import qc_weekly_templates as weekly
from app.services.qc_inspection_summary import dump, text, report_date, confirmed_date
from fastapi import HTTPException

HEADERS=['客户','验货总单数','合格','退货','合格率','退货率','备注']
DETAIL_HEADERS=['客户分组','验货日期','客户','合同号','客名','货号','数量','装箱','总箱数','结果','生产拉','机构','退货原因']
ISSUE_HEADERS=['序号','问题描述','问题分析','纠正预防措施','完成情况','责任人']
DIST_HEADERS=['批次','比率','不合格品分布']
MAX_MANUAL_ROWS=50
META_FIELDS={'overview:preparer','overview:reportDate','overview:reviewer'}
for i in range(1,MAX_MANUAL_ROWS+1):
    META_FIELDS.update(f'overview:distribution:{i}:{f}' for f in ('count','rate','name'))
    META_FIELDS.update(f'overview:issue:{i}:{f}' for f in ('problem','analysis','action','completion','owner'))

def metadata_key(factory,customer=''):
    return sha256(('qc-monthly-overview:'+factory+':'+customer).encode()).hexdigest()

def validate(field,value):
    if field.endswith(':count') and not re.fullmatch(r'(?:0|[1-9][0-9]{0,8})?',value):
        raise HTTPException(422,'批次须为空白或非负整数')
    if field.endswith(':rate') and value and not re.fullmatch(r'(?:100(?:\.0+)?|[0-9]{1,2}(?:\.[0-9]{1,4})?)%',value):
        raise HTTPException(422,'比率请填写百分数，例如 20%；范围为 0% 至 100%')
    if field=='overview:reportDate' and value and not weekly.approved._date(value):
        raise HTTPException(422,'制表日期请填写 YYYY-MM-DD')

def build(factory,start,end,records,saved,fields,customers,customer_filter):
    meta=metadata_key(factory,customer_filter)
    def supplement(key,field):
        cell=saved.get((key,field),dict(value='',version=0))
        fields.setdefault(key,{})[field]=cell
        return cell['value']
    for field in sorted(META_FIELDS):supplement(meta,field)
    info={c['key']:c for c in customers}
    summaries={};details=[];issues=[]
    for row,item in records:
        key=row['customerKey'];values=row['values']
        if key not in summaries:
            returns=supplement(key,'returns');remark=supplement(key,'overviewRemark')
            summaries[key]=dict(id=key,customerKey=key,values=[info[key]['label'],0,0,returns,'','',remark],editableFields={3:'returns',6:'overviewRemark'})
        total=summaries[key]['values'];total[1]+=1;total[2]+=values[10]=='PASS'
        indices=[1,2,3,21,5,7,8,9,10,12,13,22]
        vals=[info[key]['label'],*[values[i] for i in indices]]
        editable={j+1:row['editableFields'][i] for j,i in enumerate(indices) if i in row['editableFields']}
        details.append({**row,'values':vals,'editableFields':editable})
        if values[10]=='FAIL' or any(text(values[i]).strip() for i in (14,18,19)):
            owners=' / '.join(dict.fromkeys(text(values[i]).strip() for i in (15,16) if text(values[i]).strip()))
            vals=[len(issues)+1,values[14],values[19],values[18],values[23],owners]
            editable={j:row['editableFields'][i] for j,i in [(1,14),(2,19),(3,18),(4,23)] if i in row['editableFields']}
            if not owners:editable[5]=f'detail:{row["id"]}:firstResponsible'
            issues.append({**row,'values':vals,'editableFields':editable,
                           'context':' · '.join(x for x in [values[2],row.get('poNo',''),values[5]] if x)})
    for row in summaries.values():
        v=row['values'];v[4]=v[2]/v[1] if v[1] else ''
        v[5]=int(v[3])/v[1] if v[1] and v[3]!='' else ''
    def manual_rows(section,names,minimum=1):
        last=max([0]+[i for i in range(1,MAX_MANUAL_ROWS+1) if any(fields[meta][f'overview:{section}:{i}:{name}']['value']!='' for name in names)])
        result=[]
        for i in range(1,min(MAX_MANUAL_ROWS,max(minimum,last+1))+1):
            fs=[f'overview:{section}:{i}:{name}' for name in names]
            vals=[fields[meta][f]['value'] for f in fs]
            if section=='distribution' and vals[0]!='':vals[0]=int(vals[0])
            result.append(dict(id=f'{section}:{i}',customerKey=meta,values=vals,editableFields=dict(enumerate(fs))))
        return result
    manual=manual_rows('issue',['problem','analysis','action','completion','owner'])
    for row in manual:
        row['values']=[len(issues)+1,*row['values']]
        row['editableFields']={i+1:f for i,f in row['editableFields'].items()}
        issues.append(row)
    snapshots=[]
    source=weekly.approved.query(factory,{'from':start[:4]+'-01-01','to':end},_report_snapshots=snapshots)
    if source['excluded'].get('missingProjection') or source['excluded'].get('invalidLineage'):
        raise HTTPException(503,'年度对比记录与验货汇总未对齐，请核对后重试')
    buckets={};history=[]
    for item,marker in snapshots:
        if any(item.get(f) for f in ('reference','referenceData','testData')):continue
        history.append([item,marker])
        if customer_filter and weekly.approved._customer(item)[0]!=customer_filter:continue
        day,_=report_date(item,confirmed_date(item));m=int(day[5:7]);n=buckets.setdefault(m,[0,0]);n[0]+=1;n[1]+=item.get('result')=='PASS'
    months=[dict(month=i,total=buckets.get(i,[0,0])[0],passed=buckets.get(i,[0,0])[1],rate=(buckets[i][1]/buckets[i][0] if i in buckets else '')) for i in range(1,13)]
    signatures=dict(id='signatures',customerKey=meta,values=[fields[meta]['overview:'+f]['value'] for f in ('preparer','reportDate','reviewer')],editableFields={i:'overview:'+f for i,f in enumerate(('preparer','reportDate','reviewer'))})
    return dict(headers=HEADERS,rows=list(summaries.values()),detailHeaders=DETAIL_HEADERS,details=details,
                months=months,distributionHeaders=DIST_HEADERS,distribution=manual_rows('distribution',['count','rate','name'],3),
                issueHeaders=ISSUE_HEADERS,issues=issues,signatures=signatures,metadataKey=meta,
                historyRevision=sha256(dump(history).encode()).hexdigest())
