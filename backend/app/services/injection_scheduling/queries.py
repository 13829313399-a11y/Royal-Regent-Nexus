from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import Float, String, and_, cast, func, not_, or_, select

from app.models.injection_scheduling import (
    Demand,
    FactorySettings,
    Machine,
    Run,
    SharedRevision,
)

from .calculations import now, timestamp
from .field_registry import FIELDS


def expression(key):
    if not isinstance(key, str) or key not in FIELDS:
        raise HTTPException(422, f"未知查询字段：{key}")
    if hasattr(Demand, key):
        return getattr(Demand, key)
    if key == "production_duration_hours":
        return (
            Demand.remaining_shots
            * Demand.target_basis_hours
            / func.nullif(Demand.target_shots_per_day, 0)
        )
    if key == "planned_completion_month":
        return func.substr(cast(Demand.planned_end_at, String), 1, 7)
    expr = Demand.extras[key].as_string()
    return (
        cast(expr, Float) if FIELDS[key].value_type in {"number", "integer"} else expr
    )


def _typed(key, value):
    if value is None:
        return None
    spec = FIELDS[key]
    try:
        if spec.value_type in {"number", "integer"}:
            result = float(value)
            if not -1e30 < result < 1e30:
                raise ValueError()
            return result
        if spec.value_type == "datetime":
            return timestamp(value)
        if len(str(value)) > 2000:
            raise ValueError()
        return str(value)
    except (ValueError, TypeError, OverflowError):
        raise HTTPException(422, f"{spec.label} 查询值类型不正确") from None


def filter_expression(node, as_of, depth=0, counter=None):
    counter = counter if counter is not None else [0]
    counter[0] += 1
    if depth > 6 or counter[0] > 100 or not isinstance(node, dict):
        raise HTTPException(422, "筛选条件过于复杂")
    op = node.get("op")
    if op in {"and", "or"}:
        children = node.get("children")
        if not isinstance(children, list) or not children:
            raise HTTPException(422, "组合筛选不能为空")
        terms = [filter_expression(n, as_of, depth + 1, counter) for n in children]
        return and_(*terms) if op == "and" else or_(*terms)
    key = node.get("field")
    expr = expression(key)
    if op not in FIELDS[key].filter_ops:
        raise HTTPException(422, f"{key} 不支持 {op}")
    value = node.get("value")
    if op == "is_empty":
        return (
            or_(expr.is_(None), expr == "")
            if FIELDS[key].value_type == "text"
            else expr.is_(None)
        )
    if op == "not_empty":
        return (
            and_(expr.is_not(None), expr != "")
            if FIELDS[key].value_type == "text"
            else expr.is_not(None)
        )
    if op in {"in", "not_in", "between"}:
        if (
            not isinstance(value, list)
            or not value
            or len(value) > 1000
            or op == "between"
            and len(value) != 2
        ):
            raise HTTPException(422, "列表或区间查询格式不正确")
        vals = [_typed(key, v) for v in value]
        if op == "between":
            return expr.between(*vals)
        return expr.in_(vals) if op == "in" else not_(expr.in_(vals))
    if op in {"today", "next_days", "on_day", "overdue"}:
        if op == "overdue":
            return expr < as_of
        try:
            day = (timestamp(value) if op == "on_day" else as_of).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            n = int(value) if op == "next_days" else 1
            if not 1 <= n <= 3660:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise HTTPException(422, "日期格式不正确或未来天数不在 1–3660") from None
        return and_(expr >= day, expr < day + timedelta(days=n))
    val = _typed(key, value)
    if op == "contains":
        return expr.contains(val, autoescape=True)
    if op == "prefix":
        return expr.startswith(val, autoescape=True)
    return {
        "eq": lambda: expr == val,
        "ne": lambda: expr != val,
        "gt": lambda: expr > val,
        "gte": lambda: expr >= val,
        "lt": lambda: expr < val,
        "lte": lambda: expr <= val,
    }[op]()


def query_conditions(payload, as_of=None):
    as_of = as_of or now()
    conditions = [Demand.factory_id == payload.factory_id]
    if payload.filter:
        conditions.append(filter_expression(payload.filter, as_of))
    if payload.search and payload.search.get("text"):
        s = payload.search
        mode = s.get("mode", "exact")
        if mode not in {"exact", "contains", "prefix", "in"}:
            raise HTTPException(422, "查找模式不正确")
        key = s.get("field", "mold_code")
        keys = (
            [key]
            if key != "all"
            else [k for k, f in FIELDS.items() if f.value_type == "text"]
        )
        value = str(s["text"])
        if len(value) > 20000:
            raise HTTPException(422, "查找内容过长")
        terms = []
        for field in keys:
            expr = expression(field)
            if mode == "in":
                vals = [
                    v.strip()
                    for v in value.replace("\t", "\n").splitlines()
                    if v.strip()
                ]
                if len(vals) > 1000:
                    raise HTTPException(422, "批量查找最多 1000 个值")
                terms.append(expr.in_(vals))
            elif mode == "exact":
                terms.append(expr == _typed(field, value))
            elif mode == "contains":
                terms.append(cast(expr, String).contains(value, autoescape=True))
            else:
                terms.append(cast(expr, String).startswith(value, autoescape=True))
        conditions.append(or_(*terms))
    return conditions


def ordered_query(payload, as_of=None):
    query = select(Demand).where(*query_conditions(payload, as_of))
    sort = payload.sort or [{"field": "delivery_due_at", "direction": "asc"}]
    for entry in sort:
        expr = expression(entry.get("field"))
        direction = entry.get("direction", "asc")
        if direction not in {"asc", "desc"}:
            raise HTTPException(422, "排序方向不正确")
        query = query.order_by(
            expr.is_(None), expr.desc() if direction == "desc" else expr.asc()
        )
    return query.order_by(Demand.id)


def revision(db, factory):
    settings = db.get(FactorySettings, factory)
    shared = db.get(SharedRevision, "shared")
    return {
        "revision": settings.revision if settings else 0,
        "shared_revision": shared.revision if shared else 0,
    }


def summary(db, payload, as_of=None):
    conditions = query_conditions(payload, as_of)
    result = db.execute(
        select(
            func.count(Demand.id),
            func.sum(Demand.planned_shots),
            func.sum(Demand.completed_shots),
            func.sum(Demand.remaining_shots),
            func.sum(Demand.remaining_material_kg),
            func.sum(Demand.remaining_processing_amount),
        ).where(*conditions)
    ).one()
    count = lambda cond: (
        db.scalar(select(func.count(Demand.id)).where(*conditions, cond)) or 0
    )
    return {
        "total_count": result[0],
        "planned_shots": float(result[1] or 0),
        "completed_shots": float(result[2] or 0),
        "remaining_shots": float(result[3] or 0),
        "remaining_material_kg": float(result[4] or 0),
        "remaining_processing_amount": float(result[5] or 0),
        "pending_count": count(
            and_(Demand.planned_start_at.is_(None), Demand.remaining_shots > 0)
        ),
        "held_count": count(Demand.dispatch_state != "READY"),
        "late_count": count(Demand.delivery_slack_hours < 0),
        "unresolved_count": count(Demand.unplaced_reason.is_not(None)),
        "missing_price_count": count(Demand.price_per_shot.is_(None)),
        "machine_count": db.scalar(
            select(func.count(Machine.id)).where(
                Machine.factory_id == payload.factory_id
            )
        )
        or 0,
        "running_count": db.scalar(
            select(func.count(Run.id)).where(
                Run.factory_id == payload.factory_id, Run.status == "RUNNING"
            )
        )
        or 0,
        **revision(db, payload.factory_id),
    }
