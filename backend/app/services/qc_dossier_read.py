"""Authenticated detail projection. Only mode=ro connections; no recovery-on-read."""
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import json
import re
import sqlite3
from fastapi import HTTPException
from app.services import qc_dossier as archive
from app.services.qc_inspection_summary import summary_report_date, business_date

PUBLIC_DATA=set('po_no contract_no country customer_country customer_name product_no shipping_item reference_no source_product_no source_order_date product_name_zh product_name_en product_version date_code production_no order_type customer_release_no customer_label quantity units_per_carton carton_count standard packaging line_q customer_q requested_ship_date received_date label manual carton_mark fabric_label barcode parent_product_no port printing_requirement note remarks recheck_notice production_department inspection_agency planned_inspection_date planned_inspection_date_to inspection_date'.split())
QC_FIELDS=set('id entryId customer customerCode poNo customerPo stockNo productNo productName country quantity unitsPerCarton cartonCount production agency contractNo shipDate shippedQuantity sourceStatus sourceNote dateFrom dateTo scheduleDate scheduleDateTo actualDate inspectionDate inspectionDateSource reportDate inspectionType result status submissionStatus completion inspectionProblem remark improvement responsible firstResponsible secondResponsible otherRemark customerRequirements inspectionFactory actualQuantity inspector reportStatus submittedAt submittedBy confirmedAt confirmedBy archivedAt sourceLabel sourceSheet sourceRow revision reviewState workflowId sourceId verificationIssues'.split())
EXECUTION_FIELDS=set('actualDate actualQuantity sampleQuantity inspector institution reportNo reportMissingReason resultExplanation defects measurements result remark'.split())
REVIEW_ACTIONS={'submit','confirm','revoke','return-to-inspection'}


def public_source(payload, full):
    raw=archive.archive_value(payload)
    data=raw['data']
    visible=data if full else {k:v for k,v in data.items() if k in PUBLIC_DATA and not isinstance(v,(dict,list))}
    return {'record':raw['record'],'data':visible,'sources':raw.get('sources',[]) if full else [],
            'restricted':not full and (len(visible)!=len(data) or bool(raw.get('sources'))),
            'schemaVersion':raw['schemaVersion']}


def checked_capture(conn, identity, factory, source_id, full):
    if not identity:return None
    row=conn.execute('SELECT * FROM source_captures WHERE id=? AND factory=? AND source_id=?',(identity,factory,source_id)).fetchone()
    if not row:raise ValueError('资料关联不一致')
    payload=json.loads(row['payload'])
    record=archive.validate(payload)
    expected=archive.capture_identity(factory,source_id,archive.digest(payload))
    if (expected!=identity or archive.digest(payload)!=row['payload_hash'] or record['id']!=source_id or record['factory_id']!=factory
        or record['version']!=row['source_version'] or record['revision']!=row['source_revision'] or row['source_system']!=archive.SYSTEM):
        raise ValueError('资料校验未通过')
    return dict(id=identity,**public_source(payload,full),capturedAt=row['captured_at'],sourceUpdatedAt=row['source_updated_at'])


def detail(factory, identity, *, full_business=False):
    if not re.fullmatch(r'[a-f0-9]{32}',identity):raise HTTPException(404,'验货记录不存在')
    summary_path=Path(archive.settings.qc_department_data_dir).resolve()/'_summary'/'summaries.sqlite3'
    if not summary_path.is_file():raise HTTPException(404,'验货记录不存在')
    try:
        with closing(sqlite3.connect(summary_path.as_uri()+'?mode=ro',uri=True,timeout=.25)) as summary:
            summary.row_factory=sqlite3.Row
            summary.execute('PRAGMA query_only=ON');summary.execute('BEGIN')
            stored=summary.execute('SELECT * FROM records WHERE factory=? AND id=? AND active=1',(factory,identity)).fetchone()
            if stored is None:raise HTTPException(404,'验货记录不存在或归档已撤回')
            item=json.loads(stored['payload'])
            qc={k:item[k] for k in QC_FIELDS if k in item}
            qc['inspectionExecution']={k:v for k,v in (item.get('inspectionExecution') or {}).items() if k in EXECUTION_FIELDS}
            src=item.get('sourceRecord') or {}
            qc['sourceRecord']={k:src[k] for k in ('id','factory','sourceVersion','sourceRevision','shipDate','contractNo','customerCode','shippedQuantity','sourceStatus','sourceNote') if k in src}
            qc['photos']=[{k:p[k] for k in ('id','name','caption','mime','size') if k in p} for p in item.get('photos',[]) if isinstance(p,dict)]
            qc['reportDate']=summary_report_date(item,item.get('inspectionDate',''))
            qc['scheduleDate']=business_date(item.get('dateFrom')) or business_date(src.get('dateFrom')) if item.get('entryId') else ''
            qc['scheduleDateTo']=business_date(item.get('dateTo')) or business_date(src.get('dateTo')) or qc['scheduleDate'] if item.get('entryId') else ''
            output=dict(qc=qc,business=dict(status='not_initialized',frozen=None,latest=None,task=None,collection={'status':'not_initialized' if archive.enabled(factory) else 'disabled'}),audit=[],changes=[],sourceEvents=[],remarkOrigin='unknown',fieldPolicy='sales-authorized' if full_business else 'qc-operational')
            if not archive.path().is_file():return output
            # Same read transaction for summary and journal; no store()/sync()/reconcile().
            summary.execute('ATTACH DATABASE ? AS journal',(archive.path().as_uri()+'?mode=ro',))
            tables={r[0] for r in summary.execute("SELECT name FROM journal.sqlite_master WHERE type='table'")}
            entry_id=item.get('entryId');entry=None
            if entry_id and 'entries' in tables:
                entry=summary.execute('SELECT * FROM journal.entries WHERE id=? AND factory=?',(entry_id,factory)).fetchone()
                if entry is None:raise HTTPException(404,'验货记录来源不可验证')
            if entry is not None and not qc['scheduleDate']:
                base=json.loads(entry['base'])
                qc['scheduleDate']=business_date(base.get('dateFrom'))
                qc['scheduleDateTo']=business_date(base.get('dateTo')) or qc['scheduleDate']
            if entry is not None and 'improvement' not in qc and 'entry_details' in tables:
                supplement=summary.execute('SELECT improvement FROM journal.entry_details WHERE entry_id=?',(entry_id,)).fetchone()
                if supplement:qc['improvement']=supplement[0] or ''
            if entry is not None and 'changes' in tables:
                events=summary.execute('SELECT * FROM journal.changes WHERE entry_id=? ORDER BY id DESC',(entry_id,)).fetchall()
                for event in events:
                    delta=json.loads(event['diff']) if 'diff' in event.keys() else {}
                    safe_delta={k:v for k,v in delta.items() if k in QC_FIELDS or k in ('reason','expectedRevision','legacyCompleted') or k.startswith('inspectionExecution.') and k.split('.',1)[1] in EXECUTION_FIELDS}
                    value=dict(id=event['id'],revision=event['revision'],action=event['action'],actor=json.loads(event['actor']),at=event['created_at'],location=event['location'] if 'location' in event.keys() else '',changes=safe_delta)
                    output['changes'].append(value)
                    if event['action'] in REVIEW_ACTIONS:output['audit'].append(value)
                remark_changes=[e for e in output['changes'] if 'remark' in e['changes']]
                # Do not label a seeded source note as a QC-authored note.
                output['remarkOrigin']='qc-edited' if remark_changes else 'source-seeded' if item.get('remark') and item.get('remark')==item.get('sourceNote') else 'unknown'
                if not qc['photos'] and 'photos' in tables:
                    qc['photos']=[dict(p) for p in summary.execute('SELECT id,name FROM journal.photos WHERE entry_id=? AND removed=0',(entry_id,))]
            from app.services.qc_photo_assets import public_metadata
            for photo in qc['photos']:
                photo.update(public_metadata(summary,photo['id'],'journal'))
            if 'qc_dossier_schema' not in tables:return output
            # Archive queries use the same attached read-only connection.
            # A view-free adapter keeps existing table names private to this module.
            class Journal:
                def execute(self,sql,args=()):
                    for name in ('source_captures','source_heads','dossier_links','dossier_events','dossier_worker_state'):
                        sql=re.sub(r'\b'+name+r'\b','journal.'+name,sql)
                    return summary.execute(sql,args)
            conn=Journal()
            state=conn.execute("SELECT value,updated_at FROM dossier_worker_state WHERE key='collection'").fetchone()
            last=conn.execute("SELECT value,updated_at FROM dossier_worker_state WHERE key='last_success'").fetchone()
            collection=json.loads(state['value']) if state else {'status':'ready' if last else 'pending'}
            # Page callers only see lifecycle state, never aggregate counts from other factories.
            collection={k:v for k,v in collection.items() if k in ('status','stage','error')}
            if state:
                collection['updatedAt']=state['updated_at']
                age=(datetime.now(timezone.utc)-datetime.fromisoformat(state['updated_at'])).total_seconds()
                if age>max(120,archive.settings.qc_dossier_poll_seconds*3):
                    collection.update(status='failed',error='后台采集状态已超时，已保存资料仍可查看')
            if last:collection['lastSuccessAt']=last['updated_at']
            if not archive.enabled(factory):collection['status']='disabled'
            output['business']['collection']=collection
            captures={}
            def read_capture(identity):
                if identity not in captures:captures[identity]=checked_capture(conn,identity,factory,source,full_business)
                return captures[identity]
            source=src.get('id') if src.get('factory')==factory else None
            if not source:
                output['business']['status']='missing';return output
            status='missing'
            chosen=None
            # Never substitute a different approval or current entry revision.
            confirmation=next((e for e in output['audit'] if e['action']=='confirm' and e['revision']==item.get('revision')),None)
            if confirmation:
                chosen=conn.execute('SELECT * FROM dossier_links WHERE factory=? AND entry_id=? AND audit_id=? AND phase=\'approval\'',(factory,entry_id,confirmation['id'])).fetchone()
            if chosen:
                status=chosen['status']
                if chosen['source_id']!=source:raise ValueError('审核关联来源不一致')
                output['business']['frozen']=read_capture(chosen['capture_id'])
            task_id=item.get('workflowId')
            if task_id:
                task=conn.execute("SELECT * FROM dossier_links WHERE factory=? AND task_id=? AND phase='task' AND source_id=?",(factory,task_id,source)).fetchone()
                if task:output['business']['task']=read_capture(task['capture_id'])
            head=conn.execute('SELECT * FROM source_heads WHERE factory=? AND source_id=?',(factory,source)).fetchone()
            if head:
                output['business']['latest']=read_capture(head['capture_id'])
                output['business']['lastObservedAt']=head['last_seen_at']
            output['business']['status']=status
            for event in conn.execute('SELECT * FROM dossier_events WHERE factory=? AND (source_id=? OR entry_id=?) ORDER BY at DESC,event_key DESC',(factory,source,entry_id or '')):
                data=json.loads(event['detail']);changes={}
                if data.get('captureId') and data.get('previousCaptureId'):
                    before=read_capture(data['previousCaptureId'])
                    after=read_capture(data['captureId'])
                    for scope in ('record','data'):
                        for key in sorted(set(before[scope])|set(after[scope])):
                            a,b=before[scope],after[scope]
                            if (key in a)!=(key in b) or a.get(key)!=b.get(key) or type(a.get(key)) is not type(b.get(key)):
                                changes[scope+'.'+key]={'before':a.get(key),'after':b.get(key),'beforePresent':key in a,'afterPresent':key in b}
                output['sourceEvents'].append(dict(id=event['event_key'],at=event['at'],action=event['kind'],actor=None,changes=changes,
                    detail={k:data[k] for k in ('warning','phase','status','eventAt','observationKind') if k in data}))
            return output
    except HTTPException:raise
    except (sqlite3.Error,ValueError,KeyError,TypeError) as exc:
        raise HTTPException(503,'完整资料暂不可用，请稍后重试；未修改任何验货记录') from exc
