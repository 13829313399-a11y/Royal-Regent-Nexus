from datetime import UTC, date, datetime
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
import json
from uuid import uuid4

from sqlalchemy import func, inspect, select
from sqlalchemy.exc import IntegrityError, OperationalError
from app.models import uv_operations as m


class DomainError(Exception):
    def __init__(self, code, message, status=409, *, fields=None, version=None):
        self.status = status
        self.body = dict(code=code, message=message, field_errors=fields or {}, current_version=version, retryable=status == 503)
        super().__init__(message)


def require(condition, code, message, status=409, **kwargs):
    if not condition:
        raise DomainError(code, message, status, **kwargs)


def ts(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(value.tzinfo is not None, "timezone_required", "时间必须包含时区", 422)
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def json_value(value):
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        return ts(value)
    if isinstance(value, dict):
        return {k: json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(v) for v in value]
    return value


def record(obj, *, exclude=()):
    return json_value({column.name: getattr(obj, column.name) for column in inspect(obj).mapper.columns if column.name not in {"content", "artifact", "source_content", "token_hash", "pairing_hash", "enrollment_pairing_hash", *exclude}})


def digest(value):
    return sha256(json.dumps(json_value(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def add(db, entity_type, user=None, **values):
    item = entity_type(id=uuid4().hex, factory_id=m.FACTORY, created_by=getattr(user, "id", "system"), **values)
    db.add(item)
    db.flush()
    return item


REVERSIBLE = (m.UvOpsParticipation, m.UvOpsQualityEntry, m.UvOpsExpense, m.UvOpsWageAccrual, m.UvOpsRunCost)


def query(model, *, history=False):
    statement = select(model).where(model.factory_id == m.FACTORY)
    if not history and model in REVERSIBLE:
        statement = statement.where(model.active_key == 1)
    if not history and model == m.UvOpsWageAllocation:
        statement = statement.where(model.accrual_id.in_(select(m.UvOpsWageAccrual.id).where(m.UvOpsWageAccrual.factory_id == m.FACTORY, m.UvOpsWageAccrual.active_key == 1)))
    return statement


def get(db, model, entity_id, *, lock=False, version=None):
    statement = query(model, history=True).where(model.id == entity_id)
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    item = db.scalar(statement)
    require(item is not None, "not_found", "记录不存在或不属于当前厂区", 404)
    if version is not None:
        require(item.version == version, "version_conflict", "记录已被更新，请核对最新版本后重试", version=item.version)
    return item


def touch(item):
    item.version += 1
    item.updated_at = m.now()


def insert_once(db, model, values, keys):
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    insert = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
    statement = insert(model).values(**values).on_conflict_do_nothing(index_elements=keys).returning(model.id)
    return db.scalar(statement) is not None


def lock_period(db, business_date, *, closing=False, allow_closed=False):
    date.fromisoformat(business_date)
    period = business_date[:7]
    insert_once(db, m.UvOpsPeriod, dict(id=uuid4().hex, factory_id=m.FACTORY, period=period, status="open", version=1, created_at=m.now(), updated_at=m.now(), created_by="system"), ["factory_id", "period"])
    statement = query(m.UvOpsPeriod).where(m.UvOpsPeriod.period == period).with_for_update(read=not closing).execution_options(populate_existing=True)
    row = db.scalar(statement)
    if not closing and not allow_closed:
        require(row.status == "open", "period_closed", "该月已封账，请先通过有理由的重开或调整流程处理")
    return row


def money(value):
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def command(db, user, action, body, permissions, handler):
    """Unique receipt owns the command; a response is never emitted before commit."""
    payload_hash = digest(dict(action=action, body=body.model_dump(mode="json")))
    values = dict(id=uuid4().hex, factory_id=m.FACTORY, actor_id=user.id, operation_id=body.operation_id, action=action, payload_hash=payload_hash, permissions=list(permissions), result={}, version=1, created_at=m.now(), updated_at=m.now(), created_by=user.id)
    try:
        claimed = insert_once(db, m.UvOpsReceipt, values, ["factory_id", "actor_id", "operation_id"])
        receipt = db.scalar(query(m.UvOpsReceipt).where(m.UvOpsReceipt.actor_id == user.id, m.UvOpsReceipt.operation_id == body.operation_id))
        require(receipt.payload_hash == payload_hash, "operation_payload_conflict", "同一操作编号不能用于不同动作或数据")
        if not claimed:
            result = receipt.result
            db.rollback()
            return result
        result = json_value(handler())
        receipt.result = result
        add(db, m.UvOpsAudit, user, actor_id=user.id, operation_id=body.operation_id, action=action, entity_id=str(result.get("id", "")) if isinstance(result, dict) else "", reason=body.reason)
        db.commit()
        return result
    except IntegrityError:
        db.rollback()
        raise DomainError("constraint_conflict", "记录重复或关联数据已变化，请刷新核对") from None
    except OperationalError:
        db.rollback()
        raise DomainError("database_busy", "数据库暂忙，请保留当前操作编号稍后重试", 503) from None
    except Exception:
        db.rollback()
        raise


def values(body, *extra_exclude):
    return body.model_dump(exclude={"factory_id", "operation_id", "expected_version", "reason", *extra_exclude})


def revision(db):
    # Append-only facts + heartbeat versions, monotonic without a factory mutex.
    audit = select(func.count()).select_from(m.UvOpsAudit).scalar_subquery()
    events = select(func.count()).select_from(m.UvOpsAgentEventInbox).scalar_subquery()
    agents = select(func.coalesce(func.sum(m.UvOpsAgent.version), 0)).scalar_subquery()
    return db.scalar(select(audit+events+agents))
