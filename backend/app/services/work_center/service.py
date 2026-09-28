from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import Float, and_, case, exists, false, func, literal, or_, select, union_all
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.functions import FunctionElement

from app.core.time import parse_business_timestamp, BUSINESS_TIME_ZONE
from app.models.auth import EmployeeProfile
from app.models.work_center import WorkCenterEntry as Entry, WorkCenterEvent, WorkCenterUserState as State, WorkCenterPreferences
from app.services.work_center.registry import COVERAGE, current_query, scoped


class Epoch(FunctionElement):
    type = Float()
    inherit_cache = True


@compiles(Epoch, "sqlite")
def sqlite_epoch(element, compiler, **kw):
    value = compiler.process(list(element.clauses)[0], **kw)
    # Offset-less legacy values are business wall time. Explicit ISO offsets
    # and Z are already handled by julianday.
    return f"((julianday({value}) - 2440587.5) * 86400 - CASE WHEN upper(substr({value}, -1)) = 'Z' OR instr(substr({value}, 20), '+') > 0 OR instr(substr({value}, 20), '-') > 0 THEN 0 ELSE 28800 END)"


@compiles(Epoch, "postgresql")
def postgres_epoch(element, compiler, **kw):
    value = compiler.process(list(element.clauses)[0], **kw)
    return (f"CASE WHEN {value} IS NULL OR {value} = '' THEN NULL "
            f"WHEN {value} ~ '([Zz]|[+-][0-9]{{2}}:[0-9]{{2}})$' THEN extract(epoch FROM CAST({value} AS timestamptz)) "
            f"ELSE extract(epoch FROM (CAST({value} AS timestamp) AT TIME ZONE 'Asia/Shanghai')) END")


def now():
    return datetime.now(timezone.utc)


def stamp(value):
    if not value:
        return None
    if isinstance(value, str):
        value = parse_business_timestamp(value)
        if value is None:
            return None
    return value.replace(tzinfo=value.tzinfo or timezone.utc).astimezone(timezone.utc).isoformat()


def authorization_boundary(user, clock):
    values = [(user.identity or {}).get("next_transition_at")]
    for item in (*user.grants, *user.overrides): values.extend((item.valid_from, item.valid_until))
    future = [value for raw in values if raw for value in [parse_business_timestamp(raw)] if value and value > clock]
    return stamp(min(future)) if future else None


def context(db, user):
    profile = db.get(EmployeeProfile, user.id)
    epoch = profile.employment_epoch if profile else 1
    fingerprint = hashlib.sha256(repr((user.id, epoch, user.authorization_version, user.grants,
                                      user.overrides, user.effective_access,
                                      (user.identity or {}).get("effective_context_key"))).encode()).hexdigest()[:32]
    return epoch, fingerprint


def history_visibility(db, user, e):
    from app.models.molding_sample import MoldingSampleOrder as M
    from app.models.internal_quote import InternalQuote as Q
    from app.models.carton_supplier_portal import SupplierShipment as S
    from app.models.auth import AuthRegistrationRequest as R, AuthPasswordResetRequest as P
    from app.services.internal_quote import ALL_QUOTE_DEPARTMENTS
    from app.services.system import is_superadmin
    from app.services.auth import ALLOWED_FACTORY_IDS, ALLOWED_DEPARTMENTS, can
    mold = exists(select(M.id).where(M.id == e.entity_id, or_(
        scoped(user, M.factory_id, "molding_sample:read", ("engineering", "management"), duty=False),
        and_(M.status.in_(("待生产", "生产中", "已完成")), scoped(user, M.production_factory_id, "molding_sample:production_read", ("production", "molding"), duty=False)))))
    quote = exists(select(Q.id).where(Q.id == e.entity_id, scoped(user, Q.factory_id, "internal_quote:read", ALL_QUOTE_DEPARTMENTS, duty=False)))
    shipment = exists(select(S.id).where(S.id == e.entity_id, and_(*(scoped(user, S.factory_id, p, ("pmc-warehouse", "carton"), duty=False)
        for p in ("carton_procurement:read", "carton_procurement:receipt_write", "carton_procurement:inventory_write")))))
    registration = exists(select(R.id).where(R.id == e.entity_id, literal(True) if is_superadmin(user) else or_(false(), *[
        and_(R.factory_id == f, R.department == d) for f in ALLOWED_FACTORY_IDS for d in ALLOWED_DEPARTMENTS if can(user, "system:user_manage", f, d)])))
    from app.services.work_center.registry import reset_visibility
    reset = exists(select(P.id).where(P.id == e.entity_id, reset_visibility(db, user, history=True)))
    return or_(and_(e.module == "molding", mold), and_(e.module == "internal_quote", quote),
               and_(e.module == "carton_supplier", shipment), and_(e.module == "account_requests", or_(registration, reset)))


def authorized_rows(db, user):
    # Reuse one materialized source set for history anti-join and counts. A
    # correlated union per historical entry becomes quadratic at backlog scale.
    current = select(current_query(db, user)).cte("source_work")
    # History has a normalized evidence payload, but current authorization is
    # always obtained from the source entity, never historical recipients.
    e = Entry.__table__.c
    history = select(*(e.evidence[name].as_string().label(name) if name not in ("id", "module", "entity_id", "kind", "lifecycle", "content_version", "can_act", "verified") else
                       (literal(name == "verified").label(name) if name in ("can_act", "verified") else e[name].label(name))
                       for name in current.c.keys())).select_from(Entry.__table__.outerjoin(current, current.c.id == e.id)).where(
                           e.kind == "task", e.lifecycle.in_(("resolved", "cancelled", "superseded")),
                           history_visibility(db, user, e), current.c.id.is_(None))
    all_rows = (select(current) if db.info.get("work_center_unavailable") else union_all(select(current), history)).subquery("visible_work")
    epoch, viewer_key = context(db, user)
    joined = select(all_rows, func.coalesce(Entry.content_version, all_rows.c.content_version).label("version"),
                    func.coalesce(Entry.attention_version, 0).label("attention"), Entry.resolution_reason,
                    func.coalesce(State.read_version, 0).label("read_version"), State.snoozed_until,
                    State.snoozed_attention_version, State.archived_at, State.pinned_at,
                    func.coalesce(State.state_version, 0).label("state_version"),
                    func.coalesce(State.following, True).label("following"),
                    func.coalesce(Epoch(all_rows.c.opened), 0).label("opened_epoch"),
                    Epoch(case((func.length(all_rows.c.due) == 10, all_rows.c.due + " 23:59:59"), else_=all_rows.c.due)).label("due_epoch")
                    ).outerjoin(Entry, Entry.id == all_rows.c.id).outerjoin(State, and_(State.entry_id == all_rows.c.id,
                        State.user_id == user.id, State.employment_epoch == epoch)).subquery("personal_work")
    return joined, viewer_key


def flags(rows, user, clock):
    c = rows.c
    actionable = and_(c.kind == "task", c.can_act.is_(True), c.lifecycle.in_(("open", "in_progress")))
    snoozed = and_(actionable, c.snoozed_until > clock, c.snoozed_attention_version == c.attention)
    info = and_(c.kind == "info", c.archived_at.is_(None))
    unread = and_(c.attention > 0, c.read_version < c.version)
    return dict(actionable_total=actionable, assigned_total=and_(actionable, c.assignee == user.id),
                team_queue_total=and_(actionable, c.assignee != user.id), focus_total=and_(actionable, ~func.coalesce(snoozed, False)),
                snoozed_total=snoozed, overdue_total=and_(actionable, c.due_epoch < clock.timestamp()),
                info_unread_total=and_(info, unread), waiting_total=and_(c.kind == "task", ~c.can_act,
                    c.lifecycle.in_(("open", "in_progress")), c.watcher == user.id, c.following.is_(True)))


def decode_cursor(cursor, fingerprint):
    try:
        value = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
        if value["q"] != fingerprint or len(value["k"]) != 5:
            raise ValueError()
        if any(type(x) not in (int, float) or not math.isfinite(x) for x in value["k"][:4]) or not isinstance(value["k"][4], str):
            raise ValueError()
        return value["k"]
    except (ValueError, KeyError, TypeError, UnicodeError, binascii.Error):
        raise HTTPException(409, "查询范围已改变，请重新载入第一页")


def encode_cursor(fingerprint, values):
    return base64.urlsafe_b64encode(json.dumps({"q": fingerprint, "k": values}, separators=(",", ":")).encode()).decode()


def snapshot(db, user, *, view="todo", factory_scope="authorized", module="", q="", unread_only=False,
             due="all", cursor=None, limit=30, selected_id=None):
    from app.services.auth import ALLOWED_FACTORY_IDS
    if view not in {"todo", "assigned", "team", "waiting", "info", "history"}:
        raise HTTPException(422, "事项视图无效")
    if factory_scope != "authorized" and factory_scope not in ALLOWED_FACTORY_IDS:
        raise HTTPException(422, "厂区范围无效")
    if due not in {"all", "none", "today", "overdue"}:
        raise HTTPException(422, "期限筛选无效")
    clock = now()
    rows, viewer_key = authorized_rows(db, user)
    c, f = rows.c, flags(rows, user, clock)
    summary_query = select(*(func.coalesce(func.sum(case((condition, 1), else_=0)), 0).label(name) for name, condition in f.items()),
        func.coalesce(func.sum(case((c.verified.is_(False), 1), else_=0)), 0).label("verification_required_total")).select_from(rows)
    summary = dict(db.execute(summary_query).mappings().one())
    conditions = {"todo": f["actionable_total"], "assigned": f["assigned_total"], "team": f["team_queue_total"],
                  "waiting": f["waiting_total"], "info": and_(c.kind == "info", c.archived_at.is_(None)),
                  "history": or_(c.lifecycle.in_(("resolved", "cancelled", "superseded")), c.archived_at.is_not(None))}
    query = select(rows).where(conditions[view])
    if factory_scope != "authorized":
        query = query.where(or_(c.factory == factory_scope, c.execution == factory_scope))
    if module:
        query = query.where(c.module == module)
    if q.strip():
        term = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.where(or_(c.reference.ilike(f"%{term}%", escape="\\"), c.title.ilike(f"%{term}%", escape="\\"), c.summary.ilike(f"%{term}%", escape="\\")))
    if unread_only:
        query = query.where(c.attention > 0, c.read_version < c.version)
    today = clock.astimezone(BUSINESS_TIME_ZONE).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    if due == "none": query = query.where(c.due_epoch.is_(None))
    if due == "overdue": query = query.where(c.due_epoch < clock.timestamp())
    if due == "today": query = query.where(c.due_epoch >= today, c.due_epoch < today + 86400)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    # Stable keyset; neither creation IDs nor browser clocks are event cursors.
    ordering = [case((f["snoozed_total"], 1), else_=0), case((c.due_epoch < clock.timestamp(), 0), (and_(c.due_epoch >= today, c.due_epoch < today + 86400), 1), else_=2),
                func.coalesce(c.due_epoch, 253402300799.0), c.opened_epoch, c.id]
    fingerprint = hashlib.sha256(json.dumps([viewer_key, view, factory_scope, module, q, unread_only, due]).encode()).hexdigest()[:24]
    if cursor:
        values = decode_cursor(cursor, fingerprint)
        query = query.where(or_(*(and_(*(ordering[j] == values[j] for j in range(i)), ordering[i] > values[i]) for i in range(len(ordering)))))
    page = db.execute(query.add_columns(*(value.label(f"sort_{i}") for i, value in enumerate(ordering))).order_by(*ordering).limit(limit + 1)).mappings().all()
    next_cursor = encode_cursor(fingerprint, [page[limit-1][f"sort_{i}"] for i in range(5)]) if len(page) > limit else None
    selected = None
    if selected_id:
        selected_row = db.execute(select(rows).where(c.id == selected_id, c.kind.in_(("task", "info")))).mappings().first()
        selected = dto(selected_row, user, clock) if selected_row else {"id": selected_id, "state": "unavailable"}
    return {"context": {"viewer_key": viewer_key, "scope_key": factory_scope, "server_time": stamp(clock),
                        "business_timezone": "Asia/Shanghai", "authz_recheck_at": authorization_boundary(user, clock)},
            "summary": summary, "query": {"filtered_total": total, "cursor": cursor},
            "items": [dto(item, user, clock) for item in page[:limit]], "next_cursor": next_cursor,
            "selected_entry_state": selected, "health": {"status": "partial" if summary["verification_required_total"] or db.info.get("work_center_unavailable") else "fresh", "as_of": stamp(clock), "unavailable_sources": sorted(db.info.get("work_center_unavailable", [])), "coverage": COVERAGE}}


def dto(row, user, clock):
    from app.services.molding_sample import FACTORY_LABELS
    from app.services.internal_quote import SECTION_NAMES
    active = bool(row["can_act"]) and row["lifecycle"] in ("open", "in_progress")
    assigned = row["assignee"] == user.id
    relation = "assignee" if active and assigned else "candidate" if active else "recipient" if row["kind"] == "info" else "watcher"
    stage = row["stage"]
    route = {"molding": "molding_production" if stage.startswith("production") else "molding_engineering",
             "internal_quote": "quote", "account_requests": "account_requests", "carton_supplier": "shipment", "identity": "identity"}[row["module"]]
    snoozed = row["snoozed_until"] if row["snoozed_attention_version"] == row["attention"] else None
    read_state = "read" if row["read_version"] >= row["version"] else "legacy_unknown" if row["attention"] == 0 else "unread"
    factory = lambda value: {"id": value, "label": FACTORY_LABELS.get(value, value)} if value else None
    return {"id": row["id"], "kind": row["kind"], "module": row["module"], "title": row["title"], "summary": row["summary"],
            "reference_label": row["reference"], "lifecycle": row["lifecycle"], "viewer_relation": relation,
            "source_factory": factory(row["factory"]), "execution_factory": factory(row["execution"]),
            "department_label": SECTION_NAMES.get(row["department"], {"production": "啤机部", "pmc-warehouse": "PMC仓库", "sales-business": "业务部", "management": "管理部"}.get(row["department"], row["department"])),
            "stage_label": row["title"], "responsible_label": "指派给我" if assigned else "团队队列" if active else "流程跟进",
            "why_me": "你是本批次指定审核人" if assigned and row["module"] == "internal_quote" else "你具备当前责任范围的办理权限" if active else "与你相关的流程信息",
            "priority": "normal", "priority_reasons": ["已到业务期限"] if row["due_epoch"] and row["due_epoch"] < clock.timestamp() else [],
            "due_at": stamp(datetime.fromtimestamp(row["due_epoch"], timezone.utc)) if row["due_epoch"] else None,
            "due_source": "business" if row["due_epoch"] else None, "opened_at": stamp(row["opened"]),
            "can_act_now": active, "unavailable_reason": None if active or row["kind"] == "info" else row["resolution_reason"] or "当前阶段等待其他责任人处理",
            "resolution_reason": row["resolution_reason"], "verification_state": "verified" if row["verified"] else "unverified",
            "content_version": row["version"], "attention_version": row["attention"],
            "personal": {"read_state": read_state, "snoozed_until": stamp(snoozed), "archived_at": stamp(row["archived_at"]), "pinned": bool(row["pinned_at"]), "state_version": row["state_version"], "following": row["following"]},
            "actions": [{"key": "open", "label": "刷新账户信息" if route == "identity" else row["title"] if active else "查看源单据",
                         "mode": "refresh_identity" if route == "identity" else "navigate", "enabled": True, "disabled_reason": None,
                         "target": {"route_key": route, "params": {"id": row["entity_id"]}, "query": {"factory": row["execution"] if route == "molding_production" else row["factory"], "stage": stage, "cycle": row["cycle"]}}}]}


def detail(db, user, entry_id):
    rows, _ = authorized_rows(db, user)
    row = db.execute(select(rows).where(rows.c.id == entry_id, rows.c.kind.in_(("task", "info")))).mappings().first()
    if not row:
        raise HTTPException(404, "事项已失效或不在当前可见范围")
    return dto(row, user, now())


def events(db, user, entry_id, cursor=None, limit=5):
    detail(db, user, entry_id)
    _, viewer_key = context(db, user)
    fingerprint = f"{viewer_key}:{entry_id}"
    query = select(WorkCenterEvent).where(WorkCenterEvent.entry_id == entry_id)
    if cursor:
        try:
            value = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
            occurred = datetime.fromisoformat(value["at"])
            if value["q"] != fingerprint or not isinstance(value["id"], str):
                raise ValueError()
        except (ValueError, KeyError, TypeError, UnicodeError, binascii.Error):
            raise HTTPException(409, "经过查询范围已改变，请重新载入")
        query = query.where(or_(WorkCenterEvent.occurred_at < occurred,
            and_(WorkCenterEvent.occurred_at == occurred, WorkCenterEvent.id < value["id"])))
    rows = db.scalars(query.order_by(WorkCenterEvent.occurred_at.desc(), WorkCenterEvent.id.desc()).limit(limit + 1)).all()
    next_cursor = base64.urlsafe_b64encode(json.dumps({"q": fingerprint, "at": stamp(rows[limit-1].occurred_at), "id": rows[limit-1].id}).encode()).decode() if len(rows) > limit else None
    return {"items": [{"id": item.id, "occurred_at": stamp(item.occurred_at), "summary": item.safe_summary} for item in rows[:limit]],
            "next_cursor": next_cursor}


def patch_state(db, user, entry_id, payload):
    from app.services.transaction_lock import lock_transaction
    epoch, _ = context(db, user)
    lock_transaction(db, "work-center-state", f"{user.id}:{epoch}:{entry_id}")
    entry = detail(db, user, entry_id)
    state = db.get(State, (user.id, epoch, entry_id))
    if state is None:
        state = State(user_id=user.id, employment_epoch=epoch, entry_id=entry_id, read_version=0, state_version=0)
        db.add(state)
    changes = payload.model_fields_set
    # Reading uses monotonic max; other personal changes use optimistic version.
    if changes - {"observed_content_version", "state_version"} and payload.state_version != state.state_version:
        raise HTTPException(409, "个人设置已在另一设备更新，请刷新后重试")
    if payload.observed_content_version is not None:
        if payload.observed_content_version > entry["content_version"]:
            raise HTTPException(409, "观察版本无效，请刷新事项")
        state.read_version = max(state.read_version, payload.observed_content_version)
        state.read_at = now()
    if "snoozed_until" in changes:
        if payload.snoozed_until and (payload.snoozed_until.tzinfo is None or payload.snoozed_until <= now()):
            raise HTTPException(422, "稍后时间必须为带时区的未来时间")
        state.snoozed_until = payload.snoozed_until
        state.snoozed_attention_version = entry["attention_version"]
    if payload.archived is not None:
        if payload.archived and entry["kind"] == "task" and entry["lifecycle"] in ("open", "in_progress"):
            raise HTTPException(409, "当前责任只能通过原业务结束，不能归档")
        state.archived_at = now() if payload.archived else None
    if payload.pinned is not None:
        state.pinned_at = now() if payload.pinned else None
    if payload.following is not None:
        state.following = payload.following
    state.state_version += 1
    db.flush()
    return detail(db, user, entry_id)


def preferences(db, user, payload=None):
    if payload is not None:
        from app.services.transaction_lock import lock_transaction
        lock_transaction(db, "work-center-preferences", user.id)
    row = db.get(WorkCenterPreferences, user.id)
    defaults = {"sound_enabled": False, "toast_level": "assigned", "business_timezone": "Asia/Shanghai"}
    if payload is not None:
        if payload.version != (row.version if row else 0):
            raise HTTPException(409, "提醒偏好已更新，请刷新后重试")
        if row is None:
            row = WorkCenterPreferences(user_id=user.id, values={}, version=0, updated_at=now())
            db.add(row)
        row.values = {**row.values, **payload.model_dump(exclude_none=True, exclude={"version"})}
        row.version += 1
        row.updated_at = now()
        db.flush()
    return {**defaults, **(row.values if row else {}), "version": row.version if row else 0}
