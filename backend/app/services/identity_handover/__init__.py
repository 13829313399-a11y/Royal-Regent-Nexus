"""Explicit adapters only. Unsupported responsibilities never count as completed."""
from uuid import uuid4
from sqlalchemy import select
from app.models.identity import IamHandoverItem
from app.services.identity_policy import ensure_reader, fail, fresh_actor, lock_mutation, require_writes
from app.services.identity_resolver import stamp

# A module is marked covered only after its actual mutable responsibility is
# adapted. Queue-based registration/password recovery keeps its original flow.
COVERAGE = [
    {"module": "内部报价", "key": "internal_quote", "status": "supported", "basis": "business_owner_id / header_revision；仅可编辑报价"},
    {"module": "注册与密码找回", "key": "account_requests", "status": "role_queue", "basis": "按当前管理范围查询，仍通过原审核接口办理"},
    *[{"module": name, "key": key, "status": "uncovered", "basis": "未覆盖，需人工检查；不提供整厂交接授权"}
      for key, name in [("molding", "啤办与生产任务"), ("warehouse", "仓库与订单"), ("carton", "纸箱与供应商"),
                        ("three_d", "3D打印"), ("uv", "UV打印"), ("spray", "喷油")]],
]
EDITABLE_QUOTE_STATES = {"drafting", "ready_for_final_review"}


def assess(db, user_id):
    from app.models.internal_quote import InternalQuote
    items = [{"adapter_key": "internal_quote", "resource_id": q.id, "resource_type": "internal_quote",
              "responsibility_kind": "business_owner", "factory_id": q.factory_id, "state": q.status,
              "previous_user_id": user_id, "expected_resource_revision": q.header_revision,
              "can_reassign": q.status in EDITABLE_QUOTE_STATES, "blocking": False}
             for q in db.scalars(select(InternalQuote).where(InternalQuote.business_owner_id == user_id,
                                                            InternalQuote.status.not_in(["archived", "exported", "fully_approved"]))) ]
    return {"items": items, "count": len(items), "coverage": COVERAGE,
            "status": "pending" if items else "manual_review_required", "assessed_at": stamp()}


def persist_items(db, request):
    summary = assess(db, request.target_user_id)
    for item in summary["items"]:
        existing = db.scalar(select(IamHandoverItem).where(IamHandoverItem.change_request_id == request.id,
            IamHandoverItem.adapter_key == item["adapter_key"], IamHandoverItem.resource_id == item["resource_id"],
            IamHandoverItem.responsibility_kind == item["responsibility_kind"]))
        if existing:
            continue
        db.add(IamHandoverItem(id=uuid4().hex, change_request_id=request.id, adapter_key=item["adapter_key"],
            resource_id=item["resource_id"], responsibility_kind=item["responsibility_kind"], factory_id=item["factory_id"],
            previous_user_id=request.target_user_id, expected_resource_revision=item["expected_resource_revision"],
            status="pending" if item["can_reassign"] else "manual_review_required", created_at=stamp()))
    return summary


def item_out(item):
    return {key: getattr(item, key) for key in ("id", "change_request_id", "adapter_key", "resource_id", "factory_id",
            "previous_user_id", "successor_user_id", "expected_resource_revision", "status", "attempts", "last_error", "completed_at")}


def reassign(db, actor_id, item_id, payload):
    from app.models.internal_quote import InternalQuote
    from app.services.internal_quote import validate_quote_business_owner, _add_audit
    from app.services.auth import can
    require_writes()
    lock_mutation(db)
    actor = fresh_actor(db, actor_id)
    item = db.get(IamHandoverItem, item_id, populate_existing=True)
    if not item:
        fail("HANDOVER_NOT_FOUND", "交接项不存在", 404)
    ensure_reader(db, actor, item.previous_user_id)
    if not can(actor, "system:access_manage", "*", "*") or not can(actor, "internal_quote:header_edit", item.factory_id, "sales-business"):
        fail("OUTSIDE_MANAGEABLE_SCOPE", "没有此范围的交接与业务操作权", 403)
    if item.status == "completed":
        if item.successor_user_id == payload.successor_user_id:
            return item_out(item)
        fail("HANDOVER_ITEM_CHANGED", "此交接已完成")
    if item.adapter_key != "internal_quote":
        fail("UNSUPPORTED_HANDOVER", "此业务未支持自动交接", 422)
    from app.services.transaction_lock import lock_transaction
    batch_id = db.scalar(select(InternalQuote.batch_id).where(InternalQuote.id == item.resource_id))
    lock_transaction(db, "internal-quote", f"{item.factory_id}:{batch_id or item.resource_id}")
    quote = db.get(InternalQuote, item.resource_id, with_for_update=True, populate_existing=True)
    if not quote or quote.status not in EDITABLE_QUOTE_STATES or quote.business_owner_id != (item.successor_user_id or item.previous_user_id):
        fail("HANDOVER_ITEM_CHANGED", "报价状态或责任人已变化，请重新评估")
    if quote.header_revision != payload.expected_resource_revision or quote.header_revision != item.expected_resource_revision:
        fail("HANDOVER_ITEM_CHANGED", "业务单据已变化，请重新评估")
    name = validate_quote_business_owner(db, payload.successor_user_id, quote.factory_id, quote.created_by)
    before = quote.header_revision
    quote.business_owner_id = payload.successor_user_id
    quote.business_owner_name = name
    quote.header_revision += 1
    _add_audit(db, quote, actor, "identity_handover", old_revision=before, new_revision=quote.header_revision,
               reason=f"任职交接 {item.change_request_id}")
    item.successor_user_id = payload.successor_user_id
    item.status = "completed"
    item.attempts += 1
    item.completed_at = stamp()
    db.commit()
    return item_out(item)


def candidates(db, actor, item):
    from app.models.auth import AuthUser
    from app.models.internal_quote import InternalQuote
    from app.services.auth import build_auth_context, can
    from app.services.internal_quote import _can_review_quote
    ensure_reader(db, actor, item.previous_user_id)
    if not can(actor, "internal_quote:header_edit", item.factory_id, "sales-business"):
        fail("OUTSIDE_MANAGEABLE_SCOPE", "没有此范围的业务操作权", 403)
    quote = db.get(InternalQuote, item.resource_id)
    if not quote:
        return []
    return [{"id": u.id, "display_name": u.display_name} for u in db.scalars(select(AuthUser).where(AuthUser.status == "active"))
            if u.id != quote.business_owner_id and _can_review_quote(build_auth_context(db, u), quote.factory_id, quote.created_by)]


def reconcile(db, request):
    """Discover late work and reopen an unfinished responsibility with an invalid holder."""
    from app.models.auth import AuthUser
    from app.models.internal_quote import InternalQuote
    from app.services.auth import build_auth_context
    from app.services.internal_quote import _can_review_quote
    persist_items(db, request)
    for item in db.scalars(select(IamHandoverItem).where(IamHandoverItem.change_request_id == request.id)):
        quote = db.get(InternalQuote, item.resource_id)
        if not quote or quote.status in {"archived", "exported", "fully_approved"}:
            item.status = "no_longer_required"
            continue
        holder = db.get(AuthUser, quote.business_owner_id)
        valid = bool(holder and holder.status == "active" and _can_review_quote(build_auth_context(db, holder), quote.factory_id, quote.created_by))
        if item.status == "completed" and valid:
            continue
        if quote.business_owner_id not in {item.previous_user_id, item.successor_user_id}:
            item.status = "changed_externally"
            continue
        item.expected_resource_revision = quote.header_revision
        item.status = "pending" if quote.status in EDITABLE_QUOTE_STATES else "manual_review_required"
        item.last_error = "SUCCESSOR_UNAVAILABLE" if item.successor_user_id and not valid else ""
    db.flush()
