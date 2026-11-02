"""Metadata aggregation and private, owner-bound feedback; no chat review API."""
from copy import deepcopy
from contextlib import contextmanager
import hashlib
import json
import logging
import math
import time
from datetime import datetime, timezone
from sqlalchemy import select, func, inspect, cast, Text, text, event
from sqlalchemy.exc import SQLAlchemyError
from app import db as database
from app.core.config import settings
from app.models.assistant import (AssistantRun as Run, AssistantRunMetrics as Metrics,
    AssistantFeedback as Feedback, AssistantSubscription as Subscription, AssistantExecution as Execution,
    AssistantMessage as Message, AssistantFile as File)
from . import service, visibility, help_registry
from .errors import AssistantError

logger=logging.getLogger('assistant.operations')
CATEGORIES=('factual','off_topic','sources','experience')
PERCENTILE_MINIMUMS={'p50':20,'p95':100}
COUNTER_KEYS=('source_count','eligible_sources','citations','resolved_citations','business_attempts','business_completed',
    'business_permission_errors','current_business_sources','historical_business_sources','freshness_fresh','freshness_stale','freshness_unknown','freshness_not_applicable')


def counter_meta(value):
    if not isinstance(value,dict):return None
    result={k:value[k] for k in COUNTER_KEYS if type(value.get(k)) is int and value[k]>=0}
    if type(value.get('evidence_measured')) is bool:result['evidence_measured']=value['evidence_measured']
    return result


def duration(start,end):
    if type(start) not in (int,float) or type(end) not in (int,float):return None
    value=end-start
    return value if math.isfinite(value) and value>=0 else None


@contextmanager
def metadata_read():
    """One bounded read snapshot; no authorization/file/network IO in its body."""
    until=time.monotonic()+settings.assistant_operations_query_timeout_ms/1000
    raw=None;connection=None;listener=False
    with database.SessionLocal() as db:
        try:
            if db.bind.dialect.name=='sqlite':
                connection=db.connection()
                raw=connection.connection.driver_connection
                raw.set_progress_handler(lambda:int(time.monotonic()>=until),1000)
                db.execute(text('BEGIN'))
            elif db.bind.dialect.name=='postgresql':
                connection=db.connection(execution_options={'isolation_level':'REPEATABLE READ'})
                db.execute(text('SET TRANSACTION READ ONLY'))
                db.execute(text("SELECT set_config('statement_timeout',:limit,true)"),{'limit':str(settings.assistant_operations_query_timeout_ms)+'ms'})
            else:raise AssistantError('database_unsupported','运行统计数据库类型尚未验证。',503)
            def check_deadline(conn,cursor,statement,parameters,context,executemany):
                remaining=int((until-time.monotonic())*1000)
                if remaining<=0:raise AssistantError('operations_query_timeout','运行统计读取超时，未返回不完整计数。',504,True)
                if conn.dialect.name=='postgresql':
                    # Only a bounded server-generated integer enters this SET.
                    cursor.execute("SET LOCAL statement_timeout = '"+str(remaining)+"ms'")
            event.listen(connection,'before_cursor_execute',check_deadline);listener=True
            yield db
            if time.monotonic()>=until:raise AssistantError('operations_query_timeout','运行统计读取超时，可调整统计窗口后重试。',504,True)
        except SQLAlchemyError as exc:
            timed_out=time.monotonic()>=until or getattr(getattr(exc,'orig',None),'sqlstate',None)=='57014'
            raise AssistantError('operations_query_timeout' if timed_out else 'operations_storage_unavailable',
                '运行统计暂时无法读取，未返回不完整计数。',504 if timed_out else 503,True) from None
        finally:
            if listener:event.remove(connection,'before_cursor_execute',check_deadline)
            if raw is not None:raw.set_progress_handler(None,0)
            db.rollback()


def schema_ready(bind=None):
    try:
        inspector=inspect(bind or database.engine)
        for cls in (Metrics,Feedback,Subscription):
            table=cls.__table__
            if not inspector.has_table(table.name):return False
            if not set(table.columns.keys()) <= {c['name'] for c in inspector.get_columns(table.name)}:return False
            if set(inspector.get_pk_constraint(table.name)['constrained_columns']) != set(table.primary_key.columns.keys()):return False
            if len(inspector.get_foreign_keys(table.name)) < len(table.foreign_key_constraints):return False
        return True
    except SQLAlchemyError:
        return False


def require_ready():
    if not schema_ready():raise AssistantError('operations_schema_pending','反馈与运行统计尚未准备完成。',503)


def optional(db, function, *args, **kwargs):
    """Telemetry cannot roll back a healthy core checkpoint or cancellation."""
    if not schema_ready(db.connection()):return
    try:
        with db.begin_nested():
            function(db,*args,**kwargs)
            db.flush()
    except SQLAlchemyError as exc:
        logger.warning('metadata_write_failed type=%s',type(exc).__name__)
        if not db.is_active:
            raise AssistantError('metadata_storage_unavailable','运行存储暂时不可用，已停止继续写入。',503) from None


def admitted(db, run, payload):
    db.add(Metrics(run_id=run.id,protocol_version=payload.protocol_version,model=run.model,
        thinking=payload.thinking,search_mode=payload.web_search,route='pending',
        used_files=bool(payload.document_ids or payload.attachment_ids),used_tools=False,started_at=run.started_at,
        finished_at=None,terminal_state=None,error_code=None,first_event_seconds=None,
        first_delta_seconds=None,first_answer_seconds=None,elapsed_seconds=None,cancel_requested_at=None,
        upstream_closed_at=None,counters={},total_tokens=None,usage_state='pending'))


def counters(parts, rid):
    evidence=next((p for p in parts if p.get('type')=='evidence'),None)
    if evidence is None:return dict(evidence_measured=False)
    sources=evidence.get('sources',[])
    citations=evidence.get('citations',[])
    results={}
    for part in parts:
        value=part.get('result')
        if part.get('type') not in ('business_snapshot','business_failure','tool_result') or not isinstance(value,dict):continue
        if value.get('contract_version')==3 and value.get('run_id')==rid:
            results[(value.get('tool_call_id'),value.get('step_id'))]=value
    attempts=sum(a.get('kind')=='query_business' for a in evidence.get('activities',[]))
    successful=[r for r in results.values() if r.get('status') not in ('failed','forbidden') and r.get('data_mode')!='unavailable']
    return dict(evidence_measured=True,source_count=len(sources),
        eligible_sources=sum(s.get('citation_eligible',True) is not False for s in sources),
        citations=len(citations),resolved_citations=sum(c.get('resolution')=='resolved' for c in citations),
        current_business_sources=sum(s.get('kind')=='business' and not s.get('origin') and s.get('run_id')==rid for s in sources),
        historical_business_sources=sum(s.get('kind')=='business' and bool(s.get('origin')) for s in sources),
        business_attempts=max(attempts,len(results)),business_completed=len(successful),
        business_permission_errors=sum(r.get('diagnostic_code')=='business_forbidden' for r in results.values()),
        freshness_fresh=sum(r.get('freshness',{}).get('state')=='fresh' for r in successful),
        freshness_stale=sum(r.get('freshness',{}).get('state')=='stale' for r in successful),
        freshness_unknown=sum(r.get('freshness',{}).get('state') in (None,'unknown') for r in successful),
        freshness_not_applicable=sum(r.get('freshness',{}).get('state')=='not_applicable' for r in successful))


def finished(db,run,message):
    row=db.get(Metrics,run.id)
    if row is None or row.terminal_state is not None:return
    row.finished_at=run.finished_at
    row.terminal_state=run.state
    row.error_code=run.error_code
    row.elapsed_seconds=duration(run.started_at,run.finished_at or time.time())
    row.route=(run.context_window or {}).get('execution_v2',{}).get('route','legacy' if row.protocol_version==1 else 'chat')
    row.counters=counters(message.content_parts,run.id)
    row.used_tools=any(p.get('type') in ('tool_call','business_snapshot','business_failure') for p in message.content_parts) or bool(row.counters.get('business_attempts'))
    value=(run.usage or {}).get('total_tokens')
    row.total_tokens=value if type(value) is int and value>=0 else None
    attempt=(run.context_window or {}).get('provider_attempt_state')
    row.usage_state='actual' if row.total_tokens is not None else 'not_started' if attempt=='not_started' else 'reserved' if (run.context_window or {}).get('reserved_tokens') else 'unknown'


def cancel_requested(db,run):
    row=db.get(Metrics,run.id)
    if row and row.cancel_requested_at is None:row.cancel_requested_at=time.time()


def event_started(db,run):
    row=db.get(Metrics,run.id)
    if row and row.first_event_seconds is None:row.first_event_seconds=duration(run.started_at,time.time())


def delta_received(db,run,answer=False):
    row=db.get(Metrics,run.id)
    if row:
        elapsed=duration(run.started_at,time.time())
        if row.first_delta_seconds is None:row.first_delta_seconds=elapsed
        if answer and row.first_answer_seconds is None:row.first_answer_seconds=elapsed


def mark(rid,lease,kind):
    with service.transaction() as db:
        run=db.get(Run,rid)
        if not run or run.lease_owner!=lease or run.state not in service.ACTIVE or run.cancel_requested or run.lease_expires_at<time.time():return
        if kind=='started':optional(db,event_started,run)
        elif kind in ('delta','answer'):optional(db,delta_received,run,answer=kind=='answer')


def upstream_closed(rid,lease):
    with service.transaction() as db:
        run=db.get(Run,rid)
        if not run or run.lease_owner!=lease:return
        def write(db):
            row=db.get(Metrics,rid)
            if row and row.upstream_closed_at is None:row.upstream_closed_at=time.time()
        optional(db,write)


@help_registry.scoped_read
def readable(user,rid):
    from .capabilities import require_enabled
    require_enabled()
    value=service.snapshot(user,rid=rid)
    if any(m.get('unavailable') for m in value['items']):
        raise AssistantError('sources_unavailable','相关资料已删除或授权已改变，当前反馈与诊断不可查看。',410)
    answer=next((m for m in value['items'] if m['role']=='assistant'),None)
    if answer is None:raise AssistantError('not_found','回答不存在。',404)
    refs=visibility.sources(answer['content_parts'])
    if value.get('protocol_version')==3:
        with database.SessionLocal() as db:
            execution=db.get(Execution,rid)
            refs+=execution.source_refs if execution else []
    refs=list({s['source_id']:s for s in refs}.values())
    if not visibility.allowed(user,refs):raise AssistantError('sources_unavailable','相关资料当前不可查看。',410)
    return value,refs


def feedback_out(row):
    return None if row is None else dict(run_id=row.run_id,revision=row.revision,categories=list(row.categories),
        source_ids=list(row.source_ids),comment=row.comment,updated_at=row.updated_at)


def feedback_get(user,rid):
    require_ready()
    run,refs=readable(user,rid)
    with database.SessionLocal() as db:
        row=db.get(Feedback,rid)
        if row and (row.owner_user_id!=user.id or row.employment_epoch!=service.epoch(user)):
            raise AssistantError('not_found','反馈不存在。',404)
        return dict(run_id=rid,available=run['state'] not in service.ACTIVE,feedback=feedback_out(row),
            sources=[dict(source_id=s['source_id'],kind=s['kind'],title=s.get('title','资料'),citation_eligible=s.get('citation_eligible',True)) for s in refs])


def feedback_put(user,rid,payload):
    require_ready()
    snapshot,refs=readable(user,rid)
    if snapshot['state'] in service.ACTIVE:raise AssistantError('run_active','回答结束或停止后可以提交反馈。',409)
    if not set(payload.source_ids)<={s['source_id'] for s in refs}:
        raise AssistantError('feedback_source_invalid','只能选择本轮已登记且当前可见的来源。',422)
    frozen=payload.model_dump(mode='json',exclude={'client_request_id'})
    digest=hashlib.sha256(json.dumps(frozen,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    try:
        with service.transaction() as db:
            run=db.get(Run,rid)
            if not run:raise AssistantError('not_found','回答不存在。',404)
            service.owned(db,user,run.session_id)
            if run.state in service.ACTIVE:raise AssistantError('run_active','回答结束后可以提交反馈。',409)
            row=db.get(Feedback,rid)
            if row and (row.owner_user_id!=user.id or row.employment_epoch!=service.epoch(user)):
                raise AssistantError('not_found','反馈不存在。',404)
            if row and row.last_request_id==payload.client_request_id:
                if row.last_request_hash!=digest:raise AssistantError('idempotency_conflict','同一反馈请求编号不能提交不同内容。',409)
                return feedback_out(row)
            if payload.base_revision!=(row.revision if row else 0):
                raise AssistantError('feedback_conflict','已保存反馈已更新，当前草稿仍保留。请重新读取后核对。',409)
            now=time.time()
            if row is None:
                row=Feedback(run_id=rid,owner_user_id=user.id,employment_epoch=service.epoch(user),revision=0,
                    categories=[],source_ids=[],comment='',last_request_id='',last_request_hash='',created_at=now,updated_at=now)
                db.add(row)
            row.revision+=1
            row.categories=list(payload.categories)
            row.source_ids=list(payload.source_ids)
            row.comment=payload.comment
            row.last_request_id=payload.client_request_id
            row.last_request_hash=digest
            row.updated_at=now
            db.flush()
            return feedback_out(row)
    except SQLAlchemyError:
        raise AssistantError('feedback_storage_unavailable','反馈暂时无法保存，草稿已保留，请稍后重试。',503,True) from None


def subscription_open(user,rid,key,after_seq,*,_authorized=False):
    require_ready()
    if not _authorized:readable(user,rid)
    with service.transaction() as db:
        run=db.get(Run,rid)
        service.owned(db,user,run.session_id)
        execution=db.get(Execution,rid)
        if execution is None:raise AssistantError('legacy_run','旧运行请读取保存的回答。',409)
        if after_seq>execution.last_seq:raise AssistantError('event_cursor_ahead','订阅位置超出保存进度。',409)
        row=db.get(Subscription,(rid,key))
        if row:
            if row.after_seq!=after_seq:raise AssistantError('subscription_conflict','相同订阅编号不能用于不同起点。',409)
            return
        db.add(Subscription(run_id=rid,subscriber_id=key,after_seq=after_seq,delivered_seq=after_seq,
            applied_seq=None,connected_at=time.time(),closed_at=None))


def subscription_sent(rid,key,seq):
    with service.transaction() as db:
        def write(db):
            row=db.get(Subscription,(rid,key))
            if row:row.delivered_seq=max(row.delivered_seq,seq)
        optional(db,write)


def subscription_closed(rid,key):
    with service.transaction() as db:
        def write(db):
            row=db.get(Subscription,(rid,key))
            if row and row.closed_at is None:row.closed_at=time.time()
        optional(db,write)


def receipt(user,rid,key,seq):
    require_ready()
    readable(user,rid)
    with service.transaction() as db:
        run=db.get(Run,rid)
        service.owned(db,user,run.session_id)
        row=db.get(Subscription,(rid,key))
        if row is None:raise AssistantError('not_found','订阅不存在。',404)
        if seq<row.after_seq or seq>row.delivered_seq:
            raise AssistantError('receipt_out_of_range','确认位置超出本次订阅已发出的范围。',422)
        row.applied_seq=max(row.applied_seq or row.after_seq,seq)
        return dict(run_id=rid,subscriber_id=key,applied_seq=row.applied_seq)


def own_diagnostics(user,rid):
    require_ready()
    snapshot,refs=readable(user,rid)
    from app.models.assistant import AssistantProviderStep
    with database.SessionLocal() as db:
        row=db.get(Metrics,rid)
        steps=db.scalars(select(AssistantProviderStep).where(AssistantProviderStep.run_id==rid)).all() if snapshot.get('protocol_version')==3 else []
        return dict(run_id=rid,state=snapshot['state'],measured=row is not None,
            counters=deepcopy(row.counters) if row else None,
            timings=dict(first_event_seconds=row.first_event_seconds,first_delta_seconds=row.first_delta_seconds,
                first_answer_seconds=row.first_answer_seconds,elapsed_seconds=row.elapsed_seconds,
                upstream_close_after_cancel_seconds=duration(row.cancel_requested_at,row.upstream_closed_at)) if row else None,
            usage_state=row.usage_state if row else 'unmeasured',
            sources=[dict(source_id=s['source_id'],step_id=s.get('step_id'),tool_call_id=s.get('tool_call_id'),kind=s['kind'],as_of=s.get('as_of'),observed_at=s.get('observed_at')) for s in refs],
            steps=[dict(step_id=s.step_id,status=s.status,provider_request_id=s.request_id,usage=s.usage) for s in steps],
            citation_binding_is_semantic_support=False)


def admin_trace(user,rid):
    from .diagnostics import allowed
    if not allowed(user):raise AssistantError('diagnostics_forbidden','仅有集团系统权限的管理员可查看脱敏运行诊断。',403)
    require_ready()
    from app.models.assistant import AssistantProviderStep
    with metadata_read() as db:
        run=db.execute(select(Run.id,Run.state,Run.model,Run.error_code,Run.started_at,Run.finished_at,
            Run.provider_request_id,Run.usage).where(Run.id==rid)).mappings().first()
        if run is None:raise AssistantError('not_found','没有找到这次运行；未接收的请求请按请求编号核对服务日志。',404)
        row=db.get(Metrics,rid)
        steps=db.scalars(select(AssistantProviderStep).where(AssistantProviderStep.run_id==rid)).all() if inspect(db.connection()).has_table(AssistantProviderStep.__tablename__) else []
        feedback=db.execute(select(Feedback.categories,Feedback.source_ids,Feedback.updated_at).where(Feedback.run_id==rid)).mappings().first()
        def usage_meta(value):
            return None if not isinstance(value,dict) else {k:v for k,v in value.items() if k in ('prompt_tokens','completion_tokens','total_tokens') and type(v) is int and v>=0}
        run_meta={**dict(run),'usage':usage_meta(run['usage'])}
        return dict(metadata_only=True,run=run_meta,metrics=None if row is None else dict(counters=counter_meta(row.counters),
            usage_state=row.usage_state,first_event_seconds=row.first_event_seconds,first_delta_seconds=row.first_delta_seconds,
            first_answer_seconds=row.first_answer_seconds,elapsed_seconds=row.elapsed_seconds,
            cancel_requested_at=row.cancel_requested_at,upstream_closed_at=row.upstream_closed_at),
            steps=[dict(step_id=s.step_id,provider=s.provider,status=s.status,provider_request_id=s.request_id,
                started_at=s.started_at,finished_at=s.finished_at,usage=usage_meta(s.usage)) for s in steps],
            feedback=dict(feedback) if feedback else None,
            exclusions=['employee identity','session ID','messages','source titles and excerpts','feedback comment','provider addresses','credentials'])


def _distribution(db,column,base):
    count,lo,hi=db.execute(select(func.count(column),func.min(column),func.max(column)).where(*base,column.is_not(None))).one()
    result=dict(samples=count,min=lo,max=hi,p50=None,p95=None)
    for name,p in (('p50',.5),('p95',.95)):
        if count<PERCENTILE_MINIMUMS[name]:continue
        at=(count-1)*p
        values=db.scalars(select(column).where(*base,column.is_not(None)).order_by(column).offset(math.floor(at)).limit(2)).all()
        result[name]=values[0] if len(values)==1 else values[0]+(values[1]-values[0])*(at-math.floor(at))
    return result


def summary(user,days=7):
    from .diagnostics import allowed
    if not allowed(user):raise AssistantError('diagnostics_forbidden','仅有集团系统权限的管理员可查看运行统计。',403)
    require_ready()
    now=time.time()
    since=now-days*86400
    base=[Metrics.started_at>=since,Metrics.started_at<=now]
    with metadata_read() as db:
        total=db.scalar(select(func.count()).select_from(Run).where(Run.started_at>=since,Run.started_at<=now))
        measured=db.scalar(select(func.count()).select_from(Metrics).where(*base))
        active_runs=db.scalar(select(func.count()).select_from(Run).where(Run.started_at>=since,Run.started_at<=now,Run.state.in_(service.ACTIVE)))
        states=dict(db.execute(select(Metrics.terminal_state,func.count()).where(*base).group_by(Metrics.terminal_state)).all())
        errors=dict(db.execute(select(Metrics.error_code,func.count()).where(*base,Metrics.error_code.is_not(None)).group_by(Metrics.error_code)).all())
        usages=dict(db.execute(select(Metrics.usage_state,func.count()).where(*base).group_by(Metrics.usage_state)).all())
        sums={k:db.scalar(select(func.sum(Metrics.counters[k].as_integer())).where(*base)) for k in COUNTER_KEYS}
        source_base=[*base,Metrics.terminal_state.is_not(None),Metrics.counters['evidence_measured'].as_boolean().is_(True)]
        source_runs=db.scalar(select(func.count()).select_from(Metrics).where(*source_base))
        no_source_runs=db.scalar(select(func.count()).select_from(Metrics).where(*source_base,Metrics.counters['eligible_sources'].as_integer()==0))
        timings={name:_distribution(db,getattr(Metrics,name),base) for name in ('first_event_seconds','first_delta_seconds','first_answer_seconds','elapsed_seconds')}
        cancel_delay=Metrics.upstream_closed_at-Metrics.cancel_requested_at
        timings['upstream_close_after_cancel_seconds']=_distribution(db,cancel_delay,[*base,Metrics.cancel_requested_at.is_not(None),Metrics.upstream_closed_at.is_not(None),cancel_delay>=0])
        subbase=[Subscription.connected_at>=since,Subscription.connected_at<=now,Subscription.after_seq>0]
        sub_attempts=db.scalar(select(func.count()).select_from(Subscription).where(*subbase))
        sub_confirmed=db.scalar(select(func.count()).select_from(Subscription).where(*subbase,Subscription.applied_seq>Subscription.after_seq))
        sub_unknown=db.scalar(select(func.count()).select_from(Subscription).where(*subbase,Subscription.applied_seq.is_(None)))
        feedback_base=[Feedback.updated_at>=since,Feedback.updated_at<=now]
        feedback_total=db.scalar(select(func.count()).select_from(Feedback).where(*feedback_base))
        # Categories are a strict four-value enum; aggregate without loading
        # private comment rows or an unbounded category result set.
        category_counts={c:db.scalar(select(func.count()).select_from(Feedback).where(*feedback_base,
            cast(Feedback.categories,Text).like('%"'+c+'"%'))) for c in CATEGORIES}
        # Reuse this snapshot: a second SQLite reader can deadlock against a
        # writer waiting for our first reader to release its shared lock.
        file_counts=dict(db.execute(select(File.parse_status,func.count()).where(File.created_at>=since,File.created_at<=now).group_by(File.parse_status)).all()) if inspect(db.connection()).has_table(File.__tablename__) else None
        groups=db.execute(select(Metrics.model,Metrics.thinking,Metrics.route,Metrics.used_files,Metrics.used_tools,func.count()).where(*base)
            .group_by(Metrics.model,Metrics.thinking,Metrics.route,Metrics.used_files,Metrics.used_tools).limit(101)).all()
        def ratio(a,b):return dict(numerator=a,denominator=b,value=a/b if a is not None and b else None)
        return dict(schema_version=1,checked_at=datetime.fromtimestamp(now,timezone.utc).isoformat(),window_days=days,
            window_start=datetime.fromtimestamp(since,timezone.utc).isoformat(),runs=total,instrumented_runs=measured,
            unmeasured_runs=total-measured,active_runs=active_runs,states={k or 'unfinalized':v for k,v in states.items()},errors=errors,usage_states=usages,
            counters=sums,timings=timings,percentile_minimum_samples=PERCENTILE_MINIMUMS,
            registered_source_ratio=ratio(sums['eligible_sources'],sums['source_count']),
            no_source_ratio=ratio(no_source_runs,source_runs),
            citation_binding_ratio=ratio(sums['resolved_citations'],sums['citations']),
            current_business_query_ratio=ratio(sums['business_completed'],sums['business_attempts']),
            recovery=dict(after_seq_attempts=sub_attempts,client_confirmed_progress=sub_confirmed,missing_client_receipt=sub_unknown,
                confirmation_ratio=ratio(sub_confirmed,sub_attempts),coverage='recorded subscriptions only; no inference for failed metadata writes'),
            feedback=dict(total=feedback_total,categories=category_counts),
            files_current_parse_states=file_counts,groups_truncated=len(groups)>100,
            groups=[dict(model=m,thinking=t,route=r,used_files=f,used_tools=u,runs=n) for m,t,r,f,u,n in groups[:100]],
            definitions=dict(citation_binding='登记引用定位成功，不验证结论被来源支持；不提供答案可信度评分。',
                no_source='已终结且保存来源测量的运行中，没有已登记可引用来源的比例；包含正常普通聊天，不作为错误率或语义质量评分。未测与未终结运行不计入分母。',
                current_business_query='本轮成功取得原系统结果/本轮尝试查询；不代表字段完整、遥测新鲜或结论正确。',
                recovery='after_seq>0的订阅中，客户端明确确认已应用后续序号；缺确认保持未知，不把HTTP200当成功。',
                timings='从服务器admission计时，含排队/查询；first_delta含思考，first_answer仅最终回答正文；不等于客户端网络时延。',
                cancel='原生取消请求到上游迭代器关闭；不是设备停止或未终止读取线程的证明。',
                files='窗口内创建文件的当前解析状态；不伪造历史失败次数。',
                legacy='未采集的旧run不倒填、不当作零；来源和时延的分母只含可测记录。'))
