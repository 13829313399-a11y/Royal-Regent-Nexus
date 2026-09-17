"""Durable per-printer ownership, ordered events and non-replayed command dispatch."""

import json
from datetime import UTC, datetime, timedelta
from functools import wraps
from hashlib import sha256
from types import SimpleNamespace
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError, OperationalError

from app.core.config import settings
from app.core.time import parse_business_timestamp
from app.models import three_d_printing as m
from app.services.three_d_network_health import network_health_snapshot

FACTORY = "huakang-a"
SITE = "3dsite-huakang-a-heyuan"
OWNER = "cloud-connector"
OBSERVER = "cloud-observer"
CONNECTED_OWNERS = (OWNER, OBSERVER)
LEADER_SECONDS = 30
COMMAND_SECONDS = 8
MAX_ATTEMPTS = 3


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def stamp(value):
    return value.astimezone(UTC).isoformat(timespec="milliseconds")


def database_now(db):
    expression = (
        func.clock_timestamp()
        if db.bind.dialect.name == "postgresql"
        else func.current_timestamp()
    )
    value = db.scalar(select(expression))
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def alive(value, now):
    parsed = parse_business_timestamp(value)
    return parsed is not None and parsed > now


def write(function):
    @wraps(function)
    def wrapped(db, *args, **kwargs):
        try:
            # Acquire SQLite's writer before reading, avoiding deferred read->write races.
            # PostgreSQL locks only the addressed printer, permitting independent printers.
            if db.bind.dialect.name == "sqlite" or function.__name__ in {
                "store_event",
                "reconcile",
                "heartbeat",
                "release",
            }:
                db.execute(
                    update(m.ThreeDPrintingSetting)
                    .where(m.ThreeDPrintingSetting.factory_id == FACTORY)
                    .values(revision=m.ThreeDPrintingSetting.revision)
                )
                db.expire_all()
            result = function(db, *args, **kwargs)
            if function.__name__ == "claim_command":
                result["server_time"] = stamp(database_now(db))
            db.commit()
            return result
        except (IntegrityError, OperationalError) as error:
            db.rollback()
            raise HTTPException(409, "连接器并发冲突，请携带原请求标识重试") from error
        except Exception:
            db.rollback()
            raise

    return wrapped


def instance_key(instance_id):
    return "3dci-" + sha256(instance_id.encode()).hexdigest()[:48]


def get_instance(db, instance_id):
    instance = db.get(m.ThreeDPrintingConnectorInstance, instance_key(instance_id))
    if (
        instance is None
        or instance.factory_id != FACTORY
        or instance.site_id != SITE
        or instance.status != "active"
    ):
        raise HTTPException(409, "连接器未注册或已停用")
    site = db.get(m.ThreeDPrintingSite, SITE)
    if site is None or not site.enabled:
        raise HTTPException(409, "河源站点未启用")
    return instance


def connection(db, printer_id):
    row = db.scalar(
        select(m.ThreeDPrintingPrinterConnection)
        .where(
            m.ThreeDPrintingPrinterConnection.printer_id == printer_id,
            m.ThreeDPrintingPrinterConnection.factory_id == FACTORY,
            m.ThreeDPrintingPrinterConnection.site_id == SITE,
        )
        .with_for_update()
    )
    if row is None or not row.connection_enabled or row.connection_owner not in CONNECTED_OWNERS:
        raise HTTPException(409, "打印机尚未启用云端连接")
    printer = db.get(m.ThreeDPrintingPrinter, printer_id)
    if (
        printer is None
        or not printer.enabled
        or printer.factory_id != FACTORY
        or printer.site_id not in (None, SITE)
        or not 1 <= printer.machine_no <= 11
    ):
        raise HTTPException(409, "打印机未启用")
    return row, printer


def metadata(printer):
    return json.loads(printer.status_payload_json or "{}").get("connector", {})


def save_metadata(printer, data):
    values = json.loads(printer.status_payload_json or "{}")
    values["connector"] = data
    printer.status_payload_json = encode(values)


def require_network(db):
    if network_health_snapshot(db)["status"] != "healthy":
        raise HTTPException(409, "站点网络尚未通过探测或探测已过期")


def require_leader(db, payload):
    instance = get_instance(db, payload.instance_id)
    row, printer = connection(db, payload.printer_id)
    now = database_now(db)
    if (
        row.leader_instance_id != instance.id
        or row.leader_lease_id != payload.leader_lease_id
        or not alive(row.leader_leased_until, now)
    ):
        raise HTTPException(409, "打印机所有权租约失效")
    return instance, row, printer, now


def require_session(db, payload):
    values = require_leader(db, payload)
    meta = metadata(values[2])
    if (
        meta.get("lease_id") != payload.leader_lease_id
        or meta.get("session_id") != payload.connection_session_id
    ):
        raise HTTPException(409, "打印机连接会话已失效")
    return (*values, meta)


def audit(
    db,
    entity,
    entity_id,
    action,
    data,
    actor,
    now,
    *,
    actor_type="cloud_connector",
    actor_name="云端打印机连接器",
):
    db.add(
        m.ThreeDPrintingAuditEvent(
            id="3dca-" + uuid4().hex,
            factory_id=FACTORY,
            entity_type=entity,
            entity_id=entity_id,
            action=action,
            detail_json=encode(data),
            actor_id=actor,
            actor_type=actor_type,
            actor_name=actor_name,
            request_id="",
            created_at=stamp(now),
        )
    )


def notify(db, kind, identifier):
    # Delivered by PostgreSQL only on commit; durable rows remain the source of truth.
    if db.bind.dialect.name == "postgresql":
        db.execute(
            select(
                func.pg_notify(
                    "three_d_printing_events",
                    encode({"factory_id": FACTORY, "kind": kind, "id": identifier}),
                )
            )
        )


@write
def heartbeat(db, payload):
    site = db.get(m.ThreeDPrintingSite, SITE)
    if site is None or not site.enabled:
        raise HTTPException(409, "请先完成河源站点初始化")
    key = instance_key(payload.instance_id)
    instance = db.get(m.ThreeDPrintingConnectorInstance, key)
    now = database_now(db)
    if instance is None:
        instance = m.ThreeDPrintingConnectorInstance(
            id=key,
            factory_id=FACTORY,
            site_id=SITE,
            connector_key="cloud-connector",
            instance_id=payload.instance_id,
            started_at=stamp(now),
        )
        db.add(instance)
    elif instance.status == "disabled":
        raise HTTPException(403, "连接器已停用")
    instance.status, instance.version, instance.last_seen_at = (
        "active",
        payload.version,
        stamp(now),
    )
    stale_network = network_health_snapshot(db)["status"] != "healthy"
    for row in db.scalars(
        select(m.ThreeDPrintingPrinterConnection)
        .where(
            m.ThreeDPrintingPrinterConnection.factory_id == FACTORY,
            m.ThreeDPrintingPrinterConnection.connection_owner.in_(CONNECTED_OWNERS),
        )
        .order_by(m.ThreeDPrintingPrinterConnection.printer_id)
        .with_for_update()
    ):
        printer = db.get(m.ThreeDPrintingPrinter, row.printer_id)
        seen = parse_business_timestamp(printer.last_seen_at)
        if (
            (stale_network and row.connection_owner != OBSERVER)
            or not alive(row.leader_leased_until, now)
            or not seen
            or (now - seen).total_seconds() > 30
        ):
            mark_unavailable(db, printer, instance.id, now)
    return {
        "instance_id": payload.instance_id,
        "server_time": stamp(now),
        "protocol_version": 1,
    }


def list_printers(db, payload):
    get_instance(db, payload.instance_id)
    rows = db.scalars(
        select(m.ThreeDPrintingPrinterConnection)
        .where(
            m.ThreeDPrintingPrinterConnection.factory_id == FACTORY,
            m.ThreeDPrintingPrinterConnection.site_id == SITE,
            m.ThreeDPrintingPrinterConnection.connection_owner.in_(CONNECTED_OWNERS),
            m.ThreeDPrintingPrinterConnection.connection_enabled.is_(True),
        )
        .order_by(m.ThreeDPrintingPrinterConnection.printer_id)
        .limit(11)
    )
    return {"printers": [{"printer_id": row.printer_id} for row in rows]}


@write
def acquire(db, payload):
    instance = get_instance(db, payload.instance_id)
    row, printer = connection(db, payload.printer_id)
    # Observation proves connectivity per printer through pinned MQTT. A failed
    # probe for another printer must not prevent this one from reconnecting.
    if row.connection_owner != OBSERVER:
        require_network(db)
    now = database_now(db)
    if alive(row.leader_leased_until, now):
        # Retry returns the same grant; acquisition is not renewal.
        if row.leader_instance_id != instance.id:
            return {"acquired": False, "server_time": stamp(now)}
    else:
        row.leader_instance_id = instance.id
        row.leader_lease_id = "leader-" + uuid4().hex
        row.leader_leased_until = stamp(now + timedelta(seconds=LEADER_SECONDS))
        printer.connected, printer.state = False, "STALE"
        audit(
            db,
            "printer_ownership",
            printer.id,
            "acquired",
            {"lease_id": row.leader_lease_id},
            instance.id,
            now,
        )
    return {
        "acquired": True,
        "leader_lease_id": row.leader_lease_id,
        "leased_until": row.leader_leased_until,
        "server_time": stamp(now),
        "printer_id": printer.id,
        "machine_no": printer.machine_no,
        "host": row.lan_host,
        "port": row.mqtt_port,
        "credential_ref": row.credential_ref,
        "certificate_fingerprint": row.certificate_fingerprint,
        "connection_revision": row.connection_revision,
        "generation": metadata(printer).get("generation", 0)
        if metadata(printer).get("lease_id") == row.leader_lease_id
        else 0,
        "control_verified": row.connection_owner == OWNER and printer.machine_no
        in settings.three_d_connector_verified_machines,
    }


@write
def renew(db, payload):
    instance, row, _, now = require_leader(db, payload)
    row.leader_leased_until = stamp(now + timedelta(seconds=LEADER_SECONDS))
    instance.last_seen_at = stamp(now)
    return {
        "leader_lease_id": row.leader_lease_id,
        "leased_until": row.leader_leased_until,
        "server_time": stamp(now),
        "connection_revision": row.connection_revision,
    }


@write
def release(db, payload):
    instance, row, printer, now = require_leader(db, payload)
    row.leader_leased_until = stamp(now)
    row.last_disconnect_at = stamp(now)
    printer.connected, printer.state = False, "STALE"
    mark_unavailable(db, printer, instance.id, now)
    audit(
        db,
        "printer_ownership",
        printer.id,
        "released",
        {"lease_id": row.leader_lease_id},
        instance.id,
        now,
    )
    return {"released": True}


def mark_unavailable(db, printer, actor, now):
    from app.services.three_d_run_reconciliation import reconcile_event

    if printer.connected or printer.state != "STALE":
        printer.connected, printer.state = False, "STALE"
        printer.revision += 1
        printer.updated_at = stamp(now)
    row = db.get(m.ThreeDPrintingPrinterConnection, printer.id)
    if row is None or row.connection_owner != OBSERVER:
        reconcile_event(
            db, printer, SimpleNamespace(device_job_key="", state="STALE"),
            actor, now, connected=False,
        )
    notify(db, "printer_state", printer.id)


@write
def start_session(db, payload):
    instance, row, printer, now = require_leader(db, payload)
    if row.connection_owner != OBSERVER:
        require_network(db)
    meta = metadata(printer)
    current_generation = (
        meta.get("generation", 0)
        if meta.get("lease_id") == payload.leader_lease_id
        else 0
    )
    if (
        meta.get("lease_id") == payload.leader_lease_id
        and meta.get("session_id") == payload.connection_session_id
    ):
        if payload.generation != current_generation:
            raise HTTPException(409, "会话重试代数不一致")
        return {
            "connection_session_id": payload.connection_session_id,
            "generation": current_generation,
        }
    if payload.generation != current_generation + 1:
        raise HTTPException(409, "拒绝旧会话或跳跃会话代数")
    used = db.scalar(
        select(m.ThreeDPrintingAuditEvent.id).where(
            m.ThreeDPrintingAuditEvent.id
            == "3dsession-"
            + sha256(
                (printer.id + ":" + payload.connection_session_id).encode()
            ).hexdigest()
        )
    )
    if used:
        raise HTTPException(409, "会话标识不可重复使用")
    save_metadata(
        printer,
        {
            "lease_id": payload.leader_lease_id,
            "session_id": payload.connection_session_id,
            "generation": payload.generation,
            "sequence": 0,
            "device_job_key": "",
            "observed_at": None,
        },
    )
    printer.connected, printer.state = False, "STALE"
    row.last_connect_at = stamp(now)
    db.add(
        m.ThreeDPrintingAuditEvent(
            id="3dsession-"
            + sha256(
                (printer.id + ":" + payload.connection_session_id).encode()
            ).hexdigest(),
            factory_id=FACTORY,
            entity_type="printer_session",
            entity_id=printer.id,
            action="started",
            detail_json=encode(
                {
                    "session_id": payload.connection_session_id,
                    "generation": payload.generation,
                }
            ),
            actor_id=instance.id,
            actor_type="cloud_connector",
            actor_name="云端打印机连接器",
            request_id="",
            created_at=stamp(now),
        )
    )
    return {
        "connection_session_id": payload.connection_session_id,
        "generation": payload.generation,
    }


@write
def store_event(db, payload):
    instance, row, printer, now, meta = require_session(db, payload)
    encoded = encode(payload.model_dump(mode="json"))
    existing = db.get(m.ThreeDPrintingPrinterStateEvent, payload.event_id)
    if existing:
        if existing.factory_id != FACTORY or existing.raw_payload_json != encoded:
            raise HTTPException(409, "事件标识已用于不同内容")
        return {"event_id": existing.id, "accepted": True, "duplicate": True}
    if payload.sequence <= meta.get("sequence", 0):
        raise HTTPException(409, "拒绝乱序状态事件")
    if payload.observed_at:
        age = (now - payload.observed_at).total_seconds()
        previous = parse_business_timestamp(meta.get("observed_at"))
        if (
            age < -5
            or (payload.connected and age > 30)
            or (previous and payload.observed_at < previous)
        ):
            raise HTTPException(409, "设备观测时间过期、超前或倒退")
    event = m.ThreeDPrintingPrinterStateEvent(
        id=payload.event_id,
        factory_id=FACTORY,
        connector_instance_id=instance.id,
        printer_id=printer.id,
        machine_no=printer.machine_no,
        connection_session_id=payload.connection_session_id,
        sequence=payload.sequence,
        observed_at=stamp(payload.observed_at) if payload.observed_at else "",
        received_at=stamp(now),
        state=payload.state,
        progress=payload.progress_percent,
        remaining_minutes=payload.remaining_minutes,
        current_file=payload.current_file,
        temperatures_json=encode(
            {"nozzle": payload.nozzle_temperature, "bed": payload.bed_temperature}
        ),
        error_code=payload.error_code,
        error_text="",
        payload_version=1,
        raw_payload_json=encoded,
    )
    db.add(event)
    observation_only = row.connection_owner == OBSERVER
    connected = payload.connected and (
        observation_only or network_health_snapshot(db)["status"] == "healthy"
    )
    effective_state = payload.state if connected else "STALE"
    if effective_state != printer.state or payload.device_job_key != meta.get(
        "device_job_key", ""
    ):
        meta["control_epoch"] = meta.get("control_epoch", 0) + 1
    printer.connected, printer.state = connected, effective_state
    for key in (
        "current_file",
        "progress_percent",
        "remaining_minutes",
        "live_material",
        "nozzle_temperature",
        "bed_temperature",
    ):
        setattr(printer, key, getattr(payload, key))
    printer.error_text = payload.error_code
    if payload.observed_at:
        printer.last_seen_at = stamp(payload.observed_at)
    meta.update(
        observation_only=observation_only,
        nozzle_target=payload.nozzle_target,
        bed_target=payload.bed_target,
        layer_num=payload.layer_num,
        total_layers=payload.total_layers,
        sequence=payload.sequence,
        device_job_key=payload.device_job_key,
        observed_at=stamp(payload.observed_at)
        if payload.observed_at
        else meta.get("observed_at"),
    )
    save_metadata(printer, meta)
    printer.revision += 1
    printer.updated_at = stamp(now)
    from app.services.three_d_run_reconciliation import reconcile_event

    if row.connection_owner != OBSERVER:
        reconcile_event(db, printer, payload, instance.id, now, connected=connected)
    notify(db, "printer_state", event.id)
    return {"event_id": event.id, "accepted": True, "duplicate": False}


def command_live(db, printer, meta, now, action):
    row = db.get(m.ThreeDPrintingPrinterConnection, printer.id)
    if row is None or row.connection_owner != OWNER:
        raise HTTPException(409, "当前为只读接入，不能控制打印机")
    if (
        not settings.three_d_connector_enabled
        or not settings.three_d_connector_control_enabled
        or printer.machine_no not in settings.three_d_connector_verified_machines
    ):
        raise HTTPException(409, "云端打印机控制尚未启用")
    require_network(db)
    seen = parse_business_timestamp(printer.last_seen_at)
    if (
        not printer.connected
        or seen is None
        or not -5 <= (now - seen).total_seconds() <= 30
        or meta.get("sequence", 0) < 1
    ):
        raise HTTPException(409, "设备实时状态不可用")
    if printer.state != {"pause": "RUNNING", "resume": "PAUSE"}[action]:
        raise HTTPException(409, "打印机当前状态不允许此指令")


@write
def reconcile(db, payload):
    from app.schemas.three_d_connector import StateEvent
    from app.services.three_d_run_reconciliation import reconcile_event

    instance, row, printer, now, meta = require_session(db, payload)
    if row.connection_owner == OBSERVER:
        return {"reconciled": False, "reason": "observation_only"}
    event = db.scalar(
        select(m.ThreeDPrintingPrinterStateEvent).where(
            m.ThreeDPrintingPrinterStateEvent.printer_id == printer.id,
            m.ThreeDPrintingPrinterStateEvent.connection_session_id
            == payload.connection_session_id,
            m.ThreeDPrintingPrinterStateEvent.sequence == meta.get("sequence", 0),
        )
    )
    if event is None:
        return {"reconciled": False, "reason": "awaiting_full_status"}
    state = StateEvent.model_validate_json(event.raw_payload_json)
    fresh = (
        state.observed_at is not None
        and -5 <= (now - state.observed_at).total_seconds() <= 30
    )
    reconcile_event(
        db,
        printer,
        state,
        instance.id,
        now,
        connected=state.connected
        and fresh
        and network_health_snapshot(db)["status"] == "healthy",
    )
    return {"reconciled": True, "event_id": event.id}


@write
def create_command(db, *, printer_id, payload, user):
    row, printer = connection(db, printer_id)
    existing = db.scalar(
        select(m.ThreeDPrintingPrinterCommand).where(
            m.ThreeDPrintingPrinterCommand.factory_id == FACTORY,
            m.ThreeDPrintingPrinterCommand.idempotency_key == payload.idempotency_key,
        )
    )
    if existing:
        if (
            existing.printer_id,
            existing.action,
            existing.reason,
            existing.requested_by,
        ) != (printer_id, payload.action, payload.reason.strip(), user.id):
            raise HTTPException(409, "幂等键已用于不同指令")
        return existing
    now, meta = database_now(db), metadata(printer)
    if not alive(row.leader_leased_until, now) or row.leader_lease_id != meta.get(
        "lease_id"
    ):
        raise HTTPException(409, "打印机没有有效云端所有者")
    command_live(db, printer, meta, now, payload.action)
    if not payload.reason.strip():
        raise HTTPException(422, "控制原因不能为空")
    command = m.ThreeDPrintingPrinterCommand(
        id="3dcmd-" + uuid4().hex,
        factory_id=FACTORY,
        printer_id=printer.id,
        action=payload.action,
        status="pending",
        idempotency_key=payload.idempotency_key,
        reason=payload.reason.strip(),
        requested_by=user.id,
        requested_by_name=user.display_name or user.username,
        requested_at=stamp(now),
        expires_at=stamp(now + timedelta(seconds=settings.three_d_command_ttl_seconds)),
        result_evidence_json=encode(
            {
                "request_session": meta["session_id"],
                "request_job_key": meta.get("device_job_key", ""),
                "request_control_epoch": meta.get("control_epoch", 0),
            }
        ),
    )
    db.add(command)
    audit(
        db,
        "printer_command",
        command.id,
        "request",
        {"action": command.action, "reason": command.reason},
        user.id,
        now,
        actor_type="user",
        actor_name=user.display_name or user.username,
    )
    db.flush()
    notify(db, "printer_command", command.id)
    return command


def command_view(command):
    return {
        "command_id": command.id,
        "action": command.action,
        "command_lease_id": command.lease_id,
        "leased_until": command.leased_until,
        "attempt_count": command.attempt_count,
        "status": command.status,
    }


def claim_statement(printer_id):
    return (
        select(m.ThreeDPrintingPrinterCommand)
        .where(
            m.ThreeDPrintingPrinterCommand.factory_id == FACTORY,
            m.ThreeDPrintingPrinterCommand.printer_id == printer_id,
            m.ThreeDPrintingPrinterCommand.status.in_(
                ["pending", "leased", "dispatching"]
            ),
        )
        .order_by(
            m.ThreeDPrintingPrinterCommand.requested_at,
            m.ThreeDPrintingPrinterCommand.id,
        )
        .with_for_update(skip_locked=True)
        .limit(50)
    )


def intent_current(evidence, meta, session_id):
    return (
        evidence.get("request_session") == session_id
        and evidence.get("request_job_key") == meta.get("device_job_key", "")
        and evidence.get("request_control_epoch") == meta.get("control_epoch", 0)
    )


@write
def claim_command(db, payload):
    instance, row, printer, now, meta = require_session(db, payload)
    if (
        row.connection_owner != OWNER
        or not settings.three_d_connector_control_enabled
        or printer.machine_no not in settings.three_d_connector_verified_machines
    ):
        return {"commands": []}
    require_network(db)
    rows = list(db.scalars(claim_statement(printer.id)))
    # Expire old intentions before selecting any candidate, including timestamp ties.
    # The epoch prevents RUNNING -> PAUSE -> RUNNING from reviving an old pause.
    for command in rows:
        if command.status in {"pending", "leased"} and (
            not alive(command.expires_at, now)
            or not intent_current(
                json.loads(command.result_evidence_json),
                meta,
                payload.connection_session_id,
            )
        ):
            command.status, command.completed_at, command.result_message = (
                "expired",
                stamp(now),
                "控制意图已过期或设备状态版本已变化",
            )
            audit(
                db,
                "printer_command",
                command.id,
                "expired",
                {"reason": "intent_changed"},
                instance.id,
                now,
            )
            notify(db, "printer_command", command.id)
    # Never issue a second command while another command may be on the wire.
    for command in rows:
        if command.status == "dispatching":
            if alive(command.leased_until, now):
                return {"commands": []}
            command.status, command.completed_at, command.result_message = (
                "unknown",
                stamp(now),
                "发送后租约过期，需人工核对",
            )
            audit(
                db,
                "printer_command",
                command.id,
                "unknown",
                {"reason": "dispatch_lease_expired"},
                instance.id,
                now,
            )
            notify(db, "printer_command", command.id)
    for command in rows:
        if command.status in {"unknown", "expired"}:
            continue
        evidence = json.loads(command.result_evidence_json)
        if (
            not alive(command.expires_at, now)
            or evidence.get("request_session") != payload.connection_session_id
            or evidence.get("request_job_key") != meta.get("device_job_key", "")
        ):
            command.status, command.completed_at, command.result_message = (
                "expired",
                stamp(now),
                "指令过期或设备会话/任务已变化",
            )
            audit(
                db,
                "printer_command",
                command.id,
                "expired",
                {"reason": "expired_or_context_changed"},
                instance.id,
                now,
            )
            notify(db, "printer_command", command.id)
            continue
        if command.status == "leased" and alive(command.leased_until, now):
            return {
                "commands": [command_view(command)]
                if command.connector_instance_id == instance.id
                else []
            }
        if command.attempt_count >= MAX_ATTEMPTS:
            command.status, command.completed_at, command.result_message = (
                "expired",
                stamp(now),
                "超过未发送领取重试次数",
            )
            audit(
                db,
                "printer_command",
                command.id,
                "expired",
                {"reason": "attempt_limit"},
                instance.id,
                now,
            )
            notify(db, "printer_command", command.id)
            continue
        if command.next_attempt_at and alive(command.next_attempt_at, now):
            continue
        if printer.state != {"pause": "RUNNING", "resume": "PAUSE"}[command.action]:
            command.status, command.completed_at, command.result_message = (
                "expired",
                stamp(now),
                "设备状态已变化，旧控制意图不再下发",
            )
            audit(
                db,
                "printer_command",
                command.id,
                "expired",
                {"reason": "state_changed"},
                instance.id,
                now,
            )
            notify(db, "printer_command", command.id)
            continue
        command_live(db, printer, meta, now, command.action)
        command.status, command.connector_instance_id = "leased", instance.id
        command.lease_id = "command-" + uuid4().hex
        command.leased_until = stamp(
            min(
                now + timedelta(seconds=COMMAND_SECONDS),
                parse_business_timestamp(command.expires_at),
            )
        )
        command.claimed_at, command.attempt_count = (
            stamp(now),
            command.attempt_count + 1,
        )
        audit(
            db,
            "printer_command",
            command.id,
            "leased",
            {"lease_id": command.lease_id, "attempt": command.attempt_count},
            instance.id,
            now,
        )
        return {"commands": [command_view(command)]}
    return {"commands": []}


def owned_command(db, payload):
    instance, _, printer, now, meta = require_session(db, payload)
    command = db.scalar(
        select(m.ThreeDPrintingPrinterCommand)
        .where(
            m.ThreeDPrintingPrinterCommand.id == payload.command_id,
            m.ThreeDPrintingPrinterCommand.factory_id == FACTORY,
            m.ThreeDPrintingPrinterCommand.printer_id == printer.id,
        )
        .with_for_update()
    )
    if (
        command is None
        or command.connector_instance_id != instance.id
        or command.lease_id != payload.command_lease_id
    ):
        raise HTTPException(409, "命令领取租约不匹配")
    return instance, printer, now, meta, command


@write
def dispatch_command(db, payload):
    instance, printer, now, meta, command = owned_command(db, payload)
    if command.status != "leased":
        return {"send_permitted": False, **command_view(command)}
    if not alive(command.leased_until, now) or not alive(command.expires_at, now):
        raise HTTPException(409, "命令领取租约已过期")
    evidence = json.loads(command.result_evidence_json)
    if not intent_current(evidence, meta, payload.connection_session_id):
        raise HTTPException(409, "指令对应的会话或任务已变化")
    command_live(db, printer, meta, now, command.action)
    command.status = "dispatching"
    evidence.update(
        dispatch_sequence=meta["sequence"],
        dispatch_at=stamp(now),
        dispatch_session=payload.connection_session_id,
        leader_lease_id=payload.leader_lease_id,
    )
    command.result_evidence_json = encode(evidence)
    audit(
        db,
        "printer_command",
        command.id,
        "dispatching",
        {"lease_id": command.lease_id},
        instance.id,
        now,
    )
    return {"send_permitted": True, **command_view(command)}


@write
def acknowledge_command(db, payload):
    instance, printer, now, _, command = owned_command(db, payload)
    evidence = json.loads(command.result_evidence_json)
    ack = {
        "status": payload.status,
        "reason": payload.reason,
        "event_id": payload.evidence_event_id,
    }
    if command.status in {"succeeded", "unknown"}:
        if evidence.get("ack") != ack:
            raise HTTPException(409, "命令结果已确定，不允许覆盖")
        return command_view(command)
    if (
        command.status != "dispatching"
        or not alive(command.leased_until, now)
        or not alive(command.expires_at, now)
    ):
        raise HTTPException(409, "命令尚未发送或回执租约已失效")
    if payload.status == "succeeded":
        require_network(db)
        event = db.get(m.ThreeDPrintingPrinterStateEvent, payload.evidence_event_id)
        if (
            event is None
            or event.factory_id != FACTORY
            or event.printer_id != printer.id
            or event.connector_instance_id != instance.id
            or event.connection_session_id != payload.connection_session_id
        ):
            raise HTTPException(409, "命令结果证据不属于当前打印机会话")
        body = json.loads(event.raw_payload_json)
        if (
            event.sequence <= evidence["dispatch_sequence"]
            or event.state != {"pause": "PAUSE", "resume": "RUNNING"}[command.action]
            or not body["connected"]
            or body.get("device_job_key", "") != evidence.get("request_job_key", "")
        ):
            raise HTTPException(409, "缺少发送后的匹配设备状态证据")
    evidence["ack"] = ack
    command.result_evidence_json = encode(evidence)
    command.status, command.completed_at, command.result_message = (
        payload.status,
        stamp(now),
        payload.reason,
    )
    audit(db, "printer_command", command.id, payload.status, ack, instance.id, now)
    notify(db, "printer_command", command.id)
    return command_view(command)
