"""One transaction/lock protocol for all spray mutations, including period close."""
from datetime import date, datetime, UTC
from decimal import Decimal
import hashlib
import json

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, OperationalError

from app.models import spray_ops as m


class DomainError(Exception):
    def __init__(self, code, message, status=409, *, fields=None, conflicts=None, retryable=False):
        self.status = status
        self.body = dict(code=code, message=message, field_errors=fields or {}, conflicts=conflicts or [], retryable=retryable)
        super().__init__(message)


def require(condition, code, message, status=409, **kwargs):
    if not condition:
        raise DomainError(code, message, status, **kwargs)


def scoped(db, model, factory):
    return select(model).where(model.factory_id == factory)


def get(db, model, factory, entity_id):
    entity = db.scalar(scoped(db, model, factory).where(model.id == entity_id))
    require(entity is not None, "not_found", "当前工厂中不存在该记录", 404)
    return entity


def version(entity, expected):
    require(entity.version == expected, "version_conflict", "记录已被更新，请刷新后比较修改", conflicts=[dict(entity_id=entity.id, expected=expected, actual=entity.version)])


def touch(entity):
    entity.version += 1
    entity.updated_at = m.now()


def add(db, model, factory, **values):
    entity = model(factory_id=factory, **values)
    db.add(entity)
    db.flush()
    return entity


def serialize(entity):
    return {column.name: json_value(getattr(entity, column.name)) for column in entity.__table__.columns}


def json_value(value):
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: json_value(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_value(v) for v in value]
    return value


def canonical(value):
    return json.dumps(json_value(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def timestamp(value):
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    require(dt.tzinfo is not None, "timezone_required", "时间必须包含时区", 422)
    return dt.astimezone(UTC).isoformat()


def check_period(db, factory, business_date):
    period = db.scalar(scoped(db, m.SprayOpsPeriod, factory).where(m.SprayOpsPeriod.month == str(business_date)[:7]))
    require(not period or period.status == "open", "period_closed", "该业务月份已锁定，请使用后续期间调整或授权重开")


def seed_factories(db):
    """Only called for a new isolated database or by the migration, never per request."""
    for factory in m.FACTORIES:
        if db.get(m.SprayOpsFactory, factory) is None:
            db.add(m.SprayOpsFactory(id=factory, revision=0))
    db.flush()


def command(db, user, action, body, permissions, handler, *, changes_revision=True, check_month=True):
    factory = body.factory_id
    payload = body.model_dump(mode="json")
    fingerprint = digest(payload)
    try:
        # An UPDATE obtains SQLite's writer lock. On PostgreSQL SELECT FOR UPDATE
        # locks the same pre-existing coordination row before any business read.
        if db.bind.dialect.name == "sqlite":
            db.execute(update(m.SprayOpsFactory).where(m.SprayOpsFactory.id == factory).values(revision=m.SprayOpsFactory.revision))
        gate = db.scalar(select(m.SprayOpsFactory).where(m.SprayOpsFactory.id == factory).with_for_update().execution_options(populate_existing=True))
        require(gate is not None, "schema_not_ready", "喷油模块尚未迁移或初始化", 503)
        receipt = db.scalar(scoped(db, m.SprayOpsReceipt, factory).where(m.SprayOpsReceipt.operation_id == body.operation_id))
        if receipt:
            require(receipt.actor_id == user.id and receipt.action == action and receipt.payload_hash == fingerprint,
                    "operation_conflict", "操作编号已经用于不同内容或操作人")
            result = receipt.result
            db.commit()
            return result
        if check_month and getattr(body, "business_date", None):
            check_period(db, factory, body.business_date)
            if not action.startswith("opening.") and not action.startswith("demand."):
                from .history import guard_date
                guard_date(db, factory, body.business_date)
        result = json_value(handler(gate))
        if changes_revision:
            gate.revision += 1
        result["operation_id"] = body.operation_id
        result["factory_revision"] = gate.revision
        add(db, m.SprayOpsReceipt, factory, operation_id=body.operation_id, actor_id=user.id,
            action=action, payload_hash=fingerprint, required_permissions=list(permissions), result=result)
        add(db, m.SprayOpsAudit, factory, actor_id=user.id, action=action,
            entity_id=result.get("id", ""), operation_id=body.operation_id,
            summary=action, business_date=str(getattr(body, "business_date", None) or datetime.now(UTC).date()))
        db.commit()
        return result
    except DomainError:
        db.rollback()
        raise
    except IntegrityError as error:
        db.rollback()
        raise DomainError("constraint_conflict", "编号重复、跨厂引用或数量约束冲突") from error
    except OperationalError as error:
        db.rollback()
        raise DomainError("busy_retry", "当前工厂有其他操作，请使用同一操作编号重试", retryable=True) from error
    except Exception:
        db.rollback()
        raise


# Deny by omission at the server boundary, including command retries and exports.
COST_FIELDS = frozenset({"commercial_price", "price", "price_evidence", "unit_cost", "cost", "amount", "total_amount", "old_price", "new_price", "saving", "signed_difference", "operating_value", "material_cost", "surplus", "cost_snapshot", "rate", "exchange_rate", "frozen_snapshot", "expense_amount"})
PAYROLL_FIELDS = frozenset({"payroll_amount", "payroll", "wage", "wage_amount", "base_amount", "subsidy", "adjustment", "guarantee", "trial_amount", "rule_parameters"})


def project(value, *, cost, payroll):
    if isinstance(value, list):
        return [project(v, cost=cost, payroll=payroll) for v in value]
    if not isinstance(value, dict):
        return value
    if "parameters" in value and "kind" in value:
        readable = payroll if value["kind"] == "wage" else cost
        if not readable:
            value = {key: item for key, item in value.items() if key not in {"parameters", "evidence", "confirmed_by"}}
    return {key: project(item, cost=cost, payroll=payroll) for key, item in value.items()
            if (cost or key not in COST_FIELDS) and (payroll or key not in PAYROLL_FIELDS)}
