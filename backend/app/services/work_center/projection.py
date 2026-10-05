"""Transaction-owned, replayable projection. Never commits or executes a domain action."""
import hashlib
import json

from sqlalchemy import event, select
from app.models.work_center import WorkCenterEntry as Entry, WorkCenterEvent
from app.services.work_center.registry import current_query
from app.services.work_center.service import now, stamp
from app.core.time import parse_business_timestamp


def materialize(db, rows, *, legacy=False):
    counts = {"created": 0, "updated": 0, "unchanged": 0}
    for row in rows:
        if row["kind"] == "diagnostic":
            continue
        evidence = {key: value for key, value in dict(row).items() if key != "can_act"}
        record = db.get(Entry, row["id"])
        digest = hashlib.sha256(json.dumps(evidence, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if record and record.evidence == evidence and record.lifecycle == row["lifecycle"]:
            counts["unchanged"] += 1
            continue
        if record is None:
            record = Entry(id=row["id"], canonical_key=row["id"], module=row["module"], entity_id=row["entity_id"],
                           factory_id=row["factory"], kind=row["kind"], lifecycle=row["lifecycle"],
                           content_version=1, attention_version=0 if legacy else 1,
                           opened_at=parse_business_timestamp(row["opened"]) or now(), updated_at=now(), evidence=evidence)
            db.add(record)
            counts["created"] += 1
        else:
            if record.lifecycle != row["lifecycle"] or any(record.evidence.get(field) != evidence.get(field) for field in ("assignee", "execution", "stage", "due", "verified")):
                record.attention_version += 1
            record.evidence = evidence
            record.content_version += 1
            record.lifecycle = row["lifecycle"]
            record.resolved_at = None
            record.resolution_reason = ""
            record.updated_at = now()
            counts["updated"] += 1
        db.flush()
        source_key = f"{digest}:{record.content_version}"
        event_id = hashlib.sha256(f"{record.id}:{source_key}".encode()).hexdigest()
        if db.get(WorkCenterEvent, event_id) is None:
            db.add(WorkCenterEvent(id=event_id, entry_id=record.id, source_event_key=source_key,
                                  occurred_at=now(), event_kind="baseline" if legacy else "source_changed",
                                  safe_summary="历史责任基线已核验" if legacy else record.evidence["title"]))
    return counts


def reconcile_sources(db, sources, *, legacy=False):
    from sqlalchemy import and_, or_
    current = current_query(db, None)
    conditions = [and_(current.c.module == module, current.c.entity_id.in_(ids)) for module, ids in sources.items() if ids]
    if not conditions:
        return {"created": 0, "updated": 0, "unchanged": 0}
    rows = db.execute(select(current).where(or_(*conditions))).mappings().all()
    result = materialize(db, rows, legacy=legacy)
    live = {row["id"] for row in rows}
    old_conditions = [and_(Entry.module == module, Entry.entity_id.in_(ids)) for module, ids in sources.items() if ids]
    for entry in db.scalars(select(Entry).where(or_(*old_conditions), Entry.kind == "task", or_(
            Entry.lifecycle.in_(("open", "in_progress")),
            and_(Entry.evidence["stage"].as_string() == "legacy_history", Entry.lifecycle.in_(("resolved", "cancelled")))))):
        if entry.id in live:
            continue
        # Closure is evidence of a stage change, not a claim that the entire
        # order completed. Detailed conclusions remain in the source audit.
        entry.lifecycle, entry.resolution_reason = closure(db, entry)
        entry.content_version += 1
        entry.resolved_at = now()
        entry.updated_at = now()
        source_key = f"closed:{entry.content_version}"
        digest = hashlib.sha256(f"{entry.id}:{source_key}".encode()).hexdigest()
        if db.get(WorkCenterEvent, digest) is None:
            db.add(WorkCenterEvent(id=digest, entry_id=entry.id, source_event_key=source_key,
                                  occurred_at=now(), event_kind=entry.lifecycle, safe_summary=entry.resolution_reason))
    db.flush()
    return result


def closure(db, entry):
    """Explain only conclusions supported by current domain state."""
    from app.models.auth import AuthRegistrationRequest, AuthPasswordResetRequest
    from app.models.molding_sample import MoldingSampleOrder, MoldingSampleProblem
    from app.models.internal_quote import InternalQuote
    from app.models.carton_supplier_portal import SupplierShipment
    stage = entry.evidence.get("stage", "")
    if entry.module == "account_requests":
        model = AuthRegistrationRequest if stage == "registration" else AuthPasswordResetRequest
        source = db.get(model, entry.entity_id)
        if source and source.status in ("approved", "completed"):
            return "resolved", "申请已审批" if source.status == "approved" else "密码重置已完成"
        if source and source.status in ("rejected", "expired"):
            return "cancelled", "申请已驳回" if source.status == "rejected" else "申请已过期"
    elif entry.module == "carton_supplier":
        source = db.get(SupplierShipment, entry.entity_id)
        if source and source.status == "RECEIVED": return "resolved", "已通过原业务正式收料"
        if source and source.status == "VOID": return "cancelled", "送货单已作废"
    elif entry.module == "molding":
        source = db.get(MoldingSampleOrder, entry.entity_id)
        if stage.startswith("problem:"):
            problem = db.get(MoldingSampleProblem, stage.split(":", 1)[1])
            if problem and problem.status == "已解决": return "resolved", "生产问题已解决"
        if source:
            if source.status == "已完成": return "resolved", "已正式完成啤办生产"
            if source.status == "已作废": return "cancelled", "源单据已作废"
            if source.status == "已驳回": return "resolved", "已驳回并转回填写"
            forward = {"supervisor_review": {"待经理审核", "待生产", "生产中"}, "manager_review": {"待生产", "生产中"}, "production_start": {"生产中"}}
            if source.status in forward.get(stage, set()): return "resolved", "本阶段已办理，已转交下一阶段"
    elif entry.module == "internal_quote":
        source = db.get(InternalQuote, entry.entity_id)
        if source and (source.status == "archived" or source.archived_at): return "cancelled", "源报价已归档"
        if source and source.final_release_status in ("approved", "issued"): return "resolved", "报价已审核发布"
    return "superseded", "源单据阶段或责任范围已变化，此轮责任已结束"


def install_projection_hooks(session_factory):
    """Collect only changed source IDs, then flush projection before owner commit.

    Register on this session factory (not global Session); test reloads and
    independent DB users must not accumulate callbacks.
    """
    from app.models.molding_sample import MoldingSampleOrder, MoldingSampleProblem, MoldingSampleNotification
    from app.models.internal_quote import InternalQuote, InternalQuoteSection, InternalQuoteAlternative
    from app.models.auth import AuthRegistrationRequest, AuthPasswordResetRequest, SystemNotification
    from app.models.carton_supplier_portal import SupplierShipment

    @event.listens_for(session_factory, "before_flush")
    def collect(db, *_):
        if db.info.get("work_center_projecting"):
            return
        sources = db.info.setdefault("work_center_sources", {})
        for obj in (*db.new, *db.dirty, *db.deleted):
            module, source_id = None, None
            if isinstance(obj, MoldingSampleOrder): module, source_id = "molding", obj.id
            elif isinstance(obj, MoldingSampleProblem): module, source_id = "molding", obj.order_id
            elif isinstance(obj, MoldingSampleNotification): module, source_id = "molding", obj.order_id
            elif isinstance(obj, InternalQuote): module, source_id = "internal_quote", obj.id
            elif isinstance(obj, InternalQuoteSection): module, source_id = "internal_quote", obj.quote_id
            elif isinstance(obj, InternalQuoteAlternative): module, source_id = "internal_quote", obj.quote_id
            elif isinstance(obj, (AuthRegistrationRequest, AuthPasswordResetRequest)): module, source_id = "account_requests", obj.id
            elif isinstance(obj, SupplierShipment): module, source_id = "carton_supplier", obj.id
            elif isinstance(obj, SystemNotification) and obj.type == "identity_changed": module, source_id = "identity", obj.id
            elif isinstance(obj, SystemNotification) and obj.type == "internal_quote":
                try: module, source_id = "internal_quote", json.loads(obj.payload_json or "{}").get("quote_id")
                except (ValueError, TypeError): pass
            if module and source_id:
                sources.setdefault(module, set()).add(source_id)

    @event.listens_for(session_factory, "before_commit")
    def project(db):
        if db.info.get("work_center_projecting") or db.in_nested_transaction():
            return
        db.flush()
        sources = db.info.pop("work_center_sources", {})
        if not sources:
            return
        db.info["work_center_projecting"] = True
        try:
            reconcile_sources(db, sources)
        finally:
            db.info.pop("work_center_projecting", None)

    @event.listens_for(session_factory, "after_rollback")
    def clear(db):
        if not db.in_nested_transaction():
            db.info.pop("work_center_sources", None)
