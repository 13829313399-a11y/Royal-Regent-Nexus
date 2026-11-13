"""Monthly views of the approved archive; record-keyed report supplements only."""
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3

from fastapi import HTTPException
from app.core.config import settings
from app.services import qc_weekly_templates as weekly
from app.services.qc_inspection_summary import dump, text

HEADERS = ['序号','日期','客户','合同','出口国','货号','产品名称','数量','装箱','箱数','结果','报告','生产部门','验货机构','验货问题','第一责任人','第二责任人','备注']
CAIXING = [1,2,3,4,5,6,7,8,9,10,14,19,18,20,17]
ISSUES = [1,2,3,5,6,7,8,9,10,14,12,17]
TEMPLATES = [
    dict(id='caixing', title='彩星月度验货明细及汇总表', sourceFile='彩星验货汇总表.xls · 11月', headers=['日期','客户','合同','出口国','货号','产品名称','数量','装箱','箱数','结果','验货问题','原因分析','改善措施','不良次数','备注']),
    dict(id='all', title='月度验货明细表（全客户）', sourceFile='2026年每周验货情况统计表1.xls', headers=HEADERS),
    dict(id='issues', title='月度验货问题图文记录表', sourceFile='每周验货问题统计表.xlsx', headers=['日期','客户','合同','货号','产品名称','数量','装箱','箱数','结果','验货问题','生产','备注']),
    dict(id='customers', title='月度验货明细表（按客户）', sourceFile='2026年客户验货汇总.xls', headers=HEADERS),
]
DETAIL_FIELDS = {**weekly.DETAIL_FIELDS, 18: 'improvement', 19: 'analysisReason'}
DETAIL_FIELD = weekly.DETAIL_FIELD


def _source(factory, day):
    return weekly._source(factory, day, 'monthly')


def _path():
    return Path(settings.qc_department_data_dir).resolve() / '_monthly_reports' / 'monthly.sqlite3'


@contextmanager
def _store():
    path = _path(); path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10); conn.row_factory = sqlite3.Row
    try:
        conn.executescript(weekly.SCHEMA.replace('week', 'month'))
        conn.execute('BEGIN IMMEDIATE')
        yield conn
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally:
        conn.close()


def _supplements(factory, start):
    if not _path().exists(): return {}
    try:
        with closing(sqlite3.connect(_path().as_uri()+'?mode=ro', uri=True, timeout=10)) as conn:
            conn.row_factory = sqlite3.Row
            return {(r['customer'],r['field']):dict(value=r['value'],version=r['version']) for r in
                    conn.execute('SELECT * FROM cells WHERE factory=? AND month=?',(factory,start))}
    except sqlite3.Error as exc:
        raise HTTPException(503,'月报补充数据读取失败，请重试；已保存内容未被覆盖') from exc


def _detail(item, marker, index):
    row = weekly._detail(item, marker, index)
    row['values'].extend([text(item.get('improvement')),text((item.get('inspectionExecution') or {}).get('analysisReason')),''])
    row['editableFields'] = {i:f'detail:{row["id"]}:{field}' for i,field in DETAIL_FIELDS.items()
                             if isinstance(row['values'][i],str) and not row['values'][i].strip()}
    # References are from the same frozen approval as the text, never PO/name matching.
    row['photos'] = [dict(id=p['id'], name=p.get('name','验货照片')) for p in item.get('photos',[]) if isinstance(p,dict) and p.get('id')]
    return row


def _project(row, indices):
    return {**row, 'values':[row['values'][i] for i in indices],
            'editableFields':{j:row['editableFields'][i] for j,i in enumerate(indices) if i in row['editableFields']}}


def query(factory, day, customer=''):
    if customer and (not isinstance(customer,str) or not re.fullmatch('[a-f0-9]{64}',customer)):
        raise HTTPException(422,'客户筛选不正确')
    start,end,snapshots,revision = _source(factory,day)
    saved = _supplements(factory,start)
    customers,fields,caixing,issues,summary = {},{},[],[],{}
    rows=[]
    for item,marker in snapshots:
        key,info=weekly.approved._customer(item); customers[key]=info
        if customer and customer!=key: continue
        cells=fields.setdefault(key,{})
        row=_detail(item,marker,len(rows)+1)
        for i,field in row['editableFields'].items():
            cells[field]=saved.get((key,field),dict(value='',version=0))
            value=cells[field]['value']
            row['values'][i]=weekly.daily._quantity(value) if i==7 else value
        rows.append(_project(row,list(range(18))))
        if info['name']=='彩星':
            caixing.append(_project(row,CAIXING))
            cells['returns']=saved.get((key,'returns'),dict(value='',version=0))
            total=summary.setdefault(key,dict(id=key,customerKey=key,values=[start[:7],0,0,cells['returns']['value'],''],editableFields={3:'returns'}))
            total['values'][1]+=1
            total['values'][2]+=item.get('result')=='PASS'
        if str(row['values'][14]).strip(): issues.append(_project(row,ISSUES))
    for total in summary.values():
        v=total['values'];v[4]=int(v[3])/v[1] if v[3]!='' and v[1] else ''
    numbered=[];counts={}
    for row in rows:
        key=row['customerKey'];counts[key]=counts.get(key,0)+1
        numbered.append({**row,'values':[counts[key],*row['values'][1:]]})
    return dict(date=day,dateFrom=start,dateTo=end,sourceRevision=revision,templates=TEMPLATES,
                customers=list(customers.values()),customer=customer,fields=fields,
                tables=dict(all=rows,customers=numbered,caixing=caixing,issues=issues,summary=list(summary.values())),total=len(rows),
                summaryHeaders=['月份','验货总单数','合格单数','不合格(退货)单数','不良率'],
                scheduleCount=sum(r['dateSource']=='schedule' for r in rows),recordFieldsReadOnly=True)


def save(factory, actor, body):
    weekly._factory(factory)
    keys={'date','customerKey','field','value','baseVersion','sourceRevision','requestKey'}
    if not isinstance(body,dict) or set(body)!=keys: raise HTTPException(422,'月报保存参数不正确')
    field=body['field']; detail=DETAIL_FIELD.fullmatch(field) if isinstance(field,str) else None
    if ((field!='returns' and (not detail or detail[2] not in DETAIL_FIELDS.values()))
        or not isinstance(body['customerKey'],str) or not re.fullmatch('[a-f0-9]{64}',body['customerKey'])
        or type(body['baseVersion']) is not int or body['baseVersion']<0
        or not isinstance(body['requestKey'],str) or not re.fullmatch('[a-zA-Z0-9-]{16,80}',body['requestKey'])
        or not isinstance(body['sourceRevision'],str) or not re.fullmatch('[a-f0-9]{64}',body['sourceRevision'])
        or not isinstance(body['value'],str) or len(body['value'])>4000):
        raise HTTPException(422,'月报字段或版本不正确')
    if field=='returns' and not re.fullmatch(r'(?:0|[1-9][0-9]{0,8})?',body['value']):
        raise HTTPException(422,'实际退货次数须为空白或非负整数')
    if detail and detail[2]=='quantity' and not re.fullmatch(r'(?:[0-9]{1,15}(?:\.[0-9]{1,4})?)?',body['value']):
        raise HTTPException(422,'数量须为空白或非负数字，最多四位小数')
    fingerprint=sha256(dump(body).encode()).hexdigest()
    start,_,snapshots,revision=_source(factory,body['date'])
    actor_id=str(actor['id'])
    with _store() as conn:
        old=conn.execute('SELECT * FROM writes WHERE factory=? AND actor=? AND request_key=?',(factory,actor_id,body['requestKey'])).fetchone()
        if old:
            if old['fingerprint']!=fingerprint: raise HTTPException(409,'保存请求标识已用于不同内容')
            return json.loads(old['response'])
        if revision!=body['sourceRevision']:
            raise HTTPException(409,dict(code='source_changed',message='本月验货记录已变化，请刷新核对；补充草稿仍保留'))
        eligible=[(item,marker) for item,marker in snapshots if weekly.approved._customer(item)[0]==body['customerKey']]
        if field=='returns':
            if not eligible or text(eligible[0][0].get('customer')).strip()!='彩星':
                raise HTTPException(422,'实际退货次数只用于彩星月度汇总')
        else:
            record=next(((item,marker) for item,marker in eligible if item['id']==detail[1]),None)
            if not record or field not in _detail(*record,1)['editableFields'].values():
                raise HTTPException(422,'只能补录本客户的空白月报明细；已有审核原值不能覆盖')
        identity=(factory,start,body['customerKey'],field)
        old=conn.execute('SELECT * FROM cells WHERE factory=? AND month=? AND customer=? AND field=?',identity).fetchone()
        current=dict(value=old['value'],version=old['version']) if old else dict(value='',version=0)
        if current['version']!=body['baseVersion']:
            raise HTTPException(409,dict(code='cell_conflict',message='此格已被其他操作修改，请选择保留内容',current=current))
        version=current['version']+(body['value']!=current['value'])
        result=dict(customerKey=body['customerKey'],field=field,value=body['value'],version=version)
        stamp=datetime.now(timezone.utc).isoformat()
        if body['value']!=current['value']:
            conn.execute('INSERT INTO cells VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(factory,month,customer,field) DO UPDATE SET value=excluded.value,version=excluded.version,actor=excluded.actor,updated_at=excluded.updated_at',(*identity,body['value'],version,actor_id,stamp))
            conn.execute('INSERT INTO changes(factory,month,customer,field,old_value,new_value,version,actor,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(*identity,current['value'],body['value'],version,actor_id,stamp))
        conn.execute('INSERT INTO writes VALUES(?,?,?,?,?,?)',(factory,actor_id,body['requestKey'],fingerprint,dump(result),stamp))
        return result
