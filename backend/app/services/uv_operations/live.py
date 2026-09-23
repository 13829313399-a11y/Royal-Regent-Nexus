"""Database snapshots every five seconds: explicit broker-free SSE fallback."""
import asyncio
from datetime import UTC, datetime
import json
from sqlalchemy import String, cast, func, select, or_
from app.db import SessionLocal
from app.models import uv_operations as m
from app.services.auth import get_current_user
from . import common as c, authz as a


def workspace(db):
    config = db.scalar(c.query(m.UvOpsSettings))
    agents = {x.id: x for x in db.scalars(c.query(m.UvOpsAgent))}
    bindings = {x.machine_id: x for x in db.scalars(c.query(m.UvOpsSourceBinding).where(m.UvOpsSourceBinding.active_key.is_not(None)))}
    cursors = {x.binding_id: x for x in db.scalars(c.query(m.UvOpsSourceCursor))}
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
        machines.append(row)
    counts = {}
    data = dict(machines=machines, transport=dict(mode="database_polling", interval_seconds=5, dispatch_supported=False))
    for name, model in (("tasks", m.UvOpsTask), ("schedule", m.UvOpsScheduleBlock), ("shifts", m.UvOpsShift), ("batches", m.UvOpsBatch), ("runs", m.UvOpsRun)):
        statement=c.query(model)
        if model==m.UvOpsBatch: statement=statement.where(model.active.is_(True))
        counts[name] = db.scalar(select(func.count()).select_from(statement.subquery()))
        data[name] = [c.record(x) for x in db.scalars(statement.order_by(model.created_at.desc(), model.id).limit(100))]
    unmatched = db.scalar(select(func.count()).select_from(m.UvOpsRun).where(m.UvOpsRun.match_evidence.is_(None)))
    pending = db.scalar(select(func.sum(m.UvOpsBatch.pending))) or 0
    missing = db.scalar(select(func.count()).select_from(m.UvOpsTask).where(or_(m.UvOpsTask.cost_price_snapshot.is_(None), cast(m.UvOpsTask.cost_price_snapshot, String) == 'null')))
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
        data, coverage = workspace(db)
        return a.envelope(db, user, data, coverage=coverage)


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
        await asyncio.sleep(5)
