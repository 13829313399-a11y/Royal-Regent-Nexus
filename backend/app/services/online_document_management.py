"""Owner-managed immutable history, recoverable deletion and protection."""
import hashlib
import json
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import select, text

from app.models.online_documents import OnlineDocumentEvent as Event, OnlineDocumentRevision as Revision
from app.services import online_documents as service, online_document_protection as protection
from app.services.document_tools import storage


def verify_evidence_guards(connection):
    if connection.dialect.name == "sqlite":
        definitions = dict(connection.execute(text("SELECT name, sql FROM sqlite_master WHERE type='trigger'")).all())
        for table in ("online_document_revisions", "online_document_events"):
            for action in ("update", "delete"):
                sql = " ".join(definitions.get(f"{table}_no_{action}", "").lower().split())
                if f"before {action} on {table}" not in sql or "raise(abort," not in sql or "when " in sql:
                    raise RuntimeError("在线文档历史或操作记录的不可变保护缺失，请修复迁移后启动")
    elif connection.dialect.name == "postgresql":
        rows = connection.execute(text("""SELECT c.relname, t.tgname, t.tgenabled, pg_get_triggerdef(t.oid), pg_get_functiondef(t.tgfoid)
            FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
            WHERE c.relname IN ('online_document_revisions','online_document_events') AND NOT t.tgisinternal"""))
        guards = {r[0]: r for r in rows if r[1] == r[0] + "_immutable"}
        for table in ("online_document_revisions", "online_document_events"):
            row = guards.get(table)
            if not row or row[2] not in {"O", "A"} or "BEFORE DELETE OR UPDATE" not in row[3] or "RAISE EXCEPTION" not in row[4]:
                raise RuntimeError("在线文档历史或操作记录的不可变保护缺失，请修复迁移后启动")


def audit(db, doc, user, kind, details=None, *, command_id=None, fingerprint=""):
    db.add(Event(id=service.uid(), document_id=doc.id, kind=kind, actor_id=user.id,
                 actor_name=user.display_name, actor_epoch=service.epoch(user), revision=doc.revision,
                 details=details or {}, command_id=command_id, fingerprint=fingerprint, created_at=datetime.now(timezone.utc).isoformat(timespec="microseconds")))


def require_owner(doc, user):
    if service.access(doc, user) != "owner":
        raise HTTPException(403, "只有文件拥有者可以管理历史、回收站和保护设置")


def records(db, doc, user, *, before=0):
    require_owner(doc, user)
    # Stable keyset paging; no truncation disguised as a complete history.
    query = select(Revision).where(Revision.document_id == doc.id)
    if before:
        query = query.where(Revision.revision < before)
    rows = db.scalars(query.order_by(Revision.revision.desc()).limit(51)).all()
    return {"items": [{"revision": r.revision, "byte_size": r.byte_size, "created_at": r.created_at,
                       "actor_id": r.actor_id, "current": r.revision == doc.revision} for r in rows[:50]],
            "next_before": rows[49].revision if len(rows) > 50 else None}


def event_records(db, doc, user, before=""):
    require_owner(doc, user)
    query = select(Event).where(Event.document_id == doc.id)
    if before:
        cursor = db.scalar(select(Event).where(Event.document_id == doc.id, Event.id == before))
        if not cursor:
            raise HTTPException(422, "操作记录分页位置已失效，请刷新")
        from sqlalchemy import or_, and_
        query = query.where(or_(Event.created_at < cursor.created_at,
                                and_(Event.created_at == cursor.created_at, Event.id < cursor.id)))
    rows = db.scalars(query.order_by(Event.created_at.desc(), Event.id.desc()).limit(51)).all()
    return {"items": [{"id": r.id, "kind": r.kind, "actor_name": r.actor_name, "revision": r.revision,
                       "details": r.details, "created_at": r.created_at} for r in rows[:50]],
            "next_before": rows[49].id if len(rows) > 50 else None}


def version(db, doc, user, number):
    require_owner(doc, user)
    row = db.scalar(select(Revision).where(Revision.document_id == doc.id, Revision.revision == number))
    if not row:
        raise HTTPException(404, "历史版本不存在")
    return row


def read_asset(row):
    try:
        data = storage.resolve(row.storage_key).read_bytes()
    except OSError:
        raise HTTPException(409, "版本文件暂不可用，请保留记录并联系管理员检查备份") from None
    if len(data) != row.byte_size or hashlib.sha256(data).hexdigest() != row.sha256:
        raise HTTPException(409, "版本文件校验未通过，已停止操作，请联系管理员")
    return data


def command(db, doc, user, kind, payload):
    require_owner(doc, user)
    fingerprint = hashlib.sha256(json.dumps({"kind": kind, "payload": payload}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    previous = db.scalar(select(Event).where(Event.document_id == doc.id, Event.command_id == payload["request_id"]))
    if previous:
        if previous.actor_id != user.id or previous.actor_epoch != service.epoch(user) or previous.fingerprint != fingerprint:
            raise HTTPException(409, "该操作编号已用于其他请求，请重新打开操作面板")
        db.rollback()
        result = service.summary(doc, user)
        if doc.state_version != previous.details.get("result", {}).get("state_version"):
            result["operation_notice"] = "原操作已完成，但文档后来又有变化，请以当前列表为准"
        return result
    if doc.state_version != payload["expected_version"]:
        raise HTTPException(409, "文档已在其他窗口变更，请关闭面板并刷新后重试")
    if doc.editor_key or doc.pending_save or doc.save_error:
        raise HTTPException(409, "请所有人保存并关闭编辑窗口，确认保存成功后再操作")
    if bool(doc.deleted_at) != (kind == "recover"):
        raise HTTPException(409, "文档状态已变化，请刷新列表")
    details = {}
    if kind == "trash":
        doc.deleted_at = service.now()
        doc.grants = []
        doc.access_generation += 1
    elif kind == "recover":
        doc.deleted_at = ""
        doc.grants = []
        doc.access_generation += 1
    elif kind == "restore":
        if doc.protection:
            raise HTTPException(409, "请先解除公式区域保护，再恢复历史版本；恢复后可重新设置保护")
        target = version(db, doc, user, payload["revision"])
        data = read_asset(target)
        protocol_validate(data, doc.format)
        doc.protection = ({"rules": target.protection["rules"], "baseline_revision": doc.revision + 1,
                           "sha256": target.sha256} if target.protection else {})
        append_version(db, doc, user, data)
        details = {"restored_revision": target.revision}
    elif kind == "protection":
        if doc.format != "xlsx":
            raise HTTPException(422, "公式区域保护仅适用于 XLSX 表格")
        if payload["enabled"] == bool(doc.protection):
            raise HTTPException(409, "保护状态已变化，请重新打开设置")
        data = read_asset(doc)
        if payload["enabled"]:
            data = protection.enable(data, payload["rules"])
            doc.protection = {"rules": payload["rules"], "baseline_revision": doc.revision + 1, "sha256": hashlib.sha256(data).hexdigest()}
            append_version(db, doc, user, data)
        else:
            data = protection.disable(data)
            doc.protection = {}
            append_version(db, doc, user, data)
        details = {"enabled": payload["enabled"], "rules": payload["rules"] if payload["enabled"] else []}
    else:
        raise HTTPException(422, "未知文档操作")
    doc.updated_at = service.now()
    doc.state_version += 1
    details["result"] = {"state_version": doc.state_version, "revision": doc.revision, "protected": bool(doc.protection), "deleted_at": doc.deleted_at}
    audit(db, doc, user, kind, details, command_id=payload["request_id"], fingerprint=fingerprint)
    db.commit()
    return service.summary(doc, user)


def protocol_validate(data, extension):
    from app.services.online_document_protocol import validate
    validate(data, extension)


def append_version(db, doc, user, data):
    protocol_validate(data, doc.format)
    doc.storage_key, doc.sha256 = service.write_blob(doc.id, data)
    doc.byte_size = len(data)
    doc.revision += 1
    service.revision(db, doc, user.id)


def protection_settings(db, doc, user):
    require_owner(doc, user)
    if doc.format != "xlsx":
        raise HTTPException(422, "公式区域保护仅适用于 XLSX 表格")
    return {"document": service.summary(doc, user), "sheets": protection.inspect(read_asset(doc)),
            "rules": doc.protection.get("rules", [])}
