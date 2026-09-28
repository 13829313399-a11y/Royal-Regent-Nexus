"""SQL projections of CURRENT domain responsibilities, independent of old read/handled.

All permission predicates are applied before union, counts and pagination. There is
no per-notification permission loop and no writes in these queries.
"""
from dataclasses import replace

from sqlalchemy import String, and_, case, cast, exists, false, func, literal, or_, select, true, union_all
from sqlalchemy.orm import aliased
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.functions import FunctionElement

from app.models.auth import AuthPasswordResetRequest, AuthRegistrationRequest, SystemNotification
from app.models.carton_procurement import CartonAuditEvent, CartonReceipt
from app.models.carton_supplier_portal import SupplierShipment
from app.models.internal_quote import InternalQuote, InternalQuoteAlternative, InternalQuoteAuditLog, InternalQuoteSection
from app.models.molding_sample import MoldingSampleAuditLog, MoldingSampleOrder, MoldingSampleProblem, MoldingSampleNotification
from app.services.auth import ALLOWED_DEPARTMENTS, ALLOWED_FACTORY_IDS, can
from app.services.business_authz import has_permission_for_departments, molding_read_access, has_general_molding_read_access
from app.services.internal_quote import ALL_QUOTE_DEPARTMENTS, SECTION_DEFINITIONS, _is_sales_quote_reviewer

COVERAGE = [
    {"module": key, "state": "active"} for key in
    ("molding", "internal_quote", "account_requests", "carton_supplier", "identity")
] + [{"module": key, "state": "not_integrated"} for key in ("three_d", "uv", "spray", "customer_orders", "document_tools")]


class PayloadValue(FunctionElement):
    type = String()
    inherit_cache = True


@compiles(PayloadValue, "sqlite")
def sqlite_payload(element, compiler, **kw):
    value, name = [compiler.process(x, **kw) for x in element.clauses]
    return f"CASE WHEN json_valid({value}) THEN json_extract({value}, '$.' || {name}) ELSE NULL END"


@compiles(PayloadValue, "postgresql")
def postgres_payload(element, compiler, **kw):
    value, name = [compiler.process(x, **kw) for x in element.clauses]
    return f"(CAST({value} AS jsonb) #>> string_to_array({name}, '.'))"


def expr(value):
    return value if hasattr(value, "label") else literal(value)


def key(*parts):
    result = literal("")
    for index, part in enumerate(parts):
        if index:
            result = result + ":"
        result = result + cast(expr(part), String)
    return result


def projection(*, module, entity_id, stage, cycle=1, factory="", execution="", department="",
               assignee="", watcher="", title, reference, summary="", opened="", due="",
               version=1, can_act=True, visible=True, kind="task", lifecycle="open", verified=True):
    values = dict(id=key(module, entity_id, stage, cycle), module=module, entity_id=entity_id,
                  stage=stage, cycle=cast(expr(cycle), String), factory=factory, execution=execution,
                  department=department, assignee=assignee, watcher=watcher, title=title,
                  reference=reference, summary=summary, opened=opened, due=due,
                  content_version=version, can_act=can_act, kind=kind, lifecycle=lifecycle, verified=verified)
    return select(*(expr(value).label(name) for name, value in values.items())).where(expr(visible))


def duty_user(user):
    """A wildcard administrator is authority, not a production assignment."""
    if user is None:
        return None
    return replace(user, grants=tuple(g for g in user.grants if g.role_code != "admin"))


def scoped(user, column, permission, departments, *, local_molding=False, duty=True):
    if user is None:
        return true()
    actor = duty_user(user) if duty else user
    factories = [f for f in sorted(ALLOWED_FACTORY_IDS)
                 if has_permission_for_departments(actor, permission, f, departments)
                 and (not local_molding or molding_read_access(actor, f) in {"local", "cross_operate"})]
    return column.in_(factories)


def molding_queries(user):
    o, a = MoldingSampleOrder, MoldingSampleAuditLog
    production = func.coalesce(o.production_factory_id, case((o.factory_id.in_(("huakang-a", "huakang-b", "huadeng", "huaxing")), o.factory_id), else_=""))
    cycle = select(func.count(a.id)).where(a.order_id == o.id, a.from_status != a.to_status).correlate(o).scalar_subquery()
    cycle = key(cycle, o.production_assignment_version)
    opener = select(a.actor_user_id).where(a.order_id == o.id).order_by(a.created_at, a.id).limit(1).correlate(o).scalar_subquery()
    visible = true() if user is None else or_(
        o.factory_id.in_([f for f in ALLOWED_FACTORY_IDS if molding_read_access(user, f) and has_general_molding_read_access(user, f)]),
        and_(o.status.in_(("待生产", "生产中", "已完成")), scoped(user, production, "molding_sample:production_read", ("production", "molding"), duty=False)))
    stages = [
        ("待审核", "supervisor_review", "审核啤办单", "supervisor_review", ("engineering",), False),
        ("待经理审核", "manager_review", "终审啤办单", "manager_review", ("management",), False),
        ("已驳回", "rework", "修改并重提啤办单", "edit_draft", ("engineering", "management"), False),
        ("已撤回", "rework", "修改并重提啤办单", "edit_draft", ("engineering", "management"), False),
        ("待生产", "production_start", "开始啤办生产", "production_start", ("production", "molding"), True),
        ("生产中", "production_fill", "填写啤办结果", "production_fillback", ("production", "molding"), True),
    ]
    for status, stage, title, permission, departments, is_production in stages:
        act = scoped(user, production if is_production else o.factory_id, f"molding_sample:{permission}", departments, local_molding=True)
        if stage == "production_fill":
            act = or_(act, scoped(user, production, "molding_sample:production_complete", departments, local_molding=True))
        yield projection(module="molding", entity_id=o.id, stage=stage, cycle=cycle,
                         factory=o.factory_id, execution=production, department="production" if is_production else departments[0],
                         watcher=func.coalesce(opener, ""), title=title, reference=case((o.order_number != "", o.order_number), else_=o.id),
                         summary=o.product_name, opened=o.created_at, can_act=act, visible=visible,
                         verified=production != "" if is_production else True,
                         lifecycle="in_progress" if is_production and stage == "production_fill" else "open").where(o.status == status)
    p = MoldingSampleProblem
    yield projection(module="molding", entity_id=o.id, stage=key("problem", p.id), cycle=p.responsibility_revision,
                     factory=o.factory_id, execution=production, department="production", title="处理生产问题",
                     reference=o.order_number, summary="生产问题仍开放，请在原单据核实处理。", opened=p.created_at,
                     visible=visible, can_act=scoped(user, o.factory_id, "molding_sample:edit_draft", ("engineering", "management"), local_molding=True)
                     ).select_from(p).join(o, p.order_id == o.id).where(p.status == "待处理")


def quote_queries(user):
    q, s, a = InternalQuote, InternalQuoteSection, InternalQuoteAuditLog
    active = and_(q.status != "archived", q.archived_at == "", ~exists(select(InternalQuoteAlternative.quote_id).where(InternalQuoteAlternative.quote_id == q.id, InternalQuoteAlternative.archived.is_(True))))
    visible = scoped(user, q.factory_id, "internal_quote:read", ALL_QUOTE_DEPARTMENTS, duty=False)
    reviewer = true() if user is None else and_(q.business_owner_id == user.id, or_(
        q.factory_id.in_([f for f in ALLOWED_FACTORY_IDS if _is_sales_quote_reviewer(user, f) and can(user, "internal_quote:sales_review", f, "sales-business")]),
        and_(q.created_by == user.id, q.factory_id.in_([f for f in ALLOWED_FACTORY_IDS if _is_sales_quote_reviewer(user, f) and can(user, "internal_quote:self_review", f, "sales-business")]))))
    base = dict(module="internal_quote", entity_id=q.id, factory=q.factory_id, watcher=q.created_by,
                reference=q.quote_no, summary=q.product_name, opened=q.created_at, due=q.target_date, visible=visible)
    sibling = aliased(InternalQuote)
    same_batch = and_(sibling.factory_id == q.factory_id, or_(and_(q.batch_id != "", sibling.batch_id == q.batch_id), and_(q.batch_id == "", sibling.id == q.id)))
    from app.services.internal_quote_calculator import FORMULA_VERSION
    invalid_sections = exists(select(s.id).where(s.quote_id == sibling.id, s.is_required.is_(True), or_(
        s.status != "pending_review", s.calculation_status != "valid", s.dependency_status != "current",
        s.calculation_formula_version != FORMULA_VERSION,
        cast(PayloadValue(sibling.final_submission_manifest_json, literal("section_revisions.") + s.department), String) != cast(s.revision, String),
        PayloadValue(sibling.final_submission_manifest_json, literal("section_revisions.") + s.department).is_(None))))
    batch_reviewable = ~exists(select(sibling.id).where(same_batch, or_(sibling.module_version != "v3",
        sibling.status != "final_reviewing", sibling.final_release_status != "pending", sibling.business_owner_id != q.business_owner_id,
        sibling.formula_version != FORMULA_VERSION, invalid_sections,
        cast(PayloadValue(sibling.final_submission_manifest_json, literal("header_revision")), String) != cast(sibling.header_revision, String),
        PayloadValue(sibling.final_submission_manifest_json, literal("header_revision")).is_(None))))
    incomplete = exists(select(s.id).where(s.quote_id == sibling.id, s.is_required.is_(True), or_(
        s.filled_at == "", s.payload_json.in_(("", "{}")), s.calculation_status != "valid", s.dependency_status != "current",
        s.status.not_in(("draft", "rejected")))))
    batch_ready = ~exists(select(sibling.id).where(same_batch, or_(sibling.module_version != "v3", sibling.archived_at != "",
        sibling.status != "ready_for_final_review", sibling.business_owner_id != q.business_owner_id, incomplete)))
    sales_submitter = select(s.submitted_by_id).where(s.quote_id == q.id, s.department == "sales").correlate(q).scalar_subquery()
    followup = func.coalesce(func.nullif(sales_submitter, ""), q.created_by)
    # Batch root represents the one atomic review, never one task per product.
    yield projection(**{**base, "summary": literal("本批共 ") + cast(q.batch_size, String) + " 款产品；请核对整批内容后审核。"}, stage="whole_review", cycle=q.final_submission_revision,
                     assignee=q.business_owner_id, title="审核这批报价", department="sales-business", can_act=and_(reviewer, batch_reviewable), verified=batch_reviewable
                     ).where(active, q.module_version == "v3", q.batch_position == 1,
                             q.status == "final_reviewing", q.final_release_status == "pending")
    for code, label, departments in SECTION_DEFINITIONS:
        edit = scoped(user, q.factory_id, f"internal_quote:{code}_edit", departments)
        # Sales/engineering may help edit other sections; that capability alone
        # does not assign every department's work to them.
        cycle = select(func.coalesce(func.max(a.new_revision), 0)).where(a.quote_id == q.id,
            a.department == code, a.action.in_(("reject", "reopen", "withdraw", "whole_review_withdraw_section", "whole_review_reject_section"))).correlate(q).scalar_subquery()
        yield projection(**base, stage=key("fill", code), cycle=cycle, department=code,
                         title=f"填写{label}报价", can_act=edit).join(s, s.quote_id == q.id).where(
                             active, s.department == code, s.is_required.is_(True), s.status.in_(("draft", "rejected")),
                             or_(q.module_version == "v2", s.status == "rejected", s.filled_at == "", s.payload_json.in_(("", "{}")), s.calculation_status != "valid", s.dependency_status != "current"),
                             q.final_release_status.not_in(("pending", "approved", "issued")))
        own_submission = false() if user is None else and_(s.submitted_by_id == user.id, ~and_(q.created_by == user.id,
            q.factory_id.in_([f for f in ALLOWED_FACTORY_IDS if can(user, "internal_quote:self_review", f, "sales-business")])))
        yield projection(**base, stage=key("review", code), cycle=s.revision, department=code,
                         assignee=q.business_owner_id, title=f"审核{label}报价", can_act=and_(reviewer, ~own_submission)
                         ).join(s, s.quote_id == q.id).where(active, q.module_version == "v2", s.department == code, s.is_required.is_(True),
                                                          s.status.in_(("pending_review", "na_pending")))
    final_submit = scoped(user, q.factory_id, "internal_quote:final_submit", ("sales-business",))
    responsible = true() if user is None else followup == user.id
    yield projection(**base, stage="final_submit", cycle=q.final_submission_revision, department="sales-business",
                     assignee=case((q.module_version == "v2", followup), else_=""),
                     title="提交报价审核", can_act=and_(final_submit, or_(and_(q.module_version == "v3", batch_ready), and_(q.module_version == "v2", responsible)))
                     ).where(active, q.module_version.in_(("v2", "v3")), or_(q.module_version == "v2", q.batch_position == 1), q.status == "ready_for_final_review")
    yield projection(**base, stage="final_review", cycle=q.final_submission_revision, department="sales-business",
                     title="核实历史报价发布", can_act=or_(and_(final_submit, responsible), scoped(user, q.factory_id, "internal_quote:final_approve", ("sales-business",)))
                     ).where(active, q.module_version == "v2", q.status == "final_reviewing", q.final_release_status == "pending")


def shipment_queries(user):
    s, r, a = SupplierShipment, CartonReceipt, CartonAuditEvent
    act = and_(*(scoped(user, s.factory_id, permission, ("pmc-warehouse", "carton")) for permission in (
        "carton_procurement:read", "carton_procurement:receipt_write", "carton_procurement:inventory_write")))
    reversed_receipt = exists(select(r.id).where(r.id == s.receipt_id, r.status == "REVERSED"))
    reversal = select(func.coalesce(func.max(a.sequence), 0)).where(a.factory_id == s.factory_id,
        or_(a.entity_id == s.id, a.entity_id == s.receipt_id),
        a.event_type.in_(("SUPPLIER_SHIPMENT_RECEIPT_REVERSED", "RECEIPT_REVERSED"))).correlate(s).scalar_subquery()
    yield projection(module="carton_supplier", entity_id=s.id, stage=case((reversed_receipt, "receipt_correction"), else_="receipt"),
                     cycle=key(s.revision, reversal), factory=s.factory_id, execution=s.factory_id, department="pmc-warehouse",
                     title=case((reversed_receipt, "更正送货验收"), else_="核实这张送货单"), reference=s.delivery_note_no,
                     summary="核对实到、破损与拒收数量后，使用原收料流程确认。", opened=s.created_at,
                     can_act=act, visible=act).where(or_(s.status == "SENT", and_(s.status == "RECEIVED", reversed_receipt)))


def account_queries(db, user):
    from app.services.system import is_superadmin
    r = AuthRegistrationRequest
    scope = true() if user is None or is_superadmin(user) else or_(false(), *[
        and_(r.factory_id == f, r.department == d) for f in ALLOWED_FACTORY_IDS for d in ALLOWED_DEPARTMENTS
        if can(user, "system:user_manage", f, d)])
    yield projection(module="account_requests", entity_id=r.id, stage="registration", factory=r.factory_id,
                     department=r.department, title="审核注册申请", reference=r.id, summary="请核对申请组织与任职资料。",
                     opened=r.submitted_at, visible=scope, can_act=True).where(r.status == "pending")
    p = AuthPasswordResetRequest
    # IAM target scope includes scheduled/additional assignments. Reuse the
    # authoritative domain check; do not approximate it with a profile join.
    reset_scope = reset_visibility(db, user)
    yield projection(module="account_requests", entity_id=p.id, stage="password_reset", factory=p.factory_id,
                     department=p.department, title="核验密码重置申请", reference=p.id,
                     summary="核实本人身份后，在原申请中审批。", opened=p.submitted_at,
                     visible=reset_scope, can_act=True
                     ).where(p.status == "pending", p.claim_token_hash.is_not(None))
    from app.services.auth import now_text
    yield projection(module="account_requests", entity_id=p.id, stage="password_reset_claim", cycle=p.issue_count,
                     factory=p.factory_id, department=p.department, watcher=func.coalesce(p.reviewer_user_id, ""),
                     title="等待申请人完成密码重置", reference=p.id, summary="管理员已批准，等待申请人领取并完成。",
                     opened=p.approved_at, due=p.expires_at, visible=reset_scope, can_act=False
                     ).where(p.status == "approved", p.expires_at > now_text())


def reset_visibility(db, user, *, history=False):
    from app.services.system import is_superadmin, target_users_scopes
    if user is None or is_superadmin(user): return true()
    p = AuthPasswordResetRequest
    targets = select(p.user_id)
    if not history: targets = targets.where(p.status.in_(("pending", "approved")))
    scopes = target_users_scopes(db, targets)
    allowed = [uid for uid, required in scopes.items() if required and all(can(user, "system:user_manage", f, d) for f, d in required)]
    return p.user_id.in_(allowed)


def identity_queries(user):
    n = SystemNotification
    yield projection(module="identity", entity_id=n.id, stage="identity_changed", factory="",
                     assignee=n.target_user_id, title="任职信息已更新", reference="本人任职",
                     summary="任职信息发生变化，请刷新账户上下文，提交业务前重新核对当前权限和厂区。",
                     opened=n.created_at, kind="info", lifecycle=None, can_act=False,
                     visible=true() if user is None else n.target_user_id == user.id).where(n.type == "identity_changed")


def result_queries(user):
    n, q = SystemNotification, InternalQuote
    event = PayloadValue(n.payload_json, literal("event"))
    quote_id = PayloadValue(n.payload_json, literal("quote_id"))
    read = scoped(user, q.factory_id, "internal_quote:read", ALL_QUOTE_DEPARTMENTS, duty=False)
    recipient = true() if user is None else or_(n.target_user_id == user.id, and_(n.target_user_id == "",
        scoped(user, q.factory_id, "internal_quote:read", ALL_QUOTE_DEPARTMENTS, duty=False)))
    yield projection(module="internal_quote", entity_id=q.id, stage=key("info", n.id), title=n.title,
        reference=q.quote_no, summary="报价流程或成果已更新，请在原单据查看授权范围内的资料。", factory=q.factory_id,
        assignee=n.target_user_id, opened=n.created_at, kind="info", lifecycle=None, can_act=False,
        visible=and_(read, recipient)).select_from(n).join(q, q.id == quote_id).where(n.type == "internal_quote",
            event.in_(("customer_price_artifact_available", "final_release_approved", "whole_quote_approved")))
    m, o = MoldingSampleNotification, MoldingSampleOrder
    read_m = or_(scoped(user, o.factory_id, "molding_sample:read", ("engineering", "management"), duty=False),
                 scoped(user, o.production_factory_id, "molding_sample:production_read", ("production", "molding"), duty=False))
    target = true() if user is None else or_(
        and_(m.target_module == "engineering_molding_sample", scoped(user, m.factory_id, "molding_sample:read", ("engineering",), duty=False)),
        and_(m.target_module == "production_molding_sample_task", scoped(user, m.factory_id, "molding_sample:production_read", ("production", "molding"), duty=False)))
    yield projection(module="molding", entity_id=o.id, stage=key("info", m.id), title=case((and_(m.event_type == "生产完成回传", o.status != "已完成"), "历史完成回传已撤回"), else_=m.title),
        reference=o.order_number, summary="源业务阶段已变化，请查看原单据的当前进展。", factory=o.factory_id,
        execution=func.coalesce(o.production_factory_id, ""), opened=m.created_at, kind="info", lifecycle=None,
        can_act=False, visible=and_(read_m, target)).select_from(m).join(o, o.id == m.order_id).where(
            m.event_type.in_(("生产开始", "生产完成回传", "生产完成撤回", "生产开始撤回", "生产派厂变更")))


def current_query(db, user):
    disabled = db.info.get("work_center_unavailable", set()) if user is not None else set()
    queries = [q for name, build in providers(db, user) if name not in disabled for q in build()]
    if not queries:
        queries = [projection(module="", entity_id="", stage="", title="", reference="", visible=False)]
    return union_all(*queries).subquery("current_work")


def providers(db, user):
    return (("molding", lambda: molding_queries(user)), ("internal_quote", lambda: quote_queries(user)),
        ("carton_supplier", lambda: shipment_queries(user)), ("account_requests", lambda: account_queries(db, user)),
        ("identity", lambda: identity_queries(user)), ("business_results", lambda: result_queries(user)),
        ("legacy_history", lambda: legacy_history_queries(user)), ("integrity", lambda: diagnostic_queries(user)))


def probe_sources(db, user):
    """Failure-only isolation. Savepoints keep PostgreSQL's read snapshot usable."""
    from sqlalchemy.exc import SQLAlchemyError
    unavailable = set()
    for name, build in providers(db, user):
        try:
            with db.begin_nested():
                for query in build(): db.execute(query.limit(1)).first()
        except SQLAlchemyError:
            unavailable.add(name)
    db.info["work_center_unavailable"] = unavailable
    return unavailable


def diagnostic_queries(user):
    """Anonymous integrity markers contribute to health, never to work or lists."""
    n, o = MoldingSampleNotification, MoldingSampleOrder
    yield projection(module="molding", entity_id=n.order_id, stage=key("unverified", n.id), title="来源待核验", reference="",
        factory=n.factory_id, kind="diagnostic", lifecycle=None, can_act=False, verified=False,
        visible=scoped(user, n.factory_id, "molding_sample:notification_read", ("engineering", "management", "molding", "production"), duty=False)
        ).where(~exists(select(o.id).where(o.id == n.order_id)))
    n, q = SystemNotification, InternalQuote
    source = PayloadValue(n.payload_json, literal("quote_id"))
    yield projection(module="internal_quote", entity_id=n.id, stage="unverified", title="来源待核验", reference="",
        factory=n.target_factory_id, kind="diagnostic", lifecycle=None, can_act=False, verified=False,
        visible=scoped(user, n.target_factory_id, "internal_quote:read", ALL_QUOTE_DEPARTMENTS, duty=False)
        ).where(n.type == "internal_quote", ~exists(select(q.id).where(q.id == source)))


def legacy_history_queries(user):
    """One safe historical conclusion per source, never turn old unread into work."""
    o, n = MoldingSampleOrder, MoldingSampleNotification
    readable = or_(scoped(user, o.factory_id, "molding_sample:read", ("engineering", "management"), duty=False),
        scoped(user, o.production_factory_id, "molding_sample:production_read", ("production", "molding"), duty=False))
    yield projection(module="molding", entity_id=o.id, stage="legacy_history", title="历史啤办提醒已结束",
        reference=o.order_number, summary="源单据已完成。原提醒及业务操作可在源单据审计中追溯。", opened=o.created_at,
        factory=o.factory_id, execution=func.coalesce(o.production_factory_id, ""), can_act=False,
        visible=readable, lifecycle="resolved").where(o.status == "已完成", exists(select(n.id).where(n.order_id == o.id)))
    q, message = InternalQuote, SystemNotification
    yield projection(module="internal_quote", entity_id=q.id, stage="legacy_history", title="历史报价提醒已结束",
        reference=q.quote_no, summary="源报价已结束该办理阶段。历史提醒不能代替新的责任轮次。", opened=q.created_at,
        factory=q.factory_id, can_act=False, lifecycle=case((q.status == "archived", "cancelled"), else_="resolved"),
        visible=scoped(user, q.factory_id, "internal_quote:read", ALL_QUOTE_DEPARTMENTS, duty=False)).where(
            or_(q.status == "archived", q.final_release_status.in_(("approved", "issued"))),
            exists(select(message.id).where(message.type == "internal_quote", PayloadValue(message.payload_json, literal("quote_id")) == q.id)))
