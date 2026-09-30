"""Database snapshots every two seconds: explicit broker-free SSE fallback."""
import asyncio
from datetime import UTC, datetime
import json
import time
from copy import deepcopy
from threading import Lock
from weakref import WeakKeyDictionary
from sqlalchemy.orm import Session
from functools import lru_cache
from sqlalchemy import String, Numeric, cast, func, select, or_
from app.db import SessionLocal
from app.models import uv_operations as m
from app.services.auth import get_current_user
from . import common as c, authz as a

COLLECTIONS = (("tasks",m.UvOpsTask),("schedule",m.UvOpsScheduleBlock),("shifts",m.UvOpsShift),("batches",m.UvOpsBatch),("runs",m.UvOpsRun))

_cache = WeakKeyDictionary()
_cache_guard = Lock()


def response(db, user):
    """Coalesce concurrent reads of the same committed revision for at most 1s.

    Auth and projection always run for this request. Cached facts have their own
    repeatable-read revision/as_of; a new command/event bypasses the old entry.
    No session, user, permission or mutable response is shared.
    """
    if db.bind.dialect.name != 'postgresql':
        data, coverage = workspace(db)
        return a.envelope(db,user,data,coverage=coverage)
    revision = c.revision(db)
    # Read endpoints only: release the reader connection before single-flight
    # waiting, so a full 50-reader pool cannot starve the snapshot builder.
    db.rollback()
    with _cache_guard:
        entry = _cache.setdefault(db.bind, dict(lock=Lock(), value=None))
    with entry['lock']:
        value = entry['value']
        if value is None or value['revision'] < revision or time.monotonic()-value['tick'] >= 1:
            with Session(db.bind) as snapshot_db:
                snapshot_db.connection(execution_options={'isolation_level':'REPEATABLE READ'})
                revision = c.revision(snapshot_db)
                data, coverage = workspace(snapshot_db)
                value = dict(revision=revision,data=data,coverage=coverage,as_of=datetime.now(UTC).isoformat(),tick=time.monotonic())
            entry['value'] = value
    # project() recursively creates the response tree, so a second full copy of
    # the 500-record snapshot would only serialize CPU work across readers.
    return a.envelope(db,user,value['data'],coverage=deepcopy(value['coverage']),view_revision=value['revision'],as_of=value['as_of'])


@lru_cache(maxsize=1)
def postgres_snapshot_statement():
    """One database snapshot/round trip, no ORM hydration of hundreds of facts."""
    fields=[]
    for name,model in COLLECTIONS:
        filters=[model.factory_id==m.FACTORY]
        if model==m.UvOpsBatch: filters.append(model.active.is_(True))
        columns=[cast(col,String).label(col.name) if isinstance(col.type,Numeric) else col for col in model.__table__.columns]
        recent=select(*columns).where(*filters).order_by(model.created_at.desc(),model.id).limit(100).subquery(name+'_recent')
        fields.append(select(func.json_agg(func.row_to_json(recent.table_valued()))).scalar_subquery().label(name))
        fields.append(select(func.count()).select_from(model).where(*filters).scalar_subquery().label(name+'_total'))
    fields.extend([
        select(func.count()).select_from(m.UvOpsRun).where(m.UvOpsRun.factory_id==m.FACTORY,m.UvOpsRun.match_evidence.is_(None)).scalar_subquery().label('unmatched'),
        select(func.sum(m.UvOpsBatch.pending)).where(m.UvOpsBatch.factory_id==m.FACTORY,m.UvOpsBatch.active.is_(True)).scalar_subquery().label('pending'),
        select(func.count()).select_from(m.UvOpsTask).where(m.UvOpsTask.factory_id==m.FACTORY,or_(m.UvOpsTask.cost_price_snapshot.is_(None),cast(m.UvOpsTask.cost_price_snapshot,String)=='null')).scalar_subquery().label('missing'),
    ])
    return select(*fields)


def workspace(db):
    config = db.scalar(c.query(m.UvOpsSettings))
    agents = {x.id: x for x in db.scalars(c.query(m.UvOpsAgent))}
    bindings = {x.machine_id: x for x in db.scalars(c.query(m.UvOpsSourceBinding).where(m.UvOpsSourceBinding.active_key.is_not(None)))}
    cursors = {x.binding_id: x for x in db.scalars(c.query(m.UvOpsSourceCursor))}
    # The current cursor's durable event identifies the current job lifecycle.
    # Run.binding_id is its original binding, so it may differ after valid rebind.
    evidence = list(db.scalars(c.query(m.UvOpsAgentEventInbox).join(m.UvOpsSourceCursor,
        (m.UvOpsSourceCursor.binding_id==m.UvOpsAgentEventInbox.binding_id) &
        (m.UvOpsSourceCursor.stream_id==m.UvOpsAgentEventInbox.stream_id) &
        (m.UvOpsSourceCursor.sequence==m.UvOpsAgentEventInbox.sequence)).where(m.UvOpsAgentEventInbox.binding_id.in_([x.id for x in bindings.values()])))) if cursors else []
    identities = {}
    for item in evidence:
        raw=item.evidence
        native=raw.get('payload',{}).get('native_job_id')
        source=raw.get('source_identity',{})
        identity=source.get('job_identity') or (c.digest(dict(generation=str(source['generation']),native_job_id=native)) if source.get('generation') and native else None)
        if identity and native:
            identities[item.machine_id]=c.digest(dict(agent_id=item.agent_id,source_id=raw['source_id'],job_identity=identity))
    current_runs={x.machine_id:x for x in db.scalars(c.query(m.UvOpsRun).where(m.UvOpsRun.native_identity.in_(identities.values()),m.UvOpsRun.ended_at.is_(None)))} if identities else {}
    now = datetime.now(UTC)
    machines = []
    for machine in db.scalars(c.query(m.UvOpsMachine).order_by(m.UvOpsMachine.code)):
        binding = bindings.get(machine.id)
        cursor = cursors.get(binding.id) if binding else None
        agent = agents.get(binding.agent_id) if binding else None
        agent_age = (now-datetime.fromisoformat(agent.last_seen_at)).total_seconds() if agent and agent.last_seen_at else None
        source_age = (now-datetime.fromisoformat(cursor.observed_at)).total_seconds() if cursor else None
        health = "unconfigured" if not binding else "offline" if agent.revoked or agent_age is None or agent_age > config.stale_seconds*3 else "stale" if source_age is None or source_age > config.stale_seconds or agent_age > config.stale_seconds else "fresh"
        row = c.record(machine) | dict(collection_health=health, work_state=cursor.work_state if cursor and health == "fresh" else "unknown", observed_at=cursor.observed_at if cursor else None, agent_seen_at=agent.last_seen_at if agent else None, source_type=binding.adapter_type if binding else None, progress=None, progress_meaning="unknown", native_job_id=cursor.native_job_id if cursor else None, capabilities=binding.capabilities if binding else None)
        run=current_runs.get(machine.id)
        row['current_run_id']=run.id if run and health=='fresh' and cursor.work_state in {'running','paused','fault'} and run.last_stream_id==cursor.stream_id and run.last_binding_version==binding.binding_version and run.last_sequence<=cursor.sequence else None
        machines.append(row)
    counts = {}
    data = dict(machines=machines, transport=dict(mode="database_polling", interval_seconds=2, dispatch_supported=False))
    if db.bind.dialect.name=='postgresql':
        row=db.execute(postgres_snapshot_statement()).mappings().one()
        for name,_ in COLLECTIONS:
            counts[name]=row[name+'_total']
            data[name]=row[name] or []
        unmatched,pending,missing=row['unmatched'],row['pending'] or 0,row['missing']
    else:
        for name, model in COLLECTIONS:
            statement=c.query(model)
            if model==m.UvOpsBatch: statement=statement.where(model.active.is_(True))
            counts[name] = db.scalar(select(func.count()).select_from(statement.subquery()))
            data[name] = [c.record(x) for x in db.scalars(statement.order_by(model.created_at.desc(), model.id).limit(100))]
        unmatched = db.scalar(select(func.count()).select_from(m.UvOpsRun).where(m.UvOpsRun.factory_id==m.FACTORY,m.UvOpsRun.match_evidence.is_(None)))
        pending = db.scalar(select(func.sum(m.UvOpsBatch.pending)).where(m.UvOpsBatch.factory_id==m.FACTORY,m.UvOpsBatch.active.is_(True))) or 0
        missing = db.scalar(select(func.count()).select_from(m.UvOpsTask).where(m.UvOpsTask.factory_id==m.FACTORY,or_(m.UvOpsTask.cost_price_snapshot.is_(None), cast(m.UvOpsTask.cost_price_snapshot, String) == 'null')))
    # A recent-100 list alone can hide a long-running job or a future plan
    # created months ago. Include one current Run and next plan per machine.
    upcoming = select(m.UvOpsScheduleBlock.id,func.row_number().over(partition_by=m.UvOpsScheduleBlock.machine_id,order_by=(m.UvOpsScheduleBlock.start_at,m.UvOpsScheduleBlock.id)).label('rank')).join(m.UvOpsTask,m.UvOpsTask.id==m.UvOpsScheduleBlock.task_id).where(m.UvOpsScheduleBlock.factory_id==m.FACTORY,m.UvOpsScheduleBlock.status=='planned',m.UvOpsScheduleBlock.end_at>c.ts(now),m.UvOpsTask.status.notin_(['completed','cancelled'])).subquery()
    for name,model,ranked in [('schedule',m.UvOpsScheduleBlock,upcoming)]:
        rows={row['id']:row for row in data[name]}
        rows.update({row.id:c.record(row) for row in db.scalars(c.query(model).where(model.id.in_(select(ranked.c.id).where(ranked.c.rank==1))))})
        data[name]=list(rows.values())
    known_runs={row['id'] for row in data['runs']}
    data['runs'].extend(c.record(row) for row in current_runs.values() if row.id not in known_runs)
    data['runs'].sort(key=lambda row:row.get('last_observed_at') or '',reverse=True)
    missing_tasks={row['task_id'] for row in data['schedule']}-{row['id'] for row in data['tasks']}
    if missing_tasks:
        data['tasks'].extend(c.record(row) for row in db.scalars(c.query(m.UvOpsTask).where(m.UvOpsTask.id.in_(missing_tasks))))
    data["collection_totals"] = counts
    return data, dict(state="partial" if unmatched or pending or missing else "complete", unmatched_runs=unmatched, unconfirmed_output=pending, missing_cost_records=missing)


def snapshot(request, factory_id):
    with SessionLocal() as db:
        # A consistent snapshot avoids labeling older data with a newer revision.
        if db.bind.dialect.name == "postgresql":
            db.connection(execution_options={"isolation_level":"REPEATABLE READ"})
        user = get_current_user(request, db)
        a.authorize(user, factory_id)
        a.ready(db)
        return response(db,user)


async def events(request, factory_id):
    first = True
    while not await request.is_disconnected():
        try:
            payload = await asyncio.to_thread(snapshot, request, factory_id)
        except Exception as error:
            status = getattr(error, "status", getattr(error, "status_code", 503))
            yield 'event: '+("access_revoked" if status in {401,403} else "unavailable")+'\ndata: '+json.dumps(dict(status=status))+"\n\n"
            return
        yield f"id: {payload['meta']['view_revision']}\nevent: {'reset' if first else 'snapshot'}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
        first = False
        await asyncio.sleep(2)
