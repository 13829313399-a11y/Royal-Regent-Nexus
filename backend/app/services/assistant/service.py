"""Short transactions only. Shared DB admission/lease/cancellation across workers."""
from contextlib import contextmanager
import hashlib
import json
import time
from uuid import uuid4
from datetime import datetime, timezone
from sqlalchemy import select, func, text, delete, or_, and_
from app import db as database
from app.core.config import settings
from app.models.assistant import AssistantSession as Conversation, AssistantRun as Run, AssistantMessage as Message, AssistantAttachment as Attachment
from .errors import AssistantError
from . import capabilities, help_registry

ACTIVE = ("connecting", "thinking", "answering", "tool_running")
LEASE_SECONDS = 30
UNSET = object()


def epoch(user):
    return int((user.identity or {}).get("employment_epoch", 1))


@contextmanager
def transaction():
    with database.SessionLocal() as db:
        # The same transaction-scoped lock protects admission and terminal writes.
        # SQLite BEGIN IMMEDIATE works across processes, not just threads.
        if db.bind.dialect.name == "sqlite":
            db.execute(text("BEGIN IMMEDIATE"))
        elif db.bind.dialect.name == "postgresql":
            db.execute(text("SELECT pg_advisory_xact_lock(761903131)"))
        else:
            raise AssistantError("database_unsupported", "助手数据库类型尚未验证。", 503)
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise


def owned(db, user, session_id, *, pending=False):
    row = db.scalar(select(Conversation).where(Conversation.id == session_id, Conversation.owner_user_id == user.id,
                    Conversation.employment_epoch == epoch(user)))
    expired = row is not None and settings.assistant_retention_days and row.updated_at < time.time()-settings.assistant_retention_days*86400
    if row is None or ((row.deletion_state != "active" or expired) and not pending):
        raise AssistantError("not_found", "对话不存在或当前身份不可查看。", 404)
    return row


def session_out(row):
    return {k: getattr(row, k) for k in ("id", "title", "revision", "deletion_state", "created_at", "updated_at")}


def message_out(row, user=None):
    result = {k: getattr(row, k) for k in ("id", "run_id", "seq", "role", "content_parts", "status", "help_citations", "context_descriptor", "created_at")}
    if user and row.help_citations:
        if not help_registry.references_current(user, row.help_citations):
            result.update(content_parts=[{"type": "text", "text": "这段系统说明不再适用于当前身份或资料版本，请重新读取已核对的说明。"}], help_citations=[], context_descriptor=None, unavailable=True)
            return result
        if any(not c.get('source_fingerprint') for c in row.help_citations):
            result['help_verification'] = 'legacy_version_only'
    if user:
        from . import visibility
        from .files import snapshot as file_snapshot
        refs = visibility.sources(row.content_parts)
        if any(s.get('kind')=='help' and not s.get('source_fingerprint') for s in refs):
            result['help_verification'] = 'legacy_version_only'
        with database.SessionLocal() as db:
            if row.role == "user":
                paired = db.scalar(select(Message).where(Message.run_id == row.run_id, Message.role == "assistant"))
                refs += visibility.sources(paired.content_parts) if paired else []
            available = visibility.allowed(user, refs, db)
            try:
                for part in row.content_parts:
                    if part.get("type") == "document_ref":
                        file_snapshot(db, user, part["file_id"], row.session_id, part.get('document_version'))
                    elif part.get("type") == "image_ref":
                        from .storage import validate_attachments
                        validate_attachments(db, user, row.session_id, [part["attachment_id"]])
            except AssistantError:
                available = False
        if not available:
            result.update(content_parts=[{"type": "text", "text": "这段内容所依赖的资料已删除或授权已改变，当前不可查看。"}],
                          help_citations=[], context_descriptor=None, unavailable=True)
            return result
    return result


def settle_expired(db):
    now = time.time()
    rows = db.scalars(select(Run).where(Run.state.in_(ACTIVE), Run.lease_expires_at < now)).all()
    for row in rows:
        row.state = "cancelled" if row.cancel_requested else "interrupted"
        row.error_code = "lease_expired"
        row.finished_at = now
        account_usage(db, row)
        for m in db.scalars(select(Message).where(Message.run_id == row.id, Message.role == "assistant")):
            m.status = row.state
    db.flush()


def day_key(at):
    return datetime.fromtimestamp(at, timezone.utc).strftime("%Y-%m-%d")


def account_usage(db, run):
    session = db.get(Conversation, run.session_id)
    day = day_key(run.started_at)
    if session.budget_day != day:
        session.budget_day, session.budget_tokens, session.budget_unknown = day, 0, False
    amount = (run.usage or {}).get("total_tokens")
    if amount is None:
        amount = (run.context_window or {}).get("reserved_tokens")
    if amount is None:
        session.budget_unknown = True
    else:
        session.budget_tokens += max(0, amount)


def reserve_budget(db, payload=None):
    budget = settings.assistant_daily_token_budget
    if budget is None:
        return None
    if not settings.assistant_max_output_tokens or not capabilities.profile():
        raise AssistantError("budget_parameter_unverified", "日预算需要已核对的输出预算参数。", 503)
    # Deployment-wide UTC-day admission guard. Reserve worst-case UTF-8 text
    # plus output for every allowed tool round; unknown billing keeps reservation.
    extra_search = int(payload is not None and payload.protocol_version == 2 and payload.web_search != "off")
    reserve = (settings.assistant_context_character_budget*4 + settings.assistant_max_output_tokens)*(settings.assistant_max_tool_rounds+1+extra_search)
    rows = db.scalars(select(Conversation).where(Conversation.budget_day == day_key(time.time()))).all()
    active = db.scalars(select(Run).where(Run.state.in_(ACTIVE))).all()
    unknown = any(r.budget_unknown for r in rows) or any(not r.context_window.get("reserved_tokens") for r in active)
    used = sum(r.budget_tokens for r in rows) + sum(r.context_window.get("reserved_tokens") or 0 for r in active)
    if unknown or used+reserve > budget:
        raise AssistantError("daily_budget_exhausted", "今日模型预算已用尽或存在未知用量，请管理员核对。", 429, False)
    return reserve


def create(user, key):
    with transaction() as db:
        row = db.scalar(select(Conversation).where(Conversation.owner_user_id == user.id,
            Conversation.employment_epoch == epoch(user), Conversation.create_request_id == key))
        if row:
            if row.deletion_state != "active":
                raise AssistantError("deleted", "这个创建请求对应的对话已移除，请新建对话。", 409)
            return session_out(row)
        now = time.time()
        row = Conversation(id=uuid4().hex, owner_user_id=user.id, employment_epoch=epoch(user), create_request_id=key,
                           title="新对话", revision=1, deletion_state="active", created_at=now, updated_at=now)
        db.add(row)
        db.flush()
        return session_out(row)


def sessions(user, cursor="", limit=30, q="", favorites=False):
    expire_retention(user)
    cleanup_pending(user)
    with transaction() as db:
        settle_expired(db)
    # Visibility checks can load help fingerprints and business resources. They
    # must not hold SQLite's deployment-wide writer lock while traversing history.
    with database.SessionLocal() as db:
        query = select(Conversation).where(Conversation.owner_user_id == user.id, Conversation.employment_epoch == epoch(user), Conversation.deletion_state != "deleted")
        from sqlalchemy import inspect
        from app.models.assistant import AssistantFavorite
        has_favorites = inspect(db.bind).has_table(AssistantFavorite.__tablename__)
        if favorites:
            if not has_favorites:
                return dict(items=[], next_cursor=None)
            query = query.where(Conversation.id.in_(select(AssistantFavorite.session_id).where(AssistantFavorite.owner_user_id == user.id,
                AssistantFavorite.employment_epoch == epoch(user))))
        from .pagination import matching_page
        def render(row):
            values = [message_out(m, user) for m in db.scalars(select(Message).where(Message.session_id == row.id).order_by(Message.seq))]
            hidden = any(v.get("unavailable") for v in values)
            item = {**session_out(row), "title": "来源不可用的会话" if hidden else row.title,
                    "favorite": bool(has_favorites and db.get(AssistantFavorite, row.id))}
            text = "\n".join(p.get("text", "") for m in values if not m.get("unavailable") for p in m["content_parts"] if p["type"] == "text")
            if q and q.casefold() not in (item["title"] + text).casefold():
                return None
            if q:
                at = text.casefold().find(q.casefold())
                item["snippet"] = text[max(0, at-30):at+120] if at >= 0 else ""
            return item
        return matching_page(db, Conversation, query, cursor, limit, render)


def rename(user, sid, payload):
    with transaction() as db:
        row = owned(db, user, sid)
        if row.revision != payload.revision:
            raise AssistantError("revision_conflict", "对话名称已在另一处修改，请刷新后重试。", 409)
        row.title = payload.title.strip() or "新对话"
        row.revision += 1
        row.updated_at = time.time()
        return session_out(row)


def messages(user, sid, cursor=0, limit=50):
    with transaction() as db:
        row = owned(db, user, sid)
        settle_expired(db)
        query = select(Message).where(Message.session_id == sid)
        if cursor:
            query = query.where(Message.seq < cursor)
        rows = list(db.scalars(query.order_by(Message.seq.desc()).limit(limit + 1)))
        result = dict(session=session_out(row),
            next_cursor=rows[limit-1].seq if len(rows) > limit else None,
            active_run_id=db.scalar(select(Run.id).where(Run.session_id == sid, Run.state.in_(ACTIVE))))
    return dict(**result, items=[message_out(m, user) for m in reversed(rows[:limit])])


def admit(user, sid, payload):
    from app.schemas.assistant import canonical_request
    capabilities.require_enabled()
    frozen = canonical_request(payload)
    digest = hashlib.sha256(json.dumps(frozen, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    with transaction() as db:
        session = owned(db, user, sid)
        settle_expired(db)
        old = db.scalar(select(Run).where(Run.session_id == sid, Run.client_request_id == payload.client_request_id))
        if old:
            if old.request_hash != digest:
                raise AssistantError("idempotency_conflict", "相同请求编号不能用于不同内容。", 409)
            return dict(reused=True, run_id=old.id, state=old.state)
        capabilities.require_enabled(chat=True)
        capabilities.validate_options(payload)
        citations = help_registry.model_context(user, payload.page_context,
            strict=payload.intent in ('explain_page','explain_element')) if payload.page_context else []
        active = select(Run).join(Conversation).where(Run.state.in_(ACTIVE))
        if db.scalar(select(Run.id).where(Run.session_id == sid, Run.state.in_(ACTIVE))):
            raise AssistantError("session_busy", "这个对话还在回答中，请等待或停止后继续。", 409, True)
        count = db.scalar(select(func.count()).select_from(active.subquery()))
        own_count = db.scalar(select(func.count()).select_from(active.where(Conversation.owner_user_id == user.id).subquery()))
        if count >= settings.assistant_global_concurrency or own_count >= settings.assistant_per_user_concurrency:
            raise AssistantError("concurrency_limit", "当前正在回答的请求较多，请稍后再试。", 429, True, 2)
        from .storage import validate_attachments
        validate_attachments(db, user, sid, payload.attachment_ids)
        document_versions = {}
        if payload.document_ids:
            from .files import search_documents
            selected = search_documents(db, user, sid, payload.document_ids, payload.text, 'admission')
            document_versions = selected['report']['versions']
        reservation = reserve_budget(db, payload)
        rid, mid, lease = uuid4().hex, uuid4().hex, uuid4().hex
        now = time.time()
        seq = (db.scalar(select(func.max(Message.seq)).where(Message.session_id == sid)) or 0) + 1
        run = Run(id=rid, session_id=sid, client_request_id=payload.client_request_id, request_hash=digest,
            model=settings.assistant_model, state="connecting", lease_owner=lease, lease_expires_at=now+LEASE_SECONDS,
            cancel_requested=False, started_at=now, request_input=frozen, context_window={"reserved_tokens": reservation})
        db.add(run)
        db.flush()
        parts = [{"type": "text", "text": payload.text}] + [{"type": "image_ref", "attachment_id": a} for a in payload.attachment_ids]
        parts += [{"type": "document_ref", "file_id": ident, 'document_version': document_versions[ident]} for ident in payload.document_ids]
        ctx = payload.page_context.model_dump() if payload.page_context else None
        refs = [help_registry.citation(a) for a in citations]
        db.add(Message(id=uuid4().hex, session_id=sid, run_id=rid, seq=seq, role="user", content_parts=parts,
            status="completed", help_citations=refs, context_descriptor=ctx, created_at=now))
        db.add(Message(id=mid, session_id=sid, run_id=rid, seq=seq+1, role="assistant", content_parts=[],
            status="connecting", help_citations=refs, context_descriptor=ctx, created_at=now))
        session.updated_at = now
        if seq == 1 and session.title == "新对话":
            session.title = payload.text.strip()[:60] or "新对话"
            session.revision += 1
        return dict(reused=False, run_id=rid, message_id=mid, lease=lease, citations=[help_registry.public(a) for a in citations])


def control(rid, lease, *, parts=None, state=None, terminal=None, error=None, usage=UNSET, provider_id=None, window=None, citations=None):
    with transaction() as db:
        run = db.get(Run, rid)
        if not run or run.lease_owner != lease or run.state not in ACTIVE or run.lease_expires_at < time.time():
            raise AssistantError("lease_lost", "生成已中断，请查看保存的回答。", 409)
        session = db.get(Conversation, run.session_id)
        stop = run.cancel_requested or session.deletion_state != "active"
        if stop:
            terminal = "cancelled"
        elif not settings.assistant_enabled:
            terminal, error = "interrupted", "disabled"
        if parts is not None and session.deletion_state == "active":
            if terminal:
                # DB cancellation/kill-switch can win after the runtime's snapshot.
                # Finalize the exact saved evidence inside this terminal transaction.
                from copy import deepcopy
                from .evidence import now_iso
                parts = deepcopy(parts)
                for part in parts:
                    if part.get("type") != "evidence":
                        continue
                    changed = False
                    for activity in part["activities"]:
                        if activity["status"] == "running" or (stop and activity["status"] == "completed" and activity.get("finished_at") is None):
                            activity.update(status="completed" if terminal == "completed" else "cancelled" if terminal == "cancelled" else "failed", finished_at=now_iso())
                            changed = True
                    for citation in part["citations"]:
                        if citation["resolution"] == "pending":
                            citation["resolution"] = "unresolved"; changed = True
                    if part["search"]["execution"] == "pending":
                        part["search"].update(execution="unconfirmed" if terminal == "completed" else "failed", reason_code=error or terminal)
                        changed = True
                    if changed: part["revision"] += 1
            msg = db.scalar(select(Message).where(Message.run_id == rid, Message.role == "assistant"))
            msg.content_parts = list(parts)
        if terminal:
            run.state, run.finished_at, run.error_code = terminal, time.time(), error
        else:
            run.state = state or run.state
            run.lease_expires_at = time.time()+LEASE_SECONDS
        if usage is not UNSET:
            run.usage = usage
        if provider_id:
            run.provider_request_id = provider_id
        if window is not None:
            run.context_window = {**run.context_window, **window}
        if terminal:
            account_usage(db, run)
        msg = db.scalar(select(Message).where(Message.run_id == rid, Message.role == "assistant"))
        if msg:
            msg.status = run.state
            if citations is not None:
                msg.help_citations = citations
        return run.state


def snapshot(user, rid=None, sid=None, request_id=None):
    with transaction() as db:
        settle_expired(db)
        run = db.get(Run, rid) if rid else db.scalar(select(Run).where(Run.session_id == sid, Run.client_request_id == request_id))
        if not run:
            raise AssistantError("not_found", "没有找到这个请求。", 404)
        owned(db, user, run.session_id)
        rows = db.scalars(select(Message).where(Message.run_id == run.id).order_by(Message.seq)).all()
        result = dict(run_id=run.id, session_id=run.session_id, state=run.state, usage=run.usage, error_code=run.error_code,
            context_window=run.context_window)
    return dict(**result, items=[message_out(r, user) for r in rows])


def last_search_result(user):
    return recent_execution_status(user)["search"]["last_result"]


def recent_execution_status(user):
    result = {kind: dict(last_result=None, last_success=None, last_failure=None) for kind in ("chat", "search")}
    with database.SessionLocal() as db:
        query = select(Run).join(Conversation).where(Conversation.owner_user_id == user.id,
            Conversation.employment_epoch == epoch(user), Conversation.deletion_state == "active")
        if settings.assistant_retention_days:
            query = query.where(Conversation.updated_at >= time.time() - settings.assistant_retention_days * 86400)
        runs = db.scalars(query.order_by(Run.started_at.desc(), Run.id.desc()).limit(30)).all()
        for run in runs:
            row = db.scalar(select(Message).where(Message.run_id == run.id, Message.role == "assistant"))
            if not row:
                continue
            safe = message_out(row, user)
            if safe.get("unavailable"):
                continue
            evidence = next((p for p in safe["content_parts"] if p.get("type") == "evidence"), None)
            item = dict(run_id=run.id, state=run.state, code=run.error_code,
                        at=datetime.fromtimestamp(run.started_at, timezone.utc).isoformat())
            search = evidence.get("search") if evidence else None
            kind = "search" if search and search["execution"] not in ("not_requested", "skipped") else "chat"
            if kind == "search":
                item.update(search)
                # Legacy count-only confirmation is not evidence of a successful search.
                if item["evidence_level"] == "none" and item["execution"] == "confirmed":
                    item.update(execution="unconfirmed", reason_code="search_evidence_missing")
            bucket = result[kind]
            if bucket["last_result"] is None:
                bucket["last_result"] = item
            success = run.state == "completed" and (kind == "chat" or item["evidence_level"] != "none")
            field = "last_success" if success else "last_failure" if run.state in ("failed", "interrupted") or (kind == "search" and run.state == "completed") else None
            if field and bucket[field] is None:
                bucket[field] = item
    return result


def cancel(user, rid):
    with transaction() as db:
        settle_expired(db)
        run = db.get(Run, rid)
        if not run:
            raise AssistantError("not_found", "没有找到这个请求。", 404)
        owned(db, user, run.session_id)
        if run.state in ACTIVE:
            run.cancel_requested = True
        return dict(run_id=rid, state=run.state, cancel_requested=run.cancel_requested)


def remove(user, sid):
    with transaction() as db:
        row = owned(db, user, sid, pending=True)
        if row.deletion_state == "deleted":
            return True
        row.deletion_state, row.deleted_at = "pending", time.time()
        for run in db.scalars(select(Run).where(Run.session_id == sid, Run.state.in_(ACTIVE))):
            run.cancel_requested = True
    return cleanup(sid)


def cleanup(sid):
    from .storage import path_for
    with transaction() as db:
        settle_expired(db)
        row = db.get(Conversation, sid)
        if not row or row.deletion_state != "pending":
            return True
        if db.scalar(select(Run.id).where(Run.session_id == sid, Run.state.in_(ACTIVE))):
            return False
        from sqlalchemy import inspect
        from app.models.assistant import AssistantFile
        if inspect(db.bind).has_table(AssistantFile.__tablename__):
            from .files import erase
            for document in db.scalars(select(AssistantFile).where(AssistantFile.session_id == sid)):
                erase(db, document)
        for attachment in db.scalars(select(Attachment).where(Attachment.session_id == sid)):
            try:
                path_for(attachment.storage_key).unlink(missing_ok=True)
            except OSError:
                return False
        for model in (Attachment, Message, Run):
            db.execute(delete(model).where(model.session_id == sid))
        # Preserve an empty create-key tombstone for idempotency, without private content.
        row.title, row.deletion_state = "", "deleted"
        return True


def cleanup_pending(user=None):
    with database.SessionLocal() as db:
        query = select(Conversation.id).where(Conversation.deletion_state == "pending")
        if user:
            query = query.where(Conversation.owner_user_id == user.id, Conversation.employment_epoch == epoch(user))
        ids = db.scalars(query.limit(20)).all()
    return {sid: cleanup(sid) for sid in ids}


def expire_retention(user=None):
    if settings.assistant_retention_days is None:
        return 0
    with transaction() as db:
        query = select(Conversation).where(Conversation.deletion_state == "active",
            Conversation.updated_at < time.time()-settings.assistant_retention_days*86400)
        if user:
            query = query.where(Conversation.owner_user_id == user.id, Conversation.employment_epoch == epoch(user))
        rows = db.scalars(query.limit(20)).all()
        for row in rows:
            row.deletion_state, row.deleted_at = "pending", time.time()
            for run in db.scalars(select(Run).where(Run.session_id == row.id, Run.state.in_(ACTIVE))):
                run.cancel_requested = True
        return len(rows)
