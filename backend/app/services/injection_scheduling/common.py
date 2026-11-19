import hashlib
import json
from datetime import date, datetime
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import inspect, select, update

from app.models.injection_scheduling import FactorySettings, Operation, SharedRevision

from .calculations import now, timestamp
from .defaults import factory_defaults
from .field_registry import FACTORIES


def jsonable(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return timestamp(value).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    return value


def record(obj):
    return jsonable(
        {
            **(getattr(obj, "extras", None) or {}),
            **{c.key: getattr(obj, c.key) for c in inspect(obj).mapper.column_attrs},
        }
    )


def scoped(db, model, identity, factory):
    obj = db.get(model, identity)
    if (
        obj is None
        or getattr(obj, "factory_id", getattr(obj, "current_factory_id", factory))
        != factory
    ):
        raise HTTPException(404, "记录不存在或不属于当前厂区")
    return obj


def seed_settings(db):
    # Also used by isolated integration fixtures; runtime requires the migration.
    for factory in FACTORIES:
        if db.get(FactorySettings, factory) is None:
            db.add(
                FactorySettings(
                    factory_id=factory, revision=0, parameters=factory_defaults()
                )
            )
    if db.get(SharedRevision, "shared") is None:
        db.add(SharedRevision(id="shared", revision=0))
    db.flush()


def payload_hash(kind, payload):
    return hashlib.sha256(
        json.dumps(
            {"kind": kind, "payload": jsonable(payload)},
            sort_keys=True,
            ensure_ascii=False,
        ).encode()
    ).hexdigest()


def existing_operation(db, factory, actor, op_id, digest):
    op = db.scalar(select(Operation).where(Operation.client_operation_id == op_id))
    if op is not None:
        if (
            op.factory_id != factory
            or op.actor_id != actor
            or op.payload_hash != digest
        ):
            raise HTTPException(409, "操作标识已用于另一项保存，请重新操作")
        return op.result
    return None


def begin_write(db, payload, actor, kind):
    data = payload.model_dump() if hasattr(payload, "model_dump") else payload
    factory, op_id = data["factory_id"], data["client_operation_id"]
    digest = payload_hash(kind, data)
    prior = existing_operation(db, factory, actor, op_id, digest)
    if prior is not None:
        return prior, None
    # A single ordinary module row serializes physical-asset facts across factories.
    # The factory CAS makes stale client edits explicit on both SQLite and PostgreSQL.
    db.execute(
        update(SharedRevision)
        .where(SharedRevision.id == "shared")
        .values(revision=SharedRevision.revision + 1)
    )
    prior = existing_operation(db, factory, actor, op_id, digest)
    if prior is not None:
        db.rollback()
        return prior, None
    changed = db.execute(
        update(FactorySettings)
        .where(
            FactorySettings.factory_id == factory,
            FactorySettings.revision == data["base_revision"],
        )
        .values(revision=FactorySettings.revision + 1)
    )
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "该厂区已更新，已保留你的输入，请刷新后重新应用")
    db.expire_all()
    return None, {
        "factory_id": factory,
        "actor_id": actor,
        "client_operation_id": op_id,
        "payload_hash": digest,
        "kind": kind,
        "revision": data["base_revision"] + 1,
    }


def finish_write(db, context, result, before=None):
    result = jsonable(
        {
            **result,
            "revision": context["revision"],
            "shared_revision": db.get(SharedRevision, "shared").revision,
            "as_of": now(),
        }
    )
    db.add(
        Operation(
            **context, occurred_at=now(), before=jsonable(before or {}), result=result
        )
    )
    db.commit()
    return result


def touch(obj, actor):
    obj.revision = (obj.revision or 0) + 1
    obj.updated_by, obj.updated_at = actor, now()


def check_revision(obj, expected):
    if expected is not None and obj.revision != expected:
        raise HTTPException(409, "这条记录已被修改，请刷新后重新应用")
