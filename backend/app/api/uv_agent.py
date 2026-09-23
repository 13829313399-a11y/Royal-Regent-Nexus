from typing import Annotated
from fastapi import APIRouter, Header, Query
from app.api.uv_operations import Db, UvRoute
from app.core.config import settings
from app.models import uv_operations as m
from app.schemas import uv_operations as s
from app.services.uv_operations import common as c, authz as a, ingest

router = APIRouter(prefix="/api/internal/uv-agent", tags=["uv-agent"], route_class=UvRoute)
Authorization = Annotated[str, Header()]


def agent(db, authorization):
    c.require(settings.uv_ops_enabled, "module_disabled", "UV 模块尚未启用", 503)
    a.ready(db)
    return ingest.authenticate(db, authorization)


@router.post("/enroll")
def enroll(body: s.Enroll, db: Db):
    c.require(settings.uv_ops_enabled, "module_disabled", "UV 模块尚未启用", 503)
    a.ready(db)
    return ingest.enroll(db, body)


@router.post("/events/batch")
def events(body: s.AgentBatch, db: Db, authorization: Authorization):
    identity = agent(db, authorization)
    return ingest.batch(db, identity.id, body)


@router.post("/heartbeat")
def heartbeat(body: dict, db: Db, authorization: Authorization):
    identity = agent(db, authorization)
    identity = c.get(db, m.UvOpsAgent, identity.id, lock=True)
    c.require(not identity.revoked, 'agent_revoked', '代理凭据已撤销', 401)
    identity.last_seen_at = m.now()
    # Whitelist diagnostic fields; never persist client config or credentials.
    identity.diagnostics = {key: body.get(key) for key in ("agent_version", "sqlite_version", "queue_count", "oldest_age_seconds", "free_disk_bytes", "quarantine_count", "collector_health", "last_error_code")}
    c.touch(identity)
    db.commit()
    return dict(agent_id=identity.id, received_at=identity.last_seen_at)


@router.get("/config")
def config(db: Db, authorization: Authorization):
    identity = agent(db, authorization)
    return dict(agent_id=identity.id, factory_id=m.FACTORY, bindings=[c.record(x) for x in db.scalars(c.query(m.UvOpsSourceBinding).where(m.UvOpsSourceBinding.agent_id == identity.id, m.UvOpsSourceBinding.active_key.is_not(None)))], dispatch_supported=False)


@router.get("/commands")
def commands(db: Db, authorization: Authorization, wait_seconds: int = Query(25, ge=0, le=25)):
    agent(db, authorization)
    return dict(commands=[], dispatch_supported=False, retry_after_seconds=wait_seconds)


@router.post("/commands/{entity_id}/receipt")
def command_receipt(entity_id: str, db: Db, authorization: Authorization):
    agent(db, authorization)
    raise c.DomainError("dispatch_unsupported", "尚未验证任何原生设备控制能力", 422)
