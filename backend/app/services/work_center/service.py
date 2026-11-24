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
from app.models.carton_procurement import CartonSupplier
from app.models.carton_supplier_portal import SupplierShipment, SupplierShipmentLine, SupplierShipmentUnmatchedLine
from app.models.molding_sample import MoldingSampleOrder
from app.models.position_review import PositionReview

MODULE_LABELS = {"molding": "啤办", "internal_quote": "内部报价", "account_requests": "账户申请",
                 "carton_supplier": "供应商送货", "identity": "任职知会", "position_reviews": "岗位核对"}


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
    from app.services.position_workbench_read import visible_registration_ids
    registration = exists(select(R.id).where(R.id == e.entity_id, R.id.in_(visible_registration_ids(db, user))))
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
    if view not in {"todo", "assigned", "team", "waiting", "info", "history", "verification"}:
        raise HTTPException(422, "事项视图无效")
    if factory_scope != "authorized" and factory_scope not in ALLOWED_FACTORY_IDS:
        raise HTTPException(422, "厂区范围无效")
    if due not in {"all", "none", "today", "overdue"}:
        raise HTTPException(422, "期限筛选无效")
    clock = now()
    rows, viewer_key = authorized_rows(db, user)
    c, f = rows.c, flags(rows, user, clock)
    not_overdue = or_(c.due_epoch.is_(None), c.due_epoch >= clock.timestamp())
    f.update(overdue_active_total=and_(f["focus_total"], f["overdue_total"]),
             assigned_focus_total=and_(f["focus_total"], not_overdue, f["assigned_total"]),
             team_focus_total=and_(f["focus_total"], not_overdue, f["team_queue_total"]))
    summary_query = select(*(func.coalesce(func.sum(case((condition, 1), else_=0)), 0).label(name) for name, condition in f.items()),
        func.coalesce(func.sum(case((c.verified.is_(False), 1), else_=0)), 0).label("verification_required_total")).select_from(rows)
    summary = dict(db.execute(summary_query).mappings().one())
    # Historical orphan notices and currently inconsistent tasks have different
    # user impact. Keep both visible without implying a source outage.
    issues = []
    if summary["verification_required_total"]:
        issue_rows = db.execute(select(c.module, c.kind, func.count().label("count"))
                                .where(c.verified.is_(False)).group_by(c.module, c.kind)).mappings()
        issues = [{"module": item["module"], "reason": "source_missing" if item["kind"] == "diagnostic" else "source_inconsistent",
                   "count": item["count"]} for item in issue_rows]
    conditions = {"todo": f["actionable_total"], "assigned": f["assigned_total"], "team": f["team_queue_total"],
                  "waiting": f["waiting_total"], "info": and_(c.kind == "info", c.archived_at.is_(None)),
                  "history": or_(c.lifecycle.in_(("resolved", "cancelled", "superseded")), c.archived_at.is_not(None)),
                  "verification": and_(c.kind == "task", c.verified.is_(False))}
    query = select(rows).where(conditions[view])
    if q.strip():
        term = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.where(or_(c.reference.ilike(f"%{term}%", escape="\\"), c.title.ilike(f"%{term}%", escape="\\"), c.summary.ilike(f"%{term}%", escape="\\"),
                               and_(c.module == "account_requests", c.entity_id.ilike(f"%{term}%", escape="\\"))))
    if unread_only:
        query = query.where(c.attention > 0, c.read_version < c.version)
    today = clock.astimezone(BUSINESS_TIME_ZONE).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    if due == "none": query = query.where(c.due_epoch.is_(None))
    if due == "overdue": query = query.where(c.due_epoch < clock.timestamp())
    if due == "today": query = query.where(c.due_epoch >= today, c.due_epoch < today + 86400)
    # Count facets before keyset pagination. Each visible row counts once per
    # matching factory, including when source and execution are the same.
    from app.services.molding_sample import FACTORY_LABELS
    def factory_matches(factory):
        return or_(c.factory == factory, c.execution == factory)

    factory_filter = factory_matches(factory_scope) if factory_scope != "authorized" else literal(True)
    module_filter = c.module == module if module else literal(True)
    factory_counts = {factory: and_(factory_matches(factory), module_filter) for factory in sorted(ALLOWED_FACTORY_IDS)}
    module_counts = {key: and_(c.module == key, factory_filter) for key in MODULE_LABELS}
    counts = db.execute(query.with_only_columns(
        func.count(case((and_(factory_filter, module_filter), 1))).label("total"),
        *(func.count(case((condition, 1))).label(key) for key, condition in (factory_counts | module_counts).items()),
        maintain_column_froms=True)).mappings().one()
    facets = {"factories": [{"id": key, "label": FACTORY_LABELS.get(key, key), "count": counts[key]}
                            for key in factory_counts if counts[key]],
              "modules": [{"id": key, "label": MODULE_LABELS[key], "count": counts[key]}
                          for key in module_counts if counts[key]]}
    total = counts["total"]
    query = query.where(factory_filter, module_filter)
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
    selected_row = None
    if selected_id:
        selected_row = db.execute(select(rows).where(c.id == selected_id, c.kind.in_(("task", "info")))).mappings().first()
        if not selected_row:
            selected = {"id": selected_id, "state": "unavailable"}
    presented = present_entries(db, [*page[:limit], *([selected_row] if selected_row else [])], user, clock)
    if selected_row:
        selected = presented[-1]
    return {"context": {"viewer_key": viewer_key, "scope_key": factory_scope, "server_time": stamp(clock),
                        "business_timezone": "Asia/Shanghai", "authz_recheck_at": authorization_boundary(user, clock)},
            "summary": summary, "facets": facets, "query": {"filtered_total": total, "cursor": cursor},
            "items": presented[:len(page[:limit])], "next_cursor": next_cursor,
            "selected_entry_state": selected, "health": {"status": "partial" if summary["verification_required_total"] or db.info.get("work_center_unavailable") else "fresh", "as_of": stamp(clock), "unavailable_sources": sorted(db.info.get("work_center_unavailable", [])), "issues": issues, "coverage": COVERAGE}}


def dto(row, user, clock):
    from app.services.molding_sample import FACTORY_LABELS
    from app.services.internal_quote import SECTION_NAMES
    active = bool(row["can_act"]) and row["lifecycle"] in ("open", "in_progress")
    assigned = row["assignee"] == user.id
    relation = "assignee" if active and assigned else "candidate" if active else "recipient" if row["kind"] == "info" else "watcher"
    stage = row["stage"]
    reasons = []
    due = row["due_epoch"]
    today = clock.astimezone(BUSINESS_TIME_ZONE).date()
    if active and due is not None and due < clock.timestamp():
        reasons.append("已到业务期限")
    elif active:
        if due is not None and datetime.fromtimestamp(due, BUSINESS_TIME_ZONE).date() == today:
            reasons.append("今日到期")
        if stage.startswith("problem:"):
            reasons.append("生产待处理问题")
        if row["opened_epoch"] and clock.timestamp() - row["opened_epoch"] >= 72 * 3600:
            reasons.append("等待超过 3 天")
    route = {"molding": "molding_production" if stage.startswith("production") else "molding_engineering",
             "internal_quote": "quote", "account_requests": "account_requests", "carton_supplier": "shipment",
             "identity": "identity_approval" if stage == "identity_approval" else "identity",
             "position_reviews": "my_position" if stage == "position_result" else "position_workbench"}[row["module"]]
    snoozed = row["snoozed_until"] if row["snoozed_attention_version"] == row["attention"] else None
    read_state = "read" if row["read_version"] >= row["version"] else "legacy_unknown" if row["attention"] == 0 else "unread"
    factory_labels = {**FACTORY_LABELS, "*": "全集团", "group": "集团", "group-management": "集团职能部门"}
    factory = lambda value: {"id": value, "label": factory_labels.get(value, value)} if value else None
    return {"id": row["id"], "kind": row["kind"], "module": row["module"], "title": row["title"], "summary": row["summary"],
            "reference_label": row["reference"], "lifecycle": row["lifecycle"], "viewer_relation": relation,
            "source_factory": factory(row["factory"]), "execution_factory": factory(row["execution"]),
            "department_label": SECTION_NAMES.get(row["department"], {"production": "啤机部", "pmc-warehouse": "PMC仓库", "sales-business": "业务部", "management": "管理部", "system": "系统管理", "*": "全部部门", "three-d-printing": "3D打印部"}.get(row["department"], row["department"])),
            "stage_code": stage, "stage_label": row["title"], "responsible_label": "指派给我" if assigned else "团队队列" if active else "流程跟进",
            "why_me": "你是本批次指定审核人" if assigned and row["module"] == "internal_quote" else "你具备当前责任范围的办理权限" if active else "与你相关的流程信息",
            "priority": "urgent" if "已到业务期限" in reasons else "high" if reasons else "normal", "priority_reasons": reasons,
            "due_at": stamp(datetime.fromtimestamp(row["due_epoch"], timezone.utc)) if row["due_epoch"] else None,
            "due_source": "business" if row["due_epoch"] else None, "opened_at": stamp(row["opened"]),
            "can_act_now": active, "unavailable_reason": "当前业务版本或状态需要核对，请查看源单据。" if not row["verified"] else None if active or row["kind"] == "info" else row["resolution_reason"] or "当前阶段等待其他责任人处理",
            "resolution_reason": row["resolution_reason"], "verification_state": "verified" if row["verified"] else "unverified",
            "content_version": row["version"], "attention_version": row["attention"],
            "personal": {"read_state": read_state, "snoozed_until": stamp(snoozed), "archived_at": stamp(row["archived_at"]), "pinned": bool(row["pinned_at"]), "state_version": row["state_version"], "following": row["following"]},
            "actions": [{"key": "open", "label": "刷新账户信息" if route == "identity" else row["title"] if active else "查看源单据",
                         "mode": "refresh_identity" if route == "identity" else "navigate", "enabled": True, "disabled_reason": None,
                         "target": {"route_key": route, "params": {"id": row["cycle"] if route == "identity_approval" else row["entity_id"]}, "query": {"factory": row["execution"] if route == "molding_production" else row["factory"], "stage": stage, "cycle": row["cycle"]}}}]}


def details(*fields):
    return [{"label": label, "value": str(value)} for label, value in fields if value is not None and value != ""]


def quote_facts(quote):
    batch = quote.batch_size and quote.batch_size > 1
    parts = [f"本批共 {quote.batch_size} 款" if batch else quote.product_name]
    if quote.customer:
        parts.append(f"客户 {quote.customer}")
    parts.append(f"含 {quote.product_name} 等" if batch else f"数量 {quote.qty}")
    return {"summary": " · ".join(filter(None, parts)), "details": details(
        ("产品名称", quote.product_name), ("客户", quote.customer), ("数量", quote.qty),
        ("批次规模", quote.batch_size if batch else None), ("目标日期", quote.target_date), ("发起人", quote.created_by_name))}


def position_facts(review):
    from app.services.iam import DEPARTMENT_NAMES
    def snapshot(raw):
        try:
            value = json.loads(raw or "null")
        except (TypeError, ValueError):
            return {}
        return value if isinstance(value, dict) else {}

    declared = snapshot(review.declared_snapshot_json)
    original = snapshot(review.base_official_snapshot_json)
    position, previous = declared.get("position"), original.get("position")
    department = DEPARTMENT_NAMES.get(declared.get("department_code"))
    summary = f"申报岗位：{position}" if position else ""
    if previous and previous != position:
        summary += f"（原：{previous}）"
    elif department:
        summary = " · ".join(filter(None, [summary, department]))
    fields = details(("申报岗位", position), ("原任职岗位", previous or "未记录"),
                     ("发起方式", {"employee": "员工自报", "admin": "管理员发起"}.get(review.origin)))
    if review.last_submitted_at:
        fields.append({"label": "最近提交时间", "value": review.last_submitted_at, "format": "datetime"})
    return {"summary": summary, "details": fields}


def molding_facts(order):
    parts = [order.product_name]
    if order.client_name:
        parts.append(f"客户 {order.client_name}")
    rejected = order.reject_reason if order.status == "已驳回" else None
    if rejected:
        parts.append(f"驳回：{rejected}")
    return {"summary": " · ".join(filter(None, parts)), "details": details(
        ("产品名称", order.product_name), ("客户", order.client_name), ("负责工程", order.eng_name),
        ("所属车间", order.workshop), ("当前状态", order.status), ("驳回说明", rejected))}


def shipment_facts(db, ids):
    shipment = SupplierShipment
    # Restrict each aggregate to page IDs and join on the factory as well as
    # the shipment key. Matched lines and unmatched lines are disjoint.
    def line_counts(model):
        return (select(model.shipment_id, model.factory_id, func.count().label("n"))
                .where(model.shipment_id.in_(ids)).group_by(model.shipment_id, model.factory_id).subquery())

    matched, unmatched = line_counts(SupplierShipmentLine), line_counts(SupplierShipmentUnmatchedLine)
    query = (select(shipment.id, shipment.delivery_note_no, shipment.delivery_date, CartonSupplier.supplier_name,
                    func.coalesce(matched.c.n, 0), func.coalesce(unmatched.c.n, 0))
             .outerjoin(CartonSupplier, and_(CartonSupplier.id == shipment.supplier_id, CartonSupplier.factory_id == shipment.factory_id))
             .outerjoin(matched, and_(matched.c.shipment_id == shipment.id, matched.c.factory_id == shipment.factory_id))
             .outerjoin(unmatched, and_(unmatched.c.shipment_id == shipment.id, unmatched.c.factory_id == shipment.factory_id))
             .where(shipment.id.in_(ids)))
    for entity_id, note, delivery, supplier, regular, extra in db.execute(query):
        count = regular + extra
        summary = " · ".join(filter(None, (supplier, f"{count} 项明细", f"交期 {delivery}" if delivery else None,
                                             f"含 {extra} 项无单明细" if extra else None)))
        yield ("carton_supplier", entity_id), {"summary": summary, "details": details(
            ("供应商", supplier), ("送货单号", note), ("送货日期", delivery), ("明细项数", count))}


def page_facts(db, rows):
    ids = {}
    for row in rows:
        if row["kind"] != "diagnostic":
            ids.setdefault(row["module"], set()).add(row["entity_id"])
    result = {}
    for module, model, formatter in (("molding", MoldingSampleOrder, molding_facts),
                                     ("position_reviews", PositionReview, position_facts)):
        if module in ids:
            result.update(((module, record.id), formatter(record))
                          for record in db.scalars(select(model).where(model.id.in_(ids[module]))))
    if "carton_supplier" in ids:
        result.update(shipment_facts(db, ids["carton_supplier"]))
    return result


def present_entries(db, rows, user, clock):
    """Enrich only already-authorized, paginated rows with allowlisted fields.

    Batch per request type, never perform a contact lookup for hidden sources.
    Source data also makes pre-upgrade history readable without a DB backfill.
    """
    from app.models.auth import AuthRegistrationRequest, AuthPasswordResetRequest
    from app.models.internal_quote import InternalQuote
    from app.services.internal_quote_calculator import FORMULA_VERSION
    # Only enrich already-authorized rows on this page; never expose orphan
    # notices or broaden scope while explaining a source verification warning.
    quote_ids = {row["entity_id"] for row in rows if row["module"] == "internal_quote" and row["kind"] != "diagnostic"}
    quotes = {quote.id: quote for quote in db.scalars(select(InternalQuote).where(InternalQuote.id.in_(quote_ids)))} if quote_ids else {}
    sources = {}
    for model, stages in ((AuthRegistrationRequest, {"registration"}),
                          (AuthPasswordResetRequest, {"password_reset", "password_reset_claim"})):
        ids = {row["entity_id"] for row in rows if row["module"] == "account_requests" and row["stage"] in stages}
        if ids:
            for request in db.scalars(select(model).where(model.id.in_(ids))):
                for stage in stages:
                    sources[(stage, request.id)] = request
    facts = page_facts(db, rows)
    result = []
    for row in rows:
        item = dto(row, user, clock)
        quote = quotes.get(row["entity_id"]) if row["module"] == "internal_quote" else None
        if quote is not None:
            item.update(quote_facts(quote))
        source = facts.get((row["module"], row["entity_id"]))
        if source:
            item.update(source)
        if row["module"] == "position_reviews" and row["stage"] == "position_result" and row["summary"]:
            item["summary"] = row["summary"]
            item["details"] = [*item.get("details", []), {"label": "核对意见", "value": row["summary"]}]
        if quote is not None and not row["verified"]:
            if quote.formula_version != FORMULA_VERSION:
                item["unavailable_reason"] = "报价使用旧版计算公式，请由原业务责任人在源单据中核对并按当前公式重算、重新提交。"
                item["details"] = [{"label": "单据公式版本", "value": quote.formula_version or "未记录"},
                                   {"label": "当前公式版本", "value": FORMULA_VERSION}]
            else:
                item["unavailable_reason"] = "本批报价的提交版本、部门计算或审核状态需要核对，请在源单据中检查整批产品。"
        request = sources.get((row["stage"], row["entity_id"])) if row["module"] == "account_requests" else None
        if request is not None:
            name, username = request.display_name.strip(), request.username.strip()
            item["reference_label"] = f"{name}（{username}）" if name and name != username else username
            fields = [("申请人", name or username), ("登录账号", username)]
            if isinstance(request, AuthRegistrationRequest):
                fields += [("申请岗位", request.position or "未填写"), ("联系电话", request.phone or "未填写"), ("联系邮箱", request.email or "未填写")]
                item["summary"] = f"申请岗位：{request.position}" if request.position else "未填写申请岗位"
            else:
                fields += [("联系方式", request.contact or "未填写"), ("申请说明", request.note or "未填写")]
                item["summary"] = request.note or "未填写申请说明"
            item["details"] = [{"label": label, "value": value} for label, value in fields]
            submitted = stamp(request.submitted_at)
            item["details"].append({"label": "申请时间", "value": submitted or "未记录", "format": "datetime" if submitted else "text"})
        result.append(item)
    return result


def detail(db, user, entry_id):
    rows, _ = authorized_rows(db, user)
    row = db.execute(select(rows).where(rows.c.id == entry_id, rows.c.kind.in_(("task", "info")))).mappings().first()
    if not row:
        raise HTTPException(404, "事项已失效或不在当前可见范围")
    return present_entries(db, [row], user, now())[0]


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
