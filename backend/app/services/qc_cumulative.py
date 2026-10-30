"""Factory-scoped cumulative workbook versions and one-step undo.

Immutable complete XLSX bytes, snapshots, index and undo pointer commit in one
SQLite transaction. Source inspection rows and their photos are never rolled back.
"""
from contextlib import contextmanager
from datetime import date,datetime,timedelta
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo
from io import BytesIO
from zipfile import ZipFile
from openpyxl import load_workbook
import base64
import binascii
import json
import os
import re
import sqlite3
import time

from fastapi import HTTPException
from app.core.config import settings
from app.services import qc_inspection_sheet as sheet, qc_workbook_xml as writer

TEMPLATES=Path(__file__).resolve().parents[1]/'templates'/'qc-cumulative'
SCHEMA='''
CREATE TABLE IF NOT EXISTS archives(id INTEGER PRIMARY KEY,factory TEXT NOT NULL,version_id INTEGER NOT NULL,filename TEXT NOT NULL,created_at TEXT NOT NULL,actor TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS base_inputs(id INTEGER PRIMARY KEY,factory TEXT NOT NULL,version_id INTEGER NOT NULL,filename TEXT NOT NULL,content BLOB NOT NULL,receipt TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS heads(factory TEXT PRIMARY KEY,current_id INTEGER NOT NULL,undo_id INTEGER,revision INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS versions(id INTEGER PRIMARY KEY,factory TEXT NOT NULL,content BLOB NOT NULL,snapshot TEXT NOT NULL,metadata TEXT NOT NULL,created_at TEXT NOT NULL,actor TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS jobs(factory TEXT NOT NULL,actor TEXT NOT NULL,request_key TEXT NOT NULL,digest TEXT NOT NULL,status TEXT NOT NULL,response TEXT,started REAL NOT NULL,pid INTEGER NOT NULL,PRIMARY KEY(factory,actor,request_key));
CREATE TABLE IF NOT EXISTS repairs(id INTEGER PRIMARY KEY,factory TEXT NOT NULL,before_head TEXT NOT NULL,after_head TEXT NOT NULL,mapping TEXT NOT NULL,created_at TEXT NOT NULL,actor TEXT NOT NULL,rolled_back INTEGER NOT NULL DEFAULT 0);
'''
def dump(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def stamp():return datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()

@contextmanager
def store(write=False):
    path=Path(settings.qc_department_data_dir).resolve()/'_cumulative'/'workbooks.sqlite3'
    path.parent.mkdir(parents=True,exist_ok=True)
    conn=sqlite3.connect(path,timeout=60);conn.row_factory=sqlite3.Row
    try:
        conn.execute('PRAGMA foreign_keys=ON');conn.executescript(SCHEMA)
        conn.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
        yield conn;conn.commit()
    except Exception:conn.rollback();raise
    finally:conn.close()

def template(factory):
    # Each factory needs its own approved template. Never clone Huaxing history to another factory.
    if not re.fullmatch('[a-z0-9-]+',factory):raise HTTPException(422,'厂区无效')
    folder=TEMPLATES/factory
    try:
        manifest=json.loads((folder/'manifest.json').read_text());content=(folder/'initial.xlsx').read_bytes()
    except (OSError,ValueError):raise HTTPException(503,'当前厂区尚未配置已验证的累计模板') from None
    if manifest.get('factory')!=factory or not manifest.get('validated') or sha256(content).hexdigest()!=manifest.get('sha256'):
        raise HTTPException(503,'累计模板校验未通过，原版本未修改')
    return content

def initialize(conn,factory):
    head=conn.execute('SELECT * FROM heads WHERE factory=?',(factory,)).fetchone()
    if head:return head
    content=template(factory)
    v=conn.execute('INSERT INTO versions(factory,content,snapshot,metadata,created_at,actor) VALUES(?,?,?,?,?,?)',(factory,content,'{}','{}',stamp(),'initial')).lastrowid
    conn.execute('INSERT INTO heads VALUES(?,?,NULL,0)',(factory,v))
    return conn.execute('SELECT * FROM heads WHERE factory=?',(factory,)).fetchone()

def head_status(head):
    return {'version':head['revision'],'undoAvailable':head['undo_id'] is not None,'initial':head['revision']==0}

def filters(body):
    if not isinstance(body,dict) or set(body)-{'dateFrom','dateTo','search','result'}:raise HTTPException(422,'导入筛选无效')
    f={k:body.get(k,'') for k in ('dateFrom','dateTo','search','result')}
    if any(not isinstance(v,str) or len(v)>500 for v in f.values()):raise HTTPException(422,'导入筛选无效')
    if f['result'] not in ('','PASS','FAIL','PENDING','REJ'):raise HTTPException(422,'结果筛选无效')
    today=datetime.now(ZoneInfo('Asia/Shanghai')).date();monday=today-timedelta(days=today.weekday())
    if not f['dateFrom'] and not f['dateTo']:f.update(dateFrom=monday.isoformat(),dateTo=(monday+timedelta(days=6)).isoformat())
    for k in ('dateFrom','dateTo'):
        if f[k]:
            try:
                if date.fromisoformat(f[k]).isoformat()!=f[k]:raise ValueError()
            except ValueError:raise HTTPException(422,'日期筛选格式无效') from None
    if f['dateFrom'] and f['dateTo'] and f['dateFrom']>f['dateTo']:raise HTTPException(422,'日期范围起止颠倒')
    return f

def select(items,f):
    selected=[];excluded=0;missing=[]
    for item in items:
        if item.get('testData') or item.get('referenceData'):excluded+=1;continue
        if item.get('sourceWarning') or item.get('lineageConflict'):
            # It may still match this user's range, so report it instead of silently dropping it.
            warning=item.get('sourceWarning') or item.get('lineageConflict')
        else:warning=''
        q=f['search'].strip().lower()
        if q and q not in ' '.join(text(item.get(k)) for k in ('customer','poNo','customerPo','productNo','productName','remark')).lower():continue
        if f['result'] and item['result']!=('FAIL' if f['result']=='REJ' else f['result']):continue
        archive=item.get('actualDate') or item.get('dateFrom')
        try:day=date.fromisoformat(archive)
        except (TypeError,ValueError):missing.append(item['id']);continue
        # Scope uses the same plan-overlap semantics as the existing page; actual date is used when no plan exists.
        start=item.get('dateFrom') or archive;end=item.get('dateTo') or start
        if f['dateFrom'] and end<f['dateFrom'] or f['dateTo'] and start>f['dateTo']:continue
        if warning:raise HTTPException(409,f"记录 {item['id']} 来源关联待核对：{warning}")
        selected.append({**item,'archiveDate':day.isoformat(),'week':(day-timedelta(days=day.weekday())).isoformat()})
    if missing:raise HTTPException(422,'记录缺少实际验货日期和排期开始日：'+', '.join(missing[:10]))
    return selected,excluded

def text(value):return '' if value is None else str(value)

# Only cells written to this workbook determine whether an import has changed.
# Photo URLs/counts and source revisions are not cells; completion is part of the reused detail export.
MAPPED_FIELDS={'id','archiveDate','week','actualDate','dateFrom','dateTo','customer','poNo','country',
    'productNo','productName','quantity','unitsPerCarton','cartonCount','result','remark',
    'inspectionProblem','otherRemark','firstResponsible','secondResponsible','responsible',
    'inspectionFactory','reportStatus','production','agency','customerPo','completion'}
def business(value):return {k:v for k,v in value.items() if k in MAPPED_FIELDS}

def snapshot(item):
    value={k:v for k,v in item.items() if k not in ('photos','photoDigests','photoWarning','updatedAt','cumulativeResult')}
    value['result']=item.get('cumulativeResult',item.get('result',''))
    return value

def needs_repair(conn,head):
    for identity in (head['current_id'],head['undo_id']):
        if identity is None:continue
        row=conn.execute('SELECT snapshot,metadata FROM versions WHERE id=?',(identity,)).fetchone()
        meta=json.loads(row['metadata'])
        if json.loads(row['snapshot']) and meta.get('formatVersion',0)<writer.FORMAT_VERSION:return True
        if meta.get('conversionReceipt',{}).get('format')=='.xls' and meta.get('conversionReceipt',{}).get('version',0)<2:return True
    return False

def validate(content):
    if len(content)>300*1024*1024:raise HTTPException(413,'累计工作簿超过 300 MB；原版本未修改')
    with ZipFile(BytesIO(content)) as z:
        if z.testzip() is not None:raise HTTPException(500,'工作簿生成校验失败')
    checked=load_workbook(BytesIO(content),read_only=True);checked.close()

def state(factory,items,scope):
    f=filters(scope)
    with store(True) as conn:
        head=initialize(conn,factory);result=head_status(head)
        meta=json.loads(conn.execute('SELECT metadata FROM versions WHERE id=?',(head['current_id'],)).fetchone()[0]);result['baseName']=meta.get('baseName','QC累计验货.xlsx');result['warning']=meta.get('styleWarnings',{}).get('message','')
        current=json.loads(conn.execute('SELECT snapshot FROM versions WHERE id=?',(head['current_id'],)).fetchone()[0]);repair_required=needs_repair(conn,head)
    try:
        selected,excluded=select(items,f)
        changed=sum(1 for r in selected if business(snapshot(r))!=business(current.get(r['id'],{})))
        result.update(count=len(selected),pending=changed,excluded=excluded,repairRequired=repair_required,error='累计版本待按已存快照修复；原文件仍可导出' if repair_required else '')
    except HTTPException as exc:result.update(count=0,pending=0,excluded=0,error=exc.detail)
    return {**result,'scope':f}

def download(factory):
    # Export is a read-only SELECT of an immutable, already persisted complete file.
    path=Path(settings.qc_department_data_dir).resolve()/'_cumulative'/'workbooks.sqlite3'
    if not path.exists():return template(factory),{'version':0,'undoAvailable':False,'initial':True}
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as conn:
        conn.row_factory=sqlite3.Row
        row=conn.execute('SELECT v.content,h.revision,h.undo_id FROM heads h JOIN versions v ON v.id=h.current_id WHERE h.factory=?',(factory,)).fetchone()
        if row is None:return template(factory),{'version':0,'undoAvailable':False,'initial':True}
        return bytes(row['content']),head_status(row)

def job(factory,actor,key):
    with store() as conn:
        row=conn.execute('SELECT * FROM jobs WHERE factory=? AND actor=? AND request_key=?',(factory,actor,key)).fetchone()
        if row is None:return {'status':'unknown','requestKey':key}
        if row['status']=='running':
            try:os.kill(row['pid'],0)
            except ProcessLookupError:return {'status':'interrupted','requestKey':key,'message':'服务在提交前中断，最新完整版本仍可用；刷新状态后重试。'}
        response=json.loads(row['response']) if row['response'] else {}
        return {**response,'outcome':response.get('status'),'status':row['status'],'requestKey':key}

def operate(factory,actor,body,items,action='import'):
    if action not in ('import','undo','replace'):raise HTTPException(422,'不支持的工作簿操作')
    expected={'requestKey','expectedVersion'}|({'scope','revisions'} if action=='import' else {'filename','content'} if action=='replace' else set())
    if action=='replace' and isinstance(body,dict) and 'contentType' in body:expected.add('contentType')
    if not isinstance(body,dict) or set(body)!=expected or type(body.get('expectedVersion')) is not int:
        raise HTTPException(422,'工作簿操作参数不正确')
    key=body['requestKey']
    if not isinstance(key,str) or not re.fullmatch('[a-f0-9-]{16,64}',key):raise HTTPException(422,'缺少有效操作编号')
    digest=sha256(dump({'action':action,**body}).encode()).hexdigest()
    with store(True) as conn:
        initialize(conn,factory)
        old=conn.execute('SELECT * FROM jobs WHERE factory=? AND actor=? AND request_key=?',(factory,actor,key)).fetchone()
        if old:
            if old['digest']!=digest:raise HTTPException(409,'操作编号已用于其他请求')
            if old['status']=='succeeded':return json.loads(old['response'])
            if old['status']=='failed':
                failure=json.loads(old['response']);raise HTTPException(failure['code'],failure['message'])
            raise HTTPException(409,'该操作尚未确认结束，请查询操作状态后刷新')
        conn.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?)',(factory,actor,key,digest,'running',None,time.time(),os.getpid()))
    try:
        if action=='replace':
            from app.services import qc_workbook_upload as upload
            try:original=base64.b64decode(body['content'],validate=True)
            except (ValueError,TypeError,binascii.Error):raise HTTPException(422,'文件编码无效') from None
            content,receipt=upload.prepare(body['filename'],original,template(factory),body.get('contentType'))
        with store(True) as conn:
            head=initialize(conn,factory)
            if head['revision']!=body['expectedVersion']:raise HTTPException(409,'累计工作簿已有新版本，请刷新后重试；未覆盖或撤销他人的操作')
            if needs_repair(conn,head):raise HTTPException(409,'累计版本需先按已存快照修复；原版本和撤销点未修改')
            if action=='replace':
                old=conn.execute('SELECT * FROM versions WHERE id=?',(head['current_id'],)).fetchone()
                same_input=conn.execute('SELECT 1 FROM base_inputs WHERE factory=? AND version_id=? AND content=?',(factory,head['current_id'],original)).fetchone()
                current_year=datetime.now(ZoneInfo('Asia/Shanghai')).year
                oldmeta=json.loads(old['metadata']);oldyear=oldmeta.get('annualYear') or int(oldmeta.get('baseUploadedAt',str(current_year))[:4])
                if (bytes(old['content'])==content or same_input) and oldyear==current_year:
                    result={**head_status(head),'status':'unchanged','count':0}
                else:
                    # Exact known exports retain their managed row bindings and stable IDs.
                    known=conn.execute('SELECT * FROM versions WHERE factory=? AND content=? ORDER BY id DESC LIMIT 1',(factory,original)).fetchone()
                    if known:
                        content,metadata,snap=upgrade_version(conn,factory,known)
                        if metadata.get('annualYear',current_year)!=current_year:
                            saved=json.loads(snap)
                            if saved or metadata.get('detailSheet'):
                                metadata['detailIds']=[]
                                content,metadata=writer.build(content,saved,saved,metadata)
                            # Old-year rows remain ordinary history; their IDs/undo cannot bind new-year records.
                            keep=('detailSheet','detailDigest','detailIds','formatVersion','clientLayouts','conversionReceipt','styleRepair','styleWarnings')
                            metadata={key:metadata[key] for key in keep if key in metadata};snap='{}'
                    else:
                        snap='{}';metadata={}
                        from app.services.qc_workbook_style import unresolved_black
                        uncertain=unresolved_black(content)
                        if uncertain:metadata['styleWarnings']=styles_warning(uncertain)
                    metadata['annualYear']=current_year
                    metadata.update(baseName=Path(body['filename']).name,baseUploadedAt=stamp())
                    if not known:metadata['conversionReceipt']=receipt
                    metadata['clientLayouts']=receipt['clientLayouts']
                    old_name=json.loads(old['metadata']).get('baseName','QC累计验货.xlsx')
                    archive=conn.execute('INSERT INTO archives(factory,version_id,filename,created_at,actor) VALUES(?,?,?,?,?)',(factory,head['current_id'],old_name,stamp(),actor)).lastrowid
                    new=conn.execute('INSERT INTO versions(factory,content,snapshot,metadata,created_at,actor) VALUES(?,?,?,?,?,?)',(factory,content,snap,dump(metadata),stamp(),actor)).lastrowid
                    conn.execute('INSERT INTO base_inputs(factory,version_id,filename,content,receipt,created_at) VALUES(?,?,?,?,?,?)',(factory,new,Path(body['filename']).name,original,dump(receipt),stamp()))
                    conn.execute('UPDATE heads SET current_id=?,undo_id=NULL,revision=revision+1 WHERE factory=?',(new,factory))
                    result={'version':head['revision']+1,'undoAvailable':False,'status':'replaced','archiveId':archive,'filename':metadata['baseName'],'count':0,'conversionReceipt':receipt,'warning':metadata.get('styleWarnings',{}).get('message','')}
            elif action=='undo':
                if head['undo_id'] is None:raise HTTPException(409,'没有可撤销的导入')
                conn.execute('UPDATE heads SET current_id=undo_id,undo_id=NULL,revision=revision+1 WHERE factory=?',(factory,))
                result={'version':head['revision']+1,'undoAvailable':False,'status':'undone','count':0}
            else:
                f=filters(body['scope']);selected,excluded=select(items,f)
                requested=body['revisions']
                if not isinstance(requested,dict) or any(not isinstance(k,str) or type(v) is not int for k,v in requested.items()):raise HTTPException(422,'记录版本无效')
                version=conn.execute('SELECT * FROM versions WHERE id=?',(head['current_id'],)).fetchone()
                previous=json.loads(version['snapshot']);current=dict(previous);metadata=json.loads(version['metadata']);changed=0
                year=metadata.get('annualYear')
                if year and any(date.fromisoformat(item['archiveDate']).year!=year for item in selected):raise HTTPException(422,f'当前底表年度为 {year}，所选记录跨年度，未导入')
                selection_changed=set(metadata.get('detailIds',[]))!={item['id'] for item in selected} or metadata.get('detailScope')!=f
                metadata['detailIds']=[item['id'] for item in selected];metadata['detailScope']=f
                # No photo table, bytes, URL, image library or network access is part of this snapshot.
                with sheet.store() as sources:
                    for item in selected:
                        entry=sheet.get(sources,factory,item['id'])
                        if not sheet.photo_revision_matches(sources,entry,requested.get(item['id'])) or not sheet.photo_revision_matches(sources,entry,item['revision']):
                            raise HTTPException(409,f"记录 {item['id']} 已变化，请刷新读取后重试")
                        saved=snapshot(item)
                        if business(previous.get(item['id'],{}))!=business(saved):changed+=1
                        current[item['id']]=saved
                if not selected or (not changed and not selection_changed):
                    result={**head_status(head),'status':'empty' if not selected else 'unchanged','count':0,'excluded':excluded}
                else:
                    content,newmeta=writer.build(bytes(version['content']),previous,current,metadata)
                    validate(content)
                    new=conn.execute('INSERT INTO versions(factory,content,snapshot,metadata,created_at,actor) VALUES(?,?,?,?,?,?)',
                        (factory,content,dump(current),dump(newmeta),stamp(),actor)).lastrowid
                    conn.execute('UPDATE heads SET current_id=?,undo_id=?,revision=revision+1 WHERE factory=?',(new,head['current_id'],factory))
                    result={'version':head['revision']+1,'undoAvailable':True,'status':'imported','count':changed,'excluded':excluded}
            result['requestKey']=key
            conn.execute("UPDATE jobs SET status='succeeded',response=? WHERE factory=? AND actor=? AND request_key=?",(dump(result),factory,actor,key))
            return result
    except Exception as exc:
        code=exc.status_code if isinstance(exc,HTTPException) else 500
        message=exc.detail if isinstance(exc,HTTPException) else '工作簿生成失败，原版本和撤销点未修改'
        with store(True) as conn:conn.execute("UPDATE jobs SET status='failed',response=? WHERE factory=? AND actor=? AND request_key=?",(dump({'code':code,'message':message}),factory,actor,key))
        if isinstance(exc,HTTPException):raise
        raise HTTPException(code,message) from exc


def repair(factory,actor,expected_version):
    """Explicit administrative migration, never called by download/status or live-source synchronization.

    Repair both the active file and its undo target from their own immutable snapshots.
    Keep every old version plus a CAS-protected receipt for reverting the whole migration.
    """
    with store(True) as conn:
        head=initialize(conn,factory)
        if head['revision']!=expected_version:raise HTTPException(409,'修复版本已变化，未修改')
        if not needs_repair(conn,head):return {**head_status(head),'status':'unchanged'}
        mapping={}
        for old_id in dict.fromkeys([head['current_id'],head['undo_id']]):
            if old_id is None:continue
            row=conn.execute('SELECT * FROM versions WHERE id=?',(old_id,)).fetchone()
            content,newmeta,snap=upgrade_version(conn,factory,row)
            if content==bytes(row['content']) and dump(newmeta)==row['metadata']:mapping[old_id]=old_id;continue
            validate(content);newmeta['repairedFrom']=old_id
            mapping[old_id]=conn.execute('INSERT INTO versions(factory,content,snapshot,metadata,created_at,actor) VALUES(?,?,?,?,?,?)',
                (factory,content,snap,dump(newmeta),stamp(),actor)).lastrowid
        conn.execute('UPDATE heads SET current_id=?,undo_id=?,revision=revision+1 WHERE factory=?',
            (mapping[head['current_id']],mapping.get(head['undo_id']),factory))
        after=dict(conn.execute('SELECT * FROM heads WHERE factory=?',(factory,)).fetchone())
        repair_id=conn.execute('INSERT INTO repairs(factory,before_head,after_head,mapping,created_at,actor) VALUES(?,?,?,?,?,?)',
            (factory,dump(dict(head)),dump(after),dump(mapping),stamp(),actor)).lastrowid
        return {**head_status(after),'status':'repaired','repairId':repair_id,'versions':mapping}


def rollback_repair(factory,repair_id,expected_version):
    with store(True) as conn:
        head=initialize(conn,factory)
        receipt=conn.execute('SELECT * FROM repairs WHERE id=? AND factory=?',(repair_id,factory)).fetchone()
        if receipt is None or receipt['rolled_back']:raise HTTPException(409,'修复记录不存在或已回退')
        after=json.loads(receipt['after_head'])
        if head['revision']!=expected_version or dict(head)!=after:raise HTTPException(409,'修复后已有操作，不能覆盖新的版本或撤销点')
        before=json.loads(receipt['before_head'])
        conn.execute('UPDATE heads SET current_id=?,undo_id=?,revision=revision+1 WHERE factory=?',
            (before['current_id'],before['undo_id'],factory))
        conn.execute('UPDATE repairs SET rolled_back=1 WHERE id=?',(repair_id,))
        return {'status':'repair-reverted','version':head['revision']+1,'undoAvailable':before['undo_id'] is not None}


def archives(factory):
    with store() as conn:
        return {'items':[dict(r) for r in conn.execute('SELECT id,filename,created_at AS archivedAt FROM archives WHERE factory=? ORDER BY id DESC',(factory,))]}

def archive_download(factory,identity):
    with store() as conn:
        row=conn.execute('SELECT v.content,a.filename FROM archives a JOIN versions v ON v.id=a.version_id AND v.factory=a.factory WHERE a.factory=? AND a.id=?',(factory,identity)).fetchone()
        if row is None:raise HTTPException(404,'归档不存在')
        return bytes(row['content']),Path(row['filename']).stem+'.xlsx'


def source_for_version(conn,factory,row):
    meta=json.loads(row['metadata'])
    for record in conn.execute('SELECT b.content,v.metadata,b.version_id FROM base_inputs b JOIN versions v ON v.id=b.version_id WHERE b.factory=? ORDER BY b.id DESC',(factory,)):
        if record['version_id']==row['id'] or (meta.get('baseUploadedAt') and json.loads(record['metadata']).get('baseUploadedAt')==meta.get('baseUploadedAt')):
            raw=bytes(record['content'])
            if raw.startswith(bytes.fromhex('D0CF11E0A1B11AE1')):return raw
    manifest=json.loads((TEMPLATES/factory/'manifest.json').read_text())
    if sha256(bytes(row['content'])).hexdigest() in manifest.get('legacyStyleHashes',[]):return (TEMPLATES/factory/'original.xls').read_bytes()
    return None

def upgrade_version(conn,factory,row):
    """Repair only proven source styles, then regenerate managed output from that version's own snapshot."""
    from app.services import qc_workbook_upload as upload,qc_workbook_style as styles
    content=bytes(row['content']);meta=json.loads(row['metadata']);saved=json.loads(row['snapshot'])
    source=source_for_version(conn,factory,row)
    if not meta.get('styleRepair') and source:
        baseline,receipt=upload.prepare('source.xls',source,template(factory))
        content,audit=styles.repair_fills(content,baseline,source,meta);meta['styleRepair']=audit
        meta['conversionReceipt']=receipt
    elif not source and not meta.get('styleRepair'):
        uncertain=styles.unresolved_black(content)
        if uncertain:meta['styleWarnings']=styles_warning(uncertain)
    if meta.get('baseUploadedAt'):meta.setdefault('annualYear',int(meta['baseUploadedAt'][:4]))
    if saved and meta.get('formatVersion',0)<writer.FORMAT_VERSION:
        if set(meta.get('bindings',{}))!=set(saved):raise HTTPException(422,'托管业务身份索引不完整，原工作簿保留')
        scope=meta.get('detailScope') or filters({});selected,_=select(list(saved.values()),scope)
        meta['detailScope']=scope;meta['detailIds']=[item['id'] for item in selected]
        content,meta=writer.build(content,saved,saved,meta)
    return content,meta,row['snapshot']


def styles_warning(cells):
    refs=[name+'!'+ref for name,addresses in cells.items() for ref in addresses]
    examples='、'.join(refs[:3])
    return {'message':f'发现 {len(refs)} 处未有可靠原表关联的黑色填充（{examples}），已原样保留；不能仅凭黑色判断损坏','cells':cells}
